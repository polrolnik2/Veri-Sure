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
