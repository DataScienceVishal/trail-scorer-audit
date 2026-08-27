"""Table 5 of the TRAIL paper, transcribed, so P9 has something to compare against.

Source: arXiv:2505.08638v3, page 16, "Span and Error Annotation Statistics for
GAIA and SWEBench Datasets". Transcribed by hand from the PDF and checked
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
ABSTRACT_TRACES = 148
ABSTRACT_ERRORS = 841


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
