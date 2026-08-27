"""P7, against hand-built rows rather than the 186 MB.

The real data violates it on both splits, so a suite that only ever ran against
the clone would never take the HELD branch and would not notice if the finding
had been wired to the wrong pair of predictors. Every Row here is assembled from
numbers the test chose.
"""

from __future__ import annotations

import pytest

from trailaudit import catf1
from trailaudit.catf1 import DIFFER_ONLY_IN_WHERE, Row
from trailaudit.datacheck import HELD, VIOLATED

LABELS = ("Widget Errors", "Sprocket-only", "Gasket Handling Failures")


def block(*supports: int) -> dict[str, dict[str, float]]:
    return {
        label: {
            "precision": support / 10,
            "recall": 1.0 if support else 0.0,
            "f1": 0.5 if support else 0.0,
            "support": float(support),
        }
        for label, support in zip(LABELS, supports, strict=True)
    }


def row(predictor: str, location: float, per_category: dict, split: str = "GAIA") -> Row:
    return Row(
        split=split,
        predictor=predictor,
        joint_accuracy=location / 2,
        location_accuracy=location,
        weighted_f1=0.5,
        files_scored=10,
        per_category=per_category,
    )


def pair(located_block: dict, blind_block: dict) -> tuple[Row, ...]:
    return (
        row(DIFFER_ONLY_IN_WHERE[0], 0.9, located_block),
        row(DIFFER_ONLY_IN_WHERE[1], 0.0, blind_block),
    )


def flat(rendered: str) -> str:
    return " ".join(rendered.split())


def test_p7_is_violated_when_the_two_predictors_score_the_same_block() -> None:
    finding = catf1.p7(pair(block(4, 2, 0), block(4, 2, 0)))
    assert finding.verdict == VIOLATED
    assert "0.900 against 0.000" in flat(finding.render())


def test_p7_holds_when_the_block_moves_with_the_locations() -> None:
    """The branch the real data never takes on either split.

    If this ever fires against the clone then category F1 does see a location
    somewhere, and the finding is wrong rather than the benchmark.
    """
    assert catf1.p7(pair(block(4, 2, 0), block(3, 2, 0))).verdict == HELD


def test_p7_needs_both_predictors_before_it_says_anything() -> None:
    """One row cannot be identical to anything, and must not read as a violation."""
    alone = (row(DIFFER_ONLY_IN_WHERE[1], 0.0, block(4, 2, 0)),)
    assert catf1.p7(alone).verdict == HELD


def test_a_split_where_the_block_moves_is_left_out_of_the_finding() -> None:
    rows = pair(block(4, 2, 0), block(4, 2, 0)) + (
        row(DIFFER_ONLY_IN_WHERE[0], 0.9, block(4, 2, 0), split="SWE Bench"),
        row(DIFFER_ONLY_IN_WHERE[1], 0.0, block(1, 2, 0), split="SWE Bench"),
    )
    assert catf1.indistinguishable(rows, "GAIA")
    assert not catf1.indistinguishable(rows, "SWE Bench")
    assert "SWE Bench" not in flat(catf1.p7(rows).render())


def test_supported_counts_only_the_categories_the_gold_uses() -> None:
    scored = row("any", 0.0, block(4, 0, 7))
    assert scored.supported == ["Widget Errors", "Gasket Handling Failures"]
    assert scored.at_full_recall == ["Widget Errors", "Gasket Handling Failures"]


def test_a_supported_category_below_full_recall_is_not_counted_as_at_it() -> None:
    partial = block(4, 2, 0)
    partial["Widget Errors"]["recall"] = 0.75
    assert row("any", 0.0, partial).at_full_recall == ["Sprocket-only"]


def test_measure_turns_the_numpy_scalars_into_floats_in_taxonomy_order() -> None:
    """json.dumps refuses a numpy float, and the artifact is written at the end of the run."""
    returned = {
        "category_metrics": {
            label: {"precision": 0.5, "recall": 1.0, "f1": 0.6, "support": 3}
            for label in reversed(LABELS)
        }
    }
    converted = catf1.measure(returned, LABELS)
    assert list(converted) == list(LABELS)
    assert all(isinstance(value, float) for one in converted.values() for value in one.values())


def test_measure_keeps_every_column_the_scorer_publishes() -> None:
    returned = {
        "category_metrics": {
            label: {"precision": 0.5, "recall": 1.0, "f1": 0.6, "support": 3, "extra": 9}
            for label in LABELS
        }
    }
    assert set(catf1.measure(returned, LABELS)["Widget Errors"]) == set(catf1.COLUMNS)


def test_the_lineup_table_puts_location_next_to_the_category_columns() -> None:
    rows = pair(block(4, 2, 0), block(4, 2, 0))
    printed = catf1.lineup_table(rows, "GAIA")
    assert "location" in printed[0] and "recall 1.000" in printed[0]
    assert printed[-1].startswith(DIFFER_ONLY_IN_WHERE[1])


def test_the_category_table_leads_with_the_categories_the_gold_uses_most() -> None:
    printed = catf1.category_table(row("any", 0.0, block(2, 9, 0)))
    assert printed[1].startswith("Sprocket-only")
    assert printed[-1].startswith("Gasket Handling Failures")


@pytest.mark.parametrize("split", ["GAIA", "SWE Bench"])
def test_paired_returns_the_located_row_first(split: str) -> None:
    rows = (
        row(DIFFER_ONLY_IN_WHERE[1], 0.0, block(4, 2, 0), split=split),
        row(DIFFER_ONLY_IN_WHERE[0], 0.9, block(4, 2, 0), split=split),
    )
    located, blind = catf1.paired(rows, split)
    assert located.predictor == DIFFER_ONLY_IN_WHERE[0]
    assert blind.predictor == DIFFER_ONLY_IN_WHERE[1]
