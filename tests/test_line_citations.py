"""Every line number this repository quotes into calculate_scores.py, checked against it.

The README, the module docstrings and the terminal reports cite the pinned
scorer by line more than thirty times, and `upstream.py` states the invariant
that every one of them is a line number in the tree at PINNED_COMMIT. Nothing
enforced it. Two of them were wrong: line 48 is a comment and the pair
construction is line 49, line 16 is blank and the strip is line 17, and both
were printed to stdout on every run of the command that quoted them. The
scorer's SHA-256 is pinned, so the citations are as checkable as the digests
are, and `report.py` deliberately excludes line numbers from `loose_scores`,
which left them the one class of figure in the document with no guard at all.

The map below is the whole of what is cited. The second test walks the
repository's own prose for anything shaped like a citation and refuses a number
the map does not carry, so a new citation cannot arrive unchecked.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from trailaudit import upstream

# line number in benchmarking/calculate_scores.py -> text that line has to contain
CITED = {
    12: "def normalize_category",
    14: "if not category:",
    17: "category = category.lower().strip()",
    21: "if category == std_cat.lower()",
    26: 'if category_no_spaces in std_cat.lower().replace(" ", "")',
    30: "return category",
    33: "def calculate_metrics",
    36: 'gt_categories_raw = [error.get("category", "")',
    40: 'gen_errors = generated.get("errors", [])',
    44: "# Normalize categories",
    45: "gt_categories = [normalize_category(",
    46: "gen_categories = [normalize_category(",
    49: "gt_loc_cat_pairs = [(gt_locations[i], gt_categories[i])",
    50: "gen_loc_cat_pairs = [(gen_locations[i], gen_categories[i])",
    53: "common_pairs = set(gt_loc_cat_pairs).intersection",
    54: "joint_accuracy = len(common_pairs)",
    57: "common_locations = set(gt_locations).intersection",
    58: "location_accuracy = len(common_locations)",
    61: "y_true = np.zeros(len(all_categories))",
    64: "for cat in gt_categories:",
    66: "y_true[all_categories.index(cat)] = 1",
    70: "y_pred[all_categories.index(cat)] = 1",
    115: "all_categories = [",
    122: "]",
    154: 'print(f"Generated file {generated_file} does not exist")',
    157: "try:",
    173: "if gt_scores and gen_scores:",
    238: "gen_overall_scores.append(gen)",
    242: "except Exception as e:",
    243: 'print(f"Error processing {file}: {e}")',
    298: "# Aggregate all predictions for weighted F1 and per-category metrics",
    300: "all_y_true_array = np.vstack(all_y_true)",
    310: "support = np.sum(all_y_true_array[:, i])",
    312: "precision = true_positives / (true_positives + false_positives)",
    314: "f1 = 2 * precision * recall",
    361: 'if __name__ == "__main__":',
}

CITATION = re.compile(r"\blines?\s+(\d+)(?:\s+(?:to|and|or)\s+(\d+))?")

# "line 39 column 5" is a json decoder talking about a gold annotation file, not
# a citation into the scorer, and the two shapes are otherwise identical.
DECODER_POSITION = re.compile(r"\bline\s+\d+\s+column\s+\d+")


@pytest.mark.upstream
def test_every_cited_line_says_what_it_is_cited_for(clone: pathlib.Path) -> None:
    lines = upstream.verified_source(clone).decode("utf-8").splitlines()
    wrong = {
        number: lines[number - 1].strip()
        for number, expected in CITED.items()
        if expected not in lines[number - 1]
    }
    assert wrong == {}, f"cited line numbers that do not say what they are cited for: {wrong}"


def quoting_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Everything that could carry a citation, except this file.

    This one has to name the two numbers that were wrong in order to explain
    them, so scanning itself would report its own history as an unchecked
    citation. Same reason check_fingerprint.py skips the word list.
    """
    found = [
        *sorted((root / "src" / "trailaudit").glob("*.py")),
        *sorted((root / "tests").glob("*.py")),
        *sorted(root.glob("*.md")),
        *sorted(root.glob("docs/*.md")),
    ]
    return [path for path in found if path.name != pathlib.Path(__file__).name]


def test_nothing_cites_a_line_the_map_does_not_carry(repo_root: pathlib.Path) -> None:
    """Otherwise the map is a list of the citations somebody remembered to add.

    The check above is only as good as its coverage, and coverage of a set of
    numbers written in prose cannot be maintained by hand.
    """
    uncovered: dict[str, set[int]] = {}
    for path in quoting_files(repo_root):
        prose = DECODER_POSITION.sub("", path.read_text(encoding="utf-8"))
        cited = {
            int(number)
            for match in CITATION.finditer(prose)
            for number in match.groups()
            if number is not None
        }
        beyond = cited - set(CITED)
        if beyond:
            uncovered[path.relative_to(repo_root).as_posix()] = beyond

    assert uncovered == {}, f"line citations with nothing checking them: {uncovered}"
