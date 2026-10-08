# The end-to-end run, and the rule change it paid for

`build_artifacts` all the way through -- S1, `[P]`, S2, S3, stimulus, normalize,
the oracle stage, the reference model, the rendered suite -- with every change
on this branch. Scored by `specflow/scorecard.py`, written by the run from its
own artifacts and its own seven spec-derived designs. The control is read for
the audit column and reaches nothing else.

    SPAN       116/117 behavioural = 99.1%
    BLINDNESS  613/44746 cells = 1.4%       (population 7, effective_size 116)
    AUDIT      2/14 judgeable = 14.3%
    ACCEPTS    0 of 7 design(s)
    TARGET span > 90%, blindness < 10%, audit = 0: NOT MET

    dispositions: 132 TRUSTED, 22 ABANDONED, 3 VACUOUS
    corpus 627 bodies / 157 requirements, median 4
      {generate 157, resample 157, repair 273, cell 40}

## The two checks that convicted the control, and what they say

`REQ-0001` and `REQ-0047`. Both convict **all seven** spec-derived designs.
Both had sibling bodies in their own corpus that the control SPARES -- three of
them for REQ-0047 -- and the chooser took the refuted one anyway, because it
closes more cells.

It closes them BY convicting. A check refuted overall still separates a pair at
one testpoint, so `placement` and marginal gain both reward it. That is the
recorded way this metric was gamed -- "24 of them convict all seven designs,
which score ~0 by objecting to everything" -- arriving through the
per-testpoint predicate instead of the folded one.

`_choose_bodies` now prefers a body the population does not refute, ahead of the
`dissent_weighted` guard and of separation. A preference and never a rejection
at every tier: no spec-derived design is guaranteed correct, so a requirement
whose bodies are all refuted still freezes one. Re-choosing this run's own
corpus under that rule -- `docs/evidence/e5_rechoose.py`, zero model calls:

    as the run froze it          span  99.1%   blind 1.4%   audit 2/14   NOT MET
    refuted bodies passed over   span 100.0%   blind 5.7%   audit 0/16   MET

Blindness rose, and that is the trade stated rather than hidden: those bodies
were buying it with over-strictness.

**Two processes, identical scorecards.** Ties in the chooser are broken by
sorted, index-ordered iteration and the standing body wins an exact tie -- before
that was pinned, the same configuration gave 14.7% blindness with audit 0 of 22
on one run and 13.8% with audit 1 of 21 on the next, with nothing changed but
the interpreter's hash seed.

## What is still not reached

**The audit denominator is 16 of 117.** The benchmark's control declares no
`PROBE_PORTS` -- it predates probes, as do the nine standing yardstick designs
and every benchmark RTL -- so it can only judge the checks that read none.
`base.probe_values` makes the rest abstain rather than be convicted against
permanently-false state terms, which is how the same column read 57.6% before.
Audit 0 over 16 is thinner evidence than audit 0 over 117 would be, and the
scorecard says so in its own note.

**`ACCEPTS 0 of 7`.** The set rejects every spec-derived design. That is the
plan's over-constricted end, and its stated target -- "one class, containing the
correct design" -- is not reached. The audit column says the correct design is
not among the rejected, on the checks that can say so.
