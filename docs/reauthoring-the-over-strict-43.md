# Re-authoring the 43: over-strictness is real, and the cure has a price

*c1-i2c, 2026-08-30. Every number here is from artifacts in `docs/evidence/`;
nothing is projected.*

## Why this was run

The frozen 110 oracles decided against the **known-good** OpenCores i2c RTL read
**43 convictions of a correct design**. That is the largest carried risk in the
oracles-as-testbench plan: pointing a debug loop at RTL does not fix it, it just
asks the loop to "repair" a correct design toward 43 wrong demands.

The question: does re-authoring those 43 under the current [O] ordering --
staging before the gates every round, the `_unreached` gate, correspondence,
liveness, three verification rounds -- make them stop convicting the control?

**Method.** The real `run_oracle_stage`, unmodified, driven through a blocking
rendezvous port (`model_io.AgentPort`) with local Sonnet 5 agents standing in for
the gateway model. 240 calls, 592s of stage time once every answer was banked.
Inputs are c1-i2c's own frozen artifacts; normalization is NOT regenerated,
because re-rolling it renames the requirements and the 43 lose their labels.

**The control never gates.** `control_source=None`. No agent in the run saw the
golden RTL, directly or through a verdict. It is the held-out scoring instrument
and nothing else.

## What happened to the 43

| outcome | n | |
|---|---|---|
| **converged** -- golden now passes | 13 | 30% |
| **no check survived the gates** (`ORACLE_INVALID`) | 19 | 44% |
| **went silent** -- check exists, decides nothing | 6 | 14% |
| unchanged -- golden still convicted | 5 | 12% |

"Went silent" is counted separately from "converged" on purpose. A check that
stops deciding also stops convicting, and folding the two together is exactly
the accounting error that lets un-exercising a requirement read as progress.

So: **18 of 43 still decide anything at all** (down from 43), and among those,
over-strictness is 5/18 = 28% (was 100%).

## The whole set, both arms

Splicing the re-authored 43 back into the frozen 110 -- a requirement whose check
was rejected contributes nothing, which is the honest representation of a lost
check:

| | CONFORMS | VIOLATES | UNDECIDED | coverage | pass rate |
|---|---|---|---|---|---|
| BEFORE golden | 44 | 43 | 23 | 79% | 61% |
| BEFORE candidate | 42 | 45 | 23 | 79% | 59% |
| **AFTER golden** | **57** | **5** | **48** | **56%** | **95%** |
| **AFTER candidate** | **48** | **17** | **45** | **59%** | **85%** |

**Over-strictness fell 43 -> 5. Coverage fell 79% -> 56%.** Those are the same
event seen from two sides, and it is #99 measured on a labelled set: over-
strictness and vacuity are one expressiveness defect with two signs, so pressing
on one moves the other.

## The number that decides whether this was worth doing

Passing golden is half a measurement -- a check that abstains everywhere passes
golden too. The instrument is better only if it still tells the two designs
apart.

| | discriminating | inverted | separation |
|---|---|---|---|
| BEFORE | 9 | 6 | **+3** |
| AFTER | 12 | 3 | **+9** |

**Separation tripled**, and it attributes cleanly:

* all 9 original discriminating checks were **retained**, none lost;
* the 3 gained -- REQ-0002, REQ-0042, REQ-0117 -- are **all from the re-authored
  43**;
* 5 of the 6 inverted were **fixed** (REQ-0016, 0073, 0080, 0093, 0107); REQ-0007
  remains;
* but re-authoring also **introduced 2 new inverted** checks, REQ-0055 and
  REQ-0087. The move is net +6, not monotone, and a report that hid the two
  regressions would be describing a different run.

The golden/candidate pass-rate gap also widened from **2 points to 10**, which
materially changes the §4 gate's prospects (see below).

## What this does and does not license

**Does:** the [O] ordering plus correspondence is a real instrument improvement.
34 of 43 checks were rejected in round one and the gates caught genuine defects
-- an unlicensed `never(cmd_ack==1)` conjunct on a port its requirement never
mentions; a window opened on a raw `sda_i` edge rather than the spec's *filtered*
START, which would convict a design for correctly filtering a glitch.

**Does not:** it does not license shipping the coverage number. 25 of 43
requirements ended with nothing that decides. The pipeline got more precise by
becoming quieter, and on 19 of them by giving up entirely.

**§4's two-metric gate is vindicated as a design even as it fails this set.**
Pass rate alone would read 95% on golden and look excellent; coverage at 56%
is what stops that from being reported as success. Gating on both is what makes
the vacuous accept safe, and this run is the case that demonstrates it.

**§140 revisited.** The pass-rate gate previously had a 2-point window between
golden (61%) and candidate (59%) -- unusable. It is now 10 points (95% vs 85%).
Still not somewhere to put a fixed threshold without more designs, but a relative
ratchet is now viable where it was not.

## The defect re-authoring provably cannot fix

The specification never states `cmd`'s numeric encoding. It names START/STOP/
READ/WRITE, says the FSM "decodes `cmd`", and gives no value; `contract
["parameters"]` is empty; the design's `i2c_master_defines.v` (START=1, STOP=2,
WRITE=4, READ=8) is not part of the spec handed to the pipeline. Normalization
invented the numbers, inconsistently -- `cmd=1` is associated with all four
command names across different requirements, and six requirements gate on
`cmd=3`, which is not a legal one-hot code at all.

This run demonstrated that authoring cannot settle it. Three workers repairing
different checks reached three different conclusions about the same field: two
triangulated the correct encoding from sibling requirements, one "fixed" a check
by re-gating it to `cmd==3 (WRITE)`. The information needed to decide is not in
the material any of them was given.

All four of the encoding cases among the 43 (REQ-0006, 0030, 0066, 0121) ended
`ORACLE_INVALID` -- the correspondence gate caught the invented encoding and
refused it. That is the right direction to fail in, and the price is the
requirement rather than a wrong verdict.

**The fix is upstream:** normalization must not mint a numeric code for a field
the specification does not enumerate -- express the activation symbolically, or
emit `UNOBSERVABLE` naming the omission. A cheap interim guard: reject any
non-one-hot literal for a one-hot command field. `cmd=3` dies to that alone.

## Reproduce

```
scratchpad/asrt/drive.py --name full43 --workers 24 --resume   # the stage
scratchpad/asrt/score.py full43                                # vs golden
scratchpad/asrt/separation.py                                  # both arms
```

`--resume` replays every banked answer by `(stage, round_)` and pays only for
what is missing. This run survived four interruptions -- a wall-clock timeout, a
deliberate restart to widen the fan-out, a usage-limit kill of all 20 workers,
and a container restart -- without re-paying for a single answer.
