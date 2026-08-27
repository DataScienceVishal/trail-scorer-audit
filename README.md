# trail-scorer-audit

[![ci](https://github.com/DataScienceVishal/trail-scorer-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/DataScienceVishal/trail-scorer-audit/actions/workflows/ci.yml)

TRAIL is a benchmark of human-annotated agent execution traces from Patronus AI,
published under MIT, with a leaderboard on which the best model reaches 11
percent. This repository audits the code that produces that number.

It is possible at all because the authors published the scorer, the gold labels
and the traces. Most benchmarks ship a leaderboard and keep the scoring code,
and those cannot be audited from outside at all. Nothing here is copied or
edited: `benchmarking/calculate_scores.py` is fetched at a pinned commit,
checked against a SHA-256 recorded below, and imported by path.

Nine properties were written down before any code existed, each one a thing a
competent benchmark scorer should have. Slice 1 measures three of them. All
three come back violated.

```
$ trailaudit data-check
P3  every gold annotation file parses as JSON                             VIOLATED
    148 files on disk, 147 parse, 1 does not
    GAIA/a96c6811716c0473b86a23321db79c34.json: ',' at line 38 column 10
    the scorer catches that at line 242 and continues, so every published average divides by 147

P4  every gold category string is one of the taxonomy labels              VIOLATED
    31 distinct spellings over 836 errors, against 21 labels
    11 are not a label, covering 19 errors

P9  the repository's split sizes match the paper's Table 5                VIOLATED
    arXiv:2505.08638v3, Table 5, page 16, against the tree at 0ffbed9db859
                                              GAIA               SWE Bench
                                      paper / here            paper / here
    total traces                         118 / 117                 31 / 31
    total spans                        977 / 3,579           1,010 / 1,047
    total errors                         579 / 580               256 / 256
    unique error spans                   383 / 384               192 / 191
    traces with an error                 115 / 113                 31 / 30
```

## The headline

The paper reports 148 traces and 841 annotated errors. The scorer reads 147 of
them and 836 errors, because
`processed_annotations_gaia/a96c6811716c0473b86a23321db79c34.json` has a comma
at line 38 that should not be there, `json.load` refuses it, and the loading
call sits inside a `try` at line 157 whose `except Exception` at line 242 prints
a message and continues. Every average TRAIL publishes divides by
`files_processed`, which is 147.

Five annotated errors live in that file. 836 plus 5 is 841, which is the number
in the paper's abstract, so the skipped file is exactly the gap between what was
annotated and what is scored.

That is a small defect with a large tell attached to it: the failure is written
to stdout, once, in the middle of a run that also prints a per-category table,
and nothing downstream of it knows the corpus shrank.

## What the other two found

The gold labels use 31 distinct category strings against a 21-label taxonomy.
Most of the drift is harmless and the scorer's normaliser absorbs it:
`Context Handling Failure` reaches `Context Handling Failures`, and
`" Incorrect Problem Identification"`, with a leading space, strips back onto
its label. Four errors do not make it. `Task Orchestration Errors` twice,
`Task Orchestration Error` once and `Instruction non complience` once come out
of the normaliser lowercased and unmatched.

A dropped label is not discarded, which is the part worth knowing. It keeps its
place in `gt_loc_cat_pairs`, so it stays in the joint accuracy denominator under
a spelling no correctly-labelled prediction can match, and it never sets a bit
in the per-category vectors at lines 64 to 66, which are guarded by
`if cat in all_categories`.

Table 5 of the paper counts 118 GAIA traces. The repository at the pinned commit
has 117, and 117 gold annotation files to go with them. SWE Bench matches at 31.
The paper's own prose says 148 traces and 841 errors while Table 5's rows sum to
149 and 835, so the artifact and the paper describe slightly different datasets
and a reader cannot tell from either which one the leaderboard was computed
over.

The span counts are the widest gap and the one I am least able to explain.
Walking `span_id` recursively through `child_spans` gives 3,579 spans across the
117 GAIA traces. Table 5 says 977. Neither the root-level count nor any depth
prefix of the trees lands on 977, and I do not know what definition would. The
row is printed because leaving it out would be choosing which disagreements to
show.

## Running it

```bash
git clone https://github.com/DataScienceVishal/trail-scorer-audit.git
cd trail-scorer-audit
uv sync --all-extras
./scripts/install-hooks.sh
```

`data-check` works straight away on the committed span index, and says so about
the parts it cannot see:

```bash
uv run trailaudit data-check --no-clone
```

For the full report, fetch the benchmark. It is a 186 MB download and it lands
in `.trail/`, which is gitignored:

```bash
uv run trailaudit fetch
uv run trailaudit data-check
```

`fetch` on its own verifies three things and refuses to go on if any of them
fails: that `HEAD` is `0ffbed9db859b4a66250dc783fa4dccf86869595`, that
`benchmarking/calculate_scores.py` hashes to
`ed81ebd529da189425efb9c58183e7c1dcd55a234264ea039e03428bcc5f24d2`, and that
every dataset JSON in the tree rolls up to
`e27721ffd74bef970daa02a91e9a2362d87dd8f956a2e4ec49cf5c8c088781e5`. Append one
comment line to the scorer and `trailaudit fetch --check` goes from exit 0 to
exit 1. That is the whole of what "their unmodified scorer" means here, and it
is checkable by someone who does not believe it.

Exit codes: 0 nothing to report, 1 what is on disk does not match the pin, 2
there is nothing on disk to check, 3 a pre-registered property came back
violated. 3 is the good outcome and it is deliberately not 1, because 1 means
the audit could not trust its own input.

The test suite needs no credentials, no network and no download:

```bash
uv run pytest
```

`pytest-socket` runs with `--disable-socket` in `addopts`, so a stray network
call is a test failure rather than a slow test. The checks that genuinely need
the 186 MB skip with a message naming the command that would include them.

## How it works

Six modules, and two of them carry the idea.

`upstream.py` owns everything that touches somebody else's repository: the
pinned commit, the two digests, the fetch, and the import of
`calculate_scores.py` by path. It also reads the 21 taxonomy labels out of that
file's syntax tree rather than restating them, because `all_categories` is a
local inside `main()` at lines 115 to 122 and cannot be imported. Reading it
means the labels this audit checks against are the labels the scorer uses, by
construction, and it keeps upstream's taxonomy out of a repository that commits
no upstream content.

`spans.py` builds the one derived artifact that is committed, `index/spans.json`:
trace identifier to span identifier list, hex and integers, no trace content.
The walk is recursive because the span tree hangs off `child_spans`; the
top-level `spans` list holds one entry per GAIA trace, so a count taken from it
comes out at roughly one span per trace and looks plausible.

`gold.py` reads the annotations, `paper.py` holds Table 5 as transcribed, and
`datacheck.py` turns the three into the report above. `cli.py` is argparse.

One detail in `gold.py` is worth pointing at, because it nearly put a wrong
number in this file. The position of the trailing comma depends on the
interpreter: CPython 3.12 raises `Expecting value` at line 39 column 5 and
CPython 3.13 raises `Illegal trailing comma before end of array` at line 38
column 10, over identical bytes. `culprit()` walks from whichever position the
decoder gave to the comma both are pointing at, so the published position is
line 38 column 10 on either, and the decoder's own wording is carried alongside
without being the number anyone quotes.

## What this does not do

This is slice 1 of four. The adversarial predictors, the normaliser study and
the generated results tables are not written yet, and the six remaining
properties are not measured. In particular the central claim, that a predictor
naming every span crossed with every category scores 1.000 through this same
unmodified scorer, is slice 2's and is not in this repository yet.

It does not re-score the leaderboard. TRAIL publishes no raw model outputs and
there is no `results/` directory in the benchmark repository, so there is
nothing to re-score.

It says nothing about whether TRAIL's human annotators marked the right errors.
That is a real question and answering it needs annotators. This tests the scorer
against the labels as given.

There is no proposed replacement metric and no corrected scorer. Auditing one
benchmark is the project, and a replacement would convert a measurement anyone
can check into an opinion nobody can.

## Data and licence

`github.com/patronus-ai/trail-benchmark` at commit
`0ffbed9db859b4a66250dc783fa4dccf86869595`, which carries an MIT LICENSE,
copyright 2025 patronus-ai, read at that commit on 2026-08-27.

Not the HuggingFace dataset. `PatronusAI/TRAIL` on the Hub is gated and its
terms ask that it not be reshared outside a gated or private repository. The
same authors publish the same data ungated under MIT on GitHub, so that is what
this uses.

Nothing from `benchmarking/data/` is committed. The traces run from 96 KB to
9.04 MB and total 185.6 MB, and they derive from GAIA and SWE-Bench Lite, which
carry their own terms. The conservative reading is the one this repository acts
on: fetch on demand against a recorded digest, commit no trace bytes, and commit
no gold labels either.

The one exception is `index/spans.json`, which is identifiers and integers. It
is what lets `data-check --no-clone` run P9 on a fresh clone in under a second,
and redistributing a list of hex strings raises no question that needs
answering.

The test fixtures in `tests/fixtures/annotations/` are hand-built and synthetic,
and none of them comes from TRAIL. They are shaped like the real annotation
files and constructed for the behaviours under test: one that parses, one whose
categories have drifted in the four ways the real gold drifts, and one with a
trailing comma. A real file that happens to be malformed makes a worse fixture
than a file built to be.

Paper: Deshpande et al., *TRAIL: Trace Reasoning and Agentic Issue
Localization*, arXiv:2505.08638.
