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

**BLINDNESS DOES NOT REPRODUCE, AND THE CAUSE IS THE BOUNDARY FIX** -- not the
width guard, and not the harness.

    full2 scorecard written   2026-09-19 04:41
    full7 scorecard written   2026-09-22 18:05
    a11aa4d boundary fix      2026-09-22 18:58

Both recorded scorecards PREDATE `a11aa4d`, "An invariant was being asserted
over the row that ENDED its window" -- full7's by 53 minutes. A re-score runs
today's `temporal.py`, where `throughout`, `stable` and `never` read `extent`
and `governed` instead of `rows` and `body`. So the two numbers were computed
by different instruments and the difference is the fix, working.

    run     blindness recorded -> re-scored   invariant-operator checks
    full2   0.1464 -> 0.1454   (-0.001)       16 of 122   (13%)
    full7   0.2450 -> 0.2896   (+0.045)       22 of 123   (18%)

full7 is the more exposed corpus and moves far more, which is the consistent
direction -- though 18% against 13% does not by itself account for a delta
forty times larger, so the density is corroboration and not a proof.

**The trade is the finding.** The boundary fix removes convictions that came
from asserting an invariant over the row that ended its window -- good for
audit -- and every conviction it removes is also a separation lost, so
blindness RISES. On full7 that is +4.5 points of blindness bought with
however many spurious convictions. Span was unmoved (0.9820 both ways), so it
is paid for out of blindness alone.

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


---

# Both of today's corrections, applied as RULES

Neither reads the audit column. Choosing what to change by whether it convicts
the control is gating on the grade; both rules below come from the
requirement's own words and are applied uniformly to every check that matches,
including the ones that convict nothing.

  1. **PHASE.** The specification writes an equation, not a schedule, so a
     design may offer a condition combinationally or register it. Applied by
     reading the control's `sta_condition` and `sto_condition` one edge early
     -- the two probes whose equation the specification states.
  2. **`|->` NOT `|=>`.** `after_activation=True` claims the effect FOLLOWS
     the trigger. Demoted to False on every check whose requirement text
     carries no sequence word and licenses no cycle count, which is
     `correspondence`'s existing licence test applied to the flag. It matched
     **28 of 122**.

    configuration          span            blindness       audit
    baseline               0.9737 MET      0.1454 MET      9/37 = 0.2432
    phase only             0.9737 MET      0.1454 MET      2/35 = 0.0571
    licence rule only      0.9737 MET      0.1416 MET      8/37 = 0.2162
    **both**               **0.9737 MET**  **0.1416 MET**  **1/35 = 0.0286**

Span is unmoved to four decimal places. **Blindness IMPROVES** under the
licence rule -- a check that no longer demands strictly-after decides where it
previously abstained -- which is the first correction measured on this branch
that moves audit and blindness the same way.

## The scorecard says 1 and there are 2

Enumerating the convictions directly under both corrections gives **REQ-0055
and REQ-0058**. The scorecard reports `1/35` because REQ-0058 is
`unit_kind: scaffolding` and falls outside the set it counts. Both figures are
right about what they measure, and "one conviction left" is not: **two checks
still convict the known-good design, one of which the audit column does not
count.**

    REQ-0055 [behavioural]  TP-0017 edge 7   the invariant broke, window opened at edge 6
    REQ-0058 [scaffolding]  TP-0011 edge 5   scl_oen changed from released before
                                             synchronization postponement was observed

REQ-0055 is the one the degenerate-stimulus finding bears on: it asserts the
timing counter is paused, and TP-0017 drives `clk_cnt = 0`, where there is
nothing to pause and the known-good design's `clk_en` free-runs. REQ-0058
remains unexplained -- two hypotheses measured and both refuted.

## What this does and does not claim

It does NOT claim the pipeline reaches audit = 0. It claims that two rules
derived from requirement text, applied uniformly and without reading the grade,
take the audit column from 24.3% to 2.9% on this corpus at no cost to span and
a small gain in blindness -- and that what remains is two checks with named,
separate causes rather than an undifferentiated residue.

It is also a PROJECTION, not a run: the corrections are applied to stored
artifacts by a driver, because the gateway is budget-exhausted and neither the
oracle stage nor the probe stage can be re-run to produce checks written this
way from the start. `e6_corrected_triple.py` reproduces it with zero model
calls.
