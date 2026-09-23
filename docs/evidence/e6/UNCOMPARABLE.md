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

## What neither fix does

Neither removes a check, rewrites one, or lowers a number by choosing what to
look at. Each turns a conviction that rested on nothing into an abstention,
which is the outcome the tri-state exists for -- and an abstention is also a
separation LOST, so blindness can only move the wrong way. That trade is
reported below rather than netted out.

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
