# A gate measured alone and a gate measured last are different measurements

`well_formed` refuses an invariant asserted over a window opened `until=TO_END`.
It ships, it blocks, and the objection is argued from the source: "everything
after the first activation is inside it ... and the first such gap convicts,
whatever the design did." `full2` was frozen before it landed, so its set still
carries three such bodies -- `REQ-0034`, `REQ-0046`, `REQ-0128` -- and two of the
three convict the known-good design.

So applying it to `full2` looks like it should remove two convictions. Measured
last, after today's three library fixes, it removes **none**:

    configuration                            span     blindness   audit
    baseline (as frozen)                     0.9737   0.1457       9/42 = 0.2143
    phase + licence                          0.9737   0.1416       1/40 = 0.0250
    phase + licence + unbounded refusal      0.9649   0.1416       1/39 = 0.0256

    check set 122 -> 121
      REQ-0034   re-served from its corpus (3 of its 4 bodies are bounded)
      REQ-0128   re-served from its corpus (2 of its 3 are bounded)
      REQ-0046   NO usable alternative -- every body is unbounded -- loses its check

**0.88 points of span, and the audit RATE goes slightly up** because the
denominator loses a check while the numerator stays at one. Blindness does not
move at all.

## Why, and it is not that the gate is wrong

Its two convictions were already gone by the time it ran:

    REQ-0128   reads `idle`, an 18-bit register declared 1 bit -- refused by the
               declaration half of the width guard, which landed hours earlier
    REQ-0034   removed by the phase rule

Each gate was measured against the frozen set in isolation, and each was credited
with the convictions it removed from THAT baseline. Two of them removed the same
two. **Summing per-gate wins double-counts**, and the only way to see it is to
apply them in a stated order and report the marginal effect of each -- which is
what the three rows above are.

## What that means for the gate

Nothing about whether it should ship; it already does, and a check claiming an
invariant for the rest of a recording is refusable on its own terms whether or
not it happens to convict anything. What it means is that **its value cannot be
quoted from the frozen set any more.** On a run authored under today's
`well_formed` those three bodies are never written, so the span cost does not
arise either: `REQ-0046` would get repair rounds against a stated objection
instead of losing its check to a driver with no way to ask for another.

That is the honest form of this result, and it is a reason to re-run rather than a
number to report: the regeneration measures what happens when a gate arrives after
the fact, which is not what happens when it arrives on time.

## And the corpus said where the shape came from

    REQ-0034   round 0 generate  bounded      round 2 repair  UNBOUNDED  -> accepted UNBOUNDED
               round 0 resample  bounded
               round 1 repair    bounded
    REQ-0128   round 0 generate  bounded      round 0 resample UNBOUNDED -> accepted UNBOUNDED
               round 1 repair    bounded
    REQ-0046   every body UNBOUNDED

REQ-0034's round-1 repair is bounded and its round-2 repair is not, and the
liveness note driving that round reads: "the state this check waits for WAS
REACHED on its own stimulus and the check did not decide ... make the window open
on `sta_condition`." **Pressure to make a check DECIDE produced a window that can
only convict** -- vacuity traded for over-strictness one repair round at a time,
where no gate downstream of the loop can see which round did it.

Reproduce with `docs/evidence/e6_unbounded_rule.py <corpus-dir> <golden-suite-dir>`.
No model calls.
