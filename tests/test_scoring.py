"""The driver, tested against a stand-in scorer rather than the 186 MB one.

What is under test here is this repository's half: reading the denominator out of
stdout, counting predictions over the files that were actually scored, and
refusing to publish a precision column whose recall twin has stopped matching
what upstream returned. The stand-in returns numbers chosen by the test, which is
the only way to make that last check fail on purpose.
"""

from __future__ import annotations

import json
import pathlib
from types import ModuleType

import pytest

from stand_ins import TAXONOMY
from trailaudit import scoring
from trailaudit.gold import Annotation
from trailaudit.predictors import Case, Predictor, gold_exact, silent
from trailaudit.scoring import UNPREDICTED, UNREADABLE, DiagnosticDrifted, Skip

ONE_ERROR = {"location": "aaaa000000000001", "category": "Widget Errors"}

COPYCAT = Predictor("copycat", knows_gold=True, emit=gold_exact)
MUTE = Predictor("mute", knows_gold=False, emit=silent)


def stand_in_scorer(returns: dict[str, float], prints: str = "") -> ModuleType:
    """A module with a `main` that says what the test tells it to say."""
    module = ModuleType("stand_in_calculate_scores")

    def main(ground_truth_dir: str, generated_dir: str) -> dict[str, float]:
        if prints:
            print(prints.format(gold=ground_truth_dir, generated=generated_dir))
        return returns

    module.main = main
    return module


@pytest.fixture
def gold_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    where = tmp_path / "gold"
    where.mkdir()
    for trace in ("alpha", "beta"):
        (where / f"{trace}.json").write_text(json.dumps({"errors": [ONE_ERROR]}))
    return where


@pytest.fixture
def both_traces() -> tuple[dict[str, Case], dict[str, Annotation]]:
    cases = {
        trace: Case(span_ids=("aaaa000000000001",), taxonomy=TAXONOMY, gold=(ONE_ERROR,))
        for trace in ("alpha", "beta")
    }
    annotations = {
        trace: Annotation(
            split="fixture",
            trace=trace,
            categories=(ONE_ERROR["category"],),
            locations=(ONE_ERROR["location"],),
        )
        for trace in ("alpha", "beta")
    }
    return cases, annotations


def test_a_perfect_predictor_agrees_with_a_scorer_that_says_one_point_oh(
    tmp_path: pathlib.Path, gold_dir: pathlib.Path, both_traces
) -> None:
    cases, annotations = both_traces
    scored = scoring.score_split(
        scorer=stand_in_scorer({"joint_accuracy": 1.0, "location_accuracy": 1.0}),
        gold_dir=gold_dir,
        cases=cases,
        annotations=annotations,
        normalise=str.strip,
        predictor=COPYCAT,
        workspace=tmp_path / "work",
    )
    assert (scored.files_globbed, scored.files_processed) == (2, 2)
    assert (scored.predicted_errors, scored.gold_errors) == (2, 2)
    assert scored.volume_ratio == 1.0
    assert (scored.joint_precision, scored.location_precision) == (1.0, 1.0)


def test_a_scorer_that_returns_a_different_number_stops_the_run(
    tmp_path: pathlib.Path, gold_dir: pathlib.Path, both_traces
) -> None:
    """The check that licenses the precision column.

    The precision figures are this repository's arithmetic on TRAIL's pairs. If
    the pair-building drifted from lines 45 to 50, the precision column would go
    quietly wrong while still looking like a plausible number, so the run
    recomputes recall as well and refuses to finish when the two disagree.
    """
    cases, annotations = both_traces
    with pytest.raises(DiagnosticDrifted, match="off by"):
        scoring.score_split(
            scorer=stand_in_scorer({"joint_accuracy": 0.5, "location_accuracy": 1.0}),
            gold_dir=gold_dir,
            cases=cases,
            annotations=annotations,
            normalise=str.strip,
            predictor=COPYCAT,
            workspace=tmp_path / "work",
        )


def test_a_gold_file_the_scorer_skipped_leaves_the_denominator_and_the_volume(
    tmp_path: pathlib.Path, gold_dir: pathlib.Path, both_traces
) -> None:
    """One skip has to move three numbers together or the volume ratio is wrong.

    files_processed drops to 1, and so do the errors counted on both sides. A
    predictor whose emissions for the skipped trace stayed in the numerator
    would report a ratio over a denominator the scorer never used.
    """
    cases, annotations = both_traces
    complained = "Error processing {gold}/beta.json: Expecting value: line 39 column 5"
    scored = scoring.score_split(
        scorer=stand_in_scorer({"joint_accuracy": 1.0, "location_accuracy": 1.0}, complained),
        gold_dir=gold_dir,
        cases=cases,
        annotations=annotations,
        normalise=str.strip,
        predictor=COPYCAT,
        workspace=tmp_path / "work",
    )
    assert scored.files_processed == 1
    assert scored.predicted_errors == 1
    assert scored.gold_errors == 1
    assert [one.trace for one in scored.skipped] == ["beta"]


def test_a_silent_predictor_divides_by_nothing_rather_than_dividing_by_zero(
    tmp_path: pathlib.Path, gold_dir: pathlib.Path, both_traces
) -> None:
    cases, annotations = both_traces
    scored = scoring.score_split(
        scorer=stand_in_scorer({"joint_accuracy": 0.0, "location_accuracy": 0.0}),
        gold_dir=gold_dir,
        cases=cases,
        annotations=annotations,
        normalise=str.strip,
        predictor=MUTE,
        workspace=tmp_path / "work",
    )
    assert (scored.joint_precision, scored.location_precision) == (0.0, 0.0)
    assert scored.volume_ratio == 0.0


def test_skips_from_reads_both_messages_and_ignores_the_rest() -> None:
    gold_dir = pathlib.Path("/gold")
    printed = "\n".join(
        [
            "Generated file /work/one.json does not exist",
            "Error processing /gold/two.json: Expecting value: line 39 column 5",
            "Error processing /elsewhere/three.json: not this directory",
            "[1.0, 2.0] [1, 2]",
            "Error calculating Pearson correlation for reliability: boom",
        ]
    )
    assert scoring.skips_from(printed, gold_dir) == [
        Skip("one", UNPREDICTED),
        Skip("two", UNREADABLE),
    ]


def test_a_falsy_category_shifts_every_pair_after_it() -> None:
    """P8's mechanism, reproduced rather than fixed, because the diagnostic quotes it.

    Line 45 drops falsy categories and line 49 indexes the unfiltered locations,
    so one null category slides every later category one location earlier. On
    TRAIL's gold this never fires: all 147 loadable files have a truthy category
    on every error.
    """
    locations = ["one", "two", "three"]
    categories = ["Widget Errors", "", "Flange Misuse"]
    assert scoring.pairs(locations, categories, str.strip) == {
        ("one", "Widget Errors"),
        ("two", "Flange Misuse"),
    }


def test_both_ways_divides_by_the_prediction_count_the_second_time() -> None:
    gold = Annotation(split="f", trace="t", categories=("A", "B"), locations=("x", "y"))
    predicted = [
        {"location": "x", "category": "A"},
        {"location": "x", "category": "B"},
        {"location": "y", "category": "A"},
        {"location": "y", "category": "B"},
    ]
    measured = scoring.both_ways(gold, predicted, str.strip)
    assert measured.joint_recall == 1.0
    assert measured.joint_precision == 0.5
    assert measured.location_recall == 1.0
    assert measured.location_precision == 1.0


def test_a_trace_with_no_gold_errors_scores_zero_for_a_predictor_holding_the_answer_key() -> None:
    """Lines 54 and 58 return the int 0 rather than skipping the trace.

    This is what puts the reachable ceiling below 1.000 on both splits, and it
    is the reason the spec's "scored 1.000" could not survive the measurement.
    """
    empty = Annotation(split="f", trace="t", categories=(), locations=())
    measured = scoring.both_ways(empty, [], str.strip)
    assert measured.joint_recall == 0.0
    assert measured.location_recall == 0.0


def test_a_whitespace_category_survives_because_line_45_filters_before_normalising() -> None:
    """The order matters here even though it cannot matter on TRAIL's gold.

    Line 45 tests the raw string for truthiness and normalises afterwards, so a
    category of " " is kept. Normalising first would drop it under a normaliser
    that strips, and shift every later pairing, which is the defect this
    function exists to reproduce rather than introduce. TRAIL's own normaliser
    never returns an empty string for a truthy input, so the two orders agree on
    the real gold and disagree on any stand-in that strips.
    """
    assert scoring.pairs(["one", "two"], [" ", "Flange Misuse"], str.strip) == {
        ("one", ""),
        ("two", "Flange Misuse"),
    }


def test_as_document_rebuilds_a_gold_annotation_in_the_order_it_was_read() -> None:
    """Lines 45 to 49 pair locations against categories by position, so order is the content.

    An Annotation holds the two as parallel tuples. Rebuilding them into the
    wrong fields, or into the wrong order, would change what the scorer thinks
    the gold says while leaving every count in this audit identical.
    """
    annotation = Annotation(
        split="fixture",
        trace="alpha",
        categories=("Widget Errors", "Flange Misuse"),
        locations=("aaaa000000000001", "aaaa000000000002"),
    )
    assert scoring.as_document(annotation) == {
        "errors": [
            {"location": "aaaa000000000001", "category": "Widget Errors"},
            {"location": "aaaa000000000002", "category": "Flange Misuse"},
        ]
    }


def test_as_document_carries_no_scores_key() -> None:
    """The gold files have one. It feeds main()'s Pearson block and nothing this audit reads."""
    empty = Annotation(split="fixture", trace="alpha", categories=(), locations=())
    assert scoring.as_document(empty) == {"errors": []}


def test_averaged_under_divides_by_the_annotations_it_was_given() -> None:
    """Not by the files on disk. The gold file that will not parse is not in this dict."""
    module = ModuleType("stand_in_metrics")
    module.calculate_metrics = lambda ground_truth, generated, categories: {
        "joint_accuracy": 1.0 if generated["errors"] else 0.0,
        "location_accuracy": 0.5,
    }
    annotations = {
        trace: Annotation(split="fixture", trace=trace, categories=(), locations=())
        for trace in ("alpha", "beta", "gamma", "delta")
    }
    emitted = {"alpha": [ONE_ERROR], "beta": [], "gamma": [], "delta": []}
    assert scoring.averaged_under(module, annotations, emitted, TAXONOMY) == (0.25, 0.5)


def test_averaged_under_hands_the_taxonomy_it_was_given_to_the_scorer() -> None:
    """The whole point of it. main() cannot be asked to use a different order."""
    seen = []
    module = ModuleType("stand_in_metrics")

    def calculate_metrics(ground_truth, generated, categories):
        seen.append(tuple(categories))
        return {"joint_accuracy": 0.0, "location_accuracy": 0.0}

    module.calculate_metrics = calculate_metrics
    annotations = {"alpha": Annotation("fixture", "alpha", (), ())}
    reordered = tuple(reversed(TAXONOMY))
    scoring.averaged_under(module, annotations, {"alpha": []}, reordered)
    assert seen == [reordered]
