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

## CORRECTION: the ceiling above was my own rule, not the corpus

Every ceiling in this file was swept with the REFUTATION PREFERENCE left on --
`_choose_bodies` prefers, at every tier, a body the population does not
unanimously convict. That rule is mine; it was added to fix an audit failure.
Dropping it (`e6_refutation_cost.py`):

    corpus   preference ON   preference OFF
    run 1             5.7%             1.4%
    run 2             9.0%             6.3%
    run 3            23.3%             5.3%

Run 3's "23.3% ceiling, thirteen points above target, unreachable by any rule"
was that preference discarding 53% of the corpus. The corpus reaches 5.3%. I
swept every parameter except the one rule I had introduced myself, then
reported its cost as a property of the data.

It was also already argued against: no spec-derived design is guaranteed
correct, so a check convicting all seven may be right where all seven are
wrong. "Convicting all of them is an okay check."

## And it is a TRADE, so neither setting is reproducible

                      blindness   audit      target
    run 1  ON              5.7%    0/15      MET
    run 1  OFF             1.4%    2/14      no
    run 3  ON             23.3%    1/14      no
    run 3  OFF             5.3%    1/11      no

The preference buys audit on run 1 and buys NOTHING on run 3 while costing it
eighteen points of blindness. No fixed setting satisfies both legs on both
corpora, and choosing per-corpus by reading the audit column is gating on the
grade.

## What actually convicts the control

On run 3, four checks convict it and they are one kind:

    REQ-0042 [interface]   "The scl_oen output value 1 releases SCL so the
                            external pull-up can drive it high..."
    REQ-0005 [behavioural] "Driving scl_oen or sda_oen low pulls the
                            corresponding I2C line low..."
    REQ-0044 [interface]   "...driving sda_oen low drives the SDA line low."
    REQ-0045 [interface]   "When sda_oen is 1, the SDA line is released..."

These describe OPEN-DRAIN BUS SEMANTICS -- what happens to the external I2C
line, which is not a module output and depends on pull-ups and other masters.
The control is right to fail them; the checks over-claim. Only REQ-0005 is
classified behavioural, which is why audit reads 1 and not 4.

That is the same defect the RTL editor's floor is made of: checks written for
text that states no obligation at the module boundary. Remove that class and
audit goes to 0 WITHOUT the refutation preference, which would leave blindness
at 1.4-5.3%. That -- not selection -- is the remaining work.
