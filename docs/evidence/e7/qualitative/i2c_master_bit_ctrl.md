# i2c_master_bit_ctrl: what the errors are (luna12–15, 16 generated designs + 4 repaired)

**Method.** Open-loop traces restricted to the 669/1810 testpoints that start with a reset step, edges ≥1. Closed loop: I re-simulated all 20 designs with the updated `closed_loop.py`, which resets before every testpoint (scratch `qual/i2c_master_bit_ctrl/clwork`). Directed closed-loop tests at clk_cnt=7 give each design's phase table, and I ran the 4 ref models through the same tests. To attribute disagreement, I built golden-based "composite" models that carry one design's readings, then dropped one reading at a time (leave-one-out, LOO). Scripts and data are in `qual/i2c_master_bit_ctrl/`.

**Two golden quirks inflate the headline numbers.**
- **Golden never resets `dout`, and testpoints run back to back**, so golden's `dout` carries over from the previous testpoint. On reset-first testpoints this causes **68% of all design-vs-golden edge disagreement**. Edge agreement goes 0.26→0.76 and TP agreement 0.07→0.25 once golden's `dout` is reset ("gB"). All 20 designs and all 4 ref models reset `dout`.
- **Golden resets `cSCL/cSDA` to 00**; all 20 designs and all 4 refs reset them to 1. When clk_cnt<4 this produces a filter glitch after every reset: a fake sSCL rise, a fake STOP and an `scl_sync` reload. It costs +1.4 pts edge and +6 pts TP in open loop, and changes 63% of closed-loop testpoints. "gC" = gB plus this fix.
- After both corrections the arms are identical: edge 0.769 (generated) vs 0.770 (repaired), TP 0.317 vs 0.313.

## 1. Error modes (vs gB; share = LOO loss of composite agreement / disagreement, pooled, gen / rep; LOO overlaps, composite explains 75% / 78%)

| Mode | Design vs golden | Prevalence gen / rep (refs) | Share gen / rep | Example (design, stim, TP, edge) |
|---|---|---|---|---|
| M1 Phase table: windows 1 phase not 2; extra ack phase; START lead short | START SDA-low hold, READ/STOP SCL-high = 1 clk_en phase (golden 2); ack one phase after the last level change (golden: same edge); SDA falls 1–2 phases after decode (golden 3) | START hold 14/16, 4/4 (refs 4/4); STOP 16/16, 3/4 (4/4); READ 13/16, 3/4 (2/4); WRITE 10/16, 2/4 (2/4); trailing ack 9/16, 3/4 (3/4); short lead 10/16, 2/4 (4/4) | 53% / 62% (START largest) | luna12.r0, luna12, TP-0002, e67: golden `start_e` holds scl_oen=1/sda_oen=0; r0 already scl_oen=0 with cmd_ack=1 |
| M2 Level `slave_wait` (+ FSM gate) | `scl_oen & ~sSCL`, not golden's release-edge latch, so the design stalls whenever SCL is low while released | 20/20 (refs 4/4); gate 7/16, 4/4 (refs 4/4) | 34% / 50% | luna15.final, luna12, TP-0035, e70–86: SCL held low while idle; golden starts READ (scl_oen 1→0, e70); final frozen at 1 until e86 |
| M3 SCL kept in first phase | WRITE/READ leaves SCL released, so SDA falls with SCL high (a self-made START) | 2/16, 2/4 (ref14) | 4% / 16% | luna14.final, luna12, TP-0000, e3: golden (scl,sda)=00, final 10; al=1 from e11 |
| M4 Short input pipeline | 1-stage sync (7/16, 1/4; ref14); combinational sSCL (18/20) and sta/sto (20/20): busy/dout 1–3 edges early | see left | 6% / 6% | luna12.r0, luna12, TP-0031, e30: busy=1, golden 0 |
| M5 clk_en=0 at reset / when disabled | first tick after reset one phase late | reset: 0/16, 1/4 (12.final; ref12, ref14). Disable: 4/16, 1/4 (14.final; ref14); 13.final repaired it toward ref13 | 0 / 9% (luna12.final 25%); disable variant negligible | luna12.final reset branch |
| M6 Sticky `al` | held until reset (or START); 12/20 designs deadlock after any arbitration loss | 11/16 (8 deadlock), 4/4 (4) (refs 3/4) | 2% / 4% here; ~22% of al edges over all TPs, carried over between TPs | luna12.r0, luna12, TP-0054, e72: al=1 after golden's pulse ended |
| M7 False arbitration | `sda_chk & ~sSDA` without "SDA released", so al fires on the master's own 0 bit | 6/16, 2/4 (0/4) | 1% / 1.5% | luna15.r0, luna15, TP-0010, e236: din=0, sda_oen=0, al 0→1 |

**Root cause, spec class and whether the ref/checks encode it.** Class (a) = misread; (b) = ambiguous; (c) = silent or contradicts golden.
- **M1.**
  - *Root cause:* the generator turns each clause of a sequence into one phase (the luna12 generator's log plans a fixed number of phases per command, one per clause), so every level lasts one tick.
  - *Class:* (b). The text gives the order of changes, not their durations. Two exceptions favour golden. For WRITE, "When the FSM reaches the **stable high phase** of a WRITE bit, it asserts `sda_chk`" means release and stable-high are separate phases. For the ack, "pulls SCL low **and** asserts cmd_ack" and "returns to idle **and** pulses cmd_ack" mean the ack is not a separate step. For START lead, the I2C rule "SDA changes only while SCL is low" gives SDA-before-SCL. START hold and STOP length follow only from the OpenCores convention (4 phases per bit, 5 for START), not from the description.
  - *Ref models:* all 4 encode the short START/STOP, 3/4 the extra ack phase. Repair copied ref12's and ref14's tables exactly; 0/16 generated designs match their run's ref table.
- **M2.**
  - *Root cause:* the generator dropped "just" from "asserted when the master has **just released** SCL high … but sSCL remains low". It also built "While `slave_wait` is active … the FSM does not advance" as an explicit gate.
  - *Class:* (a). "just released" plus "remains active … until SCL is released" describes golden's latch. The gate alone is harmless (0.2% of edges on golden).
  - *Ref models:* all 4 encode the level form and the gate. Repair added the gate in luna13/14/15.
- **M3.**
  - *Class:* (b). The spec is silent on SCL at WRITE/READ start; the I2C rule justifies driving SCL low first.
  - *Ref models:* ref14 encodes it, and luna14's repair deleted `scl_oen<=0` from wr_a/rd_a.
- **M4.**
  - *Sync depth:* (a), "first captured into **two-stage** registers cSCL and cSDA". The contract's 1-bit `cscl` probe invites a single register.
  - *Registered sSCL/sta:* (c). The spec writes `sta_condition = ~sSDA & dSDA & sSCL` as an equation; golden registers it.
- **M5.**
  - *Class:* (a), explicitly contradicted: "When reset is active, … when the core is disabled … cnt is loaded from clk_cnt and **clk_en is asserted**".
  - *Ref models:* purely ref-pulled (the luna12 repair log cites the reference model's post-reset clk_en of zero).
- **M6.**
  - *Root cause:* `al` was treated as a status latch (the luna13.gen2 log treats a sticky flag as the canonical form). The reset list's "arbitration lost is cleared" encourages this.
  - *Class:* (b), tilted to golden. `busy` gets set/clear wording; `al` is only "asserted when <condition>", and the FSM's return to idle removes the condition.
  - *Ref models:* ref12/13/14 sticky. luna15 is sticky despite its pulse-like ref, so this is also a generator habit.
- **M7.**
  - *Class:* (a), "asserted when the controller **releases SDA high** but the filtered SDA line is observed low".
  - *Ref models:* the refs are right. Repair fixed it only in luna15.

## 2. Hypotheses

- **H1 (residual errors where checks are silent): REFUTED as framed; the checks are wrong.** I used the repo's hand-bound golden audit (`results/*/score_bound.json`, the checks that golden itself fails).
  - Of generated designs' failing checks, 69% are checks golden also fails; for repaired designs, 64%.
  - Of the 23 checks repair turned from fail to pass, 18 (78%) are checks golden fails.
  - luna15.final passes every decided check, including 14 that golden fails.
  - So residual errors sit where checks endorse the misreading, not where checks are silent.
- **H2 (repair pulls toward the ref model): SUPPORTED for luna12 and luna14, REFUTED for luna13 and luna15.** Edges where r0 and final differ, own stimulus:

  | Run | Edges changed | Main change at those edges | Ref agreement r0→final | Golden agreement r0→final |
  |---|---|---|---|---|
  | luna12 | 24.9% | 81%: golden→ref-only | 0.75→0.98 | 0.88→0.70 |
  | luna14 | 24.3% | 59%: golden→ref-only | 0.74→0.90 | 0.85→0.72 |
  | luna13 | 6% | 50%: moved to golden | 0.80→0.79 | 0.76→0.79 |
  | luna15 | 10% | 52%: both→neither | 0.93→0.86 | 0.83→0.81 |

  In luna12 and luna14 the repair transplanted the ref FSM tables and the ref clk_en values.
- **H3 (common mode): SUPPORTED.** One small set of readings (M1+M2+M4) explains 75–78% of both arms' disagreement. All 4 ref models share them, because the same model wrote them from the same spec. Level `slave_wait` (20/20), combinational sta/sto (20/20) and the short STOP window (19/20) are near-universal.
- **H4 (what repair fixes and breaks).**
  - *Fixes:* the `sda_oen` term in arbitration (12, 15); M7 (15); STOP window 2 phases (15); WRITE/READ windows 2 phases and no extra ack phase (14); clk_en asserted while disabled (13, matching ref13).
  - *Breaks:* WRITE window 2→1 phase (12); extra ack phase on all commands (12) and START (14); shorter START lead (12, 14); M5 (12, 14); M3 (14); FSM gate (13, 14, 15).
  - *Net golden agreement:* 12: 0.84→0.65; 13: 0.75→0.76; 14: 0.86→0.75; 15: 0.86→0.86.
- **H5 (patching style): structural transplant or local special case; repaired code is qualitatively different.**
  - *Transplants:* luna12 rewrote the FSM (−98/+38 lines); luna14 made 26 hunks.
  - *Local patches:* luna13 limited `al` to `ST_WRITE_C` and changed the counter reset; luna15 made STOP_B wait for its own release and changed the majority formula to include cSCL.
  - Simulation-only `initial` blocks appear in 3/4 finals and 0/16 generated designs.
- **H6 (residuals more timing-like after repair): REFUTED.** Closed loop with per-testpoint reset, vs gC:

  | Arm | Exact | Timing-only (order equal) | Functional |
  |---|---|---|---|
  | Generated | 0.23 | 0.28 | 0.50 |
  | Repaired | 0.22 | 0.19 | 0.59 |

  Per job (r0→final): luna12 functional 0.28→0.66; luna14 0.62→0.70; luna13 unchanged; luna15 is the exception (0.43→0.32).

## 3. Qualitative difference between the arms

The *kinds* of error are the same: the same readings explain both arms equally (75% vs 78%), and no new error mechanism appears. The *source and mixture* differ.
- **Generated designs** are independent draws from the generator's habits. They have varied phase tables, mixed sticky/pulse `al`, and some plain mistakes (M7).
- **Repaired designs converge on the run's ref model,** including its misreadings:
  - the exact ref FSM table (2/4 finals vs 0/16 generated);
  - clk_en values against explicit spec text, and keep-SCL;
  - the slave_wait gate (4/4 vs 7/16);
  - deadlocking sticky `al` (4/4 vs 8/16).
- Repair fixes only bugs on which the ref was right.
- Repair also adds patterns no generated sample contains: `initial` blocks, special-cased states, and filter-formula hacks. In closed loop these leave more *functional* (order-changing) residuals.

## Justifiable readings (share of disagreement closed)

| Reading | Textual justification | Share closed |
|---|---|---|
| Edge-qualified, latched `slave_wait` | "has just released … remains active … until SCL is released" (a) | 34% gen / 50% rep of post-artifact disagreement |
| Two phases per SCL-high window; ack on the last change | "stable high phase"; "pulls SCL low and asserts"; "returns to idle and pulses" (partial b) | Part of the 53–62% that M1 accounts for; START hold/STOP length not derivable |
| clk_en asserted during reset and disable | Explicit (a) | 9% rep (25% of luna12.final) |
| Two-stage synchronizer | Explicit (a) | Part of 6% |
| Drive SCL low before changing SDA | I2C rule (b) | 4% gen / 16% rep |
| `al` is a level ("asserted when"), checked only when SDA is released | (b) and (a) | ~3% here, but removes the deadlocks |
| Reset only the listed state (no `dout` reset) | (a) | 68% of raw out/ disagreement, but only a back-to-back-simulation artifact |
| Golden's 00 sync reset | None: no reading reaches it (c) | — |

## Could not establish
- LOO shares overlap and do not sum.
- About 22% of disagreement stays unexplained; luna13.gen3 (27% explained) and luna14.gen2 (30%) have bugs my tables cannot model.
- I did not run the shipped checks myself; H1 uses the repo's hand-bound golden audit lists.
- Results are measured against my regenerated closed-loop traces, not the coordinator's corrected ones.
