# Selection on the deep pool: one class is reachable, span > 90% is not

`POOL-DEPTH.md` meets span and blindness together on 476 well-formed bodies and
pays 38.5% audit for it, because rejections union. Selection is supposed to choose
WHICH constriction to keep. This is that measurement, on `full2`'s own 482
testpoints.

    population: 7 designs, effective_size 5, 329 split testpoints of 482

so "constrict to one class" means **5 -> 1**.

## The criterion, and the version of it that was wrong

Both legs read only the spec-derived population -- `max_convictions = t` drops a
check convicting more than `t` designs, `min_placement = p` keeps a check whose
objections land where the population SPLITS. Neither reads the control.

The THRESHOLD has to be chosen by something too, and choosing it by the audit
column is gating on the grade. So the criterion is the plan's own primary metric
-- except that the first version of it said **fewest** classes, and the grid
answered that in one run: nine of seventeen rows accept ZERO designs, so "fewest"
ranked total over-constriction first. The plan is explicit and I had not read it
closely enough:

> Accepting exactly one class is a success only if the correct design is in it --
> otherwise it is the screened set's failure wearing a good number. None, or one
> excluding the correct design => over-constricted.

Corrected: **accept EXACTLY ONE class, at the highest span.** Whether the control
is in that class is what `audit = 0` says, so that half of the success test is the
reported number rather than an input to the choice.

## The grid, on the pool with no other rule applied

    ruleset                   kept   span*   classes  accepted designs
    pool, unselected           476  0.9737         0  (none)
    t=0                        183  0.6667         5  0 1 2 3 4 5 6
    t=1                        205  0.7105         4  3 4 5 6
    t=2                        228  0.7632         1  3
    t=3                        239  0.7895         0  (none)
    t=4                        248  0.8070         0  (none)
    t=5                        264  0.8421         0  (none)
    t=6                        280  0.8509         0  (none)
    t=4, placement>=0.0        232  0.7719         0  (none)
    t=4, placement>=0.05       194  0.6930         0  (none)
    t=4, placement>=0.1        192  0.6930         0  (none)
    t=4, placement>=0.143      192  0.6930         0  (none)
    t=4, placement>=0.2        188  0.6754         2  1 6
    t=4, placement>=0.3        186  0.6754         2  1 3 6
    t=6, placement>=0.1        197  0.7018         0  (none)
    t=6, placement>=0.143      195  0.7018         0  (none)
    t=6, placement>=0.2        190  0.6754         0  (none)

`span*` is requirements covered over the behavioural-observable denominator,
computed to rank the grid; a chosen row's span is taken from `scorecard.score`.

## Three things it shows

**A MORE PERMISSIVE THRESHOLD MAKES THE SET STRICTER, and the direction is the
whole reason selection is needed.** `t` rising keeps more checks -- 183, 205, 228,
239, 248, 264, 280 -- and rejections UNION, so the accepted set shrinks: 7 designs
at `t=0`, 4 at `t=1`, 1 at `t=2`, none from `t=3` on. "Admitting more checks"
and "constricting harder" are the same move.

**One class IS reachable, at exactly one threshold.** `t=2` accepts design `3`
alone -- the shape the plan targets, 5 classes down to 1. Nothing else on the grid
does: every other row is 0, 2, 4 or 5.

**AND IT COSTS THE SPAN BAR.** `t=2` spans 76.3% against the 90% target, and no
row that constricts at all reaches 90% -- the best is `t=6` at 85.1%, which
accepts nothing. Only the unselected pool clears span, and it accepts no design.
That is the plan's own trade, sharper here than where it was first measured
(`placement` "pays 12.6 points of span"): on this pool the cheapest real
constriction costs **21 points**.

## What is NOT concluded

That selection is the wrong lever. The grid above applies NO other rule -- not the
licence rule, not the phase rule, both of which took the accepted set's audit from
9/42 to 1/40 without touching span. A pool whose spurious convictions have already
been removed should need far less constriction to reach one class, and should
therefore keep more span at the threshold that does. `e6_composite.py` runs the
four steps in a stated order and reports what each ADDS, which is the measurement
this document does not contain.

Nor that `t=2`'s accepted design is the right one. `audit` answers that and is
reported for whatever the criterion picks; it is not consulted in picking.

Reproduce: `docs/evidence/e6_select.py <corpus-dir> <golden-suite-dir>`.
No model calls. Golden is RUN and never read.
