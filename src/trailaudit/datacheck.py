"""What `trailaudit data-check` prints: three of the nine pre-registered properties, measured.

P3, P4 and P9. Each is stated as a property a competent scorer should have, and
each is reported HELD or VIOLATED with the size of the violation next to it,
because the direction of all three was already known before any code existed and
the magnitude was not.

P9 is the only one of the three that runs without the clone, off the committed
span index. P3 and P4 read the gold annotations, which this repository does not
commit, so without a clone they say they were not measured. A property that
quietly reports HELD because it could not look is worse than one that admits it.
"""

from __future__ import annotations

import textwrap
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from trailaudit import gold, paper, upstream
from trailaudit.gold import Annotation, ParseFailure

HELD = "HELD"
VIOLATED = "VIOLATED"
UNMEASURED = "not measured"

WIDTH = 96


@dataclass(frozen=True)
class Gold:
    annotations: list[Annotation]
    failures: list[ParseFailure]
    vocabulary: Counter[str]
    taxonomy: tuple[str, ...]
    normalise: Callable[[str], str]


@dataclass(frozen=True)
class Finding:
    name: str
    claim: str
    verdict: str
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
        return Finding("P3", claim, UNMEASURED, [_needs_clone()])
    parsed = len(annotated.annotations)
    refused = len(annotated.failures)
    if not refused:
        return Finding("P3", claim, HELD, [f"{parsed} files, all of them parse"])
    verb = "does not" if refused == 1 else "do not"
    return Finding(
        "P3",
        claim,
        VIOLATED,
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
        return Finding("P4", claim, UNMEASURED, [_needs_clone()])
    labels = list(annotated.taxonomy)
    off = gold.off_taxonomy(annotated.vocabulary, labels)
    errors = sum(annotated.vocabulary.values())
    if not off:
        return Finding("P4", claim, HELD, [f"{len(annotated.vocabulary)} spellings, all labels"])
    return Finding(
        "P4",
        claim,
        VIOLATED,
        [
            f"{len(annotated.vocabulary)} distinct spellings over {errors} errors, "
            f"against {len(labels)} labels",
            f"{len(off)} are not a label, covering "
            f"{sum(annotated.vocabulary[one] for one in off)} errors",
        ],
    )


def p9(measured: dict[str, dict[str, int]]) -> Finding:
    claim = "the repository's split sizes match the paper's Table 5"
    disagreeing = [
        split.name
        for split in upstream.SPLITS
        if paper.published_for(split.name).traces != measured[split.name]["traces"]
    ]
    return Finding(
        "P9",
        claim,
        VIOLATED if disagreeing else HELD,
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


def report(clone: Path | None, index: dict[str, dict[str, list[str]]]) -> tuple[list[str], bool]:
    """Everything data-check prints, and whether any property came back VIOLATED."""
    annotated = read_gold(clone) if clone is not None else None
    findings = [p3(annotated), p4(annotated), p9(measure(clone, index))]

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
