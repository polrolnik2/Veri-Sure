# The loop repaired a design: 19 failing requirements to 5

The first productive edit in six sessions. A Sonnet agent drove the real
`_EditSession` against the paced 90-check instrument on the ChipVerilog codex t1
candidate, with the golden RTL withheld, a 6-trial budget and 40 rounds.

```
                FAIL  UNCOVERED  passing
  before          19         25       46
  after            5         27       58
  trials used   4 of 6      rounds 34
```

## What it found, and it is the defect this project has been documenting all along

The candidate declares its own command encoding, and **the four values are
reversed against the specification's**:

```
  candidate     CMD_WRITE=0001  CMD_READ=0010  CMD_STOP=0100  CMD_START=1000
  i2c_master_defines.v   START=0001     STOP=0010    WRITE=0100     READ=1000
```

START and WRITE are swapped; STOP and READ are swapped. This is the same defect
class `docs/evidence/ab_defines_score.py` recorded across the benchmark -- nine
of nine generated designs guessed the encoding, eight with READ and WRITE
transposed, because the description's prose orders the commands "START, STOP,
READ, WRITE" five times against its port list's single contrary ordering.

The agent never saw the defines file or the golden design. It reached the
encoding from the recorded traces and the block sources alone, and the values it
wrote match the specification exactly.

## Honest accounting of the improvement

Fifteen requirements left the FAILING set. **Twelve of them became passing; two
went UNCOVERED** -- their checks stopped firing rather than being satisfied,
which is not a repair. Uncovered rose 25 -> 27 and passing rose 46 -> 58, and
those two numbers are the whole story. One requirement, REQ-0030, moved the
other way: it was not failing before and is now.

So the defensible claim is **twelve requirements repaired, two silenced, one
newly broken**, not "fourteen fixed".

## THE RATCHET ALMOST THREW THE FIX AWAY

The accept criterion is the per-testpoint mismatch count, and on the commit that
repaired twelve requirements it moved **104 -> 103**. One testpoint. Had it gone
to 105 the commit would have been rolled back under the regression guard, and
the encoding repair -- the single most valuable edit any session has produced --
would have been discarded.

Plan §6.2(a) predicted exactly this: "a fix that halves the divergence on one
requirement without flipping its verdict shows as ZERO progress, and the loop's
accept/rollback would discard it". It is now measured, and the fix landed on a
one-testpoint margin. The ratchet should be failing (requirement, testpoint)
pairs, as §6.2(a) proposed; it is still `sim_mismatch_cnt`.

A second commit latched at 103 -> 103 (equal is not "increased", so it is
accepted). The agent's own summary reports that commit as NOT latched, and it is
wrong: `assign scl_sync = dSCL & ~sSCL & scl_oen;` is in the shipped RTL. An
agent's account of its own session is not evidence; the trajectory is.

## What the run did NOT have

Run 5 predates three later fixes, so its evidence was worse than what is now
shipped: VCD transitions were reported one sample (10ns) late, `block_internals`
was a flat unjoined bag rather than a causal chain from the failing signal, and
there was no `edit(old_text, new_text)` -- so every change to the 4713-character
FSM block was a full retype. It succeeded anyway.

That cuts both ways. It is evidence the loop can work on thinner evidence than
the current build provides; it is also the reason the five sessions before it
are not a fair baseline for those tools, and no claim should be made that the
newer evidence path is what produced this.

## The five that remain

REQ-0009, REQ-0030, REQ-0042, REQ-0066, REQ-0095. Two of them -- REQ-0030 and
REQ-0095 -- are the known filtered-bus latency residue from
`docs/evidence/repair5.py`, which convict the GOLDEN design too and are false
demands. The agent spent its last two trials on REQ-0030 and both attempts
regressed, which is the expected outcome of chasing a check that a correct
design also fails.
