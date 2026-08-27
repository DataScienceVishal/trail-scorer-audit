"""Figures in README.md, checked against the things that produce them.

Slice 4 replaces this with generated blocks. Until then the README states
numbers by hand, and a number stated by hand is a claim: `twicerun` shipped
eight stale figures across its prose and three of them were counted correctly
elsewhere in its own tree. Nothing mechanical caught those. This is the cheap
version of the mechanical thing, and it covers the figures a reader is most
likely to check first.

What it cannot cover is anything that needs the gold annotations, which are not
committed. 147, 836 and the four dropped errors are pinned by
tests/test_pinned_clone.py instead, which skips without the download.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from trailaudit import datacheck, paper, spans, upstream


@pytest.fixture(scope="module")
def readme(repo_root: pathlib.Path) -> str:
    return (repo_root / "README.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index(repo_root: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    return spans.load(repo_root / spans.COMMITTED)


def test_the_pin_in_the_prose_is_the_pin_in_the_code(readme: str) -> None:
    assert upstream.PINNED_COMMIT in readme
    assert upstream.SCORER_SHA256 in readme
    assert upstream.CORPUS_SHA256 in readme
    assert upstream.PINNED_COMMIT[:12] in readme


def test_the_table_the_readme_pastes_is_the_table_the_command_prints(
    readme: str, index: dict[str, dict[str, list[str]]]
) -> None:
    """The pasted terminal block is the most quotable thing in the file and the easiest to
    let rot, so it is regenerated here and compared line for line."""
    printed = datacheck.table_5_rows(datacheck.measure(None, index))
    unmeasurable = {"total errors", "unique error spans", "traces with an error"}
    for line in printed:
        if any(line.startswith(label) for label in unmeasurable):
            continue
        assert line.rstrip() in readme, line


def test_the_split_counts_in_the_prose_come_from_the_index(
    readme: str, index: dict[str, dict[str, list[str]]]
) -> None:
    gaia = len(index["GAIA"])
    swe = len(index["SWE Bench"])
    assert f"has {gaia}, and {gaia} gold annotation files" in readme
    assert f"SWE Bench matches at {swe}" in readme
    assert f"Table 5 of the paper counts {paper.published_for('GAIA').traces} GAIA traces" in readme


def test_the_span_count_in_the_prose_comes_from_the_index(
    readme: str, index: dict[str, dict[str, list[str]]]
) -> None:
    walked = sum(len(ids) for ids in index["GAIA"].values())
    published = paper.published_for("GAIA").spans
    assert f"gives {walked:,} spans across the\n{len(index['GAIA'])} GAIA traces" in readme
    assert re.search(rf"Table 5 says {published}\.", readme)


def test_the_paper_totals_in_the_prose_are_the_transcribed_ones(readme: str) -> None:
    traces = sum(row.traces for row in paper.TABLE_5)
    errors = sum(row.errors for row in paper.TABLE_5)
    assert f"Table 5's rows sum to\n{traces} and {errors}" in readme
    assert f"says {paper.ABSTRACT_TRACES} traces and {paper.ABSTRACT_ERRORS} errors" in readme
