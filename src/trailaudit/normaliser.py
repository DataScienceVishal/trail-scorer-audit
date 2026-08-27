"""Every substring of every taxonomy label, put back through TRAIL's own normaliser.

`normalize_category` at lines 12 to 30 of calculate_scores.py has two loops. The
first wants an exact match once both sides are lowercased and their spaces
removed. The second is the fallback, and it is the one this module is about:

    for std_cat in all_categories:
        if category_no_spaces in std_cat.lower().replace(" ", ""):
            return std_cat

The containment runs one way only. The judge's string has to sit inside the
label, so a string vaguer than a label is promoted to it while a string more
specific than a label falls through unmatched. Both directions are already in
TRAIL's own gold: `Tool Selection` is rescued onto `Tool Selection Errors`, and
`Task Orchestration Errors` reaches nothing at all, because `Task Orchestration`
is a label and the gold spelling is that label plus a suffix.

Nothing here re-implements the rule. Whether a string reaches a label is measured
by handing upstream's own function a one-label taxonomy and seeing what comes
back, so the answers come from the file under audit rather than from a second
copy of it living in this repository. The reverse direction is measured the same
way with the two arguments swapped.
"""

from __future__ import annotations

import random
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from trailaudit import adversarial, artifacts, gold, predictors, scoring, upstream
from trailaudit.datacheck import HELD, LATENT, VIOLATED, Finding, any_violated, verdicts, wrapped

COMMITTED = Path("results/normaliser.json")

# The date the audit was run. Any fixed integer would do; what matters is that
# the shuffled order is written into the artifact so a reader can rebuild it.
SEED = 20260827

Normalise = Callable[[str, list[str]], str]

# Three strings the spec claims the fallback promotes, re-derived here rather
# than taken on trust. They are also the only place in this report where a
# candidate was chosen by a person instead of enumerated.
QUOTED_IN_THE_SPEC = ("error", "resource", "tool")

# Line 14 tests the argument before line 17 strips it, so a category of one
# space is not caught by the empty-string guard and reaches the fallback as "",
# which is inside every label.
WHITESPACE_ONLY = " "

# How many of the shortest strings get printed beside a label. The full lists go
# in the artifact; the report only has to make the length believable.
SHOWN = 4

EXACT = "exact"
FALLBACK = "fallback"
NEITHER = "neither"


def squash(text: str) -> str:
    return text.lower().replace(" ", "")


def substrings(label: str) -> set[str]:
    """Every non-empty substring of a label, in the form line 26 compares.

    Enumerating the squashed form rather than the label as written is the
    complete enumeration, not a shortcut: `category_no_spaces` is all the
    fallback ever looks at, so two candidates with the same squashed form are
    the same candidate as far as the function is concerned.
    """
    folded = squash(label)
    return {
        folded[start:stop]
        for start in range(len(folded))
        for stop in range(start + 1, len(folded) + 1)
    }


def candidates(taxonomy: Sequence[str]) -> tuple[str, ...]:
    every: set[str] = set()
    for label in taxonomy:
        every |= substrings(label)
    return tuple(sorted(every, key=lambda one: (len(one), one)))


def accepts(normalise: Normalise, candidate: str, label: str) -> bool:
    """Does `candidate` reach `label` when `label` is the only label on offer?

    A one-element taxonomy turns `normalize_category` into the predicate this
    module needs without this repository owning a second copy of the matching
    rule. It hands back the label on a hit and the lowercased candidate on a
    miss, and the two cannot collide because a candidate equal to the label is a
    hit anyway.
    """
    return normalise(candidate, [label]) == label


def which_loop(normalise: Normalise, candidate: str, label: str) -> str:
    """Whether `candidate` reaches `label` by exact match, by the fallback, or not at all.

    Measured with a decoy rather than by re-implementing line 21. The decoy is
    the candidate with a character appended, so it contains the candidate and
    cannot equal it: the fallback matches the decoy and the exact loop cannot,
    and both loops run the list in order. So the real label coming back means
    the exact loop fired before the fallback ever reached the decoy.
    """
    if not accepts(normalise, candidate, label):
        return NEITHER
    decoy = squash(candidate) + "z"
    return EXACT if normalise(candidate, [decoy, label]) == label else FALLBACK


@dataclass(frozen=True)
class Reach:
    candidate: str
    lands: str
    matched: tuple[str, ...]

    @property
    def order_dependent(self) -> bool:
        """Two labels will take this string, and only list position decides which.

        This reads two matches as decided by position, which is right as long as
        neither of them is an exact match: the exact loop at line 21 runs the
        whole list before the fallback does, so an exact hit wins from anywhere.
        A candidate could only be both if one label's squashed form sat inside
        another's, and none of TRAIL's 21 does. test_pinned_clone.py holds that
        precondition rather than leaving it as an assumption here.
        """
        return len(self.matched) > 1


def probe(taxonomy: Sequence[str], normalise: Normalise) -> tuple[Reach, ...]:
    labels = list(taxonomy)
    return tuple(
        Reach(
            candidate=one,
            lands=normalise(one, labels),
            matched=tuple(label for label in labels if accepts(normalise, one, label)),
        )
        for one in candidates(taxonomy)
    )


@dataclass(frozen=True)
class Shortest:
    label: str
    strings: tuple[str, ...]
    reaching: int

    @property
    def length(self) -> int:
        return len(self.strings[0]) if self.strings else 0


def shortest_reaching(reaches: Sequence[Reach], taxonomy: Sequence[str]) -> tuple[Shortest, ...]:
    """Per label, the shortest enumerated strings that land on it and how many land at all.

    Labels are walked in the taxonomy's own order because that is the order the
    fallback resolves ties in, so a label with nothing under it is a label every
    one of whose substrings was claimed by an earlier one.
    """
    landed: dict[str, list[str]] = {label: [] for label in taxonomy}
    for one in reaches:
        if one.lands in landed:
            landed[one.lands].append(one.candidate)
    found = []
    for label in taxonomy:
        reaching = landed[label]
        floor = min((len(one) for one in reaching), default=0)
        found.append(
            Shortest(
                label=label,
                strings=tuple(sorted(one for one in reaching if len(one) == floor)),
                reaching=len(reaching),
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class Drifted:
    """One gold spelling that is not a taxonomy label, and what the normaliser does with it."""

    spelling: str
    errors: int
    lands: str
    loop: str
    would_contain: tuple[str, ...]


def drift(
    counted: Counter[str], taxonomy: Sequence[str], normalise: Normalise
) -> tuple[Drifted, ...]:
    labels = list(taxonomy)
    found = []
    for spelling in gold.off_taxonomy(counted, labels):
        lands = normalise(spelling, labels)
        loop = which_loop(normalise, spelling, lands) if lands in set(labels) else NEITHER
        found.append(
            Drifted(
                spelling=spelling,
                errors=counted[spelling],
                lands=lands,
                loop=loop,
                # The same predicate with its arguments the other way round: which
                # labels sit inside this gold string, which is what line 26 would
                # have asked if the containment ran the other way.
                would_contain=tuple(
                    label for label in labels if accepts(normalise, label, spelling)
                ),
            )
        )
    return tuple(found)


def p6(
    shortest: Sequence[Shortest], taxonomy: Sequence[str], drifted: Sequence[Drifted]
) -> Finding:
    claim = "no string shorter than the shortest taxonomy label normalises to a taxonomy label"
    floor = min(len(squash(label)) for label in taxonomy)
    briefest = [label for label in taxonomy if len(squash(label)) == floor]
    reached = [one for one in shortest if one.strings]
    shortest_hit = min((one.length for one in reached), default=floor)
    hardest = max((one.length for one in reached), default=0)
    at_one = sum(1 for one in reached if one.length == 1)

    if shortest_hit >= floor:
        return Finding(
            "P6",
            claim,
            HELD,
            f"nothing under {floor} characters reaches a label",
            [f"nothing under {floor} characters reaches a label"],
        )

    promoted = [one for one in drifted if one.loop == FALLBACK]
    fell_through = [one for one in drifted if one.loop == NEITHER]
    lines = [
        *wrapped(
            f"the shortest labels are {floor} characters once spaces are removed: "
            f"{', '.join(repr(one) for one in briefest)}"
        ),
        *wrapped(
            f"every one of the {len(taxonomy)} is reached by a string of {hardest} characters "
            f"or fewer, and {at_one} of them by a single character"
        ),
        "",
        *wrapped(
            f"the direction is what does the damage. Line 26 asks whether the judge's string "
            f"is inside the label, never the reverse, so a string vaguer than a label is "
            f"promoted to it while a string more specific than a label matches nothing. Both "
            f"are in TRAIL's own gold: the fallback promotes {plural(len(promoted), 'spelling')} "
            f"covering {plural(sum(one.errors for one in promoted), 'error')}, and "
            f"{plural(len(fell_through), 'spelling')} covering "
            f"{plural(sum(one.errors for one in fell_through), 'error')} reach no label at all."
        ),
    ]
    return Finding(
        "P6",
        claim,
        VIOLATED,
        f"the shortest label is {floor} characters and every one of the {len(taxonomy)} is "
        f"reached by {hardest} characters or fewer, {at_one} of them by one",
        lines,
    )


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def shuffled(taxonomy: Sequence[str], seed: int = SEED) -> tuple[str, ...]:
    """The same 21 labels in a different order, fixed so the run reproduces."""
    reordered = list(taxonomy)
    random.Random(seed).shuffle(reordered)
    return tuple(reordered)


@dataclass(frozen=True)
class Rescored:
    """One predictor on one split, averaged under the pinned order and under the shuffle."""

    split: str
    predictor: str
    pinned: tuple[float, float]
    reordered: tuple[float, float]

    @property
    def figures_that_moved(self) -> tuple[str, ...]:
        """Which of this row's two figures the shuffle moved, joint before location.

        Per metric rather than per row. P5's magnitude is published as a count
        of figures against a denominator of `rows * 2`, so a row that counted as
        one while moving both of its metrics would understate the violation by
        half. Zero on the real data either way, which is exactly the condition
        this project reports TRAIL's own line 45 for.
        """
        return tuple(
            metric
            for metric, was, now in (
                ("joint", self.pinned[0], self.reordered[0]),
                ("location", self.pinned[1], self.reordered[1]),
            )
            if was != now
        )


def rescore(
    scorer: ModuleType,
    clone: Path,
    index: dict[str, dict[str, list[str]]],
    taxonomy: Sequence[str],
) -> tuple[Rescored, ...]:
    """The whole slice 2 measurement again, with a shuffled taxonomy and the same predictions.

    Only the list handed to `calculate_metrics` moves. The predictions are built
    once from the pinned order and reused, because `every-span-once` picks
    `taxonomy[0]` and would otherwise change its own answer for a reason that has
    nothing to do with the normaliser. What is left is a clean question: does the
    same input score differently because the labels were listed in another order?

    Every row is scored a third time, through `main()` under the pinned order, and
    the run stops unless that reproduces the pinned figures here. Without it a
    shuffle that moved nothing would be indistinguishable from an aggregation
    that measured nothing.
    """
    other = shuffled(taxonomy)
    bound = gold.binder(scorer.normalize_category, taxonomy)
    rows = []
    with tempfile.TemporaryDirectory(prefix="trailaudit-shuffle-") as workspace:
        for split in upstream.SPLITS:
            loaded, _ = gold.read_directory(clone / split.annotations, split.name)
            annotations = {one.trace: one for one in loaded}
            cases = adversarial.cases_for(split, index[split.name], annotations, taxonomy)
            for predictor in predictors.PREDICTORS:
                through_main = scoring.score_split(
                    scorer=scorer,
                    gold_dir=clone / split.annotations,
                    cases=cases,
                    annotations=annotations,
                    normalise=bound,
                    predictor=predictor,
                    workspace=Path(workspace) / predictor.name / split.name,
                )
                emitted = {trace: predictor.emit(case) for trace, case in cases.items()}
                pinned = scoring.averaged_under(scorer, annotations, emitted, taxonomy)
                _confirm_reproduces(pinned, through_main, predictor.name, split.name)
                rows.append(
                    Rescored(
                        split=split.name,
                        predictor=predictor.name,
                        pinned=_rounded(pinned),
                        reordered=_rounded(
                            scoring.averaged_under(scorer, annotations, emitted, other)
                        ),
                    )
                )
    return tuple(rows)


def _rounded(pair: tuple[float, float]) -> tuple[float, float]:
    return (round(pair[0], scoring.PLACES), round(pair[1], scoring.PLACES))


def _confirm_reproduces(
    pinned: tuple[float, float], through_main: scoring.Scores, predictor: str, split: str
) -> None:
    both = ((pinned[0], through_main.joint_accuracy, "joint"), (
        pinned[1],
        through_main.location_accuracy,
        "location",
    ))
    for mine, theirs, metric in both:
        if abs(mine - theirs) > scoring.AGREEMENT:
            raise scoring.DiagnosticDrifted(
                f"{predictor} on {split}: calculate_scores.main() returned {metric} accuracy "
                f"{theirs!r} and averaging calculate_metrics under the same taxonomy order "
                f"gives {mine!r}. The shuffled figures beside it would mean nothing while "
                f"these two disagree, so the run stops here."
            )


def shortest_table(shortest: Sequence[Shortest]) -> list[str]:
    rows = [f"{'label':<34}{'shortest':>9}{'reaching':>10}  strings of that length"]
    for one in shortest:
        if not one.strings:
            rows.append(f"{one.label:<34}{'none':>9}{0:>10}  every substring claimed earlier")
            continue
        shown = ", ".join(repr(text) for text in one.strings[:SHOWN])
        more = f", and {len(one.strings) - SHOWN} more" if len(one.strings) > SHOWN else ""
        rows.append(f"{one.label:<34}{one.length:>9}{one.reaching:>10}  {shown}{more}")
    return rows


def drift_table(drifted: Sequence[Drifted]) -> list[str]:
    rows = [f"{'gold spelling':<36}{'errors':>7}{'loop':>10}  lands on"]
    for one in sorted(drifted, key=lambda item: (item.loop, item.spelling)):
        lands = one.lands if one.loop != NEITHER else f"kept as {one.lands!r}"
        rows.append(f"{one.spelling!r:<36}{one.errors:>7}{one.loop:>10}  {lands}")
    return rows


def quoted_probes(taxonomy: Sequence[str], normalise: Normalise) -> list[str]:
    labels = list(taxonomy)
    lines = [f"{one!r:<12} -> {normalise(one, labels)!r}" for one in QUOTED_IN_THE_SPEC]
    lines.append(f"{WHITESPACE_ONLY!r:<12} -> {normalise(WHITESPACE_ONLY, labels)!r}")
    return lines


@dataclass(frozen=True)
class Study:
    taxonomy: tuple[str, ...]
    normalise: Normalise
    reaches: tuple[Reach, ...]
    shortest: tuple[Shortest, ...]
    vocabulary: Counter[str]
    drifted: tuple[Drifted, ...]
    rescored: tuple[Rescored, ...]

    def ambiguous_gold(self) -> list[str]:
        """Gold spellings that more than one label will take, which is what the shuffle needs."""
        return sorted(
            spelling
            for spelling in self.vocabulary
            if sum(1 for label in self.taxonomy if accepts(self.normalise, spelling, label)) > 1
        )


def study(clone: Path, index: dict[str, dict[str, list[str]]]) -> Study:
    scorer = upstream.load_scorer(clone)
    taxonomy = upstream.taxonomy(clone)
    reaches = probe(taxonomy, scorer.normalize_category)
    loaded, _ = gold.read_all(clone)
    counted = gold.vocabulary(loaded)
    return Study(
        taxonomy=taxonomy,
        normalise=scorer.normalize_category,
        reaches=reaches,
        shortest=shortest_reaching(reaches, taxonomy),
        vocabulary=counted,
        drifted=drift(counted, taxonomy, scorer.normalize_category),
        rescored=rescore(scorer, clone, index, taxonomy),
    )


def p5(done: Study) -> Finding:
    claim = "the normaliser's output depends on its input alone, not on the taxonomy order"
    ambiguous = [one for one in done.reaches if one.order_dependent]
    if not ambiguous:
        return Finding(
            "P5",
            claim,
            HELD,
            f"no string among {len(done.reaches):,} reaches two labels",
            [f"no string among {len(done.reaches)} reaches two labels"],
        )

    widest = max(ambiguous, key=lambda one: len(one.matched))
    other = list(shuffled(done.taxonomy))
    elsewhere = sum(
        1 for one in ambiguous if done.normalise(one.candidate, other) != one.lands
    )
    figures = len(done.rescored) * 2
    moved = sum(len(one.figures_that_moved) for one in done.rescored)
    in_the_gold = done.ambiguous_gold()

    lines = [
        *wrapped(
            f"{len(ambiguous)} of the {len(done.reaches):,} enumerated strings match more than "
            f"one label, so list position decides which one they get. {widest.candidate!r} "
            f"matches all {len(widest.matched)} and lands on {widest.lands!r} because that "
            f"label is listed first."
        ),
        *wrapped(
            f"reordering the taxonomy under seed {SEED} sends {elsewhere} of those "
            f"{len(ambiguous)} to a different label"
        ),
        "",
        *wrapped(
            f"{len(in_the_gold)} of the {len(done.vocabulary)} gold spellings are among them, "
            f"and no prediction is either, because the predictors emit the labels themselves "
            f"and an exact match is settled before the fallback runs. So rescoring the whole of "
            f"slice 2 under the shuffled order moves {moved} of the {figures} figures it "
            f"produces, over {len(done.rescored)} predictor and split pairs with joint and "
            f"location accuracy each, to {scoring.PLACES} decimal places."
        ),
        "",
        *wrapped(
            "which is why the verdict above reads LATENT and not VIOLATED: the consequence "
            "this property was written to catch, two people scoring the same data and getting "
            "different numbers, does not follow here. `all_categories` is a literal inside "
            "`main()` at line 115, so nobody running calculate_scores.py gets a different order "
            "by accident. The exposure is `calculate_metrics` and `normalize_category` "
            "themselves, which are importable, take the list as a parameter, and are the "
            "reusable part of this file. Latent is not held, and it still exits 3."
        ),
    ]
    return Finding(
        "P5",
        claim,
        VIOLATED if moved else LATENT,
        f"{len(ambiguous)} of {len(done.reaches):,} strings change label under a shuffled "
        f"taxonomy, {elsewhere} of them under seed {SEED}, and {moved} of the {figures} figures "
        f"in slice 2 move as a result",
        lines,
    )


def report(done: Study) -> tuple[list[str], bool]:
    findings = [p6(done.shortest, done.taxonomy, done.drifted), p5(done)]
    rescued = [one for one in done.drifted if one.loop != NEITHER]
    reversible = [one for one in done.drifted if one.loop == NEITHER and one.would_contain]

    lines = [
        findings[0].render(),
        "",
        findings[1].render(),
        "",
        f"{len(done.reaches):,} distinct substrings of the {len(done.taxonomy)} labels, and "
        f"where each one lands",
        *(f"  {row}".rstrip() for row in shortest_table(done.shortest)),
        "",
        "the three the spec names, plus a category of one space, which line 14 lets past",
        "because it tests the argument before line 17 strips it",
        *(f"  {row}" for row in quoted_probes(done.taxonomy, done.normalise)),
        "",
        f"the {len(done.drifted)} gold spellings that are not a label, and which loop caught them",
        *(f"  {row}".rstrip() for row in drift_table(done.drifted)),
        "",
        *wrapped(
            f"{len(rescued)} of the {len(done.drifted)} are rescued, covering "
            f"{sum(one.errors for one in rescued)} of the "
            f"{sum(one.errors for one in done.drifted)} errors those spellings carry. Of the "
            f"ones that are not, a label sits inside {len(reversible)} of them covering "
            f"{plural(sum(one.errors for one in reversible), 'error')}, and the same line "
            f"would catch those if it asked the containment the other way round. The rest are "
            f"misspellings no substring rule reaches."
        ),
        "",
        f"the same {len(done.rescored) * 2} figures under the pinned order and under seed {SEED}",
        *(f"  {row}".rstrip() for row in rescored_table(done.rescored)),
    ]
    return lines, any_violated(findings)


def rescored_table(rescored: Sequence[Rescored]) -> list[str]:
    head = f"{'split':<11}{'predictor':<27}{'joint':>9}{'shuffled':>10}{'location':>10}"
    rows = [f"{head}{'shuffled':>10}"]
    for one in rescored:
        rows.append(
            f"{one.split:<11}{one.predictor:<27}{one.pinned[0]:>9.6f}{one.reordered[0]:>10.6f}"
            f"{one.pinned[1]:>10.6f}{one.reordered[1]:>10.6f}"
        )
    return rows


def artifact(done: Study, index_sha256: str) -> dict:
    labels = list(done.taxonomy)
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
        "index_sha256": index_sha256,
        "properties": verdicts([p6(done.shortest, done.taxonomy, done.drifted), p5(done)]),
        "labels": len(done.taxonomy),
        "shortest_label_squashed": min(len(squash(label)) for label in done.taxonomy),
        "substrings_enumerated": len(done.reaches),
        "labels_reached": sum(1 for one in done.shortest if one.strings),
        "shortest_reaching": {
            one.label: {
                "length": one.length,
                "strings": list(one.strings),
                "reaching": one.reaching,
            }
            for one in done.shortest
        },
        "quoted_in_the_spec": {
            one: done.normalise(one, labels) for one in QUOTED_IN_THE_SPEC
        },
        "whitespace_only": done.normalise(WHITESPACE_ONLY, labels),
        "gold_drift": [
            {
                "spelling": one.spelling,
                "errors": one.errors,
                "lands": one.lands,
                "loop": one.loop,
                "labels_inside_it": list(one.would_contain),
            }
            for one in done.drifted
        ],
        "order_dependent": _order_dependent(done),
        "shuffle": {
            "seed": SEED,
            "taxonomy": list(shuffled(done.taxonomy)),
            "ambiguous_gold_spellings": done.ambiguous_gold(),
            "figures_that_moved": [
                f"{one.split}/{one.predictor} {metric}"
                for one in done.rescored
                for metric in one.figures_that_moved
            ],
            "scores": [
                {
                    "split": one.split,
                    "predictor": one.predictor,
                    "joint_accuracy": {"pinned": one.pinned[0], "shuffled": one.reordered[0]},
                    "location_accuracy": {"pinned": one.pinned[1], "shuffled": one.reordered[1]},
                }
                for one in done.rescored
            ],
        },
    }


def _order_dependent(done: Study) -> dict:
    """Every string whose label is decided by list position, with where each order sends it.

    All of them rather than a chosen few. Which ones look interesting is exactly
    the judgement an audit should not be making on the reader's behalf, and 237
    short strings cost less to commit than the argument would.
    """
    other = list(shuffled(done.taxonomy))
    ambiguous = sorted(
        (one for one in done.reaches if one.order_dependent),
        key=lambda one: (-len(one.matched), one.candidate),
    )
    return {
        "count": len(ambiguous),
        "moved_under_the_shuffle": sum(
            1 for one in ambiguous if done.normalise(one.candidate, other) != one.lands
        ),
        "strings": [
            {
                "string": one.candidate,
                "labels": len(one.matched),
                "pinned": one.lands,
                "shuffled": done.normalise(one.candidate, other),
            }
            for one in ambiguous
        ],
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit normaliser")
