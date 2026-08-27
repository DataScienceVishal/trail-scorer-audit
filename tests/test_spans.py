from __future__ import annotations

import json
import pathlib

import pytest

from trailaudit import spans, upstream
from trailaudit.spans import IndexInconsistent

BOTH_SPLITS = {"GAIA": {"t1": ["a", "b"]}, "SWE Bench": {"t2": ["c"]}}

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
    built = BOTH_SPLITS
    path = tmp_path / "spans.json"
    path.write_text(spans.render(built), encoding="utf-8")
    assert spans.load(path) == built


def test_load_rejects_a_summary_that_disagrees_with_its_own_lists(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "spans.json"
    path.write_text(spans.render(BOTH_SPLITS), encoding="utf-8")
    document = json.loads(path.read_text())
    document["summary"]["GAIA"]["spans"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="its own lists say"):
        spans.load(path)


def test_load_rejects_an_index_built_at_another_commit(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "spans.json"
    path.write_text(spans.render(BOTH_SPLITS), encoding="utf-8")
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


def test_differences_names_the_identifier_when_the_count_did_not_move() -> None:
    """A renamed span used to render as "2 spans committed, 2 found".

    The comparison is on the lists, so it fires on identifiers as well as on
    counts, and the message reported lengths either way. Only the
    differing-length case had a test, which is how a diff that printed the same
    number twice went out.
    """
    committed = {"GAIA": {"t1": ["a", "b"]}}
    fresh = {"GAIA": {"t1": ["a", "z"]}}
    (line,) = spans.differences(committed, fresh)
    assert line == "GAIA/t1: 2 spans in both, differing from position 1: committed 'b', found 'z'"


def test_a_truncated_index_is_reported_rather_than_raised_by_the_decoder(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "spans.json"
    path.write_text(spans.render(BOTH_SPLITS)[:80], encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="trailaudit index"):
        spans.load(path)


def test_build_says_what_to_run_when_the_clone_is_absent(tmp_path: pathlib.Path) -> None:
    with pytest.raises(upstream.MissingClone, match="trailaudit fetch"):
        spans.build(tmp_path / "nothing")


def test_load_refuses_an_index_that_is_missing_a_split(tmp_path: pathlib.Path) -> None:
    """`--index` can point anywhere, and datacheck.measure indexes both splits by name.

    An index carrying only GAIA used to reach `index["SWE Bench"]` and come back
    as a bare KeyError traceback, which exits 1 by accident rather than by
    contract.
    """
    path = tmp_path / "spans.json"
    path.write_text(spans.render({"GAIA": {"t1": ["a"]}}), encoding="utf-8")
    with pytest.raises(IndexInconsistent, match="SWE Bench"):
        spans.load(path)


def test_the_digest_moves_with_one_identifier_and_not_with_the_layout(
    tmp_path: pathlib.Path,
) -> None:
    """What every artifact records about the index its run read.

    Over the parsed structure, so a reindented file hashes the same and a
    swapped identifier does not. Without that an artifact says which scorer
    produced it and nothing about which input, and `--index doctored.json`
    writing to the default `--out` is invisible afterwards.
    """
    path = tmp_path / "spans.json"
    path.write_text(spans.render(BOTH_SPLITS), encoding="utf-8")
    plain = tmp_path / "compact.json"
    plain.write_text(
        json.dumps({"pinned_commit": upstream.PINNED_COMMIT,
                    "summary": spans.summarise(BOTH_SPLITS),
                    "splits": BOTH_SPLITS}),
        encoding="utf-8",
    )
    assert spans.digest(spans.load(path)) == spans.digest(spans.load(plain))

    swapped = {"GAIA": {"t1": ["a", "z"]}, "SWE Bench": {"t2": ["c"]}}
    assert spans.digest(swapped) != spans.digest(BOTH_SPLITS)
