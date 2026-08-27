"""What each predictor emits, and what it is not allowed to have looked at.

The span identifiers and the taxonomy here are invented. Nothing from TRAIL is
needed to test a cross product, and the real 21 labels live in the pinned clone
that CI does not have.
"""

from __future__ import annotations

import pytest

from stand_ins import TAXONOMY
from trailaudit import predictors
from trailaudit.predictors import Case

SPANS = ("aaaa000000000001", "aaaa000000000002", "aaaa000000000003")

GOLD = (
    {"location": "aaaa000000000002", "category": "Widget Errors"},
    {"location": "aaaa000000000003", "category": "Flange Misuse"},
    {"location": "aaaa000000000002", "category": "Sprocket-only"},
)

NONSENSE = (
    {"location": "not a span id at all", "category": "Bogus Category"},
    {"location": "another one", "category": "Also Bogus"},
)


@pytest.fixture
def case() -> Case:
    return Case(span_ids=SPANS, taxonomy=TAXONOMY, gold=GOLD)


@pytest.mark.parametrize(
    "predictor", [one for one in predictors.PREDICTORS if not one.knows_gold], ids=lambda p: p.name
)
def test_a_gold_blind_predictor_gives_the_same_answer_against_nonsense_gold(
    predictor: predictors.Predictor, case: Case
) -> None:
    """The claim in the spec, enforced rather than asserted in a docstring.

    "Information used that a real judge does not have: none." A signature cannot
    say that, because every predictor takes the same Case. Replacing the answer
    key with two made-up errors and requiring byte-identical output can.
    """
    lied_to = Case(span_ids=case.span_ids, taxonomy=case.taxonomy, gold=NONSENSE)
    assert predictor.emit(case) == predictor.emit(lied_to)


@pytest.mark.parametrize(
    "predictor", [one for one in predictors.PREDICTORS if one.knows_gold], ids=lambda p: p.name
)
def test_an_oracle_predictor_moves_when_the_gold_moves(
    predictor: predictors.Predictor, case: Case
) -> None:
    """The other half, so knows_gold is a fact about the code rather than a label.

    A predictor marked as reading the gold that turned out not to would be a
    ceiling row measuring the same thing as the floor rows, and the table would
    still look sensible.
    """
    lied_to = Case(span_ids=case.span_ids, taxonomy=case.taxonomy, gold=NONSENSE)
    assert predictor.emit(case) != predictor.emit(lied_to)


def test_the_maximal_predictor_is_the_full_cross_product(case: Case) -> None:
    emitted = predictors.all_spans_all_categories(case)
    assert len(emitted) == len(SPANS) * len(TAXONOMY)
    assert {one["location"] for one in emitted} == set(SPANS)
    assert {one["category"] for one in emitted} == set(TAXONOMY)


def test_a_span_listed_twice_is_predicted_once() -> None:
    """SWE Bench 72822db6e120878d916b515c2501246b repeats b14646a5fcac02fd.

    A duplicate cannot change a score, because line 53 intersects sets. It can
    change the volume ratio, which is the number published beside the score, so
    it is dropped and the ratio comes out lower.
    """
    twice = Case(span_ids=(SPANS[0], SPANS[1], SPANS[0]), taxonomy=TAXONOMY, gold=())
    assert len(predictors.all_spans_all_categories(twice)) == 2 * len(TAXONOMY)
    assert len(predictors.every_span_once(twice)) == 2


def test_every_span_once_emits_one_error_per_span_under_one_label(case: Case) -> None:
    emitted = predictors.every_span_once(case)
    assert [one["location"] for one in emitted] == list(SPANS)
    assert {one["category"] for one in emitted} == {TAXONOMY[0]}


def test_gold_spans_reads_the_locations_and_ignores_the_gold_categories(case: Case) -> None:
    emitted = predictors.gold_spans_all_categories(case)
    assert {one["location"] for one in emitted} == {"aaaa000000000002", "aaaa000000000003"}
    assert len(emitted) == 2 * len(TAXONOMY)
    assert "Widget Errors" in {one["category"] for one in emitted}


def test_gold_exact_copies_the_answer_key_without_aliasing_it(case: Case) -> None:
    emitted = predictors.gold_exact(case)
    assert emitted == list(GOLD)
    emitted[0]["category"] = "edited"
    assert GOLD[0]["category"] == "Widget Errors"


def test_mispaired_keeps_every_location_and_every_category_but_not_the_pairing(case: Case) -> None:
    emitted = predictors.gold_mispaired(case)
    assert len(emitted) == len(GOLD)
    assert [one["location"] for one in emitted] == [one["location"] for one in GOLD]
    assert sorted(one["category"] for one in emitted) == sorted(one["category"] for one in GOLD)
    assert emitted != list(GOLD)


def test_mispaired_cannot_move_a_trace_with_one_gold_error() -> None:
    """Where this row's residual joint accuracy comes from, stated as a test.

    Rotating a one-element list is the identity, so a trace annotated with a
    single error scores 1.000 under a predictor whose entire purpose is to get
    the pairing wrong. The report has to attribute the residual to that rather
    than let it read as noise.
    """
    single = Case(span_ids=SPANS, taxonomy=TAXONOMY, gold=(GOLD[0],))
    assert predictors.gold_mispaired(single) == [dict(GOLD[0])]


def test_the_silent_predictor_emits_nothing(case: Case) -> None:
    assert predictors.silent(case) == []


def test_the_emitted_document_carries_no_scores_key(case: Case) -> None:
    """`scores` would switch on the scorer's Pearson block at line 173.

    That block correlates a human overall score against a generated one. This
    audit measures neither, and a stray key would put correlation figures in the
    run output that no property was written about.
    """
    assert predictors.document(predictors.gold_exact(case)) == {"errors": list(GOLD)}


def test_by_name_lists_the_alternatives_when_it_misses() -> None:
    assert predictors.by_name("silent").emit is predictors.silent
    with pytest.raises(KeyError, match="all-spans-all-categories"):
        predictors.by_name("maximal")


def test_every_predictor_name_is_distinct_and_shell_safe() -> None:
    """The names end up as `--only` values and as directory names under the workspace."""
    names = [one.name for one in predictors.PREDICTORS]
    assert len(set(names)) == len(names)
    assert all(name.replace("-", "").isalnum() for name in names)
