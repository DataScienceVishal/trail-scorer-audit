"""An invented taxonomy and an invented normaliser, shared by the offline tests.

Neither is TRAIL's. The real 21 labels live in the pinned clone and are read out
of it at run time, and the real normaliser is imported from it, so the offline
suite needs stand-ins with the same shape and none of the content.
"""

from __future__ import annotations

TAXONOMY = ("Widget Errors", "Sprocket-only", "Gasket Handling Failures", "Flange Misuse")


def strip_only(spelling: str) -> str:
    """Deliberately not a copy of upstream's normaliser.

    Matching on strip() alone is enough to tell a spelling the real normaliser
    would rescue from one it drops, without this repository keeping a second
    implementation of the function it is auditing.
    """
    return spelling.strip()
