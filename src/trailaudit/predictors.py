"""Six predictors, and a record of exactly what each one is handed.

None of them is a model. Each is a few lines that turn one trace's span
identifiers, or one trace's gold labels, into the `{"errors": [...]}` document
`calculate_scores.py` reads. What they are for is to put a floor and a ceiling
around the two headline metrics so the published figures have something to sit
between.

The one the claim rests on is `all-spans-all-categories`. Its whole input is the
list of span identifiers for the trace, taken from `index/spans.json`, which
holds sixteen-digit hex strings and nothing else. It cannot read a span's name,
its inputs, its outputs or its timings, because none of those are in the file it
is given. That is the difference between this and the oracle rows: the oracle
rows need the answer key, and this one needs a list of identifiers a judge is
handed in its prompt.

`knows_gold` on each record says which side a predictor is on, and
tests/test_predictors.py holds it to that by running every `knows_gold=False`
predictor twice, once against the real gold and once against gold replaced with
nonsense, and requiring identical output.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

Error = dict[str, str]


@dataclass(frozen=True)
class Case:
    """One trace as a predictor is handed it: identifiers, the taxonomy, the answer key."""

    span_ids: tuple[str, ...]
    taxonomy: tuple[str, ...]
    gold: tuple[Error, ...]


def once_each(values: Iterable[str]) -> list[str]:
    """First appearance wins, order kept.

    SWE Bench trace 72822db6e120878d916b515c2501246b lists span
    b14646a5fcac02fd twice, so a predictor that walked the raw list would emit
    the same (location, category) pair twice. Line 53 of the scorer intersects
    sets, so the duplicate cannot change a score, but it would inflate the count
    of predictions emitted, and that count is the denominator of the volume
    ratio published next to the score. Dropping it keeps the ratio the smallest
    number this audit can honestly claim.
    """
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def silent(case: Case) -> list[Error]:
    return []


def gold_exact(case: Case) -> list[Error]:
    return [dict(one) for one in case.gold]


def gold_mispaired(case: Case) -> list[Error]:
    """The gold locations and the gold categories, rotated one step apart.

    Same locations and the same multiset of categories as `gold-exact`, and the
    same number of errors, so anything that separates the two is the pairing and
    nothing else. A trace with one gold error is unchanged by a rotation of one,
    and so is a trace whose errors all carry the same category, which is where
    this row's residual joint accuracy comes from.
    """
    locations = [one.get("location", "") for one in case.gold]
    categories = [one.get("category", "") for one in case.gold]
    return [
        {"location": location, "category": categories[(index + 1) % len(categories)]}
        for index, location in enumerate(locations)
    ]


def every_span_once(case: Case) -> list[Error]:
    """Every span identifier, once, under the first taxonomy label.

    The label is arbitrary and cannot matter to location accuracy: line 57
    intersects `gt_locations` with `gen_locations` and never looks at a category.
    It does matter to joint accuracy, which is why this row's joint figure is a
    lower bound on what one fixed label can reach rather than a property of the
    metric.
    """
    label = case.taxonomy[0]
    return [{"location": one, "category": label} for one in once_each(case.span_ids)]


def gold_spans_all_categories(case: Case) -> list[Error]:
    locations = once_each(one.get("location", "") for one in case.gold)
    return [{"location": one, "category": label} for one in locations for label in case.taxonomy]


def all_spans_all_categories(case: Case) -> list[Error]:
    return [
        {"location": one, "category": label}
        for one in once_each(case.span_ids)
        for label in case.taxonomy
    ]


def one_span_all_categories(case: Case) -> list[Error]:
    """The whole taxonomy at the first span identifier in the file, and nowhere else.

    The span is arbitrary and the choice is visible: first in document order,
    which for these traces is the root. It cannot matter to the per-category
    vectors at lines 61 to 70, which are set from the categories alone and never
    see a location, and it decides location accuracy almost entirely. That gap is
    P7, and it is why this predictor is not in PREDICTORS: the adversarial table
    reports joint, location and volume, and none of those is where this one has
    something to say.
    """
    spans = once_each(case.span_ids)
    if not spans:
        return []
    return [{"location": spans[0], "category": label} for label in case.taxonomy]


@dataclass(frozen=True)
class Predictor:
    name: str
    knows_gold: bool
    blurb: str
    emit: Callable[[Case], list[Error]]


PREDICTORS = (
    Predictor(
        "silent",
        knows_gold=False,
        blurb="emits nothing at all",
        emit=silent,
    ),
    Predictor(
        "gold-exact",
        knows_gold=True,
        blurb="the answer key, copied",
        emit=gold_exact,
    ),
    Predictor(
        "gold-mispaired",
        knows_gold=True,
        blurb="the answer key with categories rotated one step",
        emit=gold_mispaired,
    ),
    Predictor(
        "every-span-once",
        knows_gold=False,
        blurb="every span identifier, one fixed category",
        emit=every_span_once,
    ),
    Predictor(
        "gold-spans-all-categories",
        knows_gold=True,
        blurb="every gold location crossed with the taxonomy",
        emit=gold_spans_all_categories,
    ),
    Predictor(
        "all-spans-all-categories",
        knows_gold=False,
        blurb="every span identifier crossed with the taxonomy",
        emit=all_spans_all_categories,
    ),
)


# Not in PREDICTORS, and `by_name` does not find it. It exists for `trailaudit
# catf1`, where the question is what the per-category block does with a judge
# that names every category in a trace without locating any of them.
ONE_SPAN = Predictor(
    "one-span-all-categories",
    knows_gold=False,
    blurb="the whole taxonomy at the first span identifier",
    emit=one_span_all_categories,
)


def by_name(name: str) -> Predictor:
    for one in PREDICTORS:
        if one.name == name:
            return one
    raise KeyError(f"no predictor called {name!r}. Have: {', '.join(p.name for p in PREDICTORS)}")


def document(errors: Sequence[Error]) -> dict[str, list[Error]]:
    """The shape `calculate_scores.py` reads back at line 40, and nothing else.

    No `scores` key. The scorer's Pearson block at lines 173 to 238 is guarded
    by `if gt_scores and gen_scores`, so leaving it out keeps this audit clear of
    a correlation it does not measure and does not want in its output.
    """
    return {"errors": list(errors)}
