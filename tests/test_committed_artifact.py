"""results/adversarial.json, checked without the 186 MB download.

The artifact is the only place a figure in the README is allowed to come from,
so a hand edit to it would move published prose with nothing to catch it. What
these check is internal consistency: that the ratios divide, that the ceiling is
the fraction it claims to be, that no row exceeds it, and that the published
comparison in the file is the one transcribed in paper.py.

What they cannot check is that it is the artifact of a real run against the real
scorer. tests/test_pinned_clone.py reruns and diffs for that, and skips wherever
the clone is absent.
"""

from __future__ import annotations

import pathlib

import pytest

from trailaudit import adversarial, paper, scoring, upstream
from trailaudit.predictors import PREDICTORS


@pytest.fixture(scope="module")
def committed(repo_root: pathlib.Path) -> dict:
    return adversarial.load(repo_root / adversarial.COMMITTED)


@pytest.fixture(scope="module")
def splits(committed: dict) -> dict:
    return committed["splits"]


def test_it_covers_both_splits_and_every_predictor(splits: dict) -> None:
    assert set(splits) == {one.name for one in upstream.SPLITS}
    for one in splits.values():
        assert set(one["predictors"]) == {predictor.name for predictor in PREDICTORS}


def test_the_reads_column_agrees_with_the_predictor_that_produced_it(splits: dict) -> None:
    """The claim's load-bearing column. A row marked spans that read the gold is the
    whole argument gone, quietly."""
    for one in splits.values():
        for predictor in PREDICTORS:
            expected = "gold" if predictor.knows_gold else "spans"
            assert one["predictors"][predictor.name]["reads"] == expected


def test_every_volume_ratio_is_its_own_two_counts_divided(splits: dict) -> None:
    for one in splits.values():
        for row in one["predictors"].values():
            ratio = row["predicted_errors"] / one["gold_errors"]
            assert round(ratio, scoring.PLACES) == row["volume_ratio"]


def test_the_ceiling_is_the_fraction_it_says_it_is(splits: dict) -> None:
    for one in splits.values():
        share = one["traces_with_gold_errors"] / one["gold_files_scored"]
        assert round(share, scoring.PLACES) == one["reachable_ceiling"]


def test_no_predictor_scored_above_the_reachable_ceiling(splits: dict) -> None:
    """Including the one holding the answer key, which is what makes the ceiling real.

    A row above it would mean either the ceiling arithmetic is wrong or a trace
    with no gold errors scored something other than 0, and both would put a
    wrong number in the README's headline sentence.
    """
    for one in splits.values():
        for name, row in one["predictors"].items():
            assert row["joint_accuracy"] <= one["reachable_ceiling"], name
            assert row["location_accuracy"] <= one["reachable_ceiling"], name


def test_the_gold_blind_headline_beats_both_published_columns(splits: dict) -> None:
    for one in splits.values():
        row = one["predictors"][adversarial.HEADLINE.name]
        assert row["reads"] == "spans"
        for metric in ("joint_accuracy", "location_accuracy"):
            assert row[metric] > one["best_published"][metric]["value"]


def test_the_gold_blind_headline_never_beats_the_oracle_ceiling_row(splits: dict) -> None:
    """P2's direction. The oracle knows where the errors are; this one only knows the spans."""
    for one in splits.values():
        blind = one["predictors"][adversarial.HEADLINE.name]
        oracle = one["predictors"][adversarial.CEILING.name]
        for metric in ("joint_accuracy", "location_accuracy"):
            assert blind[metric] <= oracle[metric]


def test_the_published_comparison_is_the_transcribed_one(splits: dict) -> None:
    for split, one in splits.items():
        for metric in ("joint_accuracy", "location_accuracy"):
            best = paper.best_published(split, metric)
            stored = one["best_published"][metric]
            assert stored == {"model": best.model, "value": getattr(best, metric)}


def test_the_denominators_are_147_of_148(splits: dict) -> None:
    """The slice 1 finding, carried into slice 2's own numbers rather than restated.

    Every average in this artifact divides by gold_files_scored, so if that ever
    stops being 147 the headline moved and the run said nothing about it.
    """
    assert sum(one["gold_files"] for one in splits.values()) == paper.ABSTRACT_TRACES
    assert sum(one["gold_files_scored"] for one in splits.values()) == paper.ABSTRACT_TRACES - 1


def test_the_only_file_walked_past_is_the_one_that_does_not_parse(splits: dict) -> None:
    walked = [skip for one in splits.values() for skip in one["walked_past"]]
    assert [one["why"] for one in walked] == [scoring.UNREADABLE]
    assert walked[0]["trace"] == "a96c6811716c0473b86a23321db79c34"


def test_no_decoder_wording_is_stored(repo_root: pathlib.Path) -> None:
    """CPython 3.12 and 3.13 word the same trailing comma differently.

    Either wording in the file would make `trailaudit adversarial --check` pass
    on one interpreter and fail on the other.
    """
    raw = (repo_root / adversarial.COMMITTED).read_text(encoding="utf-8")
    assert "Expecting value" not in raw
    assert "trailing comma" not in raw


def test_every_score_in_the_file_is_a_fraction(splits: dict) -> None:
    for one in splits.values():
        for row in one["predictors"].values():
            for metric in ("joint", "location"):
                assert 0.0 <= row[f"{metric}_accuracy"] <= 1.0
                assert 0.0 <= row[f"{metric}_precision"] <= 1.0
