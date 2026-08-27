"""P1, P2 and the artifact, against hand-built runs rather than the real 186 MB.

Every SplitRun here is assembled from made-up numbers, which is the only way to
see what the report does when a property holds. On the real data both come back
violated, so a suite that only ever ran against the clone would never exercise
the HELD branch and would not notice if it had been wired to the wrong metric.
"""

from __future__ import annotations

from stand_ins import TAXONOMY
from trailaudit import adversarial, upstream
from trailaudit.adversarial import MISSING_SHARD, SplitRun
from trailaudit.datacheck import HELD, VIOLATED
from trailaudit.gold import Annotation
from trailaudit.predictors import PREDICTORS
from trailaudit.scoring import Scores

GEMINI_JOINT = {"GAIA": 0.183, "SWE Bench": 0.050}


def flat(rendered: str) -> str:
    """Findings wrap at 92 columns, so a phrase under test can straddle two lines."""
    return " ".join(rendered.split())


def scores(joint: float, location: float, predicted: int) -> Scores:
    return Scores(
        joint_accuracy=joint,
        location_accuracy=location,
        joint_precision=0.0,
        location_precision=0.0,
        files_globbed=10,
        files_processed=10,
        predicted_errors=predicted,
        gold_errors=100,
        skipped=(),
    )


def split_run(split: str, joint: float, location: float, absent=None) -> SplitRun:
    return SplitRun(
        split=split,
        scored={one.name: scores(joint, location, 900) for one in PREDICTORS},
        gold_files=10,
        absent_locations=absent or {},
        traces_with_gold_errors=9,
    )


def both(joint: float, location: float, absent=None) -> list[SplitRun]:
    return [split_run(one.name, joint, location, absent) for one in upstream.SPLITS]


def test_p1_is_violated_when_the_gold_blind_predictor_beats_the_published_best() -> None:
    finding = adversarial.p1(both(0.9, 0.9))
    assert finding.verdict == VIOLATED
    rendered = flat(finding.render())
    assert "Gemini-2.5-Pro-Preview-05-06" in rendered
    assert "0.900 against 0.183" in rendered


def test_p1_holds_when_it_does_not() -> None:
    """The branch the real data never takes.

    If this ever fires against the clone the project has failed in the way the
    spec named: the metric is harder to game than a first-hand check suggested
    and the README says that instead.
    """
    assert adversarial.p1(both(0.04, 0.2)).verdict == HELD


def test_p1_is_violated_on_one_metric_alone() -> None:
    """SWE Bench's published joint accuracy is 0.050, so joint is the easier half.

    A predictor that beat location accuracy and not joint would still violate
    P1, which says "on either headline metric". Reading only the joint column
    would have made that a pass.
    """
    below_on_joint = 0.9 * GEMINI_JOINT["SWE Bench"]
    assert adversarial.p1(both(below_on_joint, 0.9)).verdict == VIOLATED


def test_p2_holds_when_every_gold_location_is_indexed() -> None:
    finding = adversarial.p2(both(0.9, 0.9))
    assert finding.verdict == HELD
    assert "200 gold errors" in flat(finding.render())


def test_p2_names_the_trace_and_says_when_they_share_a_literal() -> None:
    absent = {"e7bdf7bbf6b931c3be95afe323704041": [MISSING_SHARD]}
    finding = adversarial.p2(both(0.9, 0.9, absent))
    assert finding.verdict == VIOLATED
    rendered = flat(finding.render())
    assert "e7bdf7bbf6b931c3be95afe323704041" in rendered
    assert MISSING_SHARD in rendered
    assert f"All of them are the literal '{MISSING_SHARD}'" in rendered


def test_p2_does_not_claim_a_shared_literal_when_there_is_not_one() -> None:
    absent = {"one": [MISSING_SHARD], "two": ["something else entirely"]}
    rendered = flat(adversarial.p2(both(0.9, 0.9, absent)).render())
    assert "All of them are the literal" not in rendered


def test_the_ceiling_is_the_share_of_traces_carrying_a_gold_error() -> None:
    """No predictor can pass this, gold-exact included, and the report says so.

    Lines 54 and 58 return the int 0 for a trace with no gold errors while its
    denominator still counts the trace, so the reachable maximum is below 1.000
    wherever the gold has an empty file.
    """
    assert split_run("GAIA", 0.9, 0.9).ceiling == 0.9


def test_cases_carry_the_span_ids_and_the_gold_paired_back_up() -> None:
    index = {"t1": ["aaaa000000000001", "aaaa000000000002"]}
    annotations = {
        "t1": Annotation(
            split="GAIA",
            trace="t1",
            categories=("Widget Errors",),
            locations=("aaaa000000000002",),
        )
    }
    built = adversarial.cases_for(upstream.SPLITS[0], index, annotations, TAXONOMY)
    assert built["t1"].span_ids == ("aaaa000000000001", "aaaa000000000002")
    assert built["t1"].gold == ({"location": "aaaa000000000002", "category": "Widget Errors"},)


def test_a_trace_whose_gold_did_not_parse_still_gets_a_case_with_empty_gold() -> None:
    """So the scorer's only complaint about the split is the parse failure.

    Without a prediction file the scorer prints a second message at line 154 and
    the report cannot say the denominator moved for exactly one reason.
    """
    only = {"broken": ["aaaa000000000001"]}
    built = adversarial.cases_for(upstream.SPLITS[0], only, {}, TAXONOMY)
    assert built["broken"].gold == ()
    assert built["broken"].span_ids == ("aaaa000000000001",)


def test_locations_off_the_index_reports_per_trace() -> None:
    index = {"t1": ["aaaa000000000001"], "t2": ["aaaa000000000002"]}
    annotations = {
        "t1": Annotation("GAIA", "t1", ("c",), ("aaaa000000000001",)),
        "t2": Annotation("GAIA", "t2", ("c", "c"), (MISSING_SHARD, "aaaa000000000002")),
    }
    assert adversarial.locations_off_the_index(annotations, index) == {"t2": [MISSING_SHARD]}


def test_the_report_carries_both_findings_both_tables_and_the_precision_column() -> None:
    """What `trailaudit adversarial` puts on a terminal, which no test ran before."""
    absent = {"e7bdf7bbf6b931c3be95afe323704041": [MISSING_SHARD]}
    lines, violated = adversarial.report(both(0.9, 0.9, absent))
    printed = "\n".join(lines)

    assert violated
    assert "P1" in printed and "P2" in printed
    assert all(one.name in printed for one in PREDICTORS)
    assert all(one.name in printed for one in upstream.SPLITS)
    assert "best published, Table 1" in printed
    assert "precision, which neither headline metric reports" in printed


def test_the_report_reports_nothing_when_the_predictors_stay_under_the_published_row() -> None:
    """Both properties held, which is the run this project would have had nothing to say about."""
    lines, violated = adversarial.report(both(0.04, 0.2))
    assert not violated
    assert "P1" in "\n".join(lines)
    assert VIOLATED not in "\n".join(lines)
