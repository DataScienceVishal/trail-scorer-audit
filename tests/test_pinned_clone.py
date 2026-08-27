"""What can only be checked with the real trail-benchmark on disk.

These skip in CI and everywhere else that has not run `trailaudit fetch`. They
are the other half of the offline suite rather than a replacement for it: the
committed digests, the committed index and the hand-built fixtures are checked
without them, and these say that those committed things describe the real
dataset.
"""

from __future__ import annotations

import pathlib

import pytest

from trailaudit import gold, spans, upstream

pytestmark = pytest.mark.upstream


def test_the_pinned_digests_are_the_real_ones(clone: pathlib.Path) -> None:
    assert upstream.head_commit(clone) == upstream.PINNED_COMMIT
    assert upstream.verify_scorer(clone) == upstream.SCORER_SHA256
    assert upstream.verify_corpus(clone) == upstream.CORPUS_SHA256


def test_the_committed_index_matches_a_fresh_walk(
    clone: pathlib.Path, repo_root: pathlib.Path
) -> None:
    committed = spans.load(repo_root / spans.COMMITTED)
    assert spans.differences(committed, spans.build(clone)) == []


def test_the_taxonomy_read_out_of_the_scorer_has_twenty_one_labels(clone: pathlib.Path) -> None:
    labels = upstream.taxonomy(clone)
    assert len(labels) == 21
    assert len(set(labels)) == 21


def test_importing_the_scorer_does_not_parse_sys_argv(
    clone: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The risk the spec named, closed rather than assumed.

    calculate_scores.py is a script with an argparse block at the bottom. If
    that block ran on import, this would exit rather than return a module, and
    the audit would have had to drive the scorer as a subprocess instead.
    """
    monkeypatch.setattr("sys.argv", ["pytest", "--results_dir", "/does/not/exist"])
    module = upstream.load_scorer(clone)
    assert callable(module.calculate_metrics)
    assert callable(module.normalize_category)


def test_p3_exactly_one_gold_file_does_not_parse(clone: pathlib.Path) -> None:
    """The finding this slice ends on, pinned so nobody has to retype it.

    841 annotated errors are published over 148 traces. The scorer loads 147 of
    those files and prints a message about the other one, so every figure on the
    leaderboard is an average over 147 and covers 836 errors.
    """
    loaded, refused = gold.read_all(clone)
    assert len(loaded) == 147
    (failure,) = refused
    assert failure.trace == "a96c6811716c0473b86a23321db79c34"
    assert failure.split == "GAIA"
    assert (failure.line, failure.column, failure.character) == (38, 10, ",")
    assert sum(len(one.categories) for one in loaded) == 836


def test_p4_the_gold_vocabulary_has_drifted_off_the_taxonomy(clone: pathlib.Path) -> None:
    loaded, _ = gold.read_all(clone)
    counted = gold.vocabulary(loaded)
    labels = upstream.taxonomy(clone)
    assert len(counted) == 31
    assert len(gold.off_taxonomy(counted, labels)) == 11
    assert " Incorrect Problem Identification" in counted


def test_the_normaliser_drops_four_gold_errors(clone: pathlib.Path) -> None:
    loaded, _ = gold.read_all(clone)
    labels = upstream.taxonomy(clone)
    normalise = gold.binder(upstream.load_scorer(clone).normalize_category, labels)
    lost = gold.dropped(gold.vocabulary(loaded), labels, normalise)
    assert lost == {
        "Instruction non complience": 1,
        "Task Orchestration Error": 1,
        "Task Orchestration Errors": 2,
    }
