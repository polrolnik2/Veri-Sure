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

## The risk this introduces, unresolved

The argument that kept the paragraph as the floor was real: 28% (i2c) and 15%
(or1200) of sentences that follow another inside one paragraph open with a
back-reference, and a *script* cutting there severs the referent. The classifier
is not a script — it holds the whole spec in its cached prefix, is told to
resolve the reference in its restatement, and `_BACKREF` gates the result — but
the exposure is now larger, because there are more such boundaries.

**`continues_previous` is the sharper edge.** `to_requirements` folds a
continuation unit into the previous requirement's span and **drops its
obligations entirely**. With paragraphs as units that was rare and mostly right
(a list stem and its items). With sentences as units, a four-sentence paragraph
whose last three claim continuation collapses to ONE requirement. The prompt's
gloss has been narrowed to say a continuation is a unit that states no obligation
of its own, and that claiming it for a unit that says something is how a
requirement gets lost — but that is a prompt, not a gate, and nothing measures
it. **This wants a live classify run to size before the change is trusted.**

## Also fixed here

`to_requirements` extended a continuation's span by writing `end` and leaving
`quote` alone. `assure._locate` finds a span by its quote and never reads `end`,
so the extension was invisible at G1 and the continuation unit's text read as
unattributed spec text — a hard error, silently, because the offsets still
looked right. The quote now moves with the offset.
