"""Reading, writing and diffing the JSON that a command commits.

Every command here ends the same way. It runs against the pinned clone, prints
what it found, and then either writes a JSON artifact or reruns and diffs
against the committed one under `--check`. The diff has to point at the leaf that
moved rather than saying the file changed, because the artifacts are the only
place a figure in the README is allowed to come from and "results/adversarial.json
differs" is not an actionable thing to be told.

`index/spans.json` keeps its own renderer, because a diff over 148 traces is only
readable when each trace is one line, and that layout is not worth generalising
for the sake of the three files that do not need it.
"""

from __future__ import annotations

import json
from pathlib import Path

from trailaudit import upstream


class Stale(ValueError):
    """A committed artifact was produced against a different pin than the audit runs at."""


def render(built: dict) -> str:
    return json.dumps(built, indent=2) + "\n"


def write(path: Path, built: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(built), encoding="utf-8")


def load(path: Path, rerun: str) -> dict:
    stored = json.loads(path.read_text(encoding="utf-8"))
    if stored.get("pinned_commit") != upstream.PINNED_COMMIT:
        raise Stale(
            f"{path} was produced at {stored.get('pinned_commit')} and the audit is pinned to "
            f"{upstream.PINNED_COMMIT}. Rerun `{rerun}`."
        )
    return stored


def differences(committed: dict, fresh: dict) -> list[str]:
    """Where a rerun disagrees with the committed artifact, leaf by leaf."""
    return sorted(_walk(committed, fresh, ""))


def _walk(was, now, path: str) -> list[str]:
    if isinstance(was, dict) and isinstance(now, dict):
        drifted = []
        for key in sorted(set(was) | set(now)):
            here = f"{path}.{key}" if path else key
            if key not in was:
                drifted.append(f"{here}: not in the committed artifact")
            elif key not in now:
                drifted.append(f"{here}: in the committed artifact, not in this run")
            else:
                drifted += _walk(was[key], now[key], here)
        return drifted
    if was != now:
        return [f"{path}: committed {was!r}, ran {now!r}"]
    return []
