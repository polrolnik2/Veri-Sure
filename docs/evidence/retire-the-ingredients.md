# The degeneracy is real, and the fix is one lexical rule

## The trigger, stated precisely

Stratified iteration collapses back into a reference model **iff the published
thing is a computed function rather than a named signal.**

If round 2 hands the author `sSCL` as harness arithmetic over `scl_i`, then a
round-3 check reading it compares the design against *the harness*, not against
itself. That is the reference model assembled one stratum at a time, and
attribution goes with it: a broken filter in the design makes 28 downstream
checks fail, each pointing at its own requirement, and none at the filter. The
28 diffuse convictions are exactly the state this was meant to leave.

## What has to be published instead

A **name bound to a recorded column**, discharged by a check that reads the
design's own signal. Round 2's job is to *prove* the design's `sSCL` satisfies
the definition, not to compute a replacement for it. If the design does not
expose the signal, the stratum **stalls and says so** — it must never synthesise
the value, because a synthesised value is the degeneracy.

For the i2c bit controller that is a recording-list edit: `Env` already writes a
`dut_internal` block carrying `c_state, sda_chk, clk_en, dscl_oen`, and nothing
but the list stops it carrying `sSCL`.

## Assume-guarantee, and the move that saves attribution

The upstream oracle **guarantees** `sSCL`; the 28 downstream oracles **assume**
it. The load-bearing rule is what happens when the guarantee fails:

> **A violated assumption DISCHARGES its dependents. It does not fail them.**

If the design's filter is broken, REQ-0051 convicts and the 28 dependents go to
`None` — "my assumption was violated, I say nothing." That is the tri-state the
project already has, reused. The result is one named conviction and 28
abstentions, instead of 29 convictions pointing 29 different directions.

## Enforcement: retire the ingredients

Nothing above stops an author simply recomputing the filter from `scl_i` and
asserting against that. The rule that does:

> **Once a definition is published, its ingredients leave the vocabulary of every
> stratum above it.** `scl_i` and `sda_i` remain readable by the stratum that
> discharges the filter — REQ-0051 must read them, that is its whole job — and
> are retired for everything downstream.

A downstream check then *cannot* rebuild the filter, because the raw pin is not
in its namespace. This is lexical and mechanically checkable with a primitive
that already exists: `oracles.ports_read(oracle, contract)` scans an oracle's
string constants for declared port names. Refuse any oracle whose `ports_read`
intersects the retired set.

## The measured price on h3

| | count |
|---|---|
| frozen oracles | 54 |
| reading `scl_i` and/or `sda_i` | **18** |
| of those, deciding the same or better on the filtered value | **16** |
| of those, silenced by losing the raw pin | **2** |

So retirement would refuse 18 oracles as written, 16 of which the substitution
experiment shows work at least as well on the filtered signal. Two need an
explicit exemption. That is the whole cost.

## What this does NOT fix, said plainly

If the upstream check is **weak** — it passes a filter that is actually broken —
then 28 downstream checks inherit a false assumption and the corruption
propagates exactly as feared. Stratification does not make that impossible.

What it does is **concentrate** the corruption into one named requirement
instead of diffusing it across 28. That is the entire argument for it: not
soundness, but attributability. A wrong answer that names REQ-0051 is worth more
than a wrong answer spread over REQ-0027 through REQ-0116, because the first can
be checked and the second cannot.

Which also says where the effort belongs: the gates that admit a definition into
the next stratum — witness, liveness, must_fail — carry the whole weight, and
should be strictest exactly at depth 0.
