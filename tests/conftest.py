from __future__ import annotations

import pathlib

import pytest

from trailaudit import upstream

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def clone() -> pathlib.Path:
    """The fetched trail-benchmark, or a skip naming the command that writes it.

    Every test that needs the real 186 MB is behind this. CI never has it, which
    is the point: the committed span index and the hand-built fixtures carry the
    offline suite, and these are the checks that only mean something when the
    real thing is on disk.
    """
    where = REPO_ROOT / upstream.DEFAULT_CLONE
    if not upstream.scorer_path(where).is_file():
        pytest.skip(f"no clone at {where}. Run `trailaudit fetch` to include these")
    return where


@pytest.fixture(scope="session")
def annotations() -> pathlib.Path:
    return REPO_ROOT / "tests" / "fixtures" / "annotations"
