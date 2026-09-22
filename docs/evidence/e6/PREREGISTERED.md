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

---

## What runs 1 and 2 said, and the correction it forced

    corpus   preference ON            preference OFF
    run 1    6.5% blind, audit 0/15   1.4% blind, audit 1/14
    run 2    9.9% blind, audit 0/14   6.1% blind, audit 0/13
    run 3   24.4% blind, audit 0/13   9.2% blind, audit 0/14

As pre-registered, the conviction under `refute_off` was **reported and not
used to reverse the rule**. It was used to look at the check, which is a
different thing: a control may REJECT an oracle, and reading what it rejected
is how the rejection is worth anything.

**REQ-0001, and it indicts the PLACEMENT rather than the rule.** Its six
corpus bodies:

    body  separates  refuted
      #0      18242    yes
      #1       5525    yes     <- chosen with refutation below separation
      #2      10711    yes
      #3          0    no
      #4      15626    yes
      #5       2601    no      <- chosen with refutation above it
      
Four of six convict all seven spec-derived designs, and the more over-strict
the body, the more cells it "separates" -- because a refuted check closes cells
BY convicting. A key that reads separation before refutation therefore reads
over-strictness as reach, and picks the worst of the four.

So the tier was wrong and removing the guard entirely was also wrong. The
guard belongs exactly where this tree already moved the dissent guard:
**separation first, then the guards, then more separation.**

    placement                  run 1   run 2    run 3
    tier (as shipped)           6.5%   9.91%   24.41%
    guard (above how much)         *   7.91%    9.23%
    tiebreak (below how much)   1.4%   6.13%    9.17%

The guard gives up six hundredths of a point against the most permissive
placement on run 3, and buys back the fifteen the tier was costing.

**Decided on blindness and on this tree's own stated ordering, not on the
audit column** -- the table above is reported because it is the cost of the
rule, and the placement would be the same if the audit column were blank.
