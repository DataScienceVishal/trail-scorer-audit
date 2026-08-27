"""What `trailaudit adversarial` runs and prints: P1, P2, and the six predictors side by side.

The run is six predictors by two splits, each one a separate call into
`calculate_scores.main()` at the pinned SHA with a directory of predictions and
the real gold. Nothing is mocked and nothing is scored twice.

Two numbers come out of it per row and both are published together. The first is
what TRAIL reports, joint and location accuracy, which divide the intersection
by the gold count at lines 54 and 58. The second is the volume ratio, the number
of errors the predictor emitted for every gold error, which is what the first
number costs. A row reading 0.966 at 129 predictions per gold error is a
different claim from the same 0.966 at 1, and the leaderboard column carries only
the part they have in common.
"""

from __future__ import annotations

import tempfile
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from trailaudit import artifacts, gold, paper, predictors, scoring, spans, upstream
from trailaudit.datacheck import HELD, VIOLATED, WIDTH, Finding, verdicts, wrapped
from trailaudit.gold import Annotation
from trailaudit.predictors import Case, Predictor
from trailaudit.scoring import Scores

COMMITTED = Path("results/adversarial.json")

HEADLINE = predictors.by_name("all-spans-all-categories")
CEILING = predictors.by_name("gold-spans-all-categories")

# The literal the SWE Bench annotators wrote where a span identifier was
# expected. Not a hash and not a truncation: an English sentence in the location
# field of two gold errors.
MISSING_SHARD = "Span ID not found for this shard"


@dataclass(frozen=True)
class SplitRun:
    split: str
    scored: dict[str, Scores]
    gold_files: int
    absent_locations: dict[str, list[str]]
    traces_with_gold_errors: int

    @property
    def files_scored(self) -> int:
        return next(iter(self.scored.values())).files_processed

    @property
    def gold_errors(self) -> int:
        return next(iter(self.scored.values())).gold_errors

    @property
    def ceiling(self) -> float:
        """The best score any predictor can reach on this split, including a perfect one.

        Lines 54 and 58 return the int 0 for a trace with no gold errors, and
        that 0 goes into an average whose denominator counts the trace anyway.
        So the reachable maximum is the share of scored traces that carry at
        least one gold error, and it is below 1.000 on both splits.
        """
        return self.traces_with_gold_errors / self.files_scored if self.files_scored else 0.0


def cases_for(
    split: upstream.Split,
    index: dict[str, list[str]],
    annotations: dict[str, Annotation],
    taxonomy: tuple[str, ...],
) -> dict[str, Case]:
    """One Case per gold file, including the one that will not parse.

    That file gets an empty gold and a prediction written for it anyway. Writing
    it means the scorer's only complaint about the split is the parse failure at
    line 243, rather than a parse failure plus a missing prediction at line 154,
    and the report can say the denominator moved for exactly one reason.
    """
    empty = Annotation(split=split.name, trace="", categories=(), locations=())
    return {
        trace: Case(
            span_ids=tuple(index[trace]),
            taxonomy=taxonomy,
            gold=tuple(
                {"location": location, "category": category}
                for location, category in zip(
                    annotations.get(trace, empty).locations,
                    annotations.get(trace, empty).categories,
                    strict=True,
                )
            ),
        )
        for trace in index
    }


def locations_off_the_index(
    annotations: dict[str, Annotation], index: dict[str, list[str]]
) -> dict[str, list[str]]:
    """P2, per trace: gold locations that are not a span identifier in that trace."""
    absent = {}
    for trace, annotation in annotations.items():
        known = set(index.get(trace, []))
        strangers = sorted({one for one in annotation.locations if one not in known})
        if strangers:
            absent[trace] = strangers
    return absent


def run_split(
    scorer: ModuleType,
    clone: Path,
    split: upstream.Split,
    index: dict[str, list[str]],
    taxonomy: tuple[str, ...],
    normalise: Callable[[str], str],
) -> SplitRun:
    loaded, _ = gold.read_directory(clone / split.annotations, split.name)
    annotations = {one.trace: one for one in loaded}
    cases = cases_for(split, index, annotations, taxonomy)

    scored = {}
    with tempfile.TemporaryDirectory(prefix="trailaudit-") as workspace:
        for predictor in predictors.PREDICTORS:
            scored[predictor.name] = scoring.score_split(
                scorer=scorer,
                gold_dir=clone / split.annotations,
                cases=cases,
                annotations=annotations,
                normalise=normalise,
                predictor=predictor,
                workspace=Path(workspace) / predictor.name / split.name,
            )

    return SplitRun(
        split=split.name,
        scored=scored,
        gold_files=len(cases),
        absent_locations=locations_off_the_index(annotations, index),
        traces_with_gold_errors=sum(1 for one in annotations.values() if one.categories),
    )


def run(clone: Path, index: dict[str, dict[str, list[str]]]) -> list[SplitRun]:
    scorer = upstream.load_scorer(clone)
    taxonomy = upstream.taxonomy(clone)
    normalise = gold.binder(scorer.normalize_category, taxonomy)
    return [
        run_split(scorer, clone, split, index[split.name], taxonomy, normalise)
        for split in upstream.SPLITS
    ]


def p1(runs: list[SplitRun]) -> Finding:
    claim = "all-spans-all-categories scores no better than a published judge"
    lines = [f"against the best of eight LLMs in {paper.TABLE_1_CITATION}"]
    beaten = False
    for one in runs:
        mine = one.scored[HEADLINE.name]
        for metric, label in (("joint_accuracy", "joint"), ("location_accuracy", "location")):
            best = paper.best_published(one.split, metric)
            theirs = getattr(best, metric)
            ours = getattr(mine, metric)
            beaten = beaten or ours > theirs
            lines.append(
                f"{one.split:<11}{label:<10}{ours:.3f} against {theirs:.3f}, "
                f"{ours / theirs:.1f}x, {best.model}"
            )
    lines += [
        "",
        *wrapped(
            f"its whole input is that trace's entry in {spans.COMMITTED}, a list of "
            f"sixteen-digit hex identifiers. It reads no span contents and no gold, and it "
            f"emits {_ratio_range(runs, HEADLINE.name)} errors for every gold error to get "
            f"there."
        ),
    ]
    return Finding(
        "P1",
        claim,
        VIOLATED if beaten else HELD,
        _p1_magnitude(runs, beaten),
        lines,
    )


def _p1_magnitude(runs: list[SplitRun], beaten: bool) -> str:
    per_split = []
    for one in runs:
        mine = one.scored[HEADLINE.name]
        cells = ", ".join(
            f"{label} {getattr(mine, metric):.3f} against "
            f"{getattr(paper.best_published(one.split, metric), metric):.3f}"
            for metric, label in (("joint_accuracy", "joint"), ("location_accuracy", "location"))
        )
        per_split.append(f"{one.split} {cells}")
    verb = "beats" if beaten else "stays under"
    return f"the gold-blind predictor {verb} the best published row: " + "; ".join(per_split)


def p2(runs: list[SplitRun]) -> Finding:
    claim = "every gold error location is a span identifier in its own trace"
    absent = sum(len(one) for run_ in runs for one in run_.absent_locations.values())
    errors = sum(one.gold_errors for one in runs)
    if not absent:
        return Finding(
            "P2",
            claim,
            HELD,
            f"{errors} gold errors, every location a span in its own trace",
            [f"{errors} gold errors, every location indexed"],
        )

    named = []
    every: set[str] = set()
    for one in runs:
        for trace, strangers in sorted(one.absent_locations.items()):
            named += [f"{one.split}/{trace}  {stranger!r}" for stranger in strangers]
            every.update(strangers)
    shared = f". All of them are the literal {MISSING_SHARD!r}" if len(every) == 1 else ""

    lines = [
        *wrapped(
            f"{absent} of {errors} gold locations are not a span in the trace they "
            f"annotate{shared}"
        ),
        *named,
        "",
        *wrapped(
            "so the all-spans predictor is capped below the gold-spans ceiling and its figure "
            "is a lower bound. The size of that, from the run below:"
        ),
        *(f"  {line}" for line in _ceiling_gaps(runs)),
    ]
    return Finding(
        "P2",
        claim,
        VIOLATED,
        f"{absent} of {errors} gold locations are not a span in the trace they annotate{shared}",
        lines,
    )


def _ceiling_gaps(runs: list[SplitRun]) -> list[str]:
    """How far P2 pushes the gold-blind predictor below the oracle one, per split."""
    lines = []
    for one in runs:
        blind, oracle = one.scored[HEADLINE.name], one.scored[CEILING.name]
        gaps = [
            f"{label} {getattr(blind, metric):.6f} against {getattr(oracle, metric):.6f}"
            for metric, label in (("joint_accuracy", "joint"), ("location_accuracy", "location"))
        ]
        lines.append(f"{one.split:<11}{', '.join(gaps)}")
    clean = [one.split for one in runs if not one.absent_locations]
    if clean:
        lines += textwrap.wrap(
            f"{' and '.join(clean)} has no such location, so there the gold-blind "
            f"predictor hits the ceiling exactly.",
            WIDTH - 6,
        )
    return lines


def _ratio_range(runs: list[SplitRun], name: str) -> str:
    ratios = sorted(one.scored[name].volume_ratio for one in runs)
    return f"{ratios[0]:.0f} to {ratios[-1]:.0f}"


def split_table(one: SplitRun) -> list[str]:
    head = f"{'predictor':<27}{'reads':>7}{'joint':>9}{'location':>10}{'emitted':>10}"
    rows = [f"{head}{'per gold':>10}"]
    for predictor in predictors.PREDICTORS:
        scored = one.scored[predictor.name]
        rows.append(
            f"{predictor.name:<27}{_reads(predictor):>7}{scored.joint_accuracy:>9.3f}"
            f"{scored.location_accuracy:>10.3f}{scored.predicted_errors:>10,}"
            f"{scored.volume_ratio:>9.1f}x"
        )
    joint = paper.best_published(one.split, "joint_accuracy")
    location = paper.best_published(one.split, "location_accuracy")
    rows.append(
        f"{'best published, Table 1':<27}{'':>7}{joint.joint_accuracy:>9.3f}"
        f"{location.location_accuracy:>10.3f}"
    )
    rows.append(f"{'reachable at all':<27}{'':>7}{one.ceiling:>9.3f}{one.ceiling:>10.3f}")
    return rows


def _reads(predictor: Predictor) -> str:
    return "gold" if predictor.knows_gold else "spans"


def precision_table(runs: list[SplitRun]) -> list[str]:
    heads = "".join(f"{one.split:>21}" for one in runs)
    rows = [
        f"{'':<27}{heads}",
        f"{'predictor':<27}" + "".join(f"{'joint / location':>21}" for _ in runs),
    ]
    for predictor in predictors.PREDICTORS:
        cells = ""
        for one in runs:
            scored = one.scored[predictor.name]
            cells += f"{scored.joint_precision:.3f} / {scored.location_precision:.3f}".rjust(21)
        rows.append(f"{predictor.name:<27}{cells}")
    return rows


def _footnotes(one: SplitRun) -> list[str]:
    """The two things about a split's table that a reader would otherwise have to derive."""
    lines = wrapped(
        f"reachable at all is the {one.traces_with_gold_errors} of {one.files_scored} scored "
        f"traces that carry a gold error. Lines 54 and 58 score a trace with none as 0 for "
        f"every predictor, gold-exact included, so nothing in this table reaches 1.000."
    )
    for skipped in one.scored[HEADLINE.name].skipped:
        lines += wrapped(
            f"walked past {skipped.trace}, {skipped.kind}. `trailaudit data-check` locates "
            f"the character; the decoder's own wording for it moves between CPython versions "
            f"and is not repeated here."
        )
    return lines


def report(runs: list[SplitRun]) -> tuple[list[str], bool]:
    findings = [p1(runs), p2(runs)]
    lines: list[str] = []
    for finding in findings:
        lines += [finding.render(), ""]

    for one in runs:
        lines += [
            f"{one.split}: {one.files_scored} of {one.gold_files} gold files scored, "
            f"{one.gold_errors} gold errors in them",
            *(f"  {row}".rstrip() for row in split_table(one)),
            "",
            *(f"  {line}" for line in _footnotes(one)),
            "",
        ]

    lines += [
        "precision, which neither headline metric reports: the same intersections over the",
        "prediction count instead of the gold count. A diagnostic, not a proposed metric.",
        *(f"  {row}".rstrip() for row in precision_table(runs)),
        "",
        *wrapped(
            "this repository computes that column, TRAIL does not. It rebuilds the pairs the "
            "way lines 45 to 50 build them and intersects them the way lines 53 and 57 do, and "
            "the run refuses to finish unless its recall figures reproduce the ones "
            "calculate_scores.py returned."
        ),
    ]
    return lines, any(finding.verdict == VIOLATED for finding in findings)


def artifact(runs: list[SplitRun], index_sha256: str) -> dict:
    """Every figure the prose is allowed to quote, in one committed file.

    Skip reasons are recorded as their kind and not as the decoder's wording,
    which differs between CPython 3.12 and 3.13 over the same bytes. An artifact
    that carried it would fail its own comparison test on the other interpreter.
    """
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
        "index_sha256": index_sha256,
        "table_1": paper.TABLE_1_CITATION,
        "properties": verdicts([p1(runs), p2(runs)]),
        "splits": {
            one.split: {
                "gold_files": one.gold_files,
                "gold_files_scored": one.files_scored,
                "gold_errors": one.gold_errors,
                "traces_with_gold_errors": one.traces_with_gold_errors,
                "reachable_ceiling": round(one.ceiling, scoring.PLACES),
                "walked_past": [
                    {"trace": skip.trace, "why": skip.kind}
                    for skip in one.scored[HEADLINE.name].skipped
                ],
                "locations_off_the_index": one.absent_locations,
                "best_published": {
                    metric: {
                        "model": paper.best_published(one.split, metric).model,
                        "value": getattr(paper.best_published(one.split, metric), metric),
                    }
                    for metric in ("joint_accuracy", "location_accuracy")
                },
                "predictors": {
                    predictor.name: {
                        "reads": _reads(predictor),
                        "joint_accuracy": one.scored[predictor.name].joint_accuracy,
                        "location_accuracy": one.scored[predictor.name].location_accuracy,
                        "joint_precision": one.scored[predictor.name].joint_precision,
                        "location_precision": one.scored[predictor.name].location_precision,
                        "predicted_errors": one.scored[predictor.name].predicted_errors,
                        "volume_ratio": round(
                            one.scored[predictor.name].volume_ratio, scoring.PLACES
                        ),
                    }
                    for predictor in predictors.PREDICTORS
                },
            }
            for one in runs
        },
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit adversarial")
