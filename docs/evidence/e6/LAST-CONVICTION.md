# The last conviction, and why closing it from here would be cheating

After three library fixes and two grade-blind rules, `full2` scores
**span 0.9737 / blindness 0.1416 / audit 1 of 40 = 0.0250** against a
digest-verified golden control. The target is `audit = 0`. This is about the one.

    REQ-0055 [behavioural]  TP-0004
    REQ-0058 [scaffolding]  TP-0000   -- not counted by the audit column

## Two defects are stacked on REQ-0055, and they are independent

    requirement   "While the slave-wait condition remains active because a bus
                   participant holds SCL low, the bit-level controller shall
                   PAUSE ITS TIMING COUNTER until SCL is released."
    normalize     observable: ['cmd_ack']      effect_follows: True
    verdict       "the invariant broke at edge 7, in the window opening at edge 7"

**One: the observable is wrong.** `cmd_ack` is not a timing counter -- the
contract declares `clk_en`, `cnt_zero` and `filter_cnt`. `OBSERVABLE-LICENCE.md`
measures the field at 34% of forms unlicensed by the requirement's own words, and
this is one of them. No selection can reach it: all four of REQ-0055's corpus
bodies read `cmd_ack`, and so do all 24 bodies across the seven
unlicensed-observable requirements that convict -- zero deviations.

**Two: the check asserts the property under BOTH temporal readings and keeps
whichever fails.** Its own source:

    full_window = throughout(window, low, after_activation=False)
    if full_window[0] is False:
        results.append(full_window)      # keeps the |-> failure
        continue
    # The normalized activation says the effect follows the trigger; check
    # the post-trigger states using the corresponding temporal semantics.
    after_trigger = throughout(window, low, after_activation=True)
    results.append(after_trigger)

It computes `|->`, and when that fails it reports that failure and never reaches
the `|=>` reading its own comment says normalize asked for. So it is strictly
stronger than either reading alone, and **no requirement licenses "both readings
must hold"** -- `effect_follows` is one decision, which is the whole premise of
the field.

That shape is statically detectable: the same operator, on the same window, with
both values of `after_activation`.

## And it matches EXACTLY ONE body of 122 -- which is why it is not being used

    bodies asserting the same property under both |-> and |=>   1 of 122
      of the 17 that convict golden                             1
      convicting nothing                                        0

**A rule whose entire population is the one check that convicts cannot be
distinguished from gating on the grade**, however its statement is worded. I found
this shape by inspecting the conviction, and on this corpus its coverage is
precisely the conviction. The standing rule on this branch is that choosing a
ruleset by its audit column is barred, and the bar is about what the choice is
*determined by*, not about what the sentence mentions.

So: **the shape is reported, and the triple is NOT recomputed with it.**

Compare the two rules that ARE used. The licence rule matches **28 of 122** and its
matches are decided by the requirement's words alone. The phase rule advances
exactly the two probes the specification writes an equation for
(`sta_condition`, `sto_condition`) -- a criterion stated from the specification and
applied to every check reading them, including the ones that convict nothing;
`PHASE.md` has that derivation. Both have a population fixed by something other
than the grade. A population of one, found by reading the conviction, does not.

**One thing here is not measured and is not being claimed:** how many
NON-convicting checks are phase-sensitive on the guarded path. `e6_phase_abstain.py`
asks the question only where a check convicts -- deliberately, since it computes
the audit column -- so "8 of the 10 convicting requirements are phase-sensitive" is
what was measured and the denominator over the whole set is not. An earlier draft of
this paragraph quoted 13 from a run of that driver that bypassed `decide_rtl`
entirely; that run is void.

If the shape is worth refusing -- and a check asserting a property under both
readings is refusable on its own terms -- it belongs in `well_formed` on a run
where it is applied BEFORE the bodies are frozen, and its value measured on a set
it did not have a hand in selecting. `LAYERED-GATES.md` is the worked example of
why a gate arriving after the fact measures something else.

## So audit = 0 is not honestly reachable from stored artifacts

Three routes, all closed from here:

    fix normalize's observable        needs a model call -- 429 BUDGET_EXCEEDED
    re-author REQ-0055               needs a model call
    refuse the both-readings shape    population of one; indistinguishable from
                                     grade-gating on this corpus

The gateway was re-probed at the end of this session with the `/v1` suffix and the
un-prefixed model name: `429 BUDGET_EXCEEDED`. No other credential exists in the
environment.

**The honest statement of the result is therefore: span and blindness are met,
audit is 1 conviction of 40 checks, the conviction has two named mechanical causes,
and both repairs are upstream of anything a stored artifact can express.** Not
"audit = 0 with one more rule applied".

## REQ-0058, separately

Not counted by the audit column because it is `unit_kind: scaffolding`, and listed
here so that "one conviction" is not read as "one check convicting".

`RESIDUE.md` recorded it as the one conviction with no surviving mechanism, after
two hypotheses were measured and refuted. **A third now survives**, and it does not
contradict either refutation. `phase_sensitive` flags its conviction on
`scl_sync`. The refuted hypothesis asked whether golden and the population
DISAGREE about when `scl_sync` rises -- they do not, 336 of 336 and 79 of 79 at the
same edge. This asks whether the CHECK'S VERDICT depends on that timing, and it
does: the check relates `scl_sync` to `scl_oen`, and moving one of them alone
breaks the relation. `phase_sensitive`'s own docstring is explicit that these are
different questions -- "shifting trigger and condition by the same amount preserves
their relative timing and no verdict moves" -- which is exactly why it moves one
probe at a time.

---

# The symmetric phase rule, measured — and it is WORSE

`e6_phase_abstain.py` implements the rule that asserts neither reading: a check
whose conviction flips when a probe it reads is taken at a different phase
abstains, rather than being re-decided against an advanced control.

    rule                                  span     blindness   audit
    advance sta/sto + licence rule        0.9737   0.1416      1/40 = 0.0250
    phase-sensitive convictions ABSTAIN   0.9737   0.1457      2/35 = 0.0571

    remaining, advancing   REQ-0055 [behavioural], REQ-0058 [scaffolding]
    remaining, abstaining  REQ-0055 [behavioural], REQ-0110 [behavioural]

The blindness difference is not a fair comparison -- the abstaining run does not
apply the licence rule, which is where that 0.0041 comes from. The audit columns
are comparable and abstention loses on both parts of the fraction: **8 of the 10
convicting requirements are spared, and the denominator falls 40 -> 35**, because a
requirement that abstains everywhere stops being judgeable at all. Abstention buys
its soundness with reach, exactly as the tri-state is supposed to.

## And it MISSES one the advancing rule catches, for two separate reasons

REQ-0110 -- "The I2C controller detects bus events by comparing the current
filtered SCL and SDA values with their delayed filtered values" -- convicts on 446
testpoints. Measured:

    spared by advancing sta_condition alone       4 of 446
    spared by advancing sto_condition alone     201 of 446
    spared by advancing BOTH together          441 of 446

**Its dependence is JOINT.** `phase_sensitive` moves one probe at a time, and that
is deliberate and right for what it was built for: "shifting trigger and condition
by the same amount preserves their relative timing and no verdict moves -- 20
checks flagged that way and NONE of the five." One-at-a-time catches RELATIONAL
dependence between a trigger and a condition. It cannot catch a check that depends
on two probes moving together, and this is one.

**And it perturbs in the other direction.** `phase_sensitive` calls
`delay_probes`; golden asserts these conditions one edge LATER than the population
already (`PHASE.md`: 499 of 499), so the perturbation that exposes the
disagreement is an advance, not a further delay. A check written against the
population's reading need not flip when golden's already-late probe is made later
still.

Both are limitations of the instrument as applied to a control, not defects in
what it was written for. **Neither is fixed here.** Making `phase_sensitive` test
both directions is a one-line change and strictly widens what it catches, but it
would move `PHASE.md`'s recorded "20 flagged, none of the five" and every figure
derived from it, and it deserves its own measurement rather than a footnote in
someone else's. The instrument is reporting-only, so a miss costs a report and not
a verdict.

## What the comparison settles

The advancing rule is better on this corpus and still picks a reading the
specification does not state. The abstaining rule states nothing and pays for it in
reach. **Neither reaches audit = 0**, both leave REQ-0055, and the difference
between them is a real trade rather than one being the correct implementation of
the other.
