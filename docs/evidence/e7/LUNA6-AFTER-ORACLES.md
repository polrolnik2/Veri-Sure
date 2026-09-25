# The frozen luna6 runs, scored as each oracle stage finishes

Five modules, each run from scratch (contract authored from the spec, S1
through the oracle stage) with the pipeline as of `0d8a0c6`. There are no RTL
editor rounds. Each run's shipped set (`shipped.json`: the admitted pool with
the latency refuser, cut to the greedy cover) is scored with
`e7_after_oracles.py` against golden, which is RUN and never read. The
hand-bound audit (`e7_bind_golden.py`) binds the contract's probes to golden's
own internals, and only this audit script reads that binding.

Golden replays re-run after `92c0d66`, which fixed stale inputs on reset rows
(see below).

## Figures

    module          span              blindness            audit (name)   audit (bound)
    or1200_sb       45/52  = 86.5%    6655/7637 = 87.1%    0/2            -- (0 of 9 probes exist)
    or1200_dc_fsm   57/80  = 71.2%    481/20862 =  2.3%    2/9  = 22%     20/49 = 41%
    fpu_exceptions  68/84  = 81.0%      0/29972 =  0.0%   44/68 = 65%     44/68 = 65% (all 50 bound)

i2c_master_byte_ctrl and i2c_master_bit_ctrl are still in their oracle stage.

## What each figure is made of

**sb blindness is a specification finding.** The description never states the
store-buffer FIFO depth. The seven spec-derived designs pick different depths,
so under a stream of stores with no BIU acknowledge they accept 3, 5, 9 or 13
writes (TP-0018). That disagreement touches every output port on 48 of 232
testpoints, and no check can separate it without asserting a depth the spec
does not give. Golden is the pass-through build (`OR1200_SB_IMPLEMENTED` is
commented out), so none of the nine probes exists in it and audit can be judged
on only two checks.

**dc_fsm span is the latency gate.** 18 of the 23 behavioural requirements
without a check were refused `latency:` after both repair attempts. Judged
against hand-bound golden, the refused corpus bodies split **22 pass / 25
fail**. On this module the gate is close to a coin flip, and it costs 18
requirements.

**dc_fsm audit is mostly checks the whole population also convicts.** Among the
64 shipped bodies, those that convict all 7 spec-derived designs (the existing
advisory `refuted_by_the_population`) are 15 of the 21 golden convictions,
against 2 golden-passing. An example is REQ-0010 on TP-0002: the check pairs
the post-edge state (`idle`) with the inputs sampled at that same edge, so it
reads a request presented while the FSM was still in LREFILL3 as one presented
in IDLE. Golden and all seven designs fail it.

**fpu audit is a contract misreading of the pipeline.** The contract authored
from the spec gives every output `latency_cycles: 1`. The spec describes several
registered stages (stage-0/1/2 copies of the output; output selection "through
registered intermediate results"), all gated by `enable`. The witness, the
population and the checks inherited the one-cycle reading, and the stimulus
pulses `enable` for a single cycle. Golden never updates `out` or `exception`
under a one-cycle pulse (TP-0242: golden's internal `inexact_trigger` rises,
`out` never moves), so a check expecting the result on the next row convicts
it. 35 of the 50 convictions fall within three rows of reset. Binding the 50
probes by hand changes nothing, because they bind to golden internals of the
same name.

## Offline experiments (no model calls)

Dropping every body the population refutes (design level), then re-cutting the
cover:

    set                          span     blind    audit (name)   audit (bound)
    dc_fsm  as shipped           71.2%     2.3%    2/9            20/49 = 41%
    dc_fsm  refuted dropped      61.3%     3.9%    0/7             7/38 = 18%
    full2   as shipped           97.4%    13.7%    9/41           52/100 = 52%
    full2   refuted dropped      88.6%    34.7%    8/37           34/87  = 39%

So it is **not** blindness-free. `refuted_by_the_population` is design-level:
it flags a body that convicts every design SOMEWHERE, and on full2 the same
bodies separate designs on other testpoints. Blindness rises 13.7% -> 34.7%.

Masking a body only on the testpoints where every deciding design convicts it
does cost no blindness, because a unanimous testpoint separates nothing. It
removes only 6 of dc_fsm's 21 bound convictions (21 -> 15 of 52), because
those bodies also convict golden elsewhere.

Neither is adopted. Both are measurements of where the residue sits.

## Harness defect found and fixed (`92c0d66`)

`Env.reset()` drove every functional input to idle, but `_record` bundled
`self._inputs`, which still held the pre-reset step. So an RTL trace recorded
the previous vector on reset rows, while `oracles.replay` (the population side)
recorded the idle one. On or1200_sb a pass-through check convicted the
pass-through golden on the reset rows of TP-0033 for values no pin carried.
With the fix, sb's name-bound audit goes 1/3 -> 0/2. dc_fsm is unchanged.

## The hand-bound residue, classified, and the forced-repair experiment

Every golden conviction of the shipped sets (dc_fsm, bit_ctrl, fpu; 115 in
all) was classified by an agent that read the spec, the check and the golden
trace rows, never golden's RTL: 40% the check misreads the spec or the trace,
49% contract / stimulus / harness, 11% the spec does not decide. None is a
golden violation. The dominant check error is ROW PAIRING: a row's post-edge
state read together with the inputs that produced it ("idle=1 and cs=1 in one
row" taken as a request presented in IDLE). The dominant harness causes are the
same convention seen from the other side -- a combinational acknowledge that
coincides with leaving a state is never recorded post-edge, so stimulus holds
`biudata_valid` into a fresh state to make it appear -- and the 16-edge settle
tail re-issuing a held command so a strong window is cut off mid-command.

Forced repair of every population-refuted shipped body, scored over the WHOLE
pool (no refuted body left anywhere in it for the re-cut cover to reach):

    set                               span     blind    audit (name)   audit (bound)
    dc_fsm   as shipped               71.2%     2.3%    2/9            20/49 = 40.8%
    dc_fsm   refuted dropped          61.3%     3.9%    0/7             7/38 = 18.4%
    dc_fsm   B: evidence repair       70.0%     3.5%    0/8            10/47 = 21.3%
    dc_fsm   C: B + `before` field    70.0%     3.1%    0/8            10/47 = 21.3%
    bit_ctrl as shipped               74.1%    39.3%    11/36          38/84 = 45.2%
    bit_ctrl refuted dropped          62.9%    61.1%    12/36          22/68 = 32.4%
    bit_ctrl B: evidence repair       70.7%    40.2%    13/38          28/78 = 35.9%

B tells the author all seven designs fail its check, states the row convention,
and shows the rows where they fail; a reply still refuted after two attempts is
dropped. dc_fsm: 17 targets, 15 repaired, golden convicts 15 originals and 4
repairs. bit_ctrl: 24 targets, 18 repaired, golden convicts 19 and 8. Repair
recovers the span that dropping costs; neither moves the residue below ~20%
(dc_fsm) or ~32% (bit_ctrl), because what is left is not refuted -- it is the
convention and the tail, which every design and golden meet alike.

## What changed after this (`4518076`, `8fe749e`)

* **Rows are sampled as an assertion samples them.** A clocked model is
  `outputs(i)` (reads the edge, changes nothing) + `advance(i)` (takes it); the
  simulator reads the DUT after its inputs settle and before the rising edge.
  A registered value changes in the row after the edge that loads it; a
  combinational acknowledge sits beside the inputs it answers. Author, reviewer
  and model prompts state it. Seven population models from one prompt had
  answered "which side of the edge" three ways.
* **No population-refuted body ships** (`exclude_refuted`, on by default).
* **A strong obligation opened in the settle tail and still pending when the
  rows run out abstains**; one opened while the stimulus drove still lapses.
* A wide probe is a value in the Python replay, not a 0/1 flag.

dc_fsm and bit_ctrl are re-running from their oracle stage on luna6's upstream
artifacts (`/home/user/runs/luna8`) to measure these.

## Oracle-stage re-runs on luna6's upstream (`/home/user/runs/luna8`, `luna9`, `luna10`)

Each re-runs ONLY the oracle stage, on luna6's contract, requirements,
testplan and stimulus, so the change in the figures is the oracle-stage and
testbench change alone. "removed" is the pipeline default (no
population-refuted body ships); "kept" re-cuts the same pool with them.

    dc_fsm                      span     blind    audit (name)  audit (bound)
    luna6 as shipped            71.2%     2.3%    2/9           20/49 = 40.8%
    luna8  sampled rows, removed 77.5%   49.6%    1/7            5/55 =  9.1%
    luna8                  kept 92.5%     4.4%    1/9           18/68 = 26.5%
    luna9  + witness-row repair 82.5%    73.6%    1/9            5/62 =  8.1%
    luna9                  kept 91.2%     4.9%    1/10          14/69 = 20.3%
    luna10 + cells (60), removed 87.5%    0.7%    1/8            8/63 = 12.7%
    luna10                 kept 93.8%     0.7%    1/9           14/68 = 20.6%

    bit_ctrl                    span     blind    audit (name)  audit (bound)
    luna6 as shipped            74.1%    39.3%    11/36         38/84 = 45.2%
    luna8  sampled rows, removed 86.2%   52.8%    9/36          25/93 = 26.9%
    luna8                  kept 94.8%    29.5%    14/40         51/106 = 48.1%

**Sampled rows took the convention noise out of the population.** dc_fsm's
disagreement cells fell from 20,862 to 1,194: the seven designs now differ
only where they read the spec differently.

**Refutation became exact.** Among shipped bodies every deciding design fails,
golden fails 13 of 16 on dc_fsm (luna8) and 36 of 36 on bit_ctrl. "All but
one" is NOT clean: at 6 of 7, bit_ctrl has 8 golden convictions and 3 passes.

**Refuted bodies were carrying the blindness figure.** Leaving them out took
dc_fsm's blindness to 49.6-73.6%: nearly every cell the set appeared to
separate was separated only by a check that fails every reading somewhere.
Authoring at those cells (`--cell-budget 60`; 8 targets, one per requirement
owning a blind testpoint) closed it: 0.7% with them left out, span 87.5%.

**Witness-row repair engages but does not change the pool much.** Authors
shown the witness failing their check rewrote it (e.g. a trigger that opened
in IDLE), but most refuted bodies in the pool are superseded drafts, which the
exclusion already handles.

**dc_fsm's remaining 8 hand-bound convictions** (luna10, removed): 5 on one
testpoint whose stimulus flips `tagcomp_miss` from 1 to 0 between accepting a
load and the BIU word arriving -- golden decides on the second CLOAD cycle and
takes the hit path; 3 checks failed by 6 of 7 designs; 3 by none (e.g. a
cache-inhibited load's `biu_read` demanded in the first CLOAD cycle, where
golden raises it one cycle later). The stimulus is luna6's, authored before the
specification reached every stage.

**bit_ctrl here still runs on luna6's contract**, which gives `cmd` no encoding,
so every design guessed what 4 and 8 mean; luna7's contract imports them from
`i2c_master_defines.v`.
