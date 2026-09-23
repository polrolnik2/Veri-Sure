# `score` cannot represent more than one check per requirement

## What I set out to measure, and what I actually measured

The plan's direction is "fill the pool, then select": the run accepts ONE body
per requirement -- 122 of a 616-body corpus -- so most of what was authored and
paid for never reaches the set. More bodies means more separators, which should
lower blindness.

I admitted extra well-formed bodies from the corpus and scored:

    config              bodies   span      blindness   audit          eff_size
    accepted only          122   0.9737    0.1454      9/37  = 0.2432       99
    +1 body each           241   0.9737    0.1644      15/40 = 0.3750       90
    +2 bodies each         349   0.9737    0.2336      16/43 = 0.3721       85

Blindness rising and `effective_size` FALLING as separators are added is not
how adding separators behaves. It is not what happened. `scorecard.py:201`:

    held = {str(o["req_uid"]): RequirementOracle(...)
            for o in (oracles or []) if o.get("source")}

**A dict keyed by requirement uid.** Two bodies for one requirement overwrite,
and only the last survives. So those rows do not measure 241 and 349 checks.
They measure 122 checks each time, with the accepted body REPLACED by a corpus
alternative.

## What the numbers do say, read correctly

    the body SELECTION chose        blind 0.1454   audit 9/37  = 0.2432
    an alternative from the corpus  blind 0.1644   audit 15/40 = 0.3750
    a second alternative            blind 0.2336   audit 16/43 = 0.3721

**Selection picks better bodies than the alternatives on BOTH columns** --
lower blindness and fewer convictions of a correct design -- across 122
requirements at once. That is a defence of the selection stage measured against
the pool it chose from, and the run does not report it about itself.

## The structural finding

**Blindness over a set with more than one check per requirement is not
computable by `score` as written**, and nothing prevents a caller passing such
a set -- they are silently collapsed.

So the plan's central direction cannot be MEASURED by the current instrument,
let alone shipped. `placement`'s 151-checks-from-464-bodies result was computed
by a driver with its own scoring, not by `score`. Wiring that direction into
the pipeline needs the scorecard to carry a SET, not a map -- a larger obstacle
than anything about the pool itself.

## What was not established

Whether admitting more bodies actually lowers blindness. The experiment that
would answer it cannot run until `score` stops keying by requirement, and the
numbers above say nothing about it in either direction.
