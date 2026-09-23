# The audit residue against golden, accounted for

Ten checks convict the known-good i2c design after the width guard. This is
what each is, measured. Golden is RUN and never read.

    cause                                        checks                       status
    ------------------------------------------  ---------------------------  ---------------
    `throughout` over a TO_END window            REQ-0034                     GATED
    probe PHASE (registered vs combinational)    REQ-0066 0067 0110 0111 0112 INSTRUMENT
    downstream of the same phase question        REQ-0035                     INSTRUMENT
    `slave_wait` EXTENT under-determination      REQ-0053 REQ-0055            CHARACTERISED
    cause not found                              REQ-0058                     OPEN

Seven of ten are caught by a rule that never reads golden. Two are a
specification ambiguity named but not resolved. One is unexplained.

## `slave_wait`: the sentence admits a level and an event

    "The controller shall assert slave_wait when it has released SCL high
     through scl_oen while the filtered SCL input derived from scl_i remains
     low."

Counting rows where that literal condition holds:

                 rows   slave_wait asserted   never asserted
      GOLDEN     1950                   254             1514
      CANDIDATE  1098                  1098                0

The population reads the sentence as a LEVEL -- whenever the lines are in this
state, the signal is high, and the candidate asserts it in every such row.
Golden reads it as an EVENT with hysteresis: it asserts in 254 of 1950, and
where it is asserted it was already asserted 45% of the time against 0% where
it is not. Once set, it holds; the SET condition is narrower than the literal
formula.

No probe that binds on golden separates the two cases (the closest, `sda_oen`,
gives a 0.48 gap and does not partition). Several probes that might have --
`idle`, `cnt_zero`, `filter_cnt` -- are width-refused or unbound on golden, so
the exact gate cannot be named from the trace. **That limit is itself the
finding: the probes that would explain golden's reading are the ones golden
does not carry.**

This is under-determination of EXTENT, where phase is under-determination of
TIMING. The same class of defect -- a sentence the population reads one way and
a correct design reads another -- and neither is a mechanical error in a check.

## REQ-0058: two hypotheses, both refuted

    "A falling edge on the filtered SCL input while this controller has
     released SCL high indicates that another master has forced SCL low."

    check says: "scl_oen changed from released before synchronization
                 postponement was observed"

Hypothesis 1, the condition never fires on golden: **refuted.** It fires 336
times, and `scl_sync` is set at or just after every one of them, 336 of 336.

Hypothesis 2, a phase displacement like the START/STOP conditions: **refuted.**
`scl_sync` is set at the SAME edge on both designs -- 336 of 336 on golden,
79 of 79 on the candidate -- and in none of them had `scl_oen` already left
released.

So the conviction has a cause neither measurement reached. Recorded as open
rather than filed under the nearest neighbouring mechanism, which is what
both refuted hypotheses were.

## What this does and does not do for the audit column

It does not lower it. Naming a cause is not removing a conviction: only the
`TO_END` gate actually refuses a check, and that one takes audit from 10 of 39
to 9 of 38. The phase instrument flags six more but the disposition is
deliberately left open -- there is no design-free argument that a check
asserting an unstated timing is WRONG, only that it asserts more than the
specification said.

What it does is convert an undifferentiated residue into five accounted
categories, of which three are specification under-determination rather than
defects. **That distinction is the one the audit column exists to surface**,
and it is invisible from inside the population: every member reads the sentence
the same way, so the disagreement is never a cell, and blindness and span both
report success on exactly the requirements where a correct design would be
convicted.
