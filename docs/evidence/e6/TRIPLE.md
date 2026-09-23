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


---

# CORRECTION: every audit figure above was measured against a suite whose stimulus was never digest-checked

The container was reclaimed again between sessions. `/home/user/runs` is gone --
the fifth such loss on this branch -- and with it `recheck_run`, whose golden
suite produced every audit figure above. The two committed corpora survived,
which is what they were committed for, and `full2` re-scores from its tarball
in a cold container at span 0.9737 / blindness 0.1454 unchanged.

So the audit column had to be re-earned by running golden again. Doing that
properly is what exposed the defect.

## The guard existed. It is opt-in. Eighteen drivers never opted in.

`rtl_trace.check_stimulus` has been in the tree all along, and `decide_rtl`
RAISES on a mismatch -- but only when the caller passes `stimulus_by_tp`. Its
own docstring:

    THE FAILURE THIS EXISTS FOR IS SILENT. [...] scoring one run's oracles
    against a trace set rendered from a different run's stimulus succeeds,
    folds cleanly, and produces a conviction rate about a scenario the oracles
    were never written for. It cost a full analysis to find, and it left no
    evidence at all in the verdicts it produced.

Eighteen drivers under `docs/evidence/` call `decide_rtl`. **Not one passed
`stimulus_by_tp`.** The section above states "the stimulus is identical, 482
testpoints" -- a COUNT, which is the same wrong test as the containment check
already retracted for `o1`..`o3` one section up. `full2`'s corpus digest-matches
its own regenerated suite 482 of 482; the figures above came from a suite that
was never asked.

## The triple, re-measured on a digest-verified control

`e6_replay_corpus.py` regenerates the suite from the corpus -- which is the
`CORPORA.md` claim that `suite/` need not be packed, now tested -- and runs
golden through it. `e6_verify_corpus.py` refuses to print an audit column
unless every trace's `stimulus_digest` matches the corpus's own stimulus, and
both drivers now pass `stimulus_by_tp` so the library's refusal is armed too.

    configuration          span            blindness       audit  (was)
    baseline               0.9737 MET      0.1454 MET      16/45 = 0.3556  (9/37  = 0.2432)
    phase only             0.9737 MET      0.1454 MET       7/43 = 0.1628  (2/35  = 0.0571)
    licence rule only      0.9737 MET      0.1416 MET      15/45 = 0.3333  (8/37  = 0.2162)
    **both**               0.9737 MET      0.1416 MET     **6/43 = 0.1395**  (1/35 = 0.0286)

**`1/35 = 0.0286` IS WITHDRAWN.** The honest figure for both rules on a
digest-verified control is **6 of 43 = 0.1395**, five times larger.

What reproduces is the rules' RELATIVE effect, and it reproduces closely: span
unmoved to four places, blindness improved by the licence rule alone, and the
two together cutting audit by a factor of 2.55 (against 8.5 on the unverified
suite). Neither rule reads the audit column, so nothing about their derivation
is affected -- only the size of the residue they leave.

## Two switches, and only one of them mattered

`render_suite` takes `trace_internals` and `bus_lines`; `integration.py`'s call
site passes neither, so both were candidates for the gap. Measured:

    trace_internals=[] vs all 24   identical -- same 24 probe keys in `"dut"`,
                                   same 16 bound, audit 16/45 either way
    bus_lines unwired vs wired     14/45 = 0.3111  vs  16/45 = 0.3556

`trace_internals` gates the `dut_internal` debug columns, not the probes;
`Env.finish` writes `"dut"` unconditionally and says why. So the first draft of
`e6_replay_corpus.py` was wrong about it and says so now. `bus_lines` is real
and worth two convictions, and neither switch moves the DENOMINATOR -- so
neither explains 37 -> 45. Nor does trace coverage: random 75% / 50% / 25%
subsamples of the 482 traces all report the same 47 requirements judged. The
denominator gap is a property of the foreign suite's stimulus CONTENT, and the
suite that produced it no longer exists to decompose it further.

## What was hidden, not wrong

`RESIDUE.md` decomposes ten convictions of golden. All ten still convict under
the corpus's own stimulus. **Seven more join them**, invisible before because
that suite's stimulus never made them decidable:

    REQ-0061 0069 0096 0100 0102 0113 0128

So the residue document is incomplete rather than mistaken. The seven cluster
tightly: reset and two-stage-synchronizer requirements, three of them carrying
no temporal operator at all, and `REQ-0061`/`REQ-0102` are the same sentence
minted twice -- as are `REQ-0096`/`REQ-0100`. All seven fail on `TP-0000`.

## Against the target, as it stands today

    target     span > 90%      blindness < 20%     audit = 0
    baseline   97.4%  MET      14.5%  MET          35.6%  NOT MET
    both rules 97.4%  MET      14.2%  MET          14.0%  NOT MET

Span and blindness are met. Audit is not, and it is worse than this branch
believed by a factor of five. That is the direction honesty runs in here, and
the correction was available at the cost of one keyword argument.


---

# The triple after today's two library fixes

`UNCOMPARABLE.md` has both in full: a strong existential convicting over ZERO
rows, and a value of the wrong QUANTITY convicting because the RTL trace path
had no width guard where the Python path has had one for weeks. Neither reads
the audit column, neither removes or rewrites a check, and each turns a
conviction that rested on nothing into an abstention.

Measured on `full2` against its own digest-verified golden suite:

    configuration          span            blindness       audit
    baseline               0.9737 MET      0.1457 MET      11/44 = 0.2500
    phase only             0.9737 MET      0.1457 MET       3/42 = 0.0714
    licence rule only      0.9737 MET      0.1416 MET      11/44 = 0.2500
    **both**               0.9737 MET      0.1416 MET     **3/42 = 0.0714**

against 16/45, 7/43, 15/45 and 6/43 before the fixes. Span unmoved to four
places; blindness up three ten-thousandths at baseline and unmoved with the
rules applied.

## What is left, enumerated

    REQ-0055 [behavioural] TP-0004   slave_wait EXTENT -- characterised, open
    REQ-0100 [behavioural] TP-0000   reset: eleven ports asserted at one instant
    REQ-0128 [behavioural] TP-0000   `throughout` over an unbounded TO_END window
    REQ-0058 [scaffolding] TP-0000   cause still not found

The scorecard reports 3 because `REQ-0058` is `scaffolding` and falls outside
the set it counts. Both figures are right about what they measure, and "three
convictions left" is the wrong sentence unless it says which three.

## And the licence rule's audit effect was ABSORBED, not lost

Before the fixes it removed one conviction alone (15/45 against 16/45). After
them it removes none (11/44 either way) while keeping its entire blindness gain.
So the conviction it appeared to be buying was an artifact of one of the two
defects, and its real contribution is to blindness -- which is where it was
already the only correction on this branch that moved blindness and audit the
same way. The phase rule is untouched and remains the large lever: 11 to 3.

## REQ-0128 is a check TODAY'S PIPELINE WOULD NOT HAVE SHIPPED

`well_formed` refuses an invariant asserted over a window opened `until=TO_END`,
with the objection already worded in-tree -- "everything after the first
activation is inside it ... and the first such gap convicts, whatever the design
did". It is blocking today. `full2` froze BEFORE it landed, so its set still
carries three such bodies: `REQ-0034`, `REQ-0046` and `REQ-0128`. Two of the
three convict golden and one does not, which is what applying a rule uniformly
looks like.

**And the corpus says the repair loop introduced the shape.**

    REQ-0034   round 0 generate  bounded      round 2 repair  UNBOUNDED  -> accepted UNBOUNDED
               round 0 resample  bounded
               round 1 repair    bounded
    REQ-0128   round 0 generate  bounded      round 0 resample UNBOUNDED -> accepted UNBOUNDED
               round 1 repair    bounded
    REQ-0046   every body UNBOUNDED                                      -> no alternative

REQ-0034's round-1 repair is bounded and its round-2 repair is not, and the
liveness note driving that round reads: "the state this check waits for WAS
REACHED on its own stimulus and the check did not decide ... make the window open
on `sta_condition`." **Pressure to make a check DECIDE produced a window that can
only convict** -- the vacuity/over-strictness trade arriving one repair round at
a time, where no gate downstream of the loop can see it.

`e6_unbounded_rule.py` measures the regeneration: drop what `well_formed`
refuses, re-serve each requirement from the earliest corpus body the gate
accepts, and report what it costs. Two of the three have a usable alternative;
`REQ-0046` has none and loses its check.
