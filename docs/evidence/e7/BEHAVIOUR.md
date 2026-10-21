# Measuring behaviour when there is no golden in the loop

> **Corrected 2026-10-21.** The first version of this document came from
> harnesses that ran a corpus's testpoints back to back WITHOUT the shipped
> testbench's per-testpoint reset (`Env.reset`: idle inputs, resets asserted for
> 2 edges, released). Only 18–66% of testpoints start with a reset step, so the
> rest inherited the previous testpoint's state. Both harnesses now run that
> reset before every testpoint, and every figure below is from the corrected
> rerun (f92711c).
>
> The behaviour-class counts and the validation against the formal verdict did
> not change. Per-testpoint shares and agreement with the reference model did,
> by a few points. No conclusion changed.

## The constraint, and the two kinds of metric it forces

In a run there is no golden design. Anything that chooses -- a sample, a repair,
a check -- must use golden-free information. Golden can only referee afterwards.
So the metrics come in two kinds, and they must not be mixed:

| kind | available in a run? | used for | here |
|---|---|---|---|
| **in-run** (golden-free) | yes | choosing | shipped-check score; agreement with the run's own reference model; agreement with the other generated designs of the same corpus ("peers") |
| **grading** (golden) | no | scoring the arms | formal equivalence (binary); **partial equivalence on stimulus** (graded, below); behaviour classes |

`ABLATION.md`'s "best of three" picked by the shipped checks is golden-free, so
it is a legitimate selector. But the shipped-check score is not behaviour, and
"best" by behaviour needs golden. The honest framing is:
- the baseline without a selector is a **random pick** (the pool mean);
- the **golden-chosen best** is a ceiling no run can reach;
- an in-run metric is worth selecting by only if it **tracks the grading
  metrics**. That is tested in section 4.

## Method

- **Stimulus.** Each corpus's own stimulus (227–866 testpoints) is realized into
  fixed per-edge input sequences by **the run's own reference model**
  (`realize.py`; golden-free, with `until` waits resolved against that model).
  That gives 5.6k–223k edges per corpus.
- **Designs (83).** For each corpus:
  - the 3 generation-only samples;
  - the editor job's generated design ("round 0", before repair);
  - the editor's final ("repaired").

  Two round-0 designs (luna13 byte_ctrl, luna14 fpu) were lost with their
  crashed attempts' directories, so there are 15 before/after pairs.
  Golden is the ChipVerilog reference with its child modules.
- **Open loop** (`sim.py`). Every design, golden included, is driven through the
  same input sequences of every corpus of its module (iverilog). Outputs are
  sampled before each rising edge, as the checks sample. Each testpoint is
  preceded by the testbench's reset. A golden X counts as don't-care.
- **Closed loop** (`closed_loop.py`, for latency). Each design runs the stimulus
  the way the shipped testbench does: the same per-testpoint reset, `until`
  waits resolved on **its own** outputs, the same budget and settle edges, and
  open-drain lines wired (`line = stimulus AND *_oen`).
- **Validation.** Both harnesses agree with the formal verdict on all 83
  designs. The 8 formally equivalent designs equal golden on every edge of every
  testpoint; each of the 75 non-equivalent designs differs from golden somewhere.

**Grading metrics, as shares equal to golden:**
- *edges*: edges where every output equals golden's;
- *testpoints*: whole testpoint traces equal to golden's;
- *port traces*: each output port's trace, per testpoint;
- *order-only*: the sequence of distinct output states, durations ignored;
- *per-port order-only*: each port's sequence of distinct values.

**Behaviour class:** a hash of every output at every edge over the whole module
stimulus. Two designs in different classes are provably different, and a class
that isn't golden's provably isn't equivalent to golden. The number of classes
is a lower bound on the number of distinct behaviours.

## 1. Distinct behaviours not equivalent to golden

| module | arm | designs | distinct behaviours | not golden | golden-equivalent designs |
|---|---|---|---|---|---|
| fpu | generated | 15 | 13 | 13 | 0 |
| fpu | repaired | 4 | 4 | 4 | 0 |
| bit_ctrl | generated | 16 | 16 | 16 | 0 |
| bit_ctrl | repaired | 4 | 4 | 4 | 0 |
| byte_ctrl | generated | 11 | 11 | 11 | 0 |
| byte_ctrl | repaired | 3 | 3 | 3 | 0 |
| dc_fsm | generated | 12 | 11 | 11 | 0 |
| dc_fsm | repaired | 3 | 3 | 3 | 0 |
| sb | generated | 12 | 6 | 5 | 7 |
| sb | repaired | 3 | 3 | 2 | 1 |

Per corpus, the 3–4 generated designs show 2–4 distinct behaviours, none of
them golden's, on every corpus except two sb ones:
- luna13 sb: all four designs are golden.
- luna14 sb: three of four are golden.

**In 16 of 17 corpora the repaired design is a behaviour no generated design
has.** The exception is luna14 sb, where it is golden's. The full per-corpus
table is printed by `report.py`.

**Generation produces a different wrong behaviour almost every time** (56
distinct non-golden behaviours among 66 generated designs). **Repair does not
converge** on any of them, or on golden: it produces one more.

## 2. Partial equivalence to golden, open loop

| module | arm | n | edges | testpoints | port traces | order-only |
|---|---|---|---|---|---|---|
| fpu | generated | 15 | 69.7% | 10.7% | 52.8% | 26.5% |
| fpu | repaired | 4 | 68.3% | 4.8% | 49.9% | 26.1% |
| bit_ctrl | generated | 16 | 17.5% | 2.5% | 63.5% | 4.9% |
| bit_ctrl | repaired | 4 | 17.4% | 2.3% | 64.0% | 4.2% |
| byte_ctrl | generated | 11 | 5.1% | 8.2% | 43.0% | 8.2% |
| byte_ctrl | repaired | 3 | 4.2% | 7.6% | 43.3% | 7.6% |
| dc_fsm | generated | 12 | 94.3% | 75.8% | 95.5% | 75.8% |
| dc_fsm | repaired | 3 | 92.1% | 77.8% | 94.2% | 77.8% |
| sb | generated | 12 | 83.3% | 76.2% | 87.3% | 77.0% |
| sb | repaired | 3 | 63.0% | 56.1% | 74.3% | 56.1% |
| **all** | generated | 66 | 53.2% | 32.0% | 67.8% | 36.4% |
| **all** | repaired | 17 | 48.3% | 26.6% | 64.2% | 32.1% |

## 3. Before and after repair, same job

15 jobs, from the editor's round 0 to its final, open loop:

| metric | before -> after (mean) | without luna13 sb | up / down / same |
|---|---|---|---|
| edges equal to golden | 54.8% -> 49.7% | 51.5% -> 50.1% | 5 / 9 / 1 |
| testpoints equal | 33.3% -> 29.1% | 28.5% -> 28.7% | 2 / 8 / 5 |
| port traces equal | 69.9% -> 66.3% | 67.7% -> 66.7% | 3 / 9 / 3 |
| order-only equal | 38.2% -> 33.8% | 33.8% -> 33.8% | 2 / 7 / 6 |
| **shipped checks passed** (in-run) | **75.5% -> 83.9%** | **77.8% -> 82.9%** | **11 / 2 / 2** |

**Repair raises the in-run score and does not move behaviour toward golden.**
Without the one outlier, behaviour is flat on every measure. The outlier,
luna13 sb, goes from equivalent (100%) to 45% of edges, because it was repaired
toward checks built on a buffering reference model.

## 4. Do the in-run metrics track behaviour?

Spearman rank correlation with edges equal to golden, within each module:

| module | n | shipped checks | agreement with the run's reference model | agreement with peers |
|---|---|---|---|---|
| fpu | 19 | -0.33 | +0.02 | -0.54 |
| bit_ctrl | 20 | +0.37 | +0.48 | +0.55 |
| byte_ctrl | 14 | -0.21 | +0.33 | +0.60 |
| dc_fsm | 15 | -0.53 | -0.28 | +0.44 |
| sb | 15 | -0.81 | -0.77 | +0.88 |

- **The pipeline's own score, the shipped-check pass rate, is negatively
  correlated with behaviour in 4 of 5 modules.**
- Agreement with the reference model is mixed.
- Agreement with peers is positive in 4 of 5 modules. It is the best in-run
  signal here, but it reverses on fpu.

**Selection.** The pool is a corpus's generated designs. Each pick is scored by
edges equal to golden:

| selection | mean edges equal to golden | picks the golden-best (of 17) |
|---|---|---|
| random (mean of pool) | 52.8% | -- |
| by shipped checks | 51.4% | 2 |
| by agreement with the run's reference model | 52.8% | 8 |
| by agreement with peers | 52.8% | 5 |
| golden-chosen best (**not available in a run**) | 55.3% | -- |
| repaired (editor final) | 48.3% | -- |

- **Picking by the shipped checks is worse than picking at random.** The repair
  loop optimizes that same score and ends lower still.
- No golden-free selector beats random on this score.
- Even the unattainable golden-chosen best is only 2.5 points above random. The
  generated designs are all about equally far from golden, so selection has
  little to work with. The deficit is in generation.

## 5. How much of the disagreement is latency?

A pure latency difference is unfair to judge open loop: a design that answers a
cycle late still gets the next command on the reference model's schedule.
Closed loop, each design drives its own handshakes. *Order-only* then ignores
latency and duration and keeps what the design does and in what order;
*per-port order-only* also ignores timing between ports.

Shares of testpoints equal to golden:

| module | arm | n | open loop, cycle-exact | closed loop, cycle-exact | closed loop, order-only | **latency only** | per-port order-only |
|---|---|---|---|---|---|---|---|
| fpu | generated | 15 | 10.7% | 10.6% | 26.6% | **16.0%** | 90.5% |
| fpu | repaired | 4 | 4.8% | 4.8% | 26.3% | **21.5%** | 90.8% |
| bit_ctrl | generated | 16 | 2.5% | 3.4% | 9.2% | **5.8%** | 78.9% |
| bit_ctrl | repaired | 4 | 2.3% | 3.3% | 6.9% | **3.6%** | 76.6% |
| byte_ctrl | generated | 11 | 8.2% | 8.2% | 8.2% | **0.0%** | 47.5% |
| byte_ctrl | repaired | 3 | 7.6% | 7.6% | 7.6% | **0.0%** | 46.5% |
| dc_fsm | generated | 12 | 75.8% | 75.8% | 75.8% | **0.0%** | 95.6% |
| dc_fsm | repaired | 3 | 77.8% | 77.8% | 77.8% | **0.0%** | 94.5% |
| sb | generated | 12 | 76.2% | 76.2% | 76.9% | **0.7%** | 89.5% |
| sb | repaired | 3 | 56.1% | 56.1% | 56.1% | **0.0%** | 77.8% |
| **all** | generated | 66 | 32.0% | 32.2% | 37.4% | **5.2%** | 81.3% |
| **all** | repaired | 17 | 26.6% | 26.9% | 32.8% | **5.9%** | 78.0% |

- **Latency explains under a tenth of the disagreement.** Of the testpoints
  where a design differs from golden cycle-exactly, 8% in each arm differ only
  in timing.
- That share is concentrated in fpu (16–22 points) and bit_ctrl (4–6 points).
  It is zero for byte_ctrl and dc_fsm.
- **No design is golden-equivalent up to latency** apart from the 8 that are
  equivalent outright.
- The best latency-independent shares per module are: fpu 27.4%, bit_ctrl
  14.5%, byte_ctrl 11.5%, dc_fsm 90.9% of testpoints.
- **Factoring out latency merges no behaviours.** Distinct behaviours modulo
  latency equal the cycle-exact counts in every module and arm.
- Closing the loop changes almost nothing (32.0% -> 32.2%).
- Even the weakest comparison leaves a lot unmatched. Each output port's
  sequence of values, ignoring all timing, matches golden on 81% (generated)
  and 78% (repaired) of port traces. On byte_ctrl it is 47%.

**Repair, latency-independent.** Closed-loop order-only goes 39.1% -> 34.6%
(34.8% -> 34.7% without luna13 sb); per-port order-only goes 82.4% -> 79.1%
(81.1% -> 79.9%). Up 3, down 7 and same 5 of 15 jobs on order-only. The repair
loop optimizes order-only checks, and it still does not improve order-only
behaviour.

**The in-run metrics against the latency-independent score:** shipped checks
-0.71, +0.14, -0.45, -0.14, -0.81 (fpu, bit_ctrl, byte_ctrl, dc_fsm, sb).
Making the grade order-only, like the checks, does not make the checks track it.
Peers come out +0.66, +0.52 and +0.89 on bit_ctrl, byte_ctrl and sb, but -0.67
and -0.64 on fpu and dc_fsm. Selection scored order-only gives:
- random 36.9%;
- by shipped checks 36.2%;
- by reference model 37.5%;
- by peers 37.3%;
- golden-chosen best 39.7%;
- repaired 32.8%.

## 6. Consistency: before against after repair

Computed by `consistency.py` from `BEHAVIOUR.json`, which also prints the full
spread tables.

**Paired change, 15 jobs, round 0 -> final:**

| metric | mean change (pts) | 95% bootstrap CI | median | up / down / same | Wilcoxon p | without luna13 sb: mean, CI, p |
|---|---|---|---|---|---|---|
| edges equal (open loop) | -5.0 | [-13.0, -0.2] | -0.2 | 5 / 9 / 1 | 0.104 | -1.4, [-3.4, +0.1], 0.191 |
| testpoints equal (open loop) | -4.2 | [-13.5, +1.2] | -0.1 | 2 / 8 / 5 | 0.311 | +0.2, [-1.0, +1.7], 0.547 |
| order-only testpoints (closed loop) | -4.5 | [-14.1, +1.3] | +0.0 | 3 / 7 / 5 | 0.557 | -0.1, [-2.2, +1.8], 0.910 |
| per-port order-only (closed loop) | -3.3 | [-8.2, -0.1] | -0.2 | 5 / 8 / 2 | 0.146 | -1.2, [-2.7, +0.3], 0.266 |
| **shipped checks (in-run)** | **+8.5** | **[+1.9, +17.0]** | **+4.5** | **11 / 2 / 2** | **0.017** | **+5.0, [+0.6, +9.6], 0.034** |

**Repair against drawing another design.** For each job, another of the
corpus's generated designs stands in for the repaired one:

| metric | repair: mean change | resample: mean change | repair beats resample | permutation p | without luna13 sb: repair vs resample, p |
|---|---|---|---|---|---|
| edges equal | -5.0 | -0.2 | 42% of 45 | 0.033 | -1.4 vs -0.3, 0.294 |
| testpoints equal | -4.2 | +1.0 | 47% | 0.110 | +0.2 vs +1.1, 0.684 |
| order-only testpoints | -4.5 | +0.2 | 41% | 0.104 | -0.1 vs +0.2, 0.821 |
| per-port order-only | -3.3 | +0.1 | 46% | 0.052 | -1.2 vs +0.1, 0.359 |
| shipped checks | +8.5 | +0.5 | 82% | 0.015 | +5.0 vs +0.5, 0.110 |

What this shows:
- **The shipped-check score moves reliably.** Up in 11 of 15 jobs, significant
  with and without the outlier.
- **Behaviour does not.** No behaviour metric changes significantly (Wilcoxon
  p 0.10–0.56). Medians are about zero, and the negative means are mostly
  luna13 sb.
- **Without luna13 sb, repair's change in behaviour is the size of drawing
  another design** (2.1 vs 2.3 points of edges) and indistinguishable from it
  (p 0.29–0.82).
- **The two scores are unrelated per job.** The four behaviour metrics move the
  same way in 12 of 15 jobs. The size of a job's shipped-check gain does not
  predict its behaviour change (Spearman -0.06 to +0.28).
- **Neither arm is the better one.** The figures are stable to within sampling
  noise on both sides of repair, and the one large change (luna13 sb) is for
  the worse.

**Is the spread of final scores tighter than the ablation's?** The comparison
is like for like: one design per corpus, the editor finals against each
ablation sample index (gen1, gen2, gen3). The table gives SD across reps, in
points; the ratio is repaired SD over mean ablation SD.

| module | shipped checks: repaired / ablation (ratio) | edges equal: repaired / ablation (ratio) | order-only testpoints: repaired / ablation (ratio) |
|---|---|---|---|
| fpu | 3.1 / 13.7 (0.23) | 0.0 / 4.8 (0.01) | 0.1 / 0.5 (0.15) |
| bit_ctrl | 12.9 / 13.0 (0.99) | 1.5 / 1.5 (0.97) | 4.9 / 3.4 (1.45) |
| byte_ctrl | 10.9 / 2.5 (4.30) | 2.4 / 2.7 (0.90) | 6.6 / 4.4 (1.50) |
| dc_fsm | 6.9 / 5.4 (1.28) | 3.4 / 2.7 (1.28) | 4.3 / 4.5 (0.97) |
| sb | 28.6 / 28.0 (1.02) | 32.0 / 29.5 (1.08) | 38.0 / 36.1 (1.05) |

**Pooled Brown-Forsythe test** (deviation from each arm's own median, scaled by
module SD, labels permuted within module):

| metric | repaired vs ablation deviation | p | without sb: deviation, p |
|---|---|---|---|
| shipped checks | 0.71 vs 0.72 | 0.99 | 0.72 vs 0.73, 0.96 |
| edges equal | 0.55 vs 0.70 | 0.53 | 0.51 vs 0.71, 0.44 |
| order-only testpoints | 0.53 vs 0.72 | 0.45 | 0.49 vs 0.71, 0.41 |
| testpoints equal | 0.53 vs 0.67 | 0.59 | 0.49 vs 0.64, 0.59 |

**Pooled, the final scores are no more consistent than the ablation's.**
- **One module is a real exception: fpu.** The four fpu finals land on nearly
  the same score: SD 0.0 points of edges against 4.8 for the samples. That fits
  the qualitative finding that repair moves each fpu design onto its run's
  reference-model reading.
- Elsewhere the ratios are about 1, or go the other way (byte_ctrl's
  shipped-check spread is 4 times wider).
- With 3–4 designs per module a single SD is too noisy to rank. Pooled, the
  spreads are indistinguishable on every metric (p 0.41–0.99).

## Conclusions

1. **Report graded behaviour, not the verdict alone.** Partial equivalence on
   stimulus separates designs that the binary verdict lumps together (71 of 83
   are function_fail). It also shows that repair's gains on the shipped checks
   do not reach behaviour.
2. **An in-run metric must earn its use.** Before a golden-free score selects or
   steers anything, it should be shown to rank designs the way behaviour does.
   The shipped-check score fails that test: it is anti-correlated in most
   modules, cycle-exact or not. Peer agreement is the most promising candidate,
   positive in 4 of 5 modules, but it reverses on fpu.
3. **The bottleneck is generation, not selection or latency.** Nearly every
   generated design is its own non-golden behaviour; the golden-chosen best of
   four beats random by only about 2.5 points; and latency accounts for under a
   tenth of the disagreement.

## Caveats

- Behaviour classes are on the stimulus: equal traces don't prove equivalence
  (so distinct counts are lower bounds). Unequal traces do prove a difference.
  On the 83 designs the stimulus and the formal verdict agree exactly.
- The stimulus is the runs' own, realized by each run's reference model. In
  i2c, about a third of testpoints contain a wait that never resolved under that
  model, so long idle stretches weight the edge metric. The testpoint metrics
  are not weighted that way.
- In one simulation a corpus's testpoints run back to back, each after the
  testbench's reset. State that a reset does not clear still carries over, the
  same for every design, as it does in the shipped testbench.
- The open-loop harness does not wire the open-drain lines; the closed-loop one
  does, as the shipped testbench does.
- Small samples: 3–4 generated designs per corpus; correlations within module
  pool corpora whose shipped check sets differ.
- Two round-0 designs are missing (15 before/after pairs, not 17).

## Reproduce

All CPU, no model calls, from the committed corpora and designs (about 40
minutes on 4 cores):

    export E7_BEHAVIOUR_WORK=/tmp/e7_behaviour
    for each <run> <module>: python3 docs/evidence/e7_behaviour/realize.py <run> <module>
    for each <module>:       python3 docs/evidence/e7_behaviour/sim.py <module>
                             python3 docs/evidence/e7_behaviour/closed_loop.py <module>
    python3 docs/evidence/e7_behaviour/metrics.py
    python3 docs/evidence/e7_behaviour/latency.py
    python3 docs/evidence/e7_behaviour/report.py
    python3 docs/evidence/e7_behaviour/latency_report.py
    python3 docs/evidence/e7_behaviour/consistency.py     # reads BEHAVIOUR.json only

`BEHAVIOUR.json` has one row per design: identity, arm, verdict, behaviour
classes, and every grading and in-run metric above.
