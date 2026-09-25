# The floor moves to the sentence, and the classifier stops subdividing

## What was wrong

`divide.py` cut at blank lines, list items, headings and table rows, and called
itself "a floor, not a partition": the classifier was granted the power to
divide a unit further, and `s1_classify.to_requirements` recorded whatever
sub-span it returned as the requirement's provenance.

Nothing carried that contract to the model or checked it. S1's system prompt
(3,030 chars) never used the words unit, adjacent, chain, split, divide, merge
or consecutive; `assure.py` states outright that offsets are "a HINT, not the
check"; and `splits_a_sentence` — the guard the module rests on — was only ever
called on `divide()`'s own output, never on S1's spans.

Measured on c1-i2c (127 requirements over `divide()`'s 65 units):

| shape | count |
|---|---|
| span is exactly a union of whole units | **6** of 127 |
| span subdivides a unit | **121** of 127 |
| span BEGINS mid-sentence | **41** of 127 |

The cost is not cosmetic. REQ-0002 through REQ-0010 are one feature-list
sentence cut at its commas into nine noun phrases. REQ-0010's whole span is

    " and glitch filtering."

— 22 characters that name a feature and state no behaviour — and the pipeline
authored from it a check about a three-sample majority filter window. REQ-0010
scored INVERTED against golden RTL on every run measured.

The same defect, in its other shape: `divide()` put boundaries at 6812 and 7192
on the i2c spec; S1 cut inside them at **7072**, which is not a divide boundary
at all, splitting one sentence mid-clause into REQ-0045 ("...are generated using
a majority function") and REQ-0046 ("over the three-sample histories."). Neither
half states the requirement, and both got checks.

## The change

**`divide.py` cuts at sentence ends too.** `_by_sentence` runs last, after the
shape passes have settled, on `paragraph` and `list_item` units only — a
heading is not prose, a table row's periods are not sentence ends, code is not
English. The cut regex has a lookahead (`(?<=[.!?])\s+(?=[A-Z0-9\`])`) that
keeps `i.e. when` and `2.5 us` intact, and sub-`min_words` fragments join
backwards exactly as `divide` already joined a stray "Note:".

**`s1_classify` stops subdividing.** `to_requirements` records `unit.start,
unit.end` for every obligation. The obligation's own offsets survive as an
ACCOUNTING DEVICE for `_tiling_issues` — deliberately kept, because on c1-i2c
"no obligation claims [x:y]" was **13 of the 20 issues** the classify gate ever
raised, and it is the only thing in the chain that punishes under-splitting.
Two obligations from one unit now share a span, which is correct: "the output is
the sum, saturating on overflow" is two requirements resting on one sentence,
and the distinct-span ban that would have rejected it was tried and reverted
earlier for exactly this case.

## Measurements after

`splits_a_sentence` = **0** on all 64 chipverilog specs and all 209 verilogeval
specs. `overlaps` = 0, no word-carrying gaps.

| corpus | units before | after | ratio | median unit | max unit |
|---|---|---|---|---|---|
| chipverilog (64) | 2,966 | 6,134 | 2.07x | 89 → 93 | 2,948 → **1,618** |
| verilogeval (209) | 2,201 | 2,877 | 1.31x | 33 → 52 | 1,445 → 1,322 |
| i2c_master_bit_ctrl | 65 | **168** | 2.58x | — | — |

The classify stage is one model call per unit, so i2c goes from 65 calls to 168.
It is the most heavily cached stage in the pipeline (the whole specification sits
in the shared prefix, measured at 97% hit), so the marginal cost of a unit is the
unit itself. The largest unit *shrank*, which makes the worst single call cheaper.

The two failure sites are closed at the divider: char 7072 now falls inside one
unit — `"The filtered outputs \`sSCL\` and \`sSDA\` are generated using a majority
function over the three-sample histories."` — and `" and glitch filtering."` is
not a unit, so it cannot be a span.

## Live result: n3-i2c, 168 units on gpt-5-mini/medium

| | c1-i2c | n3-i2c |
|---|---|---|
| units | 65 | **168** |
| behavioural (final response per unit) | 50 | 129 |
| requirements | 127 | **214** |
| spans exactly on unit boundaries | **6 of 127** | **214 of 214** |
| largest requirement span | 1,450 ch | **276 ch** |
| word-carrying gaps | 0 | 0 |
| gate issues | 0 | 0 |

The three failure sites this session chased are all closed at S1:

**REQ-0010** was the span `" and glitch filtering."` — 22 characters naming a
feature and stating nothing. It is now 274 characters, the whole feature-list
sentence, and its restatement is a claim a design can get wrong:

> "The module applies glitch filtering to the SDA and SCL inputs so short
> transients on those lines do not propagate to the internal bus-state and
> timing logic." — ports `sda_i`, `scl_i`

**REQ-0045/0046** were one sentence cut mid-clause at char 7072. That sentence
is one unit and one requirement now, spanning 7019–7130:

> quote: "The filtered outputs \`sSCL\` and \`sSDA\` are generated using a
> majority function over the three-sample histories."

**The filter's sampling interval exists as a requirement for the first time**,
with an 82-character span quoting the sentence verbatim:

> REQ-0142, quote: "A filter counter, \`filter_cnt\`, derives its sampling
> interval from \`clk_cnt >> 2\`."

## The `continues_previous` risk did NOT materialise — and the fold was already broken

**0 of 129 behavioural units claimed `continues_previous`.** All 28
continuations landed on `interface` or `scaffolding` units, which emit no
obligations. Sentence-sized units stand alone, and the narrowed prompt gloss
held.

But measuring it turned up that the fold had been discarding **42 of the 169
obligations c1-i2c's classifier authored — 25%** — including the `clk_cnt >> 2`
sentence above. That is a separate, pre-existing defect and it has its own
document: `docs/evidence/continuations.md`. The fix there is what makes the
number safe on a spec where continuations DO fire on behavioural units; on this
one it changed nothing, which is the right outcome for a safety net.

## The other defect this run exposed

Six of 168 responses arrived with their opening lost in transport, were scraped
by `extract_json_object` into a bare obligation object, defaulted to
`kind="scaffolding"`, and passed the gate silently — while their own reasoning
text described behaviour, including "the `busy` flag being set on START and
cleared on STOP". `parse_response` now rejects an object carrying neither
`kind` nor `obligations`. Re-issued, the six produced 19 obligations and took
the run from 195 to **214** requirements; one of them needed two repair rounds,
so the guard caught a repeat of the same truncation. Zero headless responses
remain across all 168.

## What is still unresolved

The argument that kept the paragraph as the floor stands as an argument: 28%
(i2c) and 15% (or1200) of sentences that follow another inside one paragraph
open with a back-reference, and a *script* cutting there severs the referent.
The classifier is not a script — it holds the whole spec in its cached prefix,
is told to resolve the reference in its restatement, and `_BACKREF` gates the
result — but the exposure is larger now, and the only evidence it is being
handled is that `_BACKREF` raised nothing on 214 restatements. That is
consistent with the classifier resolving references, and also with a
restatement that inherits a dependency without opening on one of the 20 words
`_BACKREF` looks for. **Nothing measures whether a restatement is genuinely
self-contained**, and this is where to look if a downstream stage starts
producing checks whose subject is wrong.

The transport defect behind the six headless responses is contained, not
diagnosed: `parse_response` now makes it loud, but the prefixes lost were 4, 5
and 14 characters — the signature of one dropped `response.output_text.delta`,
not a fixed-size truncation — and `_stream_chunk` resets its buffer per attempt
while nothing in the continuation assembly strips a leading brace. It happened
on 3.6% of one stage's calls; the same shape would be silent in any other stage
whose parser tolerates a missing field.
