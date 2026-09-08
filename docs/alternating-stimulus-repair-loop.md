# The alternating stimulus/repair loop

*A design for `oracles_stage`, written from measurements on k1-dcfsm. Every state
and every routing decision here is computable WITHOUT a known-good design; the
audit columns are computed last, stored separately, and reach no prompt and no
routing decision.*

## Why alternating, and not two rounds

The oracle stage today has one response to a check that does not decide: mint a
testpoint, replay, ask whether it decided. Repair is a separate path a check
enters for a different reason, and `oracles_stage` makes the two **one-way** — a
rejected check can never afterwards be staged.

That ordering throws away the fact each move produces for the other:

| a move | what it produces | which is the other move's input |
|---|---|---|
| new stimulus makes a silent check DECIDE | the check now says something | if what it says is wrong, that is a repair objection |
| new stimulus makes a passing check CONVICT | **the check is DISPROVED** | repair it; do not book it as a loss |
| a repair NARROWS a check | it may stop deciding | that is a stimulus request, not a failure |
| a repair changes a window | its old evidence no longer applies | its testpoints must be re-run |

**Measured**: staging two testpoints against a 126-check set that was sound on
318 testpoints made **2 of its members convict the reference**. Under today's
pipeline those are silent regressions in a set whose entire selling point is a
zero audit. Under the loop they are the two best-evidenced repair objections the
round produced.

## The state of a check, and it is golden-free

Computed from replay against the spec-derived candidate population only:

    decides_on_evidence     testpoints in the current suite where it returns a verdict
    decides_on_candidates   how many candidate designs it decides on at all
    convicts_of_N           how many candidate designs it objects to

    SILENT       decides_on_candidates == 0        -> STIMULUS
    VACUOUS      convicts == 0                     -> REPAIR: strengthen
    BAND         1 <= convicts <= threshold        -> KEEP
    SUSPECT      threshold < convicts <= N/2       -> REPAIR: narrow
    OVER_STRICT  convicts > N/2                    -> REPAIR: narrow

`threshold` is the minority rule's, measured at 100% precision on soundness over
59 checks of a 13-design population. **The threshold is a property of the
population size and must be re-derived when N changes** — a 13-design cut applied
to a 7-design population is a different rule.

## The invariants, each of which cost something to learn

**1. A before/after over EVIDENCE must be taken inside ONE RENDER.** Two runs
sharing a design, a stimulus file and a tp_uid set can still differ in every row:
the probe declaration fixes `transactional_view`'s compression key. Measured
across two drivers, **all 318 shared testpoints differed at row 0 and 13 checks
flipped verdict — 7 gaining objections and 6 losing them.** The baseline for a
staged round is therefore *the extended run restricted to the pre-existing
tp_uids*, never the previous run. The stimulus digest does not catch this,
because the stimulus is identical and only the row shape moves.

**2. New stimulus must be replayed against the WHOLE candidate population.** The
routing signal is a conviction count over candidates. Simulate a staged testpoint
on the reference alone and the audit moves while the routing signal cannot, so
the loop has nothing to alternate on. This is a required edge, and it is N extra
suite runs per staged testpoint batch.

**3. Success for a staged testpoint is read FROM THE ROW.** Did the target state
occur — never "did a check then decide". `stage_unexercised` conflates these
today, in capitals, and the conflation hides the case where the stimulus worked
and the check is the defect.

**4. Row count is a count of DISTINCT SITUATIONS, not of time.** Consecutive rows
with identical inputs and outputs collapse, so a held condition contributes ONE
row however long it is held. A stimulus prompt that says "hold the condition"
scores nothing. Measured: three cache-inhibited loads held for eight cycles each
produced exactly 3 rows; rewriting the prompt to ask for twelve *varied* accesses
was **2-3x more productive per testpoint**.

**5. A check that loses soundness under new evidence is a repair candidate, not a
discard** — and the objection handed to its author must be the conviction count
over candidates, never the reference's behaviour, which `oracles_stage.py:66-73`
forbids quoting.

## What the loop is worth, measured so far

The population it addresses is real and was mis-sized. Of a 126-check sound set,
**104 members are sound and silent**; splitting them by why:

| | |
|---|---|
| decide on under a quarter of the suite | 43 |
| name a state the suite never enters | 3 |
| decide widely and never object — genuinely blind | 42 |

median decide-rate **88 of 318**, first quartile 32. So roughly half that
population is short of evidence rather than blind — against a prior sizing of
"3 of 50", which only counted checks that abstain outright.

**And the first alternation is a negative so far**: twelve staged testpoints
raised the thinnest state's distinct situations from 45 to 61 and made **2 of 104
silent checks speak, while disproving 2 others**. The gain and the cost cancel.
That is one alternation of a loop designed for many, on a suite whose staged
fraction is 12 of 330, and it is reported here as the current figure rather than
as a verdict on the design.

## What to build, in order

1. `reachability.observed()` over the run's own replays -> the pool, per state,
   with distinct-situation counts and a shortest reproducer per state.
2. The check state machine above, emitted as one JSONL record per check per
   round, with the audit in a separate key.
3. Routing: SILENT -> stimulus for its activation state; VACUOUS/SUSPECT/
   OVER_STRICT -> repair with the conviction count as the objection; BAND -> keep.
4. The re-run edge (invariant 2) and the one-render rule (invariant 1) as
   harness refusals, not conventions.
5. Alternate until no check changes state or the budget is spent, logging every
   transition with the move that caused it.
