# Hand-built annotation files

Synthetic, and none of it comes from TRAIL. The three files here are shaped like
`processed_annotations_gaia/*.json` and built for the behaviours under test: one
that parses cleanly, one whose category strings have drifted away from the
taxonomy in the four ways the real gold labels drift, and one with a trailing
comma before a closing bracket.

Real files that happen to be malformed make worse fixtures than files built to
be. The trailing comma in TRAIL's own
`processed_annotations_gaia/a96c6811716c0473b86a23321db79c34.json` sits at line
38 of a 60-line file, and a test asserting that would be asserting a fact about
someone else's formatting rather than about the reader.

The taxonomy these are checked against is in `tests/test_gold.py` and is made up
too. Nothing here needs upstream's 21 labels, because what is under test is how
this repository counts drift, not what TRAIL's normaliser does with it.
