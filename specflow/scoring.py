"""SCORING. Everything here reads the REFERENCE, and nothing here may be called
from a selector.

Split out of `specflow.population` because that module says in writing why:

    *"the moment an audit lives beside a selector somebody wires the audit INTO
    the selector and the grade stops being independent."*

It said so and the selection work put `audit`, `Report` and `set_blindness` in
the same file as `select` anyway. The separation is now structural rather than
stated: this module imports from `specflow.population`, `specflow.population`
imports nothing from here, and a cycle would be an ImportError rather than a
review comment.

WHAT THAT MAKES ADMISSIBLE. A selection rule may be derived from anything in
`population`. Nothing in this module may reach a repair prompt, a selector, or
a design still to be graded -- it is computed LAST, over a set already built,
and it feeds nothing back.

**AND THE COMPLETENESS METRIC LIVES HERE FOR THE SAME REASON.** `set_blindness`
was reported as a golden-free number until the polarity correction; deciding
which of two disagreeing designs is actually wrong needs the reference, so it
is a scoring instrument. `wrong` is a REQUIRED argument, not an optional one,
so it cannot be computed without admitting that.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from specflow.population import DecideOn, Rows, Selection


# --------------------------------------------------------------------------
# COMPLETENESS. Golden-free, and the only number here that predicts what a
# repair loop achieves rather than describing the set it was computed from.
# --------------------------------------------------------------------------
#: `differ(rows_a, rows_b) -> bool` -- do these two designs differ at this
#: testpoint? A fact about rows, so it takes rows.
Differ = Callable[[Rows, Rows], bool]
#: `wrong(a, b, testpoint) -> set[str]` -- which of the two design NAMES
#: actually differs from the REFERENCE there. A fact about designs, so it takes
#: names. At a cell where they disagree at least one of them must be in it.
Wrong = Callable[[str, str, str], "set[str]"]


@dataclass(frozen=True)
class Blindness:
    """How much of what the population disagrees about the set cannot see.

    `spurious` is the cells the set objected at and got WRONG -- it objected to
    the design that was correct there. Those count as BLIND, because objecting
    to a correct design is a false rejection and not coverage.
    """

    blind: int
    disagreements: int
    spurious: int = 0

    @property
    def rate(self) -> float:
        """0.0 when the set truly objects somewhere in every disagreement cell."""
        return self.blind / self.disagreements if self.disagreements else 0.0

    @property
    def apparent(self) -> int:
        """Cells the set objected at, right or wrong -- what the uncorrected
        metric reported as closure."""
        return self.disagreements - self.blind + self.spurious

    @property
    def spurious_rate(self) -> float:
        return self.spurious / self.apparent if self.apparent else 0.0

    def __str__(self) -> str:
        return (f"{self.blind} of {self.disagreements} disagreement cells "
                f"unseen = {self.rate:.1%} blind, of which "
                f"{self.spurious} were objected to on the wrong side "
                f"({self.spurious_rate:.1%} of apparent closure)")


def set_blindness(
    deciders: Iterable[DecideOn],
    by_design: Mapping[str, Mapping[str, Rows]],
    *,
    differ: Differ,
    wrong: Wrong,
) -> Blindness:
    """Of the cells where two spec-derived designs disagree, how many does the
    set fail to object to ON THE SIDE THAT IS ACTUALLY WRONG.

    A cell is a (design pair, testpoint). `by_design` is
    `{design: {testpoint: rows}}`; `differ` decides whether the pair disagrees
    there; `wrong` says which of them the REFERENCE contradicts.

    **`wrong` IS REQUIRED, WHICH MAKES THIS A SCORING INSTRUMENT AND NOT A
    SELECTION ONE.** It reads a reference, so it may never feed `select` -- and
    a caller without a reference gets a TypeError rather than a flattering
    number, which is the point. See
    `blindness_credits_objecting_to_the_correct_design` for what the version
    without it reported and why that number must not be used.

    **A SPURIOUSLY CAUGHT CELL COUNTS AS BLIND.** The set objected there and
    objected to the design that was right; that is a false rejection wearing
    coverage's clothes, and counting it as closure is what made the uncorrected
    metric a rebadged objection count.

    **ONE DEFECT REMAINS AND IT IS NOT FIXED HERE.** The objection is recorded
    per TESTPOINT, so it still need not land at the disagreeing row or on the
    disagreeing port -- a check objecting elsewhere in the same testpoint is
    credited. That inflates closure, so every figure from this function is still
    OPTIMISTIC. Fixing it means carrying the objection's edge and port, which
    the recorded verdict maps do not.
    """
    checks = list(deciders)
    names = sorted(by_design)
    blind = spurious = cells = 0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = sorted(set(by_design[a]) & set(by_design[b]))
            for tp in shared:
                ra, rb = by_design[a][tp], by_design[b][tp]
                if not differ(ra, rb):
                    continue
                cells += 1
                hit_a = any(d(ra) for d in checks)
                hit_b = any(d(rb) for d in checks)
                if not hit_a and not hit_b:
                    blind += 1
                    continue
                bad = wrong(a, b, tp)
                if (hit_a and a in bad) or (hit_b and b in bad):
                    continue                      # objected on the wrong side
                blind += 1
                spurious += 1
    return Blindness(blind, cells, spurious)




@dataclass(frozen=True)
class Report:
    """A span and its false-reject rate, which are one result and not two.

    There is deliberately no accessor returning either half alone. Quoting reach
    without the audit beside it is the defect nine headlines on this work were
    retracted for, and the type is the place to stop it rather than a docstring.
    """

    checks: int
    requirements: int
    of_requirements: int
    #: How many kept checks convict a design that satisfies the specification.
    #: **Computed LAST and fed back into nothing.**
    convicts_reference: int
    blindness: Blindness | None = None

    @property
    def span(self) -> float:
        return (self.requirements / self.of_requirements
                if self.of_requirements else 0.0)

    @property
    def false_reject(self) -> float:
        return self.convicts_reference / self.checks if self.checks else 0.0

    def __str__(self) -> str:
        blind = f", {self.blindness}" if self.blindness else ""
        return (f"{self.checks} checks spanning {self.requirements} of "
                f"{self.of_requirements} = {self.span:.0%}, audit "
                f"{self.convicts_reference} = {self.false_reject:.1%}{blind}")


def audit(selection: Selection,
          convicts_reference: Callable[[str], bool],
          *, requirement_of: Callable[[str], str],
          of_requirements: int,
          blindness: Blindness | None = None) -> Report:
    """Score a set that is ALREADY BUILT against the reference. Computed last.

    Separate from `select` on purpose: the reference reaches this function and
    cannot reach that one, so no audit result can steer a selection even by
    mistake. The benchmark has a reference and production does not, which is the
    whole reason the rule above must stand without it.

    **AND THE AUDIT COLUMN IS A DEFECT TO REMOVE, NOT A RATE TO TRADE AGAINST
    REACH.** Two sets of the same size and the same span, differing only in
    whether their members spare the reference: the one auditing at 10% accepted
    a wrong design at zero objections and the one auditing at 0% rejected it.
    The unsound members do not merely add false rejects -- they remove the
    ability to reject, because a set the reference itself fails cannot have
    "zero objections" mean "correct".
    """
    kept = selection.kept
    return Report(
        checks=len(kept),
        requirements=len({requirement_of(k) for k in kept}),
        of_requirements=of_requirements,
        convicts_reference=sum(1 for k in kept if convicts_reference(k)),
        blindness=blindness,
    )



def blindness_credits_objecting_to_the_correct_design() -> str:
    """The defect the polarity check removes, and what it did to every figure
    this metric produced before it.

    Found by a reader asking why blindness tracked audit failure so strongly.
    The answer was not three mechanisms. It was mostly one artefact.
    """
    return (
        "**THE METRIC CREDITED A CELL WHEN SOME CHECK OBJECTED TO EITHER "
        "DESIGN, WITHOUT ASKING WHICH ONE WAS WRONG THERE.** At a cell where A "
        "and B disagree at least one of them differs from the reference -- but "
        "objecting to the one that is CORRECT scored identically to objecting "
        "to the one that is wrong. So a check that objects to everything "
        "achieved maximum apparent coverage and maximum false rejection at "
        "once, and the metric recorded only the first.\n\n"
        "**WHICH IS MOST OF WHY BLINDNESS TRACKED THE AUDIT.** 'Closes more "
        "cells' and 'convicts more designs' were near-synonyms under that "
        "condition, and convicting more designs is how a check convicts the "
        "reference.\n\n"
        "**MEASURED, on 5,656 disagreeing cells over nine designs:**\n\n"
        "    set                       apparent   TRUE   blindness       spurious\n"
        "    t=6, all 201 checks          3,370  2,830   40.4 -> 50.0%   540 = 16.0%\n"
        "    t=6, the 163 SOUND ones      2,552  2,484   54.9 -> 56.1%    68 =  2.7%\n"
        "    t=6, the 38 audit failures   1,868  1,231   67.0 -> 78.2%   637 = 34.1%\n\n"
        "**SPURIOUS CLOSURE IS 12.6x MORE CONCENTRATED IN THE CHECKS THAT "
        "CONVICT THE REFERENCE: 34.1% against 2.7%.** A third of what they "
        "appeared to contribute was them objecting to the correct design.\n\n"
        "**AND IT HALVES THE PRICE OF A CLEAN SET, WHICH IS THE ACTIONABLE "
        "HALF.** Dropping the 38 looked like a 14.5-point sacrifice (40.4 -> "
        "54.9). Measured on the side that is actually wrong it is **6.1 points "
        "(50.0 -> 56.1)**, and the clean set keeps **87.8% of real closure at a "
        "zero audit.** The unique true payload of the 38 is 346 cells, not the "
        "818 the uncorrected count reported.\n\n"
        "**WHAT IT COSTS THE METRIC IS ITS ADMISSIBILITY.** Deciding which side "
        "is wrong needs the reference, so this is a SCORING instrument and can "
        "never feed a selection rule. Blindness is therefore not the "
        "golden-free completeness number it was reported as. The matched-pair "
        "editor result survives only in a weaker form -- a set that objects "
        "more drives a design further -- which is consistent with the "
        "uncorrected metric having been a rebadged objection count.\n\n"
        "**AND ONE GOLDEN-FREE SIGNAL FALLS OUT OF THE CORRECTION AND IS STILL "
        "NOT ENOUGH.** INDISCRIMINACY -- of the disagreeing cells a check "
        "closes, how often it objects to BOTH designs rather than picking a "
        "side -- needs no reference and predicts audit failure at **3.35x "
        "lift, 63% precision**, the best here by a wide margin. Used as a "
        "FILTER it is dominated: it reaches 11.1% audit at 65.0% true "
        "blindness, while dropping exactly the 38 reaches 0% at 56.1%. About "
        "one point of audit per two points of blindness, against the "
        "reference's six points of audit per two. **A good predictor and a bad "
        "optimiser**, which is the fifth instrument here to be both."
    )


def objection_placement_buys_closure_more_cheaply_than_the_count() -> str:
    """The one tell worth keeping, and it is not doing the job the others were
    tried for.

    `placement` -- how much more often a check speaks where the population
    disagrees than where it agrees -- does not find sound checks among unsound
    ones. It finds, among checks that convict everything, the ones whose
    objections land where the designs actually differ.
    """
    return (
        "**IT IS A COMPLETENESS INSTRUMENT, NOT A SOUNDNESS ONE, AND THE SET "
        "IT BUILDS MAKES THAT UNAMBIGUOUS.** `placement < 0.0017` keeps 151 "
        "checks: **all 126 of t = 0, exactly 1 of the 75 between, and 24 of "
        "the 263 that convict all seven.** The audit is 24 -- so **24 of the "
        "25 checks it adds to t = 0, or 96%, convict the reference.** It is "
        "not selecting for soundness. It is choosing WHICH false rejections to "
        "accept.\n\n"
        "**AND ON THAT JOB IT BEATS THE RULE BY TWO AND A HALF TIMES.** The "
        "triple, with blindness polarity-corrected, beside every set on the "
        "board:\n\n"
        "    set                         checks   span    *audit*   blind   spurious   TRUE cells\n"
        "                                                                              per reject\n"
        "    t = 0 golden-free              126   63.2%   * 0.0%*   99.9%     33.3%          --\n"
        "    t = 6 golden-free              201   81.6%   *18.9%*   50.0%     16.0%          74\n"
        "    sound subset, REFERENCE-picked 163   77.0%   * 0.0%*   56.1%      2.7%          --\n"
        "    **placement < 0.0017**         151   69.0%   *15.9%*   20.8%      9.8%         186\n\n"
        "**It beats t = 6 on audit, on blindness and on spurious closure at "
        "once**, for 11 requirements of span -- 60 of 87 against 71. The 25 it "
        "adds close **4,471 true cells the t = 0 set cannot reach**, over 10 "
        "requirements.\n\n"
        "**IT IS A PLATEAU, NOT A FITTED EDGE.** Every threshold from 0.0005 "
        "to 0.003 gives the same 151-or-149-check set at 20.8% blind and 9.8% "
        "spurious; the curve then degrades monotonically -- 0.02 reaches 24.9% "
        "audit for 20.3% blind, and 0.08 reaches 0.0% blind at 42.5% audit, "
        "which is the whole corpus arriving.\n\n"
        "**THE HONESTY CONDITIONS, ALL THREE.** The tell is golden-free -- it "
        "reads only the check's own verdicts and which testpoints split the "
        "population. **The THRESHOLD was picked by reading a frontier that "
        "contains the audit**, so this point is a calibration exactly as "
        "`t = 0` is, and belongs in the calibrated column. The closure is "
        "concentrated to the point of fragility: **one check carries 766 of "
        "the 4,471 cells** and ten requirements carry all of them. And the "
        "blindness granularity defect is untouched -- an objection is recorded "
        "per testpoint, so it need not land at the disagreeing row or port, "
        "and every figure in the table above is optimistic in the same "
        "direction."
    )
