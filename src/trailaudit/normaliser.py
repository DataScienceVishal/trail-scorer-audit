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

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from trailaudit import artifacts, gold, upstream
from trailaudit.datacheck import HELD, VIOLATED, Finding, wrapped

COMMITTED = Path("results/normaliser.json")

Normalise = Callable[[str, list[str]], str]

# Three strings the spec claims the fallback promotes, re-derived here rather
# than taken on trust. They are also the only place in this report where a
# candidate was chosen by a person instead of enumerated.
QUOTED_IN_THE_SPEC = ("error", "resource", "tool")

# Line 14 tests the argument before line 16 strips it, so a category of one
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


def probe(taxonomy: Sequence[str], normalise: Normalise) -> tuple[Reach, ...]:
    labels = list(taxonomy)
    return tuple(Reach(one, normalise(one, labels)) for one in candidates(taxonomy))


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
        return Finding("P6", claim, HELD, [f"nothing under {floor} characters reaches a label"])

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
    return Finding("P6", claim, VIOLATED, lines)


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


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
    drifted: tuple[Drifted, ...]


def study(clone: Path) -> Study:
    taxonomy = upstream.taxonomy(clone)
    normalise = upstream.load_scorer(clone).normalize_category
    reaches = probe(taxonomy, normalise)
    loaded, _ = gold.read_all(clone)
    return Study(
        taxonomy=taxonomy,
        normalise=normalise,
        reaches=reaches,
        shortest=shortest_reaching(reaches, taxonomy),
        drifted=drift(gold.vocabulary(loaded), taxonomy, normalise),
    )


def report(done: Study) -> tuple[list[str], bool]:
    finding = p6(done.shortest, done.taxonomy, done.drifted)
    rescued = [one for one in done.drifted if one.loop != NEITHER]
    reversible = [one for one in done.drifted if one.loop == NEITHER and one.would_contain]

    lines = [
        finding.render(),
        "",
        f"{len(done.reaches)} distinct substrings of the {len(done.taxonomy)} labels, and "
        f"where each one lands",
        *(f"  {row}".rstrip() for row in shortest_table(done.shortest)),
        "",
        "the three the spec names, plus a category of one space, which line 14 lets past",
        "because it tests the argument before line 16 strips it",
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
    ]
    return lines, finding.verdict == VIOLATED


def artifact(done: Study) -> dict:
    labels = list(done.taxonomy)
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
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
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit normaliser")
