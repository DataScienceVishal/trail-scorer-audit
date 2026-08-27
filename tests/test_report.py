"""The marker mechanism, and the two ways it can be made to lie.

The blocks themselves are checked against the real README in
tests/test_readme_blocks.py. What is here is the guard: that the scan sees a
marker nobody generates, that it sees a generator nobody publishes, and that
neither of those can be mistaken for a file that already matches.

The mutation this file exists for is the second test. `twicerun` scanned for the
names its generator already offered, which meant deleting a generator and
leaving its marker produced a set comparison of `TABLES` against a subset of
`TABLES`. Nothing could fail, `--update` reported that the file already matched,
and the block sat in the README as a hand-typed figure for the rest of the
project's life.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from trailaudit import report, spans
from trailaudit.artifacts import Stale
from trailaudit.datacheck import LATENT, VIOLATED
from trailaudit.report import BLOCKS, MarkerError, Sources


@pytest.fixture(scope="module")
def src(repo_root: pathlib.Path) -> Sources:
    return report.load(repo_root)


@pytest.fixture(scope="module")
def rendered(src: Sources) -> dict[str, str]:
    return report.render(src)


def wrap(name: str, body: str) -> str:
    return f"<!-- trailaudit:{name} -->\n{body}\n<!-- /trailaudit:{name} -->\n"


def whole(rendered: dict[str, str]) -> str:
    """A minimal markdown file carrying every block, which is what the README has to be."""
    return "# heading\n\n" + "\n".join(wrap(name, body) for name, body in rendered.items())


def test_every_generator_produces_something(rendered: dict[str, str]) -> None:
    assert set(rendered) == set(BLOCKS)
    for name, body in rendered.items():
        assert body.strip(), name


def test_the_nine_properties_come_from_five_separate_runs(src: Sources) -> None:
    """Seven violated and two latent, which is what the conditions table has to show.

    Nine identical cells read as a target that moved. P5 and P8 are the two that
    fail as properties of the scorer while moving no number on this data, and
    the verdict column is where that distinction has to survive.
    """
    decided = report.properties(src)
    assert list(decided) == list(report.PROPERTIES)
    assert [one for one, decision in decided.items() if decision["verdict"] == LATENT] == [
        "P5",
        "P8",
    ]
    assert {one["verdict"] for one in decided.values()} == {VIOLATED, LATENT}


def test_a_property_nobody_decided_is_refused(src: Sources) -> None:
    without = Sources(**{**vars(src), "catf1": {**src.catf1, "properties": {}}})
    with pytest.raises(MarkerError, match="P7"):
        report.properties(without)


def test_two_commands_deciding_the_same_property_are_refused(src: Sources) -> None:
    """Both would be committed, both would be reruns of something, and only one can be shown."""
    borrowed = {**src.pairing, "properties": src.catf1["properties"]}
    twice = Sources(**{**vars(src), "pairing": borrowed})
    with pytest.raises(MarkerError, match="P7 is decided twice"):
        report.properties(twice)


@pytest.fixture
def copied(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    """The committed index and the five artifacts, somewhere they can be doctored."""
    for name in ("index", "results"):
        (tmp_path / name).mkdir()
    committed = [one for one, _ in report.every_artifact(report.load(repo_root))]
    for path in [str(spans.COMMITTED), *committed]:
        (tmp_path / path).write_text((repo_root / path).read_text(encoding="utf-8"), "utf-8")
    return tmp_path


def test_an_artifact_from_a_different_scorer_is_refused(copied: pathlib.Path) -> None:
    """The pin is checked on load; this is the half of it that is not the commit SHA.

    An artifact produced before a re-pin carries figures measured against
    different bytes, and every one of them would render into the README without
    complaint if only the commit were compared.
    """
    tampered = json.loads((copied / "results/catf1.json").read_text(encoding="utf-8"))
    tampered["scorer_sha256"] = "0" * 64
    (copied / "results/catf1.json").write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(Stale, match="catf1"):
        report.load(copied)


def test_an_artifact_produced_against_another_span_index_is_refused(
    copied: pathlib.Path,
) -> None:
    """`--index` is the flag that can make a finding disappear, so the digest is recorded.

    An index of fabricated traces matching Table 5 makes P9 hold. One built from
    the gold locations makes the gold-blind predictor an oracle at the headline
    figure while its row still reads "spans". Neither touches the scorer digest,
    so the check above sees nothing, and both write to results/ under the
    default --out.
    """
    assert report.load(copied).index, "the copy has to load before anything is doctored"

    document = json.loads((copied / spans.COMMITTED).read_text(encoding="utf-8"))
    trace = next(iter(document["splits"]["GAIA"]))
    document["splits"]["GAIA"][trace].append("0123456789abcdef")
    document["summary"] = spans.summarise(document["splits"])
    (copied / spans.COMMITTED).write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(Stale, match="span index"):
        report.load(copied)


def test_the_scan_finds_a_marker_no_generator_has_ever_heard_of() -> None:
    found = report.blocks_in(wrap("invented-last-tuesday", "a figure somebody typed"))
    assert list(found) == ["invented-last-tuesday"]


def test_a_marker_with_no_generator_fails_the_check(rendered: dict[str, str]) -> None:
    """The mutation: delete a generator, leave the marker where it is.

    Simulated by rendering everything except one block, which is exactly the
    state the README would be in the moment somebody removed a function from
    BLOCKS. If this passes, the block freezes at whatever it last said and
    nothing anywhere reports it.
    """
    markdown = whole(rendered)
    without = {name: body for name, body in rendered.items() if name != "headline"}
    assert "headline" in report.blocks_in(markdown)
    with pytest.raises(MarkerError, match="Nothing generates: headline"):
        report.stale(markdown, without)
    with pytest.raises(MarkerError, match="Nothing generates: headline"):
        report.rewrite(markdown, without)


def test_a_generator_with_no_marker_fails_the_check(rendered: dict[str, str]) -> None:
    markdown = whole({name: body for name, body in rendered.items() if name != "drift"})
    with pytest.raises(MarkerError, match="nowhere to put: drift"):
        report.stale(markdown, rendered)


def test_an_edited_block_is_named_and_then_restored(rendered: dict[str, str]) -> None:
    markdown = whole(rendered).replace("0.973", "0.111")
    assert report.stale(markdown, rendered) != []
    restored = report.rewrite(markdown, rendered)
    assert report.stale(restored, rendered) == []
    assert "0.111" not in restored


def test_rewriting_a_file_that_already_matches_changes_nothing(rendered: dict[str, str]) -> None:
    markdown = whole(rendered)
    assert report.rewrite(markdown, rendered) == markdown


def test_a_block_that_grows_does_not_shift_the_ones_below_it(rendered: dict[str, str]) -> None:
    """Replacement runs bottom up. Top down would corrupt every block after the first resize."""
    markdown = whole(rendered)
    shrunk = markdown.replace(rendered["conditions"], "| one | row |")
    assert report.rewrite(shrunk, rendered) == markdown


@pytest.mark.parametrize(
    ("markdown", "complaint"),
    [
        ("<!-- trailaudit:pin -->\nbody\n", "never closes"),
        ("<!-- /trailaudit:pin -->\n", "which is not open"),
        ("<!-- trailaudit:pin -->\n<!-- /trailaudit:drift -->\n", "while pin is open"),
        ("<!-- trailaudit:pin -->\n<!-- trailaudit:drift -->\n", "inside pin"),
        (wrap("pin", "one") + wrap("pin", "two"), "opens twice"),
    ],
)
def test_a_malformed_pair_is_refused_rather_than_skipped(markdown: str, complaint: str) -> None:
    with pytest.raises(MarkerError, match=complaint):
        report.blocks_in(markdown)


def test_a_score_typed_into_prose_is_found_and_one_inside_a_block_is_not(
    rendered: dict[str, str],
) -> None:
    markdown = whole(rendered)
    assert report.loose_scores(markdown) == []
    (complaint,) = report.loose_scores(markdown + "\nit scored 0.973 on both.\n")
    assert complaint.endswith("it scored 0.973 on both.")
    assert complaint.startswith(f"line {len(markdown.splitlines()) + 2}:")


def test_the_four_place_weighted_f1_column_is_caught_in_prose_too(
    rendered: dict[str, str],
) -> None:
    """Three places was the rule; the catf1 column publishes four.

    The pattern ended at a word boundary, so a fourth digit stopped it matching
    and every hand-typed figure from that column was invisible to the check that
    exists to find hand-typed figures.
    """
    markdown = whole(rendered)
    (complaint,) = report.loose_scores(markdown + "\nweighted F1 came out at 0.4725.\n")
    assert complaint.endswith("weighted F1 came out at 0.4725.")


def test_a_line_number_is_not_mistaken_for_a_score(rendered: dict[str, str]) -> None:
    """Lines 54 and 58, arXiv:2505.08638 and 186.4 MB all appear in the prose."""
    prose = "\nlines 54 and 58 of arXiv:2505.08638v3, over 186.4 MB, at 0ffbed9db859.\n"
    assert report.loose_scores(whole(rendered) + prose) == []


def test_the_span_index_carries_none_of_upstreams_words(src: Sources) -> None:
    """The licence position, as an assertion rather than a paragraph.

    Nothing from TRAIL is committed here except the derived index, and the index
    is identifiers. This is what notices the first time somebody adds a field
    holding a question, a category or a line of code for debugging.
    """
    committed = json.loads((src.root / spans.COMMITTED).read_text(encoding="utf-8"))
    found = set(report.strings_in(committed))
    assert found & report.upstream_strings(src) == set()
    assert [one for one in found if len(one.split()) > 3] == []
