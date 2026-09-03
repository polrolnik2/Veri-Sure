# It does not degrade with depth. Between depth 0 and 3 it stops entirely.

h3's 118 requirements, bucketed by the deepest derived signal the requirement's
own text names:

| bucket | n | TRUSTED | ORACLE_INVALID | ABANDONED | NOT_ASSERTABLE | VACUOUS | trusted |
|---|---|---|---|---|---|---|---|
| ports only | 90 | 48 | 21 | 12 | 4 | 5 | **53%** |
| depth 0–1 | 7 | **0** | 4 | 3 | 0 | 0 | **0%** |
| depth 2–3 | 4 | **0** | 3 | 0 | 1 | 0 | **0%** |
| depth 4+ | 17 | 6 | 7 | 1 | 3 | 0 | 35% |

**Every requirement naming a signal at depth 0 through 3 was discarded — eleven
of eleven.** And among the survivors, convictions of known-good RTL run 17/48
(35%) for the port-only class against 3/6 (50%) at depth 4+, small-n but
pointing the same way.

## The mechanism is not a weakened upstream check. It is an ABSENT one

The natural reading — a deep signal's violation is diluted before it reaches the
ports, so the guarantee that watches it is weak — is not what the artifacts
show. The must-fail gate, which is the instrument for exactly that, flagged
**5 weak oracles in 118, all of them in the ports-only bucket and none at any
depth**. It has no discriminating power here and can neither confirm nor refute
dilution.

What the dispositions show instead is that the mid-depth requirements never
became checks at all: ORACLE_INVALID, ABANDONED, NOT_ASSERTABLE. So an
assume-guarantee scheme does not face a weak guard for `sSCL` — it faces **no
guard for `sSCL`**, because no oracle for it survived. That is the same fact
recorded in `fixpoint-not-a-graph.md` from the other direction: every definition
at depths 0 through 4 was discarded.

## A hypothesis this data refutes

Depth 4+ recovering to 35% suggested the real variable might be distance to an
observable rather than depth from the inputs — `clk_en` and `c_state` sit right
behind `scl_oen` and `cmd_ack`. Measured, that does not hold:

| signal | depth from inputs | distance to an output |
|---|---|---|
| sSCL, sSDA | 2 | **1** |
| dSCL | 3 | **1** |
| sta_condition, sto_condition | 4 | 1 |
| clk_en, c_state | 5 | 1 |

`sSCL` is exactly as close to an output as `clk_en` is, and its requirements
were discarded while `clk_en`'s were not. Output distance does not separate the
buckets, so that explanation is dead.

What is left, and is not yet measured, is whether the internal appears as the
requirement's SUBJECT or merely as context: "dout samples the filtered SDA" is
*about* `sSDA`, whereas "the counter holds while slave_wait is asserted" is
about a port with `slave_wait` naming the phase. That distinction, not depth or
observability alone, is the next thing to test.
