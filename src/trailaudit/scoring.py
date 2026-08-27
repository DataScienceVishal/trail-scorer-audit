"""Driving TRAIL's unmodified `main()` over a directory of predictions, and reading its stdout.

`calculate_scores.main(ground_truth_dir, generated_dir)` wants two directories
and returns four averages. It does not return the count it divided by, and
`files_processed` is a local, so the only way to know the denominator without
editing the file is to read what it printed: line 154 for a prediction that is
not on disk, line 243 for a gold file that did not survive `json.load`. Those two
format strings are frozen by the SHA-256 in upstream.py, which is what makes
parsing them safe rather than brittle.

The second thing here is the precision diagnostic the spec asks for, and it is
this repository's code rather than TRAIL's. It rebuilds the pairs the way lines
45 to 50 build them, intersects them the way lines 53 and 57 do, and then divides
by the prediction count instead of the gold count. That reimplementation could
drift from the original without anyone noticing, so it computes the recall
direction as well and `score_split` refuses to return unless its recall figures
match the ones the scorer handed back. The precision column is only trustworthy
because the recall column beside it is checked against upstream on every run.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from trailaudit.gold import Annotation
from trailaudit.predictors import Case, Error, Predictor, document

NO_PREDICTION = re.compile(r"^Generated file (?P<path>.+) does not exist$")
UNREADABLE_GOLD = re.compile(r"^Error processing (?P<path>.+?): (?P<why>.+)$")

# Sums of 147 floats are not associative, so the last bits of an average depend
# on the order glob returned the files in. Everything published is three decimal
# places; this is where the artifact stops carrying digits that are a fact about
# the filesystem rather than about the scorer.
PLACES = 10

AGREEMENT = 1e-9


class DiagnosticDrifted(ValueError):
    """The precision diagnostic no longer reproduces the scorer it is quoting."""


UNREADABLE = "gold file did not parse"
UNPREDICTED = "no prediction was written for it"


@dataclass(frozen=True)
class Skip:
    """Why the scorer walked past a gold file, as one of the two constants above.

    The decoder's own message is deliberately dropped rather than recorded.
    CPython 3.12 and 3.13 word the same trailing comma differently, so an
    artifact carrying it would fail its own comparison test on the other
    interpreter, and `trailaudit data-check` already locates the character.
    """

    trace: str
    kind: str


@dataclass(frozen=True)
class Scores:
    joint_accuracy: float
    location_accuracy: float
    joint_precision: float
    location_precision: float
    files_globbed: int
    files_processed: int
    predicted_errors: int
    gold_errors: int
    skipped: tuple[Skip, ...]

    @property
    def volume_ratio(self) -> float:
        return self.predicted_errors / self.gold_errors if self.gold_errors else 0.0


def write_predictions(
    predictor: Predictor, cases: dict[str, Case], into: Path
) -> dict[str, list[Error]]:
    into.mkdir(parents=True, exist_ok=True)
    emitted = {}
    for trace, case in cases.items():
        errors = predictor.emit(case)
        (into / f"{trace}.json").write_text(json.dumps(document(errors)), encoding="utf-8")
        emitted[trace] = errors
    return emitted


def skips_from(printed: str, gold_dir: Path) -> list[Skip]:
    """Which gold files the scorer walked past, from what it said about them.

    Both messages carry a full path, and the gold file and the prediction file
    share a basename, so either message identifies the trace the same way.
    """
    found = []
    for line in printed.splitlines():
        missing = NO_PREDICTION.match(line)
        if missing:
            found.append(Skip(Path(missing["path"]).stem, UNPREDICTED))
            continue
        unreadable = UNREADABLE_GOLD.match(line)
        if unreadable and Path(unreadable["path"]).parent == gold_dir:
            found.append(Skip(Path(unreadable["path"]).stem, UNREADABLE))
    return found


def pairs(
    locations: Sequence[str], raw_categories: Sequence[str], normalise: Callable[[str], str]
) -> set[tuple[str, str]]:
    """Lines 45 and 49 of calculate_scores.py, in this repository's words.

    Line 49's `[(locations[i], categories[i]) for i in range(len(locations)) if
    i < len(categories)]` is a truncating zip written out longhand, and swapping
    it for `zip(..., strict=False)` changes nothing. Checked by mutation: that
    substitution passes every test here. The mispairing P8 is about is line 45,
    which filters the categories on truthiness and leaves the locations alone,
    so one falsy category slides every later category one location earlier.

    Reproduced rather than fixed. A diagnostic that quietly corrected the
    pairing would stop describing the thing it is a diagnostic for.
    """
    kept = [normalise(one) for one in raw_categories if one]
    return {(locations[i], kept[i]) for i in range(len(locations)) if i < len(kept)}


@dataclass(frozen=True)
class BothWays:
    joint_recall: float
    joint_precision: float
    location_recall: float
    location_precision: float


def both_ways(
    gold: Annotation, predicted: Sequence[Error], normalise: Callable[[str], str]
) -> BothWays:
    gold_locations = list(gold.locations)
    gold_pairs = pairs(gold_locations, gold.categories, normalise)
    predicted_locations = [one.get("location", "") for one in predicted]
    predicted_pairs = pairs(
        predicted_locations, [one.get("category", "") for one in predicted], normalise
    )

    shared_pairs = len(gold_pairs & predicted_pairs)
    shared_locations = len(set(gold_locations) & set(predicted_locations))
    return BothWays(
        joint_recall=_over(shared_pairs, len(gold_pairs)),
        joint_precision=_over(shared_pairs, len(predicted_pairs)),
        location_recall=_over(shared_locations, len(set(gold_locations))),
        location_precision=_over(shared_locations, len(set(predicted_locations))),
    )


def _over(shared: int, total: int) -> float:
    """Lines 54 and 58 return the int 0, not a fraction, when the denominator is empty.

    Four gold files carry no errors at all, so this branch is taken by every
    predictor on those four, including one holding the answer key. It is the
    reason nothing in the run reaches 1.000.
    """
    return shared / total if total else 0.0


def score_split(
    scorer: ModuleType,
    gold_dir: Path,
    cases: dict[str, Case],
    annotations: dict[str, Annotation],
    normalise: Callable[[str], str],
    predictor: Predictor,
    workspace: Path,
) -> Scores:
    emitted = write_predictions(predictor, cases, workspace)

    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        returned = scorer.main(str(gold_dir), str(workspace))
    skipped = skips_from(printed.getvalue(), gold_dir)

    globbed = len(list(gold_dir.glob("*.json")))
    processed = globbed - len(skipped)
    walked_past = {one.trace for one in skipped}
    scored = [trace for trace in annotations if trace not in walked_past]
    if len(scored) != processed:
        raise DiagnosticDrifted(
            f"{predictor.name} on {gold_dir.name}: the scorer walked past {len(skipped)} of "
            f"{globbed} gold files, leaving {processed}, and this repository can account for "
            f"{len(scored)} of them. A message format at line 154 or 243 has changed."
        )

    measured = [both_ways(annotations[trace], emitted[trace], normalise) for trace in scored]
    mine = _averages(measured, processed)
    _confirm(mine, returned, predictor.name, gold_dir)

    return Scores(
        joint_accuracy=round(returned["joint_accuracy"], PLACES),
        location_accuracy=round(returned["location_accuracy"], PLACES),
        joint_precision=round(mine["joint_precision"], PLACES),
        location_precision=round(mine["location_precision"], PLACES),
        files_globbed=globbed,
        files_processed=processed,
        predicted_errors=sum(len(emitted[trace]) for trace in scored),
        gold_errors=sum(len(annotations[trace].categories) for trace in scored),
        skipped=tuple(skipped),
    )


def _averages(measured: Sequence[BothWays], processed: int) -> dict[str, float]:
    if processed <= 0:
        return dict.fromkeys(
            ("joint_recall", "joint_precision", "location_recall", "location_precision"), 0.0
        )
    return {
        name: sum(getattr(one, name) for one in measured) / processed
        for name in ("joint_recall", "joint_precision", "location_recall", "location_precision")
    }


def _confirm(mine: dict[str, float], returned: dict[str, float], name: str, gold_dir: Path) -> None:
    both = (("joint_accuracy", "joint_recall"), ("location_accuracy", "location_recall"))
    for theirs, ours in both:
        gap = abs(returned[theirs] - mine[ours])
        if gap > AGREEMENT:
            raise DiagnosticDrifted(
                f"{name} on {gold_dir.name}: calculate_scores.py returned {theirs} "
                f"{returned[theirs]!r} and the precision diagnostic reproduces it as "
                f"{mine[ours]!r}, off by {gap:.3e}. The precision figures beside it are only "
                f"meaningful while these two agree, so the run stops here."
            )
