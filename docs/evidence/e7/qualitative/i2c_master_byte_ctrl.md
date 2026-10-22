# i2c_master_byte_ctrl: what the errors are

**How I measured.** I re-simulated golden and all 14 designs with a 3-edge whole-design reset before every testpoint (`qual/i2c_master_byte_ctrl/hyb/traces_rst/`), because only 76/95/79 testpoints start with a reset step. The caveat matters: golden's traces with and without the reset differ on 92% of testpoints. With the reset, the designs' testpoint-exact rate rises from ≤0.9% to about 11%. Edge agreement stays low at 0–7%, so the module really is this far from golden. Closed-loop numbers below cover only the 250 testpoints that start with a reset step. Arms: generated = 9 gen + 2 r0 = 11 designs; repaired = 3 final designs.

**Main finding.** No design uses the supplied bit controller. 11 define their own `i2c_master_bit_ctrl` and 3 (luna13 gen1, gen2 and final) inline a responder. In all 11 logs that keep the first draft, that draft instantiated the child exactly as golden does. The format/lint gate then failed with "Cannot find file containing module". The generator answered by writing a stand-in, saying in effect that the lower-level controller was not available, luna13.final). I spliced the golden child under each design's byte FSM, mapping the command encoding. This hybrid removes **72%** of all cell disagreement: 87% for the 10 designs that hold the command and 36% for the 4 that pulse it. Edge agreement rises from 0–7% to 61–92% for 10 of 14 designs.

## 1. Error modes
Cost = disagreement removed by the fix, or a golden mutant carrying only that one mode. The gen/rep column counts designs out of 11 generated and 3 repaired.

| mode | design vs golden | spec sentence | gen/rep | cost | class · root cause · in ref/checks? | example (design, stim, TP, edge, port g/d) |
|---|---|---|---|---|---|---|
| A stand-in bit ctrl | SCL never driven (scl_oen held at 1); `i2c_busy` set by the START *command*; `i2c_al`=0; each bit done in 0–3 cycles | "does not directly implement the concrete START or STOP waveforms … Those operations are implemented in i2c_master_bit_ctrl" | 11/11, 3/3 | 72% of all disagreement (i2c_busy 17%, scl_oen 20%, sda_oen 14%, most of dout 29%) | **(a)**. The lint gate had no child source, so the generator believed it had to provide one, and a minimal responder looked harmless. **Yes, in both:** all 3 ref models treat the child as instant, with constant pads. 19 of 21 population models do the same, so pad-level checks (e.g. luna14 REQ-0030, "eight scl_oen rising transitions") were outvoted and excluded | luna14.r0, luna12, TP-0001, e3, scl_oen 0/1; luna13.final, luna12, TP-0000, e4, i2c_busy 0/1 |
| B command encoding | READ=0100, WRITE=1000 (golden: WRITE=0100, READ=1000); luna14 r0/final use binary | "bit-level commands such as START, STOP, READ, WRITE, and NOP" | 11/11, 3/3 | latent: about 21% of the 11 stub designs' disagreement if the child were used as-is | **(c)**. The designs coded the commands one-hot in the order the spec lists them. No codes appear anywhere in the spec, so golden's are not derivable. Not in ref/checks | luna12.gen3 hybrid: edge 0.35 with its own codes, 0.73 with mapped codes (non-reset traces) |
| C one-cycle command pulse | `core_cmd` falls back to NOP every cycle. The real child samples `cmd` only on clk_en, so commands are lost | "In ST_START, the FSM waits for core_ack"; on return to idle it "sets core_cmd to NOP" | 3/11, 1/3 | mutant: edge 0.23, cell mismatch 0.167; ≈13% of all disagreement (only once A is fixed) | **(b), the text favours holding.** NOP is named as an action only on the two transitions back to idle, so the command is a held register. A pulse seemed fine because every stand-in acks any non-NOP command on the next cycle. Ref models hold the command | luna12.r0 hybrid: edge 0.23 vs luna12.final 0.76 |
| D ld/shift on the same edge | `sr` loads or shifts on the edge the FSM leaves IDLE or sees core_ack; golden registers ld/shift, one cycle later | "When ld is asserted, sr loads…"; abort "stops shifting and loading, deasserts cmd_ack" (FSM always block) | 7/11, 1/3 | mutant edge 0.89 (dout 0.91); ≈2.6% | **(b), weakly favours registered.** The abort sentence groups ld/shift with registered FSM outputs. **luna12 and luna14 refs use the same edge; luna13's ref registers.** Repair pulled toward it: luna12 went from registered (r0) to same-edge (final) | luna12.final, luna12, TP-0000, e3, dout 00/a5 (r0 had 00) |
| E 8th shift in WRITE | shifts again on the last write bit | "If cnt_done is not yet asserted, shift is asserted … If cnt_done is asserted … moves to ST_ACK" | 5/11, 0/3 | mutant edge 0.96; 0.6% | **(a)**. The designs wrote one symmetric `shift = core_ack & (READ\|WRITE)` term. Refs are golden-like | luna12.gen1 hybrid, luna14, TP-0002, e93, dout 00/01 |
| F ack_out after writes only | `ack_out` not updated after a read byte | "For a write transfer … core_rxd is captured into ack_out"; port note: "meaningful **mainly** after write" | 2/11, 0/3 | mutant edge 0.82; 1.0% | **(b), "mainly" favours always capturing.** **luna12's ref captures after writes only**; luna13 and luna14 refs capture always | luna12.gen1 hybrid, luna14, TP-0009, e47, ack_out 1/0 |
| G repair breakage | the edit deleted the child's `dout` driver, so core_rxd floats (z), and deleted `ld_r<=1`, so din never loads | "receives the sampled bit through core_rxd" | 0/11, 1/3 | luna14.final: ack_out 94% wrong, dout 91% | **(a)**. The log shows the editor following the reference model's claim that core_rxd is always 0, and luna14's ref does tie core_rxd to 0. It is also a **rejected** candidate (passing fell from 65 to 59, so it did not latch) that the loop handed back anyway as its best | luna14.final, luna12, TP-0000, e4, dout a5/00 |

Minor modes:
- combinational instead of registered core_txd: 14/14, mutant 0.97. Class (b); "core_txd defaults to sr[7]" does not decide it.
- no din reload after START: 14/14, mutant 0.997. Class (c).
- active-high oen: luna12.gen3, and luna12's ref drives oen=0. Class (b); the `_oen` naming convention favours active-low.

## 2. Hypotheses
- **H1 visibility: REFUTED as an arm difference.** 0 of 131 failing-check instances across all 14 designs judge scl_oen or sda_oen, and only 2 judge i2c_busy. All 131 read internal probes. Ports that no failing check judges carry **58%** of generated designs' disagreement and **57%** of repaired designs'. The one shipped bus-busy check (luna12 REQ-0098) abstains on luna12.final.
- **H2 ref-model pull: SUPPORTED in intent, REFUTED in effect.** The logs show edits aimed at the ref: the core_ack probe rewritten to `core_cmd!=NOP`, core_rxd driven to 0, ld/shift made combinational. But at the cells where r0 and final differ on the run's own stimulus, final agrees with the ref *less often* than r0 did:

  | run | changed cells | final matches ref | r0 matches ref | final matches golden | r0 matches golden | final matches neither |
  |---|---|---|---|---|---|---|
  | luna12 | 164.6k | 47.8k | 52.6k | 45.1k | 50.1k | 52% |
  | luna14 | 345.5k | 32.8k | 77.3k | 16.4k | 180.9k | 89% |

  The edits are entangled with the stand-in's timing. Per port, only luna12 dout moved toward the ref (46.2→48.2%).
- **H3 common mode: SUPPORTED.** Mode A appears in 14/14 designs, all 3 ref models and 19/21 population models. The ref models agree with golden on only 1–6% of edges, about the same as the designs.
- **H4 fixes vs breaks:**
  - luna12 is churn. Over all three stimulus runs, dout is fixed on 7.7% and broken on 7.0% of edges, and sda_oen on 14.5% vs 13.7%. Under the golden child, its pulse→hold fix is a large hidden gain (edge 0.23→0.76).
  - luna14 fixes ≤3.8% per port and breaks ack_out (72%) and dout (22%).
  - luna13 has no r0, and its final is also a rejected candidate (RESUME.md).
- **H5 style:** small local patches: 22 changed lines in luna12 and 9 in luna14. No structural rewrites, and the stand-in was left alone (luna12) or damaged (luna14). One style appears only after repair: editing *probe* outputs to the ref model's expressions (luna14 `core_ack` and `shift`, luna12 `ld` and `shift`). Under the golden child, luna12.final (0.76) looks just like gen3 (0.74).
- **H6 timing vs function: REFUTED.** In closed loop, no design has any order-only testpoint. Every non-exact testpoint is a functional difference: 207/250 for most designs and 250/250 for luna12 gen2, gen3, r0 and final, in both arms.

## 3. Do the arms differ qualitatively?
Only a little. Both arms share mode A: the failure comes from the pipeline, which gave the generator no child, not from reading the spec. Both also share mode B and have the same share of errors that no failing check judges. Three things are specific to repair:
- It edits observation probes to match the ref's abstraction. That changes what the checks see, not what the design does.
- It imports the ref models' particular misreadings: the same-edge ld/shift in luna12, and core_rxd=0 in luna14.
- Twice it ships rejected, worse candidates (luna13, luna14), because the loop returns its best rejected attempt when nothing latches.

Its one real improvement, holding the command, only shows once the supplied child is used.

## Justifiable readings (share of all disagreement)
1. **Instantiate `i2c_master_bit_ctrl`; never define it.** Justification: "Internally, the module instantiates i2c_master_bit_ctrl with the instance name bit_controller" and "does not directly handle low-level SCL/SDA timing". Treat a missing-module lint error as a gap in the environment. This closes **72%** (≈46% using the child as-is, plus ≈21% that needs golden's codes, which no reading can justify). It includes "busy = bus START/STOP detection".
2. **Hold `core_cmd` until a transition.** The spec sets it to NOP only on the two returns to idle. ≈13%, once reading 1 is applied.
3. **ld/shift are registered FSM strobes** ("stops shifting and loading" sits in the FSM always block): ≈2.6%.
4. **ack_out is captured on every ACK** ("mainly after write"): ≈1.0%.
5. **No shift on the last WRITE bit** (stated outright): ≈0.6%.

Could not establish: the as-is/encoding split on reset traces; that 21% comes from the non-reset traces. Shares for modes C–F are single-mode mutant costs times prevalence; the modes may interact.
