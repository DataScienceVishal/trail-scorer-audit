"""What `trailaudit catf1` runs and prints: P7, and the per-category block at lines 298 to 314.

Category F1 is the third column of TRAIL's Table 1 and it is built from two
21-element binary vectors per trace, at lines 61 to 70:

    for cat in gt_categories:
        if cat in all_categories:
            y_true[all_categories.index(cat)] = 1

A location never reaches those lines. So the vectors say which categories appear
somewhere in a trace, and any judge that names all 21 sets every bit of `y_pred`
whatever it thinks the errors are attached to.

The measurement is four predictors through the pinned unmodified scorer. Two of
them are the pair the property turns on: `all-spans-all-categories` names every
category at every span, and `one-span-all-categories` names every category at
the first span identifier in the file and nowhere else. Same 21 categories per
trace, same number of traces, different locations. If the per-category block
tells them apart, P7 holds.

The other two are context. `gold-exact` is what a perfect judge scores, and
`gold-spans-all-categories` is there to show that the block does move, but for
the wrong reason: it emits nothing at all in a trace whose gold has no errors,
so it sets fewer bits, which is a difference in how much it says rather than in
where it says it.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from trailaudit import adversarial, artifacts, gold, predictors, scoring, upstream
from trailaudit.datacheck import HELD, VIOLATED, Finding, any_violated, verdicts, wrapped

COMMITTED = Path("results/catf1.json")

# Ordered so the table reads from the answer key down to the predictor that
# names everything and locates nothing.
LINEUP = (
    predictors.by_name("gold-exact"),
    predictors.by_name("gold-spans-all-categories"),
    predictors.by_name("all-spans-all-categories"),
    predictors.ONE_SPAN,
)

# The two that name all 21 categories in every trace and differ only in where
# they put them. gold-spans-all-categories is not one of them: it emits nothing
# at all in a trace whose gold has no errors, so its block moves for a reason
# that has nothing to do with location.
DIFFER_ONLY_IN_WHERE = ("all-spans-all-categories", predictors.ONE_SPAN.name)

COLUMNS = ("precision", "recall", "f1", "support")


@dataclass(frozen=True)
class Row:
    split: str
    predictor: str
    joint_accuracy: float
    location_accuracy: float
    weighted_f1: float
    files_scored: int
    per_category: dict[str, dict[str, float]]

    @property
    def supported(self) -> list[str]:
        """Categories the gold uses at all. The other columns have nothing to score."""
        return [name for name, one in self.per_category.items() if one["support"]]

    @property
    def at_full_recall(self) -> list[str]:
        return [name for name in self.supported if self.per_category[name]["recall"] == 1.0]


def measure(returned: dict, taxonomy: tuple[str, ...]) -> dict:
    """The per-category block as plain floats, in the taxonomy's own order.

    numpy scalars come out of lines 300 to 310 and json.dumps refuses them, so
    the conversion happens here rather than in the artifact, where a missed one
    would be a crash at the end of a three-second run.
    """
    published = returned["category_metrics"]
    return {
        label: {name: float(published[label][name]) for name in COLUMNS} for label in taxonomy
    }


def run(clone: Path, index: dict[str, dict[str, list[str]]]) -> tuple[Row, ...]:
    scorer = upstream.load_scorer(clone)
    taxonomy = upstream.taxonomy(clone)
    rows = []
    with tempfile.TemporaryDirectory(prefix="trailaudit-catf1-") as workspace:
        for split in upstream.SPLITS:
            loaded, _ = gold.read_directory(clone / split.annotations, split.name)
            annotations = {one.trace: one for one in loaded}
            cases = adversarial.cases_for(split, index[split.name], annotations, taxonomy)
            for predictor in LINEUP:
                driven = scoring.drive(
                    scorer=scorer,
                    gold_dir=clone / split.annotations,
                    cases=cases,
                    annotations=annotations,
                    predictor=predictor,
                    workspace=Path(workspace) / predictor.name / split.name,
                )
                rows.append(
                    Row(
                        split=split.name,
                        predictor=predictor.name,
                        joint_accuracy=round(driven.returned["joint_accuracy"], scoring.PLACES),
                        location_accuracy=round(
                            driven.returned["location_accuracy"], scoring.PLACES
                        ),
                        weighted_f1=round(float(driven.returned["weighted_f1"]), scoring.PLACES),
                        files_scored=driven.files_processed,
                        per_category=measure(driven.returned, taxonomy),
                    )
                )
    return tuple(rows)


def indistinguishable(rows: tuple[Row, ...], split: str) -> bool:
    """Do the two predictors that differ only in where they put things score the same?"""
    blocks = [
        one.per_category
        for one in rows
        if one.split == split and one.predictor in DIFFER_ONLY_IN_WHERE
    ]
    return len(blocks) == len(DIFFER_ONLY_IN_WHERE) and all(one == blocks[0] for one in blocks)


def paired(rows: tuple[Row, ...], split: str) -> tuple[Row, Row]:
    """The located predictor and the unlocated one, in that order."""
    located, blind = (
        next(one for one in rows if one.split == split and one.predictor == name)
        for name in DIFFER_ONLY_IN_WHERE
    )
    return located, blind


def splits_of(rows: tuple[Row, ...]) -> list[str]:
    return list(dict.fromkeys(one.split for one in rows))


def p7(rows: tuple[Row, ...]) -> Finding:
    claim = "per-category F1 separates naming a category at the right span from naming it anywhere"
    same = [split for split in splits_of(rows) if indistinguishable(rows, split)]
    if not same:
        return Finding(
            "P7",
            claim,
            HELD,
            "the per-category block moved when the locations did",
            ["the per-category block moved with the locations"],
        )

    lines = []
    for split in same:
        located, blind = paired(rows, split)
        lines += wrapped(
            f"{split}: {located.predictor} and {blind.predictor} return the same number in "
            f"every one of the {len(blind.per_category)} columns, precision recall f1 and "
            f"support, and the same weighted F1 of {blind.weighted_f1:.4f}. Their location "
            f"accuracy is {located.location_accuracy:.3f} against "
            f"{blind.location_accuracy:.3f}, and their joint accuracy "
            f"{located.joint_accuracy:.3f} against {blind.joint_accuracy:.3f}."
        )
    lines.append("")
    for split in same:
        _, blind = paired(rows, split)
        lines += wrapped(
            f"{split}: recall is 1.000 in all {len(blind.at_full_recall)} columns carrying "
            f"support, and precision in each is that column's support over the "
            f"{blind.files_scored} scored traces. Neither number reads a trace."
        )
    return Finding(
        "P7",
        claim,
        VIOLATED,
        "; ".join(_p7_magnitude(rows, split) for split in same),
        lines,
    )


def _p7_magnitude(rows: tuple[Row, ...], split: str) -> str:
    located, blind = paired(rows, split)
    return (
        f"{split} scores the same {len(blind.per_category)} columns for a predictor at "
        f"{located.location_accuracy:.3f} location accuracy and one at "
        f"{blind.location_accuracy:.3f}"
    )


def lineup_table(rows: tuple[Row, ...], split: str) -> list[str]:
    head = f"{'predictor':<27}{'joint':>9}{'location':>10}{'weighted F1':>13}"
    printed = [f"{head}{'recall 1.000':>15}{'support':>9}"]
    for one in rows:
        if one.split != split:
            continue
        printed.append(
            f"{one.predictor:<27}{one.joint_accuracy:>9.3f}{one.location_accuracy:>10.3f}"
            f"{one.weighted_f1:>13.4f}{len(one.at_full_recall):>15}{len(one.supported):>9}"
        )
    return printed


def category_table(row: Row) -> list[str]:
    printed = [f"{'category':<34}{'support':>9}{'precision':>11}{'recall':>9}{'f1':>9}"]
    for label, scored in sorted(
        row.per_category.items(), key=lambda pair: (-pair[1]["support"], pair[0])
    ):
        printed.append(
            f"{label:<34}{int(scored['support']):>9}{scored['precision']:>11.4f}"
            f"{scored['recall']:>9.4f}{scored['f1']:>9.4f}"
        )
    return printed


def report(rows: tuple[Row, ...]) -> tuple[list[str], bool]:
    finding = p7(rows)
    lines = [finding.render(), ""]
    for split in splits_of(rows):
        _, blind = paired(rows, split)
        lines += [
            f"{split}: four predictors through the pinned scorer. Its gold uses "
            f"{len(blind.supported)} of the {len(blind.per_category)} categories",
            *(f"  {row}".rstrip() for row in lineup_table(rows, split)),
            "",
            *wrapped(
                f"and the per-category block for {blind.predictor}, which puts all "
                f"{len(blind.per_category)} labels on one span identifier and reads no trace "
                f"content at all"
            ),
            *(f"  {row}".rstrip() for row in category_table(blind)),
            "",
            *wrapped(
                f"its location accuracy on this split is {blind.location_accuracy:.3f}, so no "
                f"gold error here is annotated at the first span identifier in its trace, which "
                f"is the root. The per-category block above is what it scores anyway."
            ),
            "",
        ]
    lines += wrapped(
        "gold-spans-all-categories is the row that does move, and it moves for the wrong "
        "reason: it is the only one of the three that emits nothing in a trace whose gold "
        "carries no errors, so it sets fewer bits and picks up fewer false positives. That is a "
        "difference in how much it says. Where it says it changes nothing."
    )
    return lines, any_violated([finding])


def artifact(rows: tuple[Row, ...], index_sha256: str) -> dict:
    return {
        "pinned_commit": upstream.PINNED_COMMIT,
        "scorer_sha256": upstream.SCORER_SHA256,
        "index_sha256": index_sha256,
        "properties": verdicts([p7(rows)]),
        "identical_per_category_block": [
            split for split in splits_of(rows) if indistinguishable(rows, split)
        ],
        "differ_only_in_where": list(DIFFER_ONLY_IN_WHERE),
        "rows": [
            {
                "split": one.split,
                "predictor": one.predictor,
                "joint_accuracy": one.joint_accuracy,
                "location_accuracy": one.location_accuracy,
                "weighted_f1": one.weighted_f1,
                "files_scored": one.files_scored,
                "categories_with_support": len(one.supported),
                "categories_at_full_recall": len(one.at_full_recall),
                "per_category": one.per_category,
            }
            for one in rows
        ],
    }


def load(path: Path = COMMITTED) -> dict:
    return artifacts.load(path, rerun="trailaudit catf1")
