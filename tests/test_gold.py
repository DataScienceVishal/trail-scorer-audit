"""P3 and P4 against hand-built annotation files.

The fixtures and the taxonomy below are made up. What is under test is how this
repository counts parse failures and vocabulary drift, not what TRAIL's
normaliser does with either, so a small invented taxonomy exercises the same
code path as the real 21 labels and the suite stays offline.
"""

from __future__ import annotations

import pathlib

import pytest

from stand_ins import TAXONOMY, strip_only
from trailaudit import gold
from trailaudit.upstream import MissingClone


@pytest.fixture
def read(annotations: pathlib.Path):
    return gold.read_directory(annotations, "fixture")


def test_p3_one_fixture_does_not_parse_and_the_rest_do(read) -> None:
    loaded, refused = read
    assert sorted(one.trace for one in loaded) == ["clean", "drifted"]
    assert [one.trace for one in refused] == ["trailing_comma"]


def test_p3_the_failure_points_at_the_comma_not_at_the_decoder(read) -> None:
    """The published position has to be a fact about the file.

    CPython 3.12 blames line 9 column 5 of this fixture and 3.13 blames line 8
    column 10 of the same bytes, so the decoder's own position would put a
    different number in the README depending on who ran it.
    """
    _, refused = read
    (failure,) = refused
    assert (failure.line, failure.column, failure.character) == (8, 10, ",")
    assert failure.decoder


def test_culprit_agrees_across_both_decoder_conventions() -> None:
    text = '{\n    "errors": [\n        {"a": 1},\n    ]\n}\n'
    comma = text.index("},") + 1
    bracket = text.index("]")
    assert gold.culprit(text, comma) == gold.culprit(text, bracket)
    assert gold.culprit(text, comma) == (3, 17, ",")


def test_culprit_falls_back_to_the_decoder_position_when_no_comma_is_near() -> None:
    text = '{\n    "errors": nope\n}\n'
    assert gold.culprit(text, text.index("nope")) == (2, 15, "n")


def test_p4_names_every_spelling_that_is_not_a_label(read) -> None:
    loaded, _ = read
    counted = gold.vocabulary(loaded)
    assert gold.off_taxonomy(counted, TAXONOMY) == [
        " Widget Errors",
        "Flangee Misuze",
        "Gasket Handling Failure",
        "Sprocket-Only",
    ]


def test_p4_counts_errors_not_distinct_spellings(read) -> None:
    loaded, _ = read
    counted = gold.vocabulary(loaded)
    assert counted["Widget Errors"] == 2
    assert sum(counted.values()) == 7


def test_dropped_is_what_the_normaliser_leaves_outside_the_taxonomy(read) -> None:
    loaded, _ = read
    counted = gold.vocabulary(loaded)
    assert gold.dropped(counted, TAXONOMY, strip_only) == {
        "Flangee Misuze": 1,
        "Gasket Handling Failure": 1,
        "Sprocket-Only": 1,
    }


def test_a_rescued_spelling_is_not_dropped_and_lands_on_its_label(read) -> None:
    """The leading-space case, which the real gold has too.

    ` Incorrect Problem Identification` is one of TRAIL's gold strings and the
    normaliser strips it back onto a real label, so drift and loss are different
    counts and this repository must not report one as the other.
    """
    loaded, _ = read
    counted = gold.vocabulary(loaded)
    after = gold.normalised_counts(counted, strip_only)
    assert " Widget Errors" not in gold.dropped(counted, TAXONOMY, strip_only)
    assert after["Widget Errors"] == 3


def test_reading_a_directory_that_is_not_there_says_what_to_run(tmp_path: pathlib.Path) -> None:
    with pytest.raises(MissingClone, match="trailaudit fetch"):
        gold.read_directory(tmp_path / "nope", "fixture")
