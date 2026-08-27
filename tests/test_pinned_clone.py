"""What can only be checked with the real trail-benchmark on disk.

These skip in CI and everywhere else that has not run `trailaudit fetch`. They
are the other half of the offline suite rather than a replacement for it: the
committed digests, the committed index and the hand-built fixtures are checked
without them, and these say that those committed things describe the real
dataset.
"""

from __future__ import annotations

import pathlib
from collections import Counter

import pytest

from trailaudit import adversarial, artifacts, gold, normaliser, spans, upstream
from trailaudit.datacheck import VIOLATED

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


def test_p1_and_p2_reproduce_from_a_fresh_run(clone: pathlib.Path, repo_root: pathlib.Path) -> None:
    """The whole of slice 2, rerun against the real scorer and diffed leaf by leaf.

    Every figure the README quotes comes out of results/adversarial.json, and
    nothing offline can tell whether that file describes a real run. This is what
    can, and it is the reason `trailaudit adversarial --check` exists as well.
    """
    index = spans.load(repo_root / spans.COMMITTED)
    runs = adversarial.run(clone, index)
    committed = adversarial.load(repo_root / adversarial.COMMITTED)
    assert artifacts.differences(committed, adversarial.artifact(runs)) == []

    assert adversarial.p1(runs).verdict == VIOLATED
    assert adversarial.p2(runs).verdict == VIOLATED


def test_the_maximal_predictor_reads_no_span_contents_and_still_beats_every_model(
    clone: pathlib.Path, repo_root: pathlib.Path
) -> None:
    """The claim, measured rather than quoted, against Table 1 on page 7.

    Gemini-2.5-Pro is the best of eight on all four columns. The predictor here
    is a for loop over the committed span index crossed with the taxonomy, and
    the numbers it beats them by are the ones the README leads with.
    """
    index = spans.load(repo_root / spans.COMMITTED)
    runs = {one.split: one for one in adversarial.run(clone, index)}
    for split, joint, location in (("GAIA", 0.183, 0.546), ("SWE Bench", 0.050, 0.238)):
        mine = runs[split].scored[adversarial.HEADLINE.name]
        assert mine.joint_accuracy > joint
        assert mine.location_accuracy > location
        assert mine.volume_ratio > 80


@pytest.fixture(scope="module")
def study(clone: pathlib.Path, repo_root: pathlib.Path) -> normaliser.Study:
    return normaliser.study(clone, spans.load(repo_root / spans.COMMITTED))


def test_p6_every_one_of_the_21_labels_is_reachable_from_two_characters(
    study: normaliser.Study,
) -> None:
    """The magnitude the spec left open, and it is not close.

    The shortest label squashes to 12 characters. Nothing in the taxonomy needs
    more than 2 to be reached, because line 26 asks whether the judge's string is
    inside the label and a two-letter string is inside a great many of them.
    """
    reached = [one for one in study.shortest if one.strings]
    assert len(reached) == len(study.taxonomy) == 21
    assert max(one.length for one in reached) == 2
    assert min(len(normaliser.squash(label)) for label in study.taxonomy) == 12


def test_the_three_strings_the_spec_quotes_land_where_it_says(study: normaliser.Study) -> None:
    labels = list(study.taxonomy)
    assert study.normalise("error", labels) == "Tool Selection Errors"
    assert study.normalise("resource", labels) == "Resource Not Found"
    assert study.normalise("tool", labels) == "Tool-related"


def test_a_category_of_one_space_reaches_the_first_label(study: normaliser.Study) -> None:
    """Line 14 tests the argument, line 16 strips it, and "" is inside everything.

    So a judge that emits a single space is credited with whichever label the
    scorer's list happens to start with. Nothing else in this audit needs the
    empty-string guard to be wrong; this is only what it costs that it is.
    """
    assert study.normalise(" ", list(study.taxonomy)) == study.taxonomy[0] == "Language-only"


def test_the_eleven_drifted_gold_spellings_split_five_three_and_three(
    study: normaliser.Study,
) -> None:
    """Which loop caught each one, which is what the P4 drift table could not say.

    Five match a label exactly once case and spacing are folded away. Three need
    the fallback. Three reach nothing, and two of those are `Task Orchestration`
    plus a suffix, so the same line would catch them if the containment ran the
    other way.
    """
    by_loop = Counter(one.loop for one in study.drifted)
    assert by_loop == {normaliser.EXACT: 5, normaliser.FALLBACK: 3, normaliser.NEITHER: 3}
    assert sum(one.errors for one in study.drifted) == 19

    reversible = [one for one in study.drifted if one.loop == normaliser.NEITHER]
    assert [one.would_contain for one in reversible] == [
        (),
        ("Task Orchestration",),
        ("Task Orchestration",),
    ]


def test_no_taxonomy_label_sits_inside_another_one(study: normaliser.Study) -> None:
    """The precondition behind reading two matches as decided by list position.

    A string that matches label A exactly and label B loosely is not order
    dependent, because the exact loop at line 21 runs the whole list first. That
    can only happen if A's squashed form is inside B's, and none of the 21 is.
    """
    squashed = [normaliser.squash(label) for label in study.taxonomy]
    nested = [
        (inner, outer)
        for inner in squashed
        for outer in squashed
        if inner != outer and inner in outer
    ]
    assert nested == []


def test_p5_the_taxonomy_order_decides_237_strings_and_no_gold_spelling(
    study: normaliser.Study,
) -> None:
    """P5's magnitude, and the reason it does not reach a published number.

    237 of the 3,205 enumerated strings are settled by list position, and 'e' is
    accepted by all 21 labels. None of the 31 gold spellings is among them, so
    shuffling the taxonomy leaves all 24 figures of the slice 2 measurement
    exactly where they were.
    """
    ambiguous = [one for one in study.reaches if one.order_dependent]
    assert len(ambiguous) == 237
    assert max(len(one.matched) for one in ambiguous) == len(study.taxonomy) == 21
    assert study.ambiguous_gold() == []
    assert [one for one in study.rescored if one.moved] == []
    assert len(study.rescored) == 12


def test_p5_and_p6_reproduce_from_a_fresh_run(
    study: normaliser.Study, repo_root: pathlib.Path
) -> None:
    committed = normaliser.load(repo_root / normaliser.COMMITTED)
    assert artifacts.differences(committed, normaliser.artifact(study)) == []
    _, violated = normaliser.report(study)
    assert violated
    assert normaliser.p5(study).verdict == VIOLATED


def test_the_shuffled_rescore_reproduces_what_main_returned_under_the_pinned_order(
    study: normaliser.Study, repo_root: pathlib.Path
) -> None:
    """The control that makes a null result mean something.

    rescore() averages calculate_metrics itself, because main() takes the
    taxonomy from a literal it owns. If that averaging were wrong the shuffled
    column would be meaningless and would still print zeros. Every pinned figure
    here has to equal the one results/adversarial.json carries from main().
    """
    published = adversarial.load(repo_root / adversarial.COMMITTED)["splits"]
    for one in study.rescored:
        row = published[one.split]["predictors"][one.predictor]
        assert one.pinned == (row["joint_accuracy"], row["location_accuracy"]), one.predictor
