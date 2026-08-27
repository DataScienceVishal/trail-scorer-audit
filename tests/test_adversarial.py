"""P1, P2 and the artifact, against hand-built runs rather than the real 186 MB.

Every SplitRun here is assembled from made-up numbers, which is the only way to
see what the report does when a property holds. On the real data both come back
violated, so a suite that only ever ran against the clone would never exercise
the HELD branch and would not notice if it had been wired to the wrong metric.
"""

from __future__ import annotations

import pathlib

import pytest

from stand_ins import TAXONOMY
from trailaudit import adversarial, upstream
from trailaudit.adversarial import MISSING_SHARD, SplitRun
from trailaudit.datacheck import HELD, VIOLATED
from trailaudit.gold import Annotation
from trailaudit.predictors import PREDICTORS
from trailaudit.scoring import Scores
from trailaudit.spans import IndexInconsistent

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


def test_differences_points_at_the_leaf_that_moved() -> None:
    committed = {"splits": {"GAIA": {"joint": 0.5, "gone": 1}}}
    fresh = {"splits": {"GAIA": {"joint": 0.6, "new": 2}}}
    assert adversarial.differences(committed, fresh) == [
        "splits.GAIA.gone: in the committed artifact, not in this run",
        "splits.GAIA.joint: committed 0.5, ran 0.6",
        "splits.GAIA.new: not in the committed artifact",
    ]


def test_an_identical_rerun_reports_nothing() -> None:
    same = {"splits": {"GAIA": {"joint": 0.5, "names": ["a", "b"]}}}
    assert adversarial.differences(same, dict(same)) == []


def test_loading_an_artifact_from_another_commit_says_what_to_rerun(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "adversarial.json"
    path.write_text(adversarial.render({"pinned_commit": "0" * 40}), encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="trailaudit adversarial"):
        adversarial.load(path)
