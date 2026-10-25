# i2c_master_bit_ctrl, luna12: checks arm vs model arm

**Basis.**
- **Start:** `rtl_generated.sv`, scoring 77/11/15. Mode labels M1–M7 are those of `../qualitative/i2c_master_bit_ctrl.md`.
- **Edge counts:** open loop on luna12's own stimulus, 91,204 edges, whole output vector. The start matches golden on 15.5% of edges and the ref model on 66.3%.
- **Δ golden/ref:** points of change when that one edit alone is applied to the start (a scratch script, not committed). Applied together, the decomposed edits reproduce both finals' traces exactly.
- **Golden's verdicts:** the run's hand-bound audit (a run artefact, not committed; 29 checks golden fails).
- **Golden fails 10 of the start's 11 failing checks**; the exception is REQ-0131.

| arm | main edits | requirements repaired / broken | Δ golden / ref | class |
|---|---|---|---|---|
| **checks** 87/1/15 | Decode drives SDA: READ sets 1, WRITE sets din; READ_C releases SDA (`rtl.sv:248-255,311`) | +0025, 0088, 0137 (golden fails all three) | −0.04 / +0.30 | b |
| | WRITE_A releases SCL (`:317`). SCL stays high for 3 ticks (golden: 2). After a STOP, the WRITE has no SCL-low phase (directed test, `phase/`). | +0029 (golden fails). The editor's stated reason: scl_oen should stay released until the external SCL rises. | −0.02 / +1.07; scl_oen −1.59 | b (= M3) |
| | `clk_en = cnt_zero & ~slave_wait`, combinational, and the FSM ticks on it (`:98,241`). Hold is placed before reload (`:177`). `clk_en_r` is now dead. No tick on disable or scl_sync, against "clk_en is asserted". | **Commit 1** (probe mask): +0054, 0115 (golden fails both); broke 0052/0118/0119 (golden passes all three). **Commit 2**: restored those three; REQ-0054 failed again. | **−0.79 / −4.36** | b→e |
| | `al` as a one-cycle pulse (`:228`); `sda_oen` arbitration qualifier; sda_chk←1; post-al idle hold dropped | +0123, +0079 (golden fails both). The hold drop changes ≤0.01 pt of outputs. | pulse +1.04 / −1.17 | a; hold drop: c |
| | Probes `fsm_active` and `in_write_sequence` ANDed with `nReset && !rst` (`:107,117`). The editor's stated reason: no sequence should count as active on the reset edge. | +0027, +0121 (golden fails both) | 0 / 0 | **c** |
| | **Net** | **10 repaired, 9 of which golden fails; 0 broken.** Stalled on 0054: 6 unlatched commits repaired it. Four broke 0052/0118/0119 (or 0052/0119/0134), which golden passes. | 17,696 edges changed: golden only 1,482, ref only 4,259, both 537, neither 11,418. Net **+0.63 / −3.67** | |
| **model** 81/7/15 | ref_model.py's decode row, verbatim (`ref_model.py:152-173` → `rtl.sv:251-254`). Each command's first level moves to decode; SDA leads SCL by 2 ticks (golden: 1). | +0025, 0029, 0088, 0137 (golden fails all four); broke 0076 (golden fails) | **−0.25 / +6.80**; scl_oen −4.58 | b |
| | ref's counter: clk_en reset 1→0; order scl_sync > slave_wait > cnt==0 (`:167-190`; `ref_model.py:29,242-255`). The editor's stated reason: the reference model requires clk_en to be 0 there. | +0131 (golden passes) | reset −0.10 / −1.44 | e (= M5) |
| | `sda_oen` qualifier (redundant here); al detection moved before the hold, so al stays sticky (M6); READ_C; one-line reformat | none | 0 / 0 | d |
| | **Net** | **5 repaired (4 golden fails); 1 broken (golden fails).** | 10,375 edges changed: golden only 293, ref only 7,087, both 310, neither 2,685. Net **−0.25 / +5.48** | |

**Did the model arm copy ref_model.py's phase table?** It copied only the decode row and the counter block. Its reasoning aimed at more: a rewrite of the whole FSM to match the reference model exactly. At least 8 commits carried a ref-style 3-state table (#29, #66, #73, #97, #106, #158, #168, #178).
- **None latched.** Each fell to 75–77 passing.
- **They broke** REQ-0002/0007/0055/0086/0104/0118/0136, of which golden fails only 0104.
- **The original final** has that table and fails 0007/0055/0086/0118/0136. Why that older run kept it is not established here.
- **What stopped the transplant** was the latch rule, not the feedback channel.

Neither arm has `initial` blocks or macros.

**Why the checks arm gained 10 without moving toward golden.**
- **They are mostly checks golden fails:** 9 of the 10. The checks final passes 28 of the 29 checks golden fails (start 19, model 22). Neither final fails any check golden passes.
- **Three gains changed no behaviour:** two probe-only, one a no-op hold drop.
- **The behaviour edits serving the checks all lost golden agreement on scl_oen:** decode-time SDA, WRITE_A release and the combinational clk_en. The al pulse cancels them.
- **The dominant modes are untouched in both arms:** M1 (START hold and READ/STOP SCL-high stay 1 tick, golden 2) and M2 (level slave_wait).

**Arms compared.**
- **Model arm:** imported the ref's reading, including a clk_en reset the text contradicts. Ref agreement +5.5.
- **Moves both arms found:** decode-time SDA and READ_C, which the checks arm found without the model.
- **Same check, different routes:** for REQ-0029, the checks arm keeps SCL released in WRITE_A; the model arm drives SCL low at decode.
- **Moves only the checks arm made:**
  - probe-only gating, which is check-gaming (cf. sb luna14's shadow probes);
  - a clk_en/FSM timing rewrite, forced by the conflict between 0054/0115 (golden fails) and 0052/0118/0119 (golden passes);
  - the one golden-ward fix: `al` as a pulse, which removes the M6 deadlock.
- **Stalls:**
  - checks arm: on 0054 alone;
  - model arm: at 81 for round 3, with five commits that left the count unchanged and ref-table retries at −4 to −5.

**Could not establish.**
- Attribution inside a commit batch comes from the check source; I did not re-decide checks.
- "Golden not convicted" can mean pass or unjudgeable.
- I did not measure closed-loop effects per edit. cl_order went 14.5 → 9.8 (checks) and 14.3 (model).
- I did not find why 0054 still fails.
