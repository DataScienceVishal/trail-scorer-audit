from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trailaudit import spans, upstream
from trailaudit.spans import IndexInconsistent
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


def _index(args: argparse.Namespace) -> int:
    if args.check:
        committed = spans.load(args.out)
        fresh = spans.build(args.into)
        drifted = spans.differences(committed, fresh)
        if drifted:
            print(f"trailaudit: {args.out} and {args.into} disagree:", file=sys.stderr)
            for line in drifted[:20]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"{args.out} matches a fresh walk of {args.into}")
        _print_summary(committed)
        return 0

    upstream.verify_corpus(args.into)
    built = spans.build(args.into)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(spans.render(built), encoding="utf-8")
    print(f"wrote {args.out}")
    _print_summary(built)
    return 0


def _print_summary(by_split: dict[str, dict[str, list[str]]]) -> None:
    for name, counted in spans.summarise(by_split).items():
        repeated = counted["spans"] - counted["distinct_spans"]
        note = f", {repeated} identifier(s) repeated" if repeated else ""
        print(f"  {name:<10} {counted['traces']:>4} traces  {counted['spans']:>5} spans{note}")


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

    index = commands.add_parser(
        "index",
        help="walk every trace, extract span identifiers and nothing else, and write the "
        "committed index",
    )
    index.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    index.add_argument(
        "--out",
        type=Path,
        default=spans.COMMITTED,
        help=f"where the index is written and read (default {spans.COMMITTED})",
    )
    index.add_argument(
        "--check",
        action="store_true",
        help="rebuild from the clone and diff against the committed index instead of "
        "overwriting it. Exit 1 if they disagree",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    routes = {"fetch": _fetch, "index": _index}
    try:
        return routes[args.command](args)
    except (PinMismatch, IndexInconsistent) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 1
    except (MissingClone, FileNotFoundError) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
