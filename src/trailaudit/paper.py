"""Two tables from the TRAIL paper, transcribed, so the audit has something to compare against.

Table 1 is what the adversarial predictors are measured against and Table 5 is
what P9 checks the repository's file counts against. Both are hand-transcribed
from arXiv:2505.08638v3 and both are checked here against arithmetic the paper
publishes alongside them, because a transcription error would move a headline.

## Table 1, page 7

Eight models by six metrics, three per split: category F1, location accuracy and
joint accuracy. The two Pearson columns are not transcribed. They correlate a
human overall score against a generated one, this audit computes neither, and a
figure sitting in the tree that no code reads is a figure nobody checks.

The paper states its headline three different ways and only one of them is a
number the scorer produces:

    page 1, abstract     "the best Gemini-2.5-pro model scoring a mere 11% on TRAIL"
    page 2, intro        "achieving only 11% combined joint accuracy on both splits"
    page 8, conclusion   "Gemini 2.5-pro achieving only 18% joint accuracy on GAIA
                          and 5% on SWE Bench"
    page 7, Table 1      Gemini-2.5-Pro-Preview-05-06, joint 0.183 GAIA, 0.050 SWE Bench

The last two agree: 0.183 and 0.050 rounded. 11% is neither of them, it is not
in Table 1 either, and no aggregation of Table 1 rounds to it. The plain mean of
the two split figures is 0.1165, which is 12% to the nearest point and 11% only
if truncated. Weighting the two splits gives numbers further away, not closer:
by the 116 and 31 gold files the scorer loads, 0.155; by their 580 and 256
errors, 0.142; by Table 5's own trace counts, 0.155.

Two innocent readings, both stated because neither can be checked from here.
Table 1's note says every figure is the mean of three runs, so the unrounded
per-run pairs behind 0.183 and 0.050 could well mean to 0.114 and round to 11.
Or the combined figure was computed by pooling both splits into one call rather
than by combining the two published numbers at all.

Either way `calculate_scores.main()` is called once per split and returns one
number per split, so that is the granularity this audit compares at: per split,
against the Joint and Loc. Acc. columns of Table 1. 11% is quoted only as the
paper's own summary of two numbers it does not quite reproduce.

## Table 5, page 16

"Span and Error Annotation Statistics for GAIA and SWEBench Datasets", checked
against the parenthesised means the table publishes alongside four of its
columns, which is what fixes the reading of the last one:

    977 / 118 = 8.28     the mean the table prints beside Total Spans, GAIA
    1010 / 31 = 32.58    the same, SWE Bench
    383 / 115 = 3.33     the mean beside Unique Error Spans, GAIA
    192 / 31  = 6.19     the same, SWE Bench

Unique Error Spans is divided by Error Span Total rather than by Total Traces,
so that last column is the number of traces carrying at least one error, and
that is the reading `traces_with_errors` records. Nothing else in the table
would divide to those means.

The paper's other figures used here are its own prose: 148 traces and 841
errors, on page 5, "averaging at 5.68 errors per trace", which is 841/148.
Table 5 does not add up to either. 118 + 31 is 149 traces and 579 + 256 is 835
errors, so the paper describes its dataset three ways and the repository at the
pinned commit is a fourth.
"""

from __future__ import annotations

from dataclasses import dataclass

CITATION = "arXiv:2505.08638v3, Table 5, page 16"
TABLE_1_CITATION = "arXiv:2505.08638v3, Table 1, page 7"
ABSTRACT_TRACES = 148
ABSTRACT_ERRORS = 841

# Page 2, and again on page 1 in different words. Not a figure the scorer
# returns: `main()` produces one number per split and this is the mean of two.
COMBINED_JOINT_PROSE = 0.11

# Section 4.3, page 5: "we found errors in 114 GAIA traces and 30 from SWE
# Bench". Table 5 on page 16 says 115 and 31 for the same quantity. Both matter
# to P1 and P2 rather than only to P9, because the count of traces carrying at
# least one gold error is the ceiling on both headline metrics: lines 54 and 58
# score a trace with no gold errors as 0 for every predictor including a perfect
# one.
PROSE_TRACES_WITH_ERRORS = {"GAIA": 114, "SWE Bench": 30}


@dataclass(frozen=True)
class Scored:
    """One model's row in Table 1, for one split. None is the table's CLE.

    CLE is the paper's mark for a model whose context window could not hold the
    split's traces at all, which is three of the eight on SWE Bench. It is not a
    zero and must not be averaged as one.
    """

    model: str
    cat_f1: float | None
    location_accuracy: float | None
    joint_accuracy: float | None


TABLE_1 = {
    "GAIA": (
        Scored("Llama-4-Scout-17B-16E-Instruct", 0.041, 0.000, 0.000),
        Scored("Llama-4-Maverick-17B-128E-Instruct", 0.122, 0.023, 0.000),
        Scored("GPT-4.1", 0.218, 0.107, 0.028),
        Scored("OpenAI o1", 0.138, 0.040, 0.013),
        Scored("OpenAI o3", 0.296, 0.535, 0.092),
        Scored("Anthropic Claude-3.7-Sonnet", 0.254, 0.204, 0.047),
        Scored("Gemini-2.5-Pro-Preview-05-06", 0.389, 0.546, 0.183),
        Scored("Gemini-2.5-Flash-Preview-04-17", 0.337, 0.372, 0.100),
    ),
    "SWE Bench": (
        Scored("Llama-4-Scout-17B-16E-Instruct", 0.050, 0.000, 0.000),
        Scored("Llama-4-Maverick-17B-128E-Instruct", 0.191, 0.083, 0.000),
        Scored("GPT-4.1", 0.166, 0.000, 0.000),
        Scored("OpenAI o1", None, None, None),
        Scored("OpenAI o3", None, None, None),
        Scored("Anthropic Claude-3.7-Sonnet", None, None, None),
        Scored("Gemini-2.5-Pro-Preview-05-06", 0.148, 0.238, 0.050),
        Scored("Gemini-2.5-Flash-Preview-04-17", 0.213, 0.060, 0.000),
    ),
}


def best_published(split: str, metric: str) -> Scored:
    """The Table 1 row this audit's predictors are measured against.

    Ties go to the first row in the table's own order rather than to whichever
    the sort happens to surface, so the model named in the report does not move
    when a figure is corrected somewhere else in the table.
    """
    rows = [row for row in TABLE_1[split] if getattr(row, metric) is not None]
    if not rows:
        raise KeyError(f"Table 1 has no {metric} for {split!r}")
    return max(rows, key=lambda row: getattr(row, metric))


@dataclass(frozen=True)
class Published:
    split: str
    traces: int
    spans: int
    errors: int
    unique_error_spans: int
    traces_with_errors: int


TABLE_5 = (
    Published(
        "GAIA",
        traces=118,
        spans=977,
        errors=579,
        unique_error_spans=383,
        traces_with_errors=115,
    ),
    Published(
        "SWE Bench",
        traces=31,
        spans=1010,
        errors=256,
        unique_error_spans=192,
        traces_with_errors=31,
    ),
)

ROWS = ("traces", "spans", "errors", "unique_error_spans", "traces_with_errors")

LABELS = {
    "traces": "total traces",
    "spans": "total spans",
    "errors": "total errors",
    "unique_error_spans": "unique error spans",
    "traces_with_errors": "traces with an error",
}


def published_for(split: str) -> Published:
    for row in TABLE_5:
        if row.split == split:
            return row
    raise KeyError(f"Table 5 has no row for {split!r}")


def compare(split: str, measured: dict[str, int]) -> list[tuple[str, int, int | None]]:
    """(label, what the paper says, what was measured) for all five Table 5 rows.

    Three of the five need the gold annotations, which are not committed here,
    so the measurement comes back None without the clone and `data-check` prints
    the row as unmeasured rather than as a zero that would read like a finding.
    """
    row = published_for(split)
    return [(LABELS[name], getattr(row, name), measured.get(name)) for name in ROWS]
