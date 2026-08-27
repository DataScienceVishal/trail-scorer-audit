"""What `trailaudit data-check` prints: three of the nine pre-registered properties, measured.

P3, P4 and P9. Each is stated as a property a competent scorer should have, and
each is reported HELD or VIOLATED with the size of the violation next to it,
because the direction of all three was already known before any code existed and
the magnitude was not.

P9 is the only one of the three that runs without the clone, off the committed
span index. P3 and P4 read the gold annotations, which this repository does not
commit, so without a clone they say they were not measured. A property that
quietly reports HELD because it could not look is worse than one that admits it.

The run also writes `results/datacheck.json`, which is what the README's tables
are rendered from. Slices 2 and 3 committed an artifact each and this one did
not, because slice 1 printed its findings and stopped. That left the three
oldest findings as the only ones a reader had to take on trust, and the report
command in slice 4 needs them in the same form as the rest.
"""

from __future__ import annotations

import textwrap
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from trailaudit import artifacts, gold, paper, upstream
from trailaudit.gold import Annotation, ParseFailure
from trailaudit.upstream import MissingClone

HELD = "HELD"
VIOLATED = "VIOLATED"
UNMEASURED = "not measured"

_NOT_MEASURED = "nothing looked, so nothing is claimed"

WIDTH = 96

COMMITTED = Path("results/datacheck.json")


@dataclass(frozen=True)
class Gold:
    annotations: list[Annotation]
    failures: list[ParseFailure]
    vocabulary: Counter[str]
    taxonomy: tuple[str, ...]
    normalise: Callable[[str], str]


@dataclass(frozen=True)
class Finding:
    """One pre-registered property, decided.

    `magnitude` is one line and it is what the README's conditions table prints.
    The pre-registration promised a direction for six of the nine and a size for
    none of them, so the size is the part that had to come out of a run, and
    keeping it here means the table and the terminal report cannot disagree
    about it. `lines` is the terminal evidence under the verdict and is free to
    be as long as it needs.
    """

    name: str
    claim: str
    verdict: str
    magnitude: str
    lines: list[str]

    def render(self) -> str:
        """The claim, then the verdict in a fixed column, then the evidence indented under it.

        Padding to 72 and then adding two spaces rather than padding to 74:
        identical for every claim that fits, and a claim that does not fit still
        has a gap before its verdict instead of running into it. P6's claim is
        the one that does not fit.
        """
        head = f"{self.name}  {self.claim}"
        body = [f"    {line}".rstrip() for line in self.lines]
        return "\n".join([f"{head:<72}  {self.verdict}", *body])


def read_gold(clone: Path) -> Gold:
    annotations, failures = gold.read_all(clone)
    taxonomy = upstream.taxonomy(clone)
    return Gold(
        annotations=annotations,
        failures=failures,
        vocabulary=gold.vocabulary(annotations),
        taxonomy=taxonomy,
        normalise=gold.binder(upstream.load_scorer(clone).normalize_category, taxonomy),
    )


def p3(annotated: Gold | None) -> Finding:
    claim = "every gold annotation file parses as JSON"
    if annotated is None:
        return Finding("P3", claim, UNMEASURED, _NOT_MEASURED, [_needs_clone()])
    parsed = len(annotated.annotations)
    refused = len(annotated.failures)
    if not refused:
        return Finding(
            "P3", claim, HELD, f"{parsed} files, all of them parse", [f"{parsed} files parse"]
        )
    verb = "does not" if refused == 1 else "do not"
    return Finding(
        "P3",
        claim,
        VIOLATED,
        f"{parsed} of {parsed + refused} gold files parse, so every published average "
        f"divides by {parsed}",
        [
            f"{parsed + refused} files on disk, {parsed} parse, {refused} {verb}",
            *(str(one) for one in annotated.failures),
            *wrapped(
                f"the scorer catches that at line 242 and continues, so every published "
                f"average divides by {parsed}"
            ),
        ],
    )


def p4(annotated: Gold | None) -> Finding:
    claim = "every gold category string is one of the taxonomy labels"
    if annotated is None:
        return Finding("P4", claim, UNMEASURED, _NOT_MEASURED, [_needs_clone()])
    labels = list(annotated.taxonomy)
    off = gold.off_taxonomy(annotated.vocabulary, labels)
    errors = sum(annotated.vocabulary.values())
    spellings = len(annotated.vocabulary)
    if not off:
        return Finding(
            "P4",
            claim,
            HELD,
            f"{spellings} spellings, all labels",
            [f"{spellings} spellings, all labels"],
        )
    return Finding(
        "P4",
        claim,
        VIOLATED,
        f"{len(off)} of {spellings} gold spellings are not a label, covering "
        f"{sum(annotated.vocabulary[one] for one in off)} of {errors} errors",
        [
            f"{len(annotated.vocabulary)} distinct spellings over {errors} errors, "
            f"against {len(labels)} labels",
            f"{len(off)} are not a label, covering "
            f"{sum(annotated.vocabulary[one] for one in off)} errors",
        ],
    )


def p9(measured: dict[str, dict[str, int]]) -> Finding:
    claim = "the repository's split sizes match the paper's Table 5"
    comparable, disagreeing = cells(measured)
    return Finding(
        "P9",
        claim,
        VIOLATED if disagreeing else HELD,
        f"{len(disagreeing)} of the {comparable} Table 5 cells this repository can compare "
        f"disagree with the tree at {upstream.PINNED_COMMIT[:12]}",
        [
            f"{paper.CITATION}, against the tree at {upstream.PINNED_COMMIT[:12]}",
            *table_5_rows(measured),
            "",
            *wrapped(
                f"the paper's prose says {paper.ABSTRACT_TRACES} traces and "
                f"{paper.ABSTRACT_ERRORS} errors, and Table 5's own rows sum to "
                f"{sum(row.traces for row in paper.TABLE_5)} and "
                f"{sum(row.errors for row in paper.TABLE_5)}"
            ),
            *wrapped(
                "the last three rows are counted over the gold files that parse, so GAIA's "
                "leaves out the errors in the one that does not"
            ),
        ],
    )


def cells(measured: dict[str, dict[str, int]]) -> tuple[int, list[str]]:
    """How many of Table 5's ten cells can be compared, and which of those disagree.

    Three of the five rows need the gold annotations, so without a clone only
    four cells are comparable and the verdict rests on those. Counting a row
    nobody measured as agreeing is the failure mode this whole file is written
    against.
    """
    comparable = 0
    disagreeing = []
    for split in upstream.SPLITS:
        published = paper.published_for(split.name)
        for row in paper.ROWS:
            here = measured[split.name].get(row)
            if here is None:
                continue
            comparable += 1
            if here != getattr(published, row):
                disagreeing.append(f"{split.name} {paper.LABELS[row]}")
    return comparable, disagreeing


def _needs_clone() -> str:
    return "needs the gold annotations. Run `trailaudit fetch`"


def wrapped(sentence: str) -> list[str]:
    """Findings indent their lines by four, so the wrap has to leave room for that."""
    return textwrap.wrap(sentence, WIDTH - 4)


def table_5_rows(measured: dict[str, dict[str, int]]) -> list[str]:
    columns = [paper.compare(split.name, measured[split.name]) for split in upstream.SPLITS]
    rows = [
        f"{'':<22}" + "".join(f"{split.name:>24}" for split in upstream.SPLITS),
        f"{'':<22}" + "".join(f"{'paper / here':>24}" for _ in upstream.SPLITS),
    ]
    for position, name in enumerate(paper.ROWS):
        cells = ""
        for column in columns:
            _, published, here = column[position]
            shown = f"{here:,}" if here is not None else "unmeasured"
            cells += f"{published:,} / {shown}".rjust(24)
        rows.append(f"{paper.LABELS[name]:<22}{cells}")
    return rows


def drift_table(
    counted: Counter[str], taxonomy: Iterable[str], normalise: Callable[[str], str]
) -> list[str]:
    """Every gold spelling that is not a label, and where the normaliser sends it."""
    labels = list(taxonomy)
    known = set(labels)
    rows = []
    for spelling in gold.off_taxonomy(counted, labels):
        lands = normalise(spelling)
        fate = lands if lands in known else f"nothing, kept as {lands!r}"
        rows.append(f"{spelling!r:<38} x{counted[spelling]:<4} -> {fate}")
    return rows


def distribution(
    counted: Counter[str], taxonomy: Iterable[str], normalise: Callable[[str], str]
) -> list[str]:
    """Gold errors per category, as written and after the normaliser.

    Both columns, because they are different numbers and publishing one of them
    alone makes the gap invisible. `Formatting Errors` gains an error on the way
    through, from a gold entry that says `Formatting Error`, and either column is
    a defensible answer to "the gold distribution" as long as it says which one
    it is.
    """
    known = set(taxonomy)
    after = gold.normalised_counts(counted, normalise)
    total = sum(counted.values())
    rows = [f"{'category':<38}{'as written':>12}{'normalised':>12}{'share':>8}"]
    outside = False
    for label, times in after.most_common():
        mark = ""
        if label not in known:
            outside = True
            mark = "  *"
        exact = counted.get(label, 0)
        rows.append(f"{label:<38}{exact:>12}{times:>12}{times / total:>8.1%}{mark}")
    if outside:
        rows += [
            "",
            *textwrap.wrap(
                "* not a taxonomy label, so `as written` is 0: the normaliser found no match "
                "and handed the gold spelling back lowercased.",
                WIDTH - 2,
            ),
        ]
    return rows


def measure(
    clone: Path | None, index: dict[str, dict[str, list[str]]]
) -> dict[str, dict[str, int]]:
    """Table 5's five columns per split, from the committed index and, where present, the gold.

    Errors, unique error spans and traces with an error are counted over the
    files that parse, which is the population the scorer works on. For GAIA that
    leaves out the errors in the file with the trailing comma, and the P3 block
    above is what says so.
    """
    counted = {
        split.name: {
            "traces": len(index[split.name]),
            "spans": sum(len(ids) for ids in index[split.name].values()),
        }
        for split in upstream.SPLITS
    }
    if clone is None:
        return counted
    for split in upstream.SPLITS:
        annotations, _ = gold.read_directory(clone / split.annotations, split.name)
        locations = {one for annotation in annotations for one in annotation.locations}
        counted[split.name].update(
            errors=sum(len(one.categories) for one in annotations),
            unique_error_spans=len(locations),
            traces_with_errors=sum(1 for one in annotations if one.categories),
        )
    return counted


@dataclass(frozen=True)
class Checked:
    """One pass over the pinned tree, shared by the printed report and the artifact.

    `annotated` and `corpus` are None when the command was told there is no
    clone, which is the only supported way to run this offline. The artifact
    cannot be written in that state and says so rather than committing a file
    with three of Table 5's rows missing.
    """

    annotated: Gold | None
    measured: dict[str, dict[str, int]]
    corpus: tuple[int, int] | None


def inspect(clone: Path | None, index: dict[str, dict[str, list[str]]]) -> Checked:
    return Checked(
        annotated=read_gold(clone) if clone is not None else None,
        measured=measure(clone, index),
        corpus=upstream.corpus_size(clone) if clone is not None else None,
    )


def findings_for(checked: Checked) -> list[Finding]:
    return [p3(checked.annotated), p4(checked.annotated), p9(checked.measured)]


def report(checked: Checked) -> tuple[list[str], bool]:
    """Everything data-check prints, and whether any property came back VIOLATED."""
    annotated = checked.annotated
    findings = findings_for(checked)

    lines: list[str] = []
    for finding in findings:
        lines += [finding.render(), ""]

    if annotated is not None:
        lines.append("gold spellings that are not a taxonomy label, and where they land")
        drifted = drift_table(annotated.vocabulary, annotated.taxonomy, annotated.normalise)
        lines += [("  " + row).rstrip() for row in drifted]
        lost = gold.dropped(annotated.vocabulary, list(annotated.taxonomy), annotated.normalise)
        lines += [
            "",
            *textwrap.wrap(
                f"{sum(lost.values())} gold errors across {len(lost)} spellings normalise to "
                f"nothing in the taxonomy. Each keeps its place in gt_loc_cat_pairs under its "
                f"lowercased spelling, so it stays in the joint accuracy denominator where the "
                f"correct label cannot match it, and it never sets a bit in the per-category "
                f"vectors at lines 64 to 66.",
                WIDTH,
            ),
            "",
            "gold errors per category",
            *(
                ("  " + row).rstrip()
                for row in distribution(
                    annotated.vocabulary, annotated.taxonomy, annotated.normalise
                )
            ),
        ]

    return lines, any(finding.verdict == VIOLATED for finding in findings)


def verdicts(findings: Iterable[Finding]) -> dict:
    """The properties block every committed artifact carries.

    Written by the command that decided them rather than derived a second time
    from the numbers in the file. The README's conditions table reads this, so a
    verdict in the prose and a verdict in the terminal are the same string, and
    `--check` catches a flip the way it catches a moved figure.
    """
    return {
        one.name: {"claim": one.claim, "verdict": one.verdict, "magnitude": one.magnitude}
        for one in findings
    }


def artifact(checked: Checked, index_sha256: str) -> dict:
    """P3, P4 and P9 as figures, so the README can quote them without the 186 MB."""
    annotated = checked.annotated
    if annotated is None or checked.corpus is None:
        raise MissingClone(
            "data-check --no-clone cannot write the artifact: P3 and P4 were not measured and "
            "three of Table 5's five rows are missing. Run `trailaudit fetch` first"
        )
    labels = list(annotated.taxonomy)
    off = gold.off_taxonomy(annotated.vocabulary, labels)
    lost = gold.dropped(annotated.vocabulary, labels, annotated.normalise)
    files, size = checked.corpus
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
        "index_sha256": index_sha256,
        "table_5": paper.CITATION,
        "properties": verdicts(findings_for(checked)),
        "corpus": {"sha256": upstream.CORPUS_SHA256, "files": files, "bytes": size},
        "gold_files": {
            "on_disk": len(annotated.annotations) + len(annotated.failures),
            "parsed": len(annotated.annotations),
        },
        "unreadable": [
            {
                "split": one.split,
                "trace": one.trace,
                "line": one.line,
                "column": one.column,
                "character": one.character,
            }
            for one in annotated.failures
        ],
        "vocabulary": {
            "labels": len(labels),
            "spellings": len(annotated.vocabulary),
            "errors": sum(annotated.vocabulary.values()),
            "off_taxonomy": len(off),
            "errors_off_taxonomy": sum(annotated.vocabulary[one] for one in off),
            "dropped_spellings": len(lost),
            "dropped_errors": sum(lost.values()),
        },
        "splits": {
            split.name: {
                "here": checked.measured[split.name],
                "paper": {row: getattr(paper.published_for(split.name), row) for row in paper.ROWS},
            }
            for split in upstream.SPLITS
        },
        "paper_prose": {"traces": paper.ABSTRACT_TRACES, "errors": paper.ABSTRACT_ERRORS},
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit data-check")
