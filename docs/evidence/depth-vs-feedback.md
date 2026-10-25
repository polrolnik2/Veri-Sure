# Depth is climbable. Feedback is not.

An oracle may read only ports, so whether a testbench can hand it the
specification's own vocabulary turns on two different structural properties of
the module — and they are not the same property.

* **Depth** — how many derivation steps separate an input port from the signal
  the spec names. Deep is fine: a chain that runs forward from the inputs can be
  recomputed by the testbench from the stimulus it drove, which is what
  `i2c_filter_derive.py` does and why it clears six of twenty golden
  convictions.
* **Feedback** — whether the signal sits in a mutually recursive group. There is
  no recomputing that from inputs alone; doing it means re-implementing the
  design, which is the reference model this project deleted.

`rtl_depth.py` measures both. Dependence counts control as well as data — every
signal named in an enclosing `if`/`case` guard — because a state machine's
dependence on its guards is the whole of what makes it hard to re-derive, and a
data-only graph scores an FSM as shallow while its author drowns. It is a
regex-level extractor, not an elaborator, pinned by reproducing a chain known by
hand from the source: `cSCL(0) -> fSCL(1) -> sSCL(2) -> dSCL(3) ->
sta_condition(4)`.

## The two i2c modules have opposite shapes

|  | bit_ctrl | byte_ctrl (child black-boxed) |
|---|---|---|
| ports / internals | 17 / 37 | 22 / 17 |
| max depth | **6** | **1** |
| largest recursive group | 11 signals | 13 signals |
| spec vocabulary that is internal | 39% | 35% |
| **of that, inside the recursive core** | **32%** | **72%** |

The internal *share* is nearly the same. What differs is what kind of internal.

**bit_ctrl is deep but mostly feed-forward.** The signals its spec names —
`sSCL`(2), `sSDA`(2), `dSDA`(3), `fSCL`(1), `cSCL`(0), `filter_cnt`(0) — form a
chain running forward from `scl_i, sda_i, clk_cnt`. Two thirds of its internal
vocabulary is computable from the stimulus. That is the tractable case, and the
one already measured.

**byte_ctrl is shallow and almost entirely recursive.** `sr, shift, dcnt, go,
cnt_done, core_cmd, core_txd, core_rxd, core_ack, c_state` are one 13-signal
strongly connected component sitting one hop from the boundary, and they carry
72% of the internal mentions. Nothing about them is deep. Nothing about them is
reachable either: to hand an author `sr` you would have to run the byte
controller.

A third of byte_ctrl's remaining internal vocabulary is the `ST_*` state names —
constants, depth `-`. No boundary observation ever answers "the FSM is in
ST_ACK".

## CORRECTION: "unreachable" was wrong

I first read the 72% figure as meaning byte_ctrl's vocabulary cannot be handed
to an oracle author at all. That does not survive contact with the design, on
three counts:

* **A cycle through an OBSERVABLE signal is not a barrier.** `go` is
  `(read | write | stop) & ~cmd_ack` -- ports only. It lands in the recursive
  core solely because the cycle runs through `cmd_ack`, which the trace records.
  You read the observation instead of solving the loop. Computing an SCC over a
  graph that treats outputs as opaque nodes overstates what is trapped.
* **`assign dout = sr;`** The most-mentioned internal in the spec (15 times) IS
  a port, by identity, with no delay or gating.
* **What a trace exposes is a CHOICE.** `Env` already writes a `dut_internal`
  block; for the bit controller it carries `c_state, sda_chk, clk_en,
  dscl_oen`. Nothing but the recording list stops it carrying `sr` or `dcnt`.

Recomputed with inputs AND outputs as recorded roots, every one of bit_ctrl's
19 internals is computable from the boundary. So feedback is not the wall the
first version of this note claimed.

## What the measurement does support

Only the narrower claim, which is about the AUTHOR rather than the harness:
**depth destroys per-requirement independence.** bit_ctrl's 28 bus-touching
requirements each had to re-derive the same 4-deep filter chain before saying
anything, so they could not be authored separately -- getting 28 right requires
getting one sub-derivation right 28 times, and the measured result was that it
happened zero times. byte_ctrl has max depth 1: nothing to rebuild, so nothing
couples the requirements to each other, and correspondingly no case for
decomposing anything.

That reverses the obvious reading of i2c. The bit controller is not hard
because it is deep in the sense of large; it is hard because depth is what
forces every requirement to solve the same problem again.

Run with `python docs/evidence/rtl_depth.py` from the repository root.
