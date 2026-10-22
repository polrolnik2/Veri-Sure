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

*Pending:* the three real-child ablation samples per run are being generated. Against the one
real-child generation available so far (the arm's start):
- **edges equal to golden:** the checks final is higher on luna12 (43.8 vs 42.7) and lower on
  luna13 (31.0 vs 34.4) and luna14 (16.1 vs 16.7);
- **shipped checks:** higher on all three.

## What it means

On these modules, repairing against the checks does not improve on generating again. Its
expected behaviour equals a fresh sample's. It carries a tail risk the ablation does not have:
breaking a design that was already correct, which happened on 1 of the 2 sb jobs whose ablation
was all golden-equivalent.

The same checks are no better as a selector than as an objective. Until the checks stop sharing
the generator's misreadings (`QUALITATIVE.md`), the check score is not evidence of behaviour, for
repair or for choosing among samples.
