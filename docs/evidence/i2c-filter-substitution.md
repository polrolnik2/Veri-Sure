# What the author never had, and what it is actually worth

The i2c bit controller's spec describes its input filter in prose. Normalization
collapses every mention of "filtered SCL" to the raw port `scl_i`, so the oracle
author writes checks against the pin the testbench drove rather than the value
the design acts on. Three separate prompt-level interventions failed to close
this: the whole spec as a tie-breaker (arm B/C) produced **zero** oracles that
reconstructed the filter, and the annotated linked requirements (arm D) moved
the golden-conviction count not at all.

This measures the remaining option — give the testbench the filtered value —
and it is the one that does not need the author to cooperate.

## The layer reads only what the testbench drove

`i2c_filter_derive.py` transcribes the chain from
`i2c_master_bit_ctrl.v:235-304`: a 2-stage synchronizer, a `clk_cnt >> 2`
divider, a 3-deep shift register, and a majority-of-three vote.

Every input to it — `scl_i, sda_i, clk_cnt, nReset, rst, ena` — is a declared
**input port**. It reads no DUT output and no DUT internal. That is what
answers the obvious objection: a layer computed from the stimulus states an
assumption about what was DRIVEN, not a belief about what the design did, so a
DUT whose own filter is broken still diverges from it and still gets convicted.
The failure signal survives. A layer that instead copied the DUT's internal
`sSCL` would erase it, and that is the version not to build.

## The derivation is checked, not asserted

Two pins, both over all 455 golden traces:

| check | result |
|---|---|
| `dscl_oen == prev scl_oen` — pins the sampling convention (values entering an edge) | 169858 match / 6 |
| `if (sSCL & ~dSCL) dout <= sSDA` — predicts a recorded output the derivation never reads | 511 match / 5 |

The second is the one that matters: it validates a re-implementation against the
design's own behaviour rather than against my reading of the source.

## What it buys: 20 convictions -> 15

Each frozen oracle is decided twice over the same traces — once as written, once
with `scl_i`/`sda_i` carrying the derived filtered values. Nothing else differs,
so a conviction that clears was caused entirely by reading the raw pin.

```
as-written       convicts  20/54
filtered         convicts  15/54     6 cleared, 1 newly convicting
filtered+lag1    convicts  17/54     REFUTED (below)
```

Cleared: REQ-0028, REQ-0057, REQ-0066, REQ-0086, REQ-0100, REQ-0101.

**The registered-output lag hypothesis is refuted.** `dout <= #1 sSDA` makes a
new value visible one edge later, so a check comparing a registered output
against its input should need the previous row's filtered value. Substituting at
offset 1 makes things *worse* — 17 vs 15 — and re-convicts two that offset 0 had
cleared. The one-cycle latency is not a second missing assumption.

## The 14 survivors are not an assumption problem

57 of 118 normalized requirements mention filtering or synchronization; 13 of
the 20 convictions are in that class, and only 5 of those 13 clear. So naming
the filter does not predict being fixed by it. Classifying the survivors:

| cause | n |
|---|---|
| the clause names an **internal** the trace never exposes to an oracle (`slave_wait`, `clk_en`, `cnt`, `sda_chk`) | 5 |
| a **multi-master / clock-stretch** scenario a single-master testbench cannot stage | 6 |
| neither | 5 |

(2 requirements are in both of the first two rows.)

Nine of fourteen point at two fixes that have nothing to do with what the author
was told: expose the traced internals to oracles, and stage a second master.
`dut_internal` already carries `c_state, sda_chk, clk_en, dscl_oen` on every
row — the oracles simply cannot see it.

Reproduce with `i2c_filter_subst.py` against a run's frozen `oracles.json` and
its golden traces. No model calls.
