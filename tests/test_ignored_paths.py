"""The style check must not police the vendored clone.

`trailaudit fetch` writes 186 MB of somebody else's repository into `.trail/`,
including their README, which contains a phrase on this project's banned list.
Nothing about the audit gives it standing to fail its own commit over the TRAIL
authors' prose, and the failure would come and go depending on whether the
reader had run fetch yet, which is the worst kind of check.
"""

from __future__ import annotations

import pathlib

import check_fingerprint

# Spelled by concatenation for the same reason check_fingerprint.py builds its own
# escape markers that way: a file that needs a banned phrase in order to test the
# ban would otherwise fail the ban.
BANNED_PHRASE = "state-of" + "-the-art"


def test_the_fetched_clone_is_not_walked(tmp_path: pathlib.Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kept.md").write_text("Ordinary prose.\n", encoding="utf-8")
    vendored = tmp_path / ".trail" / "trail-benchmark"
    vendored.mkdir(parents=True)
    (vendored / "README.md").write_text(f"It is {BANNED_PHRASE}.\n", encoding="utf-8")

    walked = {path.relative_to(tmp_path).as_posix() for path in check_fingerprint.walk(tmp_path)}
    assert walked == {"docs/kept.md"}


def test_the_phrase_in_that_clone_is_one_the_checker_would_otherwise_catch(
    tmp_path: pathlib.Path,
) -> None:
    """Otherwise the test above passes for the wrong reason and proves nothing.

    If the banned list ever loses that phrase, the first test starts asserting
    that a file with no hits in it produces no hits, and would keep passing with
    the skip removed.
    """
    loose = tmp_path / "README.md"
    loose.write_text(f"It is {BANNED_PHRASE}.\n", encoding="utf-8")
    rules = check_fingerprint.parse_banned(
        check_fingerprint.find_word_list(pathlib.Path(__file__).resolve().parent)
    )
    assert check_fingerprint.check_file(loose, rules)
