"""The two transcribed tables, checked against arithmetic the paper prints itself.

A hand transcription is the one place in this repository where a typo turns
straight into a wrong headline, and neither table can be regenerated from
anything. So both are checked against numbers the paper publishes alongside
them: Table 5 prints four means in parentheses, and Table 1's per-split joint
figures have to reconcile with the 11% the abstract quotes.
"""

from __future__ import annotations

import pytest

from trailaudit import paper

# The population the scorer actually averages over, from `trailaudit data-check`
# against the pinned tree. Not the paper's counts, which is the point: these are
# the weights a reader would reach for if they wanted 11% to be a weighted mean.
GOLD_FILES_LOADED = {"GAIA": 116, "SWE Bench": 31}
GOLD_ERRORS_LOADED = {"GAIA": 580, "SWE Bench": 256}

BEST = "Gemini-2.5-Pro-Preview-05-06"


def weighted(weights: dict[str, int]) -> float:
    numerator = sum(_gemini(split).joint_accuracy * weights[split] for split in weights)
    return numerator / sum(weights.values())


def _gemini(split: str) -> paper.Scored:
    return next(row for row in paper.TABLE_1[split] if row.model == BEST)


def test_table_5_divides_to_the_means_it_prints() -> None:
    """The transcription check that does not need the paper open.

    Table 5 prints "977 (mean 8.28)" and three more like it. Those means are the
    only internal consistency the table offers, and they are what fixes the
    reading of the last column: unique error spans divided by traces carrying an
    error, not by total traces.
    """
    printed = ((paper.TABLE_5[0], 8.28, 3.33), (paper.TABLE_5[1], 32.58, 6.19))
    for row, spans_mean, error_span_mean in printed:
        assert round(row.spans / row.traces, 2) == spans_mean
        assert round(row.unique_error_spans / row.traces_with_errors, 2) == error_span_mean


def test_the_conclusion_and_table_1_are_the_same_two_numbers() -> None:
    gaia = _gemini("GAIA").joint_accuracy
    swe = _gemini("SWE Bench").joint_accuracy
    assert (round(gaia, 2), round(swe, 2)) == (0.18, 0.05)


def test_nothing_in_table_1_rounds_to_the_eleven_percent_the_abstract_quotes() -> None:
    """Which figure the audit compares against, settled rather than assumed.

    The paper quotes 11% twice, 18% and 5% once, and Table 1 holds 0.183 and
    0.050. The last three are the same two numbers. 11% is not one of them and
    the closest aggregation, the plain mean, comes out at 0.1165, which rounds up
    to 12. Table 1 says every figure is the mean of three runs, so the unrounded
    per-run pairs are the likeliest explanation and they are not published. Hence
    every comparison in this audit is made per split against Table 1 instead of
    against the 11%.
    """
    plain = (_gemini("GAIA").joint_accuracy + _gemini("SWE Bench").joint_accuracy) / 2
    assert round(plain, 4) == 0.1165
    assert round(plain, 2) != paper.COMBINED_JOINT_PROSE
    assert int(plain * 100) / 100 == paper.COMBINED_JOINT_PROSE


@pytest.mark.parametrize(
    ("name", "weights", "expected"),
    [
        ("gold files the scorer loads", GOLD_FILES_LOADED, 0.155),
        ("gold errors those files carry", GOLD_ERRORS_LOADED, 0.142),
        ("Table 5's own trace counts", {row.split: row.traces for row in paper.TABLE_5}, 0.155),
    ],
)
def test_no_weighting_of_the_two_splits_lands_on_eleven_percent(
    name: str, weights: dict[str, int], expected: float
) -> None:
    assert round(weighted(weights), 3) == expected, name
    assert round(weighted(weights), 2) != paper.COMBINED_JOINT_PROSE


def test_best_published_skips_the_models_that_could_not_read_the_split() -> None:
    """CLE is not a zero and averaging it as one would hand the audit an easier target.

    o1, o3 and claude-3.7-sonnet have no SWE Bench row at all: the paper marks
    them CLE, meaning the split's traces did not fit in the context window. o3
    has the second-best GAIA location accuracy in the table, so treating its
    missing SWE Bench row as 0.000 would be the single most flattering mistake
    available here.
    """
    assert paper.best_published("GAIA", "joint_accuracy").model == BEST
    assert paper.best_published("SWE Bench", "joint_accuracy").model == BEST
    assert paper.best_published("GAIA", "location_accuracy").model == BEST
    assert paper.best_published("SWE Bench", "location_accuracy").model == BEST

    missing = [row.model for row in paper.TABLE_1["SWE Bench"] if row.joint_accuracy is None]
    assert missing == ["OpenAI o1", "OpenAI o3", "Anthropic Claude-3.7-Sonnet"]


def test_both_splits_list_the_same_eight_models_in_the_same_order() -> None:
    gaia, swe = (
        tuple(row.model for row in paper.TABLE_1[split]) for split in ("GAIA", "SWE Bench")
    )
    assert gaia == swe
    assert len(gaia) == 8
