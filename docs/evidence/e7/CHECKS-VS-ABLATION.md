# Repair against the checks vs generating again

The question here is not checks-only vs model feedback. It is whether repairing a design
against the shipped checks beats simply generating another one.

**The ablation** is every generation-only design of the same corpus, in the same environment:
- **sb, dc_fsm, bit_ctrl:** the three samples of `ABLATION.md` plus the original job's round-0
  design, which is also the checks arm's start. That is 4 per job and 7 jobs.
- **byte_ctrl:** the real-child generation that the checks arm started from, plus three more
  real-child samples (`<run>/editor-abl-child-gen{1,2,3}`). `ABLATION.md`'s byte_ctrl samples
  had a stand-in child and are not comparable.

**The treatment** is the checks-only final (`CHECKS-FEEDBACK.md`). Scoring uses the behaviour
harness and ChipVerilog; golden is used for scoring only. Figures come from
`e7_behaviour/checks_vs_ablation.py`, which writes `CHECKS-VS-ABLATION.json`.

## Seven like-for-like jobs (sb, dc_fsm, bit_ctrl)

| job | edges equal to golden: ablation min–max (mean) | checks final | shipped checks: ablation min–max | checks final | ChipVerilog passes: ablation / checks |
|---|---|---|---|---|---|
| bit_ctrl luna12 | 17.0–18.8 (17.9) | 18.5 | 72.8–77.7 | **84.5** | 0/4 / no |
| dc_fsm luna12 | 89.5–97.1 (94.5) | 92.6 | 81.2–87.5 | 83.8 | 0/4 / no |
| dc_fsm luna13 | 89.6–95.7 (92.8) | 90.6 | 79.8–100.0 | **100.0** | 0/4 / no |
| dc_fsm luna14 | 95.5–95.9 (95.7) | 95.9 | 82.3–89.9 | **93.7** | 0/4 / no |
| sb luna12 | 44.6–56.4 (50.4) | 53.9 | 88.2–92.6 | **94.1** | 0/4 / no |
| sb luna13 | 100.0–100.0 (100.0) | 100.0 | 42.4–42.4 | 42.4 | 4/4 / yes (unchanged start) |
| sb luna14 | 97.6–100.0 (99.4) | **40.5** | 40.9–42.4 | **98.5** | 3/4 / no |

**Repair buys check score, not behaviour.**
- **Check score:** in 6 of 7 jobs the checks final passes more shipped checks than every
  ablation sample; in the seventh it is second.
- **Golden agreement:** it beats the ablation mean on edges equal to golden in 3 jobs, by
  0.2–3.5 points, and loses in 3, by 1.9, 2.2 and 58.9 points. sb luna13 ties: the arm returned
  its start unchanged.
- **Formal verdicts:** 1 of 7 checks finals passes ChipVerilog, against 7 of 28 ablation samples.
  The one pass is the start the arm did not change.

**Selection without golden.** This is the practical alternative to repair: generate several
designs and keep one.

| mean edges equal to golden, 7 jobs | all 7 | without sb luna14 |
|---|---|---|
| repair against the checks | 70.3% | 75.3% |
| keep the ablation sample that passes most shipped checks | 76.6% | 72.7% |
| keep a random ablation sample | **78.7%** | **75.2%** |
| keep the best ablation sample by golden (oracle, not available) | 80.6% | 77.3% |

- **Repair is a random fresh generation with a heavy tail.** Without sb luna14 the two are equal.
  With it, repair is 8 points worse, because it can destroy a design that was already right. On
  sb luna14 the configuration-macro move took 100% to 40.5%.
- **Choosing by the checks is worse than choosing at random** when that tail is excluded. On
  dc_fsm luna12 and sb luna12 the sample with the most passing checks is the worst one by golden.
  `BEHAVIOUR.md` found the same: the check score is anti-correlated with behaviour in 4 of 5
  modules.
- **Spread is unchanged.** Across runs, the SD of edges equal to golden for one design per corpus
  is 25.5 points for the checks finals and 20.6–26.1 for the ablation indices (sb). For dc_fsm it
  is 2.2 against 0.7–3.0.
- **Context:** on the same 7 jobs, the original model-feedback finals average 68.7%. Both kinds
  of repair land about 8–10 points below a random generation. The losses fall on different jobs:
  the original repair broke sb luna13, and the checks arm broke sb luna14.

## byte_ctrl (real-child environment)

The ablation is the arm's real-child start plus three more real-child samples per run. Each of
the 9 new samples instantiates the child.

| job | edges equal to golden: ablation min–max (mean) | checks final | its start | shipped checks: ablation min–max | checks final | ChipVerilog passes: ablation / checks |
|---|---|---|---|---|---|---|
| byte_ctrl luna12 | 18.7–42.7 (33.2) | **43.8** | 42.7 | 53.4–64.8 | 63.6 | 0/4 / no |
| byte_ctrl luna13 | 12.6–34.4 (24.5) | 31.0 | 34.4 | 22.7–51.5 | **77.3** | 0/4 / no |
| byte_ctrl luna14 | 16.7–20.2 (18.5) | 16.1 | 16.7 | 63.3–73.5 | **81.6** | 0/4 / no |

**This is the one module where repair beats a random fresh sample, and the lead comes from the
start.**
- **Against the ablation mean:** +10.6 on luna12 and +6.5 on luna13, −2.4 on luna14.
- **Against its own start:** +1.1, −3.4 and −0.6. On luna12 and luna13 the start the arm was
  given was the best of the four samples. Repair kept roughly what the start had and added little
  or nothing.
- **Check score:** above every sample on luna13 and luna14, second on luna12.
- **With the header's command codes applied to every design** (`CHECKS-VS-ABLATION-ROBUST.md`),
  the repair's loss to its start grows to 2.4 points on luna12 and 15.2 on luna13. luna14's start
  also drops its command every cycle, so codes alone leave it at 19.8% and the final at 18.8%.
  The edits that looked neutral while the codes were wrong cost real behaviour once they are
  right.
- **Spread** is unchanged. Across runs, the SD of edges equal to golden is 11.3 points for the
  checks finals and 5.0–12.1 for the ablation indices.

## All ten jobs

| mean edges equal to golden | 10 jobs | without sb luna14 |
|---|---|---|
| repair against the checks | 58.3% | 60.3% |
| *the start that repair was given* | *65.0%* | *61.1%* |
| keep the sample that passes most shipped checks | 61.4% | 57.1% |
| keep a random sample | 62.7% | 58.6% |
| keep the sample that agrees most with the other samples (golden-free) | **65.2%** | **61.4%** |
| keep the best sample by golden (oracle, not available) | 66.1% | 62.4% |

- **On average, repair does not beat the start it was given:** −6.7 points, or −0.8 without sb
  luna14. Its largest gain over a start in any job is 1.1 points.
- **Where it beats a random sample, the start was lucky:** in byte_ctrl luna12 and luna13, and in
  the 9 jobs without sb luna14.
- **Choosing by the checks scores below choosing at random,** worse in 7 jobs and better in 2
  (p = 0.18).
- **Choosing by consensus scores highest,** better in 6 jobs and worse in 3 (p = 0.51).
- **Neither difference is established** at 10 jobs. The grading is in
  `CHECKS-VS-ABLATION-ROBUST.md`.

Consensus selection is examined in `CHECKS-VS-ABLATION-ROBUST.md`, with the other metrics and
assumptions.

## What it means

On these modules, repairing against the checks does not improve on generating again.
- **Its expected behaviour is its start's.** Where it looks better than a fresh sample, the start
  was better than one.
- **It carries a tail risk the ablation does not have:** breaking a design that was already
  correct. This happened on 1 of the 2 sb jobs whose ablation was all golden-equivalent.
- **On byte_ctrl the same holds,** and it gets worse for repair once the command codes are
  right.

The same checks are no better as a selector than as an objective. Until the checks stop sharing
the generator's misreadings (`QUALITATIVE.md`), the check score is not evidence of behaviour, for
repair or for choosing among samples. Agreement between independent samples is.

`REPAIR-ANATOMY.md` shows why, output by output. The fixes are real but touch rare events. Edits
made for one check break outputs no check watches, and 82% of edit calls never reach the design.

`CHECKS-VS-ABLATION-ROBUST.md` tests this verdict against every other metric the harness records,
a random stimulus, paired and pooled baselines, outliers, significance, cost and the byte_ctrl
codes. "No better" survives all of them; "worse" rests on one job.
