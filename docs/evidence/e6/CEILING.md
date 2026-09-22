# Blindness is corpus-determined, not rule-determined

The goal asks for blindness < 10% reproducibly. Three completed end-to-end runs
of the same pipeline, on the same specification, and the BEST FIGURE ANY
SELECTION RULE CAN REACH on each one's own corpus:

    corpus   ceiling   the run achieved
    run 1      5.7%    5.7%
    run 2      9.0%    14.6%  (9.2% when re-chosen offline)
    run 3     23.3%    24.5%

The ceiling is computed by sweeping `max_dissent_weighted` from 1.0 to 99.0
under both the tier-first and separation-first orderings -- every rule this
tree has -- and taking the best. On run 3 that whole range is 23.3% to 25.9%.

**Every run landed at or near its own ceiling.** So the chooser fix is real and
does what it claimed -- it closes the gap between achieved and achievable, and
took run 2's corpus from 14.6% to 9.2% -- but it cannot move the ceiling, and
on run 3 no rule in the sweep comes within thirteen points of the target.

## What that rules out

**Selection.** Exhausted by construction: the sweep IS the rule space.

**Admission.** On run 3, 103 admissible bodies were not chosen and they reach
**0.0%** of the 7200-cell residue. On run 2 the same figure was 0.0%, on run 1
4.1% worth two tenths of a point. There is nothing left in the corpus to admit.

**Corpus thinness.** Run 3 has 587 bodies over 148 requirements at median depth
4 against run 2's 616 over 152 at the same median, and MORE distinct checks
(effective_size 107 against 100). It is not a smaller corpus; it is a corpus
whose bodies separate less.

**Authoring at cells.** Already at the plan's pre-registered null -- 40 authored
at blind cells, 2 adopted on run 3, 4 on run 2, against a "<=15% closes the
line" bar.

## What it leaves

The variance is upstream of everything measured here: what makes one run's
checks separate 94.3% of the disagreement cells and another's 76.7%, from the
same specification and the same stage code. Until that is understood and
controlled, a sub-10% figure is a property of the corpus a run happens to draw,
not of the pipeline -- which is precisely what "reproducible" excludes.

Run 1's corpus meets the target under ANY rule. Run 3's meets it under NONE.
