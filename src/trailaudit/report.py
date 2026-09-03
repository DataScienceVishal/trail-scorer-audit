"""Rendering every figure the README quotes, out of the five committed artifacts.

Each block lives between a pair of HTML comments that markdown does not show:

    <!-- trailaudit:headline -->
    ...generated...
    <!-- /trailaudit:headline -->

`trailaudit report --format md` replaces the body of every pair. `--check`
compares instead and exits 1 on a difference, which is what CI runs. So a figure
in the prose can only move by rerunning the measurement and committing what came
out.

The guard that matters is `line_up`, and it refuses in both directions. A marker
with no generator behind it is the failure that hides: nothing regenerates it,
`--check` has nothing to compare it against, and the block sits there reading
like a maintained table while it slowly stops being true. `twicerun` shipped
this same mechanism with a scan that looked only for the names its generator
already offered, so the test compared a dict against a subset of itself and
could not fail, and deleting a generator while leaving its marker was invisible
for the life of the project. The scan here matches any name, and a generator
whose block is missing from the file is refused just as loudly.

One more thing is checked that has nothing to do with markers. Every score in
this project is written to three decimal places, or four in the weighted F1
column, so a hand-typed one is easy to find: `loose_scores` looks for both
shapes outside the generated blocks and reports it. There is no honest reason
for a figure to be there.
"""

from __future__ import annotations

import json
import re
import textwrap
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from trailaudit import adversarial, catf1, datacheck, normaliser, pairing, spans, upstream
from trailaudit.artifacts import Stale

MARKER = re.compile(r"^<!--\s*(/?)trailaudit:([a-z0-9-]+)\s*-->$")

README = Path("README.md")

# P1 to P9, pre-registered before any code existed. The report refuses to render
# a conditions table that does not cover all nine exactly once.
PROPERTIES = tuple(f"P{number}" for number in range(1, 10))

# Anything that reads as a score: 0.973, 1.000, and the four-place weighted F1
# at 0.4725. Three places was the original rule and the fourth column broke it:
# the trailing \b cannot match a four-digit fraction, so a hand-typed 0.9999 in
# prose passed while 0.990 was caught. Line numbers, byte counts and arXiv
# identifiers still do not match, and no figure of either shape belongs in prose.
SCORE = re.compile(r"\b[01]\.\d{3,4}\b")

# Sixteen hex digits for a span, thirty-two for a trace, forty for a commit,
# sixty-four for a digest.
IDENTIFIER = re.compile(r"[0-9a-f]{16,64}")

WRAP = 79


class MarkerError(ValueError):
    """The README and the generators do not describe the same set of blocks."""


@dataclass(frozen=True)
class Sources:
    """The committed files every generated figure comes out of, and nothing else.

    No clone, no network, no gold. `trailaudit report --check` therefore runs on
    a fresh clone in CI, which is the only reason the drift check is worth
    having: a guard that needs the 186 MB would never run where it matters.
    """

    root: Path
    datacheck: dict
    adversarial: dict
    normaliser: dict
    catf1: dict
    pairing: dict
    index: dict


# The four artifacts whose command takes --index. `pairing` is not one of them:
# its trace is constructed and it reads the gold directly, so there is no index
# behind it to record. Naming the four rather than checking whichever files
# happen to carry the key means an artifact that stopped carrying it fails the
# comparison instead of skipping it.
FROM_THE_INDEX = frozenset(
    str(one)
    for one in (
        datacheck.COMMITTED,
        adversarial.COMMITTED,
        normaliser.COMMITTED,
        catf1.COMMITTED,
    )
)


def load(root: Path = Path(".")) -> Sources:
    loaded = Sources(
        root=root,
        datacheck=datacheck.load(root / datacheck.COMMITTED),
        adversarial=adversarial.load(root / adversarial.COMMITTED),
        normaliser=normaliser.load(root / normaliser.COMMITTED),
        catf1=catf1.load(root / catf1.COMMITTED),
        pairing=pairing.load(root / pairing.COMMITTED),
        index=spans.load(root / spans.COMMITTED),
    )
    committed_index = spans.digest(loaded.index)
    for name, artifact in every_artifact(loaded):
        if artifact["scorer_sha256"] != upstream.SCORER_SHA256:
            raise Stale(
                f"{name} was produced against a scorer hashing to "
                f"{artifact['scorer_sha256']}, and the audit is pinned to "
                f"{upstream.SCORER_SHA256}"
            )
        if name in FROM_THE_INDEX and artifact.get("index_sha256") != committed_index:
            raise Stale(
                f"{name} was produced against a span index hashing to "
                f"{artifact.get('index_sha256')}, and {spans.COMMITTED} hashes to "
                f"{committed_index}. Rerun it against the committed index"
            )
    return loaded


def every_artifact(src: Sources) -> list[tuple[str, dict]]:
    """The five results files, in the order their commands were written."""
    return [
        (str(datacheck.COMMITTED), src.datacheck),
        (str(adversarial.COMMITTED), src.adversarial),
        (str(normaliser.COMMITTED), src.normaliser),
        (str(catf1.COMMITTED), src.catf1),
        (str(pairing.COMMITTED), src.pairing),
    ]


def properties(src: Sources) -> dict[str, dict]:
    """P1 to P9, gathered from whichever command decided each one.

    Refuses a set that is not exactly the nine. Two commands claiming the same
    property would mean two verdicts for one pre-registration, and a missing one
    would leave a row out of the table with nothing to notice it had gone.
    """
    gathered: dict[str, dict] = {}
    for name, artifact in every_artifact(src):
        for number, decided in artifact["properties"].items():
            if number in gathered:
                raise MarkerError(f"{number} is decided twice, the second time by {name}")
            gathered[number] = decided
    missing = [one for one in PROPERTIES if one not in gathered]
    unknown = [one for one in gathered if one not in PROPERTIES]
    if missing or unknown:
        raise MarkerError(
            f"the artifacts decide {sorted(gathered)}, and the pre-registration is "
            f"{list(PROPERTIES)}"
        )
    return {one: gathered[one] for one in PROPERTIES}


def table(head: Iterable[str], rows: Iterable[Iterable[str]]) -> list[str]:
    columns = list(head)
    return [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
    ]


def paragraph(sentence: str) -> list[str]:
    return textwrap.wrap(" ".join(sentence.split()), WRAP)


def megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


def pin(src: Sources) -> list[str]:
    """The four digests a reader can check the audit against, including its own input.

    The index line is the only one of the four that covers something this
    repository wrote. It is here because every artifact records the same digest,
    so a reader can tell that the run behind a figure read the index that is
    committed and not one built for the occasion.
    """
    corpus = src.datacheck["corpus"]
    return [
        "```",
        f"commit  {upstream.PINNED_COMMIT}",
        f"scorer  {upstream.SCORER_SHA256}  {upstream.SCORER}",
        f"corpus  {corpus['sha256']}  {corpus['files']} files, {megabytes(corpus['bytes'])}",
        f"index   {spans.digest(src.index)}  {spans.COMMITTED}",
        "```",
    ]


def conditions(src: Sources) -> list[str]:
    return table(
        ("property", "as written before any code existed", "verdict", "how far off it is"),
        (
            (name, one["claim"], one["verdict"], one["magnitude"])
            for name, one in properties(src).items()
        ),
    )


def eleven_percent(src: Sources) -> list[str]:
    """The abstract's headline against the two cells this audit compares with.

    Every number here is divided out of the adversarial artifact, including the
    two weightings, so the arithmetic is in the document rather than only in
    paper.py where nobody reading the README would find it. The 11 percent
    itself is the one figure in this file that no run of anything produces: it is
    TRAIL's prose, transcribed.
    """
    splits = src.adversarial["splits"]
    best = {
        split: one["best_published"]["joint_accuracy"]["value"] for split, one in splits.items()
    }
    quoted = src.adversarial["paper_prose"]["combined_joint"]
    plain = sum(best.values()) / len(best)
    files = _weighted(best, {split: one["gold_files_scored"] for split, one in splits.items()})
    errors = _weighted(best, {split: one["gold_errors"] for split, one in splits.items()})
    return paragraph(
        f"The {quoted:.0%} is the abstract's, and it is not a cell in Table 1. Table 1's best "
        f"joint accuracy is "
        f"{', '.join(f'{value:.3f} on {split}' for split, value in best.items())}, which the "
        f"paper's conclusion quotes rounded, at "
        f"{' and '.join(f'{value:.0%}' for value in best.values())}. The plain mean of the two "
        f"is {plain:.1%}, which rounds to {plain:.0%} and reaches {quoted:.0%} only by "
        f"truncation, and weighting the splits moves it further off rather than closer: by the "
        f"gold files the scorer loads it is {files:.1%}, by the errors in those files "
        f"{errors:.1%}. calculate_scores.main() is called once per split and returns one number "
        f"per split, so that is the granularity this audit compares at, per split against the "
        f"two cells above."
    )


def _weighted(values: dict[str, float], weights: dict[str, int]) -> float:
    return sum(values[split] * weights[split] for split in values) / sum(weights.values())


def _above_the_fold(src: Sources) -> tuple[str, dict]:
    """The one split the first screen quotes, named out of the artifact rather than typed.

    GAIA today, because it is first in `upstream.SPLITS` and the larger of the
    two. Both blocks above the fold read it through here and print the name they
    were handed, so the opening sentence and the three-row table under it cannot
    end up describing different splits.
    """
    return next(iter(src.adversarial["splits"].items()))


def claim(src: Sources) -> list[str]:
    """The opening sentence, with the three figures it rests on.

    Generated for the same reason the tables are. `loose_scores` refuses a score
    typed into prose anywhere in the file, and the first thing a reader sees is
    the worst place for a figure that stopped being true.
    """
    split, one = _above_the_fold(src)
    blind = one["predictors"][adversarial.HEADLINE.name]
    best = one["best_published"]["joint_accuracy"]["value"]
    return paragraph(
        f"`{adversarial.HEADLINE.name}` never opens a span, never looks at the gold and does not "
        f"know what an error is. Run through TRAIL's own unmodified scorer on {split} it scores "
        f"**{blind['joint_accuracy']:.3f}** joint accuracy against **{best:.3f}** for the best "
        f"row in Table 1, by emitting **{blind['volume_ratio']:.1f}x** as many errors as the "
        f"answer key holds. Both headline metrics divide by the number of errors in the answer "
        f"key, never by the number the judge reported."
    )


def teaser(src: Sources) -> list[str]:
    """Three rows of the headline table, for a reader deciding whether to read the rest.

    The predictor that cannot read, the row it beats, and the ceiling. The
    volume ratio comes with them because it is the first objection anybody
    raises, and an objection answered two clicks further down is an objection
    that stands.
    """
    split, one = _above_the_fold(src)
    blind = one["predictors"][adversarial.HEADLINE.name]
    best = one["best_published"]
    ceiling = f"{one['reachable_ceiling']:.3f}"
    return table(
        (
            f"{split}, {one['gold_files_scored']} gold files, {one['gold_errors']} gold errors",
            "joint",
            "location",
            "errors emitted",
            "per gold error",
        ),
        (
            (
                f"`{adversarial.HEADLINE.name}`, which cannot read",
                f"{blind['joint_accuracy']:.3f}",
                f"{blind['location_accuracy']:.3f}",
                f"{blind['predicted_errors']:,}",
                f"{blind['volume_ratio']:.1f}x",
            ),
            (
                "best published, Table 1",
                f"{best['joint_accuracy']['value']:.3f}",
                f"{best['location_accuracy']['value']:.3f}",
                "",
                "",
            ),
            ("reachable by anything at all", ceiling, ceiling, "", ""),
        ),
    )


def headline(src: Sources) -> list[str]:
    lines: list[str] = []
    for split, one in src.adversarial["splits"].items():
        rows = [
            (
                f"`{name}`",
                row["reads"],
                f"{row['joint_accuracy']:.3f}",
                f"{row['location_accuracy']:.3f}",
                f"{row['predicted_errors']:,}",
                f"{row['volume_ratio']:.1f}x",
            )
            for name, row in one["predictors"].items()
        ]
        best = one["best_published"]
        rows.append(
            (
                "best published, Table 1",
                "",
                f"{best['joint_accuracy']['value']:.3f}",
                f"{best['location_accuracy']['value']:.3f}",
                "",
                "",
            )
        )
        ceiling = f"{one['reachable_ceiling']:.3f}"
        rows.append(("reachable by anything at all", "", ceiling, ceiling, "", ""))
        lines += [
            f"{split}, {one['gold_files_scored']} of {one['gold_files']} gold files scored, "
            f"{one['gold_errors']} gold errors in them:",
            "",
            *table(
                ("predictor", "reads", "joint", "location", "errors emitted", "per gold error"),
                rows,
            ),
            "",
        ]
    return lines[:-1]


def absent_locations(src: Sources) -> list[str]:
    """P2 as a sentence, with the count and the literal itself read out of the artifact.

    It was prose: "Two gold errors give their location as the literal string".
    Changing "Two" to anything at all passed every check in the repository,
    because nothing outside a marker pair is compared against a measurement.
    """
    strangers = [
        one
        for split in src.adversarial["splits"].values()
        for listed in split["locations_off_the_index"].values()
        for one in listed
    ]
    named = " and ".join(f"`{one}`" for one in sorted(set(strangers)))
    return paragraph(
        f"The gold-blind predictor sits a little under the oracle one on SWE Bench, and the "
        f"reason is P2: {len(strangers)} gold errors give their location as a string that no "
        f"trace contains, {named}, so a predictor working from span identifiers cannot reach "
        f"them and an oracle working from the gold can."
    )


def unreadable_gold(src: Sources) -> list[str]:
    files = src.datacheck["gold_files"]
    return paragraph(
        f"{files['parsed']} of the {files['on_disk']} gold annotation files parse. What stops "
        f"the rest is a trailing comma: `json.load` refuses the file, the call sits inside a "
        f"`try` at line 157 whose `except Exception` at line 242 prints a message and continues, "
        f"and every average TRAIL publishes divides by `files_processed`, which is "
        f"{files['parsed']}. The errors annotated in the file that did not parse are exactly the "
        f"gap between the count in the paper's abstract and the count the scorer sees."
    )


def containment(src: Sources) -> list[str]:
    """Both directions of line 26, named out of the drift table rather than by hand.

    One gold spelling the fallback rescues and one it drops for being a label
    plus a suffix. Which two those are is a fact about TRAIL's gold, so the
    sentence reads them out of the artifact and the pair below it in the drift
    block is where a reader checks them.
    """
    drifted = src.normaliser["gold_drift"]
    # The widest example of each rather than the first, because a spelling one
    # character short of its label makes the point less clearly than one seven
    # characters short of it.
    rescued = max(
        (one for one in drifted if one["loop"] == "fallback"),
        key=lambda one: len(one["lands"]) - len(one["spelling"]),
    )
    dropped = max(
        (one for one in drifted if one["loop"] == "neither" and one["labels_inside_it"]),
        key=lambda one: len(one["spelling"]) - len(one["labels_inside_it"][0]),
    )
    return paragraph(
        f"Containment in that direction promotes a string vaguer than a label and drops one more "
        f"specific than a label. Both are already in TRAIL's own gold. `{rescued['spelling']}` is "
        f"rescued onto `{rescued['lands']}`, while `{dropped['spelling']}` reaches nothing at "
        f"all, because `{dropped['labels_inside_it'][0]}` is a label and the gold spelling is "
        f"that label plus a suffix. Enumerating every substring of every label and putting each "
        f"one back through the pinned `normalize_category` gives the size of it:"
    )


def ceiling(src: Sources) -> list[str]:
    splits = src.adversarial["splits"]
    shares = ", ".join(
        f"{one['traces_with_gold_errors']} of the {one['gold_files_scored']} scored traces on "
        f"{split}"
        for split, one in splits.items()
    )
    reached = " and ".join(f"{one['reachable_ceiling']:.3f}" for one in splits.values())
    return paragraph(
        f"Nothing in either table reaches 1.000, and the row holding the answer key does not "
        f"either. A trace whose gold carries no error scores 0 at lines 54 and 58 for every "
        f"predictor, a perfect one included, and the average divides by the file count anyway. "
        f"So the ceiling is the share of traces that carry an error, {shares}, which is "
        f"{reached}."
    )


def precision(src: Sources) -> list[str]:
    splits = src.adversarial["splits"]
    names = list(next(iter(splits.values()))["predictors"])
    return table(
        ("predictor", *(f"{split}, joint / location" for split in splits)),
        (
            (
                f"`{name}`",
                *(
                    f"{one['predictors'][name]['joint_precision']:.3f} / "
                    f"{one['predictors'][name]['location_precision']:.3f}"
                    for one in splits.values()
                ),
            )
            for name in names
        ),
    )


def table_5(src: Sources) -> list[str]:
    splits = src.datacheck["splits"]
    rows = []
    for row, label in _TABLE_5_ROWS.items():
        cells = []
        for one in splits.values():
            cells += [f"{one['paper'][row]:,}", f"{one['here'][row]:,}"]
        rows.append((label, *cells))
    return table(
        (
            "Table 5",
            *(f"{split}, {source}" for split in splits for source in ("paper", "here")),
        ),
        rows,
    )


# Table 5's row names, kept here rather than imported from paper.py because this
# module renders the artifact and paper.py is the transcription that went into
# it. The artifact is the only input a generator is allowed to have.
_TABLE_5_ROWS = {
    "traces": "total traces",
    "spans": "total spans",
    "errors": "total errors",
    "unique_error_spans": "unique error spans",
    "traces_with_errors": "traces with an error",
}

_LOOP = {
    "exact": "matched exactly, once both sides were folded",
    "fallback": "rescued by the substring fallback",
    "neither": "reached no label",
}


def drift(src: Sources) -> list[str]:
    drifted = src.normaliser["gold_drift"]
    width = max(len(repr(one["spelling"])) for one in drifted)
    rows = []
    for one in drifted:
        lands = one["lands"] if one["loop"] != "neither" else f"kept as {one['lands']!r}"
        rows.append(f"{one['spelling']!r:<{width}}  x{one['errors']:<3} {one['loop']:>8}  {lands}")
    return ["```", *rows, "```"]


def fallback(src: Sources) -> list[str]:
    shortest = src.normaliser["shortest_reaching"]
    lengths = [one["length"] for one in shortest.values() if one["strings"]]
    probes = dict(src.normaliser["quoted_in_the_spec"])
    probes[" "] = src.normaliser["whitespace_only"]
    width = max(len(repr(one)) for one in probes)
    return [
        *paragraph(
            f"The shortest of the {src.normaliser['labels']} labels is "
            f"{src.normaliser['shortest_label_squashed']} characters once its spaces are "
            f"removed. Every one of them is reached by a string of {max(lengths)} characters "
            f"or fewer, and {lengths.count(1)} by a single character, out of the "
            f"{src.normaliser['substrings_enumerated']:,} distinct substrings the "
            f"{src.normaliser['labels']} labels have between them."
        ),
        "",
        "```",
        *(f"{one!r:<{width}}  ->  {lands}" for one, lands in probes.items()),
        "```",
    ]


def shuffle(src: Sources) -> list[str]:
    ambiguous = src.normaliser["order_dependent"]
    shuffled = src.normaliser["shuffle"]
    moved = len(shuffled["figures_that_moved"])
    figures = len(shuffled["scores"]) * 2
    return paragraph(
        f"{ambiguous['count']} of the {src.normaliser['substrings_enumerated']:,} substrings "
        f"the {src.normaliser['labels']} taxonomy labels contain sit inside more than one of "
        f"those labels, so list position decides which one they get, and "
        f"{ambiguous['moved_under_the_shuffle']} of them land somewhere else once the "
        f"taxonomy is reordered under seed {shuffled['seed']}. Of the "
        f"{src.datacheck['vocabulary']['spellings']} spellings TRAIL's gold actually uses, "
        f"{len(shuffled['ambiguous_gold_spellings'])} are ambiguous, so rescoring every "
        f"predictor on both splits under the shuffled order moved {moved} of the {figures} "
        f"figures it produces."
    )


def per_category(src: Sources) -> list[str]:
    return table(
        ("split", "predictor", "joint", "location", "weighted F1", "columns at recall 1.000"),
        (
            (
                one["split"],
                f"`{one['predictor']}`",
                f"{one['joint_accuracy']:.3f}",
                f"{one['location_accuracy']:.3f}",
                f"{one['weighted_f1']:.4f}",
                f"{one['categories_at_full_recall']} of {one['categories_with_support']} "
                f"with support",
            )
            for one in src.catf1["rows"]
        ),
    )


def null_category(src: Sources) -> list[str]:
    latent = src.pairing["on_the_real_gold"]
    return [
        *table(
            ("the same two real errors, scored three ways", "joint", "location"),
            (
                (
                    one["label"],
                    f"{one['joint_accuracy']:.3f}",
                    f"{one['location_accuracy']:.3f}",
                )
                for one in src.pairing["runs"]
            ),
        ),
        "",
        *paragraph(
            f"Of the {latent['gold_errors']} real gold errors, "
            f"{latent['falsy_categories']} carry a category that is null or empty, so "
            f"{latent['traces_that_would_mispair']} files mispair and "
            f"{latent['traces_that_would_lose_a_pair']} lose a pair. No published number moves "
            f"because of this one."
        ),
    ]


def committed_files(src: Sources) -> list[str]:
    """What is actually inside each file this repository commits, counted rather than described.

    The licence position rests on the answer, so it is measured on every run
    instead of being asserted once and left. `index/spans.json` carrying nothing
    but identifiers was true when it was written; the thing that makes it stay
    true is this table failing when somebody adds a field for debugging.
    """
    theirs = upstream_strings(src)
    rows = []
    for name in [str(spans.COMMITTED), *(one for one, _ in every_artifact(src))]:
        path = src.root / name
        found = set(strings_in(json.loads(path.read_text(encoding="utf-8"))))
        rows.append(
            (
                f"`{name}`",
                f"{path.stat().st_size:,}",
                f"{len(found):,}",
                f"{sum(1 for one in found if IDENTIFIER.fullmatch(one)):,}",
                f"{len(found & theirs)}",
                f"{sum(1 for one in found if len(one.split()) > 3)}",
            )
        )
    return table(
        (
            "file",
            "bytes",
            "distinct strings",
            "identifiers",
            "TRAIL's own words",
            "longer than three words",
        ),
        rows,
    )


def upstream_strings(src: Sources) -> set[str]:
    """Every string in these artifacts that TRAIL wrote rather than this repository.

    The 21 taxonomy labels, the 11 gold spellings that are not one of them, and
    the gold locations that turned out to be an English sentence. Read back out
    of the artifacts, so the set cannot drift from what was measured.
    """
    labels = set(src.normaliser["shortest_reaching"])
    spellings = {one["spelling"] for one in src.normaliser["gold_drift"]}
    locations = {
        one
        for split in src.adversarial["splits"].values()
        for listed in split["locations_off_the_index"].values()
        for one in listed
    }
    return labels | spellings | locations


def strings_in(node: object) -> Iterator[str]:
    """Every string in a JSON document, keys included.

    Keys included because `results/catf1.json` is keyed by taxonomy label:
    counting values alone would report a file carrying 168 of upstream's strings
    as carrying none, which is the opposite of what the table is for.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from strings_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings_in(value)
    elif isinstance(node, str):
        yield node


BLOCKS: dict[str, Callable[[Sources], list[str]]] = {
    "claim": claim,
    "teaser": teaser,
    "pin": pin,
    "conditions": conditions,
    "eleven-percent": eleven_percent,
    "headline": headline,
    "ceiling": ceiling,
    "absent-locations": absent_locations,
    "precision": precision,
    "table-5": table_5,
    "unreadable-gold": unreadable_gold,
    "drift": drift,
    "containment": containment,
    "fallback": fallback,
    "shuffle": shuffle,
    "per-category": per_category,
    "null-category": null_category,
    "committed-files": committed_files,
}


def render(src: Sources) -> dict[str, str]:
    return {name: "\n".join(build(src)) for name, build in BLOCKS.items()}


@dataclass(frozen=True)
class Block:
    """Where one generated block's body sits, as a half-open range of line indices."""

    name: str
    start: int
    end: int


def blocks_in(markdown: str) -> dict[str, Block]:
    """Every marker pair in the file, whatever it is called.

    Matching any name rather than only the names `BLOCKS` offers is the whole
    difference between a check and a decoration, and it is the half `twicerun`
    got wrong: scanning for known names means an orphaned marker is invisible to
    the scan, to the comparison, and to `--check`, and the block quietly freezes
    at whatever it last said.
    """
    lines = markdown.splitlines()
    found: dict[str, Block] = {}
    opened: tuple[str, int] | None = None
    for number, line in enumerate(lines):
        marker = MARKER.match(line.strip())
        if not marker:
            continue
        closing, name = marker.group(1), marker.group(2)
        if closing:
            if opened is None:
                raise MarkerError(f"line {number + 1} closes {name}, which is not open")
            if opened[0] != name:
                raise MarkerError(
                    f"line {number + 1} closes {name} while {opened[0]} is open from "
                    f"line {opened[1] + 1}"
                )
            found[name] = Block(name, opened[1] + 1, number)
            opened = None
            continue
        if opened is not None:
            raise MarkerError(
                f"line {number + 1} opens {name} inside {opened[0]}, open from "
                f"line {opened[1] + 1}"
            )
        if name in found:
            raise MarkerError(f"{name} opens twice, at lines {found[name].start} and {number + 1}")
        opened = (name, number)
    if opened is not None:
        raise MarkerError(f"{opened[0]} opens at line {opened[1] + 1} and never closes")
    return found


def line_up(found: Iterable[str], rendered: Iterable[str]) -> None:
    """Refuse a README and a set of generators that do not describe the same blocks.

    Both directions. A generator with no marker is a figure that stopped being
    published; a marker with no generator is a figure that stopped being
    checked, and only one of those is visible when you read the file.
    """
    orphaned = sorted(set(found) - set(rendered))
    unpublished = sorted(set(rendered) - set(found))
    if not orphaned and not unpublished:
        return
    complaint = ["the README and the generators do not describe the same blocks."]
    if orphaned:
        complaint.append(f"Nothing generates: {', '.join(orphaned)}.")
    if unpublished:
        complaint.append(f"The README has nowhere to put: {', '.join(unpublished)}.")
    complaint.append("Add the marker pair, or delete the generator.")
    raise MarkerError(" ".join(complaint))


def stale(markdown: str, rendered: dict[str, str]) -> list[str]:
    """Which generated blocks are not what the artifacts produce, by name."""
    found = blocks_in(markdown)
    line_up(found, rendered)
    lines = markdown.splitlines()
    return sorted(
        name
        for name, block in found.items()
        if "\n".join(lines[block.start : block.end]) != rendered[name]
    )


def rewrite(markdown: str, rendered: dict[str, str]) -> str:
    found = blocks_in(markdown)
    line_up(found, rendered)
    lines = markdown.splitlines()
    # Bottom up, so replacing a block of a different length does not move the
    # line numbers of the blocks still to be replaced.
    for block in sorted(found.values(), key=lambda one: -one.start):
        lines[block.start : block.end] = rendered[block.name].splitlines()
    return "\n".join(lines) + ("\n" if markdown.endswith("\n") else "")


def loose_scores(markdown: str) -> list[str]:
    """Lines outside every generated block that carry something shaped like a score."""
    inside = {
        number
        for block in blocks_in(markdown).values()
        for number in range(block.start - 1, block.end + 1)
    }
    return [
        f"line {number + 1}: {line.strip()}"
        for number, line in enumerate(markdown.splitlines())
        if number not in inside and SCORE.search(line)
    ]
