"""What each command does at its exit codes, which is where the failure paths live.

`_settle` is called directly rather than through a command, because all four of
its callers need the 186 MB on disk and it is the shared exit 1 and exit 3 path
for every one of them.
"""

from __future__ import annotations

import argparse
import json
import pathlib

import pytest

from trailaudit import artifacts, cli, spans, upstream
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


def test_adversarial_asks_for_the_clone_rather_than_scoring_against_nothing(
    tmp_path: pathlib.Path, repo_root: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No --no-clone here, unlike data-check.

    data-check can report P9 off the committed span index alone. P1 and P2 need
    TRAIL's scorer and TRAIL's gold, and a flag that let this run without them
    would only be able to produce a number that came from somewhere else.
    """
    argv = [
        "adversarial",
        "--into",
        str(tmp_path / "no-clone-here"),
        "--index",
        str(repo_root / spans.COMMITTED),
    ]
    assert main(argv) == 2
    assert "trailaudit fetch" in capsys.readouterr().err


def trace_tree(root: pathlib.Path, by_split: dict[str, dict[str, list[str]]]) -> pathlib.Path:
    """A clone-shaped directory of traces for `index` to walk, invented here.

    Nothing in it comes from the benchmark. The identifiers are made up and each
    file carries a span tree and nothing else, which is all spans.build reads.
    """
    for split in upstream.SPLITS:
        here = root / split.traces
        here.mkdir(parents=True)
        for trace, ids in by_split[split.name].items():
            (here / f"{trace}.json").write_text(
                json.dumps({"spans": [{"span_id": one} for one in ids]}), encoding="utf-8"
            )
    return root


TRACES = {"GAIA": {"t1": ["aaaa000000000001", "aaaa000000000002"]}, "SWE Bench": {"t2": ["bbbb"]}}


def test_index_check_agrees_with_the_tree_it_was_built_from(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clone = trace_tree(tmp_path / "clone", TRACES)
    committed = tmp_path / "spans.json"
    committed.write_text(spans.render(TRACES), encoding="utf-8")

    assert main(["index", "--check", "--into", str(clone), "--out", str(committed)]) == 0
    assert "matches a fresh walk" in capsys.readouterr().out


def test_index_check_names_the_trace_that_moved_and_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clone = trace_tree(tmp_path / "clone", TRACES)
    committed = tmp_path / "spans.json"
    committed.write_text(spans.render(TRACES), encoding="utf-8")
    (clone / upstream.SPLITS[0].traces / "t1.json").write_text(
        json.dumps({"spans": [{"span_id": "aaaa000000000001"}, {"span_id": "cccc"}]}),
        encoding="utf-8",
    )

    assert main(["index", "--check", "--into", str(clone), "--out", str(committed)]) == 1
    complaint = capsys.readouterr().err
    assert "GAIA/t1" in complaint
    assert "'cccc'" in complaint


def test_index_writes_what_it_walked(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clone = trace_tree(tmp_path / "clone", TRACES)
    for directory in upstream.CORPUS_DIRS[1:]:
        (clone / directory).mkdir(parents=True)
    monkeypatch.setattr(upstream, "CORPUS_SHA256", upstream.corpus_digest(clone))
    out = tmp_path / "written" / "spans.json"

    assert main(["index", "--into", str(clone), "--out", str(out)]) == 0
    assert spans.load(out) == TRACES
    printed = " ".join(capsys.readouterr().out.split())
    assert "GAIA 1 traces 2 spans" in printed


def test_a_missing_clone_keeps_the_message_written_for_it(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """MissingClone subclasses FileNotFoundError to carry that sentence.

    Catching the two together printed the errno string instead, which names a
    path and not the command that writes it.
    """
    committed = tmp_path / "spans.json"
    committed.write_text(spans.render(TRACES), encoding="utf-8")

    argv = ["index", "--check", "--into", str(tmp_path / "nothing"), "--out", str(committed)]
    assert main(argv) == 2
    assert "Run `trailaudit fetch` first" in capsys.readouterr().err


def test_a_file_that_is_not_there_is_named(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["report", "--check", "--root", str(tmp_path)]) == 2
    assert "no file at" in capsys.readouterr().err


def test_an_index_built_at_another_commit_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """1 rather than 3: the audit could not trust its input, so it reported nothing."""
    document = json.loads(spans.render(TRACES))
    document["pinned_commit"] = "0" * 40
    stale = tmp_path / "spans.json"
    stale.write_text(json.dumps(document), encoding="utf-8")

    assert main(["data-check", "--no-clone", "--index", str(stale)]) == 1
    assert "trailaudit index" in capsys.readouterr().err


def test_no_clone_cannot_check_the_artifact_two_thirds_of_which_needs_the_gold(
    repo_root: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "data-check",
        "--no-clone",
        "--check",
        "--index",
        str(repo_root / spans.COMMITTED),
    ]
    assert main(argv) == 2
    assert "P3 and P4 are two thirds of what is in it" in capsys.readouterr().err


def test_report_check_passes_against_the_committed_readme(
    repo_root: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one end-to-end property CI can enforce, run the way CI runs it."""
    argv = [
        "report",
        "--check",
        "--readme",
        str(repo_root / "README.md"),
        "--root",
        str(repo_root),
    ]
    assert main(argv) == 0
    assert "all of them what the artifacts render" in capsys.readouterr().out


def readme_copy(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    copied = tmp_path / "README.md"
    copied.write_text((repo_root / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
    return copied


def test_report_check_names_a_block_that_no_longer_matches(
    repo_root: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The doctored row is every-span-once, which is in the headline table and nowhere else.

    The row the claim rests on is now in two blocks: the full table and the
    three-row teaser above the fold. Doctoring that one would fail two blocks at
    once and the assertion below would pass on either, which is a weaker test
    than it reads as.
    """
    copied = readme_copy(repo_root, tmp_path)
    copied.write_text(
        copied.read_text(encoding="utf-8").replace("| 0.088 | 0.974 |", "| 0.111 | 0.222 |"),
        encoding="utf-8",
    )

    argv = ["report", "--check", "--readme", str(copied), "--root", str(repo_root)]
    assert main(argv) == 1
    assert "block headline is not what the artifacts render" in capsys.readouterr().err


def test_report_check_catches_a_score_typed_into_the_prose(
    repo_root: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copied = readme_copy(repo_root, tmp_path)
    with copied.open("a", encoding="utf-8") as handle:
        handle.write("\nand on the second split it reached 0.958.\n")

    argv = ["report", "--check", "--readme", str(copied), "--root", str(repo_root)]
    assert main(argv) == 1
    assert "states a score outside every block" in capsys.readouterr().err


def test_report_rewrites_the_block_that_moved_and_then_says_it_matches(
    repo_root: pathlib.Path, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copied = readme_copy(repo_root, tmp_path)
    original = copied.read_text(encoding="utf-8")
    copied.write_text(original.replace("| 0.973 | 0.974 |", "| 0.111 | 0.222 |"), encoding="utf-8")

    # That figure is in three blocks: the headline table, the per-category table
    # and the teaser above the fold, which is the point of rewriting by block
    # rather than by string.
    argv = ["report", "--readme", str(copied), "--root", str(repo_root)]
    assert main(argv) == 0
    rewritten = capsys.readouterr().out
    assert rewritten.startswith("rewrote 3 of ")
    for name in ("headline", "per-category", "teaser"):
        assert name in rewritten, name
    assert copied.read_text(encoding="utf-8") == original

    assert main(argv) == 0
    assert "already matches the artifacts" in capsys.readouterr().out


def settling(tmp_path: pathlib.Path, check: bool) -> argparse.Namespace:
    return argparse.Namespace(check=check, out=tmp_path / "run.json")


def reread(path: pathlib.Path) -> dict:
    return artifacts.load(path, rerun="trailaudit adversarial")


MEASURED = {"pinned_commit": upstream.PINNED_COMMIT, "splits": {"GAIA": {"joint": 0.5}}}


def test_settle_writes_the_artifact_and_carries_the_verdict(tmp_path: pathlib.Path) -> None:
    assert cli._settle(settling(tmp_path, check=False), MEASURED, reread, violated=True) == 3
    assert reread(tmp_path / "run.json") == MEASURED
    assert cli._settle(settling(tmp_path, check=False), MEASURED, reread, violated=False) == 0


def test_settle_reproducing_a_violation_still_exits_three(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts.write(tmp_path / "run.json", MEASURED)
    assert cli._settle(settling(tmp_path, check=True), MEASURED, reread, violated=True) == 3
    assert "matches this run" in capsys.readouterr().out


def test_settle_turns_a_moved_figure_into_exit_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """1 outranks 3 here: the printed report and the committed file are two claims."""
    artifacts.write(tmp_path / "run.json", MEASURED)
    moved = {**MEASURED, "splits": {"GAIA": {"joint": 0.6}}}

    assert cli._settle(settling(tmp_path, check=True), moved, reread, violated=True) == 1
    assert "splits.GAIA.joint: committed 0.5, ran 0.6" in capsys.readouterr().err
