# Words this project does not use in prose

Enforced by `scripts/check_fingerprint.py`, which parses the fenced blocks below.
The pre-commit hook runs it over the staged diff and CI runs it over the tree.

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

`eval harness` is here because Vishal uses the phrase himself throughout the brief and it is the ordinary name for the thing. `agent harness` earns its place the same way, and half the slate involves running an agent, so it would otherwise recur constantly. `underscore` is here because it names a character that appears constantly in Python discussion.

Note what stays caught: bare `harness` as a verb, as in "harness the power of embeddings". There is a test for exactly that in `test_check_fingerprint.py`, because an exception that quietly widens into a blanket pass is worse than no exception.

## Punctuation and symbols

Enforced in code, not listed as words.

**Em dash family**, banned in any form anywhere: `U+2014` (em dash), `U+2013` (en dash), `U+2015` (horizontal bar). Use a hyphen, a comma, a colon, or restructure the sentence. En dash is included because the usual defence for it, numeric ranges, reads fine with a hyphen and the exception would be abused.

**Emoji**, banned anywhere: the standard emoji blocks plus variation selector `U+FE0F` and the zero-width joiner sequences. Includes the ones that look like punctuation, such as the check mark `U+2705` and the cross mark `U+274C`, which turn up constantly in generated README tables.

## Structural tells

Not machine-checkable. `voice-auditor` reads for these and reports with line numbers.

- Every section the same length
- Exactly three bullets under every heading
- A bold lead-in on every bullet in a list, with no bullet that just says its thing
- A rhetorical question followed immediately by its own answer
- A closing paragraph that restates the opening
- Headings that all share one grammatical shape, for example all gerunds or all noun phrases
- Feature lists padded to six items where three of them are trivial
- Badge walls
- "Contributions are welcome" on a personal project nobody is contributing to

## Code tells

`code-smell-auditor` owns these. Also not machine-checkable, mostly.

- Comments that restate the line below them
- Docstrings on trivial one-line functions
- `# Initialize variables` and its relatives
- `except Exception as e: print(f"Error: {e}")`
- Variables named `data`, `result`, `temp`, `output`, `processed_data`
- An abstract base class with exactly one implementation
- A config dataclass with one field
- `Optional[Any]` type hints
- Files suspiciously similar in length
- Every function carrying an identically shaped docstring

The last one is the tell that survives the others. Uniform, evenly spaced perfection is itself the signal.

## Numbers in prose

Added 2026-08-27 after a voice audit of `twicerun` found eight stale figures, three of which the same repository counted correctly elsewhere in its own tree. Nothing mechanical catches these, and they are the most common real defect this list has produced.

- A comment or docstring stating a count, a fraction or a bracket that a committed artifact, or another file in the same tree, already contradicts
- A range published above the paragraph that records the same range being exceeded
- A docstring written in the future tense about work that has since shipped
- One quantity stated more than once in different words, where no two statements agree
- A figure presented as precise, with no provenance, sitting beside looser statements of the same thing that do have it

The one that matters most is the first. `twicerun` shipped a comment justifying a constant from the inverse of its own measurement, and the correct figure was ten lines away in a sibling file. A count in prose is a claim, and this list has been wrong about counts six times.

The fix is not more care. It is not writing the number twice: generate the prose from the measurement, or point at the table that already holds it.

