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


---

# CORRECTION: o1..o3 are a DIFFERENT instrument and cannot be re-scored

The section above says `o3` "would move the same way under the same
substitution". That was a guess presented as a prediction, and it is wrong in a
way that matters more than the guess.

I ran the substitution on `o3` and `o2` using `full2`'s contract, on the
strength of every req_uid and tp_uid being contained in full2's. The numbers
that came back -- o3 span 0.842, blindness **0.9972**, audit 4/13 -- are
INVALID and are retracted. The cause:

    run        population declares
    full2      24 probes
    full7      24 probes
    e6/myrun   24 probes
    o1         17 probes
    o2         17 probes
    o3         17 probes

`o1`..`o3` ran against a contract declaring **17** probes. Replaying one of
their population members under full2's 24-probe contract reports all 24
`unavailable`, so every probe-reading check abstains and blindness goes to
99.7% by construction. Shared requirement and testpoint uids do not make two
runs the same instrument, and containment was the wrong test.

Their own contract is not on disk -- `o1`..`o3` kept only `scorecard.json`,
`oracles.json`, `witness.py`, `population/` and `agent_io/` -- so the
substitution cannot be done for them at all.

## What this says about o3's recorded triple

`o3`'s 97.5% / 3.5% / 0.0% stands as what ITS run measured, and it is not
comparable to `full2`'s. It is a different probe contract, hence a different
population, a different corpus and a different control relationship. Its
`audit = 0 of 15` is over a control that exposes none of ITS 17 probes, so the
same criticism applies -- but the correction it would need is not the one
computed here, and I have no way to compute it.

## What is re-scorable, and what is not

    run       own contract   stimulus matches a suite with golden traces   re-scorable
    full2     (shared)       yes                                           YES  -- done
    full7     yes            no (its own stimulus, digest differs)         needs a suite run
    o1..o3    NO             n/a                                           NO

So `full2` is the only run re-scored here, and **97.4% / 14.5% / 24.3% is the
only honest triple on the board.** It misses two of the three targets.


---

# full7, re-scored on its OWN instrument

`full7` carries a complete instrument of its own -- contract, stimulus,
testplan, `ref_model.py`, a 443-test suite and a 7-member distinct population.
An earlier note here said it "needs a suite run"; it does not, it needed
looking in `full7/specflow/suite` rather than `full7/suite`. Golden was run
through that suite (442 traces) and the run re-scored against it.

    column      as the run recorded it      re-scored with an RTL control
    ---------   -------------------------   -----------------------------
    SPAN        0.9820  (109 of 111)        0.9820  (109 of 111)
    BLINDNESS   0.2450                      0.2896
    AUDIT       0.0667  -- 1 of 15          **0.3600 -- 18 of 50**

Span reproduces to four places. The audit denominator goes **15 -> 50**,
because golden exposes 16 of full7's 24 declared probes against 0 for the
Python control. Eight remain unexposed and are the familiar list -- `cnt_zero`,
`active_command`, the four `*_sequence` probes, plus full7's own
`write_stable_high_phase` and `read_sample_window`.

**BLINDNESS DOES NOT REPRODUCE AND I CANNOT ACCOUNT FOR IT.** 0.2450 recorded
against 0.2896 here, on a cell count that matches exactly (29392). The
population is replayed in Python by `score`, which the width guard does not
touch -- it lives in the cocotb runtime -- so the obvious explanation is wrong.
The testpoint count also differs by one (442 traces against 443 rendered
tests). Recorded as unexplained rather than attributed.

## The two honest triples

    run     span     blindness   audit            audit denominator
    full2   97.4%    14.5%       24.3%            37 of 111
    full7   98.2%    29.0%       36.0%            50 of 109

    target  > 90%    < 10%       = 0

Span is met on both. **Blindness and audit are met on neither**, and the
audit column is worse on the instrument whose control can see more of the set
-- full7's golden exposes 16 of 24 probes where full2's exposes 10, and full7's
audit is correspondingly higher at 36.0%. That direction is consistent: the
more of a check set a real design can be judged on, the more of it convicts
that design.
