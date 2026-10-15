# Two convictions that rested on nothing, and the guards that refuse them

Both fixes below are in `specflow`, not in a driver. Both are mechanical: no
design, no population, no reference, no model call. Both were found by measuring
the audit column against a golden suite whose stimulus was digest-verified for
the first time -- see `TRIPLE.md`'s correction -- which made seven convictions
visible that a foreign suite had hidden.

And neither reads the audit column to decide what to change. The rule in each
case is stated without reference to which checks convict: one says a verdict
over zero rows is not a verdict, the other says a value of the wrong quantity is
not a comparison. Both then apply to every check that matches.

## 1. A strong existential over ZERO rows convicted

    trace   29 edges; the activation holds only at the last one
    window  rows = [edge 28], closed = False, body = []
    check   eventually(w, ..., strong=True, after_activation=True)
    verdict FALSE -- "the obligation was never discharged"

Nothing was discharged because nothing was looked at. `after_activation=True`
reads `w.body`, which is `rows[1:]`, which is empty.

**This is not `strong`'s deliberate power**, which is the whole reason it is a
required argument: a liveness claim that can never be violated is worthless, and
"5 of 14 abstaining checks abstained for exactly this reason" is the measurement
that put it there. That power is over a window that HAS rows and does not contain
the response. Zero rows is a different thing.

### The rule is the module's own, applied where it was missing

Asked over an empty read set, five operators already refuse, in their own words:

    throughout  "had no rows to hold over ... so nothing was checked"
    stable      "had no rows to hold over"
    never       "the forbidden condition had no rows to occur in"
    pulse       "had no rows to pulse in ... so nothing was checked"
    nexttime    "nothing follows the activation; the trace ends there"

and four convicted:

    eventually  "the obligation was never discharged"
    until       "the release never occurred"
    sequence    "stalled at step 1 of N"
    nth         (delegates to sequence)

The four are exactly `_TAKES_STRONG`. So this is not a new policy; it is nine
operators being made to agree, and the argument needs nothing outside
`temporal.py`. `_nothing_read` is the shared verdict, and
`test_the_invariant_family_ALREADY_abstains_over_zero_rows` pins the five the
argument rests on, so the argument cannot quietly stop being true.

Measured: REQ-0061 convicts golden i2c on TP-0000 exactly here.

## 2. A value of the wrong QUANTITY convicted, and it looks like data

    REQ-0102's verdict, verbatim:
      "the raw `scl_i` and `sda_i` signals are not captured into `cSCL` and
       `cSDA`: expected (1, 1), observed (3, 3)"

`cSCL` is a two-stage synchronizer. Both stages high is 3. The contract declares
it a 1-bit flag, the check compares it to 1, and `3 != 1` convicts a design that
is doing exactly what the requirement says.

Five of the sixteen probes that bind on golden exceed their declared width:

    cscl  csda        declared 1, observed 0..3    two-stage synchronizers
    fscl  fsda        declared 1, observed 0..7    three-sample filter histories
    filter_cnt        declared 1, observed 0..3    the filter counter

Measured over all 482 traces, not a sample. Nineteen other ports -- `al`,
`busy`, `clk_en`, `cmd_ack`, `dout`, `dscl`, `dsda`, `idle`, `scl_o`,
`scl_oen`, `scl_sync`, `sda_chk`, `sda_o`, `sda_oen`, `slave_wait`, `sscl`,
`ssda`, `sta_condition`, `sto_condition` -- stay inside theirs. So this is not a
blanket objection to the contract's widths; it is five named quantities, and all
five are ones the specification describes as multi-bit.

`probes.py` already records the cause and refuses to treat it as a check defect:
the specification says "the three-sample histories `fSCL` and `fSDA`" and "a
filter counter, `filter_cnt`", and the probe stage minted all three at width 1
"beside its own `spans` quoting those very phrases."

### One defect, two paths, guarded once

`Env.sample` has refused a sample wider than `PROBE_WIDTHS` declares since the
width guard landed, so the **Python reference-model** route was protected. The
**RTL trace** route -- the one every audit figure on this branch is measured on
-- had nothing. `over_width_ports` is the same rule on the other path, and
`decide_rtl` folds it into the downgrade it already performs for a missing port
or a 4-state X: "a conviction that rests on an unknown value is downgraded to an
abstention, and only a conviction is."

Three choices in it, each pinned by a test:

  * **A declared width of 0 or absent is not a claim**, so nothing is enforced.
    The guard must not invent a bound the contract never stated.
  * **Scoped to the ports the check READS.** Otherwise one wide signal the check
    never mentions silences the whole testpoint -- the same scoping the
    unknown-value guard already uses, for the same reason.
  * **Decided ONCE over the whole recording, not per testpoint.** A 3-bit `fscl`
    reads 0 or 1 on plenty of testpoints and 0..7 on others, so asking per
    testpoint would make one check abstain where the register happened to go
    high and convict where it happened not to -- a verdict that depends on the
    stimulus rather than on whether the quantity is comparable at all.

### The value test cannot see a wide register that reads ZERO

    REQ-0100 convicts golden at edge 0 of TP-0000, and exactly ONE of the eleven
    ports it asserts disagrees:

        idle   observed 0   expected 1

`idle` reads 0 on **every one of 482 testpoints**. So the value test reports
nothing about it: a flag that is low and an 18-bit register that is zero are the
same number. `probes.py` had already recorded what it is -- "`filter_cnt` 14-bit
and `idle` 18-bit, where the check expects 0 or 1" -- and no test computable from
a trace alone could reach that.

**The simulator knows, and the trace was not carrying it.** `len(handle)` is how
`Env.sample`'s refusal already works, so `Env.finish` now records the sampled
width of every signal into the trace and `rtl_trace.declared_width_gap` refuses a
port whose declared width it exceeds. Measured on the regenerated golden suite:

    port         declared   simulator reports
    cscl              1         2
    csda              1         2
    fscl              1         3
    fsda              1         3
    filter_cnt        1        14
    idle              1        18

    ...and EIGHTEEN other ports agree with their declaration.

Six, against the five the value test found -- and the sixth is `idle`, which was
the last behavioural conviction with a mechanical cause. The figures reproduce
`probes.py`'s independently recorded 14 and 18 exactly.

Recorded for every sampled signal and not only refused ones, because the refusal
in `Env.sample` needs `PROBE_WIDTHS` on the reference model and **`full2`'s
`ref_model.py` does not define it** -- its 482-testpoint replay recorded
`width_refused: {}`. On the artifacts that actually exist the runtime guard is
inert, so the trace is the only place the fact can survive. A trace with no
`widths` map predates this and yields nothing, which is the same answer
`unknown_ports` gives for a trace predating `stimulus_digest`: unverifiable and
verified are different facts.

## What neither fix does

Neither removes a check, rewrites one, or lowers a number by choosing what to
look at. Each turns a conviction that rested on nothing into an abstention,
which is the outcome the tri-state exists for -- and an abstention is also a
separation LOST, so blindness can only move the wrong way. The trade, measured
on `full2` against a digest-verified golden control:

    configuration       span     blindness            audit
    before both fixes   0.9737   0.1454               16/45 = 0.3556
    after both fixes    0.9737   0.1457  (+0.0003)    11/44 = 0.2500

    with TRIPLE.md's two rules on top
    before              0.9737   0.1416                6/43 = 0.1395
    after               0.9737   0.1416  (unmoved)      3/42 = 0.0714

**Five spurious convictions for three ten-thousandths of blindness at baseline,
and none at all once the two rules are applied.** That is a far better trade than
the boundary fix, which bought its convictions at +4.5 points of blindness on
`full7`. Span is unmoved to four places throughout.

The three that stopped convicting are exactly the three diagnosed:

    REQ-0061   zero rows -- window opens at edge 28 of a 29-edge trace
    REQ-0102   cscl / csda read as flags, observed 3
    REQ-0096   filter_cnt / fscl / fsda read as flags

and its own verdict text had misled the diagnosis of REQ-0096 for a while: the
message reads "reset asserted but idle was 1, expected 1", which cannot be true.
Its comprehension iterates `expected.items()`, so the value it prints as observed
IS the expected one. The comparison it performs is correct; only the report is
wrong. Nothing in the pipeline catches a failure message that cannot be true, and
this is not a proposal that something should -- it is a note that the verdict
text is not evidence about the check.

### And one rule's effect was absorbed

Before these fixes the licence rule removed one conviction on its own
(15/45 against a baseline 16/45). After them it removes none (11/44 either way),
while keeping its whole blindness gain (0.1457 -> 0.1416). So what it appeared to
be buying on the audit column was two artifacts of these two defects, and its
real contribution is to blindness. The phase rule is unaffected and remains the
large lever: 11 convictions to 3.

Neither addresses `REQ-0055`'s `slave_wait` extent question, `REQ-0058`, or the
duplicated requirements (`REQ-0061`/`REQ-0102` and `REQ-0096`/`REQ-0100` are two
obligations minted twice, so the residue's size overstates the number of
distinct disagreements). Those are in `RESIDUE.md`.

## Verification

Both fixes were mutation-checked, each guard independently:

    temporal.py    eventually / sequence / until guard removed, one at a time
                   -> the ZERO_ROWS test names the operator that convicted
    rtl_trace.py   guard removed; `>` weakened to `>=`; an undeclared width
                   treated as 1; the read-scoping dropped; width asked per
                   testpoint instead of per recording
                   -> a different test fails for each

with `-B`, `PYTHONDONTWRITEBYTECODE=1` and cleared `__pycache__`. Full suite and
`ruff check specflow tests` clean.
