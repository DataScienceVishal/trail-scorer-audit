from __future__ import annotations

import pathlib

import pytest

from trailaudit.cli import build_parser, main


def test_fetch_check_on_an_absent_clone_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["fetch", "--check", "--into", str(tmp_path / "not-here")]) == 2
    assert "Run `trailaudit fetch`" in capsys.readouterr().err


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
