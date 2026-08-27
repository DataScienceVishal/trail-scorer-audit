"""The pin, tested against a fake clone rather than the real one.

Everything here runs with no network and no 186 MB download. What it cannot
check offline is that the committed digest is the digest of the real
calculate_scores.py, which is what `trailaudit fetch --check` is for and what
tests/test_pinned_clone.py asserts when the clone happens to be present.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from trailaudit import upstream
from trailaudit.upstream import MissingClone, PinMismatch

SCORER_SOURCE = '''
import numpy as np


def main(ground_truth_dir, generated_dir):
    all_categories = ["Alpha", "Beta Errors", "Gamma"]
    return all_categories


if __name__ == "__main__":
    raise SystemExit(main("a", "b"))
'''


@pytest.fixture
def fake_clone(tmp_path: pathlib.Path) -> pathlib.Path:
    """A clone-shaped directory with three dataset JSONs and a stand-in scorer.

    The contents are made up. Nothing from patronus-ai/trail-benchmark is
    committed to this repository, so a test that needs a tree to walk has to
    build one.
    """
    clone = tmp_path / "clone"
    for index, directory in enumerate(upstream.CORPUS_DIRS):
        here = clone / directory
        here.mkdir(parents=True)
        for name in ("beta", "alpha"):
            (here / f"{name}{index}.json").write_text(
                json.dumps({"trace_id": f"{name}{index}", "spans": []}), encoding="utf-8"
            )
    scorer = upstream.scorer_path(clone)
    scorer.parent.mkdir(parents=True, exist_ok=True)
    scorer.write_text(SCORER_SOURCE, encoding="utf-8")
    return clone


@pytest.fixture
def pin_to_fake(fake_clone: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    scorer = upstream.sha256_of(upstream.scorer_path(fake_clone))
    monkeypatch.setattr(upstream, "SCORER_SHA256", scorer)
    monkeypatch.setattr(upstream, "CORPUS_SHA256", upstream.corpus_digest(fake_clone))
    return fake_clone


def test_scorer_digest_refuses_an_edited_file(pin_to_fake: pathlib.Path) -> None:
    scorer = upstream.scorer_path(pin_to_fake)
    scorer.write_text(SCORER_SOURCE + "\n# one added comment\n", encoding="utf-8")
    with pytest.raises(PinMismatch, match="unmodified"):
        upstream.verify_scorer(pin_to_fake)


def test_scorer_digest_accepts_the_pinned_bytes(pin_to_fake: pathlib.Path) -> None:
    assert upstream.verify_scorer(pin_to_fake) == upstream.SCORER_SHA256


def test_corpus_digest_notices_one_changed_trace(pin_to_fake: pathlib.Path) -> None:
    victim = pin_to_fake / upstream.CORPUS_DIRS[0] / "alpha0.json"
    victim.write_text(json.dumps({"trace_id": "alpha0", "spans": [{"span_id": "x"}]}))
    with pytest.raises(PinMismatch, match="rolls up to"):
        upstream.verify_corpus(pin_to_fake)


def test_corpus_digest_does_not_depend_on_readdir_order(pin_to_fake: pathlib.Path) -> None:
    """Without the sort in corpus_manifest this passes on one machine and fails on the other.

    macOS returns directory entries roughly in creation order and the
    ubuntu-latest runner does not, so a manifest built straight off rglob would
    have produced a digest that only reproduces where it was recorded. Reversing
    rglob is the cheapest way to make that difference show up here rather than
    in CI.
    """
    straight = upstream.corpus_digest(pin_to_fake)
    unsorted_rglob = pathlib.Path.rglob

    def backwards(self: pathlib.Path, pattern: str):
        return reversed(list(unsorted_rglob(self, pattern)))

    original = pathlib.Path.rglob
    pathlib.Path.rglob = backwards  # type: ignore[method-assign]
    try:
        assert upstream.corpus_digest(pin_to_fake) == straight
    finally:
        pathlib.Path.rglob = original  # type: ignore[method-assign]


def test_taxonomy_comes_out_of_the_pinned_source(pin_to_fake: pathlib.Path) -> None:
    assert upstream.taxonomy(pin_to_fake) == ("Alpha", "Beta Errors", "Gamma")


def test_taxonomy_refuses_a_scorer_without_all_categories(
    fake_clone: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scorer = upstream.scorer_path(fake_clone)
    scorer.write_text("def main(a, b):\n    return []\n", encoding="utf-8")
    monkeypatch.setattr(upstream, "SCORER_SHA256", upstream.sha256_of(scorer))
    with pytest.raises(PinMismatch, match="all_categories"):
        upstream.taxonomy(fake_clone)


def test_missing_clone_says_what_to_run(tmp_path: pathlib.Path) -> None:
    with pytest.raises(MissingClone, match="trailaudit fetch"):
        upstream.verify_scorer(tmp_path / "nothing-here")


def test_locally_modified_names_the_file_git_says_changed(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (
        ["init", "--quiet"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "test"],
    ):
        subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True)
    (repo / "kept.json").write_text("{}\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--quiet", "-m", "seed"], check=True, capture_output=True
    )
    assert upstream.locally_modified(repo) == []

    (repo / "kept.json").write_text('{"edited": true}\n')
    assert upstream.locally_modified(repo) == ["kept.json"]
