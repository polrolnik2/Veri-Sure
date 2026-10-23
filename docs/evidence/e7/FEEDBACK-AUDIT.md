# Was the editor's feedback right? Every commit, against golden

This audit asks two questions:
1. Is the feedback the checks-only editor gets on each evaluation correct?
2. What happens when a commit breaks a part of the design that was right?

**Method.** Every editing session is replayed exactly, and every design the editor submitted is
scored against golden. Each score is set beside what the editor was told. Figures come from
`e7_behaviour/feedback_audit.py` and `feedback_audit_report.py`, written to
`FEEDBACK-AUDIT.json` and `FEEDBACK-AUDIT-SUMMARY.json`.

**Replay:**
- **Sources:** the session's trajectory and editor log give every staged edit and every commit's
  verdict.
- **Edits are applied with the editor's own splice.** A replaced block's prior text is recovered
  from the recorded diff, or from the editor's own `read_block`, `focus` and `list_suspect_blocks`
  output when the trajectory truncated that diff. Each recovery is checked by recomputing the diff.
- **Coverage:** 8 jobs, 74 commits. Each replay reproduces the RTL its job delivered, and every
  edit resolves.
- **Correction:** an earlier version of this audit miscounted two bit_ctrl commits as exactly
  replayed. They had been scored as changing no output; both in fact changed outputs and broke
  something. The figures below include them.
- **Excluded jobs:**
  - luna13 byte_ctrl: its trajectory holds only the last of six launches;
  - luna12 dc_fsm: its logs were lost.
- 73 commits are scored. The 74th was rejected before simulation, so it has no verdict.

**Scoring** is as in `metrics.py`: open loop, golden X don't-care, probes stripped. For each
commit, the submitted design is compared with the accepted design it would replace, cell by cell,
where a cell is one output on one edge:
- **fixed:** the cell becomes equal to golden;
- **broken:** a cell that was equal to golden no longer is.

This is done on every run's stimulus, and separately on the run's own stimulus, which is what the
shipped checks see.

## The short answer

1. **The feedback is computed on the right design, but as a signal about behaviour it is no
   better than chance.**
   - The replay reproduces every final, so the editor was judged on what it submitted.
   - Commits whose passing count rose were net worse by golden 9 times and net better 6 times.
   - Commits whose passing count fell were net better 15 times and net worse 11.
   - No association: Fisher p = 0.34. On the run's own stimulus, p = 1.00.
2. **Almost every commit that changes behaviour breaks something.**
   - 53 of the 55 commits that changed any output broke a cell that was right.
   - In mixed commits, breaks are a median 48% of the changed cells (IQR 31–78%).
   - Only 2 commits were clean improvements, and both were rejected (+0.01 points of edges).
3. **When a commit breaks a part that was right, the feedback rarely says where.**
   - In 41 of the 53 breaking commits the editor was told some requirement BROKE. But the checks of
     the requirements it was told about read the broken outputs for only 35% of the broken cells.
   - In the other 12 it was told nothing broke.
   - **A breaking commit still latches if passing rises on net.** 16 did. In those, 92% of the
     broken cells were on outputs no reported requirement reads, and 8 of the 16 reported nothing
     broken.
4. **The gate filters big losses, not small ones.** Summed over commits, in points of edges equal
   to golden:

   | | gains | losses |
   |---|---|---|
   | accepted | +3.7 | −64.5 |
   | rejected | +12.8 | −326.0 |

   - **Most of the rejected loss is sb's:** −200 points on luna13 and −100 on luna14. On luna13
     the `find_signal` defect led the session to delete live code, and the gate rejected those
     commits.
   - **Most of the accepted loss is sb luna14's** configuration line.
   - **Without sb,** accepted gains and losses nearly cancel: +3.7 against −2.8. The gate
     rejected +12.8 of gains, over three times what it accepted, and −26.2 of losses.

## 1. What golden says each commit did

| golden's view | latched | not latched | mean change in edges equal, latched / not (points) |
|---|---|---|---|
| clean improvement (fixed, nothing broken) | 0 | 2 | — / +0.01 |
| mixed (fixed and broken) | 14 | 33 | +0.06 / −0.41 |
| regression (broken, nothing fixed) | 2 | 4 | −30.8 / −75.0 |
| unchanged (no output changed) | 1 | 17 | 0 / 0 |

Of the 47 mixed commits, 24 are net positive and 23 net negative. The gate latched 6 of the
positive ones and 8 of the negative ones.

## 2. Did the feedback point the same way as golden?

| passing requirements | golden net better | golden net worse | golden unchanged |
|---|---|---|---|
| rose (16) | 6 | 9 | 1 |
| unchanged (29) | 5 | 9 | 15 |
| fell (28) | 15 | 11 | 2 |

Judged on the run's own stimulus only, the counts are similar:
- rose: 7 better, 8 worse;
- fell: 13 better, 13 worse;
- p = 1.00.

Judged by edges equal to golden, counting changes of at least 0.05 points:
- rose: 5 better, 6 worse;
- fell: 10 better, 10 worse.

| module | commits | passing rose → golden better : worse | passing fell → better : worse |
|---|---|---|---|
| bit_ctrl | 18 | 1 : 3 | 6 : 2 |
| byte_ctrl | 39 | 3 : 3 | 9 : 7 |
| dc_fsm | 3 | 2 : 1 | — |
| sb | 13 | 0 : 2 | 0 : 2 |

## 3. Per job

| job | commits | latched | latched: clean / mixed net+ / mixed net− / regressions / unchanged | rejected: clean / mixed net+ / mixed net− / regressions / unchanged |
|---|---|---|---|---|
| bit_ctrl luna12 | 18 | 4 | 0 / 1 / 3 / 0 / 0 | 0 / 9 / 2 / 0 / 3 |
| byte_ctrl luna12 | 20 | 5 | 0 / 2 / 2 / 0 / 1 | 2 / 4 / 5 / 0 / 4 |
| byte_ctrl luna14 | 19 | 3 | 0 / 1 / 2 / 0 / 0 | 0 / 5 / 8 / 1 / 2 |
| dc_fsm luna13 | 1 | 1 | 0 / 1 / 0 / 0 / 0 | — |
| dc_fsm luna14 | 2 | 2 | 0 / 1 / 1 / 0 / 0 | — |
| sb luna12 | 1 | 1 | 0 / 0 / 0 / 1 / 0 | — |
| sb luna13 | 9 | 0 | — | 0 / 0 / 0 / 2 / 7 |
| sb luna14 | 3 | 1 | 0 / 0 / 0 / 1 / 0 | 0 / 0 / 0 / 1 / 1 |

## What this says about the editor's position

- **The gate is not a regression check.** Its notion of "broke" is a requirement changing verdict.
  The requirement that changes is usually not where the damage is: 35% of broken cells are on an
  output it reads. So even when the editor is told something broke, it is not told what.
- **The editor cannot use the feedback to tell good edits from bad ones.** The direction of the
  verdict is unrelated to golden's, so the edits that latch are close to a random choice among
  those submitted, as far as behaviour goes. That fits the near-zero net effect of repair in
  `CHECKS-VS-ABLATION-ROBUST.md`.
- **The edits are rarely clean.** 2 of 55 behaviour-changing submissions were pure improvements.
  This is golden's judgement of the edits, independent of the gate. But these are edits made to
  satisfy the checks, so this data cannot separate the quality of the edits from the quality of
  their targets. `REPAIR-ANATOMY.md` and the proposed ablations address that.

## Caveats

- **The commits are concentrated.** 57 of the 73 come from three jobs on two modules (bit_ctrl
  luna12, byte_ctrl luna12 and luna14). Commits within a job are sequential and not independent.
  dc_fsm and sb contribute 16.
- **Two jobs are missing:** luna13 byte_ctrl (11 latched commits) and luna12 dc_fsm.
- **Golden is scored open loop** on the pipeline's stimulus. The editor's checks run in the
  shipped testbench (closed loop, two-state Verilator). The own-stimulus view narrows the first
  difference, not the second.
- **The checks' own computation was not re-run.** The requirement counts are as the editor
  reported them.
- **Mixed effects are small on average:** +0.06 points of edges for latched mixed commits.
