# Pre-registration: how the refutation preference is decided

Written after run 3's two arms were measured and **before** runs 1 and 2
reported, so the rule cannot be fitted to the column it must not be fitted to.

## The choice

`_choose_bodies` applies refutation as a TIER -- `tier = spared or per_req[uid]`
-- so a body the whole spec-derived population convicts is beaten by ANY body
it spares, whatever either one separates. The two arms are `refute_on` (as
shipped) and `refute_off` (the tier removed).

## The rule, fixed in advance

**Decided on BLINDNESS at equal SPAN. The audit column is reported beside it
and does not enter the decision.** A control may reject an oracle; it may never
repair one, and choosing a ruleset by its audit column is gating on the grade
in slow motion -- the same objection that retired the witness gate.

Run 3, the hardest corpus, at identical span (98.2%):

    refute_on    blindness 24.4%    audit 0/13
    refute_off   blindness  9.2%    audit 0/14

Fifteen points of blindness at no cost in span. **`refute_off` is taken.** It
is taken whatever runs 1 and 2 say about audit; if either shows a conviction
under `refute_off` that `refute_on` avoids, that is reported as the cost of the
rule and not used to reverse it.

## Why this is a repair and not a fit

The preference was introduced to answer an over-strictness symptom: bodies
convicting every design and the control alike. `BOUNDARY.md` shows the cause
was `throughout` asserting over the row that ENDED its window -- an operator
bug, design-independent, provable with no reference. With the cause fixed, the
preference has nothing left to prevent, and what it still does is discard
separation: on run 3 it was throwing away 53% of the corpus.

So the ordering becomes the one this tree already argued for when the dissent
guard was demoted from a tier: **separation first, then the guards, then more
separation.** Refutation moves to the bottom of the same key -- it breaks a tie
between bodies that separate equally, and it no longer outranks separating at
all.
