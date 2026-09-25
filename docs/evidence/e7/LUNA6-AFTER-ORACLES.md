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
