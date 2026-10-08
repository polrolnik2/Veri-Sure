# The first run to meet all three, scored by the run itself

`specflow/scorecard.py`, written by `run_oracle_stage` from this run's own
artifacts and its own six spec-derived designs. The control is read for the
audit column and reaches nothing else.

    SPAN       117/120 behavioural = 97.5%
    BLINDNESS  915/26378 cells = 3.5%      (population 6, effective_size 110)
    AUDIT      0/15 judgeable = 0.0%
    ACCEPTS    0 of 6 design(s)

    dispositions: ABANDONED 18, TRUSTED 125, VACUOUS 5
    corpus 602 bodies / 148 requirements {generate 148, resample 148,
                                          repair 266, cell 40}
    62 requirements freeze a different body of their own corpus

## What is NOT demonstrated here

**This is `run_oracle_stage` re-entered on a frozen upstream** --
`docs/evidence/e5u`, via `e5_oracle_stage.py` -- and not `build_artifacts`
end to end. The upstream is one a previous run produced, so S1, `[P]`, S2, S3,
the stimulus and normalize are held fixed and only the oracle stage is under
test. That is what makes two of these comparable to each other; it is not what
makes one comparable to a pipeline run.

**The audit denominator is 15 of 117.** The i2c control declares no
`PROBE_PORTS` -- it predates probes, as do the nine standing yardstick designs
and every benchmark RTL -- so it can only judge the checks that read none. That
is a property of the benchmark's control and not of the suite, and
`base.probe_values` makes the rest abstain rather than be convicted against
sixteen permanently-false state terms, which is how the same column read 57.6%
before.

**`ACCEPTS 0 of 6`** says the set rejects every spec-derived design. That is the
plan's over-constricted end, measured, and it is not what the plan asks for --
"one class, containing the correct design". The audit column says the correct
design is not among the rejected, on the 15 checks that can say so.

## The three rules that produced it, all golden-free

  refutation is ADVISORY   no spec-derived design is guaranteed correct, so
                           none of them discards a check. It earns a repair
                           round. This removed the whole `ORACLE_INVALID`
                           bucket: 11-18 requirements per run.
  a BODY is chosen, not    `_choose_bodies` picks each requirement's body by
  a CHECK dropped          marginal cells closed under a `dissent_weighted`
                           guard. Choosing costs nothing; dropping costs a
                           requirement. 21.4% -> 3.5% blind at no span cost.
  probes carry the SPEC'S  a requirement about `cSCL` has a probe called
  NAME                     `cscl` to name, instead of being routed to a
                           declared output it never mentions.
