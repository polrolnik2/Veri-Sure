"""Golden-free instruments for judging a check, measured on k1-dcfsm.

The oracle stage has one hard problem: deciding whether a check is OVER-STRICT
(it convicts a design that satisfies its requirement) without the known-good
design, which exists only in the benchmark. Everything here is an attempt at
that question using artifacts the pipeline can actually have -- several designs
written independently from the same specification, and mechanical mutants of
one of them.

WHAT WAS MEASURED, so a caller knows what these are worth. On 134 checks that
fire, 7 are both SOUND (spare the known-good design) and DISCRIMINATING (convict
a design wrong on 61% of the suite, written from the specification and held out
of every selection) -- a 5.2% base rate, spanning 7 requirements of 89. Figures
below quoting a 3.0% base rate were taken against that design AFTER an editor
had been pointed at the check set, so they are a floor.

SOUND HERE MEANS "DECIDES ON THE KNOWN-GOOD DESIGN AND NEVER CONVICTS IT", AND
THE FIRST HALF IS LOAD-BEARING. Written as "convicts it nowhere" the predicate is
satisfied vacuously by a check that never decides there at all, which is sound by
silence rather than by evidence -- the same conflation `stage_unexercised` names
in capitals, arriving in the metric instead of in the staging loop. It is not
hypothetical: recomputing this plan's headline adequacy without the first half
counted one extra check, one that decides 0 of 318 testpoints on the known-good
design and exactly 1 on a held-out one. Every figure here requires the check to
decide.

    split_cell_soundness   84% precision as an unsoundness predictor; the checks
                           it keeps convict the known-good design 29% of the
                           time against a 63% base rate. The best soundness
                           filter measured.
    disagreement_cells     97% of a held-out design's errors fall in the 11% of
                           cells the ensemble cannot agree on -- an 8.6x
                           localisation. It says WHERE the question is, and
                           NOTHING here can answer it: see
                           `split_cells_are_a_specification_finding`. Put the
                           map in front of whoever owns the specification.
    refuted_by             a check that spares every candidate and convicts a
                           mechanical mutant is 100% sound (19 of 19) and 0%
                           discriminating (0 of 19). Use it to reject a check
                           that cannot fail, never as evidence that one is good.

AND THE ONE THING THAT DOES NOT WORK, measured at every threshold: the ensemble's
own CONSENSUS is not an accept criterion. At k-of-13 agreement for every k from
9 to 13, a design wrong on 61% of the suite scores at or BELOW the known-good
design, because the population's errors are correlated through the ambiguity of
the specification they were all written from. Correctness is what makes the
known-good design an outlier. `consensus_cells` is exported for the
disagreement map only, and `agreement_is_not_an_oracle` documents the refutation
so it cannot be rediscovered as a good idea.

THE SAME IDEA ONE LEVEL DOWN IS ALSO REFUTED, and it is the more tempting one
because the correlation argument above does not obviously apply: a requirement
usually carries two to four independently authored checks, so "the requirement
objects when at least k of its checks object" is an ensemble over readings of
ONE SENTENCE rather than of a whole specification. Measured at k = 1, 2, a
majority and unanimity, it adds ZERO requirements that the best single check for
that requirement did not already supply. `check_agreement_is_not_an_oracle`
carries the numbers.

AND THE SET IS NOT A DESCENT CRITERION EITHER, which is the one that matters for
a repair loop: a loop does not need an accept threshold, it needs a number that
falls as the design improves. Over 16 designs and six golden-free weightings, no
weighting orders designs by their actual distance from the known-good design at
better than +0.20 Spearman, and the checks that DISCRIMINATE between designs
order them backwards at -0.54. `conviction_count_is_not_a_descent_criterion`
carries that, and it is the reason to score a repair loop on requirements it
satisfies rather than on objections it has left, and
`soundness_buys_termination_not_correctness` for the one property a sound
set does have and the one it does not, and
`the_residue_is_check_strength` for where the remaining gap actually is
once span, stimulus and volume have each been excluded by measurement, and
`strength_and_soundness_are_exchanged_not_traded` for what happens when you
attack that residue directly -- and
`the_soundness_boundary_is_reachable_from_one_side_only` for the correction that
makes that partition actionable, because the boundary turns out to be findable
from the over-strict side (7 of 47) and not from the weak side (0 of 34),
p = 0.0196. Author strict and narrow; never author weak and strengthen.

AND THE STOPPING POINT IS WORSE THAN WEAK, WHICH IS THE ONE A LOOP AUTHOR MUST
READ BEFORE ANY OF THE ABOVE. On a set carrying even one check the known-good
design fails, zero objections is not poor evidence of correctness -- it is proof
of INCORRECTNESS, by arithmetic rather than by measurement, because the
known-good design does not score zero either. Measured on the widest golden-free
set here, spanning a majority of the specification at a 10% false-reject rate: a
Sonnet editor reached zero and the bounded miter says DIFFERS, having moved
TOWARD the reference while objections fell 11 to 3 and back AWAY from it over the
final 3 to 0. `zero_objections_can_be_incompatible_with_correctness` carries it,
and it is why a loop is stopped on a trial budget rather than on its criterion
going quiet.

AND ONE THING HERE IS CHEAP AND POSITIVE, WHICH IS RARE ENOUGH TO SAY SEPARATELY.
Two authoring populations that measure equally bad are not interchangeable: on
the 34 requirements answered by both a port-only author and a probe-using one,
the adequate sets are 3 and 2 and their INTERSECTION IS ZERO, so the union is 5
where the better arm alone is 3. An arm comparison decides which prompt to ship
and must not decide which bodies to keep.
`authoring_populations_are_complementary_not_ordered` carries it.

AND ONE GATE HERE IS ENDORSED RATHER THAN REFUTED, WITH ITS PRICE ATTACHED.
"objects to at most 2 of 13 independently written designs" keeps 59 checks and
59 of 59 spare the known-good design -- precision 100% against a 31% base rate,
spanning 44% of the specification and reading no known-good design to do it. It
is also why the set it produces is weak: of the 18 adequate checks in the largest
perfectly sound set, it keeps 9. Its precision and its cost are the same
property. `the_minority_rule_is_precise_and_that_is_what_it_costs` carries both.

AND THE CELL ITSELF NOW HAS A DECOMPOSITION RATHER THAN ONLY A SIZE. Among sound
checks, the 52 that convict no candidate hold 3 adequate ones and the 16 that
convict at least one hold 15 -- so ADEQUATE = SOUND AND REFUTABLE at 94%
precision and 83% recall, with the second leg reading no known-good design.
Composed with the soundness gate it is the first golden-free adequacy instrument
here, at a 10.7x lift on n = 7. `adequacy_is_soundness_and_refutability` carries
it, including why it must not be used to SELECT.

AND THE AUDIT COLUMN IS A DEFECT, NOT A RATE TO TRADE AGAINST REACH. Two 68-check
sets spanning the same 45 of 89 requirements, differing only in whether 7 members
convict the known-good design: against a design wrong on 200 of 318 testpoints,
the one with the unsound members scores ZERO objections and accepts it, and the
perfectly sound one objects. Over the whole corpus 129 bodies catch that design
across 64% of the specification and exactly ONE of them is sound.
`soundness_is_what_makes_the_criterion_work` carries it.

AND REMOVING THE UNSOUND MEMBERS IS STILL NOT ENOUGH, WHICH CLOSES THE CORPUS.
The largest perfectly sound set here spans a majority -- 68 checks over 45 of 89
requirements at a zero false-reject rate -- an editor drove a held-out design to
ZERO objections against it in 6 of 14 trials, and the miter says DIFFERS at 193
of 318 testpoints. 124 corpus bodies catch that design across 62% of the
specification and NOT ONE of them is sound, and since this set already is every
sound check in the corpus there are none a better selection could have found.
`a_perfectly_sound_majority_set_still_false_accepts` carries it, and the residue
it leaves is check strength rather than any property of the set.

AND THE TWO PROPERTIES CANNOT BE COMPOSED FROM SEPARATE BODIES, WHICH RETIRES
THE LAST CEILING ARGUMENT HERE. On the 26 requirements holding a sound body and
a discriminating body that are never the same body, an author shown BOTH and
told in numbers where the answer sits between them landed 0 adequate of 26 --
and 8 sound + 18 discriminating = 26 = n, so the two sets came out exactly
disjoint, at the minimum the marginals allow. A ceiling computed by counting the
two legs separately counts a vacuous body as half a check and an over-strict
body as the other half. `the_two_legs_cannot_be_composed_from_separate_bodies`
carries it.

AND THE BEST GOLDEN-FREE FILTER HERE DOES NOT SURVIVE BEING A TARGET, WHICH
CLOSES THE AUTHORING ROUTE. Given to 24 authors as a stated numeric goal with
each check's own measured count fed back, "objects to 1 or 2 of 13" drove two
into the band -- both sound, neither discriminating -- and the round's one
adequate check convicts 12 of 13, so the rule would have rejected it. The count
is a soundness signal, and there is no second golden-free signal for the other
leg. `the_adequacy_filter_does_not_survive_being_a_target` carries it, together
with the through-line all three authoring rounds share: every one lands on the
overlap its own marginals force and never above it.

WHY ALL OF THAT FAILS IS MEASURED AND IS NOT A PROPERTY OF ANY INSTRUMENT HERE.
On the cells the population cannot agree on, a reader asked ONE targeted question
-- one cell, one port, the specification and the input sequence, no design at all
-- scores WORSE than the population it was meant to beat, and reproduces the
population's exact wrong answer on most of the cells it gets wrong. The
correlated error belongs to the specification-and-reader pair, not to the
design-writing task, so no change of instrument, ordering or granularity
decorrelates it. `split_cells_are_a_specification_finding` carries the numbers
and the one thing that follows from them, and
`accuracy_is_the_wrong_axis_for_a_reference` carries the last shape the idea
takes -- the consensus as an expected-value column rather than as a criterion,
which is 99.822% accurate and drives a loop nowhere.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

Rows = Sequence[Mapping[str, Any]]
ByDesign = Mapping[str, Rows]


def _cell(row: Mapping[str, Any], port: str) -> str:
    out = row.get("outputs") or {}
    ins = row.get("inputs") or {}
    return str(out.get(port, ins.get(port)))


def consensus_cells(by_design: ByDesign, ports: Iterable[str],
                    *, min_agree: int | None = None
                    ) -> dict[tuple[int, str], tuple[str, int]]:
    """`{(row index, port): (agreed value, how many designs agreed)}`.

    `min_agree` defaults to unanimity. A cell is omitted when fewer than that
    many designs share the top value.

    NOT AN ORACLE. See `agreement_is_not_an_oracle`.
    """
    names = list(by_design)
    if not names:
        return {}
    need = len(names) if min_agree is None else min_agree
    n = min(len(by_design[k]) for k in names)
    out: dict[tuple[int, str], tuple[str, int]] = {}
    for i in range(n):
        for p in ports:
            vals = [_cell(by_design[k][i], p) for k in names]
            top, cnt = Counter(vals).most_common(1)[0]
            if cnt >= need:
                out[(i, p)] = (top, cnt)
    return out


def disagreement_cells(by_design: ByDesign, ports: Iterable[str]) -> set[int]:
    """Row indices where the designs do NOT all agree on some port.

    On k1 these are 11% of cells and hold 97% of a held-out design's errors --
    the only localisation of the residue this project has measured. Use it to
    aim authoring or stimulus at the rows where the specification is ambiguous.
    """
    names = list(by_design)
    if not names:
        return set()
    n = min(len(by_design[k]) for k in names)
    hot: set[int] = set()
    for i in range(n):
        for p in ports:
            if len({_cell(by_design[k][i], p) for k in names}) > 1:
                hot.add(i)
                break
    return hot


def split_cell_soundness(decide_on, by_design: ByDesign,
                         ports: Iterable[str]) -> bool:
    """True when the check makes a demand where the population is CERTAIN.

    `decide_on(rows)` must return True when the check CONVICTS those rows.

    The argument: on cells where every independently written design agrees, the
    agreed value matched the known-good design 99.82% of the time on k1. So a
    check convicting a design THERE is, at those odds, the thing that is wrong.
    This is sharper than "it convicts every candidate", which cannot tell a
    correct demand from a misreading the whole population shares.

    Measured: 84% precision as an unsoundness predictor; checks it clears
    convict the known-good design 29% of the time against a 63% base rate.
    A True verdict is a REASON TO REJECT, never a proof.
    """
    hot = disagreement_cells(by_design, ports)
    for rows in by_design.values():
        certain = [r for i, r in enumerate(rows) if i not in hot]
        if certain and decide_on(certain):
            return True
    return False


def refuted_by(decide_on, candidates: Iterable[Rows],
               mutants: Iterable[Rows]) -> bool:
    """True when the check spares every candidate and convicts some mutant.

    A mutant is a design wrong BY CONSTRUCTION, so this is a golden-free proof
    that the check CAN fail -- which "no candidate objected" is not, since every
    candidate may simply be right.

    ITS LIMIT IS MEASURED AND IS SEVERE: of 19 checks this promoted, 19 spare
    the known-good design and ZERO catch a from-scratch design that is wrong on
    61% of the suite. A mechanical mutant is an operator substitution; a real
    design's errors are different readings of an ambiguous sentence.

    AND DO NOT USE THE CONVERSE AS A REJECTION, which is what an earlier
    version of this docstring advised. "It objects to no candidate" is NOT
    "it cannot fail": the population may simply be RIGHT about that
    requirement. Measured on two designs held out of the population -- of the
    14 sound checks that caught one of them, THREE convict none of the 13
    candidates, so a refutable leg would have discarded 21% of the entire
    measured yield, and this function promotes 0 of those 3. Keep such a
    check. A pass here is still not evidence the check is any good.
    """
    if any(decide_on(rows) for rows in candidates):
        return False
    return any(decide_on(rows) for rows in mutants)


def agreement_is_not_an_oracle() -> str:
    """Why the ensemble's agreed value must never be used as an expected value.

    Kept as code rather than a comment so it is found by whoever reaches for the
    idea, which is a natural one and is refuted.
    """
    return (
        "Measured on k1 at every agreement threshold from 9 to 13 of 13: a "
        "design differing from the known-good design on 61% of the suite scores "
        "at or BELOW that design against the consensus (k=13: 0 against 58; "
        "k=12: 174 against 189; k=11: 233 against 359), and the margin widens as "
        "the threshold relaxes. The population's errors are correlated through "
        "the ambiguity of the one specification they were all written from, so "
        "unanimity encodes the shared misreading and being right is what the "
        "criterion penalises. Use `disagreement_cells` to find where the "
        "question is; never use the agreed value as the answer."
    )


def accuracy_is_the_wrong_axis_for_a_reference() -> str:
    """Why 99.822% accurate is compatible with driving a repair loop nowhere.

    The last shape this idea takes: not the consensus as a pass/fail criterion
    over checks, which `agreement_is_not_an_oracle` refutes, but the consensus as
    an EXPECTED VALUE COLUMN -- a mismatch table for a repair loop, which is the
    one thing this pipeline has never given its editor. The reference really is
    that accurate, and it still cannot drive anything.
    """
    return (
        "Measured on k1 over 36,440 cells. The 13-design population is unanimous "
        "on 89.6% of them and the agreed value matches the known-good design on "
        "99.822% of those -- a reference wrong 18 times in ten thousand, built "
        "with no known-good design anywhere in its provenance. Used as a mismatch "
        "table over 16 designs it ranks the known-good design 15th of 16: all 13 "
        "population members score exactly 0 disagreements, and so does a held-out "
        "design written from the same specification that differs from the "
        "known-good design on 193 of 318 testpoints. Only the known-good design "
        "(58) and one design that corrected a real defect (298) disagree at all, "
        "and both scores are penalties for leaving the population's distribution. "
        "The failure is structural: a consensus over a population is satisfied by "
        "that population by construction, and by anything drawn from the same "
        "distribution. What a reference needs is not to be right often but to be "
        "right WHERE THE DESIGN UNDER TEST IS WRONG, and this one is silent on "
        "100% of what makes that held-out design wrong. Do not read a high "
        "accuracy figure as evidence that a reference can drive a loop."
    )


def check_agreement_is_not_an_oracle() -> str:
    """Why an ensemble of CHECKS for one requirement buys nothing either.

    The companion to `agreement_is_not_an_oracle`, and the more tempting idea of
    the two: a requirement typically carries several independently authored
    checks, so requiring k of them to agree looks like a way to cancel one
    author's misreading without any reference design. It does not.
    """
    return (
        "Measured on k1 over 134 checks spanning 63 requirements, 1 to 4 checks "
        "each. Taking 'the requirement objects when at least k of its checks "
        "object': at k=1 the requirement is SOUND (spares the known-good design) "
        "12 times and DISCRIMINATING (convicts a held-out wrong design) 49 "
        "times, at unanimity 40 and 24 -- so k trades one for the other exactly "
        "as a conviction-count threshold does. The cell that needs BOTH peaks at "
        "4 requirements, and its union with the per-check set is the per-check "
        "set, so the ensemble never reaches past its own best member. At "
        "unanimity the marginals 40 and 24 of 63 predict an overlap of 15.2 if "
        "the two properties were independent; the observed overlap is 4, close "
        "to the minimum the marginals allow. Sound and discriminating are not "
        "merely uncorrelated but near-disjoint, which is why every threshold, "
        "filter and ensemble measured here lands in the same place."
    )


def conviction_count_is_not_a_descent_criterion() -> str:
    """Why a repair loop must not descend on how many checks object.

    The natural way to drive an editor with a check set: count the objections
    and minimise them. Measured here and it points the wrong way, which is worth
    more than the two failed loop trajectories that suggested it -- those were
    two runs, this is a property of the corpus.
    """
    return (
        "Measured on k1 over 16 designs -- the known-good one, 13 written "
        "independently from the specification, and two held out. Scoring each "
        "by total (check, testpoint) convictions, the known-good design ranks "
        "2nd, but by 0.7% over a population spanning 15%, and among the 15 "
        "wrong designs the Spearman against testpoints actually differing from "
        "the known-good design is -0.223: the count is slightly ANTI-correlated "
        "with correctness. Six golden-free weightings were tried (equal, "
        "discriminating, checkwise, rare, split-cell-clean, and the "
        "intersection); none reaches +0.3, and every one either separates the "
        "known-good design from the population or orders the population, never "
        "both -- split-cell-clean is the only positive ordering at +0.201 and "
        "ranks the known-good design 13th of 16, while the intersection ranks "
        "it LAST. Worst is the subset that ought to carry the signal: checks "
        "whose verdict varies across the population order designs BACKWARDS at "
        "-0.542, because a check that separates spec-derived designs separates "
        "them along their shared misreading, on which the correct design is the "
        "outlier. Score a repair loop on requirements it satisfies, not on "
        "objections it has left, and do not read a falling objection count as "
        "progress toward correctness."
    )

def soundness_buys_termination_not_correctness() -> str:
    """What a perfectly sound check set does and does not do for a repair loop.

    The one positive property any rule here has produced: a set no correct
    design violates makes zero objections REACHABLE, which is necessary --
    against a set carrying one unsatisfiable demand the loop can never
    terminate. The mistake is to read that as progress toward correctness.
    """
    return (
        "Measured on k1 with the largest perfectly sound set the corpus can "
        "produce: 50 checks over 40 requirements, 45% of the specification, "
        "ZERO of them convicting the known-good design. Two Sonnet editor runs "
        "on two designs written from the specification and held out of every "
        "selection. On the clean one, objections went 7 to 1 while testpoints "
        "differing from the known-good design went 249 to 188 -- the criterion "
        "and the grade moving TOGETHER, and one output repaired to never "
        "differing at all. So a perfectly sound set does give a repair loop a "
        "correct gradient, which is more than any other rule measured here. "
        "What it does NOT give is enough of one: the run ended with ONE "
        "objection left on a design still wrong on 59% of the suite, so the set "
        "runs out of things to say long before the design is right. The limit "
        "is SPARSITY, not direction. (A second run on a design carrying an "
        "injected constant no requirement mentions went the other way, 7 to 2 "
        "objections while divergence rose 194 to 217; that measures the "
        "injected defect, not the set, and is not evidence about the gradient.) "
        "Soundness buys termination and a usable direction. It does not buy "
        "sufficiency, and zero objections against a sparse sound set still "
        "means very little.\n\n"
        "AND MORE CHECKS DO NOT CLOSE THE GAP, measured rather than assumed. "
        "Authoring three fresh checks each for the 22 behavioural "
        "requirements the sound set does not cover -- 66 calls, all parsing, "
        "all compiling, no duplicate bodies -- moved span from 40 to 43 of 89 "
        "and produced ZERO new objections against the design under test. The "
        "comparison explains it: on the requirements the set ALREADY covers, "
        "53% of firing checks pass the rule; on the ones it does not, the "
        "original corpus scored 0% over 54 prior attempts and the fresh round "
        "13% over 66 more, six of its seven survivors landing on the three "
        "least demanding sentences in the population. A requirement without a "
        "sound check is not an unattempted one; it is a harder one.\n\n"
        "REPRODUCED ON A SECOND SET, AND SPAN IS NOT THE VARIABLE. A "
        "golden-free set spanning 45 of 89 requirements -- 51%, a majority, "
        "at a 10% false-reject rate -- drove the same held-out design from "
        "11 objections to 3 in six trials, divergence 249 to 192, one "
        "output repaired to never differing, and one edit clearing four "
        "objections at once by finding a shared root cause. The gradient is "
        "therefore confirmed twice, independently. But the SMALLER set -- 40 "
        "requirements, 44%, zero unsound -- finished four testpoints CLOSER "
        "to correct on the same design. Nine more requirements, eighteen "
        "more checks and four more objections bought no extra correctness. "
        "Spanning a majority and driving a design to correctness are "
        "independent properties of a set, and neither run reached "
        "equivalence."
    )

def the_residue_is_check_strength() -> str:
    """Where the gap actually is, after span, stimulus and volume are excluded.

    A sound set that says almost nothing about a mostly-wrong design fails one
    of two ways, and they demand opposite work: SILENCE (the checks never decide
    where the design is wrong -- a stimulus finding) or BLINDNESS (they decide
    there and pass -- which no stimulus fixes). Separating them is the same
    distinction staging conflates, asked of the accept criterion instead.
    """
    return (
        "Measured on k1, per check, restricted to the testpoints where a port "
        "THAT CHECK ITSELF READS differs from the known-good design -- because a "
        "testpoint is wrong if any of ten outputs differs, and a check watching "
        "one port is not blind for passing a defect on another. Of 50 sound "
        "checks against a held-out design: 3 are exposed to a wrong port and "
        "never decide there, 36 DECIDE where their own port is wrong and PASS, "
        "and 7 object. Across 3,399 decisions on exposed testpoints there are "
        "134 objections -- 3.9%. One check reads a single port, decided on all "
        "99 testpoints where that port is wrong, and objected zero times.\n\n"
        "So the stimulus loop is worth 3 checks of 50 here, not the lever it is "
        "usually assumed to be: the suite already drives the design into the "
        "wrong behaviour on the exact ports the checks read. The residue is "
        "CHECK STRENGTH -- a check asserts a fragment of its sentence and the "
        "design violates the sentence elsewhere in the same port. That single "
        "fact explains why more checks do not help (the ones already watching "
        "do not object), why selection does not help (the blindness is uniform, "
        "36 of 50, not a removable subset), and why a correct repair gradient is "
        "still far too shallow to finish.\n\n"
        "The uncomfortable half: raising 3.9% means each check asserting MORE of "
        "its sentence, and asserting more is what produces over-strictness. This "
        "set is at 3.9% strength and ZERO unsound simultaneously, which is the "
        "first time both ends of that trade have been measured on one set.\n\n"
        "REPRODUCED ON A SET 36% LARGER, AND IT DOES NOT SCALE. The same "
        "measurement on the largest perfectly sound set this corpus contains -- "
        "68 checks over 45 of 89 requirements, against the same held-out design "
        "-- reads 4 probe-only, 3 SILENT, 54 BLIND, 7 objecting, and strength "
        "134/4804 = 2.8%. **THE STIMULUS OPPORTUNITY IS THE SAME THREE CHECKS AT "
        "68 AS AT 50**: the 18 checks added are 18 more blind ones and zero more "
        "silent ones, and strength FELL, because the additions decide more and "
        "object no more. So the 3-of-50 is not an artifact of that set's size, "
        "and a stimulus round is worth the same three checks however wide the set "
        "gets."
    )

def strength_and_soundness_are_exchanged_not_traded() -> str:
    """The sharpest form of the finding this whole module is about.

    Every other measurement here reports the two properties as anti-correlated
    ACROSS a corpus, which leaves room for hoping a better author or a better
    prompt lands in between. This one watches a single author make a single
    change to a single check, 34 times, and there is no in between.
    """
    return (
        "Measured on k1. 34 sound checks that read a real output, decide on 13 "
        "independently written designs and object to none of them, each "
        "re-authored to assert every obligation in its own requirement sentence. "
        "The objection was admissible -- the sentence itself, plus a count over "
        "the candidate population -- and named the over-reach hazard outright. "
        "All 34 returned, compiled, and none came back unchanged.\n\n"
        "Strength, measured as objections over decisions on testpoints where a "
        "port the check itself reads is wrong, went 1.8% to 44.1%: a 24x rise, "
        "so asserting the whole sentence is well within what the author can do. "
        "Checks objecting to a held-out design went 3 to 18. And checks "
        "convicting the known-good design went 0 to 23 of 34.\n\n"
        "THE BOTH CELL IS 0 OF 34. Sound after the edit: 11. Discriminating "
        "after the edit: 21. Overlap: zero, against 6.8 expected under "
        "independence -- and zero is the MINIMUM the marginals allow, since 11 + "
        "21 = 32 of 34. Every check that gained discrimination lost soundness "
        "and every check that kept soundness gained none, with no exceptions.\n\n"
        "So this is not a correlation between two properties of a corpus; it is "
        "a partition produced by the edit itself. The few percent of checks that "
        "are both sound and discriminating are not a low yield from a hard task "
        "-- they are authors happening to stop at exactly the right point. What "
        "would fix it is a soundness oracle available WHILE authoring, so the "
        "author can stop at the boundary instead of crossing it. Nothing here "
        "builds one without the known-good design."
    )





def zero_objections_can_be_incompatible_with_correctness() -> str:
    """The result a repair loop is most likely to be built on, and it is false.

    Every other refutation here says a check set is a WEAK guide. This one says
    something stronger about the moment the guide declares success: on a set that
    carries even one over-strict check, reaching zero objections is not weak
    evidence of correctness -- it is PROOF of incorrectness, available before any
    equivalence instrument runs, and the loop cannot see it.
    """
    return (
        "Measured on k1, on the widest golden-free set this corpus has produced: "
        "68 checks over 45 of 89 requirements = 51%, A MAJORITY OF THE "
        "SPECIFICATION, selected by a rule that reads only spec-derived designs. "
        "The audit, computed afterwards and feeding nothing: 7 of the 68 convict "
        "the known-good design -- a 10% false-reject rate.\n\n"
        "THAT 10% IS THE WHOLE FINDING, READ FORWARD RATHER THAN AS A COST. "
        "The known-good design scores SEVEN objections against this set. A design "
        "scoring ZERO therefore disagrees with it on at least those seven checks, "
        "so it is not that design. Zero objections and equivalence are MUTUALLY "
        "EXCLUSIVE here, and the exclusion is arithmetic -- no miter, no held-out "
        "grade and no sampling is involved in deriving it.\n\n"
        "It is not hypothetical. A Sonnet editor, driven through the shipped "
        "staged-buffer policy on a design written from the specification and held "
        "out of every selection, went 11 objections to 3 to 0 in 12 of 14 trials "
        "and stopped, correctly, because the criterion it was given said it was "
        "finished. The bounded miter returns DIFFERS, with all three grade pins "
        "green in the same process.\n\n"
        "AND THE LAST LEG IS THE PART TO KEEP. Objections 11 -> 3 moved the "
        "design toward the reference: 249 of 318 testpoints differing -> 192, "
        "2,904 differing cells -> 2,733, and one output repaired to NEVER "
        "differing. Objections 3 -> 0 moved it back: 200 testpoints, 3,075 cells, "
        "that repaired output broken again at 54 cells, and every one of the ten "
        "declared outputs differing. The three points were each re-measured in "
        "their own clean run directory. So the gradient was real and it INVERTED "
        "over the final approach, at exactly the objection count that reads as "
        "success.\n\n"
        "The consequence for a loop is a disposition rule, not a better set: a "
        "check set whose over-strict count is unknown -- which is every set "
        "outside a benchmark -- cannot have zero objections read as done. Score "
        "the loop on requirements it satisfies, stop it on a trial budget, and "
        "treat a run that reaches zero as a set defect to investigate rather than "
        "a design to ship."
    )

def authoring_populations_are_complementary_not_ordered() -> str:
    """Whether to keep a second population, when the first one measures better.

    Every arm comparison on this plan asks which population is BETTER, gets an
    answer inside the noise, and moves on. That is the wrong question for a set
    that is a union: two populations equally bad on average are worth keeping
    together if they are bad in different places, and worth collapsing if not.
    Measured here for the first time, and they are disjoint.
    """
    return (
        "Measured on k1, on the 34 behavioural requirements the production run "
        "never trusted, each answered by BOTH a port-only author and one given "
        "spec-licensed state probes -- so the comparison is paired on the "
        "requirement and a vague sentence subtracts from both arms equally.\n\n"
        "NEITHER ARM IS BETTER. Adequate checks: 3 from the port-only arm, 2 "
        "from the probe arm, two-sided sign test p = 1.000. The two legs move in "
        "opposite directions and cancel -- the probe arm is more often sound (9 "
        "against 6 paired, p = 0.607) and the port-only arm more often "
        "discriminating (11 against 6, p = 0.332). That is the same exchange this "
        "module measures inside a single check, appearing between two authors.\n\n"
        "AND THE ADEQUATE SETS ARE DISJOINT: 3 + 2, INTERSECTION 0. No "
        "requirement got an adequate check from both arms. So the union is 5 of "
        "34 where the better arm alone is 3 -- two thirds more, from a lever that "
        "costs nothing, because in an A/B both populations have already been "
        "authored and the losing arm is usually discarded.\n\n"
        "The rule this sets: an arm comparison decides which PROMPT to ship and "
        "must not decide which BODIES to keep. Score arms against each other, "
        "then select the set over their union. On this corpus the widest "
        "perfectly sound set draws from every arm that was ever run, and "
        "discarding any losing arm would have cost it span.\n\n"
        "What this does NOT say is that more arms keep paying. Two arms are two "
        "samples, the disjointness is measured once, and a third arm might "
        "overlap both. The claim is the narrow one: a losing arm is not an empty "
        "arm, and this plan has been treating it as one."
    )

def the_minority_rule_is_precise_and_that_is_what_it_costs() -> str:
    """The one golden-free gate on this plan that works, and its price.

    Everything else here refutes an instrument. This one endorses one -- and the
    endorsement is the smaller half, because a filter that is perfectly precise
    about soundness turns out to be perfectly precise about removing the checks
    that discriminate. Read both numbers or this becomes a recommendation.
    """
    return (
        "THE RULE: keep a check that objects to at most 2 of 13 independently "
        "written spec-derived designs. It reads no known-good design, and its "
        "rationale is not tuning -- a requirement that MOST competent independent "
        "implementations violate is more likely one the CHECK has misread than "
        "one all those authors got wrong.\n\n"
        "Measured on k1 over 218 checks that fire, where the base rate of "
        "soundness is 68/218 = 31%: the rule keeps 59, and **59 OF 59 SPARE THE "
        "KNOWN-GOOD DESIGN. PRECISION 100%.** An earlier version of this was 7 of "
        "7 and readable as an accident; at 59 of 59 against a 31% base rate it is "
        "not. It spans 39 of 89 requirements = 44%, and it is the best "
        "golden-free soundness instrument measured here by a wide margin -- the "
        "next is the split-cell filter at 84%.\n\n"
        "AND IT REMOVES HALF THE ADEQUACY, WHICH IS THE PART TO CARRY. The "
        "largest perfectly sound set this corpus contains is 68 checks over 45 "
        "requirements = 51%, and it holds 18 checks that are also discriminating. "
        "The rule recovers 59 of those 68 checks -- 87% -- but only **9 of the 18 "
        "adequate ones**. It drops 13% of the set and 50% of what makes the set "
        "worth having.\n\n"
        "The mechanism is visible in what it drops: the nine rejected checks "
        "convict 6, 8, 11, 12 and 13 of the 13 candidates. They are sound AND "
        "they object to most of the population -- which is exactly the profile "
        "the rule is built to reject, and exactly the profile of a check that "
        "discriminates. So this is not a tuning loss to be recovered at another "
        "threshold; the rule's precision and its cost are the same property.\n\n"
        "Use it as a soundness gate, which is what it is, and never as a "
        "selector for the final set: gate with it, then take the union with "
        "whatever else the corpus offers, because the checks it rejects are where "
        "half the discrimination lives."
    )

def adequacy_is_soundness_and_refutability() -> str:
    """The first near-exact decomposition of the cell everything here is about.

    Every other entry measures how hard the adequate cell is to reach. This one
    says what it IS, on this corpus, in two properties that are each cheap to
    compute -- and the more interesting half of the answer is that the leg doing
    the work is one this plan dropped as harmful.
    """
    return (
        "Measured on k1 over 218 checks that decide on the known-good design, "
        "with discrimination against BOTH held-out designs. Among the 68 SOUND "
        "checks, where the chance of discriminating is 26% -- three times BELOW "
        "the 75% base rate over all firing checks, which is the anti-correlation "
        "this module exists to document:\n\n"
        "    SOUND and convicting NO candidate   52 checks,  3 adequate =  6%\n"
        "    SOUND and convicting AT LEAST ONE   16 checks, 15 adequate = 94%\n\n"
        "**ADEQUATE = SOUND AND REFUTABLE, at 94% precision and 83% recall.** "
        "Not a correlation -- a decomposition, and the second leg reads only "
        "spec-derived candidates, so it needs no known-good design.\n\n"
        "COMPOSED WITH THE SOUNDNESS GATE IT IS THE FIRST GOLDEN-FREE ADEQUACY "
        "INSTRUMENT HERE. 'Convicts between 1 and 2 of 13' keeps 7 checks of "
        "which 6 are adequate: 86% against an 8% base rate, a 10.7x lift, where "
        "the best previously measured was 3.4x at 10% precision. Recall is 6 of "
        "18 = 33%, and n = 7, so it is an instrument for saying WHICH checks do "
        "the work, not a way of getting more of them.\n\n"
        "TWO THINGS IT IS NOT, and both matter. The upper bound at 2 was chosen "
        "by reading the known-good design, so the composite is a CALIBRATED rule "
        "and not a score. And the lift does not come from the refutable leg "
        "predicting discrimination: at 86% against a 75% base rate that leg is "
        "at chance on its own. It works by REMOVING the 52 sound-and-blind "
        "checks, which is a different mechanism from the one its name suggests.\n\n"
        "SO THE DECISION TO DROP THE REFUTABLE LEG AS A SELECTION RULE STANDS, "
        "AND NOW HAS ITS REASON. It discards 52 checks to keep 16, and the 52 are "
        "SOUND AND SILENT -- a check that never objects never mis-steers a repair "
        "loop, so keeping it costs nothing, while dropping it loses the 3 adequate "
        "checks among them. Use this to REPORT which members of a set carry its "
        "discrimination; do not use it to build the set."
    )

def soundness_is_what_makes_the_criterion_work() -> str:
    """The counterweight to every "over-strictness is the cost of span" reading.

    This module measures soundness as something a set PAYS for -- a false-reject
    rate quoted beside a span. Measured against a design that a set actually
    accepted, the sign flips: the unsound members are not a tax on an otherwise
    working criterion, they are why it stopped working.
    """
    return (
        "Measured on k1 against the design a 68-check golden-free set drove to "
        "ZERO objections and which the bounded miter calls DIFFERS -- wrong on "
        "200 of 318 testpoints and on all ten declared outputs. Every one of the "
        "259 corpus bodies re-decided against its traces:\n\n"
        "    decide on it                                215 of 259\n"
        "    OBJECT to it            129, over 57 of 89 requirements = 64%\n"
        "    of those, inside the set that accepted it     0\n"
        "    of those, SOUND                               1\n\n"
        "**THE CORPUS KNOWS THE DESIGN IS WRONG ACROSS 64% OF THE "
        "SPECIFICATION AND CAN SAY SO SOUNDLY WITH EXACTLY ONE CHECK.** 128 of "
        "the 129 catches are bought by also condemning the known-good design. "
        "That is this module's central anti-correlation stated where it costs "
        "something, rather than as a distribution over a corpus.\n\n"
        "AND THE ONE SOUND CATCH IS THE ACTIONABLE HALF. Swap the accepting "
        "set's 7 over-strict members for 7 sound ones -- same 68 checks, same 45 "
        "of 89 requirements, same 51% span, audit 10% down to 0 -- and the "
        "resulting set OBJECTS to that design where the original accepted it:\n\n"
        "    the set with 7 unsound members   0 objections   ACCEPTED\n"
        "    the perfectly sound set          1 objection    REJECTED\n\n"
        "So the false-reject rate is not the price of the span. On this pair it "
        "is the whole difference between a criterion that discriminates and one "
        "that does not, at identical size and identical coverage. A set's audit "
        "column should be read as a defect to remove, not as a rate to trade "
        "against reach.\n\n"
        "WHAT IT DOES NOT SAY: that the sound set is sufficient. One objection on "
        "a design wrong on 200 testpoints is discrimination, not adequacy, and "
        "the sound set's own limit is measured elsewhere here. The claim is "
        "narrow and it is about the AUDIT COLUMN: unsound members do not merely "
        "add false rejects, they remove the criterion's ability to reject."
    )

def a_perfectly_sound_majority_set_still_false_accepts() -> str:
    """The ceiling result, and the one that closes the corpus rather than a lever.

    `zero_objections_can_be_incompatible_with_correctness` shows that a set
    carrying an over-strict check makes termination a certificate of
    NON-equivalence. The obvious response is to remove the over-strict checks --
    and this is that experiment, run on the largest perfectly sound set the
    corpus can produce, which happens to span a majority.
    """
    return (
        "Measured on k1. MAXSOUND is every one of the 259 corpus bodies that "
        "decides on the known-good design and convicts it nowhere: **68 checks "
        "over 45 of 89 requirements = 51%, A MAJORITY, at a false-reject rate of "
        "ZERO.** It is selected BY the known-good design, so it is a CEILING and "
        "never a score -- but that is what makes the negative below exhaustive "
        "rather than a sampling result.\n\n"
        "A Sonnet editor through the shipped staged-buffer policy, on a design "
        "written from the specification and held out of every selection, reached "
        "**0 objections of 68 in 6 of 14 trials.** Re-scored in its own clean run "
        "directory. All three grade pins green in the same process.\n\n"
        "**THE MITER RETURNS DIFFERS. The design is wrong on 193 of 318 "
        "testpoints -- 61% -- and on nine of its ten declared outputs.**\n\n"
        "EVERY AVAILABLE EXPLANATION IS EXCLUDED BY THE SET'S OWN PROPERTIES. Not "
        "unsoundness: the audit is zero, so unlike the set in "
        "`zero_objections_can_be_incompatible_with_correctness` reaching zero here "
        "is CONSISTENT with equivalence rather than proof against it. Not "
        "thinness: 51% of the specification, the widest sound set the corpus "
        "holds. Not a wrong gradient: divergence fell on both measures, 249 "
        "testpoints to 193 and 2,904 differing cells to 2,798, and one output was "
        "repaired to never differing. Not an editor stopping early: it terminated "
        "with 8 trials unspent because its criterion was satisfied.\n\n"
        "AND THE CORPUS CANNOT FIX IT, WHICH IS THE PART THAT CLOSES THE "
        "QUESTION. Re-deciding all 259 bodies against that design: **124 object, "
        "across 55 of 89 requirements = 62% of the specification, and ZERO of the "
        "124 are sound.** MAXSOUND already IS every sound check in the corpus, so "
        "these are not checks a better selection missed -- there are none to "
        "miss. **No sound set this corpus can produce rejects this design.**\n\n"
        "So the binding constraint is not soundness, span, selection, termination "
        "or the gradient. It is that the checks watch the right ports and pass: "
        "of these 68, four read no real output, three are exposed to a wrong port "
        "and never decide, seven object, and **54 decide where their own port is "
        "wrong and pass**, at 134 objections in 4,804 exposed decisions = 2.8%. "
        "See `the_residue_is_check_strength`."
    )

def the_soundness_boundary_is_reachable_from_one_side_only() -> str:
    """The one prescription this module produces, and it corrects its own claim.

    `strength_and_soundness_are_exchanged_not_traded` measures 34 checks widened
    across the soundness boundary with 0 landing in between, and reads that as a
    partition -- the boundary is not findable. Measured from the OTHER side it is
    findable, and the asymmetry is the actionable result.
    """
    return (
        "Measured on k1, on the two rounds that move a single check across the "
        "same boundary in opposite directions, by the same author family, one "
        "edit each:\n\n"
        "    STRENGTH   sound and blind -> assert MORE   34 checks,  0 adequate =  0%\n"
        "    NARROWING  over-strict -> assert LESS       47 checks,  7 adequate = 15%\n\n"
        "**Two-sided Fisher exact p = 0.0196.** The boundary is reachable from the "
        "over-strict side and not from the weak side.\n\n"
        "WHY THE POPULATIONS ARE COMPARABLE, since that is what the claim rests "
        "on. Both are single-edit repairs of an existing body, both are Haiku, "
        "both got an admissible objection that reads only spec-derived designs -- "
        "'you decided N times and objected zero times' one way, 'you object to N "
        "of 13 independently written implementations' the other. Neither author "
        "saw a known-good design, a held-out design, or any equivalence verdict. "
        "The narrowing round's leak check was 0 violations over 47 prompts.\n\n"
        "SO THE PRESCRIPTION IS TO AUTHOR STRICT AND NARROW, NEVER WEAK AND "
        "STRENGTHEN. A check that objects to most of a spec-derived population is "
        "a repairable check; a check that objects to none of it is, on this "
        "evidence, not. That reverses the direction every repair round on this "
        "plan has pushed -- unexercised, vacuous and off-target all push a check "
        "toward FIRING, and none of them pushes it toward demanding less.\n\n"
        "THE COST, WHICH IS THE HALF THAT MAKES IT A RATE AND NOT A ROUTE. Of the "
        "47, twelve came back VACUOUS -- sound by asserting nothing, which the "
        "pre-registration scores as a loss exactly as harshly as still "
        "over-reaching -- and 24 did not move. Adequacy went 16 to 23 of 89, 18% "
        "to 26%: the largest single-round gain here, and not a majority.\n\n"
        "AND THE ROUTE IS BOUNDED, not merely slow. Its population is the "
        "requirements that have an over-strict body which already catches a "
        "held-out design, and there are 47 of them. Even if every one landed, "
        "adequacy would reach 16 + 47 = 63 of 89 = 71%. At 15% a round on a "
        "shrinking pool it converges well short of that, so this raises the "
        "measured ceiling and does not by itself deliver a majority.\n\n"
        "AND A SECOND ROUND MEASURED THE DECAY, WHICH SETTLES THE CEILING. The 28 "
        "checks still over-strict and still discriminating were narrowed again, "
        "each author shown its own first rewrite and told to find a DIFFERENT "
        "over-reach -- the loop-memory discipline measured effective on RTL "
        "repair. **It landed 1 of 28 = 4%**, against a pre-registered bar of 5 "
        "for the rate holding. Adequacy 23 to 24 of 89.\n\n"
        "THE NUMBER IS THE SAME AS THE OTHER LEVER'S, TO THE UNIT:\n\n"
        "    repair    (push a check to FIRE)     8 of 45 = 18%   ->  1 of 28 = 4%\n"
        "    narrowing (push a check to NARROW)   7 of 47 = 15%   ->  1 of 28 = 4%\n\n"
        "Two levers pushing a check in OPPOSITE directions, with different "
        "objections, produce the same two-round shape. **Stated carefully: the "
        "within-lever decay is p = 0.245 at n = 28 and is NOT independently "
        "significant.** What is solid is that the second round missed its bar and "
        "landed exactly on the precedent, so the first attempt is where a "
        "repair's value is and further rounds are worth about one check each.\n\n"
        "SO THE ROUTE IS BOUNDED IN PRACTICE AS WELL AS IN PRINCIPLE. At the "
        "measured rates it converges near 27-28 of 89 = 31%, against the 45 a "
        "majority needs. **Authoring does not reach a majority on this corpus, "
        "and that is now a decay curve rather than a tally of failed rounds.**"
    )

def the_two_legs_cannot_be_composed_from_separate_bodies() -> str:
    """Why "both legs exist for N requirements" is not "N is reachable".

    `the_soundness_boundary_is_reachable_from_one_side_only` measures a check
    moved across the boundary from each side and reads the asymmetry as a
    prescription. This measures the one configuration neither round had: an
    author shown BOTH ends for the same requirement, and told in numbers where
    the answer sits between them.
    """
    return (
        "Measured on k1, on the 26 requirements where the corpus holds a body "
        "that is SOUND and a body that DISCRIMINATES and never the same body. "
        "One author per requirement, shown both, told each body's conviction "
        "count over 13 independently written implementations, and told outright "
        "that the check the requirement needs objects to a MINORITY of the 13 "
        "and to more than zero. Both failure modes named. Integrity: 26 of 26 "
        "returned, 26 of 26 compile, 0 duplicate bodies across requirements, and "
        "0 returned either input unchanged.\n\n"
        "                     INPUT A   INPUT B   THE MERGE\n"
        "    SOUND                 26         0           8\n"
        "    DISCRIMINATING         0        26          18\n"
        "    **ADEQUATE**           0         0       **0**\n\n"
        "AND ZERO IS THE MINIMUM THE MARGINALS ALLOW, WHICH IS THE CLAIM. "
        "8 + 18 = 26 = n, so the two sets COULD have been disjoint and they "
        "are, exactly: every merge is sound XOR discriminating, never both and "
        "never neither. The overlap expected under independence is 5.5.\n\n"
        "THAT IS THE SECOND ROUND TO LAND ON THE MARGINAL MINIMUM, and it is "
        "tighter than the first. The strength round's 11 + 21 = 32 of 34 left "
        "two requirements free to fall in neither cell; this leaves none.\n\n"
        "AND THE TARGET WAS STATED IN NUMBERS, SO THIS IS NOT A READING "
        "FAILURE. Where the 26 landed on the scale the prompt named: SIX at 0 "
        "convictions of 13, THREE in the 2-4 band the prompt asked for, and "
        "SEVENTEEN at 10-13. **Three hit the band and none of the three is "
        "adequate** -- two are sound and catch no held-out design, one is "
        "unsound and narrow. The minority rule identifies a SOUNDNESS band; "
        "landing in it buys soundness and buys no discrimination.\n\n"
        "THE EXCHANGE IS EXACT ON THE ONE OBJECTION THAT MATTERS. 18 of the 26 "
        "discriminating inputs object to the design the largest perfectly sound "
        "set accepted at zero objections; after the merge 16 still do, and "
        "every one of the 16 is over-strict, so not one can enter a sound set. "
        "The merges that became sound are exactly the merges that stopped "
        "objecting to it.\n\n"
        "SO A CEILING COMPUTED BY COUNTING THE TWO LEGS SEPARATELY DOES NOT "
        "TRANSFER. Over this corpus a sound body exists for 52 of 89 "
        "requirements and a discriminating body for 64, with both present in "
        "different bodies for 50 -- and that 50 counts a vacuous body as half "
        "an adequate check and an over-strict body as the other half. They do "
        "not compose. **Read every 'both legs exist' figure as an upper bound "
        "on a quantity that is not reachable by combining them.**\n\n"
        "TWO LIMITS, AND NEITHER EXPLAINS THE RESULT. The prompt listed the "
        "ports each input reads but not the contract's declared-port block, so "
        "some authors described a DECLARED probe as a signal that does not "
        "exist: 11 of 15 probe-bearing pairs kept one, 4 dropped every one, 1 "
        "added one -- far better than the 12 of 12 a repair round drops, and "
        "the clause that did it is 'use only the ports the two checks already "
        "read'. It cannot explain 0 of 26, because 22 of the 26 dropped no "
        "probe and none of those is adequate either. And it is one author, one "
        "round, one design, at the first-attempt rate -- which on this plan has "
        "always been the high one."
    )


def the_adequacy_filter_does_not_survive_being_a_target() -> str:
    """What happens when the best golden-free filter here is optimised for.

    `adequacy_is_soundness_and_refutability` measures "objects to 1 or 2 of 13"
    at 86% precision on adequacy as a FILTER over checks that landed there by
    themselves, and says outright it must not be used to SELECT. This measures
    the stronger misuse -- handing it to an author as a TARGET, with the check's
    own measured count fed back so it can tell which way it overshot.
    """
    return (
        "Measured on k1, on 24 checks whose conviction count over 13 "
        "independently written implementations sat outside the band. Each author "
        "got its own body, its measured count, the direction to move, the target "
        "stated as a number, and the complete declared-port list. Integrity: 24 "
        "of 24 returned, 24 of 24 compile, 0 duplicates, 0 unchanged.\n\n"
        "                                  before   after\n"
        "    IN BAND -- convicts 1-2 of 13      0       2\n"
        "    SOUND                              7      10\n"
        "    DISCRIMINATING                    17      15\n"
        "    **ADEQUATE**                       0   **1**\n\n"
        "AND THE TWO THAT REACHED THE BAND SETTLE WHAT THE BAND IS. One convicts "
        "2 of 13 and one convicts 1; **both are sound and NEITHER "
        "discriminates**. The rule delivers the leg it was built on and does not "
        "deliver the other one when it is aimed at rather than filtered with.\n\n"
        "AND THE ONE ADEQUATE CHECK CONVICTS 12 OF 13 -- OUTSIDE THE BAND, so "
        "the rule would have rejected the only check the round produced that "
        "works. Both halves fail in the same round on the same population: it "
        "does not drive authors to adequacy, and it does not select the adequate "
        "check when one appears.\n\n"
        "THE FEEDBACK IS NOT THE PROBLEM, AND SAYING SO KEEPS THE NEGATIVE "
        "HONEST. The distribution moved: one check sat between 1 and 5 "
        "convictions before the round and five do after. An author handed the "
        "count can steer. It steers into a region that is sound and blind, "
        "because the count is a soundness signal and there is no second "
        "golden-free signal for the other leg -- discrimination is defined "
        "against a design that is wrong, and every wrong design available is "
        "drawn from the same specification-and-reader pair.\n\n"
        "AND IT IS THE THIRD CONSECUTIVE ROUND TO LAND ON THE MARGINAL MINIMUM, "
        "which is the structural claim this module has been circling:\n\n"
        "    round                              n   SOUND  DISCR  S+D  min  OBS\n"
        "    strength   -- blind, assert MORE  34     11     21    32    0    0\n"
        "    merge      -- both ends shown     26      8     18    26    0    0\n"
        "    band       -- numeric target      24     10     15    25    1    1\n\n"
        "**Three rounds, three instructions, three populations, and every one "
        "lands exactly on the floor its own marginals permit** -- against 6.8, "
        "5.5 and 6.2 expected under independence. No round here has ever "
        "produced an overlap larger than arithmetic forces. The two properties "
        "are not merely anti-correlated across a corpus; they are exchanged one "
        "for one by whatever edit the author makes.\n\n"
        "AND THE ADEQUACY RATE IS 4% FOR THE THIRD TIME. Repair round 2 landed 1 "
        "of 28, narrowing round 2 landed 1 of 28, and this lands 1 of 24 -- "
        "three levers, three different objections, one figure. Adequacy 24 to 25 "
        "of 89 = 28%, against the 45 a majority needs."
    )


def split_cells_are_a_specification_finding() -> str:
    """Why a disagreement cell is escalated, never resolved automatically.

    `disagreement_cells` localises the residue better than anything else here,
    and the natural next step -- have a model resolve those cells, or at least
    flag the ones the specification leaves open -- is measured and does not work.
    """
    return (
        "Measured on k1 over 20 cells drawn from the 3,863 a 13-design "
        "population cannot agree on. Each was put to a fresh reader as ONE "
        "targeted question: one cell, one port, the specification, the declared "
        "interface, and the input sequence from reset, with no design of any "
        "kind. The population majority is right on 60.9% of split cells and on "
        "11 of the 20 sampled; the questioner scored 7 of 20 -- WORSE than the "
        "population, not better. On the 9 cells where the population is wrong it "
        "was right once, and produced the population's exact wrong answer 7 "
        "times. So the correlated error is not an artifact of writing a whole "
        "module under a budget; it is what this text produces in a competent "
        "reader, and no simpler task decorrelates it. Worse for tooling: the "
        "prompt offered 'the specification does not determine this' as a first "
        "class answer, and 0 of 20 used it -- the ambiguity is invisible to the "
        "reader it misleads, so a model cannot be asked to flag the gaps either. "
        "Treat a split cell as a SPECIFICATION defect and route the map to "
        "whoever owns the specification. Do not resolve it with another model, "
        "and do not gate on a model's claim that the text is clear."
    )
