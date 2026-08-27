"""Reading TRAIL's gold annotations the way its scorer reads them, and counting what it loses.

`main()` in calculate_scores.py opens each gold file inside a `try` at line 157
and catches everything at line 242 with a printed message, then continues. So a
gold file that does not parse is not an error, it is one fewer term in an
average whose denominator is `files_processed`. This module finds those, and
finds the gold category strings that survive loading but not normalising.

Nothing here calls the normaliser directly. It is passed in, because the real
one lives in the pinned clone and the tests have no clone: a stand-in of four
made-up labels exercises the same code path offline, and `data-check` hands over
`normalize_category` from the file whose SHA-256 has already been checked.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from trailaudit.upstream import SPLITS, MissingClone


@dataclass(frozen=True)
class ParseFailure:
    """Where a gold file stops being JSON, located by character rather than by decoder.

    `line` and `column` point at the character that broke the parse, worked out
    by `culprit()`. `decoder` is whatever json.JSONDecodeError said, kept
    verbatim and never used as the published position, because it moves between
    interpreters: CPython 3.12 calls TRAIL's bad file "line 39 column 5:
    Expecting value" and CPython 3.13 calls the same bytes "line 38 column 10:
    Illegal trailing comma before end of array". Publishing either one would
    have made a headline figure a fact about the reader's Python.
    """

    split: str
    trace: str
    line: int
    column: int
    character: str
    decoder: str

    def __str__(self) -> str:
        return (
            f"{self.split}/{self.trace}.json: {self.character!r} at line {self.line} "
            f"column {self.column}"
        )


def culprit(text: str, position: int) -> tuple[int, int, str]:
    """The character the decoder tripped on, as (line, column, character), 1-indexed.

    3.13 points `pos` straight at the offending comma. 3.12 points it at the
    bracket that follows, having only noticed once it needed a value and found a
    closing token. Taking the comma when either place holds one collapses the
    two readings onto the character a person would point at.
    """
    if not text:
        return 1, 1, ""
    here = position if 0 <= position < len(text) else len(text) - 1
    back = here - 1
    while back >= 0 and text[back].isspace():
        back -= 1
    at = back if text[here] != "," and back >= 0 and text[back] == "," else here
    line = text.count("\n", 0, at) + 1
    column = at - text.rfind("\n", 0, at)
    return line, column, text[at]


@dataclass(frozen=True)
class Annotation:
    split: str
    trace: str
    categories: tuple[str, ...]
    locations: tuple[str, ...]


def read_directory(where: Path, split: str) -> tuple[list[Annotation], list[ParseFailure]]:
    if not where.is_dir():
        raise MissingClone(f"{where} is not a directory. Run `trailaudit fetch` first")
    loaded: list[Annotation] = []
    refused: list[ParseFailure] = []
    for path in sorted(where.glob("*.json"), key=lambda p: p.stem):
        text = path.read_text(encoding="utf-8")
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            line, column, character = culprit(text, exc.pos)
            refused.append(ParseFailure(split, path.stem, line, column, character, str(exc)))
            continue
        errors = document.get("errors") or []
        loaded.append(
            Annotation(
                split=split,
                trace=path.stem,
                categories=tuple(error.get("category", "") for error in errors),
                locations=tuple(error.get("location", "") for error in errors),
            )
        )
    return loaded, refused


def read_all(clone: Path) -> tuple[list[Annotation], list[ParseFailure]]:
    loaded: list[Annotation] = []
    refused: list[ParseFailure] = []
    for split in SPLITS:
        found, failed = read_directory(clone / split.annotations, split.name)
        loaded.extend(found)
        refused.extend(failed)
    return loaded, refused


def vocabulary(annotations: Sequence[Annotation]) -> Counter[str]:
    """Every gold category string as written, with how many errors carry it."""
    counted: Counter[str] = Counter()
    for one in annotations:
        counted.update(one.categories)
    return counted


def off_taxonomy(counted: Counter[str], taxonomy: Sequence[str]) -> list[str]:
    """P4. The gold strings that are not, character for character, one of the labels."""
    known = set(taxonomy)
    return sorted(spelling for spelling in counted if spelling not in known)


def normalised_counts(counted: Counter[str], normalise: Callable[[str], str]) -> Counter[str]:
    after: Counter[str] = Counter()
    for spelling, times in counted.items():
        after[normalise(spelling)] += times
    return after


def dropped(
    counted: Counter[str],
    taxonomy: Sequence[str],
    normalise: Callable[[str], str],
) -> dict[str, int]:
    """Gold strings the normaliser hands back unchanged because nothing matched.

    A dropped category is not discarded. It keeps its place in
    `gt_loc_cat_pairs` under its lowercased spelling, so it stays in the joint
    accuracy denominator while no prediction using the correct taxonomy label
    can ever match it, and it never sets a bit in the per-category vectors at
    lines 64 to 66 because those are guarded by `if cat in all_categories`.
    """
    known = set(taxonomy)
    return {
        spelling: times
        for spelling, times in sorted(counted.items())
        if normalise(spelling) not in known
    }


def binder(
    normalise: Callable[[str, list[str]], str], taxonomy: Sequence[str]
) -> Callable[[str], str]:
    """Upstream's two-argument normalize_category, in the one-argument shape used above."""

    def bound(spelling: str) -> str:
        return normalise(spelling, list(taxonomy))

    return bound
