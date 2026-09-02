"""results/datacheck.json, and whether it agrees with the artifacts written beside it.

P3, P4 and P9 were measured by `data-check` and printed. This file is where they
were finally written down, so the README can quote them without the 186 MB, and
the checks here are the ones that do not need it either: that the counts inside
the file add up, that the Table 5 column it carries is the one transcribed in
paper.py, and that the two commands which both counted the gold got the same
answer.

tests/test_pinned_clone.py reruns the measurement itself and skips wherever the
clone is absent.
"""

from __future__ import annotations

import pathlib

import pytest

from trailaudit import adversarial, datacheck, pairing, paper, upstream


@pytest.fixture(scope="module")
def committed(repo_root: pathlib.Path) -> dict:
    return datacheck.load(repo_root / datacheck.COMMITTED)


def test_the_file_count_is_the_two_it_splits_into(committed: dict) -> None:
    counted = committed["gold_files"]
    assert counted["parsed"] + len(committed["unreadable"]) == counted["on_disk"]
    assert counted["on_disk"] == paper.ABSTRACT_TRACES


def test_the_unreadable_file_is_located_by_character_and_not_by_decoder(committed: dict) -> None:
    """CPython 3.12 and 3.13 name different positions for these bytes.

    gold.culprit() collapses the two onto the comma itself, and the artifact
    stores that. Storing the decoder's own message would make this file fail its
    own rerun on the other interpreter, which is the shape of bug that put a
    wrong line number in a README once already.
    """
    (failure,) = committed["unreadable"]
    assert failure["character"] == ","
    assert (failure["line"], failure["column"]) == (38, 10)
    assert "Expecting" not in str(failure)


def test_the_vocabulary_counts_nest_the_way_they_claim_to(committed: dict) -> None:
    counted = committed["vocabulary"]
    assert counted["off_taxonomy"] <= counted["spellings"]
    assert counted["errors_off_taxonomy"] <= counted["errors"]
    assert counted["dropped_spellings"] <= counted["off_taxonomy"]
    assert counted["dropped_errors"] <= counted["errors_off_taxonomy"]


def test_the_error_total_is_the_two_splits_added_up(committed: dict) -> None:
    per_split = sum(one["here"]["errors"] for one in committed["splits"].values())
    assert per_split == committed["vocabulary"]["errors"]


def test_the_published_column_is_the_transcribed_one(committed: dict) -> None:
    for split, one in committed["splits"].items():
        published = paper.published_for(split)
        assert one["paper"] == {row: getattr(published, row) for row in paper.ROWS}


def test_p9s_magnitude_is_the_number_of_cells_that_actually_disagree(committed: dict) -> None:
    """The one figure in the conditions table that is a count of other figures.

    Recomputed here from the same file rather than trusted, because a magnitude
    that drifts from the table under it is worse than no magnitude: the table is
    long enough that nobody counts it by hand.
    """
    measured = {split: one["here"] for split, one in committed["splits"].items()}
    comparable, disagreeing = datacheck.cells(measured)
    assert (comparable, len(disagreeing)) == (10, 8)
    assert f"{len(disagreeing)} of the {comparable}" in committed["properties"]["P9"]["magnitude"]


def test_the_corpus_block_is_what_fetch_verifies(committed: dict) -> None:
    assert committed["corpus"]["sha256"] == upstream.CORPUS_SHA256
    assert committed["corpus"]["files"] > paper.ABSTRACT_TRACES
    assert committed["corpus"]["bytes"] > 100_000_000


def test_the_three_commands_that_counted_the_gold_agree_with_each_other(
    repo_root: pathlib.Path, committed: dict
) -> None:
    """data-check, adversarial and pairing each counted the same gold separately.

    Three artifacts written by three runs, and one gold corpus underneath all of
    them. If they disagree, one of them is stale and the README is about to
    quote whichever was rendered last.
    """
    scored = adversarial.load(repo_root / adversarial.COMMITTED)["splits"]
    assert sum(one["gold_files"] for one in scored.values()) == committed["gold_files"]["on_disk"]
    assert (
        sum(one["gold_files_scored"] for one in scored.values())
        == committed["gold_files"]["parsed"]
    )
    assert sum(one["gold_errors"] for one in scored.values()) == committed["vocabulary"]["errors"]

    latent = pairing.load(repo_root / pairing.COMMITTED)["on_the_real_gold"]
    assert latent["gold_errors"] == committed["vocabulary"]["errors"]
