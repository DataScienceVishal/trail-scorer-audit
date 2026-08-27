"""The substring enumeration and P6, against an invented normaliser rather than TRAIL's.

Nothing here needs the 186 MB or the real 21 labels. What is under test is this
repository's half: which strings get enumerated, how they are grouped, which of
the normaliser's two loops caught a spelling, and whether the finding says HELD
when a normaliser genuinely does not launder anything. The real figures are in
tests/test_pinned_clone.py, which reruns against the pinned scorer and skips
where the clone is absent.
"""

from __future__ import annotations

from collections import Counter

from stand_ins import TAXONOMY, first_prefix
from trailaudit import normaliser
from trailaudit.datacheck import HELD, VIOLATED
from trailaudit.normaliser import EXACT, FALLBACK, NEITHER


def flat(rendered: str) -> str:
    return " ".join(rendered.split())


def test_substrings_are_enumerated_in_the_form_line_26_compares() -> None:
    """Spaces gone and lowercased, because `category_no_spaces` is all the fallback sees."""
    assert normaliser.substrings("Ab C") == {"a", "b", "c", "ab", "bc", "abc"}


def test_the_empty_string_is_not_a_candidate() -> None:
    """It cannot arrive as a substring, only as whitespace that line 16 strips.

    Line 14's guard tests the argument before the strip, so `" "` gets past it
    and reaches the fallback as "". That path is reported separately, and letting
    "" into the enumeration would have put it under whichever label came first
    with no explanation of how a judge would ever emit it.
    """
    assert "" not in normaliser.candidates(TAXONOMY)


def test_candidates_come_out_shortest_first_and_deduplicated() -> None:
    shared = ("Widget Errors", "Widget Failures")
    every = normaliser.candidates(shared)
    assert len(every) == len(set(every))
    assert [len(one) for one in every] == sorted(len(one) for one in every)
    assert "widget" in every


def test_accepts_asks_the_normaliser_rather_than_matching_the_string_here() -> None:
    assert normaliser.accepts(first_prefix, "widget", "Widget Errors")
    assert not normaliser.accepts(first_prefix, "errors", "Widget Errors")


def test_which_loop_separates_an_exact_match_from_a_looser_one() -> None:
    """The decoy trick, on a normaliser whose looser loop is not TRAIL's."""
    assert normaliser.which_loop(first_prefix, "widget errors", "Widget Errors") == EXACT
    assert normaliser.which_loop(first_prefix, "widget", "Widget Errors") == FALLBACK
    assert normaliser.which_loop(first_prefix, "sprocket", "Widget Errors") == NEITHER


def test_a_label_reached_only_through_an_earlier_one_is_reported_as_unreachable() -> None:
    """`Widget Failures` sits behind `Widget Errors`, so `widget` never gets to it.

    The row has to say so rather than be left out of the table. A label missing
    from the shortest-string list reads as an oversight; a label printed with
    nothing under it is the finding that the fallback resolves ties by position.
    """
    behind = ("Widget Errors", "Widget Failures")
    reaches = normaliser.probe(behind, first_prefix)
    shortest = {one.label: one for one in normaliser.shortest_reaching(reaches, behind)}
    assert shortest["Widget Errors"].strings == ("w",)
    assert shortest["Widget Failures"].reaching > 0
    assert "widget" not in shortest["Widget Failures"].strings


def test_the_per_label_counts_add_up_to_the_candidates_that_reached_a_label() -> None:
    """Under a prefix rule most substrings reach nothing, and those are not counted twice.

    TRAIL's substring rule has no such candidates: every substring of a label
    reaches at least that label. Holding the accounting to the weaker invariant
    means the same code is right for both.
    """
    reaches = normaliser.probe(TAXONOMY, first_prefix)
    shortest = normaliser.shortest_reaching(reaches, TAXONOMY)
    landed = [one for one in reaches if one.lands in set(TAXONOMY)]
    assert sum(one.reaching for one in shortest) == len(landed)
    assert len(landed) < len(reaches)


def test_drift_records_which_loop_caught_each_spelling_and_what_contains_it() -> None:
    counted = Counter({"Widget": 4, "Widget errors": 1, "Widget Errors Everywhere": 2})
    drifted = {one.spelling: one for one in normaliser.drift(counted, TAXONOMY, first_prefix)}

    assert drifted["Widget"].loop == FALLBACK
    assert drifted["Widget"].lands == "Widget Errors"
    assert drifted["Widget errors"].loop == EXACT
    assert drifted["Widget Errors Everywhere"].loop == NEITHER
    assert drifted["Widget Errors Everywhere"].errors == 2


def test_a_spelling_that_reaches_nothing_records_the_labels_sitting_inside_it() -> None:
    """The reverse containment, measured by swapping the same two arguments.

    `Widget Errors Everywhere` is a label plus a suffix. It reaches no label
    because the containment runs the other way, and that is the mechanism behind
    three of the four gold errors TRAIL's normaliser drops.
    """
    counted = Counter({"Widget Errors Everywhere": 1, "Wodget": 1})
    drifted = {one.spelling: one for one in normaliser.drift(counted, TAXONOMY, first_prefix)}
    assert drifted["Widget Errors Everywhere"].would_contain == ("Widget Errors",)
    assert drifted["Wodget"].would_contain == ()


def test_p6_is_violated_when_a_short_string_reaches_a_label() -> None:
    reaches = normaliser.probe(TAXONOMY, first_prefix)
    shortest = normaliser.shortest_reaching(reaches, TAXONOMY)
    finding = normaliser.p6(shortest, TAXONOMY, ())
    assert finding.verdict == VIOLATED
    assert "reached by a string of" in flat(finding.render())


def test_p6_holds_against_a_normaliser_that_launders_nothing() -> None:
    """The branch TRAIL's own normaliser never takes.

    `strip_only` matches on the whole string, so no substring of a label reaches
    it, and P6 comes back held. Without this the report could have been wired to
    return VIOLATED unconditionally and every run against the real data would
    still have looked right.
    """
    only_whole = normaliser.probe(TAXONOMY, lambda spelling, labels: spelling.strip())
    shortest = normaliser.shortest_reaching(only_whole, TAXONOMY)
    assert normaliser.p6(shortest, TAXONOMY, ()).verdict == HELD


def test_the_verdict_stays_in_its_column_when_the_claim_overruns_it() -> None:
    """P6's claim is the longest of the nine and it does not fit the fixed column."""
    reaches = normaliser.probe(TAXONOMY, first_prefix)
    shortest = normaliser.shortest_reaching(reaches, TAXONOMY)
    head = normaliser.p6(shortest, TAXONOMY, ()).render().splitlines()[0]
    assert head.endswith("  VIOLATED")


def test_plural_agrees_with_its_count() -> None:
    assert normaliser.plural(1, "spelling") == "1 spelling"
    assert normaliser.plural(3, "spelling") == "3 spellings"


def test_the_drift_table_names_the_spelling_the_count_and_the_loop() -> None:
    counted = Counter({"Widget": 4})
    rows = normaliser.drift_table(normaliser.drift(counted, TAXONOMY, first_prefix))
    assert "'Widget'" in rows[1]
    assert "fallback" in rows[1]
    assert "Widget Errors" in rows[1]
