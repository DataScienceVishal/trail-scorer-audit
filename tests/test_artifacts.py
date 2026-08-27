"""The read, write and diff every committed artifact shares.

The diff is what `--check` reports, so a diff that said "the file changed" and
nothing more would leave a reader with a failing command and no way to tell
whether a headline moved or a count of substrings did.
"""

from __future__ import annotations

import pathlib

import pytest

from trailaudit import adversarial, artifacts, upstream


def test_differences_points_at_the_leaf_that_moved() -> None:
    committed = {"splits": {"GAIA": {"joint": 0.5, "gone": 1}}}
    fresh = {"splits": {"GAIA": {"joint": 0.6, "new": 2}}}
    assert artifacts.differences(committed, fresh) == [
        "splits.GAIA.gone: in the committed artifact, not in this run",
        "splits.GAIA.joint: committed 0.5, ran 0.6",
        "splits.GAIA.new: not in the committed artifact",
    ]


def test_an_identical_rerun_reports_nothing() -> None:
    """Two separately built dicts, not one dict and a shallow copy of it.

    `dict(committed)` copies the top level only, so `committed["splits"]` and
    `copy["splits"]` were the same object and the walk compared it against
    itself. That passes whatever the comparison does.
    """
    committed = {"splits": {"GAIA": {"joint": 0.5, "names": ["a", "b"]}}}
    rerun = {"splits": {"GAIA": {"joint": 0.5, "names": ["a", "b"]}}}
    assert committed["splits"] is not rerun["splits"]
    assert artifacts.differences(committed, rerun) == []


def test_a_list_that_moved_is_reported_whole() -> None:
    """Lists are compared as values, not walked.

    results/normaliser.json holds a list of strings under every one of the 21
    labels, and walking those per element would report a shifted list as a
    finding on every position after the shift.
    """
    moved = artifacts.differences({"strings": ["a", "b"]}, {"strings": ["a", "c"]})
    assert moved == ["strings: committed ['a', 'b'], ran ['a', 'c']"]


def test_loading_an_artifact_from_another_commit_names_the_command_to_rerun(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "adversarial.json"
    artifacts.write(path, {"pinned_commit": "0" * 40})
    with pytest.raises(artifacts.Stale, match="trailaudit adversarial"):
        adversarial.load(path)


def test_a_truncated_artifact_says_which_command_rewrites_it(tmp_path: pathlib.Path) -> None:
    """Half a file on disk used to escape as a json.decoder traceback.

    `load` already had the right voice for the other way an artifact can be
    unusable, which is a pin that moved under it.
    """
    path = tmp_path / "adversarial.json"
    artifacts.write(path, {"pinned_commit": upstream.PINNED_COMMIT, "splits": {}})
    path.write_text(path.read_text(encoding="utf-8")[:30], encoding="utf-8")
    with pytest.raises(artifacts.Stale, match="trailaudit adversarial"):
        adversarial.load(path)


def test_write_creates_the_directory_it_was_pointed_at(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "not" / "there" / "yet.json"
    written = {"pinned_commit": upstream.PINNED_COMMIT, "labels": 21}
    artifacts.write(path, written)
    assert artifacts.load(path, "trailaudit normaliser") == written
