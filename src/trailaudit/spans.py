"""The one derived artifact this repository commits: trace identifier to span identifiers.

Identifiers and integers, no trace content. That is deliberate. The traces are
185.6 MB and derive from GAIA and SWE-Bench Lite, so committing any of them
would need a licence answer this project does not have. Committing the
identifiers needs no answer, and it is enough for what the audit does with them:
the adversarial predictor names every span in a trace and never reads one.

Span identifiers are not the top-level `spans` list. That holds one entry per
GAIA trace and one or two per SWE Bench trace, because the tree hangs off
`child_spans` and nests several levels deep. A reader who takes
`len(doc["spans"])` for the span count gets roughly one span per trace, which is
the mistake this module exists to not make.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from trailaudit import upstream
from trailaudit.upstream import SPLITS, MissingClone

COMMITTED = Path("index/spans.json")


class IndexInconsistent(ValueError):
    """The committed index does not describe itself consistently."""


def span_ids(trace: dict[str, Any]) -> list[str]:
    """Depth-first over `spans` then `child_spans`, in document order.

    Duplicates are kept rather than collapsed. One SWE Bench trace emits the
    same span identifier twice, and a set here would have hidden it behind a
    count that looked right.
    """
    found: list[str] = []
    stack = list(reversed(trace.get("spans") or []))
    while stack:
        span = stack.pop()
        identifier = span.get("span_id")
        if identifier is not None:
            found.append(identifier)
        stack.extend(reversed(span.get("child_spans") or []))
    return found


def build(clone: Path) -> dict[str, dict[str, list[str]]]:
    by_split: dict[str, dict[str, list[str]]] = {}
    for split in SPLITS:
        here = clone / split.traces
        if not here.is_dir():
            raise MissingClone(f"{here} is not a directory. Run `trailaudit fetch` first")
        by_split[split.name] = {
            path.stem: span_ids(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(here.glob("*.json"), key=lambda p: p.stem)
        }
    return by_split


def digest(by_split: dict[str, dict[str, list[str]]]) -> str:
    """One hash over the index a run actually read, for that run's artifact to record.

    Over the parsed structure rather than the file's bytes, so reindenting the
    JSON does not move it and one changed identifier does. This is the index's
    half of what SCORER_SHA256 does for the scorer. Without it an artifact
    records which scorer produced it and not which input, and `--index
    something-else.json` writing to the default `--out` leaves a committed file
    that nothing downstream can tell apart from the real run.
    """
    canonical = json.dumps(by_split, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def summarise(by_split: dict[str, dict[str, list[str]]]) -> dict[str, dict[str, int]]:
    return {
        name: {
            "traces": len(traces),
            "spans": sum(len(ids) for ids in traces.values()),
            "distinct_spans": len({one for ids in traces.values() for one in ids}),
        }
        for name, traces in by_split.items()
    }


def render(by_split: dict[str, dict[str, list[str]]]) -> str:
    """One trace per line, so a diff points at the trace that moved.

    json.dump with an indent puts every span identifier on its own line, which
    buries 148 traces in several thousand lines; without an indent the whole
    artifact is one line and a diff says only that it changed.
    """
    lines = [
        "{",
        f'  "pinned_commit": {json.dumps(upstream.PINNED_COMMIT)},',
        f'  "summary": {json.dumps(summarise(by_split), sort_keys=True)},',
        '  "splits": {',
    ]
    for split_index, (name, traces) in enumerate(by_split.items()):
        lines.append(f"    {json.dumps(name)}: {{")
        for trace_index, (trace, ids) in enumerate(traces.items()):
            comma = "," if trace_index < len(traces) - 1 else ""
            lines.append(f"      {json.dumps(trace)}: {json.dumps(ids)}{comma}")
        lines.append("    }" + ("," if split_index < len(by_split) - 1 else ""))
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def load(path: Path = COMMITTED) -> dict[str, dict[str, list[str]]]:
    """Read the committed index, re-deriving the summary rather than trusting it.

    The summary is in the file for a human who opens it, not as a second source
    of truth. Recomputing it on every load means a hand-edited count is a load
    error instead of a figure that quietly disagrees with the lists below it.
    """
    text = path.read_text(encoding="utf-8")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IndexInconsistent(
            f"{path} is not JSON: {exc.msg} at line {exc.lineno} column {exc.colno}. Rebuild "
            f"it with `trailaudit index`."
        ) from exc
    if document.get("pinned_commit") != upstream.PINNED_COMMIT:
        raise IndexInconsistent(
            f"{path} was built at {document.get('pinned_commit')}, and the audit is pinned to "
            f"{upstream.PINNED_COMMIT}. Rebuild it with `trailaudit index`."
        )
    by_split = document["splits"]
    absent = [split.name for split in SPLITS if split.name not in by_split]
    if absent:
        raise IndexInconsistent(
            f"{path} has no entry for {', '.join(absent)}, and every command that reads it "
            f"expects one per split. Rebuild it with `trailaudit index`."
        )
    derived = summarise(by_split)
    if derived != document.get("summary"):
        raise IndexInconsistent(
            f"{path} carries a summary of {document.get('summary')}, and its own lists say "
            f"{derived}"
        )
    return by_split


def differences(
    committed: dict[str, dict[str, list[str]]],
    fresh: dict[str, dict[str, list[str]]],
) -> list[str]:
    lines: list[str] = []
    for name in sorted(set(committed) | set(fresh)):
        was, now = committed.get(name, {}), fresh.get(name, {})
        for trace in sorted(set(was) | set(now)):
            if trace not in was:
                lines.append(f"{name}/{trace}: in the clone, not in the committed index")
            elif trace not in now:
                lines.append(f"{name}/{trace}: in the committed index, not in the clone")
            elif was[trace] != now[trace]:
                lines.append(f"{name}/{trace}: {_disagreement(was[trace], now[trace])}")
    return lines


def _disagreement(was: list[str], now: list[str]) -> str:
    """What changed about one trace's spans, without printing the same number twice.

    The list comparison fires on identifiers as well as on counts, and reporting
    lengths alone rendered a renamed span as "2 spans committed, 2 found", which
    reads as a broken diff rather than as a finding. Only the differing-length
    case had a test.
    """
    if len(was) != len(now):
        return f"{len(was)} spans committed, {len(now)} found"
    at = next(
        position
        for position, (before, after) in enumerate(zip(was, now, strict=True))
        if before != after
    )
    return (
        f"{len(was)} spans in both, differing from position {at}: committed {was[at]!r}, "
        f"found {now[at]!r}"
    )
