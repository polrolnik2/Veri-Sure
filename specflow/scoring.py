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

from specflow.population import (
    DecideOn,
    PopulationShape,
    Rows,
    Selection,
)


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
    #: **THE THIRD LEG, AND IT IS NOT OPTIONAL.** Span and audit alone describe
    #: what a set refuses; blindness describes what it cannot see, and the set
    #: that optimises the first two is the one that says nothing.
    blindness: Blindness
    #: **THE POPULATION'S OWN STRUCTURE, ATTACHED.** k1's rule reads 126-for-126
    #: with one design present and 6.2% without it, and every subset of the
    #: seven that audits at exactly zero contains that design. A conviction
    #: count is not interpretable without knowing what it counted, so a Report
    #: cannot be built without saying.
    population: PopulationShape

    @property
    def span(self) -> float:
        return (self.requirements / self.of_requirements
                if self.of_requirements else 0.0)

    @property
    def false_reject(self) -> float:
        return self.convicts_reference / self.checks if self.checks else 0.0

    @property
    def triple(self) -> tuple[float, float, float]:
        """span, audit, TRUE blindness -- and there is no accessor for one."""
        return self.span, self.false_reject, self.blindness.rate

    def __str__(self) -> str:
        shape = self.population
        worst = max(shape.dissent, key=lambda d: shape.dissent[d])
        return (f"{self.checks} checks spanning {self.requirements} of "
                f"{self.of_requirements} = {self.span:.0%}, audit "
                f"{self.convicts_reference} = {self.false_reject:.1%}, "
                f"blind {self.blindness.rate:.1%} "
                f"[population {len(shape.designs)} designs, effective "
                f"{shape.effective_size()}, top dissent {worst} at "
                f"{shape.dissent[worst]:.0%}]")


def audit(selection: Selection,
          convicts_reference: Callable[[str], bool],
          *, requirement_of: Callable[[str], str],
          of_requirements: int,
          blindness: Blindness,
          population: PopulationShape) -> Report:
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
        population=population,
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


# --------------------------------------------------------------------------
# THE EXPERIMENTS. Every one reads the reference, so every one lives here.
# P1, P2 and F0 sweep the population and the corpus; V0 and V2a ask what a
# retained corpus would actually contain; F1 asks whether a text-side
# instrument transfers off its home module.
# --------------------------------------------------------------------------

def the_zero_audit_belongs_to_one_design() -> str:
    """P1, pre-registered, and it fires the retraction.

    Every subset of k1's seven designs, swept at `t = 0`, with the audit
    computed over all 464 bodies and the blindness denominator held fixed at
    all 5,656 cells so a smaller population cannot look less blind for free.
    """
    return (
        "**THE 126-FOR-126 IS A PROPERTY OF ONE DESIGN AND IS RETRACTED AS A "
        "PROPERTY OF THE RULE.**\n\n"
        "120 subsets of size 2 or more produce a non-empty `t = 0` set. "
        "**32 of them audit at exactly 0%. All 32 contain G. Zero of the 57 "
        "G-free subsets reach it.**\n\n"
        "    population size   with G: mean t=0 audit   without G\n"
        "    2                 2.2%  (6 subsets)         11.4%  (15)\n"
        "    3                 1.2%  (15)                10.1%  (20)\n"
        "    4                 0.8%  (20)                 8.8%  (15)\n"
        "    5                 0.5%  (15)                 7.5%  (6)\n"
        "    6                 0.3%  (6)                  6.2%  (1)\n"
        "    7                 0.0%  (1)                  --\n\n"
        "and the five worst `t = 0` audits are DH, BDH, BH, BD and CD at "
        "13.3-13.8% -- **every one of them G-free.**\n\n"
        "**THE MECHANISM, STATED PLAINLY.** G is off the population majority at "
        "78% of split cells. 'Objects to nobody, including G' is therefore "
        "close to 'objects to almost nothing', so G is a SINK that absorbs "
        "over-strict checks before the rule has to judge them. The rule's "
        "stated rationale is that a requirement most competent independent "
        "implementations violate is more likely one the CHECK misread; G is not "
        "a typical competent implementation, and the operative rule is nearer "
        "**'do not object to the weirdest design'**.\n\n"
        "**WHAT SURVIVES.** The rule still works -- 6.2% false rejection at "
        "`t = 0` without G is far better than the 64.4% base rate over the "
        "whole corpus. What does not survive is the exactness, and exactness "
        "was the whole argument for preferring it to every gate measured at "
        "1.1x-1.6x lift. `B2`'s characterisation is a GATE, not a reporting "
        "convenience: a population whose dissent is dominated by one member "
        "cannot support a precision claim about the rule."
    )


def weighting_the_population_is_decoration() -> str:
    """P2. Two ways of not counting every design as one opinion, and neither
    moves the frontier."""
    return (
        "Weighting each design by its mean distance from the rest, normalised "
        "to sum to N:\n\n"
        "    B 0.80   C 0.93   D 0.77   E 0.76   F 1.25   G 1.64   H 0.85\n\n"
        "**NOTE WHICH WAY THIS PUSHES.** The most independent design is the "
        "OUTLIER, so independence-weighting weights G UP -- the exact opposite "
        "of what `dissent_weighted` does. Both are on the board and neither was "
        "chosen by looking at the answer.\n\n"
        "    rule                     t    checks    span   audit   blind\n"
        "    unweighted               5       188   80.5%   14.4%   54.4%\n"
        "    unweighted               6       201   81.6%   18.9%   50.0%\n"
        "    independence-weighted    6       197   81.6%   17.3%   51.0%\n\n"
        "Interpolating the unweighted curve to the weighted point's audit of "
        "17.3% gives about 51.7% blindness against the weighted 51.0% -- "
        "**0.7 points, inside the resolution of a 464-body corpus.** At the "
        "tight end it is worse on two axes of three: `t = 1` weighted reads "
        "65.5% span / 1.5% audit / 98.9% blind against unweighted's 72.4% / "
        "7.4% / 95.4%.\n\n"
        "**PRE-REGISTERED BAR: beat unweighted on the frontier at matched "
        "audit, or weighting is decoration. It does not, so it is.** Taken with "
        "`dissent_weighted` losing to the plain count at every matched size, "
        "the finding is that re-weighting the population -- in either "
        "direction -- is not where the signal is."
    )


def corpus_size_buys_span_and_saturates_on_blindness() -> str:
    """F0, pre-registered: flat refutes volume before anything is built,
    monotone makes A1 most of the plan. It is monotone, and the two axes
    separate."""
    return (
        "Subsampling the 464-body corpus, five draws per size, full triple at "
        "every threshold; `t = 6` shown:\n\n"
        "    corpus   checks    span   audit   blind\n"
        "       100       45   37.2%   21.6%   73.5%\n"
        "       200       88   57.7%   19.5%   60.5%\n"
        "       300      130   67.6%   19.8%   52.7%\n"
        "       464      201   81.6%   18.9%   50.0%\n\n"
        "**MONOTONE, SO A1 IS LOAD-BEARING -- AND THE TWO AXES SEPARATE, WHICH "
        "THE PRE-REGISTRATION DID NOT ANTICIPATE.** Audit is FLAT across a 4.6x "
        "range of corpus size (21.6% to 18.9%), so volume neither helps nor "
        "hurts soundness. Span climbs the whole way and is still climbing at "
        "464. Blindness climbs and then **saturates**: the first 100 bodies buy "
        "26 points, the last 164 buy 2.7.\n\n"
        "**AND THE SPAN COLUMN IS PARTLY TAUTOLOGICAL.** A random subsample of "
        "bodies also subsamples REQUIREMENTS, so some of that climb is just "
        "coverage arriving rather than selection improving. The "
        "non-tautological result is the blindness curve, and it says volume "
        "reaches a ceiling well inside the corpus this pipeline could already "
        "produce.\n\n"
        "**THE CEILING ABOVE ALL OF IT: the 464 bodies answer 73 of k1's 87 "
        "requirements, so no selection over this corpus can span more than "
        "83.9%** -- and `t = 6` is at 81.6%. Nearly all the span left on the "
        "table is requirements with no body at all, which is an AUTHORING "
        "problem, not a selection one."
    )


def resampling_one_prompt_produces_copies_and_blunderbusses() -> str:
    """V0, the experiment that should have preceded the capability axes.

    For every pair of bodies answering the same requirement, how differently do
    they behave against the seven designs, grouped by what differs between them.
    """
    return (
        "**THE HEADLINE NUMBER IS 46% AND THE HONEST ONE IS 4%.**\n\n"
        "Over 2,693 draw-vs-draw pairs -- the same prompt resampled -- 46% are "
        "COMPLEMENTARY: each reaches polarity-corrected disagreement cells the "
        "other does not. Conditioned on soundness that collapses:\n\n"
        "    draw-vs-draw pairs            pairs   identical   complementary   mean gain\n"
        "    **both SOUND**                   93       **69%**        **4%**        52\n"
        "    one sound, one not              715          4%           19%        857\n"
        "    both convict the reference    1,885         91%           58%      1,031\n\n"
        "**Among bodies that are both sound, resampling produces a copy 69% of "
        "the time and a complementary body 4% of the time.** The variance is "
        "STRENGTH, not semantics: one draw is a blunderbuss and the other is "
        "not. **A1 retains copies plus blunderbusses**, so the variety track is "
        "load-bearing rather than optional.\n\n"
        "**AND THE BOTTOM ROW IS A STRUCTURAL FINDING ABOUT THE RULE ITSELF.** "
        "Those pairs are 91% identical in their seven-bit conviction vector and "
        "58% complementary in which cells they close. **The rule's view cannot "
        "see the difference that matters for closure** -- which is exactly why "
        "`placement`, which reads WHERE a check objects, buys closure the "
        "conviction count cannot.\n\n"
        "**ONE GROUP READ 0.00 ON EVERY METRIC AND IT IS A CACHE ARTIFACT.** "
        "The volume round's 8 pairs scored Hamming 0, Jaccard 0, zero new "
        "cells, 100% identical. **8 of 8 are byte-identical bodies.** The "
        "recording key is `{stage}_r{round}` and the resume port returns the "
        "FIRST response for a matching key, so N draws under one stage name are "
        "one response replayed N times. The documented failure mode is live in "
        "the data, and the volume round is not evidence about resampling."
    )


def obligation_decomposition_is_untested_on_most_of_its_target() -> str:
    """V2a, and the pre-registered verdict fires only where the test applies.

    Selection drops a whole body for one over-strict clause, so separable
    obligations are the only mechanism on the board that could raise span and
    lower audit at once. The free ceiling test asks how many of the 38 checks
    convicting the reference at `t = 6` contain a sound proper subset.
    """
    return (
        "**1 of 38 -- AND THE TEST ONLY APPLIES TO 6 OF THEM.** Reporting the "
        "first number alone would be the instrument's coverage published as the "
        "corpus's property.\n\n"
        "    what the body's structure actually is                        count\n"
        "    ONE TEMPORAL EXPRESSION -- the idiom does not apply, UNTESTED    20\n"
        "    one guard -- a single obligation, indivisible                     8\n"
        "    two or more droppable guards -- TESTED                            6\n"
        "    computed verdict variable -- no droppable guard                   3\n"
        "    if/else verdict -- my visitor never scanned `orelse`               1\n\n"
        "A subset counted only if it SPARED the reference **and still convicted "
        "at least one of the seven** -- deleting every guard makes a check that "
        "convicts nobody, which is soundness by silence.\n\n"
        "**THE GUARD IDIOM IS DROPPED: 1 of 6.** The axis as a whole is NOT "
        "refuted. Over half the reference-convicting checks state their whole "
        "obligation as a single temporal expression, which has no guards to "
        "drop; decomposing those means weakening an activation, a closing "
        "condition or an expectation, and that is a different experiment that "
        "has not been run.\n\n"
        "**AND ONE ROW IS MY OWN PARSER.** The visitor scanned an `if` node's "
        "body and not its `orelse`, so a `return (False, ...)` in an else "
        "branch read as no obligation at all. One check of 38, and it does not "
        "move the count of divisible ones -- an if/else is a single obligation "
        "either way -- but the miss is recorded because a structural classifier "
        "that under-counts produces exactly this shape of clean negative."
    )


def claim_kinds_transfer_where_lint_patterns_did_not() -> str:
    """F1. With correspondence dropped this is the ONLY remaining faithfulness
    instrument, so it is scored on both questions it has to answer."""
    return (
        "A licence rule names a CLAIM KIND -- a cycle count, a bit-slice, a "
        "value equality, a state name, a boundary word, an ordering -- and asks "
        "whether the requirement's own span licenses a claim of that kind. "
        "Kinds are module-independent by construction where signal names are "
        "not.\n\n"
        "**THE TRANSFER TEST PASSES, AND IT IS THE FIRST TEXT-SIDE INSTRUMENT "
        "HERE THAT HAS.** Derived on k1, scored on 316 frozen i2c bodies across "
        "five runs:\n\n"
        "    claim kind        makes it   FIRES   fire rate\n"
        "    cycle_count             28       6         21%\n"
        "    bit_slice                4       4        100%\n"
        "    value_equality          20      12         60%\n"
        "    state_name               6       3         50%\n"
        "    boundary                33      18         55%\n"
        "    ordering               228      51         22%\n\n"
        "**Zero of six fire zero times.** Three of four earlier text predicates "
        "fired zero times outside their home population; that is the lint "
        "failure and this is not it.\n\n"
        "**THE PRECISION TEST FAILS.** On k1, where there IS a reference:\n\n"
        "    set                          checks    span   audit   blind\n"
        "    t = 6, all                      201   81.6%   18.9%   50.0%\n"
        "    t = 6 minus the LIBRARY         155   72.4%   16.1%   50.8%\n"
        "    t = 6 minus the 38 (reference)  163   77.0%    0.0%   56.1%\n\n"
        "The library refuses 46 checks: **13 convict the reference and 33 are "
        "sound checks thrown away.** Union lift **1.40x, below the shipped "
        "licence rule's 1.64x**, and the two kinds with high lift fire twice "
        "each -- `bit_slice` reads 4.95x on 2 checks, which is the sample-size "
        "illusion, not a result. `ordering` carries 42 of the 46 fires at "
        "1.18x, so the library's yield is mostly its weakest rule.\n\n"
        "**AND FIRING IS NOT BEING RIGHT.** i2c has no population and no "
        "reference here, so the held-out column measures APPLICABILITY and "
        "nothing else. Held-out precision is unmeasured and stays unmeasured "
        "until F3 has a population. The split result is the useful one: the "
        "claim-kind formulation solves the transfer problem that killed the "
        "lint patterns and does not solve the precision problem, which is where "
        "the remaining work is."
    )


def the_population_majority_is_right_less_than_half_the_time() -> str:
    """The figure the plan flagged as needing reconciliation, reconciled -- and
    it is a stronger version of a warning already in `population`.

    Two numbers were on the board: the reference off the population majority at
    49.6% of split cells over SEVEN designs, against a recorded "majority right
    on 2,353 of 3,863 = 60.9%" over THIRTEEN.
    """
    return (
        "**NOT A CONTRADICTION -- TWO POPULATIONS.** Recomputed over k1's seven "
        "designs, 348 testpoints and 10 scored outputs:\n\n"
        "    split cells (design, testpoint, row, port)      4,085\n"
        "    the majority MATCHES the reference              1,981 = 48.5%\n"
        "    the reference is OFF the majority               1,965 = 48.1%\n"
        "    no reference value to adjudicate                  139 =  3.4%\n\n"
        "which is the 49.6% figure, recomputed with the unadjudicable cells "
        "separated out rather than folded in. The 60.9% was measured over "
        "THIRTEEN designs on 3,863 cells. Both stand; neither may be quoted "
        "without its population size, which is the same discipline "
        "`Selection.summary` applies to a threshold.\n\n"
        "**AND THE RECONCILIATION IS THE FINDING.** On seven designs the "
        "population's majority is right LESS THAN HALF THE TIME. `population` "
        "already forbids using the agreed value as an expected value, on the "
        "argument that the population's errors correlate through the ambiguity "
        "of the specification they were all written from. This is that "
        "argument with a number on it, and the per-port breakdown shows where "
        "it bites:\n\n"
        "    port              split cells   majority right\n"
        "    dc_addr                   837            38.1%\n"
        "    saved_addr                714            33.1%\n"
        "    first_miss_ack            385            33.5%\n"
        "    biu_read                  493            53.5%\n"
        "    biu_write                 448            56.2%\n"
        "    burst                     334            77.2%\n\n"
        "**The three ports carrying most of the disagreement are the three the "
        "majority is most often WRONG about** -- two thirds wrong on the two "
        "address ports. A consensus value taken from this population as an "
        "expected value would be an oracle that is wrong where it speaks most.\n\n"
        "**WHAT THIS DOES NOT TOUCH.** The selection rule does not use the "
        "agreed value; it counts convictions. This bounds the ENSEMBLE idea, "
        "not the minority rule, and it says nothing about whether a bigger "
        "population's majority would do better -- the thirteen-design figure "
        "suggests it might, and that is one measurement on one module."
    )


def the_packaged_pipeline_reproduces_every_recorded_figure() -> str:
    """F2's FREE HALF. F2 proper authors a fresh corpus, which costs model
    calls; everything after authoring is free and had never been run through
    the packaged path -- every recorded number came from a scratch driver.
    """
    return (
        "Driven over k1's real artifacts -- 464 bodies, 7 designs, 348 "
        "testpoints -- through `characterise` -> `refuse_unusable_population` "
        "-> `GateLegs.corpus_path` -> `select` -> `sweep` -> `audit` -> "
        "`Report`:\n\n"
        "     t   checks    span   *audit*   blind   spurious\n"
        "     0      126   63.2%   * 0.0%*   99.9%      33.3%\n"
        "     1      149   72.4%   * 7.4%*   95.4%      28.7%\n"
        "     2      167   78.2%   *13.2%*   70.7%      12.5%\n"
        "     3      171   78.2%   *13.5%*   68.3%      11.3%\n"
        "     4      179   79.3%   *15.1%*   65.9%      10.4%\n"
        "     5      188   80.5%   *14.4%*   54.4%       3.7%\n"
        "     6      201   81.6%   *18.9%*   50.0%      16.0%\n"
        "     7      464   83.9%   *64.4%*    0.0%       0.0%\n\n"
        "plus the bucket profile (ends 389, middle 75) and the "
        "reference-picked sound subset at 163 checks / 77.0% / 0.0% / 56.1%. "
        "**EVERY TARGET ROW MATCHES.**\n\n"
        "**AND THE POPULATION GATE REFUSED, WHICH IS THE POINT.** "
        "`refuse_unusable_population` was written from P1's retraction and it "
        "declines k1's own population -- G off the majority at 86% of split "
        "testpoints. A run that sailed through would mean the gate does not "
        "bind on the population that motivated it. The refusal is recorded and "
        "then overridden EXPLICITLY, because the discipline is 'report the "
        "structure beside it or not at all', not 'never report it'. The "
        "`Report` line carries it inline:\n\n"
        "    201 checks spanning 71 of 87 = 82%, audit 38 = 18.9%, blind "
        "50.0%\n    [population 7 designs, effective 3, top dissent G at 86%]\n\n"
        "**WHAT IS STILL UNEXERCISED.** A1-A3 retain a corpus that no run has "
        "yet produced, and B1's producer has authored nothing. This shows the "
        "SELECTION half of F2 agrees with the record; the AUTHORING half is "
        "untested and is what the paid run would test."
    )


def elicited_alternative_readings_produce_strength_not_difference() -> str:
    """V1, live and paid, run on BOTH authors so the prompt and the model are
    separable.

    Show the author its own prior body and ask for a check that DISAGREES with
    it about scope or demand. It cleared its pre-registered bar by three orders
    of magnitude, and the bar turned out to be gameable by exactly the thing the
    experiment was meant to rule out.
    """
    return (
        "**THE CONTROLLED RESULT: HOLDING THE AUTHOR FIXED AND CHANGING ONLY "
        "THE PROMPT MULTIPLIES FALSE REJECTION BY FOUR.** `gpt-5.6-luna` wrote "
        "the recorded 464-body corpus under the SHIPPED prompt, and `t = 6` of "
        "that corpus audits at 18.9%. The same author under the "
        "alternative-reading prompt audits at **75.0%**.\n\n"
        "Both authors ran the same 30 prompts:\n\n"
        "                                    gpt-5.6-terra   gpt-5.6-luna\n"
        "    authored                             24 of 30       29 of 30\n"
        "    declined as single-reading                  6              1\n"
        "    survive the corpus-path gate               20             24\n"
        "    mean indiscriminacy                     0.319          0.401\n"
        "    mean objection mass                     0.080          0.072\n"
        "    convict ALL SEVEN designs             8 of 20       17 of 24\n"
        "    *audit*                              *9 = 45%*    *18 = 75%*\n\n"
        "against a `t = 6` sample's indiscriminacy of **0.02** and mass of "
        "**0.005**. **The effect is the prompt's, not one model's**, and the "
        "author that wrote the corpus shows it MORE strongly -- 20x the "
        "indiscriminacy and 71% of its bodies convicting every design.\n\n"
        "**THE BAR: new set-level cells > 0. MEASURED: +2,826 (terra) and "
        "+2,767 (luna) over `t = 6`.** The blindness round scored exactly zero "
        "on this metric with a stronger targeting signal. This is not a near "
        "miss in the other direction -- it is the whole denominator.\n\n"
        "**AND THAT IS THE METRIC BREAKING, NOT THE EXPERIMENT SUCCEEDING.** At "
        "every disagreement cell at least one of the two designs IS wrong, so a "
        "check objecting to BOTH designs everywhere closes 100% of cells while "
        "picking no side at all. The triple says what the sets are worth:\n\n"
        "    set                               checks    span   *audit*   blind\n"
        "    t = 6                                201   81.6%   *18.9%*   50.0%\n"
        "    sound subset (REFERENCE-picked)      163   77.0%   * 0.0%*   56.1%\n"
        "    t = 6 + V1 (terra)                   221   81.6%   *21.3%*    0.0%\n"
        "    t = 6 + V1 (luna)                    225   81.6%   *24.9%*    1.0%\n"
        "    V1 alone (terra)                      20   23.0%   *45.0%*    0.0%\n"
        "    V1 alone (luna)                       24   27.6%   *75.0%*    1.6%\n\n"
        "**THE FINDING IS THE SAME ONE V0 FOUND, NOW FOR A TARGETED PROMPT AND "
        "WITH THE AUTHOR CONTROLLED.** Resampling produces strength rather than "
        "semantics; so does asking explicitly for a disagreeing reading. The "
        "author moves along the strictness axis because that is the axis the "
        "request is easiest to satisfy on -- a wider activation and a harsher "
        "demand IS a disagreement about scope and demand, and it is not a "
        "second reading of the sentence.\n\n"
        "**WHAT MUST CHANGE IS D1's BAR.** 'New disagreement cells the SET "
        "reaches' cannot distinguish a complementary check from a blunderbuss, "
        "and the pre-registration should have read *an undominated point on the "
        "TRIPLE*.\n\n"
        "**THE TWO-ARM DESIGN EXISTS BECAUSE I GOT THE FIRST ARM WRONG.** The "
        "terra pass ran because I inspected the gateway catalog with `ms[:10]` "
        "and `gpt-5.6-luna` sits at index 10; I concluded from my own "
        "truncation that it was no longer served, when the 404 that started the "
        "search was the `openai/` prefix in `OPENAI_MODEL`. Re-running on luna "
        "turned a confound I had written into a finding into a control arm, and "
        "the control is what makes the 18.9% -> 75.0% comparison mean "
        "anything.\n\n"
        "**AND THE CONFOUND I WROTE NAMED THE WRONG MODEL ENTIRELY.** This "
        "driver's header calls luna 'the corpus's author'. It is not: see "
        "`the_recorded_corpus_is_subagent_authored_and_half_survivor_pool`. The "
        "recorded bodies were written by Claude subagents, so V1's two arms "
        "compare two gateway models to each other and NEITHER of them to the "
        "author of the corpus V1 is scored against."
    )


def the_control_is_not_a_proxy_for_the_grade_it_is_the_grade() -> str:
    """STEP 2, part 1. Before fitting anything to the control's verdict, check
    that it agrees with the grade it stands in for.

    Scored on all three runs that carry a control, each against golden traces
    driven by ITS OWN stimulus, at each check's own `tp_uids`, over checks live
    on the golden.
    """
    return (
        "**THE CONTROL PREDICTS THE GOLDEN ALMOST EXACTLY, AND THAT IS A "
        "PROBLEM FOR THE PLAN THAT WANTED TO FIT TO IT.**\n\n"
        "    run       live   flagged convict   unflagged convict     lift      z\n"
        "    a2-i2c      74     28 of 29  96.6%    2 of 45   4.4%    21.72x   7.88\n"
        "    d1-i2c      25      5 of  5 100.0%    0 of 20   0.0%       inf   5.00\n"
        "    c1-i2c      72     28 of 32  87.5%    8 of 40  20.0%     4.38x   5.69\n\n"
        "On d1 the flagged set is EXACTLY the golden-convicting set. Across the "
        "three runs the flag finds **61 of the 71** checks the golden falsifies "
        "-- missing 10 -- and flags **5** the golden does not: 66 flags, 92% "
        "precision, 86% recall.\n\n"
        "**SO THE HONESTY CONDITION I WROTE WAS TOO WEAK, AND THIS CORRECTS "
        "IT.** The plan said fitting to the control is 'weaker contamination "
        "than fitting to the audit, not zero'. It is not weaker. A model "
        "recorded in the pipeline's own docstring as scoring 181/181 against "
        "golden RTL is not a proxy for the grade, it IS the grade wearing "
        "another name, and a rule fitted to it is reference-calibrated outright "
        "-- the same class as choosing `t = 0` by reading the audit.\n\n"
        "**TWO CONSEQUENCES, BOTH BINDING.** The held-out grade must be a module "
        "with NO control, which is k1 alone "
        "(`over_strictness_bounded_by = 'witness'`, flagged list empty); and "
        "every figure fitted this way is reported in the CALIBRATED column and "
        "never as a golden-free frontier point.\n\n"
        "**WHAT IT IS STILL GOOD FOR.** It turns 'can any golden-free feature "
        "family predict soundness at all' from a question with one module's "
        "labels into one with ~190 near-ground-truth labels over three runs. A "
        "comprehensive negative there closes the selection line, and nothing "
        "else on the board can close it.\n\n"
        "**AND IT PRICES THE PIPELINE'S OWN CHOICE EXACTLY.** The stage computes "
        "this flag every run and declines to act on it -- 'reported only: the "
        "control may not select which oracles survive' -- because gating on it "
        "tunes the reference model toward the grade transitively. That is the "
        "right call, and the cost of it is now measured: 61 checks the golden "
        "falsifies, known at authoring time, shipped TRUSTED."
    )


def the_rule_does_not_transfer_and_the_second_population_also_has_an_outlier() -> str:
    """F3, live and complete: five i2c designs authored from the specification,
    elaborated, suite-run against c1-i2c's own stimulus, and swept.

    Pre-registered: same direction, similar shape, and the population
    characterised FIRST. If i2c has no dominant dissenter and the precision
    collapses there, the rule is k1's outlier. If i2c ALSO has one, that is a
    fact about how these populations are generated and not a vindication.
    """
    return (
        "**BOTH HALVES OF THE PRE-REGISTRATION FIRED, AND NEITHER FAVOURS THE "
        "RULE.**\n\n"
        "**i2c'S POPULATION ALSO HAS A G.** Five designs written independently "
        "from the same specification by the same author, 331 testpoints, 226 of "
        "them split:\n\n"
        "    pair distance            per-design dissent\n"
        "      d0-d2  65.6%             d0   **80.1%**\n"
        "      d0-d1  58.6%             d2     59.7%\n"
        "      d0-d3  58.6%             d4     46.0%\n"
        "      ...                      d1     35.0%\n"
        "      d1-d3   6.0%             d3     34.1%\n\n"
        "    effective size 4 of 5   clusters {d0} {d1,d3} {d2} {d4}\n\n"
        "The shape is k1's, reproduced on a different module: one design far off "
        "the majority (d0 at 80.1%, k1's G at 78.1%), the largest pair distances "
        "all involving it, and one near-clone pair 6% apart (d1-d3, k1's B/D/E at "
        "6.3-6.6%). `refuse_unusable_population` REFUSES this population, exactly "
        "as it refuses k1's. **Two populations, two outliers: that is a property "
        "of how independent authoring produces designs, not a vindication of a "
        "rule whose precision depends on one.**\n\n"
        "**AND THE PRECISION DOES NOT TRANSFER EVEN SO.** 110 checks, 36 of them "
        "(33%) deciding nowhere on the population, none broken; 53 of 110 = "
        "48.2% convict the reference.\n\n"
        "     t  checks    span   *audit*   blind   spurious\n"
        "     0      18   16.4%   *11.1%*  100.0%      0.0%\n"
        "     1      21   19.1%   *14.3%*   97.3%      0.0%\n"
        "     2      22   20.0%   *18.2%*   97.0%      0.0%\n"
        "     3      23   20.9%   *17.4%*   93.1%      0.0%\n"
        "     4      28   25.5%   *32.1%*   72.6%      0.0%\n"
        "     5      74   67.3%   *71.6%*    1.2%      1.2%\n\n"
        "**`t = 0` audits at 11.1%, not 0%.** On k1 the same threshold over the "
        "same rule gave 126 checks for 126 with a zero. Here it is 2 of 18 -- "
        "with a dominant dissenter present to absorb over-strict checks, which "
        "is the condition the k1 zero was attributed to. So the outlier does not "
        "even explain it: the exactness is k1's, and it is not reproduced on a "
        "second module under the same population shape.\n\n"
        "**EVERY ROW IS DOMINATED** by the reference-picked subset at 77.0% / "
        "0.0% / 56.1%: worse span, worse audit and worse blindness at once. F3 "
        "is a NEGATIVE and is reported as one.\n\n"
        "**WHAT IS NOT A RESULT ABOUT THE RULE, STATED SEPARATELY.** Two of the "
        "five authored designs did not ELABORATE -- d0 assigned ANSI `output` "
        "wires procedurally, d1 re-declared them as `reg`, the same Verilog-2001 "
        "trap in mirror image. Each was given one repair round with ONLY its own "
        "source and its own simulator output, and both then elaborated. That is "
        "plumbing, and it is reported as plumbing: the population is five "
        "designs because a syntax repair made it five, not because five were "
        "written correctly.\n\n"
        "**AND F3 PAID FOR ITSELF IN A DIFFERENT CURRENCY.** Replicating onto a "
        "second population is what exposed `effective_size` measuring shared "
        "dissent rather than clone distance -- see "
        "`population.effective_size_measured_clone_distance_not_shared_dissent`. "
        "A rule validated on one population validates its instruments on one "
        "population too."
    )


def the_recorded_corpus_is_subagent_authored_and_half_survivor_pool() -> str:
    """WHAT THE 464 BODIES ACTUALLY ARE. Every audit figure in this module has
    that corpus underneath it, and until the user asked why F2 came out so bad
    I had two facts about it wrong.
    """
    return (
        "**THE CORPUS HAS NO GATEWAY CALLS IN IT AT ALL.** I recorded, in F2's "
        "and V1's own driver headers, that the 464 bodies were authored by "
        "`gpt-5.6-luna`. Checked: **no script in that scratchpad imports "
        "`model_io`, `ResumePort`, `responses_model` or `openai`, and the whole "
        "tree contains zero `*_meta.json`** -- the file every `make_port` call "
        "writes. Every body was authored by a CLAUDE SUBAGENT reading a "
        "`.prompt.txt`, because the gateway key was under a standing "
        "prohibition for the whole period the corpus was built. The only "
        "gateway calls that have ever touched it are V1's and F2's, from the "
        "session in which the user lifted that prohibition.\n\n"
        "**AND IT IS TWO POOLS, NOT ONE SAMPLE.**\n\n"
        "    family     what it is                                  n   convict\n"
        "    `off`      every body ever written for the 26          350   *83.0%*\n"
        "               requirements no run ever solved,\n"
        "               scavenged off disk and deduped by text\n"
        "    curated    survivors from the 52 requirements          114     ~5%\n"
        "               that WERE solved\n"
        "    -------------------------------------------------------------------\n"
        "    all                                                    464   *64.4%*\n\n"
        "So **64.4% is a blend whose value is set by how many requirements were "
        "never solved**, not a base rate for authoring. Quoting it as the "
        "number a fresh corpus must beat compares an ungated first-draft pool "
        "against a mixture that is three quarters failure history and one "
        "quarter survivors.\n\n"
        "**THE SURVIVOR HALF READS AS PERFECTION AND IS NOT.** The `shipping` "
        "family is 17 bodies over 15 requirements, convicting at **0 of 17**, "
        "which I read as what the shipping prompt produces. E0d authored **34**; "
        "19 requirements' bodies never entered the corpus. Rescoring all 34 raw "
        "responses with the same instrument: **15 of 34 = 44.1% convict, 8 of "
        "34 = 24% decide nowhere.** The zero was the retention, not the prompt.\n\n"
        "**WHAT THIS DOES AND DOES NOT INVALIDATE.** The sweep, the tells, the "
        "blindness and every frontier point are computed WITHIN this corpus and "
        "compared against rows drawn from the same corpus, so they stand. What "
        "falls is every sentence that used 64.4% as an external baseline, and "
        "every attribution of a difference to the author -- including the "
        "confound V1 and F2 each declared, which named the wrong direction."
    )


def a_one_pass_corpus_is_inert_and_selection_cannot_rescue_it() -> str:
    """F2's authoring half, live, on both authors. A fresh corpus built ON
    PURPOSE, gated only by the free structural floors, then selected.

    Pre-registered: the golden-free frontier must reach a point NOT DOMINATED by
    the reference-picked sound subset at 77.0% / 0.0% / 56.1%.
    """
    return (
        "**BOTH ARMS ARE A NEGATIVE.** The first version of this finding also "
        "said the recorded corpus's own author was the worse of the two. That "
        "sentence was wrong twice over and is corrected below.\n\n"
        "34 requirements, 3 draws each, distinct stage labels per draw:\n\n"
        "                                gpt-5.6-terra   gpt-5.6-luna\n"
        "    authored                         99 of 102     102 of 102\n"
        "    DISTINCT bodies                         99            102\n"
        "    duplicate rate                        0.0%           0.0%\n"
        "    **decide nowhere**              **35 = 35%**   **43 = 42%**\n"
        "    survive the corpus-path gate            64             59\n"
        "    whole corpus span                    27.6%          31.0%\n"
        "    whole corpus *audit*               *62.5%*        *89.8%*\n\n"
        "**EVERY THRESHOLD IS DOMINATED.** Luna's `t = 0` is four checks at 50% "
        "audit; terra's is twelve at 33%; the recorded corpus has 126 checks at "
        "`t = 0` auditing at **zero**. Domination is measured against the "
        "reference-picked subset at 77.0% / 0.0% / 56.1%, never against the "
        "corpus base rate, so this verdict does not move under the correction "
        "that follows.\n\n"
        "**THE CORRECTION: 89.8% AND 64.4% ARE NOT THE SAME MEASUREMENT, AND "
        "THE RECORDED CORPUS HAS A DIFFERENT AUTHOR THAN I RECORDED.** Two "
        "errors, both mine, both found by the user asking why F2 was so bad.\n\n"
        "  *The denominators.* 89.8% is 53 of the 59 checks that DECIDE "
        "somewhere; 64.4% is 299 of ALL 464 recorded bodies. Like for like, "
        "luna is **53 of 102 = 52.0%**.\n\n"
        "  *The author.* `f2_corpus.py`'s header states the recorded corpus was "
        "authored by `gpt-5.6-luna`. It was not. **No script in that scratchpad "
        "imports `model_io`, `ResumePort`, `responses_model` or `openai`, and "
        "the tree holds zero `*_meta.json`** -- every one of the 464 bodies was "
        "written by a CLAUDE SUBAGENT from a `.prompt.txt`, under the standing "
        "prohibition on the gateway key. F2 and V1 are the first gateway calls "
        "those prompts ever received.\n\n"
        "**AND THE 464-BODY BASE RATE IS A MIXTURE OF A SURVIVOR POOL AND A "
        "FAILURE POOL.** 350 of the 464 are every body ever written for the 26 "
        "requirements no run ever solved, scavenged off disk and deduped: they "
        "convict at **83.0%**. The other 114 are survivors from 52 requirements "
        "that were solved, at ~5%. 64.4% is the blend, and F2 -- an ungated "
        "first-draft pool -- belongs beside the 83.0%, not beside the blend.\n\n"
        "**THE MATCHED COMPARISON, SAME 34 SHIPPING PROMPTS.** The recorded "
        "`shipping` family reads 0 of 17 convicting, which I took for a rate. It "
        "is a survivor pool: E0d authored 34 and only 15 requirements' bodies "
        "entered the corpus. Rescoring all 34 raw responses with F2's own "
        "instrument:\n\n"
        "    author, same 34 prompts    authored  dead   convict/authored\n"
        "    Claude subagent, 1 draw          34   24%      15 = **44.1%**\n"
        "    gpt-5.6-luna, 3 draws           102   42%      53 = **52.0%**\n"
        "    gpt-5.6-terra, 3 draws           99   35%      40 = **40.4%**\n\n"
        "So terra beats the recorded author and luna trails it by eight points. "
        "**What does not move is the dead rate, 42% against 24%**, and that is "
        "this finding's actual content.\n\n"
        "**THE CAUSE IS INERTNESS, AND IT IS NOT THE SELECTION RULE'S TO "
        "FIX.** Two fifths of a freshly authored corpus decides nothing on any "
        "of seven designs. A check that never decides convicts nobody, so the "
        "rule at low `t` KEEPS it preferentially -- which is why `t = 0` "
        "collapses to four checks rather than filling up with them: the "
        "DECIDES leg drops them first, and what is left is too small to span "
        "anything.\n\n"
        "**WHAT THIS EXPERIMENT ACTUALLY TESTED, STATED NARROWLY.** One pass "
        "per prompt, three draws, **no repair rounds and no staging loop**. A3 "
        "is about which GATES run on the corpus path and says nothing about the "
        "loops, and I ran without them. So this is not evidence that dropping "
        "`correspondence` is wrong; it is evidence that **A1's retention is "
        "necessary and nowhere near sufficient** -- a corpus needs the staging "
        "loop that makes checks decide before there is anything for selection "
        "to select over. The 0.0% duplicate rate across both arms does "
        "independently confirm that per-draw stage labels defeat the "
        "`{stage}_r{round}` collapse.\n\n"
        "**AND THE F2 BAR WOULD HAVE BEEN MISREAD WITHOUT THE AUDIT CEILING.** "
        "The first verdict this driver printed called `t = 7` 'not dominated' "
        "at 31.0% / 89.8% / 1.0% -- undominated only because a corpus objecting "
        "to nearly everything is barely blind. The same 0%-blindness artifact "
        "that broke V1's bar, caught here by refusing any point whose audit "
        "exceeds `t = 6`'s 18.9%."
    )
