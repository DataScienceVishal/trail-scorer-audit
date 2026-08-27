from __future__ import annotations

import json
import pathlib

import pytest

from trailaudit import spans, upstream
from trailaudit.spans import IndexInconsistent

NESTED = {
    "trace_id": "t1",
    "spans": [
        {
            "span_id": "root",
            "child_spans": [
                {"span_id": "a", "child_spans": [{"span_id": "a1"}, {"span_id": "a2"}]},
                {"span_id": "b", "child_spans": []},
            ],
        }
    ],
}


def test_span_ids_descends_into_child_spans() -> None:
    assert spans.span_ids(NESTED) == ["root", "a", "a1", "a2", "b"]


def test_the_top_level_list_alone_would_have_found_one_span() -> None:
    """The mistake the recursive walk exists to avoid, stated as a test.

    Both GAIA and SWE Bench hang their whole tree off one or two root entries,
    so a span count taken from `len(doc["spans"])` comes out near the trace
    count and looks plausible.
    """
    assert len(NESTED["spans"]) == 1
    assert len(spans.span_ids(NESTED)) > 1


def test_a_repeated_identifier_survives_the_walk() -> None:
    """One SWE Bench trace really does emit the same span_id twice.

    72822db6e120878d916b515c2501246b carries b14646a5fcac02fd in two places, so
    deduplicating inside span_ids would silently make its span count 13 instead
    of 14 and the committed index would stop describing the file.
    """
    twice = {"spans": [{"span_id": "x", "child_spans": [{"span_id": "x"}]}]}
    assert spans.span_ids(twice) == ["x", "x"]


def test_a_span_with_no_identifier_contributes_nothing_but_its_children() -> None:
    headless = {"spans": [{"child_spans": [{"span_id": "kid"}]}]}
    assert spans.span_ids(headless) == ["kid"]


def test_render_and_load_round_trip(tmp_path: pathlib.Path) -> None:
    built = {"GAIA": {"t1": ["a", "b"]}, "SWE Bench": {"t2": ["c"]}}
    path = tmp_path / "spans.json"
    path.write_text(spans.render(built), encoding="utf-8")
    assert spans.load(path) == built


def test_load_rejects_a_summary_that_disagrees_with_its_own_lists(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "spans.json"
    path.write_text(spans.render({"GAIA": {"t1": ["a", "b"]}}), encoding="utf-8")
    document = json.loads(path.read_text())
    document["summary"]["GAIA"]["spans"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="its own lists say"):
        spans.load(path)


def test_load_rejects_an_index_built_at_another_commit(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "spans.json"
    path.write_text(spans.render({"GAIA": {"t1": ["a"]}}), encoding="utf-8")
    document = json.loads(path.read_text())
    document["pinned_commit"] = "0" * 40
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="trailaudit index"):
        spans.load(path)


def test_differences_names_the_trace_that_moved() -> None:
    committed = {"GAIA": {"t1": ["a", "b"], "t2": ["c"]}}
    fresh = {"GAIA": {"t1": ["a"], "t3": ["d"]}}
    assert spans.differences(committed, fresh) == [
        "GAIA/t1: 2 spans committed, 1 found",
        "GAIA/t2: in the committed index, not in the clone",
        "GAIA/t3: in the clone, not in the committed index",
    ]


def test_build_says_what_to_run_when_the_clone_is_absent(tmp_path: pathlib.Path) -> None:
    with pytest.raises(upstream.MissingClone, match="trailaudit fetch"):
        spans.build(tmp_path / "nothing")
