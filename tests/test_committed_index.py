"""The committed span index, checked without the 186 MB download.

This artifact is what makes the audit run on a fresh clone in seconds, and it is
the only upstream-derived thing in the repository. If it is wrong, everything
downstream of it is wrong quietly, so the shape checks here are deliberately
literal.
"""

from __future__ import annotations

import pathlib
import re

from trailaudit import spans, upstream

SPAN_ID = re.compile(r"[0-9a-f]{16}")


def test_the_committed_index_loads(repo_root: pathlib.Path) -> None:
    loaded = spans.load(repo_root / spans.COMMITTED)
    assert set(loaded) == {split.name for split in upstream.SPLITS}


def test_every_identifier_is_a_sixteen_digit_hex_span_id(repo_root: pathlib.Path) -> None:
    """OpenTelemetry span ids are 8 bytes. A trace id would be 32 digits and would
    mean the walk picked up the wrong key."""
    loaded = spans.load(repo_root / spans.COMMITTED)
    odd = [
        one
        for traces in loaded.values()
        for ids in traces.values()
        for one in ids
        if not SPAN_ID.fullmatch(one)
    ]
    assert odd == []


def test_no_trace_is_indexed_as_empty(repo_root: pathlib.Path) -> None:
    """An empty list is what a walk that missed `child_spans` would leave behind."""
    loaded = spans.load(repo_root / spans.COMMITTED)
    empty = [
        f"{name}/{trace}"
        for name, traces in loaded.items()
        for trace, ids in traces.items()
        if not ids
    ]
    assert empty == []


def test_trace_identifiers_do_not_repeat_across_splits(repo_root: pathlib.Path) -> None:
    loaded = spans.load(repo_root / spans.COMMITTED)
    gaia, swe = (set(loaded[split.name]) for split in upstream.SPLITS)
    assert gaia & swe == set()
