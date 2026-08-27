"""P8 against a stand-in scorer and hand-built annotations.

The constructed trace and the three runs need a scorer, and the real one lives
in the pinned clone. What is offline here is the shape of the trace, the count of
real gold files the defect would reach, and whether the finding can come back
held at all. tests/test_pinned_clone.py runs the three through TRAIL's own
calculate_scores.py and pins the numbers.
"""

from __future__ import annotations

from stand_ins import TAXONOMY
from trailaudit import pairing
from trailaudit.datacheck import HELD, LATENT, VIOLATED
from trailaudit.gold import Annotation
from trailaudit.pairing import LOCATIONS, Latent, Run


def flat(rendered: str) -> str:
    return " ".join(rendered.split())


def runs(with_null_gold: float, clean: float, with_null_prediction: float) -> tuple[Run, ...]:
    return (
        Run("gold null", True, False, with_null_gold, 0.667),
        Run("control", False, False, clean, 1.0),
        Run("prediction null", False, True, with_null_prediction, 1.0),
    )


NOTHING_LATENT = Latent(
    gold_errors=836,
    falsy_categories=0,
    traces_that_would_mispair=0,
    traces_that_would_lose_a_pair=0,
)


def test_the_constructed_trace_puts_the_null_first_and_keeps_two_real_errors() -> None:
    listed = pairing.errors(TAXONOMY, with_null=True)
    assert [one["location"] for one in listed] == list(LOCATIONS)
    assert listed[0]["category"] is None
    assert [one["category"] for one in listed[1:]] == list(TAXONOMY[:2])


def test_the_control_trace_is_the_same_two_errors_without_the_null() -> None:
    """Same real content, so anything separating the two runs is the null and nothing else."""
    with_null = pairing.errors(TAXONOMY, with_null=True)
    without = pairing.errors(TAXONOMY, with_null=False)
    assert without == with_null[1:]


def test_the_categories_come_from_the_taxonomy_it_was_handed() -> None:
    """This module names no labels of its own, so the trace stays valid if the pin moves."""
    invented = ("Alpha Errors", "Beta Failures", "Gamma Issues")
    listed = pairing.errors(invented, with_null=True)
    assert [one["category"] for one in listed[1:]] == ["Alpha Errors", "Beta Failures"]


def test_p8_is_latent_when_no_real_gold_error_can_trigger_it() -> None:
    """The scorer breaks on the constructed trace and no gold file reaches that line.

    Which is the whole of P8's position on the real data, and the reason the
    verdict column carries a third value rather than nine identical cells.
    """
    finding = pairing.p8(runs(0.0, 1.0, 0.0), NOTHING_LATENT)
    assert finding.verdict == LATENT
    rendered = flat(finding.render())
    assert "control scores 1.000 joint" in rendered
    assert "0 of 836 gold errors carry a falsy category" in rendered


def test_p8_is_violated_outright_when_the_gold_carries_a_falsy_category() -> None:
    """One annotated error with no category anywhere in either split would do it."""
    reached = Latent(
        gold_errors=836,
        falsy_categories=1,
        traces_that_would_mispair=1,
        traces_that_would_lose_a_pair=0,
    )
    assert pairing.p8(runs(0.0, 1.0, 0.0), reached).verdict == VIOLATED


def test_p8_holds_when_the_null_costs_nothing() -> None:
    """The branch a scorer that filtered both lists together would take.

    Nothing in the real run reaches it, so without this the finding could have
    been a constant with a table printed underneath.
    """
    assert pairing.p8(runs(1.0, 1.0, 1.0), NOTHING_LATENT).verdict == HELD


def test_p8_fires_on_the_prediction_side_alone() -> None:
    """The judge's own null is the case a real judge hits, and it is a separate run.

    The gold-side run scores 1.000 here, so a finding that only counted gold-side
    damage would name that 1.000 as the cost of the null.
    """
    finding = pairing.p8(runs(1.0, 1.0, 0.0), NOTHING_LATENT)
    assert finding.verdict == LATENT
    rendered = flat(finding.render())
    assert "takes it to 0.000." in rendered
    assert "mentions one further span with no category" in rendered


def test_the_control_is_the_run_carrying_no_null_on_either_side() -> None:
    """It is not the first of the three, and reading it positionally would pick the wrong one."""
    assert pairing.control(runs(0.0, 1.0, 0.0)).joint_accuracy == 1.0
    assert pairing.CASES[0][1] is True


def annotated(*categories: str | None) -> Annotation:
    return Annotation(
        split="fixture",
        trace="one",
        categories=categories,
        locations=tuple(f"span-{index}" for index in range(len(categories))),
    )


def test_a_null_before_the_last_error_mispairs_the_rest() -> None:
    counted = pairing.latent([annotated(None, "Widget Errors", "Flange Misuse")])
    assert counted.falsy_categories == 1
    assert counted.traces_that_would_mispair == 1
    assert counted.traces_that_would_lose_a_pair == 0


def test_a_null_in_the_last_position_loses_a_pair_rather_than_mispairing() -> None:
    """Two different defects out of one line, and calling both mispairing overstates it.

    A falsy category at the end shortens the list without shifting anything, so
    every earlier pair is right and the trace simply loses its last one.
    """
    counted = pairing.latent([annotated("Widget Errors", "Flange Misuse", "")])
    assert counted.traces_that_would_mispair == 0
    assert counted.traces_that_would_lose_a_pair == 1


def test_a_trace_with_no_falsy_category_counts_towards_neither() -> None:
    counted = pairing.latent([annotated("Widget Errors", "Flange Misuse")])
    assert counted == Latent(2, 0, 0, 0)


def test_latent_counts_errors_across_every_annotation_it_was_given() -> None:
    counted = pairing.latent([annotated("Widget Errors"), annotated(None, "Flange Misuse")])
    assert counted.gold_errors == 3
    assert counted.falsy_categories == 1


def test_the_table_carries_every_run_and_both_metrics() -> None:
    printed = pairing.table(runs(0.0, 1.0, 0.0))
    assert len(printed) == 4
    assert "0.000     0.667" in printed[1]


def test_the_report_prints_the_finding_the_trace_and_the_three_runs() -> None:
    """The whole of what `trailaudit pairing` puts on a terminal, which no test ran before."""
    lines, violated = pairing.report(runs(0.0, 1.0, 0.0), NOTHING_LATENT, TAXONOMY)
    printed = "\n".join(lines)

    assert violated, "a latent violation is not held, and the command still exits 3"
    assert "P8" in printed
    assert LATENT in printed
    assert "the constructed trace, which is this repository's and not TRAIL's" in printed
    assert '"category": null' in printed
    assert printed.count("span-one") == 1


def test_the_report_says_nothing_happened_when_the_null_costs_nothing() -> None:
    """The scorer this repository would like to be auditing, and the exit 0 path."""
    lines, violated = pairing.report(runs(1.0, 1.0, 1.0), NOTHING_LATENT, TAXONOMY)
    assert not violated
    assert HELD in "\n".join(lines)
