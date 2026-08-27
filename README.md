# trail-scorer-audit

Audits the scoring code behind TRAIL, a benchmark of 148 human-annotated agent
execution traces published by Patronus AI under MIT.

TRAIL ships a leaderboard where the best model reaches 11 percent. The two
headline numbers behind that figure, location accuracy and location-category
joint accuracy, are computed in
[`benchmarking/calculate_scores.py`](https://github.com/patronus-ai/trail-benchmark/blob/0ffbed9db859b4a66250dc783fa4dccf86869595/benchmarking/calculate_scores.py),
and both divide the size of an intersection by the size of the gold set. This
repository measures what follows from that, and what else the scoring path does
to the labels on the way through, using their file at a pinned commit with
nothing copied and nothing edited.

The audit exists because the authors published the scorer, the gold labels and
the traces openly. Most benchmarks ship a leaderboard and keep the scoring code
to themselves, and those cannot be audited at all.

Zero model calls, zero dollars, and the test suite runs with the network
switched off.

## Status

Slice 1 of four. `fetch`, `index` and `data-check` are here; the adversarial
predictors, the normaliser study and the generated results tables are not.
