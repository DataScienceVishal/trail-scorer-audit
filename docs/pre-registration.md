# The nine properties, as written before any code existed

This is the pre-registration section of the project spec. It is here so that
the README's claim that the nine were fixed in advance is something a reader can
check rather than take on trust.

## Provenance, and what a reader still has to take on trust

One edit, and it is the only one: the spec was written in the third person
about me, and this copy says "my" where that one said my name. Nothing else
changed, and the nine claims and their contingencies are the original wording.

The spec was written on 2026-08-27 at 10:16. The first commit in this repository
is 2026-08-27 at 10:28, twelve minutes later, and it is scaffolding. Both
timestamps are checkable: the second with `git log --reverse`, the first only
against the file this section was copied out of.

That file is not published. It is a working document for a portfolio of
unrelated projects and the rest of it discusses things that have no business in
a public repository, including which employers I might apply to. So
what is reproduced here is one section of a longer private document.

The honest statement of the trust boundary: you can verify that these nine
claims and their contingencies are internally consistent with what the audit
went on to report, and you can verify the commit timestamps. You cannot verify
from inside this repository that the section was not edited between 10:16 and
being committed here. If that matters to you, the finding to weigh it against is
that not one of the nine held: seven came back violated and two came back
violated but latent, meaning the defect is real in the code and moves no number
on this data. Nothing holding is the outcome most favourable to me, and it is
the reason to read the section sceptically rather than take the timestamp for
more than it is worth.

**One arithmetic error in the section below, left in rather than corrected.** The
paragraph after the table says four of the nine had a known direction, and then
names P2, P5 and P6 as the open ones. Nine minus three is six, and six is what
the README says. The spec was wrong when it was written and the number was
already right everywhere the audit reports it.

Correcting it here would be the easier option and it is the wrong one, because
this file is only worth reading if it is what was written at the time. A
pre-registration that gets tidied up after the results are in is not a
pre-registration. So the error stays, this note names it, and you can weigh both.

## The pre-registered properties

Written before any code exists, so the target cannot move afterwards. These are properties a competent benchmark scorer should have. A property that is **violated** is a finding.

Note the inversion against `twicerun`, where a triggered condition was bad news for the project. Here the object under test is someone else's code, so a violation is a result and a clean sweep would mean the project has nothing to publish. That asymmetry is stated in the README too, because it is exactly the kind of thing that makes a pre-registration worth less than it looks if nobody points it out.

| property, as written before any code | how it is measured | what a violation means |
|---|---|---|
| **P1** A predictor emitting every span crossed with every category scores no better than the best real judge on either headline metric | the all-spans predictor through the pinned unmodified scorer, joint and location accuracy, against the published 0.110 and the paper's location figure | both headline metrics are recall in practice and not only in the source. Leaderboard position is partly a function of how many errors a model emits. This is the claim |
| **P2** Every gold error location appears as a span identifier in its own trace file | per-trace set difference, gold locations against the committed span index | the gold references locations the trace does not contain, or the two use different identifier formats. Either caps the all-spans predictor below the gold-spans ceiling and makes P1's figure a lower bound |
| **P3** Every gold annotation file parses as JSON | parse each file in both `processed_annotations_*` directories, count and name the failures | the published numbers silently cover fewer traces than the paper claims, because the scorer wraps loading in try/except |
| **P4** Every gold category string is one of the 21 taxonomy labels | distinct category strings across all gold files, matched exactly | labels and taxonomy have drifted apart, and the normaliser is deciding what some fraction of the gold means |
| **P5** The normaliser's output depends on its input alone, not on the order of the taxonomy list it is passed | find every string matching more than one label under the fallback, then re-run the whole slice 2 measurement with `all_categories` shuffled under a fixed seed and diff every score | two people running the same scorer on the same data can get different numbers. Genuinely open: I do not know where `all_categories` comes from or whether its order is stable |
| **P6** No string shorter than the shortest taxonomy label normalises to a taxonomy label | enumerate every substring of every label, group by assigned label, report the shortest string reaching each of the 21 | the fallback converts vague output into a specific category. The direction is the finding: the judge's string must be a substring of the label, so vagueness is laundered and specificity falls through unmatched. Magnitude genuinely open |
| **P7** Per-category F1 distinguishes a judge that names the right category at the right span from one that names it anywhere in the trace | score a predictor emitting all 21 categories at a single arbitrary span, report per-category recall | cat F1 is per-trace set membership and location never enters it |
| **P8** The scorer pairs each predicted location with the category predicted for it | constructed annotation file, one null category followed by two real ones, through the unmodified scorer | one null category silently mispairs every subsequent error in that trace. Latent on the current gold data, where all 147 files check out, and the README must not imply otherwise |
| **P9** The repo's split sizes match the paper's Table 5 | count files per split directory, compare against the table | the artifact and the paper describe different datasets and a reader cannot tell which one the leaderboard was computed over |

Four of these have a known direction from my own first-hand check. That is worth saying out loud rather than dressing them up as open questions: what pre-registration buys here is the **magnitude** and the **contingency**, both fixed before the code exists, not the direction. P2, P5 and P6 are open in direction as well, and P2 is the one the headline depends on.

---

## What would mean the project failed

- **The all-spans predictor scores below 0.110 on either headline metric.** Then the central claim is wrong, the metric is harder to game than a first-hand check suggested, and the README says that instead. Genuinely reachable if P2 is violated badly.
- **Fewer than three properties are violated.** Then the pathology is thinner than it looked and this is a note in a gist, not a repo. Ship it as a note.
- **The audit needs an API key, a network call, or more than 30 seconds from the committed index.** The whole pitch is that the central result costs nothing and never drifts. If it drifts, it is not this project.

---

