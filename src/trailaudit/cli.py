from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from trailaudit import (
    adversarial,
    artifacts,
    catf1,
    datacheck,
    normaliser,
    pairing,
    report,
    spans,
    upstream,
)
from trailaudit.artifacts import Stale
from trailaudit.report import MarkerError
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

    `--index` is the one flag that can still change a verdict, and saying it
    plainly is better than the sentence above pretending otherwise: an index of
    fabricated traces matching Table 5 makes P9 hold, and one built from the gold
    locations makes the gold-blind predictor an oracle. What stops that being
    invisible is provenance rather than a refusal. Every artifact records the
    sha256 of the index its run read, `trailaudit report --check` refuses one
    that is not the committed index, and each of these commands prints the
    digest it is working from.
    """
    if args.no_clone and args.check:
        print(
            "trailaudit: --no-clone cannot check results/datacheck.json. P3 and P4 are two "
            "thirds of what is in it and both need the gold annotations.",
            file=sys.stderr,
        )
        return 2

    index = spans.load(args.index)
    _announce_index(args.index, index)
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

    checked = datacheck.inspect(clone, index)
    lines, violated = datacheck.report(checked)
    print("\n".join(lines))
    if clone is None:
        print(f"\n{datacheck.COMMITTED} untouched: one of its three properties was measured")
        return 3 if violated else 0
    return _settle(
        args, datacheck.artifact(checked, spans.digest(index)), datacheck.load, violated
    )


def _adversarial(args: argparse.Namespace) -> int:
    if not upstream.scorer_path(args.into).is_file():
        print(
            f"trailaudit: no clone at {args.into}. The predictors are scored by TRAIL's own "
            f"calculate_scores.py against TRAIL's own gold, so both have to be on disk. "
            f"Run `trailaudit fetch`.",
            file=sys.stderr,
        )
        return 2
    upstream.verify_corpus(args.into)

    index = spans.load(args.index)
    _announce_index(args.index, index)
    runs = adversarial.run(args.into, index)
    built = adversarial.artifact(runs, spans.digest(index))
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

    index = spans.load(args.index)
    _announce_index(args.index, index)
    done = normaliser.study(args.into, index)
    built = normaliser.artifact(done, spans.digest(index))
    lines, violated = normaliser.report(done)
    print("\n".join(lines))
    return _settle(args, built, normaliser.load, violated)


def _catf1(args: argparse.Namespace) -> int:
    if not upstream.scorer_path(args.into).is_file():
        print(
            f"trailaudit: no clone at {args.into}. P7 is the per-category block that TRAIL's "
            f"own main() returns, so the scorer and the gold both have to be on disk. "
            f"Run `trailaudit fetch`.",
            file=sys.stderr,
        )
        return 2
    upstream.verify_corpus(args.into)

    index = spans.load(args.index)
    _announce_index(args.index, index)
    rows = catf1.run(args.into, index)
    built = catf1.artifact(rows, spans.digest(index))
    lines, violated = catf1.report(rows)
    print("\n".join(lines))
    return _settle(args, built, catf1.load, violated)


def _pairing(args: argparse.Namespace) -> int:
    if not upstream.scorer_path(args.into).is_file():
        print(
            f"trailaudit: no clone at {args.into}. The constructed trace is scored by TRAIL's "
            f"own calculate_scores.py, and the count of real gold files it would affect comes "
            f"from TRAIL's own gold. Run `trailaudit fetch`.",
            file=sys.stderr,
        )
        return 2
    upstream.verify_corpus(args.into)

    scored, counted = pairing.run(args.into)
    taxonomy = upstream.taxonomy(args.into)
    built = pairing.artifact(scored, counted, taxonomy)
    lines, violated = pairing.report(scored, counted, taxonomy)
    print("\n".join(lines))
    return _settle(args, built, pairing.load, violated)


def _announce_index(path: Path, index: dict[str, dict[str, list[str]]]) -> None:
    """Name the index a run read, since --index can point at any file on disk.

    The digest goes into the artifact as well. This line is for the case where
    no artifact is written, which is `data-check --no-clone`: without it a run
    against a fabricated index prints a page of findings and says nothing about
    where they came from.
    """
    print(f"span index {path}, sha256 {spans.digest(index)}\n")


def _report(args: argparse.Namespace) -> int:
    """Render every block in the README from the committed artifacts, or check that it matches.

    No clone and no network, so this is the one property of the finished
    repository that CI can actually enforce end to end. Everything else it runs
    is either offline consistency or a skip.
    """
    src = report.load(args.root)
    rendered = report.render(src)
    markdown = args.readme.read_text(encoding="utf-8")

    if args.check:
        moved = report.stale(markdown, rendered)
        loose = report.loose_scores(markdown)
        for name in moved:
            print(
                f"trailaudit: {args.readme} block {name} is not what the artifacts render",
                file=sys.stderr,
            )
        for line in loose:
            print(
                f"trailaudit: {args.readme} states a score outside every block, {line}",
                file=sys.stderr,
            )
        if moved or loose:
            print(
                f"rerun `trailaudit report --format {args.format}` and commit what it writes",
                file=sys.stderr,
            )
            return 1
        print(f"{args.readme}: {len(rendered)} blocks, all of them what the artifacts render")
        return 0

    rewritten = report.rewrite(markdown, rendered)
    moved = report.stale(markdown, rendered)
    if not moved:
        print(f"{args.readme} already matches the artifacts, {len(rendered)} blocks")
        return 0
    args.readme.write_text(rewritten, encoding="utf-8")
    print(f"rewrote {len(moved)} of {len(rendered)} blocks in {args.readme}")
    for name in moved:
        print(f"  {name}")
    return 0


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
        epilog="Exit codes: 0 nothing to report, 1 what is on disk does not match the pin or a "
        "committed artifact, 2 there is nothing on disk to check, 3 a pre-registered property "
        "came back violated. The nine are spread over data-check, adversarial, normaliser, "
        "catf1 and pairing, and each of those exits 3 on a violation. 3 is the good outcome and "
        "it is deliberately not 1: 1 says the audit could not trust its own input, 3 says the "
        "audit ran and TRAIL's scorer did the thing the property was written to catch.",
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
    check.add_argument(
        "--out",
        type=Path,
        default=datacheck.COMMITTED,
        help=f"where the run artifact is written and read (default {datacheck.COMMITTED})",
    )
    check.add_argument(
        "--check",
        action="store_true",
        help="rerun and diff against the committed artifact instead of overwriting it. Exit 1 "
        "if any figure moved",
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

    categories = commands.add_parser(
        "catf1",
        help="report P7: the per-category block for a predictor that names all 21 categories "
        "at one arbitrary span, against three that name them elsewhere",
    )
    categories.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    categories.add_argument(
        "--index",
        type=Path,
        default=spans.COMMITTED,
        help=f"the committed span index, which supplies the one span (default {spans.COMMITTED})",
    )
    categories.add_argument(
        "--out",
        type=Path,
        default=catf1.COMMITTED,
        help=f"where the run artifact is written and read (default {catf1.COMMITTED})",
    )
    categories.add_argument(
        "--check",
        action="store_true",
        help="rerun and diff against the committed artifact instead of overwriting it. Exit 1 "
        "if any figure moved",
    )

    zipped = commands.add_parser(
        "pairing",
        help="report P8: a constructed trace with one null category, scored by the pinned "
        "scorer, plus how many real gold files the defect would affect",
    )
    zipped.add_argument("--into", type=Path, default=DEFAULT_CLONE, help="where the clone is")
    zipped.add_argument(
        "--out",
        type=Path,
        default=pairing.COMMITTED,
        help=f"where the run artifact is written and read (default {pairing.COMMITTED})",
    )
    zipped.add_argument(
        "--check",
        action="store_true",
        help="rerun and diff against the committed artifact instead of overwriting it. Exit 1 "
        "if any figure moved",
    )

    rendered = commands.add_parser(
        "report",
        help="render every table and figure in the README out of the committed artifacts, "
        "between the HTML comment markers, so no number in the prose is typed by hand",
    )
    rendered.add_argument(
        "--format",
        choices=("md",),
        default="md",
        help="the only rendering there is. The blocks are markdown because the README is",
    )
    rendered.add_argument(
        "--readme", type=Path, default=report.README, help=f"which file (default {report.README})"
    )
    rendered.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="where results/ and index/ are read from (default the working directory)",
    )
    rendered.add_argument(
        "--check",
        action="store_true",
        help="compare instead of writing. Exit 1 if a block has drifted from the artifact that "
        "renders it, if a marker has no generator or a generator has no marker, or if a score "
        "appears in prose outside every block",
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
        "catf1": _catf1,
        "pairing": _pairing,
        "report": _report,
    }
    try:
        return routes[args.command](args)
    except (PinMismatch, IndexInconsistent, Stale, DiagnosticDrifted, MarkerError) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 1
    except (MissingClone, FileNotFoundError) as exc:
        print(f"trailaudit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
