# Checks-only editor feedback: what changes when the reference model stops being "expected"

`QUALITATIVE.md` found that repair converges on the run's reference model, misreadings
included. The reference model is one LLM reading of the specification, yet the RTL Editor
was handed it as ground truth on five channels:
- failure rows whose `expected=` is the model's value;
- the trace report built from those rows;
- the failing-testpoint count (DUT against model) as its gradient;
- the model-compare ACCEPT as its stop condition;
- the model's source, labelled "the expected behaviour".

This rerun asks what repair does when all five are replaced by the shipped checks alone.
What the repair changed in the RTL, arm by arm, is in `CHECKS-FEEDBACK-QUALITATIVE.md`.

## Setup

- **Two arms, one start each.** Every job repairs one starting design twice, with
  `e7_rtl_editor.py --feedback`:
  - **checks:** the editor sees only the shipped checks. That is the failing requirements'
    text, each check's own complaint and the edge where it fired, the design's own port
    values around that edge, and the checks' source. It stops when no shipped check fails.
    Its gradient is the count of failing check instances. No value the model computed
    reaches it (706d973).
  - **model:** the old feedback on current code, as the control.
  - **When a commit latches:** in both arms, when passing shipped requirements rise. It also
    latches when they hold, nothing is silenced, and the arm's own progress count falls. In the
    model arm that count is testpoints disagreeing with the model, so the model also steers
    those ties (`CHECKS-FEEDBACK-QUALITATIVE.md`).
- **Starts.**
  - sb, dc_fsm, bit_ctrl: each original job's round-0 design (`rtl_generated.sv`).
  - byte_ctrl: a fresh generation per run, with its child `i2c_master_bit_ctrl` supplied
    to the lint gate (41958ed). Every earlier byte_ctrl design had a stand-in child; see
    "byte_ctrl" below.
- **Same budget as the originals:** 3 rounds, 20 trials, the run's shipped checks, its
  rendered suite.
- **Fidelity check.** The suites were rebuilt from the corpora as `integration.py` renders
  them. All 7 original round-0 designs reproduce their original review exactly, failing
  requirement lists included.
- **Jobs.** 10 jobs, 20 arms, all finished. luna13 byte_ctrl's checks arm was resumed
  after interruptions; see its `RESUME.md`.
- **Scoring** uses the behaviour harness (`BEHAVIOUR.md`, with the per-testpoint reset) and
  ChipVerilog. Golden is used for scoring only.

## What happened

| | start | checks arm | model arm |
|---|---|---|---|
| edges equal to golden, mean of 9 jobs (excl. sb luna13) | 61.1% | 53.7% | 53.0% |
| agreement with the run's reference model, same 9 | 54.3% | **55.5%** | **64.8%** |
| same, all 10 jobs | 53.3% | 54.4% | 68.3% |
| jobs where golden agreement fell / rose (edges, of 10) | | 5 / 4 | 7 / 2 |
| shipped checks passed, mean of 10 | 68.8% | 82.0% | 87.2% |
| ChipVerilog pass, of 10 | | 1 (sb luna13, induction) | 1 (byte_ctrl luna12, bounded k=16 only; see below) |
| mean model calls / trials / hours per job | | 214 / 9.2 / 2.5 | 297 / 10.3 / 3.0 |

1. **Without the model in the feedback, repair no longer moves designs onto the
   reference model.** Under model feedback, agreement with the run's reference model
   rises 10–15 points. Under checks only it stays where the start was (+1 point), and it
   is lower than the model arm in 8 of 10 jobs. (Calls and hours for luna13 byte_ctrl's
   checks arm count only its final resume; its trials count the whole chain.)
2. **That does not make repair move designs toward golden.** Both arms end further from
   golden than they started: 7 and 8 points, on average, excluding sb luna13.
   - The checks are not derived from the reference model: they are written before it
     exists.
   - But they are written by the same LLM from the same text.
   - They are then kept or dropped by a vote of further readings by the same LLM: the
     population. The witness can only trigger repairs, and the shipped set is chosen on
     the population alone.

   So they share the model's common-mode misreadings, and repair satisfies those.
   Checks-only feedback lost golden agreement in 5 of 10 jobs, model feedback in 7 of 10.
3. **The largest single difference is sb luna13.** The start is formally equivalent to
   golden.
   - **Checks arm:** found no edit the checks would latch (28/7/31 for all 3 rounds) and
     returned it unchanged. That was not the feedback protecting it. The editor's signal tool
     reads both arms of an `` `ifdef `` as conflicting drivers, so all 9 commits deleted live
     code (`CHECKS-FEEDBACK-QUALITATIVE.md`).
   - **Model arm:** reached 65/0/1 by defining `OR1200_SB_IMPLEMENTED` inside the module
     and building the FIFO, exactly as the original job did. That took golden agreement
     from 100% to 45% of edges.
4. **The same misreading broke sb luna14 under both feedbacks.** That start is also
   equivalent to golden. Both arms reached 65/0/1 within 4 commits, by two forms of the
   same configuration move:
   - checks arm: `` `define OR1200_SB_IMPLEMENTED ``;
   - model arm: inverting the guard to `` `ifndef OR1200_SB_NOT_IMPLEMENTED ``.

   The checks require the FIFO, because every population model built one, so removing
   the model does not remove the pull. The original model-feedback job kept this design
   equivalent; that was not repeated.
5. **Where the start is already close, both feedbacks leave it close.** dc_fsm starts at
   90–96% of edges equal to golden and stays there under either arm (89.6–96.1%). On
   whole testpoints the arms split in opposite directions on two runs: luna12 favours
   model (81.6 vs 69.5), luna13 favours checks (83.1 vs 75.3).
6. **Checks-only feedback is not weaker at satisfying the checks.**
   - It went further than model feedback on 3 jobs: bit_ctrl luna12 (87 vs 81 passing),
     byte_ctrl luna14 (80 vs 72) and byte_ctrl luna13 (75 vs 58).
   - It went less far on 3: byte_ctrl luna12 (56 vs 70), dc_fsm luna12 (67 vs 77) and
     sb luna13, where it kept the equivalent start.
   - The other 4 tie.
   - It made about a quarter fewer model calls per job (214 vs 297), mostly by stopping
     earlier when nothing latches.

   Passing more checks is not progress: on byte_ctrl luna13 the checks arm passes 75 to the
   model arm's 58 yet matches golden on fewer edges (31.0% vs 43.7%).

### Per job

Golden-graded columns: `g_edge` (edges equal to golden), `g_tp` (whole testpoints equal),
`cl_order` (closed loop, order of distinct output states equal). `ref` is edge agreement
with the run's own reference model; `ship` is shipped requirements passed. The original
final is the original job's (model feedback, earlier code), for reference; for byte_ctrl it
repaired a different, stand-in start.

| job | design | verdict | ship | g_edge | g_tp | cl_order | ref |
|---|---|---|---|---|---|---|---|
| bit_ctrl luna12 | start | function_fail | 74.8 | 18.4 | 3.2 | 14.5 | 66.3 |
| | original final | function_fail | 74.8 | 15.6 | 1.8 | 4.9 | 83.1 |
| | **model** | function_fail | 78.6 | 17.6 | 2.1 | 14.3 | 71.7 |
| | **checks** | function_fail | 84.5 | 18.5 | 2.0 | 9.8 | 62.6 |
| byte_ctrl luna12 | start (real child) | function_fail | 59.1 | 42.7 | 27.0 | 27.4 | 0.9 |
| | original final | function_fail | 81.8 | 1.9 | 0.0 | 0.0 | 0.0 |
| | **model** | pass (k=16) | 79.5 | 35.0 | 19.8 | 27.0 | 0.4 |
| | **checks** | function_fail | 63.6 | 43.8 | 27.2 | 27.5 | 0.9 |
| byte_ctrl luna13 | start (real child) | function_fail | 50.5 | 34.4 | 21.4 | 21.5 | 5.6 |
| | original final | function_fail | 73.2 | 6.7 | 11.4 | 11.5 | 84.8 |
| | **model** | function_fail | 59.8 | 43.7 | 20.0 | 27.4 | 5.5 |
| | **checks** | function_fail | 77.3 | 31.0 | 19.5 | 20.0 | 5.4 |
| byte_ctrl luna14 | start (real child) | function_fail | 73.5 | 16.7 | 13.8 | 19.6 | 7.4 |
| | original final | function_fail | 60.2 | 4.2 | 11.3 | 11.4 | 3.9 |
| | **model** | function_fail | 73.5 | 16.7 | 13.8 | 19.6 | 7.4 |
| | **checks** | function_fail | 81.6 | 16.1 | 13.5 | 14.7 | 11.5 |
| dc_fsm luna12 | start | function_fail | 82.5 | 95.7 | 75.4 | 75.4 | 90.6 |
| | original final | function_fail | 86.2 | 90.8 | 82.8 | 82.8 | 99.9 |
| | **model** | function_fail | 96.2 | 90.4 | 81.6 | 81.6 | 98.6 |
| | **checks** | function_fail | 83.8 | 92.6 | 69.5 | 69.5 | 89.1 |
| dc_fsm luna13 | start | function_fail | 90.5 | 90.3 | 79.0 | 79.0 | 98.9 |
| | original final | function_fail | 100.0 | 89.6 | 75.3 | 75.3 | 100.0 |
| | **model** | function_fail | 100.0 | 89.6 | 75.3 | 75.3 | 100.0 |
| | **checks** | function_fail | 100.0 | 90.6 | 83.1 | 83.1 | 98.1 |
| dc_fsm luna14 | start | function_fail | 82.3 | 95.8 | 70.9 | 70.9 | 99.6 |
| | original final | function_fail | 93.7 | 96.0 | 75.2 | 75.2 | 100.0 |
| | **model** | function_fail | 93.7 | 96.1 | 75.5 | 75.5 | 99.9 |
| | **checks** | function_fail | 93.7 | 95.9 | 74.9 | 74.9 | 99.7 |
| sb luna12 | start | equivalence_error | 89.7 | 56.1 | 36.7 | 36.7 | 77.8 |
| | original final | equivalence_error | 94.1 | 44.5 | 34.1 | 34.1 | 97.4 |
| | **model** | equivalence_error | 94.1 | 43.2 | 34.1 | 34.1 | 99.8 |
| | **checks** | equivalence_error | 94.1 | 53.9 | 35.7 | 35.7 | 77.2 |
| sb luna13 | start | pass | 42.4 | 100.0 | 100.0 | 100.0 | 43.8 |
| | original final | equivalence_error | 98.5 | 44.6 | 34.1 | 34.1 | 100.0 |
| | **model** | function_fail | 98.5 | 44.6 | 34.2 | 34.2 | 100.0 |
| | **checks** | **pass** | 42.4 | 100.0 | 100.0 | 100.0 | 43.8 |
| sb luna14 | start | pass | 42.4 | 100.0 | 100.0 | 100.0 | 42.1 |
| | original final | pass | 47.0 | 100.0 | 100.0 | 100.0 | 42.1 |
| | **model** | function_fail | 98.5 | 44.6 | 34.2 | 34.2 | 100.0 |
| | **checks** | equivalence_error | 98.5 | 40.5 | 34.1 | 34.1 | 55.4 |

## byte_ctrl: the missing child, and the command codes behind it

All 14 earlier byte_ctrl designs wrote their own stand-in for `i2c_master_bit_ctrl`. The
generator's lint gate had no child source and rejected a correct instantiation ("Cannot find
file containing module"); see root cause 2 in `QUALITATIVE.md`. With the child supplied to
every lint (41958ed), all three new generations instantiate it as `bit_controller`.

| byte_ctrl designs | n | edges equal to golden | testpoints equal | closed-loop per-port order | shipped checks |
|---|---|---|---|---|---|
| generated, stand-in child | 11 | 5.1% (0.0–8.1) | 8.2% | 47.5% | 76.7% |
| repaired, stand-in child | 3 | 4.2% (1.9–6.7) | 7.6% | 46.5% | 71.7% |
| **generated, real child** | 3 | **31.3%** (16.7–42.7) | **20.7%** | **61.0%** | **61.0%** |
| real child, then repaired (both arms) | 6 | 31.0% (16.1–43.8) | 19.0% | 60.0% | 72.6% |

- **Golden agreement:** about 6× more edges equal golden with the real child. The worst
  real-child design beats the best stand-in design.
- **Shipped checks:** fall by 16 points. The run's checks and reference model were written
  by a pipeline with the same stand-in reading, and they reward it.
- **Repair on top:** under either feedback it recovers about 10 points of checks and
  leaves golden agreement unchanged.

**A ChipVerilog "pass" here is not equivalence.** luna12's model-arm final passes as
`bounded_seq`, k=16 from a zero-initialised state, yet only 35.0% of its edges equal golden.
A byte transfer takes far longer than 16 cycles, so the bound never reaches the behaviour
that differs. Every other pass in this study is an induction proof that the harness confirms
at 100%.

## What this means

1. **Stop calling the reference model expected.** With checks-only feedback, repair stops
   rendering the model's reading in RTL: reference-model agreement stays flat instead of
   rising 10–15 points, and the checks are satisfied about as well.
2. **It is not sufficient on its own.** The checks are independent of the model, but they
   are another reading of the same text by the same LLM, so repair against them still
   imports the misreadings the two share. That is the luna14 sb
   result under both arms, and the mean loss of golden agreement under both. The fix is the
   reading, not the feedback channel (`QUALITATIVE.md`, rules R1–R6).
3. **Refuse the configuration move outright.** Both sb breakages, and the original luna13 sb
   repair, came from defining or inverting a configuration macro inside the module. This is
   R1, and the editor should reject it mechanically, whatever the feedback.
4. **Fix the environment first.** Supplying byte_ctrl's child was worth more than any repair:
   about 6× golden edge agreement, against no change from repair under either feedback. The
   next defect behind it is the command encoding the child decodes. The spec gives no values,
   and every design swaps READ and WRITE. Correcting those two constants takes luna12's start
   from 43.2% to 97.6% of edges equal to golden, and luna13's from 34.4% to 74.1%
   (`BYTE-CTRL-CODES.json`).

## Caveats

- **One run per arm.** Repair is noisy. luna13 byte_ctrl's checks arm reached 58/20/19 after
  round 1 in one attempt and 55/21/21 in the next, from the same start. Differences of a few
  points between arms are within that noise. sb luna13 and luna14, both equivalent starts,
  show that even the direction of the outcome can depend on whether the editor happens on
  the configuration move.
- **luna13 byte_ctrl, checks arm, took six launches (five interruptions).**
  - An OOM kill: the reviewer kept every check's per-testpoint rows; fixed in 4eba03f.
  - A provider 5xx.
  - Two gateway connection resets.
  - A container restart.

  Its `RESUME.md` records which work each launch kept. The final design's chain used 20
  trials over 3 rounds, like every other job, but its round-1 repair was attempted more than
  once.
- **luna12 dc_fsm, model arm:** its probe-port `rtl.sv` was lost after the job finished; see
  that directory's `NOTE.md`. The deliverable ChipVerilog graded, and that the harness
  simulates, was recovered.
- **Gateway path:** the environment's `OPENAI_BASE_URL` path (`/api/v1`) is stale; the
  gateway serves `/v1`. The reruns overrode the path in-process, same host and credentials.
- **Evidence stored:** RTL, summaries and verdicts only, under
  `<run>/editor-cf-{gen,checks,model}/<module>/`. Editor logs and model I/O are not in the
  repository.

## Reproduce

- `e7_module.py <runs-root> <module> --editor-only --tag cf-checks --feedback checks --rtl <start>`
- the same with `--tag cf-model --feedback model`
- byte_ctrl's start: `--rounds 0 --tag cf-gen`, with the child passed automatically by
  `e7_module.py`.
- Scoring:
  1. `e7_behaviour/sim.py` and `closed_loop.py <module> <design>...`
  2. `metrics.py`
  3. `latency.py`
  4. `checks_feedback.py`, which writes `CHECKS-FEEDBACK.json`
