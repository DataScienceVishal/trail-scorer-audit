# trail-scorer-audit

[![ci](https://github.com/DataScienceVishal/trail-scorer-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/DataScienceVishal/trail-scorer-audit/actions/workflows/ci.yml)

TRAIL is a benchmark of human-annotated agent execution traces from Patronus AI,
published under MIT. Its abstract reports the best model scoring 11 percent.
This repository audits the code that produces the numbers behind that.

A program that cannot read scores higher than every model in their Table 1.

<!-- trailaudit:claim -->
`all-spans-all-categories` never opens a span, never looks at the gold and does
not know what an error is. Run through TRAIL's own unmodified scorer on GAIA it
scores **0.973** joint accuracy against **0.183** for the best row in Table 1,
by emitting **129.1x** as many errors as the answer key holds. Both headline
metrics divide by the number of errors in the answer key, never by the number
the judge reported.
<!-- /trailaudit:claim -->

<!-- trailaudit:teaser -->
| GAIA, 116 gold files, 580 gold errors | joint | location | errors emitted | per gold error |
|---|---|---|---|---|
| `all-spans-all-categories`, which cannot read | 0.973 | 0.974 | 74,865 | 129.1x |
| best published, Table 1 | 0.183 | 0.546 |  |  |
| reachable by anything at all | 0.974 | 0.974 |  |  |
<!-- /trailaudit:teaser -->

Every figure in this file was measured on a machine with the corpus on disk and
committed as an artifact. CI never fetches it, so the badge covers the code and
not the numbers.

The audit is possible at all because the TRAIL authors published the scorer, the
gold labels and the traces. A benchmark that publishes a table of model scores
and keeps its scoring code to itself cannot be audited from outside.

```bash
git clone https://github.com/DataScienceVishal/trail-scorer-audit.git
cd trail-scorer-audit && uv sync --all-extras && uv run trailaudit report --check
```

## The nine pre-registered properties

Each one is a property a competent benchmark scorer should have, fixed in the
spec before the repository existed. Six had a known direction from a first-hand
read of the scorer; what pre-registration buys is the magnitude and the
contingency, not the direction. P2, P5 and P6 were open in direction as well.

<!-- trailaudit:conditions -->
| property | as written before any code existed | verdict | how far off it is |
|---|---|---|---|
| P1 | all-spans-all-categories scores no better than a published judge | VIOLATED | the gold-blind predictor beats the best published row: GAIA joint 0.973 against 0.183, location 0.974 against 0.546; SWE Bench joint 0.958 against 0.050, location 0.961 against 0.238 |
| P2 | every gold error location is a span identifier in its own trace | VIOLATED | 2 of 836 gold locations are not a span in the trace they annotate. All of them are the literal 'Span ID not found for this shard' |
| P3 | every gold annotation file parses as JSON | VIOLATED | 147 of 148 gold files parse, so every published average divides by 147 |
| P4 | every gold category string is one of the taxonomy labels | VIOLATED | 11 of 31 gold spellings are not a label, covering 19 of 836 errors |
| P5 | the normaliser's output depends on its input alone, not on the taxonomy order | LATENT | 237 of 3,205 strings change label under a shuffled taxonomy, 115 of them under seed 20260827, and 0 of the 24 figures the adversarial run publishes move as a result |
| P6 | no string shorter than the shortest taxonomy label normalises to a taxonomy label | VIOLATED | the shortest label is 12 characters and every one of the 21 is reached by 2 characters or fewer, 8 of them by one |
| P7 | per-category F1 separates naming a category at the right span from naming it anywhere | VIOLATED | GAIA scores the same 21 columns for a predictor at 0.974 location accuracy and one at 0.000; SWE Bench scores the same 21 columns for a predictor at 0.961 location accuracy and one at 0.000 |
| P8 | the scorer pairs each predicted location with the category predicted for it | LATENT | one null category takes a correct judge from 1.000 joint to 0.000 on the constructed trace, and 0 of 836 real gold errors carry one |
| P9 | the repository's split sizes match the paper's Table 5 | VIOLATED | 8 of the 10 Table 5 cells this repository can compare disagree with the tree at 0ffbed9db859 |
<!-- /trailaudit:conditions -->

<details>
<summary>A pre-registration where a clean sweep would have meant nothing to publish</summary>

The section of the spec that fixed them is committed as
[docs/pre-registration.md](docs/pre-registration.md), verbatim apart from one
declared edit, with its own note on what a reader can check from inside this
repository and what they cannot.

Note the inversion, because it is what makes a pre-registration worth less than
it looks if nobody says it: here the object under test is somebody else's code,
so a violation is a result and a clean sweep would have meant there was nothing
to publish. Naming the nine in advance is what stops the target moving, not what
makes the outcome surprising.

Two verdicts, and the difference between them is the point. VIOLATED means the
property fails and a number somebody published moves because of it. LATENT means
the property fails and nothing on this data moves: rescoring every predictor
under a shuffled taxonomy leaves all 24 of P5's figures where they were, and no
gold error in either split carries the null category P8 turns on. Both still
exit 3, because the pre-registration asked about the scorer rather than about
how lucky the data is. What each latent verdict rests on is worked out in the P5
fold on the shuffled taxonomy and the P8 fold on the null category.

</details>

<details>
<summary>How can that be true? The full table, both splits</summary>

Nothing here is copied or edited: `benchmarking/calculate_scores.py` is fetched
at a pinned commit, checked against a SHA-256, run by compiling those same
bytes, and left alone.

Six predictors go through it here, and a seventh, `one-span-all-categories`, is
scored in the fold on category F1, which is where P7 needs it. The one the claim
rests on is `all-spans-all-categories`, and its entire input is that trace's
entry in `index/spans.json`: a list of hex identifiers with no contents
attached. It is a loop over the cross product of those identifiers and the
labels in the taxonomy. The predictors that read the gold are there as reference
points. `gold-exact` is a perfect judge, `gold-spans-all-categories` is what
oracle knowledge of the locations buys, and `silent` emits nothing.

`joint` and `location` are TRAIL's two headline metrics, computed by their code
at lines 54 and 58 of `calculate_scores.py`. Both divide the intersection by the
gold count. There is a precision term at line 312, it belongs to a per-category
metric, and it reaches neither headline number.

The comparison row in both tables below is Table 1's best, per split, and that
needs one paragraph because the paper states its headline three ways:

<!-- trailaudit:eleven-percent -->
The 11% is the abstract's, and it is not a cell in Table 1. Table 1's best
joint accuracy is 0.183 on GAIA, 0.050 on SWE Bench, which the paper's
conclusion quotes rounded, at 18% and 5%. The plain mean of the two is 11.6%,
which rounds to 12% and reaches 11% only by truncation, and weighting the
splits moves it further off rather than closer: by the gold files the scorer
loads it is 15.5%, by the errors in those files 14.2%. calculate_scores.main()
is called once per split and returns one number per split, so that is the
granularity this audit compares at, per split against the two cells above.
<!-- /trailaudit:eleven-percent -->

<!-- trailaudit:headline -->
GAIA, 116 of 117 gold files scored, 580 gold errors in them:

| predictor | reads | joint | location | errors emitted | per gold error |
|---|---|---|---|---|---|
| `silent` | spans | 0.000 | 0.000 | 0 | 0.0x |
| `gold-exact` | gold | 0.974 | 0.974 | 580 | 1.0x |
| `gold-mispaired` | gold | 0.553 | 0.974 | 580 | 1.0x |
| `every-span-once` | spans | 0.088 | 0.974 | 3,565 | 6.1x |
| `gold-spans-all-categories` | gold | 0.973 | 0.974 | 8,064 | 13.9x |
| `all-spans-all-categories` | spans | 0.973 | 0.974 | 74,865 | 129.1x |
| best published, Table 1 |  | 0.183 | 0.546 |  |  |
| reachable by anything at all |  | 0.974 | 0.974 |  |  |

SWE Bench, 31 of 31 gold files scored, 256 gold errors in them:

| predictor | reads | joint | location | errors emitted | per gold error |
|---|---|---|---|---|---|
| `silent` | spans | 0.000 | 0.000 | 0 | 0.0x |
| `gold-exact` | gold | 0.968 | 0.968 | 256 | 1.0x |
| `gold-mispaired` | gold | 0.538 | 0.968 | 256 | 1.0x |
| `every-span-once` | spans | 0.040 | 0.961 | 1,046 | 4.1x |
| `gold-spans-all-categories` | gold | 0.960 | 0.968 | 4,032 | 15.8x |
| `all-spans-all-categories` | spans | 0.958 | 0.961 | 21,966 | 85.8x |
| best published, Table 1 |  | 0.050 | 0.238 |  |  |
| reachable by anything at all |  | 0.968 | 0.968 |  |  |
<!-- /trailaudit:headline -->

</details>

<details>
<summary>Of course a maximal predictor maxes a recall metric</summary>

The `per gold error` column of the two headline tables is what the score costs,
and it is the answer to that objection. Of course a maximal predictor maxes a
recall metric. That is the finding rather than a rebuttal to it: nothing in
Table 1, and nothing in either metric's name, tells a reader that a model
emitting more errors scores at least as well for that reason alone. Nor does the
order matter: lines 53 and 57 intersect sets, so shuffling the errors a judge
reports changes neither figure.

<!-- trailaudit:ceiling -->
Nothing in either table reaches 1.000, and the row holding the answer key does
not either. A trace whose gold carries no error scores 0 at lines 54 and 58 for
every predictor, a perfect one included, and the average divides by the file
count anyway. So the ceiling is the share of traces that carry an error, 113 of
the 116 scored traces on GAIA, 30 of the 31 scored traces on SWE Bench, which
is 0.974 and 0.968.
<!-- /trailaudit:ceiling -->

<!-- trailaudit:absent-locations -->
The gold-blind predictor sits a little under the oracle one on SWE Bench, and
the reason is P2: 2 gold errors give their location as a string that no trace
contains, `Span ID not found for this shard`, so a predictor working from span
identifiers cannot reach them and an oracle working from the gold can.
<!-- /trailaudit:absent-locations -->

Dividing the same intersections by the prediction count instead of the gold
count gives the column the metric does not report. This is a diagnostic and not
a proposed metric. The audit computes it, TRAIL does not, and the run refuses to
finish unless its own recall figures reproduce the ones `calculate_scores.py`
returned. That check anchors the pair building and the intersection, which both
directions share, and not the final division: upstream computes no precision, so
there is nothing there to reproduce.

<!-- trailaudit:precision -->
| predictor | GAIA, joint / location | SWE Bench, joint / location |
|---|---|---|
| `silent` | 0.000 / 0.000 | 0.000 / 0.000 |
| `gold-exact` | 0.974 / 0.974 | 0.968 / 0.968 |
| `gold-mispaired` | 0.559 / 0.974 | 0.555 / 0.968 |
| `every-span-once` | 0.023 / 0.130 | 0.014 / 0.191 |
| `gold-spans-all-categories` | 0.083 / 0.974 | 0.062 / 0.968 |
| `all-spans-all-categories` | 0.011 / 0.130 | 0.013 / 0.191 |
<!-- /trailaudit:precision -->

</details>

## The rest of the table, up close

<details>
<summary>One trailing comma keeps a gold file out of every published average</summary>

<!-- trailaudit:unreadable-gold -->
147 of the 148 gold annotation files parse. What stops the rest is a trailing
comma: `json.load` refuses the file, the call sits inside a `try` at line 157
whose `except Exception` at line 242 prints a message and continues, and every
average TRAIL publishes divides by `files_processed`, which is 147. The errors
annotated in the file that did not parse are exactly the gap between the count
in the paper's abstract and the count the scorer sees.
<!-- /trailaudit:unreadable-gold -->

That is a small defect with a large tell attached: the failure goes to stdout,
once, in the middle of a run that also prints a per-category table, and nothing
downstream of it knows the corpus shrank.

</details>

<details>
<summary>Gold labels that miss the taxonomy, and the fallback that catches them</summary>

The gold category strings and the taxonomy have drifted apart. Most of the drift
is absorbed on the way through the normaliser, and the `loop` column says which
of its two loops caught each one.

<!-- trailaudit:drift -->
```
' Incorrect Problem Identification'  x1      exact  Incorrect Problem Identification
'Context Handling Failure'           x5   fallback  Context Handling Failures
'Formatting Error'                   x1   fallback  Formatting Errors
'Goal deviation'                     x1      exact  Goal Deviation
'Instruction Non-Compliance'         x2      exact  Instruction Non-compliance
'Instruction non complience'         x1    neither  kept as 'instruction non complience'
'Language-Only'                      x3      exact  Language-only
'Poor Information retrieval'         x1      exact  Poor Information Retrieval
'Task Orchestration Error'           x1    neither  kept as 'task orchestration error'
'Task Orchestration Errors'          x2    neither  kept as 'task orchestration errors'
'Tool Selection'                     x1   fallback  Tool Selection Errors
```
<!-- /trailaudit:drift -->

A dropped label is not discarded, which is the part worth knowing. It keeps its
place in `gt_loc_cat_pairs` under its lowercased spelling, so it stays in the
joint accuracy denominator where no correctly-labelled prediction can match it,
and it never sets a bit in the per-category vectors at lines 64 to 66, which are
guarded by `if cat in all_categories`.

The second loop is the one worth looking at. It asks whether the judge's string
sits inside a taxonomy label, never the reverse:

```python
for std_cat in all_categories:
    if category_no_spaces in std_cat.lower().replace(" ", ""):
        return std_cat
```

<!-- trailaudit:containment -->
Containment in that direction promotes a string vaguer than a label and drops
one more specific than a label. Both are already in TRAIL's own gold. `Tool
Selection` is rescued onto `Tool Selection Errors`, while `Task Orchestration
Errors` reaches nothing at all, because `Task Orchestration` is a label and the
gold spelling is that label plus a suffix. Enumerating every substring of every
label and putting each one back through the pinned `normalize_category` gives
the size of it:
<!-- /trailaudit:containment -->

<!-- trailaudit:fallback -->
The shortest of the 21 labels is 12 characters once its spaces are removed.
Every one of them is reached by a string of 2 characters or fewer, and 8 by a
single character, out of the 3,205 distinct substrings the 21 labels have
between them.

```
'error'     ->  Tool Selection Errors
'resource'  ->  Resource Not Found
'tool'      ->  Tool-related
' '         ->  Language-only
```
<!-- /trailaudit:fallback -->

A category of one space gets past the empty-string guard at line 14, because
line 14 tests the argument before line 17 strips it, and then matches the first
label in the list.

</details>

<details>
<summary>An order dependence that costs nothing today</summary>

<!-- trailaudit:shuffle -->
237 of the 3,205 substrings the 21 taxonomy labels contain sit inside more than
one of those labels, so list position decides which one they get, and 115 of
them land somewhere else once the taxonomy is reordered under seed 20260827. Of
the 31 spellings TRAIL's gold actually uses, 0 are ambiguous, so rescoring
every predictor on both splits under the shuffled order moved 0 of the 24
figures it produces.
<!-- /trailaudit:shuffle -->

So P5 is violated as a property of the function and the consequence it was
written to catch does not follow. Two people scoring the same data today do not
get different numbers. `all_categories` is a literal inside `main()` at line 115,
so nobody running `calculate_scores.py` gets a different order by accident, and
none of the gold spellings is ambiguous enough for the order to reach it. The
exposure is `calculate_metrics` and `normalize_category` themselves, which are
importable, take the list as a parameter, and are the part of that file another
project would reuse.

Reported as latent rather than quietly downgraded to held, because the
pre-registration asked whether the output depends on its input alone and the
answer is that it does not. Latent is a violation whose cost on this corpus is
zero, and the row says so in both columns rather than in neither.

</details>

<details>
<summary>Category F1 never looks at where the error is</summary>

The third column of the paper's Table 1 is built from two binary vectors per
trace at lines 61 to 70, one bit per label. A location never reaches those
lines. So a judge naming every category somewhere in a trace sets every bit of
`y_pred`, whatever it thinks the errors are attached to.

Two predictors make that concrete. Both name every label in every trace, and
they differ only in where: one puts them on every span, the other puts all of
them on the first span identifier in the file and nowhere else.

<!-- trailaudit:per-category -->
| split | predictor | joint | location | weighted F1 | columns at recall 1.000 |
|---|---|---|---|---|---|
| GAIA | `gold-exact` | 0.974 | 0.974 | 1.0000 | 19 of 19 with support |
| GAIA | `gold-spans-all-categories` | 0.973 | 0.974 | 0.4817 | 19 of 19 with support |
| GAIA | `all-spans-all-categories` | 0.973 | 0.974 | 0.4725 | 19 of 19 with support |
| GAIA | `one-span-all-categories` | 0.000 | 0.000 | 0.4725 | 19 of 19 with support |
| SWE Bench | `gold-exact` | 0.968 | 0.968 | 1.0000 | 13 of 13 with support |
| SWE Bench | `gold-spans-all-categories` | 0.960 | 0.968 | 0.7205 | 13 of 13 with support |
| SWE Bench | `all-spans-all-categories` | 0.958 | 0.961 | 0.7066 | 13 of 13 with support |
| SWE Bench | `one-span-all-categories` | 0.000 | 0.000 | 0.7066 | 13 of 13 with support |
<!-- /trailaudit:per-category -->

The per-category block is identical for the pair, column for column, at a
location accuracy of zero against a location accuracy that is nearly perfect.
`gold-spans-all-categories` is the row that does move, and it moves for the
wrong reason: it is the only one that stays silent in a trace whose gold carries
no error, so it sets fewer bits and picks up fewer false positives. That is a
difference in how much it says, not in where.

</details>

<details>
<summary>One null category, and a correct judge scoring zero</summary>

Lines 45 and 49 build the pairs both headline metrics are computed from. The
categories are filtered on truthiness, the locations are not, and then the two
lists are zipped by position:

```python
gt_categories = [normalize_category(cat, all_categories)
                 for cat in gt_categories_raw if cat]
gt_loc_cat_pairs = [(gt_locations[i], gt_categories[i])
                    for i in range(len(gt_locations)) if i < len(gt_categories)]
```

One error carrying a null category shortens the category list by one, and every
category after it slides onto the location belonging to the error before. Lines
46 and 50 do the same to the judge's output, so a judge that names both real
spans, gets both categories right, and mentions one further span with no
category has all of its correct answers land on the wrong span.

<!-- trailaudit:null-category -->
| the same two real errors, scored three ways | joint | location |
|---|---|---|
| gold carries a null first, prediction correct | 0.000 | 0.667 |
| both clean, which is the control | 1.000 | 1.000 |
| gold clean, prediction carries a null first | 0.000 | 1.000 |

Of the 836 real gold errors, 0 carry a category that is null or empty, so 0
files mispair and 0 lose a pair. No published number moves because of this one.
<!-- /trailaudit:null-category -->

The trace those three runs score is constructed and belongs to this repository,
not to TRAIL. It is demonstrated rather than found because it is latent: this is
a defect in the scorer, not a correction to the published numbers.

</details>

<details>
<summary>The paper and the repository describe different datasets</summary>

Table 5 of the paper counts the corpus five ways per split. The tree at the
pinned commit disagrees with most of them, and the paper's own prose disagrees
with Table 5: the abstract's trace and error counts are not what Table 5's rows
sum to.

<!-- trailaudit:table-5 -->
| Table 5 | GAIA, paper | GAIA, here | SWE Bench, paper | SWE Bench, here |
|---|---|---|---|---|
| total traces | 118 | 117 | 31 | 31 |
| total spans | 977 | 3,579 | 1,010 | 1,047 |
| total errors | 579 | 580 | 256 | 256 |
| unique error spans | 383 | 384 | 192 | 191 |
| traces with an error | 115 | 113 | 31 | 30 |
<!-- /trailaudit:table-5 -->

The last three rows are counted over the gold files that parse, so GAIA's leave
out the errors in the file that does not. The span row is the widest gap and the
one I am least able to explain. Walking `span_id` recursively through
`child_spans` gives the count on the right. Neither the root-level count nor any
depth prefix of the trees lands on the published one, and I do not know what
definition would. The row is printed because leaving it out would be choosing
which disagreements to show.

</details>

## Running it, and reading the code

<details>
<summary>How to run it</summary>

<!-- trailaudit:pin -->
```
commit  0ffbed9db859b4a66250dc783fa4dccf86869595
scorer  ed81ebd529da189425efb9c58183e7c1dcd55a234264ea039e03428bcc5f24d2  benchmarking/calculate_scores.py
corpus  e27721ffd74bef970daa02a91e9a2362d87dd8f956a2e4ec49cf5c8c088781e5  296 files, 186.4 MB
index   4370086c255bdc6bc90a0af032ef68f72a23bc2c362234058c7d82258a52b928  index/spans.json
```
<!-- /trailaudit:pin -->

```bash
git clone https://github.com/DataScienceVishal/trail-scorer-audit.git
cd trail-scorer-audit
uv sync --all-extras
./scripts/install-hooks.sh
```

Two things work immediately on a fresh clone, because they read committed
artifacts and nothing else:

```bash
uv run trailaudit report --format md --check
uv run trailaudit data-check --no-clone
```

The first regenerates every block in this file and exits 1 if any of them has
drifted from the artifact behind it. The second reports P9 off the committed
span index and says P3 and P4 were not measured rather than reporting them as
held.

Everything else needs the benchmark. The download lands in `.trail/`, which is
gitignored, and its size is in the pin block above:

```bash
uv run trailaudit fetch
uv run trailaudit index --check
uv run trailaudit data-check
uv run trailaudit adversarial
uv run trailaudit normaliser
uv run trailaudit catf1
uv run trailaudit pairing
```

Each of those writes its artifact under `results/`. Pass `--check` instead and
it reruns the measurement, diffs against what is committed leaf by leaf, and
exits 1 naming the figure that moved.

`index --check` is second in that list because everything after it is scored
against `index/spans.json`, and the predictor the whole claim rests on is handed
nothing else. It rebuilds the index from the traces on disk and exits 1 naming
the trace that moved. The same file is the one input `--index` can be pointed
somewhere else, so every artifact records the sha256 of the index its run read,
each command prints that digest before it starts, and `report --check` refuses
an artifact whose index digest is not the committed one. An index of fabricated
traces makes P9 hold and an index built from the gold locations turns the
gold-blind predictor into an oracle, and neither can be committed here without
the digest saying so.

`fetch` verifies three things and refuses to go on if any of them fails: that
`HEAD` is the pinned commit, that `calculate_scores.py` hashes to the recorded
digest, and that every dataset JSON in the tree rolls up to the corpus digest.
Append one comment line to the scorer and `trailaudit fetch --check` goes from
exit 0 to exit 1.

The digest covers the file, and the audit runs the scorer by compiling those
same bytes rather than by handing the path to Python's import machinery. That
distinction is the difference between a checkable claim and a decorative one:
`SourceFileLoader` prefers a `__pycache__` entry whose header carries the
source's mtime and size, without reading the source, so bytecode compiled from
anything at all would have run under the pinned file's name while the digest
went on matching. Upstream's `.gitignore` lists `__pycache__/`, so `git status`
would not have named it either. What the pin still does not cover is the numpy,
scikit-learn and scipy that `calculate_scores.py` imports at module level, which
`pyproject.toml` pins by version and not by digest.

Exit codes: 0 nothing to report, 1 what is on disk does not match the pin or a
committed artifact, 2 there is nothing on disk to check, 3 a pre-registered
property came back violated. 3 is the good outcome and it is deliberately not 1,
because 1 means the audit could not trust its own input.

</details>

<details>
<summary>What each file does, and which one to read first</summary>

`upstream.py` owns everything that touches somebody else's repository: the
pin, the digests, the fetch, and the one place `calculate_scores.py` is compiled
and run. It reads the taxonomy out of that file's syntax tree rather than
restating it, because `all_categories` is a local inside `main()` and cannot be
imported. So the labels the audit checks against are the labels the scorer uses,
by construction.

`predictors.py` is the seven predictors, the six in the headline table plus
`one-span-all-categories` for P7, each declaring whether it is allowed to see
the gold, with a test that holds every one of them to what it claims to read.
`scoring.py` writes a directory of predictions and drives TRAIL's `main()` over
it. `spans.py` builds the one derived artifact that is committed.
`adversarial.py`, `normaliser.py`, `catf1.py`, `pairing.py` and `datacheck.py`
are one property group each, and every one of them prints a report and writes a
JSON artifact.

`report.py` is the part worth reading if you only read one. It renders every
figure in this file out of those artifacts, between HTML comment markers, and
refuses in both directions: a marker with no generator behind it is an error,
and a generator whose block is missing from the file is an error. The one-way
version of that check is a mechanism that cannot fail. `twicerun`, an earlier
repository of mine, shipped exactly that: it scanned only for the names its
generator already offered, so the comparison was a set against a subset of
itself. Deleting a generator while leaving its marker stayed invisible for the
life of that project, and the block sat there reading like a maintained table.

The other half of the same idea is that every score in this project is written
to three decimal places, or four in the weighted F1 column, which makes a
hand-typed one easy to find. `report --check` looks for both shapes outside the
generated blocks and fails on a hit, including in this paragraph, which is how
the sentence you are reading ended up phrased the way it is. Three places was
the rule when that check was written and the four-place weighted F1 column
arrived after it: the pattern ended at a word boundary, so a fourth digit
stopped it matching and a hand-typed figure from that column went straight
past.

</details>

<details>
<summary>A green badge over numbers CI never measured would be a smaller version of TRAIL's mistake</summary>

CI runs `ruff`, the style check in `scripts/check_fingerprint.py`, and the
suite, and nothing in that list touches the corpus. `tests/test_readme_blocks.py`
renders every block in this file out of the committed artifacts and fails on a
byte of difference, so a green badge means the code does what its tests say and
this file quotes what the artifacts hold. It does not mean the figures in those
artifacts are right, because nothing in CI reruns the measurement that produced
them.

The suite runs with `pytest-socket` and `--disable-socket` in `addopts`, so a
stray network call is a test failure rather than a slow test. No credentials, no
model calls, no download, nothing to configure. Everything that reads the real
corpus is marked `upstream` and skips wherever it is absent, which on a runner
is every time.

Reproducing the findings takes `trailaudit fetch` and then each of the commands
listed under How to run it, with `--check`, on a machine whose owner has
accepted GAIA's terms. Saying so is not a weakness to bury. A benchmark audit
that overstated what its own CI proved would be making a smaller version of the
mistake it is reporting.

</details>

## How this was built

An agent pipeline wrote most of this code, and the checks in this repository
are the reason I am willing to publish what it produced.

The rule I settled on is that anything I would otherwise have to remember gets
turned into something that fails a build. Eighteen blocks in this README are
rendered from committed artifacts, so a figure here cannot be a figure anybody
typed. Thirty-six line numbers quoted into someone else's source are held against
that source at its pinned hash. The suite runs with sockets disabled, so the claim
that this project makes no model calls is enforced rather than asserted.

<details>
<summary>The four defects those checks caught, and the one they nearly missed</summary>

Worth naming, because a verification layer that has never caught anything is
decoration.

**The digest did not cover the bytes that ran.** `fetch --check` hashed
`calculate_scores.py` and then handed the path to Python's import machinery,
which will use a cached `__pycache__` entry when its header matches the source.
A forged entry could replace both metric lines with `1.0` while the digest still
passed. The audit now compiles the bytes it hashed. This is the one that would
have been fatal, because the whole claim rests on running their code unmodified.

**An input flag could turn a violated property into a pass.** Passing `--index`
with a fabricated span index gave exit 0 and a HELD verdict, on an index holding
no real identifier. Worse, an index built from the gold locations turned the
gold-blind predictor into an oracle while the artifact still recorded it as
reading only spans. Every artifact now records the digest of the index its run
read, and the README refuses to render from one that does not match.

**The guard against wrong line citations had the same bug it was guarding.** Two
citations into the pinned file were wrong, so I added a test pinning all of them.
The pattern was case sensitive, and the two that had been wrong both opened a
sentence. The guard could read every citation except the ones most likely to be
edited.

**The style checker reported a file it could not read as clean.** It returned no
findings on a decode error and exited 0, which is the same shape as the defect
this project reports in TRAIL: a check that looks like it ran.

Three of those four were found by pointing the same adversarial habit at my own
work that the audit points at TRAIL's. That is the part of this repository I would
defend hardest, and it is not the finding.

</details>

## Limits and licence

<details>
<summary>The paper's finding is not in dispute, the two numbers that measure it are</summary>

What is not in dispute is the paper's own claim, that debugging agent traces is
hard and that frontier models are bad at it. What is in dispute is that these
two numbers measure it. That is the narrower claim and the more useful one.

It does not re-score the published table. TRAIL publishes no raw model outputs
and there is no `results/` directory in the benchmark repository, so there is
nothing to re-score. Running my own judges instead would compare a number
produced under one setup against a number produced under another, which
confounds model with method and answers no question anyone asked.

It says nothing about whether TRAIL's human annotators marked the right errors.
That is a real question, answering it needs annotators, and this tests the
scorer against the labels as given.

There is no proposed replacement metric, no corrected scorer, no fork and no
pull request. Auditing one benchmark is the project, and a replacement would
convert a measurement anyone can check into an opinion nobody can. The
precision column is a diagnostic that lives inside the audit and does not become
a package.

Every defect here is the kind a benchmark accumulates: a trailing comma, label
strings that drifted from the taxonomy they were written against, a normaliser
fallback that was reasonable when it was written and does something unintended
at the edges, a metric that reads as accuracy and computes as recall. Naming
them in a repository with reproducible commands is more useful than not naming
them.

</details>

<details>
<summary>Where the data comes from, and why no trace bytes are committed</summary>

`github.com/patronus-ai/trail-benchmark` at the commit the pin block under How
to run it records, which carries an MIT LICENSE, copyright 2025 patronus-ai,
read at that commit on 2026-08-27.

The licence question is not as settled as it looks, and the design here is the
one that is safe under every reading of it. TRAIL's MIT file says "the Software"
throughout and mentions neither upstream dataset. The traces derive from GAIA,
which is gated on HuggingFace behind a condition that it not be reshared outside
a gated or private repository, and from SWE-bench Lite, whose dataset card
states no licence identifier at all. Three sources, three different answers, and
nothing at the pinned commit tells a redistributor which one governs the bytes.
So: fetch on demand against a recorded digest, commit no trace bytes, commit no
gold labels, and let the download happen on the reader's machine under whatever
terms they accepted. That is where the decision belongs.

What is committed is the span index and the five run artifacts, and what is in
them is counted on every run rather than asserted once:

<!-- trailaudit:committed-files -->
| file | bytes | distinct strings | identifiers | TRAIL's own words | longer than three words |
|---|---|---|---|---|---|
| `index/spans.json` | 99,308 | 4,782 | 4,774 | 0 | 0 |
| `results/datacheck.json` | 2,370 | 56 | 5 | 0 | 7 |
| `results/adversarial.json` | 6,090 | 58 | 6 | 1 | 7 |
| `results/normaliser.json` | 47,497 | 374 | 3 | 32 | 4 |
| `results/catf1.json` | 30,373 | 57 | 3 | 21 | 2 |
| `results/pairing.json` | 1,542 | 35 | 2 | 2 | 5 |
<!-- /trailaudit:committed-files -->

`index/spans.json` is a mapping from trace identifier to the span identifiers in
that trace. Nothing else: no question text, no code, no natural language, and
nothing that could be reassembled into either upstream dataset. It is what makes
`data-check --no-clone` work on a fresh clone in under a second.

The results files are not identifiers and integers, and the column above says
so. TRAIL's own words in them are the taxonomy labels, the gold spellings that
are not one of those labels, and the gold location that turned out to be an
English sentence. That location is also the one entry in the last column this
repository did not write: everything else longer than three words is a claim or
a magnitude of its own.

The test fixtures in `tests/fixtures/annotations/` are hand-built and synthetic,
and none of them comes from TRAIL. They are shaped like the real annotation
files and constructed for the behaviours under test: one that parses, one whose
categories have drifted in the four ways the real gold drifts, one with a
trailing comma. A real file that happens to be malformed makes a worse fixture
than a file built to be.

Paper: Deshpande et al., *TRAIL: Trace Reasoning and Agentic Issue
Localization*, arXiv:2505.08638.

</details>
