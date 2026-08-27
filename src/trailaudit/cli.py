from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from trailaudit import adversarial, artifacts, datacheck, normaliser, spans, upstream
from trailaudit.artifacts import Stale
from trailaudit.scoring import DiagnosticDrifted
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


def _data_check(args: argparse.Namespace) -> int:
    """A violated property exits 3, which is the good outcome here, and is why it is not 1.

    1 means the audit could not trust its input: the scorer has been edited, or
    the index does not describe the tree. 3 means the audit ran and a
    pre-registered property came back violated, which is the whole point of
    pointing it at somebody else's scorer. Folding the two into one integer
    would make "TRAIL has a trailing comma" and "your copy of TRAIL is not the
    pinned one" the same event to anything reading the code.

    There is deliberately no flag that turns a violation into 0. A flag that
    lets a caller choose the exit code is a flag that lets a caller make a
    finding disappear, and `|| true` already exists for anyone who wants that
    and is willing to write it down.
    """
    index = spans.load(args.index)
    clone = None if args.no_clone else args.into
    if clone is not None and not upstream.scorer_path(clone).is_file():
        print(
            f"trailaudit: no clone at {clone}, so P3 and P4 cannot be measured. "
            f"Run `trailaudit fetch`, or pass --no-clone to accept that.",
            file=sys.stderr,
        )
        return 2
    if clone is not None:
        upstream.verify_scorer(clone)

    lines, violated = datacheck.report(clone, index)
    print("\n".join(lines))
    return 3 if violated else 0


def _adversarial(args: argparse.Namespace) -> int:
    index = spans.load(args.index)
    if not upstream.scorer_path(args.into).is_file():
        print(
            f"trailaudit: no clone at {args.into}. The predictors are scored by TRAIL's own "
            f"calculate_scores.py against TRAIL's own gold, so both have to be on disk. "
            f"Run `trailaudit fetch`.",
            file=sys.stderr,
        )
        return 2
    upstream.verify_corpus(args.into)

    runs = adversarial.run(args.into, index)
    built = adversarial.artifact(runs)
    lines, violated = adversarial.report(runs)
    print("\n".join(lines))
    return _settle(args, built, adversarial.load, violated)


def _normaliser(args: argparse.Namespace) -> int:
    if not upstream.scorer_path(args.into).is_file():
        print(
            f"trailaudit: no clone at {args.into}. P5 and P6 are measured by asking TRAIL's "
            f"own normalize_category what it does with each string, so the file has to be on "
            f"disk. Run `trailaudit fetch`.",
            file=sys.stderr,
        )
        return 2
    upstream.verify_corpus(args.into)

    done = normaliser.study(args.into, spans.load(args.index))
    built = normaliser.artifact(done)
    lines, violated = normaliser.report(done)
    print("\n".join(lines))
    return _settle(args, built, normaliser.load, violated)


def _settle(
    args: argparse.Namespace,
    built: dict,
    load: Callable[[Path], dict],
    violated: bool,
) -> int:
    """Write the artifact, or under --check rerun and diff against it instead.

    The exit code carries the property verdict either way, so a `--check` run
    that reproduces a violation still exits 3. Only a figure that moved turns it
    into 1, because that is the case where the printed report and the committed
    artifact are two different claims.
    """
    if args.check:
        drifted = artifacts.differences(load(args.out), built)
        if drifted:
            print(f"\ntrailaudit: {args.out} and this run disagree:", file=sys.stderr)
            for line in drifted[:20]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"\n{args.out} matches this run")
        return 3 if violated else 0

    artifacts.write(args.out, built)
    print(f"\nwrote {args.out}")
    return 3 if violated else 0


def _already_pinned(clone: Path) -> bool:
    try:
        return upstream.head_commit(clone) == upstream.PINNED_COMMIT
    except PinMismatch:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trailaudit",
        description="Audit the scoring code behind the TRAIL agent-trace benchmark.",
        epilog="Exit codes: 0 nothing to report, 1 what is on disk does not match the pin, "
        "2 there is nothing on disk to check, 3 data-check found a pre-registered property "
        "violated. 3 is the good outcome and it is deliberately not 1: 1 says the audit could "
        "not trust its own input, 3 says the audit ran and TRAIL's scorer did the thing the "
        "property was written to catch.",
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

    check = commands.add_parser(
        "data-check",
        help="report P3, P4 and P9 against the pinned tree: what fails to parse, what the "
        "scorer actually loads, where the gold vocabulary has drifted, what the normaliser "
        "drops, and the split counts against the paper's Table 5",
    )
    check.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    check.add_argument(
        "--index",
        type=Path,
        default=spans.COMMITTED,
        help=f"the committed span index, which carries P9 on its own (default {spans.COMMITTED})",
    )
    check.add_argument(
        "--no-clone",
        action="store_true",
        help="report only what the committed index supports, and say that P3 and P4 were not "
        "measured rather than reporting them as held",
    )

    predictors = commands.add_parser(
        "adversarial",
        help="score six predictors through the pinned unmodified scorer and report P1 and P2: "
        "joint accuracy, location accuracy, and how many errors each one emitted per gold error",
    )
    predictors.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    predictors.add_argument(
        "--index",
        type=Path,
        default=spans.COMMITTED,
        help=f"the committed span index, which is the whole input to the predictor the claim "
        f"rests on (default {spans.COMMITTED})",
    )
    predictors.add_argument(
        "--out",
        type=Path,
        default=adversarial.COMMITTED,
        help=f"where the run artifact is written and read (default {adversarial.COMMITTED})",
    )
    predictors.add_argument(
        "--check",
        action="store_true",
        help="rerun and diff against the committed artifact instead of overwriting it. Exit 1 "
        "if any figure moved",
    )

    fallback = commands.add_parser(
        "normaliser",
        help="report P5 and P6 against the pinned normalize_category: every substring of every "
        "taxonomy label, the shortest string that reaches each of the 21, and where the gold "
        "spellings that are not labels end up",
    )
    fallback.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    fallback.add_argument(
        "--index",
        type=Path,
        default=spans.COMMITTED,
        help=f"the committed span index, which the shuffled rescore needs because it runs the "
        f"slice 2 predictors again (default {spans.COMMITTED})",
    )
    fallback.add_argument(
        "--out",
        type=Path,
        default=normaliser.COMMITTED,
        help=f"where the run artifact is written and read (default {normaliser.COMMITTED})",
    )
    fallback.add_argument(
        "--check",
        action="store_true",
        help="rerun and diff against the committed artifact instead of overwriting it. Exit 1 "
        "if any figure moved",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    routes = {
        "fetch": _fetch,
        "index": _index,
        "data-check": _data_check,
        "adversarial": _adversarial,
        "normaliser": _normaliser,
    }
    try:
        return routes[args.command](args)
    except (PinMismatch, IndexInconsistent, Stale, DiagnosticDrifted) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 1
    except (MissingClone, FileNotFoundError) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
