# The filter requirements are partial, and the spans prove it

REQ-0010 and REQ-0046 convict the golden design and acquit the one that deleted
the filter. That is not a normalization defect, an expressiveness defect, or an
author defect. **The specification states the filter in one sentence and S1 cut
it into pieces that no single requirement can check.**

## What the specification says, in one place

> *"A filter counter, `filter_cnt`, derives its sampling interval from
> `clk_cnt >> 2`. Whenever this counter expires, new synchronized samples are
> shifted into the three-sample histories."*  — char 10812

So "a short glitch" is fully defined, as a composition: one that cannot occupy
2 of 3 samples taken `clk_cnt >> 2` clocks apart. **The threshold is not a
constant — it is a function of a runtime input port.**

## Where the cluster's spans actually point

| req | span | quote |
|---|---|---|
| REQ-0010 | 476–498 | *" and glitch filtering."* |
| REQ-0045 | 6932–7072 | *"...A filter counter then controls when samples are shifted into `fSCL` and `fSDA`. The filtered outputs `sSCL` and `sSDA` are generated "* |
| REQ-0046 | 7072–7190 | *"using a majority function over the three-sample histories. This reduces the effect of short glitches..."* |
| **REQ-0083** | **covers 10812** | the sentence with `clk_cnt >> 2` |

Three things follow, and each is independently disqualifying.

**REQ-0045 and REQ-0046 are ONE SENTENCE, split at char 7072, mid-clause** --
"are generated " | "using a majority function". Neither half states a property;
together they state one.

**REQ-0010's span is 22 characters of a feature-list bullet**, from the
overview paragraph. Its TEXT asserts the whole mechanism -- "sampling histories
... majority function over the three-sample histories" -- which its span does
not contain. That is S1 asserting content its provenance does not support.

**The number belongs to a requirement outside the cluster.** `clk_cnt >> 2` is
in REQ-0083's span. No requirement that talks about short glitches owns the
definition of short, and no requirement that owns the definition talks about
glitches.

## Why every fix so far missed

Each was aimed at a layer that was not the problem:

* `sustains` -- the schema holds `int` bounds, and this threshold is a formula
  over a port. Normalization was RIGHT to leave it empty.
* `runs` / `nth` -- present, imported, taught. The author still cannot compute a
  bound whose inputs are in another requirement's span.
* the `when` clauses -- 76% empty to 0%, and irrelevant here.

The authored checks then hardcode a constant: REQ-0046 uses "fewer than three
held edges", and my own suggestion was `at_most=1`. Both assume the filter
samples every edge. Measured across the suite, `clk_cnt >> 2` ranges over
**0, 1, 2, 3, 4, 25, 250, 8191, 16383** -- at `clk_cnt=1000` a glitch of
hundreds of edges is still short. A fixed bound calls that sustained, looks for
a response, convicts golden for filtering it, and passes the design that
deleted the filter and reacts to everything. **That is the inversion,
mechanically.**

## What each one actually warrants

**REQ-0010 -- NOT_ASSERTABLE.** Its span is a feature-list bullet. A list item
naming a capability has no falsifiable consequence at the boundary, which is
the disposition REQ-0020 already got for a port-table gloss.

**REQ-0045 -- UNOBSERVABLE.** Cadence only, ports `clk_cnt` and `clk`, effects
on internal `fSCL`/`fSDA`. Nothing at the interface without a route.

**REQ-0046 -- a MONOTONICITY assertion, not a threshold one.** This is the
constructive part. The threshold is unavailable, but the ORDER survives:

> if a disturbance of width W produced no response, no disturbance narrower
> than W may produce one.

That is checkable with `runs` and no knowledge of `clk_cnt >> 2` whatsoever --
rank the runs by summed `held`, and convict only on an inversion of the
ordering. It cannot be defeated by the filter being slow, because it never
names a boundary; it is violated exactly when a design suppresses a long
disturbance and passes a short one, which is what an absent filter does.

**The general lesson is about S1, not about oracles.** A requirement whose span
does not contain the numbers its text depends on cannot be made checkable
downstream, and no gate in the current pipeline asks whether it does.


## Blast radius, measured — and my whole-unit proposal is wrong

I proposed requiring every `spec_span` to be a union of whole `divide()` units,
on the reasoning that this restores "granularity stops being the model's to
pick". Measured on c1-i2c's 127 requirements against the 65 units `divide()`
produces:

| rule | flagged |
|---|---|
| span must be a union of WHOLE units | **121 of 127** |
| span must not BEGIN MID-SENTENCE | **41 of 127** |

**The whole-unit rule is unenforceable.** Only 6 requirements satisfy it.
Subdivision is not an occasional slip, it is the dominant mode, and a rule that
rejects 95% of the set is a rule nobody can adopt.

**And the reason is visible in the first ten offenders.** REQ-0002 through
REQ-0010 are ONE SENTENCE cut at its commas:

    REQ-0002  "The module supports generation of I2C START and STOP conditions,"
    REQ-0003  "single-bit WRITE cycles, "
    REQ-0004  "single-bit READ cycles, "
    REQ-0005  "bus-busy detection, "
    ...
    REQ-0010  " and glitch filtering."

Nine "requirements" that are NOUN PHRASES. None of them asserts anything, and
REQ-0010 -- the one that produced an inverted check -- is fragment nine of a
feature list. Its text describes the whole majority-filter mechanism because a
requirement had to be written and the fragment gave nothing to write from.

**The enforceable rule is the one `divide.py` already holds itself to.**
`splits_a_sentence` flags 41 of 127, and it catches every requirement in this
story: REQ-0010, REQ-0045, REQ-0046 and REQ-0083 are all flagged. 32% is a real
cost, but it is a cost against a check that `divide()` passes by construction
and S1 was simply never asked to pass.

That is the proposal, corrected: not "spans must be whole units" but "a span may
not begin mid-sentence", applied to `requirements.json` rather than only to
`divide()`'s own output in its tests.
