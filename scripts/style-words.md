# Words this project does not use in prose

Enforced by `scripts/check_fingerprint.py`, which parses the fenced blocks below.
The pre-commit hook runs it over the staged diff and CI runs it over the tree.

Punctuation and emoji are handled in code rather than listed here: the em dash
family and the emoji blocks are matched by pattern, not by word.

The fenced blocks are the half a script can hold. The section after them is the
half nothing runs, kept in the same file because the reason for both is the same.

## Single words

```banned-words
delve
delves
delved
delving
leverage
leverages
leveraging
leveraged
robust
robustly
seamless
seamlessly
comprehensive
comprehensively
cutting-edge
harness
harnesses
harnessed
harnessing
unlock
unlocks
unlocked
unlocking
elevate
elevates
elevated
elevating
streamline
streamlines
streamlined
streamlining
empower
empowers
empowered
empowering
showcase
showcases
showcased
showcasing
boast
boasts
boasting
underscore
underscores
underscored
underscoring
pivotal
meticulous
meticulously
realm
realms
landscape
landscapes
tapestry
tapestries
```

## Phrases

```banned-phrases
at its core
it is worth noting
it's worth noting
a testament to
navigating the complexities
in today's fast-paced
let us dive in
let's dive in
in conclusion
the key takeaway
dive deep
deep dive
game changer
game-changing
best-in-class
state-of-the-art
paradigm shift
```

## Patterns

Written as Python regex, case-insensitive, applied to prose files only.

```banned-regex
not only .{1,60}? but also
it is not just .{1,60}?, it is
it's not just .{1,60}?, it's
whether you (are|'re) .{1,60}? or
in the (ever[- ]evolving|rapidly changing) .{0,30}(world|landscape|realm)
```

## Exceptions

Some of the banned words have legitimate technical uses. The checker skips a hit when the surrounding text matches one of these. Keep this list short: every exception is a hole in the net.

```allowed-contexts
eval harness
evaluation harness
test harness
agent harness
harness/
harness.py
_harness
underscore-separated
leading underscore
trailing underscore
double underscore
financial leverage
```

## Tells no pattern catches

Three of these, each found by reading and each fixed more than once before it got
written down here.

**An undisclosed figure typed by hand.** `spans.py` opened on a trace corpus of
185.6 MB, the generated pin block said 186.4, and eleven docstrings said 186.
Every one of the three was true of something: 148 trace files are 185,571,847
bytes, and the 148 gold annotation files take the 296-file corpus to 186,421,678.
None of them said which quantity it was quoting, so three separate measurements
read as one figure drifting. `adversarial.py` had the worse version, 0.973, 0.974
and 129 typed into a docstring for values `loose_scores` computes and does not
read back. Both went in `bb39e9b`. A number in prose either renders from a
committed artifact or names what measured it.

**A reference that needs a fold the reader has not opened.** Six across the 15
folds here. One opened on "those 3,205 strings", first named two folds earlier.
Two pointed back at fold 10 from folds 12 and 14. One said "both tables" with its
antecedent in the previous fold. Folds are collapsed by default, so the ordinary
reader has opened one of them, and to that reader all six were dangling pronouns.
`712f8b6` gave each fold its own subject. A fold either stands on its own or names
the fold it needs.

**Bold setting a rhythm rather than marking a claim.** This one arrived from
twicerun, which ran 16 paragraph-initial bold lead-ins across 19 folds, nearly all
admissions in the same grammatical shape, so by the eighth the bold had stopped
meaning "this one" and started meaning "another of those". There are four here,
all inside one fold, and each states a separate defect in its own words, which is
the use this is not about. The question to ask is whether deleting the asterisks
would cost the reader anything. Down a run of paragraphs that all carry them, it
would not.

## Change log

- 2026-09-19: Added the three unmatched tells above. The first two are this
  repository's, dated to the commits that fixed them. The third is twicerun's and
  is recorded here because the four lead-ins this README keeps are close enough to
  the line that the next person adding one should know where the line is.
