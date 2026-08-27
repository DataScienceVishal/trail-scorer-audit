"""An invented taxonomy and two invented normalisers, shared by the offline tests.

None of it is TRAIL's. The real 21 labels live in the pinned clone and are read
out of it at run time, and the real normaliser is imported from it, so the
offline suite needs stand-ins with the same shape and none of the content.

`Widget Failures` shares a prefix with `Widget Errors` on purpose. Without a
pair like that no string in this taxonomy could match two labels, and the
order-dependence tests would have nothing to bite on.
"""

from __future__ import annotations

TAXONOMY = (
    "Widget Errors",
    "Sprocket-only",
    "Gasket Handling Failures",
    "Flange Misuse",
    "Widget Failures",
)


def strip_only(spelling: str) -> str:
    """Deliberately not a copy of upstream's normaliser.

    Matching on strip() alone is enough to tell a spelling the real normaliser
    would rescue from one it drops, without this repository keeping a second
    implementation of the function it is auditing.
    """
    return spelling.strip()


def first_prefix(spelling: str, taxonomy: list[str]) -> str:
    """An exact loop, then a looser loop several labels can win, resolved by list position.

    That shape is what normaliser.py asks questions of. The looser loop here is
    prefix matching, not the substring matching TRAIL uses, and the difference is
    the point: a stand-in that copied the rule under audit would let a test pass
    by agreeing with the copy rather than by exercising the code.
    """
    if not spelling:
        return ""
    folded = spelling.lower().strip().replace(" ", "")
    for label in taxonomy:
        if folded == label.lower().replace(" ", ""):
            return label
    for label in taxonomy:
        if label.lower().replace(" ", "").startswith(folded):
            return label
    return spelling.lower().strip()
