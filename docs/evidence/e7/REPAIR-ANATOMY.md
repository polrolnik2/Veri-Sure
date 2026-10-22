# What the checks-only repair changed, output by output

`CHECKS-VS-ABLATION.md` found that repairing against the shipped checks does no better than
generating again. This looks inside the 10 checks-arm jobs:
- the editor's edits;
- the RTL that survived;
- the outputs it moved;
- the checks it satisfied.

Figures come from `e7_behaviour/repair_anatomy.py`, which writes `REPAIR-ANATOMY.json`.
- **Scoring:** open loop, every run's stimulus, golden X don't-care, as in `metrics.py`.
- **Edit counts:** from the editor logs, counts only. luna12 dc_fsm's log was lost.
- **RTL:** start → final diffs are quoted where useful.

## The short answer

**Repair does do things. They cancel.**
- **It makes real fixes,** where a check restates a spec sentence literally. These touch rare
  events, so they barely move edges; dc_fsm luna13 and luna14 gain 4 points of whole testpoints
  but only 0.1–0.3 of edges.
- **It also breaks things in two ways:**
  - where a check shares the generator's misreading, the fix goes the wrong way: sb luna14's
    store buffer, byte_ctrl's narrowed abort;
  - an edit made to satisfy one check changes an output no check is watching: byte_ctrl luna13's
    `dout`, −17 points.
- **Most of the editing never reaches the design.** Of 358 edit calls, 65 (18%) ended in a
  commit that latched. The rest were reverted, discarded or never committed. What survives is
  0 to 41 changed lines per job.

**Per output,** across all 95 (job, output) pairs, against the final's own start:

| final vs its start | pairs |
|---|---|
| better | 10 |
| worse | 38 |
| unchanged (within 0.05 points) | 47 |

Against the four fresh samples of the same job:

| final vs the fresh samples | pairs |
|---|---|
| above every one | 4 |
| below every one | 15 |
| inside their range | 76 |

Repair invents an error no fresh sample makes more often than it finds a fix no fresh sample has.

**The fresh samples and the repaired finals differ in kind.**
- **Fresh samples differ structurally.** On sb luna12 they span 44.6–56.4% of edges; on
  byte_ctrl luna12, 18.7–42.7%.
- **Repair changes the conditions of a few outputs locally,** chosen by the failing checks.
- **The outputs every design gets wrong are untouched** by repair: byte_ctrl's `sda_oen` near 53%
  because of the command codes, and bit_ctrl's `scl_oen` near 80%. These shared errors are what
  costs most, and the checks do not see them.

## Per job: what changed, and where the edits went

| job | edges changed | fixed | broken | still wrong | net | testpoints equal, change | requirements flipped to pass (read a spec output / probes only) | RTL lines changed (+/−) | edit calls: latched / reverted / discarded / never committed | commits latched / not |
|---|---|---|---|---|---|---|---|---|---|---|
| bit_ctrl luna12 | 22.6 | 2.6 | 2.5 | 17.5 | +0.1 | −1.2 | 10 (9 / 1) | +22 / −19 | 14 / 37 / 11 / 3 | 4 / 14 |
| byte_ctrl luna12 | 4.1 | 1.5 | 0.4 | 2.2 | +1.1 | +0.2 | 5 (5 / 0); 1 newly failing | +23 / −16 | 12 / 30 / 7 / 2 | 5 / 15 |
| byte_ctrl luna13 | 47.8 | 4.6 | 8.0 | 35.3 | −3.4 | −1.9 | 8 (8 / 0) | +11 / −8 | 20 / 57 / 23 / 7 | 11 / 20 |
| byte_ctrl luna14 | 25.2 | 0.9 | 1.5 | 22.9 | −0.6 | −0.3 | 8 (8 / 0) | +18 / −7 | 4 / 26 / 5 / 1 | 3 / 16 |
| dc_fsm luna12 | 3.6 | 0.0 | 3.1 | 0.5 | −3.1 | −5.9 | 1 (1 / 0) | +21 / −12 | lost | lost |
| dc_fsm luna13 | 1.1 | 0.3 | 0.0 | 0.8 | +0.3 | **+4.1** | 8 (8 / 0) | +5 / −4 | 4 / 0 / 0 / 0 | 1 / 0 |
| dc_fsm luna14 | 0.4 | 0.2 | 0.2 | 0.0 | +0.1 | **+4.0** | 9 (8 / 1) | +6 / −13 | 9 / 0 / 0 / 0 | 2 / 0 |
| sb luna12 | 2.2 | 0.0 | 2.2 | 0.0 | −2.2 | −1.0 | 3 (3 / 0) | +1 / −1 | 1 / 0 / 0 / 0 | 1 / 0 |
| sb luna13 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0 | 0 | 0 / 43 / 26 / 0 | 0 / 9 |
| sb luna14 | 59.5 | 0.0 | 59.5 | 0.0 | −59.5 | −65.9 | 37 (26 / 11) | +1 / −0 | 1 / 15 / 0 / 0 | 1 / 3 |

How to read the edge columns:
- They are percentages of all compared edges.
- **Fixed:** wrong at the start, right in the final, counting every output.
- **Broken:** right at the start, wrong in the final.
- **Still wrong:** changed, but wrong both before and after.
- **RTL lines:** counted on the delivered design, whitespace ignored.
- **Probes only:** the shipped check names no spec output, only internal signals the contract
  names.

## Per output

Outputs whose agreement with golden moved by at least 0.5 points. **Fixed** and **broken** are
the shares of that output's edges.

| job | output | start | final | fresh samples min–max (mean) | fixed | broken |
|---|---|---|---|---|---|---|
| bit_ctrl luna12 | `al` | 97.7 | **99.8** | 96.8–97.7 (97.2) | 2.10 | 0.03 |
| bit_ctrl luna12 | `scl_oen` | 83.3 | 79.2 | 76.4–83.3 (80.6) | 5.53 | 9.73 |
| bit_ctrl luna12 | `sda_oen` | 93.0 | 93.0 | 90.9–93.0 (91.6) | 3.56 | 3.55 |
| byte_ctrl luna12 | `ack_out` | 90.8 | 91.9 | 74.9–92.0 (84.0) | 1.27 | 0.11 |
| byte_ctrl luna12 | `sda_oen` | 52.6 | 53.8 | 52.6–54.5 (53.4) | 1.57 | 0.37 |
| byte_ctrl luna12 | `dout` | 82.1 | 81.5 | 36.5–82.1 (67.0) | 0.21 | 0.74 |
| byte_ctrl luna13 | `ack_out` | 79.3 | **82.3** | 46.9–79.3 (69.8) | 17.70 | 14.68 |
| byte_ctrl luna13 | `dout` | 78.0 | 61.0 | 35.8–78.0 (56.8) | 2.11 | 19.08 |
| byte_ctrl luna13 | `scl_oen` | 89.5 | 78.4 | 54.8–89.5 (73.3) | 3.49 | 14.55 |
| byte_ctrl luna13 | `sda_oen` | 54.1 | 52.5 | 51.2–54.1 (52.6) | 3.19 | 4.82 |
| byte_ctrl luna13 | `cmd_ack` | 99.7 | 98.8 | 97.8–99.7 (98.9) | 0.12 | 0.98 |
| byte_ctrl luna14 | `ack_out` | 72.8 | 62.1 | 57.1–74.9 (69.4) | 4.36 | 14.99 |
| byte_ctrl luna14 | `sda_oen` | 54.5 | **58.8** | 53.4–54.5 (54.2) | 7.41 | 3.05 |
| byte_ctrl luna14 | `scl_oen` | 59.2 | *57.1* | 59.2–59.9 (59.4) | 6.78 | 8.84 |
| dc_fsm luna12 | `biu_write` | 100.0 | *97.3* | 98.3–100.0 (99.6) | 0 | 2.68 |
| dc_fsm luna12 | `first_miss_ack` | 100.0 | *97.7* | 99.4–100.0 (99.9) | 0 | 2.31 |
| dc_fsm luna12 | `first_hit_ack` | 100.0 | *98.4* | 100.0–100.0 | 0 | 1.62 |
| dc_fsm luna12 | `dcram_we` | 99.2 | 97.6 | 97.6–99.2 (98.8) | 0 | 1.60 |
| dc_fsm luna13 | `tag_we` | 98.0 | **98.9** | 97.8–98.4 (98.1) | 0.93 | 0 |
| dc_fsm luna13 | `dcram_we` | 97.7 | 98.5 | 97.7–99.2 (98.4) | 0.83 | 0.01 |
| sb luna12 | `dcsb_ack_o` | 94.7 | *94.1* | 94.7–94.7 | 0 | 0.57 |
| sb luna12 | six `sbbiu_*_o` outputs | 67.2–74.5 | −1.3 each | | 0 | 1.3 |
| sb luna14 | nine bus and ack outputs | 100.0 | *57.1–94.7* | all 100.0 except `dcsb_ack_o` (97.6–100) | 0 | 5.3–43.0 |

Bold: above every fresh sample. Italic: below every fresh sample.
- **On bit_ctrl and byte_ctrl the outputs churn.** A few points of an output's edges are fixed
  while as many or more are broken, often on the same output.
- **On dc_fsm and sb, an output either gains or loses, almost never both.** The edits there are
  small conditions on rare events.

## What the surviving edits do

Each entry gives the RTL changes, then their effect on the outputs.

- **sb luna14** adds one line, `` `define OR1200_SB_IMPLEMENTED ``.
  - It switches the store buffer on; golden leaves it off. 37 requirements flip to passing,
    26 of them reading a spec output.
  - Every bus output falls 14–43 points, and none of the 59.5% of edges it changes is a fix.
  - The checks share the misreading (`CHECKS-FEEDBACK-QUALITATIVE.md`), so satisfying them is the
    error.
- **sb luna12** changes one condition, `if (sbbiu_ack_i)` → `if (sbbiu_ack_i && outstanding_store_r)`.
  - 3 requirements flip.
  - Seven outputs each lose 0.6–1.3 points, with nothing fixed.
- **sb luna13** has no surviving edit. Its 9 commits deleted live code that `find_signal`
  misreported, and none latched.
- **dc_fsm luna13** makes a spec-literal fix on rare events:
  - it confines the cache-inhibit request to `CLOAD`/`CSTORE`, drops a qualifier from the hit
    ack, and uses the registered `cache_inhibit_r` in `dcram_we` and `tag_we`;
  - 8 requirements flip, 0.3% of edges are fixed and none broken, and whole testpoints gain 4.1
    points.
- **dc_fsm luna14** makes another spec-literal fix:
  - it drops `!biudata_error`, `!ci_req` and `(!hitmiss_eval_r || dcqmem_cycstb_i)` from the
    `first_hit_ack` and `first_store_hit_ack` terms, removes `ci_req` from the miss test, and
    confines it to `CLOAD` in the RAM and tag writes;
  - 9 requirements flip. Edges fixed and broken are equal (0.2% each), but whole testpoints gain
    4.0 points, because each fix completes a testpoint.
- **dc_fsm luna12** changes 33 lines that assign `state`, `store_r`, `load_r`, `cache_inhibit_r`
  and `cnt`. This is the inserted wait state described in `qualitative-cf/or1200_dc_fsm.md`.
  - 1 requirement flips.
  - 3.1% of edges are broken and none fixed.
  - Three outputs end below every fresh sample: `first_hit_ack`, `first_miss_ack` and
    `biu_write`.
- **bit_ctrl luna12** makes six kinds of change at once:
  - `al` becomes a one-cycle pulse, and the arbitration test gains `sda_oen`. This is a real fix:
    `al` rises to 99.8%, above every sample.
  - The probe outputs `fsm_active` and `in_write_sequence` are ANDed with the resets. This
    changes no spec output.
  - `clk_en` is redefined as `cnt_zero & ~slave_wait_r`, and the counter reload moves below
    another branch.
  - SDA is driven at command decode.
  - `scl_oen` changes 0 → 1 in one state.
  - `sda_chk_r` is set to 1 instead of `din`.

  The last four together move `scl_oen` and `sda_oen` both ways: `scl_oen` −4.1 net (5.5% fixed,
  9.7% broken) and `sda_oen` ±0.
- **byte_ctrl luna12:**
  - `ack_out` is captured only on a write's ACK; the shift register loads its first bit; every
    `core_ack_r` test is gated with `ena`; NOP is handled.
  - `ack_out` +1.1, `sda_oen` +1.2 and `dout` −0.6, for a net of +1.1.
- **byte_ctrl luna13:**
  - The probes `ld` and `shift` are redefined combinationally, to the checks' reading. The shift
    register is clocked by the new `ld`/`shift`, so a probe edit changes the datapath.
  - `core_txd` muxes in `ack_in` during a write's ACK.
  - The abort is narrowed to `al_r && !core_ack_r`.
  - `ack_out` +3.0 (above every sample), but `dout` −17.0 and `scl_oen` −11.1.
- **byte_ctrl luna14:**
  - The abort is narrowed to the READ/WRITE states, against the spec's "treats i2c_al like an
    abort/reset condition", and a `stop_pending` latch is added.
  - `sda_oen` +4.3 (above every sample), `ack_out` −10.7, and `scl_oen` −2.1 (below every
    sample).

## Why so many edits change so little

1. **Most edits are thrown away.**
   - **Edit calls:** 358 across the 9 logged jobs.
     - 208 (58%) were in commits that did not latch and were reverted.
     - 72 (20%) were discarded before committing.
     - 13 were never committed.
     - 65 (18%) survived.
   - **Commits:** 28 of 106 latched.
   - sb luna13 made 69 edit calls and kept none.
2. **What survives is small and aimed at rare situations.**
   - **The failing checks describe narrow windows:** a cache-inhibited load, an ACK after a
     write, an arbitration loss.
   - **Small edits are enough to satisfy them:**
     - every final differs from its start in 41 RTL lines or fewer, counting added and removed;
     - on 6 of 10 jobs they change at most 4.1% of edges;
     - dc_fsm luna13 flips 8 requirements by changing 1.1% of edges.
3. **When an edit does reach frequent behaviour, fixes and breaks cancel.**
   - bit_ctrl fixes 2.6% of edges and breaks 2.5%; byte_ctrl luna13 4.6% and 8.0%; luna14 0.9%
     and 1.5%.
   - The latch counts requirements, not behaviour. An edit that flips a requirement latches
     whatever else it changes, as `dout` on byte_ctrl luna13 shows.
4. **Most changed edges were wrong for another reason and stay wrong.**
   - On bit_ctrl and byte_ctrl luna13 and luna14, 17–35% of edges change yet stay wrong. An
     output was fixed or broken, but another output on the same edge was already wrong.
   - On byte_ctrl that other output is usually `sda_oen` or `scl_oen`, wrong on about half the
     edges in every design because of the command codes (`BYTE-CTRL-CODES-POOL.json`).
   - A whole edge cannot become right until the shared error is fixed, and no check points at it.
5. **The checks reward the reading they encode, right or wrong.**
   - 76 of the 89 requirements flipped to passing name a spec output, so repair is not merely
     gaming probes.
   - It moves outputs toward each check's reading. That reading matches golden only where the
     check restates the spec literally (dc_fsm, bit_ctrl's `al`, byte_ctrl luna12's `ack_out`).
   - Where it does not, the move is the error (sb luna14, the narrowed aborts).

## Caveats

- **"Reads a spec output"** means the check's source names one. It may still mainly constrain a
  probe and use the output as context.
- **Edit fates are counted from the tool calls in the logs.**
  - An edit call is attributed to the next commit or discard.
  - luna13 byte_ctrl spans its six launches; the latched work of a crashed launch carried
    forward.
  - luna12 dc_fsm's log was lost (`luna12/editor-cf-checks/or1200_dc_fsm/NOTE.md`).
- **Per-output figures are open loop.** The closed-loop per-port order measure also falls
  against the start, by 4.8 points on average (`CHECKS-VS-ABLATION-ROBUST.md`).
- **One run per job.** The edits an arm happens to find decide much of its outcome.
