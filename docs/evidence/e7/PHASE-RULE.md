# A decision-time probe-phase rule, measured four ways, and not adopted

## Why it was tried

With the pipeline's own rules only -- the cover shipped by `build_artifacts`,
no licence demotion, no advance of golden's probes -- `full2` scores:

    span 97.4%   blindness 5.9%   audit 10/41

Six of the ten convictions (REQ-0035, 0066, 0067, 0110, 0111, 0112) are the
probe-phase mechanism `PHASE.md` names: the specification writes
`sta_condition = ~sSDA & dSDA & sSCL`, an equation and not a schedule; golden
registers it; every spec-derived population member computes it on the same
row (measured below). The audit figure `COVER.md` reported (1/38) was reached
by reading golden's `sta_condition`/`sto_condition` one edge early -- a rule
applied to the CONTROL only, naming two bit_ctrl probes. That cannot be a
pipeline rule: it adjusts the grade, not the checks.

The candidate pipeline rule was uniform instead: judging ANY design, a
conviction that a probe's unstated schedule can undo is not evidence.

## The four variants, on `full2`, cover re-cut under each

    rule                                            blind     audit
    none (pipeline today)                           5.9%      10/41
    one probe at a time, +1, non-False exonerates   12.7%      8/40
    one probe at a time, +/-1, non-False            16.0%      6/38
    one probe at a time, +1, PASS exonerates        11.2%      8/40
    one probe at a time, +/-1, PASS exonerates      14.1%      7/39

The symmetric variant was fixed in advance as the one to adopt (the
specification admits both readings, so neither direction is privileged), and
PASS-only was adopted as a correction on principle before its number was seen
(an abstention is not a vindication -- `_worst`, `PHASE.md`). Every variant
breaks blindness < 10% and none reaches audit 0, so none is wired.
`oracles.decide(..., phase_free=...)` exists, is tested, and has no caller.

## Why it fails, measured

**The population does not diversify on phase.** Where the spec's START
equation holds on a replayed trace, all seven `full2` designs assert
`sta_condition` on the same row, 13 of 13 each. So the blindness the rule costs
is not phase diversity the population legitimately contains; a shift rule
cannot tell "registered" from "wrong by one row", and exonerates both.

**One probe at a time is the wrong unit.** REQ-0110's check asserts
`sta_condition` iff the START comparison AND `sto_condition` iff the STOP
comparison, on every row. Golden fails it on TP-0000 under every single-probe
shift, and passes only when both conditions move together. REQ-0067 by
contrast passes with `sto_condition` alone moved; moving its trigger `ssda`
the other way ALSO passes it, which is the leak -- a shifted trigger relocates
the activation rather than testing a schedule.

## What is being measured next

The normalized form already separates the two roles: `observable` is what a
requirement asserts, `activation.opens_on`/`until` is what opens its window.
REQ-0110 observes `[sta_condition, sto_condition]`; REQ-0067 observes
`[sto_condition]` and triggers on `ssda`/`sscl`. The next variant shifts the
asserted probes TOGETHER, and separately the trigger probes together, and
exonerates only on a pass.
