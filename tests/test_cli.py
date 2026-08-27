from __future__ import annotations

import pathlib

import pytest

from trailaudit import spans
from trailaudit.cli import build_parser, main


def test_fetch_check_on_an_absent_clone_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fetch", "--check", "--into", str(tmp_path / "not-here")]) == 2
    assert "Run `trailaudit fetch`" in capsys.readouterr().err


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_data_check_without_a_clone_exits_three(
    repo_root: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """3 rather than 1, because 1 means the audit could not trust its input.

    P9 alone is enough to make this non-zero off the committed index, which is
    what a reader gets on a fresh clone before downloading anything.
    """
    argv = ["data-check", "--no-clone", "--index", str(repo_root / spans.COMMITTED)]
    assert main(argv) == 3
    assert "VIOLATED" in capsys.readouterr().out


def test_data_check_asks_for_the_clone_rather_than_reporting_two_held(
    tmp_path: pathlib.Path, repo_root: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "data-check",
        "--into",
        str(tmp_path / "no-clone-here"),
        "--index",
        str(repo_root / spans.COMMITTED),
    ]
    assert main(argv) == 2
    printed = capsys.readouterr()
    assert "--no-clone" in printed.err
    assert "HELD" not in printed.out
