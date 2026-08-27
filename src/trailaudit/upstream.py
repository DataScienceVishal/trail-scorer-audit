"""Everything that touches patronus-ai/trail-benchmark, pinned so it cannot move.

The audit's central claim is that a maximal predictor scores 1.000 through
TRAIL's *own* scorer. "Own" and "unmodified" are assertions unless somebody who
does not trust this repository can check them, so the pin is three separate
things and any of them failing stops the run:

    the commit SHA         the tree the line numbers in the README refer to
    the scorer's SHA-256   calculate_scores.py itself, byte for byte
    the corpus SHA-256     one rolled-up digest over every dataset JSON, so a
                           half-finished fetch or a locally edited trace is not
                           mistaken for the published dataset

Nothing from the clone is copied into this repository, including the 21-label
taxonomy, which `taxonomy()` reads back out of the pinned file's syntax tree
rather than restating here. That extractor is only ever pointed at bytes whose
digest has already been checked, which is what makes it safe to be as literal
as it is.

The clone lands in `.trail/`, which is gitignored. Licence position, checked at
the pinned commit on 2026-08-27: the repository carries an MIT LICENSE,
copyright 2025 patronus-ai, and the traces derive from GAIA and SWE-Bench Lite,
which carry their own terms. So the conservative reading is what this repository
acts on: fetch on demand, commit no trace bytes, and commit no gold labels.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPO = "https://github.com/patronus-ai/trail-benchmark.git"

# Read on 2026-08-27, and current `main` on that date. Every line number this
# project quotes is a line number in this tree.
PINNED_COMMIT = "0ffbed9db859b4a66250dc783fa4dccf86869595"

SCORER_SHA256 = "ed81ebd529da189425efb9c58183e7c1dcd55a234264ea039e03428bcc5f24d2"

# sha256 over the manifest text built by corpus_manifest(), not over the bytes
# themselves. One number to commit instead of one per file, and when it fails
# git is asked which paths moved rather than this repository carrying a table of
# hashes to diff against.
CORPUS_SHA256 = "e27721ffd74bef970daa02a91e9a2362d87dd8f956a2e4ec49cf5c8c088781e5"

DEFAULT_CLONE = Path(".trail/trail-benchmark")

SCORER = "benchmarking/calculate_scores.py"


@dataclass(frozen=True)
class Split:
    name: str
    traces: str
    annotations: str


SPLITS = (
    Split("GAIA", "benchmarking/data/GAIA", "benchmarking/processed_annotations_gaia"),
    Split(
        "SWE Bench",
        "benchmarking/data/SWE Bench",
        "benchmarking/processed_annotations_swe_bench",
    ),
)

# Order matters: the manifest is built from these in sequence, so the corpus
# digest depends on it.
CORPUS_DIRS = (
    "benchmarking/data",
    "benchmarking/processed_annotations_gaia",
    "benchmarking/processed_annotations_swe_bench",
)


class MissingClone(FileNotFoundError):
    """No clone where one was expected. `trailaudit fetch` writes it."""


class PinMismatch(ValueError):
    """What is on disk is not what the pin says it should be."""


def sha256_of(path: Path) -> str:
    running = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            running.update(chunk)
    return running.hexdigest()


def corpus_manifest(clone: Path) -> list[tuple[str, str]]:
    """Every dataset JSON under the pinned tree, as (path relative to the clone, digest).

    Sorted by POSIX path so the ordering does not depend on the filesystem's
    readdir order, which differs between macOS and the ubuntu-latest runner and
    would otherwise make the rolled-up digest machine-specific.
    """
    listed: list[tuple[str, str]] = []
    for directory in CORPUS_DIRS:
        here = clone / directory
        if not here.is_dir():
            raise MissingClone(f"{here} is not a directory. Run `trailaudit fetch` first")
        for path in sorted(here.rglob("*.json"), key=lambda p: p.relative_to(clone).as_posix()):
            listed.append((path.relative_to(clone).as_posix(), sha256_of(path)))
    return listed


def corpus_digest(clone: Path) -> str:
    text = "".join(f"{name}  {digest}\n" for name, digest in corpus_manifest(clone))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def corpus_size(clone: Path) -> tuple[int, int]:
    """(files, bytes) over the same paths the digest covers, by stat rather than by read.

    The README quotes the download size, and a size quoted from memory is the
    figure most likely to be wrong by the time anyone checks it. This walks the
    three corpus directories without opening anything, so it costs nothing next
    to the digest.
    """
    files = 0
    total = 0
    for directory in CORPUS_DIRS:
        here = clone / directory
        if not here.is_dir():
            raise MissingClone(f"{here} is not a directory. Run `trailaudit fetch` first")
        for path in here.rglob("*.json"):
            files += 1
            total += path.stat().st_size
    return files, total


def scorer_path(clone: Path) -> Path:
    return clone / SCORER


def head_commit(clone: Path) -> str:
    done = _git(clone, "rev-parse", "HEAD")
    if done.returncode != 0:
        raise PinMismatch(f"{clone} is not a git checkout: {done.stderr.strip()}")
    return done.stdout.strip()


def locally_modified(clone: Path) -> list[str]:
    """Paths git says differ from the checked-out commit.

    This is the answer to "which file broke the corpus digest", and it comes
    from git's object store rather than from a table of hashes committed here.
    Empty means the digest failed for some other reason, most likely that the
    checkout is not at the pinned commit.
    """
    done = _git(clone, "status", "--porcelain", "--untracked-files=all")
    if done.returncode != 0:
        return []
    return sorted(line[3:] for line in done.stdout.splitlines() if line)


def verify_scorer(clone: Path) -> str:
    """Check the one file the central claim rests on, and hand back its digest."""
    path = scorer_path(clone)
    if not path.is_file():
        raise MissingClone(f"no scorer at {path}. Run `trailaudit fetch` first")
    found = sha256_of(path)
    if found != SCORER_SHA256:
        raise PinMismatch(
            f"{path} hashes to {found}, not the pinned {SCORER_SHA256}. The audit reports "
            f"numbers produced by an unmodified {SCORER} and will not run against an edited "
            f"one. Delete {clone} and refetch, or move the pin if you meant to."
        )
    return found


def verify_corpus(clone: Path) -> str:
    found = corpus_digest(clone)
    if found != CORPUS_SHA256:
        changed = locally_modified(clone)
        named = ", ".join(changed[:5]) if changed else "git reports no modified paths"
        raise PinMismatch(
            f"the dataset under {clone} rolls up to {found}, not the pinned {CORPUS_SHA256}. "
            f"git says: {named}"
        )
    return found


def load_scorer(clone: Path) -> ModuleType:
    """Import benchmarking/calculate_scores.py by path, after checking its digest.

    Safe to import rather than shell out, which was the open question when this
    was specced: argparse sits behind an `if __name__ == "__main__"` guard at
    line 361, and `module_from_spec` sets `__name__` to the spec's name, so
    nothing parses sys.argv. What does run at module level is `import numpy`,
    `from sklearn.metrics import f1_score` and `from scipy.stats import
    pearsonr`, which is why those three are pinned dependencies of a project
    that calls none of them directly.
    """
    verify_scorer(clone)
    path = scorer_path(clone)
    spec = importlib.util.spec_from_file_location("trail_benchmark_calculate_scores", path)
    if spec is None or spec.loader is None:
        raise MissingClone(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def taxonomy(clone: Path) -> tuple[str, ...]:
    """The error categories, read out of the pinned file rather than restated here.

    `all_categories` is a local inside `main()` at lines 115 to 122, so it
    cannot be imported, and the two remaining options were to copy the list into
    this repository or to read it. Reading it means the labels this audit checks
    against are the labels the scorer uses, by construction, and it keeps
    upstream's taxonomy out of a repository that commits no upstream content.
    """
    verify_scorer(clone)
    tree = ast.parse(scorer_path(clone).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "all_categories" for t in node.targets):
            continue
        return tuple(ast.literal_eval(node.value))
    raise PinMismatch(f"no all_categories assignment in {scorer_path(clone)}")


def fetch(into: Path) -> None:
    """Fetch exactly the pinned commit, depth 1. The only thing here that opens a socket.

    Not `git clone`: cloning takes the branch and then has to be moved to the
    pin, which downloads history nobody reads and leaves a checkout that looks
    like it tracks upstream. Fetching the SHA directly means the pin is what
    goes over the wire, and a pin that has been rewritten out of the remote
    fails here rather than three commands later.
    """
    into.mkdir(parents=True, exist_ok=True)
    _checked(into, "init", "--quiet")
    _git(into, "remote", "remove", "origin")
    _checked(into, "remote", "add", "origin", REPO)
    _checked(into, "fetch", "--quiet", "--depth", "1", "origin", PINNED_COMMIT)
    _checked(into, "checkout", "--quiet", "--force", PINNED_COMMIT)


def _git(where: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(where), *argv], capture_output=True, text=True, check=False
    )


def _checked(where: Path, *argv: str) -> None:
    done = _git(where, *argv)
    if done.returncode != 0:
        raise PinMismatch(f"git {' '.join(argv)} failed in {where}: {done.stderr.strip()}")
