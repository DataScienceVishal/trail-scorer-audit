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


def rescored(
    *rows: tuple[str, str, tuple[float, float], tuple[float, float]],
) -> tuple[normaliser.Rescored, ...]:
    """Rows as (split, predictor, pinned pair, shuffled pair), joint then location.

    Both metrics are given separately because P5 counts figures rather than
    rows, and a helper that set the two to the same number could only ever build
    a row where both moved or neither did.
    """
    return tuple(
        normaliser.Rescored(split, name, pinned=pinned, reordered=reordered)
        for split, name, pinned, reordered in rows
    )


def hand_built(reaches, drifted=(), vocabulary=None, rows=()) -> normaliser.Study:
    return normaliser.Study(
        taxonomy=TAXONOMY,
        normalise=first_prefix,
        reaches=reaches,
        shortest=normaliser.shortest_reaching(reaches, TAXONOMY),
        vocabulary=Counter(vocabulary or {}),
        drifted=drifted,
        rescored=rows,
    )


def test_a_string_two_labels_will_take_is_marked_order_dependent() -> None:
    reaches = {one.candidate: one for one in normaliser.probe(TAXONOMY, first_prefix)}
    assert reaches["widget"].matched == ("Widget Errors", "Widget Failures")
    assert reaches["widget"].order_dependent
    assert not reaches["sprocket"].order_dependent


def test_the_shuffle_is_a_permutation_and_the_seed_decides_it() -> None:
    once = normaliser.shuffled(TAXONOMY)
    assert sorted(once) == sorted(TAXONOMY)
    assert once == normaliser.shuffled(TAXONOMY)
    assert once != normaliser.shuffled(TAXONOMY, seed=normaliser.SEED + 1)


def test_p5_is_violated_by_a_string_that_two_labels_will_take() -> None:
    """Six strings here, the prefixes of `widget` that both Widget labels accept."""
    finding = normaliser.p5(hand_built(normaliser.probe(TAXONOMY, first_prefix)))
    assert finding.verdict == VIOLATED
    rendered = flat(finding.render())
    assert "6 of the 502 enumerated strings match more than one label" in rendered
    assert "'w' matches all 2 and lands on 'Widget Errors'" in rendered


def test_p5_holds_against_a_normaliser_nothing_is_ambiguous_under() -> None:
    """`strip_only` matches whole strings, so no candidate reaches two labels.

    Without this the finding could have been wired to VIOLATED unconditionally,
    and the 237 would look like a measurement rather than a constant.
    """
    only_whole = normaliser.probe(TAXONOMY, lambda spelling, labels: spelling.strip())
    assert normaliser.p5(hand_built(only_whole)).verdict == HELD


def test_p5_counts_the_figures_that_moved_rather_than_assuming_none_did() -> None:
    """The real run moves nothing, so the branch that reports movement never fires there.

    A P5 that printed "moves 0 of the 24" from a hard-coded zero would look
    identical on the real data and would be wrong the moment a gold spelling
    drifted onto an ambiguous string. Two rows here, one of which moves its
    location figure and not its joint one, so the answer is 1 of 4 rather than
    the 2 of 4 a row-counting numerator would give.
    """
    done = hand_built(
        normaliser.probe(TAXONOMY, first_prefix),
        rows=rescored(
            ("GAIA", "silent", (0.5, 0.5), (0.5, 0.5)),
            ("GAIA", "gold-exact", (0.9, 0.4), (0.9, 0.6)),
        ),
    )
    rendered = flat(normaliser.p5(done).render())
    assert "moves 1 of the 4 figures" in rendered


def test_a_row_that_moves_both_metrics_counts_as_two_of_the_figures() -> None:
    """The numerator counted rows and the denominator counted figures.

    Both are zero on the real data, so the published ratio understated a
    violation by up to 2x with nothing in the run to show it.
    """
    done = hand_built(
        normaliser.probe(TAXONOMY, first_prefix),
        rows=rescored(("GAIA", "gold-exact", (0.9, 0.4), (0.8, 0.6))),
    )
    assert "moves 2 of the 2 figures" in flat(normaliser.p5(done).render())


def test_a_rescored_row_names_which_of_its_two_figures_moved() -> None:
    (still,) = rescored(("GAIA", "silent", (0.5, 0.5), (0.5, 0.5)))
    assert still.figures_that_moved == ()
    (joint_only,) = rescored(("GAIA", "silent", (0.5, 0.5), (0.6, 0.5)))
    assert joint_only.figures_that_moved == ("joint",)
    (both,) = rescored(("GAIA", "silent", (0.5, 0.5), (0.6, 0.6)))
    assert both.figures_that_moved == ("joint", "location")


def test_the_rescored_table_puts_the_two_orders_side_by_side() -> None:
    rows = normaliser.rescored_table(rescored(("GAIA", "silent", (0.25, 0.25), (0.75, 0.75))))
    assert "0.250000  0.750000" in rows[1]
