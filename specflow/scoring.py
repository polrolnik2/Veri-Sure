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


def a_golden_free_rule_transfers_across_modules_and_is_still_one_knob() -> str:
    """STEP 2b, complete. Fit a golden-free rule to the CONTROL label on three
    i2c runs, transfer it to k1 -- the only module with no control -- and grade
    it on k1's golden audit.

    Pre-registered: >= 3x in training, >= 2x on the held-out run with no refit,
    AND an undominated triple. Two of three clauses clear.
    """
    return (
        "**THE LIFT BARS CLEAR AND THE TRIPLE BAR FAILS, SO STEP 2b IS A "
        "NEGATIVE -- BUT THE FIRST TWO CLAUSES ARE THE BEST RESULT THIS "
        "QUESTION HAS HAD.**\n\n"
        "**Nine golden-free features rank the control label the same way on all "
        "three runs.** AUC per run (0.50 = nothing):\n\n"
        "    feature            a2      d1      c1    mean\n"
        "    mass             0.802   0.933   0.803   0.846\n"
        "    placement        0.766   0.924   0.747   0.812\n"
        "    dissent_weighted 0.771   0.876   0.724   0.790\n"
        "    count            0.771   0.871   0.723   0.788\n"
        "    n_lines          0.704   0.886   0.634   0.741\n\n"
        "**Leave-one-run-out, one feature and one threshold transfers.**\n\n"
        "    held out    train    HELD OUT       z   rule\n"
        "    a2-i2c      4.67x       3.53x    4.14   mass > 0.0426\n"
        "    d1-i2c      4.64x      10.86x    2.98   mass > 0.01964\n"
        "    c1-i2c      6.83x       3.30x    3.71   mass > 0.02118\n\n"
        "The same feature is chosen in every fold and the thresholds sit in a "
        "narrow band. **A depth-2 tree transfers WORSE** (6.11x, 7.56x, 1.84x -- "
        "one fold below the bar), which is P4's composition negative again: a "
        "composition that cannot beat its best component is reported as a "
        "negative and the component is used alone.\n\n"
        "**AND `count` -- THE STATISTIC THE SHIPPED RULE ALREADY USES -- DOES AS "
        "WELL OR BETTER** on every fold: 3.77x / inf / 9.96x against mass's "
        "3.53x / 10.86x / 3.30x. So this is not a new rule; it is the shipped "
        "one validated against a near-ground-truth label on three independent "
        "oracle sets.\n\n"
        "**THE HELD-OUT MODULE CLEARS TOO.** `mass > 0.0207`, fitted entirely on "
        "the i2c runs and never shown k1, on k1's golden audit: **6 of 11 "
        "convict against 1 of 18 -- 9.82x, z = 2.99.** That is the first "
        "cross-module transfer in this investigation; P5's model was 3.06x and "
        "per-module.\n\n"
        "**THEN THE TRIPLE KILLS IT.** On k1's 2,836 disagreement cells:\n\n"
        "    set                                n    span*   *audit*   blind\n"
        "    all 29 live (the frozen set)      29    33.3%    *24.1%*   37.8%\n"
        "    mass <= 0.0207 (fitted on i2c)    18    20.7%     *5.6%*   90.6%\n"
        "    count == 0 (t = 0, shipped)        8     9.2%     *0.0%*  100.0%\n\n"
        "Audit 24.1% -> 5.6% costs **53 points of blindness**. That is "
        "`soundness_and_blindness_are_one_knob` exactly: the rule sits ON the "
        "selection frontier, not off it. Contrast the control flag, which bought "
        "48.6% -> 19.0% for **0.7** points -- the control is a different knob "
        "and `mass` is not.\n\n"
        "*span is over k1's 87 requirements and a 30-check frozen set caps at "
        "34.5%, so it is NOT comparable to the 77.0% target row; no domination "
        "claim is made on that axis. Audit and blindness are comparable, and on "
        "those the set is dominated.*\n\n"
        "**A METHOD DEFECT WORTH KEEPING.** The first threshold search maximised "
        "LIFT with a floor of five rows a side. It reported INFINITE training "
        "lift on every fold and transferred at 0.00x, 'inf' (z = 0.72) and "
        "2.74x (z = 1.37) -- and I nearly recorded that as the negative. "
        "Maximising lift is degenerate: it isolates two flagged checks and calls "
        "it a rule. Youden's J with a floor that is a FRACTION of the fold "
        "cannot be gamed that way, and it is what produced the table above. The "
        "AUC read is what exposed it, because it needs no threshold at all."
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


def the_whole_oracle_stage_loss_on_two_frozen_sets_is_the_faithfulness_gate() -> str:
    """E0, run offline on the two frozen sets that survived the data loss.

    Step 2 of the protocol was to reproduce the recorded verdicts through the
    real `_dispositions` rather than re-derive them arithmetically, so the
    counts below come out of the shipped code path.
    """
    return (
        "**EVERY DISCARD IN BOTH SETS IS CORRESPONDENCE.** Not one "
        "`malformed:`, not one `vacuous:`, not one `unreached:`.\n\n"
        "    set            considered  TRUSTED  discarded  reasons\n"
        "    affected23             23       15          8  7 off-target, 1 not-assertable\n"
        "    reauthor43             43       24         19  19 off-target\n\n"
        "Both reproduce through `_dispositions` exactly -- **23 of 23 and 43 of "
        "43** -- so this is the code's own verdict, not arithmetic on a table. "
        "Under the plan's rule, where a faithfulness reason becomes a label and "
        "only `well_formed`, a replay break and `DEAD_ORACLE` still block, "
        "**TRUSTED goes 15 -> 23 and 24 -> 43, and NOTHING remains blocked**.\n\n"
        "**AND 63 REPAIR ROUNDS WERE SPENT ON THE CHECKS IT THEN DISCARDED** -- "
        "18 on affected23 (median 3, max 4) and 45 on reauthor43 (median 2, max "
        "5). That is paid authoring work, gated out after the fact by a "
        "reviewer reading two texts.\n\n"
        "**WHAT E0 CANNOT SAY, AND THE LIMIT IS THE FINDING.** Liveness "
        "verdicts are recorded for **15 of 15** and **24 of 24 kept** checks and "
        "**0 of 8 and 0 of 19 discarded** ones; `oracles` holds only the TRUSTED "
        "bodies; neither set carries a control or variants. So the admission "
        "**cannot be priced from these artifacts at all** -- not its audit, not "
        "its blindness, not even whether the admitted checks would have run. "
        "**The artifact retains survivors only, at exactly the point a decision "
        "about discarding needs the discarded.** `_retain`/`CorpusBody` was "
        "built to close this and both sets predate it.\n\n"
        "**SCOPE.** Two sets, one module family, no control on either. It "
        "establishes what the gate removed and what the artifact kept. It "
        "establishes nothing about whether removing it was right."
    )


def placement_selected_a_blunderbuss_set_and_the_blindness_number_was_polarity_uncorrected() -> str:
    """A RETRACTION of the best triple on this board, derived from the recorded
    description rather than re-measured -- the 464-body corpus is gone.

    `objection_placement_buys_closure_more_cheaply_than_the_count` reports
    `placement < 0.0017` at span 69.0% / audit 15.9% / **blind 20.8%**, against
    `t = 6`'s 50.0% and the reference-picked subset's 56.1%. It was cited in the
    plan as the reason selection is the endpoint.
    """
    return (
        "**THE SIGN IS THE OPPOSITE OF THE RULE.** The shipped tell is\n\n"
        "    placement = share of SPLIT testpoints spoken on\n"
        "              - share of AGREED testpoints spoken on\n\n"
        "so it runs **+1** for a check objecting only where the designs differ, "
        "**-1** for one objecting only where they agree, and **0 for a check "
        "objecting EVERYWHERE or NOWHERE**. Verified directly on a two-design "
        "shape: +1.0000, -1.0000, 0.0000. A completeness leg wants the HIGH "
        "end, and `placement < 0.0017` keeps the low end.\n\n"
        "**WHAT THAT SET IS MADE OF, FROM ITS OWN DESCRIPTION.** 151 checks = "
        "**all 126 of `t = 0`**, which convict nobody and therefore score 0 by "
        "objecting to nothing, plus 25 of which **24 convict all seven "
        "designs** and therefore score ~0 by objecting to everything. The "
        "threshold is not selecting for landing on disagreements; it is "
        "selecting for **symmetric** placement, which silence and a "
        "blunderbuss both have.\n\n"
        "**AND THAT IS WHY THE 20.8% DOES NOT SURVIVE POLARITY CORRECTION.** "
        "Set blindness there is scored as 'the share of disagreement cells "
        "where NO check objects to EITHER design'. A check convicting BOTH "
        "sides of a pair satisfies that and **separates neither** -- it closes "
        "the cell on paper and adjudicates nothing. `t = 0` alone is 99.9% "
        "blind; the 24 blunderbusses separate no pair; so under "
        "`variety.separates` the set closes essentially nothing `t = 0` did "
        "not. **The 20.8% is the un-corrected predicate, and objecting to both "
        "sides is exactly how a blindness score was gamed once before on this "
        "project.**\n\n"
        "**CONSEQUENCES.** `Ruleset.min_placement` ships with the sign the tell "
        "actually has and no default threshold, because the recorded plateau "
        "(0.0005-0.003) belongs to the other direction and does not transfer. "
        "The claim that selection is the endpoint rested on this row and now "
        "rests on nothing measured: `t = 6` at 40.4% blind is the best "
        "SURVIVING golden-free point, and it costs 18.9% audit.\n\n"
        "**SCOPE, and it is the weak part.** This is an inference from the "
        "recorded composition of the set -- 126 + 24 convicting all seven -- "
        "not a re-measurement, because the corpus it was computed over did not "
        "survive. What is directly verified is the tell's sign and that a "
        "both-sides conviction closes a cell under one predicate and not the "
        "other. **Re-scoring that set under polarity correction is the "
        "experiment that would settle it, and it needs the corpus back.**"
    )


def the_faithfulness_gate_kept_the_over_strict_and_rejected_the_sound() -> str:
    """E2, run live on E3's requirements. Driver: `docs/evidence/e2_admission.py`.

    E0 established this could not be priced from the surviving artifacts --
    liveness exists for 15/15 and 24/24 KEPT checks and 0/8 and 0/19 DISCARDED
    ones, and only TRUSTED bodies are stored -- so the rejected checks were
    generated fresh and scored against the nine spec-derived designs, with the
    control supplying the audit column last and feeding nothing.
    """
    return (
        "Correspondence rejected **20 of 25** authored oracles.\n\n"
        "    arm         checks   convict the control   blind\n"
        "    KEPT             5          80.0% (4/5)    23.1%\n"
        "    ADMITTED        20          15.0% (3/20)   87.6%\n"
        "    UNION           25          28.0% (7/25)   23.1%\n\n"
        "**THE GATE KEPT 1 OF THE 18 SOUND CHECKS AND 4 OF THE 7 UNSOUND "
        "ONES.** Not neutral with respect to soundness -- anti-selective. The "
        "pre-registered branch was 'audit no worse on the admitted set => the "
        "gate was discarding at random'; the measured answer is stronger and in "
        "the same direction.\n\n"
        "**AND THE ADMITTED CHECKS ADD NO DISCRIMINATION, WHICH IS THE OTHER "
        "PRE-REGISTERED BRANCH ARRIVING AT THE SAME TIME.** The union is 23.1% "
        "blind and kept-only is 23.1% blind: the twenty admitted checks close "
        "**not one additional cell**. They are 87.6% blind on their own. They "
        "are sound BY SILENCE, so the span they buy is real and the "
        "constriction they buy is nothing.\n\n"
        "**THE UNION'S 28% IS A DENOMINATOR, NOT AN IMPROVEMENT, and must not "
        "be read as one.** Rejections union, so a suite containing the four "
        "over-strict kept checks rejects the control whatever else is admitted. "
        "Admission dilutes the RATE and removes none of them. The only way that "
        "28% becomes a real gain is if the four are dropped, and dropping them "
        "needs the control -- which is barred.\n\n"
        "**A RED FLAG ON THE GATE ITSELF: 80% REJECTION AGAINST A CALIBRATION "
        "OF 4.3%.** `correspondence` records 'over 70 frozen oracles it rejects "
        "3' and '2 of the first 40' live. Twenty of twenty-five is nearly twenty "
        "times that. Something about this run is outside its calibration -- the "
        "hand-written contract, `gpt-5-mini` doing both the authoring and the "
        "reviewing, or the window defect E3 measured at 65.9%, which makes point "
        "checks that a reviewer would rightly call off-target. **The direction "
        "of the finding does not depend on which, but the magnitude does.**\n\n"
        "**SCOPE.** 25 requirements, one module, one model authoring and "
        "reviewing, seven synthetic testpoints, n = 5 in the kept arm. The kept "
        "arm being 4-of-5 unsound is five checks, not a rate."
    )


def a_run_retains_one_body_per_requirement_so_selection_has_no_choice() -> str:
    """E0b + E2 driven through the SHIPPED `run_oracle_stage`, both arms on
    identical inputs. Driver: `docs/evidence/e0b_stage_both_arms.py`.

    E2 had been measured by hand-assembling `run_oracle_gen` + `correspondence`;
    this is the code path a run actually takes, and because the stage retains a
    corpus it answers E0b at the same time.
    """
    return (
        "    arm        TRUSTED  labels  ABANDONED  NOT_ASSERTABLE  ORACLE_INVALID\n"
        "    gated            6       0          7               1               6\n"
        "    demoted         14      16          6               0               0\n\n"
        "**DEMOTING TAKES TRUSTED 6 -> 14 OF 20**, and the 16 labels carry every "
        "objection that used to discard. `NOT_ASSERTABLE` and `ORACLE_INVALID` "
        "go to zero because both were faithfulness grounds; the six remaining "
        "ABANDONED are the mechanical ones.\n\n"
        "**E0b: THE CORPUS IS ONE BODY PER REQUIREMENT.** 26 bodies over 20 "
        "requirements gated, 22 over 20 demoted -- **median depth 1, max 2** in "
        "both arms. `placement` selected 151 from 464 bodies over 87 "
        "requirements, a median near five. **So a run gives selection nothing to "
        "choose from per requirement**: at depth 1 every filter is a delete, "
        "which is the pre-registered 'binding constraint' outcome and the "
        "clearest statement yet of why volume is the lever and filtering is not."
        "\n\n"
        "**AND THE RUN EXPOSED A DENOMINATOR DEFECT, WHICH IS NOW FIXED.** "
        "`considered()` read **3** where it should read 13. The abandonment loop "
        "iterated the whole `normalized` map rather than the requirements the "
        "stage was given, so with 20 requirements and 41 normalized forms "
        "`abandoned` collected 17 entries of which **10 had no disposition at "
        "all** -- and `considered()` subtracts `len(abandoned)`, so the "
        "denominator came out more than four times too small and every rate "
        "over it was inflated. A full run has `normalized == requirements` and "
        "never sees it; an `only`-scoped round does. Guarded, with the "
        "invariant pinned: everything `abandoned` names must be something "
        "`dispositions` names too.\n\n"
        "**SCOPE.** 20 requirements, one module, `gpt-5-mini` authoring and "
        "reviewing, `repair_attempts = 1` -- and repair attempts are exactly "
        "what would deepen a corpus, so median 1 at one attempt is not median 1 "
        "at the default of two. The direction is what stands: a run retains "
        "nothing like the depth the recorded selection results were computed "
        "over."
    )


def my_own_driver_skipped_the_indirect_pass_and_lost_half_the_sample() -> str:
    """A defect in the MEASUREMENT, not the pipeline, caught by reading the
    abandonment reasons E1's instrumentation had just made visible.

    `integration.py` normalizes in TWO passes -- `run_normalize_fanout` then
    `resolve_indirect`. The E3 and E2 drivers called only the first.
    """
    return (
        "**19 OF 20 ABANDONMENTS IN THE GATED ARM WERE 'no observation route "
        "found'**, which fires when a requirement has neither an observable "
        "port nor an indirect route. 52 of the 115 normalized forms (45%) have "
        "no observable port, and the pass that gives those a route is exactly "
        "the one I did not call. **AND ALL 52 STATE AN "
        "`unobservable_reason`** -- 52 of 52, not a subset -- which is precisely "
        "the field `resolve_indirect` consumes, so every one of them was an "
        "input the pass was waiting for. Replayed offline by "
        "`docs/evidence/e2_why_abandoned.py`, which reproduces the run's own "
        "seeded sample and returns 19 + 1 = the 20 the gated arm recorded. "
        "The `_unreached` guard agreed: 18 of 18 "
        "silenced requirements reported 'nothing was attempted', because there "
        "was no route to stage.\n\n"
        "**SO HALF THE SAMPLE WAS LOST TO A MISSING PASS, NOT TO THE "
        "PIPELINE.** The indirect pass is recorded recovering 15 of 18 "
        "conceding requirements (83%) with a real port AND route, and "
        "`resolve_indirect` writes those ports into `observable`, so those 19 "
        "would mostly not have been blind at all.\n\n"
        "**WHAT IT DOES AND DOES NOT INVALIDATE.** Both arms of E2 ran the same "
        "omission, so the gated-vs-demoted COMPARISON survives -- the defect is "
        "common-mode. What falls is every ABSOLUTE span figure from these runs: "
        "13 of 40 gated is not the module's span, it is the span of a run "
        "missing its second normalization pass. E0b's corpus-depth median is "
        "unaffected (it counts bodies per requirement among those that reached "
        "authoring at all), and E3's window residual is unaffected because "
        "`resolve_indirect` writes `observable`, `observed_via`, "
        "`unobservable_reason` and `activated_via` and never touches "
        "`activation.windowed`.\n\n"
        "**HOW IT WAS CAUGHT, which is the part worth keeping.** Not by "
        "reviewing the driver -- by reading the abandonment reasons, which only "
        "became readable when E1 threaded `unreached_silenced` and the "
        "abandonment breakdown into the artifact earlier the same session. The "
        "instrumentation found a defect in the experiment that was built to use "
        "it."
    )


def the_indirect_pass_recovers_91_percent_and_the_residue_is_not_a_gate() -> str:
    """Two questions that look like one: is the abandonment recoverable, and is
    it a faithfulness judgment? Measured, the answer differs for each part.

    `no observation route found` fires when a normalized form has neither an
    observable port nor an indirect route -- normalization was asked which port
    shows this requirement and answered "none". That is a model reading prose,
    so the suspicion that it is a faithfulness gate is the right suspicion.
    Both normalizations are on disk (`normalized-direct-only.json` and
    `normalized-all.json`) and `e2_why_abandoned.py` replays both.
    """
    return (
        "**THE INDIRECT PASS RECOVERS 48 OF 53 = 91%**, from the rerun's own "
        "log: `indirect pass: blind 53 -> 5 (recovered 48)`. That is above the "
        "83% route-recovery already on record. Over the whole module the "
        "abandonment grounds go\n\n"
        "    direct pass only      52 no route  +  3 no discrimination  = 55\n"
        "    after resolve_indirect  5 no route  +  2 no discrimination  =  7\n\n"
        "and on the seeded 40-requirement sample, 20 -> 3.\n\n"
        "**FOR THE 48 THAT RECOVERED, IT WAS A FAITHFULNESS ERROR IN THE FULL "
        "SENSE.** A model judged 'nothing observes this', the judgment "
        "terminally abandoned the requirement out of numerator AND denominator, "
        "and it was overturned nine times in ten by asking again with more "
        "information. A blocking claim refuted at that rate is the "
        "miscalibration this tree has paid for twice. The saving grace is that "
        "the pipeline already carries its own refutation -- `resolve_indirect` "
        "is part of `integration.py` and MY DRIVER DID NOT CALL IT. The defect "
        "was in the measurement, and the gate it appeared to expose is a gate "
        "the pipeline does not actually run unrefuted.\n\n"
        "**FOR THE RESIDUAL 5, IT IS NOT.** Four say in their OWN restated text "
        "that they impose no requirement -- 'Implementation details:' and "
        "'Processing Flow:' are headings, '6.' and '11.' are bare list-item "
        "markers -- and the fifth is the module's input port declaration list. "
        "There is nothing to observe because they assert nothing. Probes do not "
        "help them either: probes name internal STATE so a state-dependent "
        "activation becomes expressible, and these have no behaviour to be "
        "stateful about.\n\n"
        "**AND THE OBVIOUS DENOMINATOR FIX IS ONE THE CODEBASE ALREADY "
        "REFUTED, which is why it is recorded here.** S1's `unit_kind` "
        "separates them perfectly -- 4 of 4 scaffolding, 0 of 96 behavioural -- "
        "so using it to shrink the span denominator is the tempting move. "
        "`s1_classify` forbids it on measured grounds: `unit_kind` is 'ADVISORY "
        "AND NEVER A FILTER... A heading classified scaffolding still becomes a "
        "requirement and still goes downstream -- it will fail to yield an "
        "oracle, and that is where the fact belongs. The previous design "
        "dropped it here instead, silently: 49 of n3-i2c's 168 units produced "
        "nothing.' It is also MODEL-ASSIGNED, so filtering on it would put a "
        "faithfulness judgment in the denominator, which is the worst place "
        "for one. The oracle-stage abandonment IS the intended destination.\n\n"
        "**WHAT SURVIVES IS A FLOOR, NOT A FIX.** Of the 40 sampled, 4 are "
        "non-behavioural by S1's advisory read (3 interface, 1 scaffolding) and "
        "2 are residually unroutable. So roughly 5% of the span denominator can "
        "never yield a check and no authoring or selection lever beats it. "
        "Report it as a known floor; do not subtract it."
    )


def normalization_repeats_its_decisions_and_not_its_prose() -> str:
    """Two runs of the E2 driver over the same 115 requirements, same contract,
    same direct-pass inputs. Nothing had ever measured how much of normalization
    repeats, so nothing knew whether a difference between two runs was a result
    or a draw. Replayed by `e3c_normalize_reproducibility.py` from two kept
    samples; zero model calls.
    """
    return (
        "**THE TEXT MOVES AND THE DECISION DOES NOT.**\n\n"
        "    forms differing in activation/expectation/observable/observed_via\n"
        "                                     88 of 115   77%\n"
        "      observed_via                   84          73%\n"
        "      activation                     64          56%\n"
        "      expectation                    59          51%\n"
        "      observable                     18          16%\n"
        "    the UNROUTABLE set                1 of 115    0.9%  (REQ-0005)\n"
        "    indirect pass recovered          48, then 47 of 53\n\n"
        "**SO THE SPLIT IS THE FINDING.** A restatement that rewords the "
        "activation and keeps the port is a different PROMPT and the same "
        "DECISION. `observable` and the unroutable set are what anything "
        "downstream branches on, and they are the two that barely move -- one "
        "requirement in 115. The prose an author reads is different three times "
        "in four.\n\n"
        "**WHAT IT LICENSES AND WHAT IT DOES NOT.** It licenses treating the "
        "abandonment census as stable: 'no observation route found' is a "
        "reproducible verdict, so the 52 -> 5 recovery is a property of the "
        "pipeline and not of a draw. It does NOT license reading small "
        "differences in span, audit or blindness between two runs as effects, "
        "because the authoring prompt differs on 77% of requirements and no "
        "run-to-run interval has ever been computed for those figures. Every "
        "triple in this directory is ONE SAMPLE.\n\n"
        "**AND IT IS NOT A CALL-LEVEL RETEST.** Both passes re-ran, so this is "
        "compound variance over `run_normalize_fanout` and `resolve_indirect` "
        "together, which is the right quantity for 'does re-running the "
        "pipeline give the same forms' and the wrong one for 'is one call "
        "deterministic'. An earlier attempt of mine to read round-1 vs round-2 "
        "correspondence verdicts as a retest was withdrawn for exactly this "
        "reason: the normalized form fed to round 2 had itself changed, so the "
        "input was not held fixed and the flip rate measured nothing."
    )


def correspondence_costs_half_the_stage_and_its_label_predicts_nothing() -> str:
    """E2 runs correspondence in BOTH arms so the arms differ only in whether
    its verdict blocks. That keeps the comparison clean and it keeps the bill.
    Measured on the direct-only unbiased run.
    """
    return (
        "**THE COST IS IDENTICAL IN BOTH ARMS AND IT IS ABOUT HALF THE "
        "STAGE.**\n\n"
        "    gated    80 correspondence calls   94 oracle calls   46%\n"
        "    demoted  80 correspondence calls   66 oracle calls   55%\n\n"
        "**AND IN THE DEMOTED ARM IT BUYS ALMOST NOTHING.** Repair is driven by "
        "`rejected`, so demoting the verdict to a label also removes the repair "
        "it used to force: 21 requirements repaired and 35 repair entries in "
        "the gated arm, against **2 requirements and 4 entries** demoted. The "
        "29 labels block nothing and rewrite almost nothing.\n\n"
        "**THE LABEL DOES NOT PREDICT CONVICTING THE CONTROL.**\n\n"
        "    labelled by correspondence   4 of 9 deciding convict   44%\n"
        "    unlabelled                   3 of 6 deciding convict   50%\n\n"
        "No signal, and what there is points the wrong way. **n IS 15 DECIDING "
        "CHECKS**, so this cannot separate 44% from 50% and is not offered as "
        "an effect -- it is offered as the absence of a large one, which is all "
        "that is needed to say the label is not earning 55% of a budget.\n\n"
        "**THE ARM THE EXPERIMENT IS MISSING.** Gated and demoted both RUN "
        "correspondence. The configuration that tests whether it is worth "
        "running -- correspondence OFF, `want_correspondence=False` -- was "
        "never run, so E2 measures what the gate costs and not what the "
        "instrument costs. It should have been a third arm.\n\n"
        "**AND THE TWO ARMS DIFFER IN MORE THAN GATING, which weakens the "
        "clean reading.** 21 repairs against 2 means the gated arm's checks "
        "have been rewritten far more, so 'same checks, gate on and off' is not "
        "what was compared. The span difference is between a heavily repaired "
        "set and a barely repaired one."
    )


def span_went_to_92_percent_and_the_set_constricted_no_harder() -> str:
    """Two things at once: a replicate that dwarfs the effect it was measuring,
    and a quantity that did not move when span nearly doubled.

    Runs 2 and 3 are IDENTICAL configurations -- same driver, same seed, same
    115 requirements, both calling `resolve_indirect`. Run 1 is the direct-only
    driver and is not a replicate of either.
    """
    return (
        "**THE REPLICATE. Same code, same seed, same inputs, two runs:**\n\n"
        "                  run 2      run 3\n"
        "    gated         13 of 40   20 of 40\n"
        "    demoted       21 of 40   37 of 40\n"
        "    demotion gain +8         +17\n\n"
        "The BASELINE moved 7 requirements and the TREATMENT moved 16, on "
        "nothing but a re-run. The demotion effect is positive both times and "
        "**its magnitude is not estimable from two samples** -- so `+8 of 40` "
        "as I first reported it, and `+17` as it would be tempting to report "
        "now, are both single draws. This is the same variance "
        "`normalization_repeats_its_decisions_and_not_its_prose` measured "
        "upstream: 77% of the forms an author reads differ between these two "
        "runs.\n\n"
        "**AND SPAN REACHED 92.5% WITHOUT BUYING CONSTRICTION.** The triple on "
        "the frozen sets, 9 spec-derived designs, the control, 445 cells:\n\n"
        "                     span     decide  eff  audit   blind   accepts\n"
        "    run 1 kept       32.5%     9       7   55.6%   21.6%   0 of 9\n"
        "    run 1 union      52.5%    15       9   46.7%   11.5%   0 of 9\n"
        "    run 3 kept       50.0%     7       6   28.6%   31.9%   0 of 9\n"
        "    run 3 union      92.5%    14       9   50.0%   15.5%   0 of 9\n\n"
        "**`effective_size` IS 9 IN BOTH UNIONS.** The raw set went from 21 "
        "checks to 37 -- a 76% increase -- and the number of DISTINCT verdict "
        "vectors did not move. `decide` barely moved either, 15 to 14. So of 37 "
        "TRUSTED checks, 14 decide anything on this population and they collapse "
        "to 9 behaviours. The plan's rule that a check count may never stand in "
        "for `effective_size` is what makes this visible, and this is the case "
        "it was written for: **span can be pushed from 32% to 92% with the "
        "constriction power of the set unchanged.**\n\n"
        "**EVERY SET STILL ACCEPTS 0 OF 9 DESIGNS**, at audit 28.6% to 71.4%. "
        "That is over-constriction throughout, so none of these blindness "
        "numbers describe constriction TOWARD a class -- E4b measured that "
        "stall directly and it has not been escaped.\n\n"
        "**WHAT CANNOT BE CONCLUDED, and I concluded it once already.** From "
        "run 1 I reported 'audit on the admitted set is BETTER, not worse' "
        "(33.3% against 55.6%). Run 3 reverses it exactly: admitted 71.4% "
        "against kept 28.6%. With 7 deciding checks per group neither sample "
        "separates anything, and the two disagree in direction. **E2's "
        "pre-registered audit branch is therefore unresolved, not answered.** "
        "Runs 1 and 3 also differ in normalization correctness as well as in "
        "draw, so the triple comparison is confounded; only the span replicate "
        "(runs 2 and 3) is clean.\n\n"
        "**WHAT THE EXPERIMENT NEEDS IS REPLICATES, NOT ANOTHER LEVER.** No "
        "figure in this directory carries an interval, and the spread here is "
        "larger than most effects claimed against it."
    )


def the_population_refutes_the_over_strict_checks_for_free() -> str:
    """The first change this session that improves a core metric rather than
    measuring one. `variety.refuted_by_the_population`, scored by
    `e2d_refutation.py` on both arms of the unbiased run.
    """
    return (
        "**THE RULE.** A check convicting EVERY spec-admissible design has "
        "convicted the correct design too, unless the specification is "
        "unsatisfiable. The specification admits at least seven equivalence "
        "classes; a check that rejects all of them has rejected the class the "
        "right answer is in. The argument is logical, not statistical, and the "
        "instrument reads only spec-derived designs -- there is no parameter a "
        "reference could arrive through.\n\n"
        "**MEASURED ON BOTH ARMS. The control column is computed LAST and feeds "
        "nothing.**\n\n"
        "    gated (20 TRUSTED, 8 decide)\n"
        "      all                         eff 5  audit 25%  blind 31.9%  accepts 0\n"
        "      drop refuted (2)            eff 4  audit  0%  blind 31.9%  accepts 5\n"
        "      ceiling, reference-picked   eff 4  audit  0%  blind 31.9%  accepts 5\n\n"
        "    demoted (37 TRUSTED, 14 decide)\n"
        "      all                         eff 9  audit 50%  blind 15.5%  accepts 0\n"
        "      drop refuted (5)            eff 8  audit 22%  blind 15.5%  accepts 0\n"
        "      ceiling, reference-picked   eff 6  audit  0%  blind 31.9%  accepts 5\n\n"
        "**ON THE GATED ARM THE GOLDEN-FREE RULE REACHES THE REFERENCE-PICKED "
        "CEILING EXACTLY** -- same checks dropped, same audit, same blindness, "
        "same accepted set. Selecting on the control is barred because it tunes "
        "the suite toward the held-out grade; here the population alone found "
        "the same answer.\n\n"
        "**AND IT IS FREE, NOT A TRADE.** Blindness does not move on either "
        "arm. That is structural rather than lucky: a check convicting both "
        "sides of a pair SEPARATES neither, so `separates` is False on every "
        "cell it touches and removing it cannot open a closed one. The test "
        "`test_refutation_removes_no_separation` pins exactly that.\n\n"
        "**THE ACCEPTED SET STOPS BEING EMPTY**, which nothing else this "
        "session managed: 0 of 9 designs to 5 of 9 on the gated arm. Every "
        "triple reported before this was measured on a set that rejected the "
        "entire design space, where blindness describes constriction past "
        "everything rather than toward a class. 5 of 9 is under-constricted and "
        "it is a starting point that exists.\n\n"
        "**PRECISION 7 OF 7, RECALL 7 OF 9, AND n IS 7.** Every refuted check "
        "convicts the control; the demoted arm leaves 2 control-convictors "
        "standing that convict 5 and 8 of 9 rather than all 9. So the rule is "
        "sufficient and not necessary, and with seven positives these rates "
        "carry no useful interval. What does not depend on n is the blindness "
        "column, which is an identity.\n\n"
        "**WHAT IT DOES NOT DO YET.** It is not wired into `run_oracle_stage`, "
        "which measures liveness against a single WITNESS and has no population "
        "parameter. Adding one would create an argument a normal run cannot "
        "fill -- the nine designs here are an experiment artifact, not a "
        "pipeline product -- so the instrument lives where the population does "
        "and the stage is left alone. The `max_convictions` leg in `population` "
        "expresses the same filter for a caller that HAS a population; what was "
        "missing was the measurement that its weakest non-trivial setting is "
        "free."
    )


def every_requirement_gets_one_body_and_only_repair_adds_more() -> str:
    """Corpus depth, measured on four frozen sets, and the contradiction it
    exposes in the admission plan.
    """
    return (
        "**GENERATION PRODUCES EXACTLY ONE BODY PER REQUIREMENT. ALL DEPTH "
        "BEYOND ONE IS REPAIR.**\n\n"
        "    run 3 gated     40 generate + 12 repair = 52   median 1  max 2\n"
        "    run 3 demoted   40 generate +  0 repair = 40   median 1  max 1\n"
        "    run 1 gated     40 generate + 14 repair = 54   median 1  max 2\n"
        "    run 1 demoted   40 generate +  1 repair = 41   median 1  max 2\n\n"
        "`fanout=True` does not fan out per requirement; it parallelises across "
        "them. So the corpus a run can offer selection is one body per "
        "requirement plus whatever repair happened to produce, capped by "
        "`max_repairs` -- 1 in this driver, hence max depth 2.\n\n"
        "**AND THAT CONTRADICTS THE PLAN'S SPINE.** The plan has admission "
        "'enlarge the pool by 35-44%' so that selection has something to choose "
        "from. Admission enlarges the TRUSTED SET and SHRINKS THE CORPUS: "
        "repair is driven by `rejected`, demotion stops the gates rejecting, so "
        "the demoted arm repairs 1 requirement instead of 18 and its corpus "
        "falls from 52 bodies to 40 with **max depth 1 -- literally no "
        "alternative body for any requirement**. The span lever removes the "
        "only mechanism producing depth, and E0b's pre-registration fires: 'a "
        "run median of 1 means selection has nothing to choose from per "
        "requirement'.\n\n"
        "**RAISING `max_repairs` IS DEPTH OF THE WRONG KIND.** A repair body is "
        "a revision under an instruction to be more precise, and `_decides` "
        "records what that instruction does: of the rejected checks whose "
        "verdict moved across repair, six went from convicting to ABSTAINING "
        "and three from passing to abstaining -- nine checks that stopped "
        "deciding. A corpus of narrowing revisions is not a corpus of "
        "alternative readings.\n\n"
        "**RE-NORMALIZATION LOOKS LIKE THE GENERATOR NOBODY TRIED, AND THE "
        "EVIDENCE IS CONFOUNDED.** Normalization repeats its decisions and not "
        "its prose -- 77% of forms differ between two same-config runs while "
        "the routing decision moves on 1 of 115. Comparing the 20 shared "
        "TRUSTED bodies across two runs:\n\n"
        "    byte-identical        0 of 20 =   0%\n"
        "    median similarity     0.07\n"
        "    resampling one prompt, recorded:  69% IDENTICAL\n\n"
        "Different prose is a different ANCHOR, which is exactly what "
        "resampling fails to vary -- but **these two runs differ in "
        "normalization CORRECTNESS as well as in draw** (direct-only against "
        "`resolve_indirect`), so the comparison is confounded and this is not "
        "yet a lever. The clean test is two IDENTICAL-config runs with both "
        "sets frozen, comparing bodies; run 2's freeze failed on drift and its "
        "bodies were lost, which is the only reason it has not been done."
    )


def s2_ran_off_the_end_of_the_requirement_list() -> str:
    """The first full-pipeline run with all three levers on never reached them:
    it failed at S2, two stages upstream of the oracle stage.

    Recorded because a lever that is never reached is indistinguishable from a
    lever that does not work, and because the failure is in a stage none of
    this session's changes touched.
    """
    return (
        "**BUILD ok=False, stage=S2, 32 issue(s). `oracles.json` MISSING.**\n\n"
        "    S1 minted        148 requirements   REQ-0000 .. REQ-0147\n"
        "                     113 behavioural, 19 scaffolding, 16 interface\n"
        "    S2 produced      412 testpoints\n"
        "    of which          32 cover REQ-0148 .. REQ-0159, which DO NOT "
        "EXIST\n\n"
        "S2 ran off the end of the requirement list and kept numbering. The "
        "gate caught it correctly -- a nonexistent uid presents as 'does not "
        "declare needs=testplan', because every one of the 148 real "
        "requirements declares it. The tail is contiguous (TP-0380..TP-0411) "
        "and the invented uids are sequential, so this is a continuation past "
        "the end rather than scattered corruption.\n\n"
        "**NOT CAUSED BY THIS SESSION'S CHANGES**, which touch `oracles_stage`, "
        "`oracle_gen` and parameter plumbing in `integration`. S1 and S2 are "
        "untouched. **BUT THE CONFIGURATION WAS MINE**: the driver passed "
        "`max_repairs=2` to save calls where the pipeline default is 5, so S2 "
        "got two rounds to fix a 32-issue tail and did not converge. Re-run at "
        "the default before reading this as an S2 defect rather than a budget "
        "one.\n\n"
        "**AND 17 PROBES WERE NAMED BY NO ACTIVATION OR EFFECT** -- `in_idle`, "
        "`start_detected`, `filter_cnt_expired`, `scl_sync_active` and 13 more. "
        "Either normalize did not use a declared probe or `[P]` over-nominated. "
        "Worth recording next to this because probes are the lever proposed for "
        "state-dependent activations -- 78 of 115 forms carry no `inputs` "
        "predicate -- and here a third of them went unused.\n\n"
        "**THE GENERAL POINT.** Every measurement in this directory before this "
        "run drove `run_oracle_stage` directly, which skips S1, S2, S3 and the "
        "stimulus loop. The first attempt to run the whole thing failed "
        "upstream of everything measured, which is exactly the class of defect "
        "a driver cannot see."
    )


def the_full_pipeline_on_the_plans_own_metrics() -> str:
    """A complete run -- S1 through the reference model -- with the demotion,
    an in-run population and cell authoring all configured. Scored against the
    standing nine designs and the control, both of which the run never saw.

    Driver `e5_full_pipeline.py`, report `e5_report.py`.
    """
    return (
        "**BUILD ok=True. 151 requirements.**\n\n"
        "    TRUSTED 102   ABANDONED 31   ORACLE_INVALID 12   VACUOUS 6\n"
        "    SPAN         102 of 151 = 67.5%\n"
        "    CORPUS       285 bodies / 151 reqs, median 2, max 11\n"
        "                 generate 151, repair 122, cell 12\n"
        "    DECIDE        51 of 102 on >=1 design\n"
        "    EFFECTIVE     16 distinct verdict vectors\n"
        "    AUDIT         15 of 51 = 29.4% convict the control\n"
        "    BLINDNESS      5 of 445 = 1.1%\n"
        "    CONSTRICTION  accepts 0 of 9 designs\n\n"
        "**BLINDNESS IS ESSENTIALLY SOLVED AND THAT IS THE RESULT.** 1.1% "
        "against the 15.5% of the best driver-built set and the 50-56% the "
        "plan's ladder stalls at. Five cells of 445 are unadjudicated. The "
        "polarity correction is on, so a check convicting both sides closes "
        "nothing -- these are real separations.\n\n"
        "**AND THE SET STILL ACCEPTS NOTHING, WHICH IS THE FAILURE.** The "
        "plan's headline is one equivalence class containing the correct "
        "design; this is zero classes. So over-strictness, not blindness, is "
        "now the binding constraint -- an inversion of the premise every "
        "earlier stage was built on.\n\n"
        "**THE REFUTATION LEG SCALES WITH THE POPULATION, MEASURED.** The run "
        "refuted 12 checks against its OWN three designs. Against the standing "
        "nine a further 9 are refuted, and **9 of 9 convict the control** -- "
        "21 of 21 across both populations, precision still perfect and still "
        "reading no reference.\n\n"
        "    as frozen (102)            audit 29.4%  blind 1.1%  accepts 0\n"
        "    minus 9-design refuted     audit 14.3%  blind 1.1%  accepts 0\n"
        "    ceiling, reference-picked  audit  0.0%  blind 5.8%  accepts 3\n\n"
        "Audit halves at no blindness cost, again. But it cannot reach 0: six "
        "control-convicting checks survive because they do not convict ALL "
        "nine. And even the barred ceiling accepts 3 designs -- `h, q, s` -- so "
        "one class is not reachable on this board by dropping checks at all.\n\n"
        "**CELL AUTHORING RAN AND THIS RUN CANNOT SCORE IT.** 12 targets, 12 "
        "bodies, 25 calls -- and **0 survived to the frozen set**, closing 0 "
        "cells. That is not E4's pre-registered null. E4 asks whether authoring "
        "at a disagreement can reach a blindness RESIDUE, and this set reached "
        "1.1% blind without any cell check: there was no residue to attack. "
        "The adoption rule is also too strict -- a cell check enters `held` "
        "only where the requirement's draft decides nothing -- so all 12 went "
        "to the corpus by construction. **Report as inconclusive, not as a "
        "negative.**\n\n"
        "**WHERE THE LOSS MOVED.** 27 of 31 abandonments are now 'never "
        "reached in N attempts' -- the stimulus loop -- and 3 are 'no "
        "observation route found', against 52 of 115 before `resolve_indirect` "
        "was in the loop. Normalization observability is closed; stimulus "
        "reachability is the new binding constraint. Also 216 of 625 "
        "testpoints are named by no oracle and 140 move nothing at all."
    )


def a_rejection_rule_is_selection_and_mine_was_a_point_on_the_sweep() -> str:
    """**THIS RETRACTS `no_selection_rule_beats_not_selecting_on_the_full_
    pipeline_set`, WHICH WAS WRONG.** That finding reported the `t` sweep as
    dominated by not selecting at every threshold. It was an artifact of mixing
    two scorings: the kept sets came from `population.select`, which hands a
    check the population member's testpoints CONCATENATED into one trace, and
    the columns were per-testpoint verdicts. Scored one way throughout, the
    sweep says close to the opposite. Driver `e5_selection.py`.

    It also retracts the framing that `refuted_by_the_population` is "a
    rejection rule, not selection". A rejection rule IS selection -- both take
    a check set and return a subset from the checks' verdicts against the
    population -- and this one is not merely of the same kind, it is a POINT ON
    THE SWEEP.
    """
    return (
        "**`refuted_by_the_population` IS `max_convictions = N-1`.** Verified "
        "on the full-pipeline set: both drop the same 9 checks -- REQ-0020, "
        "0024, 0027, 0081, 0092, 0120, 0124, 0134, 0149 -- for identical kept "
        "counts, audit, blindness and accepted designs. 'Convicts every design' "
        "and 'convicts more than N-1' are the same predicate. So it is not a "
        "new instrument beside selection; it is the weakest non-trivial "
        "threshold of the rule the plan already had.\n\n"
        "**THE SWEEP, ONE SCORING, per-testpoint verdicts throughout:**\n\n"
        "    t   kept eff  audit   blind   accepts  classes  set rejects\n"
        "                                                     the control\n"
        "    0    27   5   0.0%  100.0%      9        8        no\n"
        "    2    27   5   0.0%  100.0%      9        8        no\n"
        "    3    34   8   2.9%   13.5%      4        4        YES\n"
        "    4    37  10   2.7%    5.8%      3        3        YES\n"
        "    5    39  12   7.7%    1.1%      0        0        YES\n"
        "    8    42  15  14.3%    1.1%      0        0        YES\n"
        "    9    51  16  29.4%    1.1%      0        0        YES\n"
        "    reference-picked (BARRED): 36 kept, 5.8% blind, accepts h,q,s\n\n"
        "**t=4 REPRODUCES THE BARRED CEILING GOLDEN-FREE.** Same accepted set "
        "`h, q, s`, same 5.8% blindness, 37 checks against 36 -- reached by "
        "counting convictions over spec-derived designs and reading no "
        "reference. That is a real result and the previous finding denied it.\n\n"
        "**AND THE PLAN'S HEADLINE STILL FAILS, ON ITS SECOND HALF.** 'One "
        "class containing the correct design' -- at every t from 3 up the SET "
        "REJECTS THE CONTROL, so the correct design is not among the accepted "
        "however few classes remain. t=3 and t=4 are the screened set's failure "
        "wearing a good number, which the plan named in advance: 'accepting "
        "exactly one class is a success only if the correct design is in it'. "
        "Below t=3 nothing is rejected at all -- 9 designs, 8 classes, 100% "
        "blind -- so the accepted-set column is vacuous there rather than "
        "good.\n\n"
        "**ONE CHECK IS DOING IT.** At t=3 and t=4 exactly one surviving member "
        "convicts the control. The distance between this board and the plan's "
        "target is a single over-strict check that convicts at most four "
        "designs, which no conviction-count threshold can separate from a "
        "sound one.\n\n"
        "**AND `select`'s OWN SCORING IS NOT THIS SCORING, which is worth more "
        "than the retraction.** Concatenating a design's testpoints into one "
        "trace changes verdicts wholesale:\n\n"
        "    t=0   select keeps 16, per-testpoint keeps 27, agreeing on  1\n"
        "    t=4   select keeps 20, per-testpoint keeps 37, agreeing on 10\n"
        "    t=8   select keeps 28, per-testpoint keeps 42, agreeing on 19\n\n"
        "At t=0 the two procedures agree on ONE check. Any figure quoted from "
        "`select` is about a trace shape the checks were not authored against, "
        "and cannot be compared with a per-testpoint number without saying so."
    )
