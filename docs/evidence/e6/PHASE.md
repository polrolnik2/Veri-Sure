# A probe entry obliges a name and a width. It does not oblige a PHASE.

Ten checks convict the known-good i2c design after the width guard. One,
REQ-0034, has a known shape and is now refused at authoring. **Five of the
remaining nine are one mechanism**, and it is not a wrongness in golden or in
the checks. It is a question the specification leaves open and the contract has
no field for.

## The measurement

The specification states the formula itself: *"sto_condition = sSDA & ~dSDA &
sSCL"*. So compute that formula from the SAME recorded trace the check reads,
and ask where the probe of that name actually sits.

    where the spec's own formula holds, the probe is asserted:

                 probe            same   ONE EDGE LATER   earlier   never
      GOLDEN     sta_condition       0               70         0       0
      GOLDEN     sto_condition       0              429         0       0
      CANDIDATE  sta_condition      13                0         0       0
      CANDIDATE  sto_condition       9                0         0       0

**499 of 499 on golden, one edge late. 22 of 22 on the candidate, same edge.**
Not a tendency -- unanimous, in both directions.

Golden REGISTERS the condition. The spec-derived population computes it
COMBINATIONALLY. The specification writes an equation and never says which, and
both are faithful readings of it.

## What it costs

    REQ-0066   "filtered SDA fell ... but sta_condition was not asserted"
    REQ-0067   "sto_condition did not assert when filtered SDA rose ..."
    REQ-0110   "filtered SDA rose ... but sto_condition was not detected"
    REQ-0111   "filtered START transition occurred while sta_condition was not asserted"
    REQ-0112   "filtered SDA rose ... but sto_condition did not assert"

Five of the nine residual convictions, every one of them saying the same thing:
the transition happened and the probe was not yet high. All five are correct
about what they observed and wrong about what it means.

## Why this is the same defect as the other two, and the worst form of it

A `dir: "probe"` entry carries a NAME and a WIDTH. Three ways a check reading
one can be wrong about a design that did not receive the contract:

    1. NAME      `cscl` never binds to `cSCL`             -> silent abstention
    2. QUANTITY  `fscl` binds a 3-bit history as a level  -> spurious conviction
    3. PHASE     `sto_condition` binds the same 1-bit
                 quantity, one cycle displaced            -> spurious conviction

(1) was fixed by case-insensitive binding, (2) by the width guard. **(3) cannot
be fixed by either**, because nothing is mis-bound: the name matches, the width
matches, the quantity matches, and the value is right one edge later.

And the population cannot reveal it. Every member computes the condition
combinationally, because every member was handed the same contract, so the
whole population agrees and the cell is not a disagreement cell. **Blindness
cannot see this and span cannot see this. Only a design from outside the family
can, which is exactly what the audit column is for.**

## What would close it

The contract would have to state, per probe, whether the specification's
equation describes a value available in the same cycle or one registered from
it -- and a check reading a probe would have to be written against that. There
is no such field today, and inventing one is a change to what a probe MEANS,
not a guard that can be bolted on.

The cheaper and more honest alternative: a check that reads a probe to detect
an EVENT should be phase-tolerant by construction -- "within one cycle of the
transition" rather than "at the transition" -- unless the specification states
the timing, which is the rule `correspondence` already applies to cycle counts
("licensed ONLY if the text states the number"). Applying that existing rule to
probe reads would make all five of these abstain or pass instead of convict.

Neither is implementable without deciding what the specification meant, which
is an authoring question and not a mechanical one. **It is recorded here as the
largest single item in the audit residue: 5 of 9, one cause.**

## The four that remain

    REQ-0035   "busy was not cleared after the detected STOP condition"
    REQ-0053   "the expected response never occurred, and the window opening at
                edge 30 ran to the end of trace"
    REQ-0055   "the invariant broke at edge 7, in the window opening at edge 6"
    REQ-0058   "scl_oen changed from released before synchronization
                postponement was observed"

REQ-0035 is plausibly downstream of the same phase question -- `busy` is set and
cleared BY `sta_condition`/`sto_condition`, so a registered condition clears
`busy` a cycle later too. Not measured, and not claimed.

REQ-0053 and REQ-0055 are about `slave_wait`; REQ-0058 about `scl_oen` against
a synchronisation postponement. No shared mechanism established.


---

# An instrument for it, and two corrections it forced

`temporal.phase_sensitive(decide, trace, probes, requirement_text)` replays a
check against copies of the trace in which one probe holds its previous value,
and returns the probes whose schedule the verdict depends on. Licensed where
the requirement states a timing, which is `correspondence`'s existing rule for
cycle counts applied to probe reads. Design-free: any runnable trace serves,
the way `oracle_liveness` uses any runnable design.

## Correction 1: delaying every probe together finds nothing

The obvious instrument -- shift all probes, see if the verdict moves -- flags
**20 of 122 checks and NONE of the five.** A check of this shape reads its
TRIGGER from probes as well (`ssda`, `dsda`, `sscl`), so shifting trigger and
condition by the same amount preserves their relative timing and no verdict
moves. The instrument was measuring nothing and its unit tests passed, because
a hand-built two-signal trace does not have that structure.

**One probe at a time** breaks exactly the relation the check depends on:

    FLAGGED by single-probe delay: 31 of 122
      of the 9 residual convictions: REQ-0035, 0066, 0067, 0110, 0111, 0112
      of the five phase cases:       all five

        REQ-0066 flips on  ssda, sta_condition
        REQ-0067 flips on  ssda, sto_condition
        REQ-0110 flips on  dsda, ssda, sta_condition
        REQ-0111 flips on  ssda, sta_condition
        REQ-0112 flips on  ssda, sto_condition

Each flips on the probe the diagnosis named. **Six of the nine residual
convictions, caught by a rule that never reads golden.**

## Correction 2: the first run of it silently measured nothing

The first attempt reported `0 of 122` flagged. Three separate faults, each
hidden by the next:

1. The harness hand-built trace rows keyed on `index`; the real shape keys on
   `edge`. Every `decide` raised `KeyError`.
2. `phase_sensitive` swallows a raising check -- deliberately, since a check
   that cannot run is another gate's business -- so all 122 failures read as
   "not phase-sensitive". **That is the same "degrades rather than raises"
   pattern this branch spent the morning removing from `_frozen_oracles`, and
   I wrote it into a new instrument the same day.**
3. Fixing the shape gave `0` again from a different cause: the substrate was a
   live editor's results directory, holding 51 traces of a run in progress
   rather than 422.

The fix for (1) is to use `rtl_trace.rows_from`, the pipeline's own reshape,
rather than reconstructing it. For (3), a dedicated substrate directory. For
(2) the swallow stays -- it is right for the pipeline -- but a measurement
harness must assert that `decide` ran before trusting a negative.

## What it does NOT establish

25 of the 31 flagged checks do not convict golden. That is not a false positive
rate: a check may depend on a probe's schedule and still agree with golden,
because golden happens to share that probe's phase. The screen is about the
claim the check makes, not about whether the claim has been cashed.

Whether 31 of 122 should be REFUSED is not settled here. Refusing them costs
span, and unlike the `TO_END` shape there is no design-free argument that the
check is wrong -- only that it asserts a timing the specification did not
state. The honest disposition is an objection that buys a repair round, which
is what the author needs to decide between "state the timing" and "tolerate
either reading".


---

# A global probe advance removes all ten convictions, and proves nothing

Reading golden's probes one edge EARLY -- every probe taking its next row's
value, the inverse of `delay_probes` -- removes every conviction:

    req        as recorded   probes advanced one edge
    REQ-0034   CONVICTS      abstains
    REQ-0035   CONVICTS      abstains
    REQ-0053   CONVICTS      spares
    REQ-0055   CONVICTS      spares
    REQ-0058   CONVICTS      spares
    REQ-0066   CONVICTS      abstains
    REQ-0067   CONVICTS      abstains
    REQ-0110   CONVICTS      abstains
    REQ-0111   CONVICTS      abstains
    REQ-0112   CONVICTS      abstains

**SEVEN OF THE TEN ABSTAIN RATHER THAN SPARE, AND AN ABSTENTION IS NOT A
VINDICATION.** It removes the conviction from the numerator and the check from
the denominator at once. A check that stops deciding has not been shown to
agree with the design; it has been shown to have lost its activation, which is
what shifting twenty-four probes at once does.

So this does NOT validate "a phase field in the probe contract would make six
checks pass". It shows only that all ten convictions are sensitive to a uniform
probe shift -- consistent with phase being broadly implicated, and far too
blunt to attribute a cause. The intervention that would validate the fix shifts
ONE probe, the one the specification's equation defines, and leaves the rest
alone.

## The `slave_wait` extent finding survives a confound check

REQ-0053 and REQ-0055 SPARING under the global advance raised the worry that
the extent measurement in RESIDUE.md was phase-confounded: it compares
`scl_oen`, an OUTPUT that the shift does not touch, against `sscl`, a PROBE
that it does. If golden's probes sat one edge behind its outputs, that
comparison was misaligned.

They do not, and it was not:

                 advanced 0                  advanced 1
      GOLDEN     254 asserted / 1696 not     272 / 1722    (13% -> 14%)
      CANDIDATE  997 asserted /  101 not    1015 /   82    (91% -> 93%)

One edge of shift moves golden from 13% to 14% and the candidate from 91% to
93%. The gap is not phase. **Golden really does assert `slave_wait` on a
narrower condition than the sentence's literal reading**, and REQ-0053 and
REQ-0055 sparing under the global advance is a side effect of shifting the
several other probes they read, not evidence about `slave_wait`.
