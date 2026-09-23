# 81% of the suite drives the prescaler into a degenerate mode

`clk_cnt` is the clock prescale value: it is loaded into the divider that
generates `clk_en`, the tick the whole bit-level FSM advances on. At
`clk_cnt = 0` the divider reloads to zero, so `clk_en` fires every cycle and
there is no division to speak of.

    testpoints driving clk_cnt == 0 for the WHOLE trace:  342 of 422  (81%)

## What that costs, measured

    clk_en duty, split by whether the prescaler is degenerate

                 clk_cnt == 0 (342 traces)     clk_cnt > 0 (80 traces)
      GOLDEN     100% high of 13178 edges       44% high of 5273
      CANDIDATE   86% high of 13538             36% high of 5151

**On the degenerate traces golden's `clk_en` is free-running -- 100% high,
never once low.** With no division there is nothing to pause, and golden pauses
nothing. The spec-derived candidate gates it anyway, 14% low.

So a requirement about PAUSING the timing counter -- REQ-0051 "hold its timing
counter and keep clk_en low while slave_wait is asserted", REQ-0055 "pause its
timing counter until SCL is released", REQ-0117 the same -- is not observable
on 81% of the suite. On those traces "the counter is paused" and "the counter
is running" produce the same trace on a correct design, because the counter has
nothing to count.

## Why this matters to all three columns

**Audit.** REQ-0055 convicts golden, and the testpoint it is decided on
(TP-0017) drives `clk_cnt = 0`. The check asserts an obligation the
configuration makes unobservable, and golden's free-running `clk_en` reads as a
violation of it. That is a stimulus defect surfacing as a conviction of a
correct design.

**Blindness.** A cell is a disagreement between two spec-derived designs. The
entire prescaler-timing dimension is exercised in a degenerate mode four times
out of five, so disagreements THERE mostly never occur -- and a dimension that
produces no cells cannot be blind, it is simply absent from the denominator.
Blindness is measured over the cells the stimulus produced, not over the
behaviours the specification admits.

**Span.** The requirements are still covered -- a testpoint exists and the
check runs. Coverage is not the same as exercise, and nothing in the pipeline
distinguishes them here.

## What it does NOT establish

That golden is right and the candidate wrong on the degenerate traces. At
`clk_cnt = 0` the specification arguably does not determine whether `slave_wait`
should still gate `clk_en`, since there is no prescaling to gate. Both
behaviours may be faithful; that is a question about the text, not settled here.

Nor that REQ-0055's conviction is FULLY explained by this. It also fails on the
candidate, at a different edge, so at least one other thing is going on.

## The actionable part

`clk_cnt` is a 16-bit input and the stimulus stage drove it to 0 on 81% of
testpoints. Whatever chose that -- a default, an idle value, an unconstrained
pick collapsing to zero -- it left the module's central timing mechanism
exercised in its one degenerate configuration most of the time. That is
measurable before any check is authored, from `stimulus.json` alone, and
nothing measures it.
