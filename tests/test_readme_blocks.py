"""The README against the artifacts it is rendered from.

This is the whole of slice 4 stated as a test failure. Every figure in that file
sits inside a marker pair, `trailaudit report --format md` writes the bodies,
and the only way to move a number is to rerun the measurement and commit what
came out. It runs offline against committed JSON and never touches the clone.

The file it replaces, test_readme_numbers.py, checked a handful of hand-typed
figures by searching for them in the prose. That caught the ones somebody
thought to write a search for.
"""

from __future__ import annotations

import pathlib

import pytest

from trailaudit import paper, report
from trailaudit.report import BLOCKS


@pytest.fixture(scope="module")
def markdown(repo_root: pathlib.Path) -> str:
    return (repo_root / report.README).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered(repo_root: pathlib.Path) -> dict[str, str]:
    return report.render(report.load(repo_root))


REGENERATE = "Run `uv run trailaudit report --format md` and commit what it writes."


def test_no_block_has_drifted_from_the_artifact_behind_it(
    markdown: str, rendered: dict[str, str]
) -> None:
    assert report.stale(markdown, rendered) == [], REGENERATE


def test_the_readme_carries_every_block_and_no_others(
    markdown: str, rendered: dict[str, str]
) -> None:
    """Both directions, which is the half that is easy to leave out.

    stale() refuses a mismatch rather than reporting no drift across the blocks
    that happen to line up, so this asserts the same thing a second way: the set
    of markers in the file is the set of generators, exactly.
    """
    assert set(report.blocks_in(markdown)) == set(BLOCKS)


def test_no_score_is_typed_into_the_prose(markdown: str) -> None:
    assert report.loose_scores(markdown) == [], REGENERATE


def test_the_headline_in_the_opening_is_the_transcribed_one(markdown: str) -> None:
    """The one number in the prose that is not generated, because nothing here measures it.

    It is TRAIL's own headline, transcribed in paper.py with the pages it appears
    on, and written as a percentage rather than as a score so it reads as theirs
    and stays out of the shape `loose_scores` hunts for. The eleven-percent block
    reconciles it against Table 1's two cells; this holds the opening sentence to
    the same transcription.

    The opening is everything above the first `<details>`, which is what a reader
    sees before clicking anything. It cannot be the first `## `: the findings
    table sits under a heading and above every fold, so that split would stop
    short of it. A split matching nothing at all is the worse failure, because it
    hands the assertion the whole README including the eleven-percent block that
    reconciles the figure, and the check passes on the thing it was meant to
    hold to account.
    """
    opening = " ".join(markdown.split("<details")[0].split())
    assert f"{paper.COMBINED_JOINT_PROSE:.0%}".replace("%", " percent") in opening


def test_the_pre_registration_is_committed_linked_and_carries_the_nine(
    markdown: str, repo_root: pathlib.Path
) -> None:
    """The README asserts four times over that the nine were fixed before any code existed.

    The spec they came from is a private working document covering a portfolio
    of unrelated projects, so what is committed is that one section, with its own
    note on what a reader can and cannot check. A claim about a document nobody
    can read is worth less than the document.
    """
    spec = (repo_root / "docs" / "pre-registration.md").read_text(encoding="utf-8")
    assert "docs/pre-registration.md" in markdown
    for name in report.PROPERTIES:
        assert f"**{name}**" in spec, name


def test_nothing_is_left_to_be_written(markdown: str) -> None:
    for placeholder in ("TODO", "FIXME", "coming soon", "lorem ipsum"):
        assert placeholder.lower() not in markdown.lower()
