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
and `dout` moves at edge 4.

**Correction to an earlier account.** I first wrote that this was a power-on
capture because `dSCL` starts at 0 and the first clock after reset therefore
satisfies `sSCL & ~dSCL`. That is wrong: golden resets `dSCL <= 1'b1` and
`sSCL <= 1'b1`. The real mechanism is reset RECOVERY. `rst` forces
`cSCL <= 2'b00` -- the sampled bus is held low -- while `fSCL <= 3'b111` and
`sSCL <= 1'b1`. When `rst` releases, `fSCL` shifts in the low `cSCL[1]`
(111 -> 110 -> 100 -> 000) and `sSCL` falls; then `cSCL` refills from
`scl_i = 1` and `sSCL` rises again. **That is a genuine rising edge of the
filtered SCL**, and `dout` captures on it, exactly once per testpoint.

The evidence for the attribution does not depend on that mechanism being right.
Across golden's 311 testpoints with >=8 rows, `dout`'s first change is at row 4
in **180 testpoints where `sda_i` is clean at row 3** and 17 where it is not. A
response to a glitch cannot occur in traces with no glitch. The glitch is not
the cause.

### Is convicting golden here defensible? No -- and the specification is explicit

`dout` is unreset in golden (`always @(posedge clk) if (sSCL & ~dSCL) dout <=
sSDA;`, not even in the `nReset` sensitivity list), so it is worth asking
whether the SPEC demands otherwise and golden is simply wrong.

It does not, and it is not silent by accident. The spec's item 15 enumerates
what reset does:

> *"On asynchronous reset `nReset = 0`, the FSM returns to idle, output enables
> are released high, command acknowledge is cleared, arbitration lost is
> cleared, busy is cleared, counters and filters are reset, and filtered
> SCL/SDA are initialized high."*

Every other output is named -- `cmd_ack`, `al`, `busy`, the output enables.
`dout` is absent. The prose at line 101 repeats the same enumeration and omits
it again, and the port table hedges: *"most sequential state elements are
immediately initialized"* -- most, not all.

`dout`'s only stated behaviour anywhere in the spec is *"captures the filtered
SDA value on the rising edge of the filtered SCL signal"* (lines 53, 84, 115),
with no reset qualifier. REQ-0100 sharpens it to **"on EVERY rising edge of the
filtered SCL signal."**

So the reset-recovery rise is a rising edge of filtered SCL, and **REQ-0100
requires the capture that REQ-0046's check convicts.** A check that convicts it
does not catch a golden defect; it puts REQ-0046 in direct contradiction with
the more specific REQ-0100.

**Nothing was dropped that covered this.** All seven reset requirements
(REQ-0018, 0019, 0075, 0076, 0077, 0082, 0083) and all the `dout` capture
requirements (REQ-0004, 0031, 0051, 0068, 0100) are frozen and TRUSTED. The one
`dout` requirement that is ABANDONED, REQ-0113, was abandoned for
*"never reached in 3 attempt(s)"* and concerns the FSM returning to idle with
`cmd_ack`, not reset. No requirement about `dout`'s reset value was dropped,
because none was ever written -- the specification does not state one.

### What the attribution gate costs

It discards an observation rather than re-attributing it, so a design that DID
respond to a glitch in a window another input also moved would be discarded
too. That is a loss of sensitivity bought for soundness, and on this stimulus it
is expensive: it is part of why 329 of 334 testpoints abstain.

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


## Was the golden conviction attributable to a missing requirement?

Asked directly: the re-authored check failed golden only on a reset artifact --
could that be because REQ-0010 was not in the set?

**The instinct is right about a missing normalization and wrong about which
one.** REQ-0010 was never absent from the frozen SUITE -- it is the INVERTED
check, present and passing run 10 -- and none of REQ-0046's three
`observed_via` routes points at it (they name REQ-0047, REQ-0051, REQ-0096). Its
absence from `normalized.json` cannot reach REQ-0046's authoring.

What WAS missing is REQ-0046's own abort. Comparing the two normalizations:

| | `activation.aborts_on` |
|---|---|
| c1-i2c (what the subagent was given) | **`None`** |
| n1-i2c (after the fixes) | `[{nReset: 0}, {rst: 1}]` |

So a reset guard really was absent from the material, and the new run supplies
it.

**And it would not have helped.** No golden trace contains a reset condition at
all -- **0 of 334** show `nReset=0` or `rst=1` anywhere, because the harness
applies reset before edge 0 and the recording starts after deassertion. On
TP-0024 every row reads `nReset=1, rst=0, ena=1`, including the rows that
convict. An abort expressed over INPUT VALUES cannot exclude a window that no
input marks.

The conviction is the filter pipeline still settling after a reset the trace
never shows: `rst` forced `cSCL` low, and on release the majority filter shifts
that low out over the next several edges, producing one filtered-SCL rise and
one `dout` capture around edge 4.

So the exclusion this needs is *"the filter has not settled since reset"* -- a
COUNT of edges from the start of the recording, not a condition on any port.
That is the same class of gap `sustains` was added to close, reappearing on the
reset side, and `Activation` has no term for it.

**A prediction for the re-run**, worth checking rather than assuming: the newly
authored REQ-0046 will carry the reset abort and should still convict golden on
TP-0024, because the abort cannot fire.
