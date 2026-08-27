from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trailaudit import upstream
from trailaudit.upstream import DEFAULT_CLONE, MissingClone, PinMismatch


def _fetch(args: argparse.Namespace) -> int:
    clone: Path = args.into
    if not args.check:
        if (clone / ".git").is_dir() and _already_pinned(clone):
            print(f"{clone} is already at {upstream.PINNED_COMMIT[:12]}, verifying instead")
        else:
            print(f"fetching {upstream.REPO} at {upstream.PINNED_COMMIT} into {clone}", flush=True)
            upstream.fetch(clone)

    if not clone.is_dir():
        print(f"trailaudit: no clone at {clone}. Run `trailaudit fetch`", file=sys.stderr)
        return 2

    head = upstream.head_commit(clone)
    if head != upstream.PINNED_COMMIT:
        print(
            f"trailaudit: {clone} is at {head}, not the pinned {upstream.PINNED_COMMIT}",
            file=sys.stderr,
        )
        return 1
    print(f"  commit  {head}")
    print(f"  scorer  {upstream.verify_scorer(clone)}  {upstream.SCORER}")
    corpus = upstream.verify_corpus(clone)
    print(f"  corpus  {corpus}  over {len(upstream.CORPUS_DIRS)} directories")
    labels = upstream.taxonomy(clone)
    print(f"  taxonomy read from the pinned file: {len(labels)} categories")
    return 0


def _already_pinned(clone: Path) -> bool:
    try:
        return upstream.head_commit(clone) == upstream.PINNED_COMMIT
    except PinMismatch:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trailaudit",
        description="Audit the scoring code behind the TRAIL agent-trace benchmark.",
        epilog="Exit codes: 0 the check passed, 1 what is on disk does not match the pin, "
        "2 there is nothing on disk to check.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser(
        "fetch",
        help="fetch patronus-ai/trail-benchmark at the pinned commit and verify its digests",
    )
    fetch.add_argument(
        "--into",
        type=Path,
        default=DEFAULT_CLONE,
        help=f"where the clone lands, gitignored (default {DEFAULT_CLONE})",
    )
    fetch.add_argument(
        "--check",
        action="store_true",
        help="verify what is already on disk and fetch nothing. This is the offline half, "
        "and it is what a reader runs to confirm the audit ran against an unedited scorer",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch":
            return _fetch(args)
    except PinMismatch as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 1
    except MissingClone as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unrouted subcommand {args.command!r}")


if __name__ == "__main__":
    sys.exit(main())
