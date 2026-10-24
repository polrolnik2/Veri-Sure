# `continues_previous` discards 25% of what the classifier authors

Measured on **c1-i2c**, which is the frozen baseline — before the sentence
floor, before whole-unit spans. This is not a risk the floor introduces. It is
a defect the pipeline already had, and it caused a failure this session spent
its budget chasing.

## Method

`docs/evidence/continuations.py` replays c1-i2c's 65 recorded classify
responses through the divider that produced them and through the
`to_requirements` of that commit. The replay reproduces **all 127 requirements
verbatim and in document order**, so the reconstruction is exact and the
discard count below is the real one, not an estimate.

## The number

| | c1-i2c |
|---|---|
| units | 65 |
| behavioural | 50 |
| claimed `continues_previous` | **14 — 28% of behavioural** |
| ...of which carried obligations | **14 of 14** |
| obligations **discarded** by the fold | **42** |
| authored → kept | **169 → 127**, i.e. **25% discarded** |

Every continuation carried content. The fold's code is three lines:

```python
if out.continues_previous and reqs and i > 0 and units[i - 1].end <= start:
    reqs[-1]["spec_spans"][-1]["end"] = end
    continue          # <- the obligation is gone
```

It extends the previous requirement's span and drops `ob.text` and `ob.ports`.
Because the SPAN survives, `assure`'s unattributed-spec-text check sees nothing
missing — which is why this has been invisible for the whole project.

## What was lost

23 of the 42 have no kept requirement resembling them (token Jaccard < 0.34);
the other 19 are near-duplicates of a neighbour and their loss is cheap.

**The orphan that explains the filter cluster:**

> "The filter counter `filter_cnt` derives its sampling interval from the
> prescale value `clk_cnt` shifted right by two bits."

No kept requirement states it. The survivor, REQ-0045, reads *"A filter counter
derived from `clk_cnt` must trigger periodic sample-shift events"* — with no
`>> 2`. So when [O] came to author the filter checks, the sampling interval had
no requirement to quote, REQ-0045 was unassertable, and REQ-0010/0045/0046 all
scored INVERTED or vacuous against golden RTL. **The sentence stating the number
was folded away before normalization ever saw it.**

Other orphans with no counterpart anywhere in the 127:

* `busy` is set after a detected START and cleared after a detected STOP
* the main FSM transitions to idle when arbitration-lost is asserted
* both output enables are released when arbitration-lost is asserted
* `din` determines SDA drive state during WRITE (`din=0` drives low, `din=1`
  releases)
* `sda_oen` = 0 drives the SDA line low
* the raw `scl_i`/`sda_i` are captured into `cSCL`/`cSDA` on the rising `clk`

## Why the fold exists, and what it should do instead

The intent is right: a continuation's span must include its referent, or the
requirement reads as a claim that its own text does not support. The
implementation achieves that by **deleting the obligation**, which is the one
thing it must not do — the obligations are self-contained restatements that the
`_BACKREF` gate already forces to stand on their own. They are requirements.

So: a continuation's obligations are EMITTED, with a span reaching back to the
unit that opens the chain, and the previous requirement's span is left alone.
The referent is in the provenance either way; the difference is that the
requirement still exists.

Chains are followed to their start, not one unit back: three consecutive
continuation units all anchor on the last unit that stood alone, so the third
one's span still contains its referent.

## What the fix recovers, measured

Replaying c1-i2c's recorded responses with **only the fold changed** — the old
divider and the old subdividing spans held constant, so nothing else can move
the number:

| | |
|---|---|
| requirements | **127 → 169 (+42)** |
| of those, textually new | **42 of 42** |
| widest span produced | **1,830 chars of 15,713 — 11.6%** |

The catch-all stays unavailable: the chain closes at the first unit that stands
alone, so no span approaches the document. And on the paragraph floor those
widths are the worst case — with the sentence floor the anchor is a sentence,
not a 1,350-character paragraph.

Named among the 42 recovered:

* `filter_cnt` derives its sampling interval from `clk_cnt` shifted right by two
  bits — **the number the filter cluster needed and did not have**
* `busy` set after a detected START; `busy` cleared after a detected STOP
* the main FSM transitions to idle when arbitration-lost asserts
* both output enables release when arbitration-lost asserts
* `al` asserts on a STOP detected while the FSM is active on a non-STOP command
* `din` determines SDA drive state during WRITE bit operations

## On the new division it fires zero times -- and that reading is CONFOUNDED

n3-i2c, 168 sentence-floor units on gpt-5-mini/medium: **0 of 129 behavioural
units claimed `continues_previous`**, against 14 of 50 (28%) on c1-i2c.

**That does NOT establish that sentence-sized units stand alone, and it was
first reported here as though it did. It is withdrawn.** The prompt n3-i2c ran
carried a gloss written when the fold still dropped obligations -- "claiming it
for a unit that says something is how a requirement gets lost" -- which is a
warning against setting the flag. Zero is equally consistent with a model
declining a flag it was told would cost it requirements.

## What the flag now means, and where it is decided

Four designs passed through. The fourth is the one where the ORDER is right.

| | `continues_previous` | decided by | what was wrong |
|---|---|---|---|
| original | folded the unit into the previous requirement's span and **deleted its obligations** | the classifier | 42 of 169 obligations discarded on c1-i2c, silently |
| second | kept the obligations, **widened their spans** backwards | the classifier | no loss, but two independent classifications stood, one per half of a thought |
| third | **merged the units**, then re-classified the block | the classifier | every merged block had been classified at a granularity the same call had just declared wrong, and that work was thrown away |
| now | **merged the units**, then classified | a **separate, earlier stage** | -- |

`divide` produces a **scaffold**. A requirement can straddle one of its
boundaries and only a reader can tell, so S1 now runs three steps in this order:

    divide      a script cuts at authorial boundaries and sentence ends
    boundary    one short call per unit: is this unit and the one before it a
                single unit? Chains of yes are merged
    classify    one call per FINAL unit: kind, obligations, ports

**Classification runs once, at the granularity that survives.** That is why the
boundary question is its own stage rather than a field on the classifier's
answer: when one call decided both, `ports`, the obligation split and every
other relational field were authored against a fragment and then discarded
wherever the same call said "merge".

The two stages share the S1 cache shape -- whole specification and contract in a
byte-identical prefix -- but never share a cache key, because their system text
differs in the first bytes. The boundary answer is a sentence and a boolean, so
the pass is short where it counts: output tokens dominate latency.

**Cost, stated plainly.** Boundary is N calls, classify is M <= N. Against a
single classify pass this is not free: where nothing merges it is N extra cheap
calls for an unchanged partition. That is the price of never classifying at a
granularity that is about to be revised, and it is paid whether or not the
revision happens.

**The chain is unbounded, and that is the one way the catch-all could return.**
If every flag after the first were set, all units would merge into a single unit
spanning the whole specification -- the exact answer this subsystem exists to
make unavailable. A cap is deliberately not imposed (a number standing in for a
property is what `MIN_SPAN_CHARS` and the distinct-span ban were both reverted
for); the largest merged block wants reporting in `s1_gate.json` the way
`word_carrying_gaps` is reported.

**Still unmeasured live.** Every i2c number on record predates this stage.
