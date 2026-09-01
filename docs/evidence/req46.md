# REQ-0046, re-authored with `sustains`: the trial, and what it moved

## The bar

    on GOLDEN  (filter present)   -> PASS
    on RUN 10  (filter bypassed)  -> FAIL

Either verdict alone is worthless. The frozen REQ-0046 was thrown away as
ORACLE_INVALID for convicting every design, and the surviving REQ-0010 is
INVERTED. Both previous attempts failed on the golden column.

## A correction first: the scorer was measuring nothing

`decide_rtl` iterates `oracle.tp_uids`. `score_req46.py` passed `tp_uids=[]`
with a comment claiming that meant "every testpoint". It means *none*, and
`_worst([])` returns a constant `ok=False, broken="the oracle names no
testpoint"` -- a verdict-shaped object that never opened a trace. **The script
printed FAIL/FAIL for every input**, and the intermediate readings I took from
it while diagnosing are withdrawn. The script now names every testpoint it
loaded. The headline result below survives the fix unchanged; the intermediate
ones did not.

## The trial

A Sonnet subagent was given the requirement text, the normalized form with
`activation.sustains` populated, the contract ports and the trace row shape --
and **no RTL of any kind**. It returned `req46-authored.py`: 133 lines that find
maximal pull-low runs, sum `held` to recover true width, classify short
(<=1 edge) against sustained (>=2), require the short ones to leave
`(busy, dout, al)` undisturbed and at least one sustained one to produce a
response, and abstain rather than pass vacuously.

    GOLDEN  FAIL      RUN 10  FAIL      -- reproduces the old failure mode.

**`sustains` was not the binding constraint.** The check states the repetition
the schema previously could not hold, and it still convicts the known-good
design. The remaining defect is **attribution**: the check blames the glitch for
every change in its observation window.

## The two confounds, measured

Golden's single conviction is `TP-0024`: a 1-edge glitch on `sda_i` at edge 3,
and `dout` moves at edge 4. That is golden's power-on capture --
`always @(posedge clk) if (sSCL & ~dSCL) dout <= sSDA;` has no reset branch, so
the first clock after reset captures unconditionally. Across golden's 311
testpoints with >=8 rows, `dout`'s first change is at row 4 in **180 testpoints
where `sda_i` is clean at row 3** and 17 where it is not. The glitch is not the
cause.

Gating `dout` on the when-clause `observed_via` already carried -- *"around a
filtered-SCL rising sample"* -- moves the conviction to `TP-0234` rather than
removing it: there `scl_i` rises at edge 4 and `dout` captures at edge 9, five
edges later, which is the synchroniser plus filter depth. That is the
**legitimate** response to a sustained edge sharing the window with the glitch.

So the two confounds are different and each needs its own gate, both readable
off the author's own material:

| gate | source | removes |
|---|---|---|
| observe each port only inside its own when-clause | `observed_via[*].when` | the power-on `dout` capture, in traces with no `scl_i` edge at all |
| discard any window in which another input also moves | the requirement's causal wording, *"must not CAUSE filtered-edge events"* | the legitimate filtered response sharing the window |

With both (`req46-attributed.py`, written by hand as diagnosis, not authoring):

    GOLDEN  abstain (334 testpoints, 0 convictions)
    RUN 10  FAIL

## What that is, and what it is not

It is the correct asymmetry -- the check no longer convicts the design that has
the filter, and it convicts the one that deleted it. Under the standing rule
that *a check not covered against golden is not a verdict*, golden is
GOLDEN-SILENT here, not acquitted and not convicted.

It is **not** a demonstration that the check discriminates, because golden never
supplies evidence. The reason is stimulus, and it is now quantified. Counting
testpoints that present a pull-low run in an *attributable* window -- one no
other input disturbs:

| | both arms | short only | sustained only | neither |
|---|---|---|---|---|
| golden | 7 | 6 | 85 | 236 |
| run 10 | 7 | 6 | 85 | 236 |

Of 334 testpoints, **329 abstain for want of a usable pair** on both designs.

## The category has changed

REQ-0046 was an expressiveness problem -- the schema could not state the count.
`sustains` fixed that, and the first check authored against it states the count
correctly. What is left is a **stimulus** problem: the suite almost never stages
a sub-threshold glitch and a sustained change in the same quiet window, so the
differential `observed_via` prescribes has nowhere to run. That is `add_stimulus`
work with a concrete target, not another authoring round.
