# The triple with an audit denominator that means something

`full2`'s stored artifacts, re-scored by the current code with **golden RTL as
the audit control** instead of the Python transliteration. No model calls: span
and blindness come from `score` replaying the stored 7-member population in
Python, audit from `decide_rtl` over traces a real simulation wrote. Both are
stages this branch changed, which is what "run only from the stage you changed"
buys when the gateway is down.

Golden is RUN and never read.

    column      as the run recorded it        re-scored with an RTL control
    ---------   ---------------------------   -----------------------------
    SPAN        0.9737  (111 of 114)          0.9737  (111 of 114)
    BLINDNESS   0.1464  (3887 of 26549)       0.1454  (3860 of 26549)
    AUDIT       0.0000  -- 0 of 14            **0.2432 -- 9 of 37**

Span and blindness reproduce. **The audit column does not, and that is the
entire point.**

## What changed, and what did not

The check set is IDENTICAL -- same 122 bodies, verified by digest against the
run's own `oracles.json`. The population is identical, 7 distinct sources. The
stimulus is identical, 482 testpoints. Nothing was selected, dropped or
re-authored.

Only the CONTROL changed, from a Python transliteration to the known-good RTL:

    control                    declared probes exposed   checks it can judge
    Python transliteration     0 of 24                   14 of 111
    GOLDEN RTL                 10 of 24                  37 of 111

`audit = 0.0` was a rate over the eighth of the set that could see the control
at all. `audit = 0.2432` is a rate over a quarter of it. **The second number is
worse and more honest, and the first was never evidence that the set spares a
correct design.**

## The denominator is still not the whole set

Golden exposes 10 of the 24 declared probes. Fourteen it does not carry at all:

    idle  cnt_zero  cscl  csda  filter_cnt  filter_cnt_expired  fscl  fsda
    active_command  filtered_scl_rise  start_sequence  stop_sequence
    read_sequence  write_sequence

so 74 checks still say nothing about it. Six of those fourteen are the
width-refused ones -- the design HAS a signal of that name and the width guard
declines to sample it as a different quantity. The other eight are genuinely
absent: spec-named abstractions golden computes inline.

`audit = 9 of 37` is therefore a floor, not a final figure. It is the honest
reading available today, and it is 2.6x the denominator the recorded run had.

## Against the target

    target     span > 90%      blindness < 10%     audit = 0
    measured   97.4%  MET      14.5%  NOT MET      24.3%  NOT MET

`o3`, a different corpus of the same module, records 97.5% / 3.5% / 0.0% and
meets all three ON ITS OWN INSTRUMENT. Its audit column is 0 of 15 against the
same probe-less Python control, so the same substitution would move it the same
way. It has not been re-scored here because `o3`'s artifact set is missing the
contract, stimulus, normalized and requirements files its run wrote elsewhere;
only `full2` and `full7` carry a complete set.

**What the substitution shows is that the audit column, as the pipeline reports
it today, is not measuring what the target means by it.** Fixing that makes the
number worse. That is the direction honesty runs in here, and it is why the
remaining work is to lower a real 24.3% rather than to preserve a nominal 0.
