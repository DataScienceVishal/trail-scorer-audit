"""What data-check reports, and what it refuses to report when it cannot look.

All offline. The gold half runs against the hand-built fixtures and the P9 half
runs against the committed span index, which is the same artifact `data-check
--no-clone` uses on a fresh clone.
"""

from __future__ import annotations

import pathlib

import pytest

from stand_ins import TAXONOMY, strip_only
from trailaudit import datacheck, gold, paper, spans
from trailaudit.datacheck import HELD, UNMEASURED, VIOLATED, Gold


@pytest.fixture
def annotated(annotations: pathlib.Path) -> Gold:
    loaded, failures = gold.read_directory(annotations, "fixture")
    return Gold(
        annotations=loaded,
        failures=failures,
        vocabulary=gold.vocabulary(loaded),
        taxonomy=TAXONOMY,
        normalise=strip_only,
    )


def test_p3_without_a_clone_is_unmeasured_and_not_held() -> None:
    """The guard that stops a property passing because nothing looked at it.

    HELD here would be the worst outcome the tool has: a pre-registration that
    reports a clean sweep in CI, where the gold annotations have never been
    downloaded, and reads as evidence that TRAIL's files are fine.
    """
    finding = datacheck.p3(None)
    assert finding.verdict == UNMEASURED
    assert finding.verdict != HELD
    assert "trailaudit fetch" in finding.render()


def test_p4_without_a_clone_is_unmeasured_and_not_held() -> None:
    finding = datacheck.p4(None)
    assert finding.verdict == UNMEASURED
    assert finding.verdict != HELD


def test_p3_names_the_file_and_the_denominator(annotated: Gold) -> None:
    finding = datacheck.p3(annotated)
    assert finding.verdict == VIOLATED
    rendered = finding.render()
    assert "3 files on disk, 2 parse, 1 does not" in rendered
    assert "trailing_comma.json: ',' at line 8 column 10" in rendered
    assert "divides by 2" in rendered


def test_p3_holds_when_everything_parses(annotated: Gold) -> None:
    intact = Gold(
        annotations=annotated.annotations,
        failures=[],
        vocabulary=annotated.vocabulary,
        taxonomy=annotated.taxonomy,
        normalise=annotated.normalise,
    )
    assert datacheck.p3(intact).verdict == HELD


def test_p4_counts_spellings_and_the_errors_they_cover(annotated: Gold) -> None:
    rendered = datacheck.p4(annotated).render()
    assert datacheck.p4(annotated).verdict == VIOLATED
    assert f"6 distinct spellings over 7 errors, against {len(TAXONOMY)} labels" in rendered
    assert "4 are not a label, covering 4 errors" in rendered


def test_p9_holds_when_the_counts_agree() -> None:
    agreeing = {row.split: {"traces": row.traces, "spans": row.spans} for row in paper.TABLE_5}
    assert datacheck.p9(agreeing).verdict == HELD


def test_p9_is_violated_when_one_split_is_short() -> None:
    short = {row.split: {"traces": row.traces, "spans": row.spans} for row in paper.TABLE_5}
    short["GAIA"]["traces"] -= 1
    assert datacheck.p9(short).verdict == VIOLATED


def test_a_row_nobody_measured_says_so_rather_than_showing_zero() -> None:
    partial = {row.split: {"traces": row.traces, "spans": row.spans} for row in paper.TABLE_5}
    rendered = "\n".join(datacheck.table_5_rows(partial))
    assert "unmeasured" in rendered
    assert "579 / 0" not in rendered


def test_the_distribution_marks_a_row_the_normaliser_left_outside(annotated: Gold) -> None:
    rows = datacheck.distribution(annotated.vocabulary, annotated.taxonomy, annotated.normalise)
    marked = [row for row in rows if row.endswith("*")]
    assert len(marked) == 3
    assert any(row.startswith("Widget Errors") and not row.endswith("*") for row in rows)


def test_report_without_a_clone_still_finds_p9(repo_root: pathlib.Path) -> None:
    """`data-check --no-clone` on a fresh clone, which is what CI would run."""
    index = spans.load(repo_root / spans.COMMITTED)
    lines, violated = datacheck.report(datacheck.inspect(None, index))
    rendered = "\n".join(lines)
    assert violated
    p9_line = next(line for line in rendered.splitlines() if line.startswith("P9  "))
    assert p9_line.endswith(VIOLATED)
    assert rendered.count(UNMEASURED) == 2
    assert "total traces" in rendered
