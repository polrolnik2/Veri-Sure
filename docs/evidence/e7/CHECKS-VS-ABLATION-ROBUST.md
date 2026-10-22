# Does the verdict survive other metrics and assumptions?

`CHECKS-VS-ABLATION.md` concluded that repairing a design against the shipped checks does no
better than generating another one. Each assumption behind that verdict is varied here, one at a
time, over all 10 jobs:
- sb, dc_fsm and bit_ctrl: 7 jobs;
- byte_ctrl with the real child: 3 jobs.

Each job compares the checks-only final with 4 fresh generation-only designs, one of which is the
final's own start. Figures come from `e7_behaviour/checks_vs_ablation_robust.py`, which writes
`CHECKS-VS-ABLATION-ROBUST.json`. Two new scorers feed it:
- `e7_behaviour/random_stim.py` (`RANDOM-STIM.json`): a stimulus the pipeline did not write;
- `e7_behaviour/byte_ctrl_codes_pool.py` (`BYTE-CTRL-CODES-POOL.json`): byte_ctrl with the
  header's command codes.

## The short answer

**"No better" survives every alternative tried. "Worse" does not.**
- **No golden-graded measure favours repair.** There are 15: open loop, closed loop, random
  stimulus, exact, order-only, per port and formal. Repair's mean is below a fresh sample's on
  every one. The median job difference is within ±0.4 points, and repair beats 38–55% of single
  fresh samples. No exact rank test separates it from one more fresh sample (p ≥ 0.27).
- **The mean loss rests on one job.** On edges equal to golden it is −4.4 points, with a 95% CI of
  [−17.5, +3.7]. Leaving one job out moves it anywhere from −6.1 to +1.7; sb luna14 carries it.
- **The data rule out a large gain, not a small one.** A benefit of a few points, or none, is
  consistent with them.
- **Repair wins only on what it optimises:** +13.9 points of shipped checks, in 9 of 9 jobs that
  moved (p < 0.01).

**Two assumptions change part of the picture.**
1. **The selector.** Keeping the sample that agrees most with the other samples (consensus,
   golden-free) beats a random sample by 2.5 points and comes within 0.9 of the oracle.
   - It improves as more samples are drawn.
   - Selecting by shipped checks or by the reference model gets worse as more samples are drawn.
   - So `CHECKS-VS-ABLATION.md`'s "choosing is no better than random" is a property of those two
     selectors, not of choosing.
2. **byte_ctrl's command codes.** As generated, byte_ctrl is the one module where repair beats the
   ablation mean (on luna12 and luna13), but there its starts were already the best samples. With
   the header's codes in every design, repair falls behind its own start on all three runs, by 2.4,
   15.2 and 1.0 points of edges.

**Two more points:**
- **A golden-free guard makes repair harmless, not useful.** "Keep the start if the final agrees
  less with the fresh samples" removes sb luna14's loss. The guarded repair then equals its starts
  (64.9% vs 65.0%).
- **Repair is expensive.** The checks arm's editor used 1–54× the output tokens of one generation
  (median 15×) and up to 7.4M uncached input tokens. A generation uses 6–11k uncached input and
  12–14k output tokens.

## The assumptions, one by one

| assumption in `CHECKS-VS-ABLATION.md` | alternative | edges equal to golden, repair − alternative baseline | verdict |
|---|---|---|---|
| edges equal to golden | 14 other golden-graded measures (section 1) | means −2.0 to −7.7; medians −0.4 to +0.2 | same |
| the pipeline's stimulus, all corpora | the run's own corpus only | −4.1 | same |
| | closed loop: stimulus reacts to the design | order-only −6.4; per port −4.3 | same |
| | random input sequences the pipeline did not write | −2.0 (median −0.3) | same |
| baseline: mean of the 4 fresh samples | the final's own start (paired) | −6.7; 4 better / 5 worse | same |
| | the 3 fresh samples other than the start | −3.6 | same |
| aggregate: mean over jobs | each module weighted equally | −3.6 | same |
| | median job | +0.1 | same |
| | share of single samples beaten | 0.51 | same |
| no outlier | leave one job out | −6.1 to +1.7 | "worse" does not survive |
| differences are real | exact rank test; bootstrap | p = 0.95; CI [−17.5, +3.7] | "worse" does not survive |
| select by shipped checks | by reference model; by consensus | consensus beats random by 2.5 | **changes** |
| repair is always accepted | consensus guard | guarded repair = its starts | harmless, not useful |
| one repair vs one sample | equal cost | 1–54× a generation's output tokens | favours sampling |
| byte_ctrl codes as generated | header codes in every design | vs own start −2.4 / −15.2 / −1.0 (as generated +1.1 / −3.4 / −0.6) | worse for repair |

## 1. Every metric

Checks final minus the fresh-sample mean, in points, over the 10 jobs. `wins` is the share of
single fresh samples it beats, ties counting half. The rank test asks whether its position among
its job's 5 designs is uniform, which it would be if repair were one more fresh sample.

| metric | vs fresh samples: mean [95% CI] | median | jobs better / worse | leave one out | vs own start | wins | rank p |
|---|---|---|---|---|---|---|---|
| edges equal to golden | −4.4 [−17.5, +3.7] | +0.1 | 5 / 4 | −6.1 to +1.7 | −6.7 | 0.51 | 0.95 |
| edges equal, own corpus stimulus only | −4.1 [−17.5, +3.9] | +0.2 | 6 / 3 | −5.5 to +2.2 | −6.9 | 0.50 | 1.00 |
| output-port traces equal | −3.7 [−12.7, +1.7] | −0.2 | 4 / 5 | −4.9 to +0.4 | −5.5 | 0.40 | 0.38 |
| whole testpoints equal | −5.4 [−18.3, +2.6] | +0.1 | 5 / 4 | −6.8 to +0.6 | −6.8 | 0.45 | 0.68 |
| order-only testpoints, open loop | −5.5 [−18.8, +2.7] | +0.1 | 5 / 4 | −6.9 to +0.7 | −6.6 | 0.50 | 1.00 |
| per-port order only, open loop | −3.1 [−11.2, +1.8] | −0.2 | 4 / 5 | −4.1 to +0.6 | −4.5 | 0.38 | 0.27 |
| whole testpoints equal, closed loop | −5.6 [−18.5, +2.4] | +0.1 | 5 / 4 | −7.0 to +0.3 | −7.0 | 0.45 | 0.68 |
| order-only testpoints, closed loop | −6.4 [−19.7, +2.1] | +0.1 | 5 / 4 | −7.9 to −0.3 | −7.6 | 0.42 | 0.52 |
| per-port order only, closed loop | −4.3 [−11.9, +0.2] | −0.4 | 3 / 6 | −5.0 to −0.6 | −4.8 | 0.40 | 0.38 |
| equal to golden on every stimulus (0/1) | −7.5 [−22.5, 0.0] | 0.0 | 0 / 1 | −8.3 to 0.0 | −10.0 | 0.46 | 0.40 |
| equal to golden up to latency, closed loop (0/1) | −7.5 [−22.5, 0.0] | 0.0 | 0 / 1 | −8.3 to 0.0 | −10.0 | 0.46 | 0.40 |
| ChipVerilog pass (0/1) | −7.5 [−22.5, 0.0] | 0.0 | 0 / 1 | −8.3 to 0.0 | −10.0 | 0.46 | 0.40 |
| edges equal, random stimulus | −2.0 [−11.9, +4.9] | −0.3 | 4 / 5 | −3.4 to +2.4 | −4.3 | 0.55 | 0.69 |
| port traces equal, random stimulus | −7.7 [−23.5, +4.3] | 0.0 | 3 / 6 | −10.9 to −0.9 | −9.4 | 0.49 | 0.95 |
| whole testpoints equal, random stimulus | −6.5 [−21.0, +2.5] | 0.0 | 2 / 4 | −8.4 to +0.2 | −9.0 | 0.45 | 0.60 |
| *golden-free:* shipped checks passed | **+13.9 [+5.1, +25.8]** | +8.3 | 9 / 0 | +9.2 to +15.5 | +13.2 | 0.89 | <0.01 |
| *golden-free:* edges equal to the reference model | +0.3 [−2.7, +3.9] | 0.0 | 4 / 5 | −1.2 to +1.1 | +1.1 | 0.40 | 0.38 |
| *golden-free:* edges equal to the fresh samples | −3.8 [−18.0, +6.0] | 0.0 | 5 / 4 | −6.3 to +2.6 | −8.0 | 0.40 | 0.38 |

- **Not one golden-graded measure is above zero on average.** Each has a median within half a
  point of zero.
- **The paired comparison is no kinder.** Against its own start, repair is 4–10 points worse on
  average.
- **Without sb luna14 the paired change on edges is −0.8 points.** Repair barely moves a design;
  when it moves one far, it is the wrong way.
- **The shipped-check score is the only measure whose interval excludes zero.**
- **The reference model does not register repair either:** +0.3. In the checks arm the model is
  not feedback; it is the run's own golden-free estimate of behaviour.

**The random stimulus** (`random_stim.py`) shares nothing with the pipeline but the values each
input takes and how often it changes.
- **What it is:** each testpoint starts from reset, then each input takes random values from that
  set, held for random spans.
- **It is consistent with the formal verdicts:** every design ChipVerilog proves equivalent
  scores 100% on it.
- **It moves individual jobs, not the verdict.** On dc_fsm luna14 the final and its start score
  97%, against 82–84% for the other three samples. Under the pipeline's stimulus all five sat
  within 0.4 points.
- **It is weak on bit_ctrl,** where golden's outputs change on only 2.9% of its edges.

## 2. Which design to keep, without golden

Mean over the 10 jobs of the kept design's score (%):

| metric | repair | repair + consensus guard | random sample | most shipped checks | most agreement with the reference model | most agreement with the other samples | oracle |
|---|---|---|---|---|---|---|---|
| edges equal to golden | 58.3 | 64.9 | 62.7 | 61.4 | 60.8 | **65.2** | 66.1 |
| edges equal, own corpus | 58.6 | 65.4 | 62.7 | 61.7 | 60.8 | **65.7** | 66.3 |
| whole testpoints equal | 46.0 | 53.1 | 51.4 | 51.5 | 50.8 | 52.4 | 55.8 |
| order-only testpoints, closed loop | 46.9 | 54.8 | 53.3 | 53.5 | 52.8 | 54.2 | 57.2 |
| per-port order, closed loop | 77.3 | 82.2 | 81.6 | 81.1 | 80.4 | **82.3** | 83.1 |
| ChipVerilog pass | 10.0 | 20.0 | 17.5 | 20.0 | 20.0 | 20.0 | 20.0 |
| edges equal, random stimulus | 56.2 | 60.3 | 58.2 | 56.5 | 56.0 | 59.5 | 61.9 |

**Without sb luna14**, repair's largest loss, the figures for edges equal to golden are:

| repair | guarded repair | its starts | random sample | most shipped checks | reference model | consensus | oracle |
|---|---|---|---|---|---|---|---|
| 60.3 | 61.0 | 61.1 | 58.6 | 57.1 | 56.5 | **61.4** | 62.4 |

Repair now beats a random sample (+1.7) but not its own starts (−0.8). Its apparent lead is the
starts' luck; the same holds for byte_ctrl, below.

**Best of k:** the expected edges equal to golden when k samples are drawn and one is kept.

| selector | k = 1 | k = 2 | k = 3 | k = 4 |
|---|---|---|---|---|
| most shipped checks | 62.7 | 62.6 | 61.9 | 61.4 |
| most agreement with the reference model | 62.7 | 61.8 | 61.0 | 60.8 |
| most agreement with the other samples | 62.7 | 64.6 | 65.1 | 65.2 |
| golden (oracle) | 62.7 | 65.0 | 65.9 | 66.1 |

**The two selectors that encode the run's reading of the spec get worse the more they choose
from.** Those are the shipped checks and the reference model, which is debugged against them.
- They pick the same sample in all 7 non-byte_ctrl jobs.
- On sb luna13 and luna14 the golden-equivalent designs pass 42% of shipped checks and match the
  reference model on 42–44% of edges.

**Consensus encodes no reading, only agreement between independent attempts, and it improves
with k.**
- Its failure mode is a shared misreading. Where all samples are wrong the same way, it cannot
  help: byte_ctrl's codes are the case.

**The guard** keeps the start in 6 of 10 jobs, including sb luna14 (consensus 38% for the final,
99% for the start).
- The guarded repair's 64.9% is its starts' 65.0%. The starts happen to be better than the
  average sample (62.7%), which is why it beats a random one.
- So the guard removes repair's tail but adds nothing to the start.

## 3. byte_ctrl with the command codes fixed

Every real-child byte_ctrl design swaps READ and WRITE relative to `i2c_master_defines.v`.
- The spec gives no values (`CHECKS-FEEDBACK-QUALITATIVE.md`).
- One sample, luna14 acg2, uses a 3-bit encoding instead.
- `byte_ctrl_codes_pool.py` gives every design of the comparison the header's codes and changes
  nothing else.

Edges equal to golden (%), all stimulus:

| run | the start | the three other samples | checks final | final − start, codes fixed (as generated) |
|---|---|---|---|---|
| luna12 | 96.9 | 92.0, 60.6, 24.6 | 94.5 | −2.4 (+1.1) |
| luna13 | 73.6 | 64.7, 32.3, 14.6 | 58.4 | −15.2 (−3.4) |
| luna14 | 19.8 | 84.1, 24.5, 20.3 | 18.8 | −1.0 (−0.6) |

- **Once the codes are right, repair falls behind its start on every run.** On luna13 the same
  edits cost 3.4 points with the wrong codes and 15.2 with the right ones. While the child ran the
  wrong commands, most of what repair changed could not show.
- **Against the fresh-sample mean** it is +26.0 and +12.1 on luna12 and luna13, and −18.4 on
  luna14. This is the same pattern as before: luna12's and luna13's starts were the best of their
  four samples.
- **luna14's start also drops its command every cycle**, so the codes alone do not rescue it
  (`BYTE-CTRL-CODES.json`, "hold"). The best luna14 sample with the header's codes (84.1%) is the
  one with the 3-bit encoding.
- **The codes were hiding most of the difference between samples.** With them fixed, the fresh
  samples range from 15% to 97% of edges. Which sample you start from then matters far more than
  repair.

## 4. Cost

Tokens, uncached input / output, in thousands. A fresh sample is one generation. The editor's
figure counts only its own calls, made on top of the generation it starts from.

| job | one generation | the checks arm's editor | editor ÷ generation (output) |
|---|---|---|---|
| bit_ctrl luna12 | 11 / 14 | 7378 / 759 | 54× |
| byte_ctrl luna12 | 6 / 12 | 7378 / 384 | 33× |
| byte_ctrl luna13 | 6 / 12 | ≥ 2033 / ≥ 302 | ≥ 26× |
| byte_ctrl luna14 | 6 / 12 | 5151 / 425 | 37× |
| dc_fsm luna12 | 11 / 13 | lost | |
| dc_fsm luna13 | 11 / 13 | 195 / 14 | 1× |
| dc_fsm luna14 | 11 / 13 | 470 / 54 | 4× |
| sb luna12 | 8 / 14 | 58 / 15 | 1× |
| sb luna13 | 8 / 14 | 6181 / 205 | 15× |
| sb luna14 | 8 / 14 | 1029 / 65 | 5× |

- **luna13 byte_ctrl** was resumed several times, and its log holds only the last launches. Its
  figure is a lower bound. byte_ctrl's generation figure is the mean of the 9 real-child samples.
- **dc_fsm luna12's** editor directory was lost (`luna12/editor-cf-checks/or1200_dc_fsm/NOTE.md`).
- **The equal-cost comparison is lopsided.** For the price of one repair, the 4-sample best-of-k
  above could be bought several times over on most jobs. Consensus selection's 65.2% is then
  available at a fraction of the cost.

## What was not tested

- **Whether the checks that repair satisfies are right.** This needs a check score restricted to
  checks golden itself passes. That takes each run's probes bound to golden's internals by hand;
  `BOUND-AUDIT.md` did this for one other corpus, not for these runs.
- **Other stopping points.** Only the finals were kept, so stopping repair earlier cannot be
  scored.
- **More runs per job, more modules.** There are 10 jobs, 4 modules and one checks run per job.
  At this spread the 95% CI on the mean is about 20 points wide.
- **The random stimulus has limits:**
  - it drives the open-drain lines open loop;
  - it does not respect protocols, so some of what it compares is behaviour the spec leaves open;
  - it says little about bit_ctrl.

## What it means

The verdict should be stated as **"repair against the checks shows no benefit over a fresh
sample, on any measure of behaviour"**, not as "repair is worse". The difference from "worse"
rests on one job and is inside the noise.

Two findings are new:
1. **Choosing among fresh samples can beat a random one,** but only with a selector that does not
   share the run's reading of the spec. Consensus does. The checks and the reference model do
   not, and choosing harder with them makes things worse.
2. **Fixing the generator's blind spot does not rescue repair; it exposes it.** On byte_ctrl,
   once the command codes are right, the repaired designs fall further behind their starts.
