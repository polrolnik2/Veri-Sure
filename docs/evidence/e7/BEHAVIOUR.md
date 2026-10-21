# Measuring behaviour when there is no golden in the loop

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
  sampled before each rising edge, as the checks sample. A golden X counts as
  don't-care (at most 1.3% of edges on 2 ports).
- **Closed loop** (`closed_loop.py`, for latency). Each design runs the stimulus
  the way the shipped testbench does: `until` waits resolve on **its own**
  outputs, with the same budget and settle edges, and open-drain lines wired
  (`line = stimulus AND *_oen`).
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
| dc_fsm | generated | 12 | 12 | 12 | 0 |
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

**Generation produces a different wrong behaviour almost every time** (57
distinct non-golden behaviours among 66 generated designs). **Repair does not
converge** on any of them, or on golden: it produces one more.

## 2. Partial equivalence to golden, open loop

| module | arm | n | edges | testpoints | port traces | order-only |
|---|---|---|---|---|---|---|
| fpu | generated | 15 | 68.9% | 11.9% | 56.6% | 25.7% |
| fpu | repaired | 4 | 67.6% | 7.6% | 52.7% | 23.0% |
| bit_ctrl | generated | 16 | 31.1% | 5.4% | 64.9% | 12.8% |
| bit_ctrl | repaired | 4 | 29.1% | 5.6% | 64.9% | 12.3% |
| byte_ctrl | generated | 11 | 2.8% | 0.4% | 40.2% | 0.4% |
| byte_ctrl | repaired | 3 | 2.1% | 0.4% | 41.0% | 0.4% |
| dc_fsm | generated | 12 | 90.6% | 72.7% | 93.9% | 72.6% |
| dc_fsm | repaired | 3 | 88.0% | 74.2% | 92.6% | 74.1% |
| sb | generated | 12 | 76.7% | 67.9% | 82.5% | 68.6% |
| sb | repaired | 3 | 50.2% | 39.1% | 63.3% | 39.2% |
| **all** | generated | 66 | 54.1% | 29.7% | 67.4% | 34.7% |
| **all** | repaired | 17 | 47.5% | 23.2% | 62.4% | 28.4% |

## 3. Before and after repair, same job

15 jobs, from the editor's round 0 to its final, open loop:

| metric | before -> after (mean) | without luna13 sb | up / down / same |
|---|---|---|---|
| edges equal to golden | 55.8% -> 49.1% | 52.6% -> 50.8% | 5 / 9 / 1 |
| testpoints equal | 31.9% -> 25.7% | 27.0% -> 26.9% | 4 / 7 / 4 |
| port traces equal | 69.3% -> 64.2% | 67.1% -> 65.6% | 3 / 10 / 2 |
| order-only equal | 37.1% -> 30.4% | 32.6% -> 31.9% | 5 / 6 / 4 |
| **shipped checks passed** (in-run) | **75.5% -> 83.9%** | **77.8% -> 82.9%** | **11 / 2 / 2** |

**Repair raises the in-run score and does not move behaviour toward golden.**
Without the one outlier, behaviour is flat to slightly worse on every measure.
The outlier, luna13 sb, goes from equivalent (100%) to 25% of edges, because it
was repaired toward checks built on a buffering reference model.

## 4. Do the in-run metrics track behaviour?

Spearman rank correlation with edges equal to golden, within each module:

| module | n | shipped checks | agreement with the run's reference model | agreement with peers |
|---|---|---|---|---|
| fpu | 19 | -0.37 | -0.12 | -0.40 |
| bit_ctrl | 20 | +0.45 | +0.08 | -0.17 |
| byte_ctrl | 14 | -0.04 | +0.22 | +0.59 |
| dc_fsm | 15 | -0.49 | +0.39 | +0.50 |
| sb | 15 | -0.80 | -0.72 | +0.86 |

**The pipeline's own score, the shipped-check pass rate, is negatively
correlated with behaviour in 4 of 5 modules.** None of the three in-run metrics
is consistently positive. Peer agreement comes closest: positive in 3 of 5,
negative on fpu and bit_ctrl.

**Selection.** The pool is a corpus's generated designs. Each pick is scored by
edges equal to golden:

| selection | mean edges equal to golden | picks the golden-best (of 17) |
|---|---|---|
| random (mean of pool) | 53.6% | -- |
| by shipped checks | 51.7% | 3 |
| by agreement with the run's reference model | 54.2% | 8 |
| by agreement with peers | 53.9% | 5 |
| golden-chosen best (**not available in a run**) | 56.9% | -- |
| repaired (editor final) | 47.5% | -- |

- **Picking by the shipped checks is worse than picking at random.** The repair
  loop optimizes that same score and ends lower still.
- The best golden-free selector (the reference model) gains 0.6 points over
  random.
- Even the unattainable golden-chosen best is only 3.3 points above random. The
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
| fpu | generated | 15 | 11.9% | 11.9% | 25.8% | **13.9%** | 88.4% |
| fpu | repaired | 4 | 7.6% | 7.6% | 23.1% | **15.5%** | 84.0% |
| bit_ctrl | generated | 16 | 5.4% | 10.2% | 21.7% | **11.5%** | 77.3% |
| bit_ctrl | repaired | 4 | 5.6% | 9.6% | 18.5% | **8.9%** | 73.8% |
| byte_ctrl | generated | 11 | 0.4% | 2.9% | 2.9% | **0.0%** | 43.0% |
| byte_ctrl | repaired | 3 | 0.4% | 2.5% | 2.5% | **0.0%** | 42.4% |
| dc_fsm | generated | 12 | 72.7% | 72.8% | 72.8% | **0.0%** | 94.1% |
| dc_fsm | repaired | 3 | 74.2% | 74.5% | 74.5% | **0.0%** | 93.1% |
| sb | generated | 12 | 67.9% | 68.0% | 68.7% | **0.7%** | 84.2% |
| sb | repaired | 3 | 39.1% | 39.2% | 39.3% | **0.0%** | 65.7% |
| **all** | generated | 66 | 29.7% | 31.3% | 37.3% | **6.1%** | 78.4% |
| **all** | repaired | 17 | 23.2% | 24.6% | 30.3% | **5.7%** | 72.6% |

- **Latency explains about a tenth of the disagreement.** Of the testpoints
  where a design differs from golden cycle-exactly, 9% (generated) and 8%
  (repaired) differ only in timing.
- That share is concentrated in fpu (14–16 points) and bit_ctrl (9–12 points).
  It is zero for byte_ctrl and dc_fsm.
- **No design is golden-equivalent up to latency** apart from the 8 that are
  equivalent outright.
- The best latency-independent shares per module are: fpu 26.8%, bit_ctrl
  32.9%, byte_ctrl 4.1%, dc_fsm 86.6% of testpoints.
- **Factoring out latency merges no behaviours.** Distinct behaviours modulo
  latency equal the cycle-exact counts in every module and arm.
- Closing the loop recovers 1.6 points over open loop (29.7% -> 31.3%), mostly
  on bit_ctrl and byte_ctrl. So the open-loop cascade was small.
- What survives even the weakest comparison is large. Each output port's
  sequence of values, ignoring all timing, matches golden on only 78% (generated)
  and 73% (repaired) of port traces. On byte_ctrl it is 43%.

**Repair, latency-independent.** Closed-loop order-only goes 39.2% -> 32.3%
(34.9% -> 34.0% without luna13 sb); per-port order-only goes 78.8% -> 73.4%
(77.3% -> 75.2%). Up 5, down 8 and same 2 of 15 jobs on order-only. The repair
loop optimizes order-only checks, and it still does not improve order-only
behaviour.

**The in-run metrics against the latency-independent score:** shipped checks
-0.15, +0.11, -0.25, -0.33, -0.80 (fpu, bit_ctrl, byte_ctrl, dc_fsm, sb).
Making the grade order-only, like the checks, does not make the checks track it.
Peers come out +0.55, +0.72 and +0.87 on bit_ctrl, byte_ctrl and sb, but -0.19
and -0.32 on fpu and dc_fsm. Selection scored order-only gives:
- random 36.7%;
- by shipped checks 36.3%;
- by reference model 38.2%;
- by peers 37.4%;
- golden-chosen best 40.2%;
- repaired 30.3%.

## 6. Consistency: before against after repair

Computed by `consistency.py` from `BEHAVIOUR.json`; it also prints the full
spread tables.

**Spread.**
- Designs generated for one corpus scatter by a few points: standard deviation
  0.6–3.7 points of edges and 0.5–5.2 of order-only testpoints.
- Across reps the spread is similar, except sb. There every rep is either
  golden's pass-through or a buffering design, so it splits 100% / ~25%.
- The repaired arm is no tighter than the generated one. fpu's edge spread
  narrows (SD 4.1 -> 0.9), but its order-only spread widens (0.9 -> 5.8).

**Paired change, 15 jobs, round 0 -> final:**

| metric | mean change (pts) | 95% bootstrap CI | median | up / down / same | Wilcoxon p | without luna13 sb: mean, CI, p |
|---|---|---|---|---|---|---|
| edges equal (open loop) | -6.7 | [-17.1, -0.5] | -0.0 | 5 / 9 / 1 | 0.135 | -1.8, [-3.7, -0.1], 0.244 |
| testpoints equal (open loop) | -6.2 | [-18.8, +0.7] | +0.0 | 4 / 7 / 4 | 0.465 | -0.1, [-1.1, +1.0], 0.770 |
| order-only testpoints (closed loop) | -6.9 | [-20.2, +1.5] | -0.1 | 5 / 8 / 2 | 0.414 | -0.8, [-4.4, +2.4], 0.677 |
| per-port order-only (closed loop) | -5.4 | [-13.2, -0.2] | -1.6 | 3 / 10 / 2 | 0.057 | -2.1, [-5.1, +0.5], 0.110 |
| **shipped checks (in-run)** | **+8.5** | **[+1.9, +17.0]** | **+4.5** | **11 / 2 / 2** | **0.017** | **+5.0, [+0.6, +9.6], 0.034** |

**Repair against drawing another design.** For each job, another of the
corpus's generated designs stands in for the repaired one:

| metric | repair: mean change | resample: mean change | repair beats resample | permutation p | without luna13 sb: repair vs resample, p |
|---|---|---|---|---|---|
| edges equal | -6.7 | -0.0 | 38% of 45 | 0.022 | -1.8 vs -0.0, 0.190 |
| testpoints equal | -6.2 | +0.1 | 49% | 0.099 | -0.1 vs +0.1, 0.928 |
| order-only testpoints | -6.9 | +0.4 | 36% | 0.061 | -0.8 vs +0.5, 0.522 |
| per-port order-only | -5.4 | +1.1 | 38% | 0.009 | -2.1 vs +1.2, 0.057 |
| shipped checks | +8.5 | +0.5 | 82% | 0.015 | +5.0 vs +0.5, 0.110 |

What this shows:
- **The shipped-check score moves reliably.** Up in 11 of 15 jobs, significant
  with and without the outlier.
- **Behaviour does not.** No behaviour metric changes significantly (Wilcoxon
  p ≥ 0.057). Medians are about zero, and the negative means are mostly
  luna13 sb.
- **Without luna13 sb, repair's change in behaviour is the size of drawing
  another design** (2.5 vs 3.3 points of edges) and indistinguishable from it
  (p 0.19–0.93). It leans slightly negative: repair beats a fresh sample in
  only 38–52% of comparisons. Per-port order-only is the nearest to a
  detectable loss (p 0.057).
- **The two scores are unrelated per job.** The four behaviour metrics move the
  same way in 10 of 15 jobs. The size of a job's shipped-check gain does not
  predict its behaviour change (Spearman -0.38 to +0.25).
- **Neither arm is the better one.** The figures are stable to within sampling
  noise on both sides of repair, and the one large change (luna13 sb) is for
  the worse.

## Conclusions

1. **Report graded behaviour, not the verdict alone.** Partial equivalence on
   stimulus separates designs that the binary verdict lumps together (71 of 83
   are function_fail). It also shows that repair's gains on the shipped checks
   do not reach behaviour.
2. **An in-run metric must earn its use.** Before a golden-free score selects or
   steers anything, it should be shown to rank designs the way behaviour does.
   The shipped-check score fails that test: it is anti-correlated in most
   modules, cycle-exact or not. Peer agreement is the most promising candidate,
   but it is inconsistent on n = 14–20 per module.
3. **The bottleneck is generation, not selection or latency.** Nearly every
   generated design is its own non-golden behaviour; the golden-chosen best of
   four beats random by only about 3 points; and latency accounts for about a
   tenth of the disagreement.

## Caveats

- Behaviour classes are on the stimulus: equal traces don't prove equivalence
  (so distinct counts are lower bounds). Unequal traces do prove a difference.
  On the 83 designs the stimulus and the formal verdict agree exactly.
- The stimulus is the runs' own, realized by each run's reference model. In
  i2c, about a third of testpoints contain a wait that never resolved under that
  model, so long idle stretches weight the edge metric. The testpoint metrics
  are not weighted that way.
- In one simulation a corpus's testpoints run back to back. Each starts with its
  reset step, but state a reset does not clear carries over identically for
  every design.
- The open-loop harness does not wire the open-drain lines; the closed-loop one
  does, as the shipped testbench does.
- Small samples: 3–4 generated designs per corpus; correlations within module
  pool corpora whose shipped check sets differ.
- Two round-0 designs are missing (15 before/after pairs, not 17).

## Reproduce

All CPU, no model calls, from the committed corpora and designs (about 30
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
