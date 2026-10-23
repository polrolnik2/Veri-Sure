# A better latch, tested offline: does any golden-free rule agree with golden?

`FEEDBACK-AUDIT.md` found that the editor's latch has no detectable association with golden. A
commit is kept if passing shipped requirements rise, and that verdict's direction is unrelated to
golden's. This tests golden-free alternatives on the same audited commits, then on a held-out set.
Figures come from `e7_behaviour/latch_offline.py` and are written to `LATCH-OFFLINE.json` and
`LATCH-OFFLINE-cf-model.json`.

**Method.** Every commit is replayed exactly (`feedback_audit.py`). Each rule decides accept or
reject from what a run has, without golden. Golden then judges each commit by net output-edge
cells fixed minus broken, and each rule's decisions are scored against that.
- **Behaviour** is simulated on the run's own stimulus, open loop.
- **"Fresh samples"** are the job's three other generation-only designs, never the start.
- **Decisions are scored commit by commit,** not by replaying a whole session under the new rule.

## Pre-registration, and what happened to it

- **The primary rule, fixed before any result:** TARGETED. It keeps the current latch and
  additionally rejects a commit that changes outputs on any testpoint outside those of the
  requirements failing on the accepted design.
  - **It failed.** It accepts 1 commit of 73 on the checks arm and 2 of 93 on the model arm.
  - **Why:** almost every commit, good or bad, changes behaviour on testpoints whose checks pass
    (median 36 such testpoints per commit). "Don't touch what passes" does not separate good
    edits from bad ones.
- **Seven secondary rules** were compared on the checks arm. CONSENSUS-ONLY was the only one
  associated with golden: keep a commit if and only if its agreement with the fresh samples rises.
  It was chosen after the data were seen.
- **The held-out test, specified before it was run:** the model-feedback arm's commits, from the
  same starts but separate sessions with different edits.
  - **Hypothesis:** the change in agreement correlates positively with golden, and CONSENSUS-ONLY
    accepts commits that are more often net better than those it rejects.
  - **One secondary rule was named in advance:** CONSENSUS + passing does not fall.

## Results

**Checks arm** (where the rules were chosen): 73 commits in 8 jobs.

| rule | accepted | accepted: better / worse | rejected: better / worse | Fisher p | accepted gains / losses, points of edges |
|---|---|---|---|---|---|
| current latch | 17 | 6 / 10 | 20 / 19 | 0.39 | +3.7 / −64.5 |
| TARGETED (primary) | 1 | 0 / 0 | 26 / 29 | 1.00 | 0 / 0 |
| STRICT (nothing broke) | 9 | 2 / 6 | 24 / 23 | 0.26 | +1.5 / −62.5 |
| reference model must not fall | 10 | 2 / 7 | 24 / 22 | 0.15 | +0.8 / −60.4 |
| consensus must not fall | 6 | 3 / 2 | 23 / 27 | 0.66 | +2.1 / 0.0 |
| **CONSENSUS-ONLY** | 26 | **18 / 8** | 8 / 21 | **< 0.01** | +8.8 / −2.1 |
| CONSENSUS + passing does not fall | 11 | 6 / 5 | 20 / 24 | 0.74 | +4.6 / 0.0 |
| REF-ONLY | 22 | 9 / 13 | 17 / 16 | 0.58 | +11.2 / −71.5 |

**Held-out model arm:** 93 commits in 9 jobs.

| rule | accepted | accepted: better / worse | rejected: better / worse | Fisher p | accepted gains / losses |
|---|---|---|---|---|---|
| current latch | 25 | 10 / 13 | 9 / 38 | 0.05 | +45.0 / −168.5 |
| TARGETED (primary) | 2 | 0 / 0 | 19 / 51 | 1.00 | 0 / 0 |
| STRICT | 18 | 8 / 8 | 11 / 43 | 0.03 | +24.2 / −140.0 |
| reference model must not fall | 15 | 5 / 8 | 14 / 43 | 0.32 | +14.2 / −140.4 |
| consensus must not fall | 11 | 5 / 4 | 14 / 47 | 0.05 | +28.8 / −1.3 |
| **CONSENSUS-ONLY** | 20 | **10 / 10** | 9 / 41 | **0.02** | +30.0 / −1.4 |
| CONSENSUS + passing does not fall | 12 | 9 / 3 | 10 / 48 | < 0.01 | +30.0 / −1.3 |
| REF-ONLY | 43 | 13 / 30 | 6 / 21 | 0.58 | +17.3 / −217.7 |

**Correlation of each golden-free signal with golden's net cells** (Spearman):

| signal | checks arm | model arm (held out) |
|---|---|---|
| change in passing requirements (the current latch) | −0.14 | +0.32 |
| testpoints changed outside the failing requirements' (negated) | −0.01 | +0.56 |
| **change in agreement with the fresh samples** | **+0.57** | **+0.67** |
| change in agreement with the reference model | −0.12 | −0.13 |

## What holds

- **The held-out hypothesis holds.**
  - The change in agreement correlates with golden on the held-out arm (+0.67).
  - CONSENSUS-ONLY separates its accepts from its rejects there: 50% of accepted commits are net
    better, against 18% of rejected ones (p = 0.02; own stimulus p = 0.01).
- **Consensus is the only signal that works on both arms.**
  - The passing count is uninformative on the checks arm and weakly informative on the model
    arm.
  - The reference model is uninformative on both. It shares the checks' reading of the spec
    (`CHECKS-VS-ABLATION-ROBUST.md`).
  - The "outside the failing testpoints" signal flips between arms.
- **Its main effect is on losses.**
  - Under CONSENSUS-ONLY, the losses accepted fall from −64.5 to −2.1 points on the checks arm,
    and from −168.5 to −1.4 on the model arm.
  - It keeps more gain on the checks arm (+8.8 against +3.7) and less on the model arm (+30.0
    against +45.0).
  - sb luna14's configuration line drops the design's agreement with the samples from 99% to 38%,
    so CONSENSUS-ONLY rejects it.
- **The rule implemented is CONSENSUS-ONLY.** The hybrid (agreement rises and passing does not
  fall) does best on the held-out arm. But it fails on the checks arm, where adding the checks
  condition removes the signal, so it is not adopted.

## What does not

- **Commit by commit, not session by session.** Under a different latch the editor would have
  built on a different accepted design after its first changed decision. Whether the rule improves
  the finals needs live runs.
- **Consensus cannot fix what every sample gets wrong.** byte_ctrl's command codes are the
  example. A correct fix of a shared misreading would lower agreement and be rejected.
- **The sample is still small and clustered.** 166 commits in all, mostly from bit_ctrl and
  byte_ctrl, three peers per job, and commits within a session are correlated. The checks-arm
  p-value is not a test: the rule was chosen on those commits. The held-out p-values are, for the
  one rule and one secondary named in advance.
- **Peers cost generations.** Three extra samples per job at about 12k output tokens each, small
  against a repair session's 14k–760k (`CHECKS-VS-ABLATION-ROBUST.md`).
- **Session-start tracking matched the next round's history in 17 of 19 session ends** on the
  model arm, so two sessions' failing lists, used only by TARGETED, are approximate.

## The fix

`eda_agent/consensus_gate.py` and `RTLEditor(latch_rule="consensus", latch_gate=...)`; in the e7
runner, `--latch consensus --peer A.sv --peer B.sv --peer C.sv`.
- The checks still say what is failing.
- A commit is kept only if the design's agreement with the independent samples rises.
- The peers are simulated, never shown to the editor.
- The editor is told the agreement before and after, and which outputs moved away from the
  peers.
- `--full-view` separately gives the editor the whole design and lets it edit anywhere.
- Both default off.
- **Gate check:** on sb luna12's start, the gate reproduces this test's agreement exactly
  (0.860426).

## Live iteration, small runs only

Run at small scale to find errors, not to measure the effect. Four sessions were stopped about an
hour into a full arm, followed by four smoke runs of 3 trials and 1 round, all with checks
feedback, the consensus latch and `--full-view`. The analysis tool is
`e7_behaviour/smoke_report.py`.

| run | what happened | golden's view of the final |
|---|---|---|
| 4 stopped full-arm sessions (bit_ctrl luna12, byte_ctrl luna12–14) | 13 commits judged by the gate, no errors; 1 latched, 12 refused. 3 refused batches changed no output at all. | not scored (stopped) |
| smoke 1: sb luna12 | latched a **+0.08-point** rise, which golden scores as a pure regression (1,565 cells broken) | 56.1% → 54.5% of edges |
| smoke 2: dc_fsm luna13 | one commit, +0.17 points, latched | 90.3% → 90.5% edges, 79.0% → 82.8% testpoints (61 cells fixed, 6 broken) |
| smoke 2: sb luna12 | the +0.08 rise refused by the new margin, then **shipped anyway** (bug below) | 54.5% |
| smoke 3: sb luna12 | all 3 commits refused (one would have taken agreement from 86.0% to 50.6%) | unchanged, 56.1% |
| smoke 4: byte_ctrl luna12 | 1 commit (passing 52 → 56, agreement 63.73% → 63.65%), refused | unchanged, 42.7% |

**Defects found and fixed:**
1. **A rise below 0.1 points latched** (smoke 1). Gains that small were a coin flip in the audited
   commits on both arms, so `ConsensusGate.MIN_GAIN` = 0.001. This is tuned, not tested.
2. **A refused design was shipped** (smoke 2). The best-design tracker ranked on raw agreement,
   ignoring the margin, so `restore_best` returned the design the latch had just refused.
   `note_best` now applies the margin. Confirmed in smoke 3.
3. **Batches that change no output spent trials** (the stopped sessions). The refusal now says so.
4. **A batch behaving exactly like one already refused was resubmitted** (smoke 3). The gate
   fingerprints behaviour, and the refusal names the earlier trial. This is not yet exercised live.

**Not a defect, but the main inefficiency:**
- **Steering and latch disagree.** The editor is steered by the checks and judged by agreement,
  so most check-raising commits are refused: 12 of 13 in the stopped sessions.
- **Telling the editor where its design disagrees with the peers would close that gap.** But it
  would turn the peers into feedback, which risks importing their shared errors. That is a
  design decision, not a fix.
- **Short smoke runs end on the turn budget.** The editor loop allows as many agent turns as it
  has trials, so a 3-trial byte_ctrl session made one commit.

All smoke runs cost about 10–106k output tokens each.
