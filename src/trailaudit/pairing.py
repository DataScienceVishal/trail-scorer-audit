"""What `trailaudit pairing` runs and prints: P8, the one defect that never fires on the gold.

Lines 44 to 48 of calculate_scores.py build the pairs both headline metrics are
computed from:

    gt_categories = [normalize_category(cat, all_categories)
                     for cat in gt_categories_raw if cat]
    gt_loc_cat_pairs = [(gt_locations[i], gt_categories[i])
                        for i in range(len(gt_locations)) if i < len(gt_categories)]

Each of those is one line upstream and is wrapped here to fit.

The categories are filtered on truthiness and the locations are not, and then
the two lists are paired by position. So one error carrying a null or empty
category shortens the category list by one, and every category after it slides
onto the location belonging to the error before. Lines 45 and 48 do the same to
the judge's output, so a judge that emits one null category mispairs its own
answers.

No gold file in either split carries a falsy category, so this changes no
published number. Which is why it is demonstrated on a constructed trace rather
than found in the data, and why the count of real files it affects is printed
next to the demonstration instead of being left out.

The constructed trace is three errors: one with a null category, then two with
real ones. Its locations are `span-one` and friends rather than sixteen-digit
hex, so nothing here can be mistaken for a file from the benchmark.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from trailaudit import artifacts, gold, upstream
from trailaudit.datacheck import HELD, VIOLATED, Finding, verdicts, wrapped
from trailaudit.gold import Annotation

COMMITTED = Path("results/pairing.json")

LOCATIONS = ("span-one", "span-two", "span-three")

TRACE = "constructed"


def errors(taxonomy: tuple[str, ...], with_null: bool) -> list[dict]:
    """Two real errors, optionally behind one carrying a null category.

    The two categories are the first two labels the pinned scorer defines, read
    from the clone rather than written here, so this file names no taxonomy of
    its own and the constructed trace is valid against whatever the pin says.
    """
    real = [
        {"location": LOCATIONS[1], "category": taxonomy[0]},
        {"location": LOCATIONS[2], "category": taxonomy[1]},
    ]
    if not with_null:
        return real
    return [{"location": LOCATIONS[0], "category": None}, *real]


@dataclass(frozen=True)
class Run:
    """One pass of the constructed trace through the pinned scorer."""

    label: str
    gold_has_null: bool
    prediction_has_null: bool
    joint_accuracy: float
    location_accuracy: float


CASES = (
    ("gold carries a null first, prediction correct", True, False),
    ("both clean, which is the control", False, False),
    ("gold clean, prediction carries a null first", False, True),
)


def score(scorer: ModuleType, taxonomy: tuple[str, ...], where: Path) -> tuple[Run, ...]:
    scored = []
    for index, (label, gold_null, gen_null) in enumerate(CASES):
        here = where / str(index)
        gold_dir, gen_dir = here / "gold", here / "generated"
        gold_dir.mkdir(parents=True)
        gen_dir.mkdir(parents=True)
        _write(gold_dir, errors(taxonomy, gold_null))
        _write(gen_dir, errors(taxonomy, gen_null))

        with contextlib.redirect_stdout(io.StringIO()):
            returned = scorer.main(str(gold_dir), str(gen_dir))
        scored.append(
            Run(
                label=label,
                gold_has_null=gold_null,
                prediction_has_null=gen_null,
                joint_accuracy=returned["joint_accuracy"],
                location_accuracy=returned["location_accuracy"],
            )
        )
    return tuple(scored)


def _write(where: Path, listed: list[dict]) -> None:
    (where / f"{TRACE}.json").write_text(json.dumps({"errors": listed}, indent=2), "utf-8")


@dataclass(frozen=True)
class Latent:
    """How often the defect could fire on the real gold, which is the size of it."""

    gold_errors: int
    falsy_categories: int
    traces_that_would_mispair: int
    traces_that_would_lose_a_pair: int


def latent(annotations: list[Annotation]) -> Latent:
    """A falsy category anywhere but the last position shifts every category after it.

    In the last position it shortens the category list without shifting anything,
    so the trace loses its final pair rather than mispairing. Two different
    defects from one line, and reporting them as one number would overstate the
    first.
    """
    falsy = mispairs = lost = 0
    for one in annotations:
        empty = [index for index, category in enumerate(one.categories) if not category]
        falsy += len(empty)
        if not empty:
            continue
        if any(index < len(one.categories) - 1 for index in empty):
            mispairs += 1
        else:
            lost += 1
    return Latent(
        gold_errors=sum(len(one.categories) for one in annotations),
        falsy_categories=falsy,
        traces_that_would_mispair=mispairs,
        traces_that_would_lose_a_pair=lost,
    )


def run(clone: Path) -> tuple[tuple[Run, ...], Latent]:
    scorer = upstream.load_scorer(clone)
    taxonomy = upstream.taxonomy(clone)
    loaded, _ = gold.read_all(clone)
    with tempfile.TemporaryDirectory(prefix="trailaudit-pairing-") as workspace:
        scored = score(scorer, taxonomy, Path(workspace))
    return scored, latent(loaded)


def control(scored: tuple[Run, ...]) -> Run:
    return next(one for one in scored if not one.gold_has_null and not one.prediction_has_null)


def p8(scored: tuple[Run, ...], counted: Latent) -> Finding:
    claim = "the scorer pairs each predicted location with the category predicted for it"
    clean = control(scored)
    misjudged = next(one for one in scored if one.prediction_has_null)
    broken = [
        one
        for one in scored
        if one is not clean and one.joint_accuracy < clean.joint_accuracy
    ]
    if not broken:
        return Finding(
            "P8",
            claim,
            HELD,
            "one null category changed no score on the constructed trace",
            ["one null category changed no score on the constructed trace"],
        )

    lines = [
        *wrapped(
            f"three runs of the pinned scorer over one constructed trace, with the same two "
            f"real errors in every one of them. The control scores "
            f"{clean.joint_accuracy:.3f} joint. Adding one error with a null category, on "
            f"either side, takes it to "
            f"{', '.join(f'{one.joint_accuracy:.3f}' for one in broken)}."
        ),
        "",
        *wrapped(
            f"the sharpest of the three is the judge's own: one that names both real spans, "
            f"gets both categories right, and mentions one further span with no category scores "
            f"{misjudged.location_accuracy:.3f} location accuracy and "
            f"{misjudged.joint_accuracy:.3f} joint. Line 45 drops its null category, line 48 "
            f"pairs what is left against the unfiltered location list, and both of its correct "
            f"answers land on the wrong span."
        ),
        "",
        *wrapped(
            f"latent on the real gold: {counted.falsy_categories} of {counted.gold_errors} gold "
            f"errors carry a falsy category, so {counted.traces_that_would_mispair} files "
            f"mispair and {counted.traces_that_would_lose_a_pair} lose a pair. No published "
            f"figure moves because of this. It is a defect in the scorer, not a correction to "
            f"the leaderboard, and the README says so in those words."
        ),
    ]
    return Finding(
        "P8",
        claim,
        VIOLATED,
        f"one null category takes a correct judge from {clean.joint_accuracy:.3f} joint to "
        f"{misjudged.joint_accuracy:.3f} on the constructed trace, and "
        f"{counted.falsy_categories} of {counted.gold_errors} real gold errors carry one",
        lines,
    )


def table(scored: tuple[Run, ...]) -> list[str]:
    rows = [f"{'run':<46}{'joint':>9}{'location':>10}"]
    for one in scored:
        rows.append(f"{one.label:<46}{one.joint_accuracy:>9.3f}{one.location_accuracy:>10.3f}")
    return rows


def report(
    scored: tuple[Run, ...], counted: Latent, taxonomy: tuple[str, ...]
) -> tuple[list[str], bool]:
    finding = p8(scored, counted)
    lines = [
        finding.render(),
        "",
        "the constructed trace, which is this repository's and not TRAIL's",
        *(
            f"  {row}"
            for row in json.dumps({"errors": errors(taxonomy, True)}, indent=2).splitlines()
        ),
        "",
        "and the three runs of it through the pinned unmodified scorer",
        *(f"  {row}".rstrip() for row in table(scored)),
    ]
    return lines, finding.verdict == VIOLATED


def artifact(scored: tuple[Run, ...], counted: Latent, taxonomy: tuple[str, ...]) -> dict:
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
        "properties": verdicts([p8(scored, counted)]),
        "constructed_trace": {"errors": errors(taxonomy, True)},
        "runs": [
            {
                "label": one.label,
                "gold_has_null": one.gold_has_null,
                "prediction_has_null": one.prediction_has_null,
                "joint_accuracy": one.joint_accuracy,
                "location_accuracy": one.location_accuracy,
            }
            for one in scored
        ],
        "on_the_real_gold": {
            "gold_errors": counted.gold_errors,
            "falsy_categories": counted.falsy_categories,
            "traces_that_would_mispair": counted.traces_that_would_mispair,
            "traces_that_would_lose_a_pair": counted.traces_that_would_lose_a_pair,
        },
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit pairing")
