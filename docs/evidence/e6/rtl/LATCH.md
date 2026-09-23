# The latch fixes, and the case that proves they are not a loophole

`rtldbg5`: same 518-line candidate, same 122 frozen checks, same 90-trial
budget as `rtldbg4`. The only difference is the two latch fixes. It was killed
mid-round-0 by `429 BUDGET_EXCEEDED`, so this is 17 commits of a round, not a
finished run -- but the mechanism is visible in them.

      #  latch       passing       mismatch  kind
      1  False      86 -> 86     246 -> 207
      2  False      86 -> 83     246 -> 204
      3   True      86 -> 87     246 -> 206  latch
      4   True      87 -> 88     206 -> 176  latch
      5   True       held 88     176 -> 175  GRADIENT
     ...
     13   True       held 88     175 -> 131  GRADIENT
     14  False      88 -> 88     131 ->  48
     15  False      88 -> 88     131 ->  48

## The baseline no longer resets

Commit #2 rolls back at 83 and #3's baseline reads **86** -- the accepted
design, not the attempt just discarded. After #4 reaches 88 every later
baseline reads 88.

`rtldbg4`, on the same inputs without the fix, read its baseline from whatever
the last failed commit scored: #6 rolled back at 86 and #7 "latched 86 -> 88",
banking a design that only recovered ground the accepted one already held. Its
passing count never passed 88 across 25 commits.

## The gradient banks a repair that tips no requirement

#13 latched `175 -> 131` failing testpoints at passing held 88 -- a 25%
reduction the old rule discarded, because no requirement crossed from failing
to passing. On `rtldbg4` the same shape appeared as #14 (`178 -> 79`) and #21
(`105 -> 48`) and both were thrown away.

## AND IT IS NOT A LOOPHOLE, WHICH IS THE PART WORTH KEEPING

#14 and #15 look BETTER than #13 -- `131 -> 48`, a 63% reduction -- and were
refused:

    Commit did NOT latch ... Note what happened: REQ-0089, REQ-0125 stopped
    firing altogether rather than passing.

That is defect #93 arriving through the new clause and being stopped by it. The
gradient requires `not ((bad0 | ok0) & dark1)`, so a silencing puts those two
requirements in the dark set and closes it. The bigger number was bought by
losing evidence, and the guard priced it correctly.

A rule that had simply ratcheted on the failing count would have latched #14.

## Not finished

17 commits of round 0, then the budget ended. What is NOT measured here: where
the loop converges with the fixes, and whether the golden distance
(`GOLDEN.md`: 17385 -> 24151 defect cells under the old loop) improves, holds
or worsens. The candidate at the point of death is `rtldbg5-partial.v`.
