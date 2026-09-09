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
**Corrected after four more authoring rounds: on the grown 484-body corpus it
keeps 108 and 105 spare the known-good design -- 97%, not 100% -- and the three
exceptions are bodies those rounds produced.** The golden-free span rose with it,
rule B reaching 50 of 89 = 56% at a 10% false-reject rate and rule C 44 of 89 =
49% at 3%; neither can be an accept criterion, for the reason the audit column
always gives. `golden_free_span_grew_and_the_precision_did_not_hold` carries the
table and the correction.

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

AND GROWING THE CORPUS AND RE-RUNNING IT CHANGES NOTHING. Rebuilt over the
484-body corpus the authoring rounds produced, the same construction gives 119
checks over 52 of 89 = 58% at a zero false-reject rate, with 31 discriminating
members against 18. An editor drove the same held-out design to 0 objections and
the miter still says DIFFERS -- at 187 of 318 testpoints, with objections,
testpoints and cells all falling together and one output repaired, so not even a
wrong gradient is left to blame. The objection rate on exposed decisions is 3.9%
both times. `a_wider_sound_set_lands_the_same_design_in_the_same_place` carries
it.

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
**Corrected on a second held-out design:
`the_consensus_is_an_oracle_even_though_it_is_not_a_ranking`.**

AND TWO OF THE ENTRIES HERE ARE ABOUT THE DRIVER RATHER THAN THE CRITERION,
because both cost a measurement before they were understood. A repair loop
latches on the COUNT of passing requirements, so a criterion encoded one
pseudo-requirement per output cannot see an edit that removes 70% of the
disagreement and leaves every output still wrong somewhere -- it reads
"passing 1 -> 1" and rolls the edit back. Two numbers are needed and they are
not the same number: a fine one to steer, a coarse one to judge.
`a_ratchet_on_counts_refuses_an_improvement_it_cannot_see` carries it. And a run
directory written by two agents at once yields a design, a state file and a score
that describe different moments, with nothing in it saying so;
`a_run_directory_written_by_two_agents_is_not_a_measurement` carries the tell and
the only remedy, which is to archive it unread and start again.

AND THE SAME GRANULARITY QUESTION HAS A SECOND HALF, AT THE OTHER END OF THE
PIPELINE. Every judgement here is of a WHOLE BODY, and a requirement states
several obligations, so one over-reaching obligation makes a body unsound and
takes its others down with it. 307 bodies are unsound AND discriminating and
they span 61 of 89 requirements = 69%, against 17 = 19% with an adequate body --
which is the size of the prize. Splitting each body along the objection reasons
it itself emits buys +4 requirements, is GOLDEN-SELECTED and therefore a ceiling,
and is blind to 78% of its own population because that many bodies print one
message for every conviction they make. What blinds it is the author's detail
string rather than the check, which is free to fix.
`a_body_is_judged_whole_and_its_obligations_are_not` carries it, including why
even the optimistic extrapolation stops short of a majority.
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


def golden_free_span_grew_and_the_precision_did_not_hold() -> str:
    """The golden-free score after four authoring rounds, and a correction.

    `the_minority_rule_is_precise_and_that_is_what_it_costs` reports the rule at
    59 of 59 -- PERFECT precision -- on a 259-body corpus. Precision is a
    property of the population a rule is applied to, and the corpus has since
    grown to 484. Re-measured, it is not perfect.
    """
    return (
        "Measured on k1 over 484 check bodies -- the original 259 plus the "
        "narrowing, merge and band rounds. Every row below is produced by a rule "
        "reading only spec-derived designs; the audit is computed last and feeds "
        "nothing.\n\n"
        "    rule                        checks   requirements   of 89   *audit*\n"
        "    C  convicts <= 2 of 13        108         44          49%    *3%*\n"
        "    B  convicts a minority        125         50        **56%**  *10%*\n"
        "    the ceiling, selected BY the\n"
        "    known-good design            126         52          58%     *0*\n\n"
        "**A GOLDEN-FREE SET NOW SPANS 56% OF THE SPECIFICATION**, up from the "
        "51% the same rule reached before these rounds, and rule C is up from "
        "44% to 49%. The ceiling moved 51% to 58%, so the golden-free rules "
        "tracked it rather than closing on it.\n\n"
        "**AND SPAN IS STILL NOT AN ACCEPT CRITERION, WHICH IS THE HALF THAT "
        "MATTERS.** 13 of rule B's 125 members convict the known-good design, so "
        "that design scores 13 against its own criterion and any design scoring "
        "zero is a different design -- the arithmetic that made the earlier "
        "rule-B run's termination a certificate of NON-equivalence. Rule C is "
        "the same defect in miniature at 3.\n\n"
        "THE CORRECTION, AND IT IS TO A HEADLINE HERE. The minority rule at "
        "threshold 2 was measured 59 of 59 -- perfect -- and quoted as the best "
        "golden-free soundness instrument by a wide margin. On the grown corpus "
        "it keeps 108 and **105 of them spare the known-good design: 97%, not "
        "100%**, against a base rate of 126 sound among 424 deciding = 30%. That "
        "is a 3.2x lift at n = 108 and it is still the best instrument here -- "
        "but the perfect figure was a property of the smaller population, and "
        "the three exceptions are bodies these authoring rounds produced.\n\n"
        "SO THE RULE DID NOT DEGRADE BY BEING WRONG; IT DEGRADED BY BEING "
        "APPLIED TO CHECKS AUTHORED AGAINST IT. Three of the rounds scored here "
        "used the conviction count as an objection or a target, and the checks "
        "that came back are the ones the rule now misjudges. **A golden-free "
        "gate measured on a corpus it did not shape is measuring something else "
        "once it starts shaping one**, which is the same Goodhart the target "
        "round measured directly and is why the audit column must be recomputed "
        "after every authoring round rather than carried forward."
    )


def a_wider_sound_set_lands_the_same_design_in_the_same_place() -> str:
    """The ceiling result, re-run on the corpus four authoring rounds grew.

    `a_perfectly_sound_majority_set_still_false_accepts` closed the corpus AS IT
    THEN WAS: no sound body objected to the design that set accepted, so there
    were none a better rule could have found. Bodies have since been authored
    that did not exist. This is the same construction over the larger corpus,
    and it is the only run whose input had changed.
    """
    return (
        "Measured on k1. The set is every body in the 484-body corpus that "
        "decides on the known-good design and convicts it nowhere -- the same "
        "construction as before, on a corpus grown by the narrowing, merge and "
        "band rounds:\n\n"
        "                       checks   span        *audit*  DISCRIMINATING\n"
        "    the earlier set       68   45 of 89=51%    *0*        18\n"
        "    **this one**         119   52 of 89=58%    *0*        31\n\n"
        "75% more checks, seven more points of span, 72% more discriminating "
        "members, at the same zero false-reject rate. The extra discrimination "
        "is real where it can be seen: **12 objections against a held-out design "
        "at init where the earlier set found 7.**\n\n"
        "A Sonnet editor through the shipped edit-session policy, on that design "
        "-- written from the specification by an agent forbidden to open any "
        "other, and held out of every selection that produced this set -- reached "
        "**0 objections of 119 on trial 7 of 14**, and the reset-constrained "
        "bounded miter says **DIFFERS**, with all three grade pins green in the "
        "same process. The zero-objection design was re-scored from scratch in "
        "its own run directory, 0 of 119, before any of this was quoted.\n\n"
        "                    objections   testpoints differing   cells   repaired\n"
        "    at init            12 of 119    249 of 318 (78%)     2,904    none\n"
        "    the earlier set     0 of  68    193 of 318 (61%)     2,798    one output\n"
        "    **this set**        0 of 119    187 of 318 (59%)     2,786    one output\n\n"
        "**AND THE GRADIENT IS CORRECT THE WHOLE WAY, WHICH IS WHAT MAKES THIS "
        "THE CLEAN NEGATIVE.** Objections, testpoints and cells all fell "
        "together and one output was repaired to never differing, with no "
        "inversion over the final approach -- unlike the earlier over-strict run, "
        "whose last three objections cost 8 testpoints and 342 cells and broke "
        "the output it had repaired. Nothing went backwards here and the design "
        "is still wrong on 59% of the suite.\n\n"
        "SO EVERY REMAINING EXPLANATION IS EXCLUDED. Not unsoundness (audit zero "
        "by construction). Not thinness (the widest sound set this corpus has "
        "produced). Not weak discrimination (31 adequate members against 18). "
        "Not a wrong gradient (all four measures moved together). Not an editor "
        "stopping early (7 trials unspent, and its criterion is correct that no "
        "check objects).\n\n"
        "**AND THE RESIDUE DID NOT MOVE, TO ONE DECIMAL PLACE.** Judged only on "
        "the testpoints where a port each check itself reads is wrong: the "
        "earlier 50-check set objected on 134 of 3,399 exposed decisions = 3.9%; "
        "this one objects on **300 of 7,677 = 3.9%**. Twice the decisions, twice "
        "the objections, the identical rate, and the same two checks deciding on "
        "249 of 249 exposed testpoints without objecting once. **Check strength "
        "is not a property of a set's size, its span, or its selection rule.**"
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


def a_vacuous_check_is_not_a_defect_and_the_routing_assumes_it_is() -> str:
    """Why "convicts no candidate" must not route to a strengthen repair.

    The alternating loop classifies a check by how many of N spec-derived
    designs it objects to: none is VACUOUS, a minority is KEEP, a majority is
    OVER-STRICT. The first of those three is the one with no instrument behind
    it, and this measures what that costs on the set the loop actually holds.
    """
    return (
        "Measured on k1 over a 119-body set and a SEVEN-design population, with "
        "adequacy audited last: SOUND means the check decides on the known-good "
        "design and convicts it nowhere, ADEQUATE adds that it convicts a design "
        "held out of every selection.\n\n"
        "| state | checks | sound | adequate |\n"
        "|---|---|---|---|\n"
        "| VACUOUS -- convicts 0 of 7 | 82 | 82 = 100% | **8** |\n"
        "| KEEP -- convicts 1 to 3 | 21 | 19 = 90% | **6** |\n"
        "| OVER-STRICT -- convicts 4 to 7 | 16 | 12 | 0 |\n\n"
        "**8 OF THE 14 ADEQUATE CHECKS ARE CLASSIFIED VACUOUS**, so the routing "
        "sends them to the one repair move measured to trade soundness for "
        "discrimination 34 times out of 34. No threshold reaches them: they "
        "convict ZERO candidates, so the adequate count is the same 14 at every "
        "cut from 1 to 7. The population is simply RIGHT about those "
        "requirements, which is what this module's `refuted_by` docstring warns "
        "about in the abstract and this measures at scale -- it was 3 of 14 when "
        "first seen and it is 8 of 14 here.\n\n"
        "TWO CONSEQUENCES, AND THE SECOND IS THE ONE TO BUILD ON.\n\n"
        "The keep state is the only one BELOW the base rate on soundness -- 90% "
        "against 95% -- and it is the only one worth keeping. Its two unsound "
        "members are the price of its six adequate ones, and the 82 that spare "
        "the known-good design perfectly are the 82 that mostly say nothing. A "
        "cut chosen for soundness precision is choosing against adequacy.\n\n"
        "And the instrument the VACUOUS state lacks already exists here: "
        "`refuted_by`. A check that spares every candidate and convicts a "
        "mechanical one-line mutant of one has demonstrated it CAN fail, with no "
        "known-good design and no model call. **Route a refutable vacuous check "
        "to KEEP, not to a repair.** Until that leg runs, an accept gate is what "
        "contains the damage -- discard a strengthened body unless it lands in "
        "the keep band, so an adequate vacuous check survives the round "
        "unchanged.\n\n"
        "WHAT THIS DOES NOT SAY. It is not a measurement of the minority rule's "
        "precision. This body set descends from a soundness-selected set and a "
        "gated repair round, so it is 95% sound before any rule touches it, and "
        "the cut reads 1.03x lift on it against the 100%-at-a-31%-base-rate "
        "measured on the full corpus. A soundness filter cannot be calibrated on "
        "a population already selected for soundness; what this table answers is "
        "the different question of what the cut is worth INSIDE the loop."
    )


def new_evidence_moves_the_rule_and_the_audit_together() -> str:
    """The strongest evidence here that the golden-free routing tracks soundness.

    Every other figure in this module compares a rule against an audit on ONE
    body of evidence, where a threshold can be fitted. This is a before/after
    across an evidence change neither column had seen.
    """
    return (
        "Measured on k1. A stimulus round staged 18 testpoints on axes the suite "
        "had never exercised -- bus errors, requests aborted mid-transaction, "
        "reset arriving while a transaction is outstanding, back-to-back "
        "refills, and the data-valid strobe pausing mid-sequence -- taking the "
        "evidence from 330 to 348 testpoints. Both halves were scored INSIDE ONE "
        "RENDER, because a probe declaration fixes the row-compression key and "
        "two renders differ in every row.\n\n"
        "    checks whose golden-free STATE changed        8\n"
        "    checks that BECAME unsound on the audit       8\n"
        "    intersection                                  8\n"
        "    state-changed but still sound                 0\n"
        "    newly unsound but state unchanged             0\n\n"
        "**EVERY CHECK THE RULE MOVED TO OVER-STRICT IS EXACTLY A CHECK THAT "
        "STARTED CONVICTING THE KNOWN-GOOD DESIGN, AND NO OTHER CHECK DID "
        "EITHER.** The eight went from 0 or 1 convictions to 6 or 7 of a "
        "seven-design population, so it is a decisive conviction event and not a "
        "marginal one. Nothing was fitted: the movement was caused by stimulus "
        "neither column had seen, and the two were computed independently.\n\n"
        "This is the mechanism the conviction-count rule claims, observed rather "
        "than assumed -- a demand no independent implementation satisfies is "
        "more likely one the check misread than one all those authors got "
        "wrong, and on all eight the known-good design agrees with the "
        "authors.\n\n"
        "AND THE SAME ROUND BOUGHT NO SPAN, WHICH IS THE HALF TO CARRY. The keep "
        "set went 21 checks over 16 requirements to 17 over 12, while the "
        "ADEQUATE count did not move at all -- 14 before, 14 after, every "
        "adequate member surviving. What the wider evidence removed was four "
        "FALSE keeps. So a stimulus round is an EVIDENCE move, not a span move: "
        "it can only make the measurement more nearly right, and a measurement "
        "getting more nearly right looks like a loss whenever the previous "
        "number was too high. **Quote a keep-set span only beside the evidence "
        "it was measured on. A span that falls when the evidence widens was "
        "never a span.**"
    )


def the_keep_state_must_include_the_zero() -> str:
    """The golden-free rule's best form, measured on the whole authored corpus.

    A conviction-count rule has two natural boundaries: drop a check that
    convicts most of the population, and drop one that convicts none of it. The
    second is the one that keeps getting reintroduced, and it is the one that
    does not pay.
    """
    return (
        "Measured on k1 over ALL 484 authored bodies -- not the "
        "soundness-selected subset an earlier loop ran on -- against SEVEN "
        "independently written spec-derived designs and 348 testpoints. The "
        "audit is computed last and feeds nothing.\n\n"
        "| rule | checks | requirements | of 89 | *audit* | *adequate* |\n"
        "|---|---|---|---|---|---|\n"
        "| convicts 1-3 of 7 | 27 | 14 | 16% | *48%* | *6* |\n"
        "| **convicts AT MOST 3 of 7** | **111** | **44** | **49%** | ***12%*** | ***14*** |\n"
        "| convicts 0 of 7 alone | 84 | 35 | 39% | *0%* | *8* |\n"
        "| convicts 4-7 of 7 | 313 | 61 | 69% | *96%* | *1* |\n"
        "| everything that decides | 424 | 67 | 75% | *74%* | *15* |\n\n"
        "**REQUIRING A KEPT CHECK TO CONVICT AT LEAST ONE CANDIDATE COSTS 30 "
        "REQUIREMENTS OF SPAN AND QUADRUPLES THE FALSE-REJECT RATE**, and throws "
        "away 8 of the corpus's 15 adequate checks. It is not a filter that "
        "trades reach for precision; it loses on both. The fix is one "
        "comparison: keep a check that convicts AT MOST half the population, "
        "including none of it.\n\n"
        "44 of 89 = 49% at a 12% false-reject rate, holding 14 of the 15 "
        "adequate checks, is the best golden-free pair measured here -- one "
        "requirement short of a majority, and the first time reach and precision "
        "moved the same way at once.\n\n"
        "AND THE CUT ITSELF, RE-DERIVED FOR THIS POPULATION. It was calibrated "
        "at 100% precision on THIRTEEN designs against a 31% base rate. On seven "
        "designs and 484 bodies the base rate is 26% and the cut at half the "
        "population reads **88% precision at 88% recall, a 3.34x lift, n=111**. "
        "The 100% does not survive the population shrink and the rule does. A "
        "conviction threshold is a function of the population SIZE and must be "
        "re-derived when N changes, never carried across.\n\n"
        "THE CORRECTION THIS REPLACES. The same rule measured on a body set "
        "descended from a soundness-selected set reads a 10% false-reject rate. "
        "That is an artefact of the population, not a property of the rule: an "
        "audit whose denominator was chosen by the instrument being audited is a "
        "lower bound and must be labelled as one."
    )


def the_editor_can_read_a_state_it_cannot_argue_about() -> str:
    """The validation run, and the one thing that made the editor's refusal right.

    An editor handed an over-strict check has, on this plan's own measurement,
    no way to tell it from a legitimate demand: it scored 1 of 3 on that
    judgement in an earlier run and its stated reason was false. This is the
    same judgement made correctly, and the difference is what the check reads.
    """
    return (
        "Measured on k1. A 21-check set over 16 of 89 requirements, selected by "
        "a conviction-count rule over seven spec-derived designs, drove a Sonnet "
        "editor on a design written from the specification and held out of every "
        "selection. No reference design, no reference trace, no expected "
        "value.\n\n"
        "| | objections of 21 | testpoints differing | cells | trials |\n"
        "|---|---|---|---|---|\n"
        "| at init | 8 | 279 of 348 = 80% | 4,450 | 0 |\n"
        "| after the loop | **2** | **223 of 348 = 64%** | **3,969** | **3 of 14** |\n\n"
        "Objections fell 75%, divergence 20% and cells 11%, all the same way, in "
        "three trials with eleven unused. The bounded miter says DIFFERS with all "
        "three pins green in the same process, so the set is still too SPARSE to "
        "finish -- a statement about its size, not its direction.\n\n"
        "**AND THE TWO OBJECTIONS IT COULD NOT CLEAR ARE EXACTLY THE TWO CHECKS "
        "THE AUDIT CALLS UNSOUND.** The editor refused them with a reason it "
        "could check rather than argue: the requirement demands something on "
        "entry to a state whose feature is compiled out of this build, and the "
        "check fires that template on ordinary back-to-back traffic. Verified "
        "independently and exactly -- the state's probe is true in 0 of the "
        "reference's 5,723 rows across 348 testpoints.\n\n"
        "    earlier ceiling run   1 of 3   refused one unsound check and two\n"
        "                                   sound ones, for a reason that is false\n"
        "    this run              2 of 2   refused exactly the unsound pair, for\n"
        "                                   a reason readable off the trace\n\n"
        "**THE DIFFERENCE IS THAT THE STATE IS A DECLARED PROBE.** 'This state "
        "never occurs' stops being a belief the editor argues for and becomes a "
        "fact it reads out of recorded rows. That is the probe architecture "
        "paying somewhere this plan never looked -- not in the check author, in "
        "the EDITOR -- and it is the first time here that the editor's soundness "
        "judgement was right for a reason that can be verified rather than "
        "asserted. n is two; the mechanism is what to carry, not the rate."
    )


def an_occurrence_claim_is_checkable_and_a_meaning_claim_is_not() -> str:
    """CORRECTS `the_editor_can_read_a_state_it_cannot_argue_about`.

    That entry reported the editor's soundness judgement as 2 of 2 on a
    21-check set. On a 111-check set the same editor family named FIVE
    requirements as the check's fault and one of them is unsound, so the 2-of-2
    was small-n. What survives is the distinction between the two kinds of
    claim, which is the part worth carrying.
    """
    return (
        "Measured on k1, two editor runs on the same held-out design with the "
        "same evidence. **The rate is 1 of 5, not 2 of 2** -- the smaller set "
        "happened to stop on the unsound pair. The DISTINCTION is what "
        "survives:\n\n"
        "    OCCURRENCE  'this state never happens'      RIGHT, 1 of 1\n"
        "    MEANING     'the requirement owes one X'    WRONG, 0 of 4\n\n"
        "The occurrence claim is a count over recorded rows and the state is a "
        "declared probe, so the editor counted it -- 0 of 27,278 edges -- and it "
        "is the one check in the set the audit calls unsound. The four meaning "
        "claims are readings of a sentence: whether a requirement owes one "
        "increment or two, whether an enable governs acceptance or continuation. "
        "The editor supported each with real counted evidence from the traces, "
        "and the evidence was about what the DESIGN does, never about what the "
        "REQUIREMENT means -- which is the question it was answering.\n\n"
        "**A probe makes an occurrence claim decidable and does nothing for a "
        "meaning claim.** That is a bound on what any quantity of trace evidence "
        "can buy an editor arguing with a check, and it is why an editor's "
        "refusal must be recorded rather than trusted."
    )


def more_span_did_not_buy_more_correctness() -> str:
    """Two sets, one design, a 3x span gap, and one testpoint of difference."""
    return (
        "Measured on k1. Two golden-free-selected sets drove the same Sonnet "
        "editor on the same design -- written from the specification, held out "
        "of every selection -- over the same 348-testpoint suite, graded by the "
        "same bounded miter with all three pins green.\n\n"
        "| set | span | objections | testpoints differing | cells | trials |\n"
        "|---|---|---|---|---|---|\n"
        "| 21 checks | 16 of 89 = 18% | 8 -> 2 | 279 -> **223 = 64%** | 4,450 -> 3,969 | 3 of 14 |\n"
        "| 111 checks | 44 of 89 = **49%** | 23 -> 7 | 279 -> **220 = 63%** | 4,450 -> 3,834 | 5 of 14 |\n\n"
        "**THREE TIMES THE SPAN LANDED THE DESIGN THREE TESTPOINTS CLOSER**, and "
        "both are DIFFERS. Spanning a majority of the specification and driving "
        "a design to correctness are independent properties of a check set, and "
        "the second does not follow from the first at any span this corpus "
        "reaches. Both runs also stopped with most of their trial budget unspent "
        "and with only checks the editor declined left, so neither is a "
        "measurement of the editor running out of room."
    )


def selection_is_exhausted_and_authoring_is_the_constraint() -> str:
    """Whether a better rule could have caught what a check set missed.

    Every "the rule dropped the good checks" hypothesis on this plan has been
    argued rather than counted. This counts it: all 484 authored bodies
    re-decided against the design a golden-free set actually produced.
    """
    return (
        "Measured on k1 against the design a 111-check golden-free set drove a "
        "Sonnet editor to -- 7 objections remaining, and the bounded miter says "
        "DIFFERS at 63% of testpoints.\n\n"
        "    corpus bodies OBJECTING to it        278 of 484, over 60 of 89 = 67%\n"
        "    of those, SOUND on the reference       6\n"
        "    of those six, already in the keep set  5\n"
        "    requirements a sound body catches      6 = 7% of 89\n\n"
        "**THE CORPUS KNOWS THE DESIGN IS WRONG ACROSS 67% OF THE SPECIFICATION "
        "AND CAN SAY SO SOUNDLY ON 7%, AND THE GOLDEN-FREE RULE HAS ALREADY "
        "FOUND FIVE OF THE SIX.** 272 of the 278 catches are bought by also "
        "condemning the reference. So this is not a selection failure with a "
        "better rule waiting to be found -- there is ONE more sound catcher in "
        "the whole corpus, and no rule can select what was never written.\n\n"
        "AND THE RESIDUE HAS A NUMBER ON THIS SET. Restricted to the keep set and "
        "to decisions where a port THE CHECK ITSELF READS is wrong -- a check "
        "watching one output is not blind for passing a defect on another -- it "
        "objects on **95 of 6,521 exposed decisions = 1.5%**. This plan measured "
        "3.9% twice, on earlier sets against designs no editor had worked on; "
        "1.5% is what is left once an editor has cleared everything the set "
        "could see, which is the same statement one round further on.\n\n"
        "**So the binding constraint is AUTHORING, and it is not the NUMBER of "
        "checks -- it is what a check asserts.** 484 bodies over 68 requirements "
        "yield six that can soundly convict a design wrong on 63% of the suite."
    )


def narrowing_the_span_gap_reaches_a_majority() -> str:
    """The one authoring move with a positive yield, aimed where span can grow.

    Selection is exhausted (see
    `selection_is_exhausted_and_authoring_is_the_constraint`), so the remaining
    lever is authoring. Of every authoring round measured on this plan, exactly
    one has a positive yield: narrowing a check that objects to most of an
    independently written population.
    """
    return (
        "Measured on k1. The population is the ONLY one in which narrowing can "
        "add span: the 23 requirements holding an OVER-STRICT body (convicts 4 "
        "to 7 of seven spec-derived designs) and no keepable one. One call each, "
        "on the least over-strict body.\n\n"
        "Admissible and checked before dispatch -- the objection is 'your check "
        "objects to N of seven independently written implementations of this "
        "specification', with no known-good design, no held-out design and no "
        "equivalence verdict in it. Leak check: 0 violations over 23 prompts "
        "against 182 lines of the reference's source. Integrity: 23 of 23 "
        "returned, 23 parse, 0 duplicates, 0 unchanged.\n\n"
        "    23 calls, 6 ACCEPTED by the gate = 26%\n"
        "      all six sound; two of them adequate\n"
        "      17 refused: 16 still over-strict, 1 silent, 0 gone blind\n\n"
        "| the golden-free keep set | checks | requirements | of 89 | *audit* | *adequate* |\n"
        "|---|---|---|---|---|---|\n"
        "| before | 111 | 44 | 49% | *12%* | *14* |\n"
        "| **after** | **117** | **50** | **56%** | ***11%*** | ***16*** |\n\n"
        "**SPAN UP, FALSE REJECTS DOWN, ADEQUACY UP -- the first round here where "
        "all three moved the right way at once.** The landing rate is 26% against "
        "an earlier 15% and 4%, because the population was chosen tightly: one "
        "body per requirement, the least over-strict, only where span could be "
        "gained, with the conviction cut re-derived for the population size.\n\n"
        "**AND 56% SPAN IS NOT 56% ADEQUACY.** The set carries 16 "
        "measured-adequate checks -- sound, and objecting to a design held out of "
        "every selection -- which is 16 of 89 = 18% of the specification. Quoting "
        "the span without the adequacy is the defect this module's own history "
        "has retracted headlines for."
    )


def the_refutable_leg_predicts_discrimination_and_still_must_not_select() -> str:
    """A golden-free substitute for adequacy, measured, and what it turned into.

    Adequacy needs a known-good design for one leg and a held-out wrong one for
    the other, so it cannot be a reported score; and across two editor runs it
    did not predict the grade. This is the replacement that was proposed for it
    and what happened when it was measured.
    """
    return (
        "Measured on k1 over a 117-check set. The proposal was: on the "
        "situations where independently written implementations DISAGREE about a "
        "port a check reads, how often does it say anything? The predictor is "
        "computed on seven candidates and the outcome on a design held out of "
        "everything, so the two share no evidence.\n\n"
        "| rule | checks | catch the held-out design | precision | *lift over 22%* |\n"
        "|---|---|---|---|---|\n"
        "| every check that decides | 113 | 25 | 22% | *1.00x* |\n"
        "| convicts >= 1 candidate | 28 | 16 | **57%** | ***2.58x*** |\n"
        "| objects in a DISPUTED situation | 28 | 16 | **57%** | ***2.58x*** |\n\n"
        "**THE TWO SETS ARE IDENTICAL -- the same 28 checks, nothing in either "
        "difference.** At testpoint granularity 64% of (testpoint, port) pairs "
        "are already disputed, against the 11% `disagreement_cells` reports per "
        "CELL, so the filter removes nothing and the substitute is the refutable "
        "leg under a new name.\n\n"
        "WHY ONLY THE WEAK TEST WAS AVAILABLE, and it is structural. The "
        "transactional view compresses each design's rows independently, so row "
        "i of one candidate is not row i of another and a cell-level comparison "
        "has nothing to align on. A cell-level disagreement strength would need "
        "raw-edge alignment and is untested.\n\n"
        "**WHAT SURVIVES: the refutable leg predicts DISCRIMINATION at 57% "
        "against a 22% base, 2.58x, n=28, golden-free and with no model call** -- "
        "an instrument for the half of adequacy that never had one. **AND IT "
        "STILL MUST NOT SELECT.** It misses 9 of the 25 catchers -- sound and "
        "blind checks that catch a wrong design the candidates happen to get "
        "right -- and as a keep rule it was measured to cost 30 requirements of "
        "span and quadruple the false-reject rate. Report with it; never select "
        "with it."
    )


def a_majority_span_set_satisfied_in_full_is_still_not_equivalent() -> str:
    """The finish condition, run on a set spanning a majority of a specification.

    Every earlier negative here had an available excuse -- the set was unsound,
    or thin, or badly selected, or the editor stopped early. This one has none
    of them, and the residue it leaves is zero.
    """
    return (
        "Measured on k1. A 117-check set over 50 of 89 requirements = 56%, "
        "selected by a conviction-count rule over seven spec-derived designs and "
        "nothing else, drove a Sonnet editor on a design written from the "
        "specification and held out of every selection.\n\n"
        "    init  25 objections over 18 requirements\n"
        "      1    9\n"
        "      2    4\n"
        "      3    4   did not latch; the requirement ratchet refused it, correctly\n"
        "      4    2   49 of 50 requirements pass, 4 of 14 trials used\n\n"
        "The two it stopped on are exactly the two the audit calls UNSOUND -- "
        "both demanding something on entry to a state whose feature is compiled "
        "out of the build, verified twice as an occurrence claim: that state's "
        "probe is true in 0 of the reference's 5,723 rows and 0 of the accepted "
        "design's 6,127. **So the design satisfies every SOUND check the set "
        "contains.**\n\n"
        "    testpoints differing   279 of 348 = 80%  ->  236 = 68%\n"
        "    differing cells                   4,450  ->  3,533\n"
        "    GRADE                                        DIFFERS, three pins green\n\n"
        "**AND THE RESIDUE IS ZERO.** Restricted to that set and to decisions "
        "where a port THE CHECK ITSELF READS is wrong: **0 objections in 6,542 "
        "exposed decisions = 0.0%.** The design is wrong on 236 testpoints and "
        "every sound check in a majority-span set watches it happen and says "
        "nothing. Earlier sets measured 3.9% twice and 1.5% once.\n\n"
        "**EVERY AVAILABLE EXCUSE IS EXCLUDED BY THE RUN'S OWN PROPERTIES.** Not "
        "soundness -- every sound member is satisfied. Not span -- a majority. "
        "Not selection -- five of the corpus's six sound catchers were already "
        "kept. Not stimulus -- 348 testpoints, the design driven wrong on 236. "
        "Not the editor -- 4 of 14 trials, stopping on checks it disproved by "
        "counting. Not the gradient -- objections, cells and testpoints all fell "
        "together inside the run.\n\n"
        "**WHAT IS LEFT IS WHAT A CHECK ASSERTS: a fragment of its requirement, "
        "satisfied by a design that violates the rest of the sentence.** Span is "
        "not the quantity to optimise, and a set can span a majority, be "
        "satisfied in full, and certify a design wrong on two thirds of its "
        "observable behaviour."
    )


def a_gate_makes_a_failing_repair_free_without_making_it_work() -> str:
    """The strength lever, re-run with an accept gate, and what the gate buys.

    Strength repair -- ask an author to assert every obligation in its
    requirement's sentence -- is the only lever aimed at what
    `the_residue_is_check_strength` names. It was measured once at 34 of 34
    crossing into over-strictness and 0 landing.
    """
    return (
        "Measured on k1 over 40 requirements whose keep-set check convicts NONE "
        "of seven independently written spec-derived designs. Gate: accept iff "
        "the new body convicts 1 to 3 of the seven and the old convicted 0 -- a "
        "conviction count, so golden-free.\n\n"
        "    calls                                40\n"
        "    ACCEPTED by the gate                  3 = 8%, all sound, two adequate\n"
        "    crossed to over-strict, discarded    21\n"
        "    still convict none, discarded        16\n\n"
        "**THE GATE IS THE ENTIRE DIFFERENCE FROM THE ROUND THAT FAILED.** "
        "Banking every body would have taken this round's false-reject count "
        "from 0 to 19 of 40; the gate keeps 0. The authors did not improve -- 21 "
        "of 40 still crossed, as 34 of 34 did before. What changed is that "
        "crossing now costs nothing, so a lever that lands 8% is worth running "
        "and a lever that lands 8% ungated is not.\n\n"
        "**AND 8% IS NOT ENOUGH TO BUILD ON.** The pre-registered bar was 5 of 40 "
        "to justify re-validating the set; 3 lands in the band that says record "
        "the rate and stop, and no further validation run was dispatched. Moving "
        "a bar after seeing the number is the defect this module's history is "
        "made of.\n\n"
        "A PROMPT DEFECT IN THIS ROUND, AND IT BIASES AGAINST IT. The prompt "
        "enumerated the declared outputs and probes, said 'do not invent any "
        "other signal name', and never enumerated the declared INPUTS -- one "
        "author called a declared input 'NOT in the declared interface'. **11 of "
        "40 strengthened bodies dropped an input the old body read.** A check "
        "that drops an input it needs asserts LESS, which is the opposite of what "
        "the round asks, so 3 of 40 is a FLOOR and this is not a clean test of "
        "the lever."
    )


def the_consensus_is_an_oracle_even_though_it_is_not_a_ranking() -> str:
    """CORRECTS `accuracy_is_the_wrong_axis_for_a_reference`, which closed this
    route on a sample of one held-out design.

    That entry reports a unanimous consensus ranking the known-good design 15 of
    16 while every population member AND a held-out design scored 0, and
    concludes a consensus "has nothing to say to any design a
    specification-reading author would write". Measured again on a second
    held-out design, that is too strong.
    """
    return (
        "Measured on k1. Seven designs written independently from the "
        "specification by agents forbidden to open any other implementation, all "
        "run on one 348-testpoint stimulus. Wherever all seven produce the "
        "identical value at a (clock edge, DECLARED OUTPUT) sample, that value "
        "is the reference: **240,573 unanimous cells**.\n\n"
        "Declared outputs only, deliberately -- two output-equivalent designs "
        "may encode their states differently, so demanding the population's "
        "value at a probe would convict a correct design for its encoding. Raw "
        "edges, not transactional rows, because the transactional view "
        "compresses each design independently and cannot be aligned across "
        "designs.\n\n"
        "    a population member (the control)          0   by construction\n"
        "    THE KNOWN-GOOD DESIGN                  2,073   = 0.86%\n"
        "    held-out L, unedited                   9,857\n"
        "    held-out L, after a 117-check loop     5,602\n\n"
        "**THE KNOWN-GOOD DESIGN SCORES 4.8x BETTER THAN THE HELD-OUT ONE** -- "
        "the first instrument here on which it is clearly the best "
        "non-population design -- and its false-reject rate is known IN ADVANCE, "
        "which no check set's ever is.\n\n"
        "**ZERO IS STILL NOT THE ACCEPT CRITERION.** A design scoring zero has "
        "matched the population everywhere including the 2,073 cells where the "
        "population is wrong, which is evidence against equivalence by the same "
        "arithmetic that makes an over-strict check set's zero fatal. The "
        "criterion is DESCENT under a trial budget.\n\n"
        "AND IT SUPPLIES THE ONE THING AN EDITOR HAS NEVER HAD HERE: an "
        "expected value that is OBSERVED rather than reconstructed. Not "
        "synthesised, not inferred -- what seven agents who never saw each "
        "other's work all produced at that moment.\n\n"
        "**THE CORRECTION.** The earlier entry closed this route because held-out "
        "J scored 0. Held-out L, written the same way by the same kind of agent "
        "and held out of everything, scores 9,857. The discrimination is a "
        "property of the (reference, design) PAIR, as the both-cell turned out to "
        "be. THREE THINGS DIFFER BETWEEN THE TWO MEASUREMENTS AND CANNOT BE "
        "SEPARATED -- thirteen designs against seven, 318 testpoints against 348, "
        "all cells against declared outputs only -- and unanimity over seven is "
        "easier than over thirteen, so this table has more cells and more chances "
        "to disagree. The gap is far too large to be only that. The honest "
        "statement is that the route was closed on a sample of one held-out "
        "design and should not have been."
    )


def a_ratchet_on_counts_refuses_an_improvement_it_cannot_see() -> str:
    """The granularity of a repair loop's ratchet is a proxy-metric choice, and
    the coarse one is measured to REFUSE a real improvement.

    `_EditSession.commit` latches an edit when the COUNT of passing requirements
    rises. That is the pipeline's own accept rule and it is not wrong; what is
    wrong is what a driver hands it as a "requirement" when the criterion is not
    a check set.
    """
    return (
        "Driving the editor on the consensus reference (one expected value per "
        "declared output per raw edge, from seven independently written "
        "implementations) the obvious encoding is ONE PSEUDO-REQUIREMENT PER "
        "DECLARED OUTPUT -- ten of them, each passing iff that output disagrees "
        "nowhere.\n\n"
        "**THAT ENCODING CANNOT SEE PROGRESS, AND THE ARGUMENT IS ARITHMETIC "
        "RATHER THAN EMPIRICAL.** A wrong design disagrees somewhere on nearly "
        "every output, so nearly every pseudo-requirement is failing; an edit "
        "that removes most of the disagreement on an output but not all of it "
        "leaves that pseudo-requirement failing, and the count does not move. "
        "The observed instance: an edit taking the disagreement from 9,857 cells "
        "to under 3,000 -- a ~70% reduction -- read *passing requirements 1 -> 1* "
        "and was REFUSED and rolled back.\n\n"
        "**RE-ENCODED ON (OUTPUT, TESTPOINT) PAIRS THE SAME EDIT LATCHES.** A "
        "pair passes iff that output disagrees nowhere in that testpoint, so an "
        "edit that fixes an output on 200 testpoints and not on 30 raises the "
        "count by 200. Re-measured serially from the unedited held-out design, "
        "one commit under the pair ratchet takes 9,857 cells to **2,540**.\n\n"
        "**THE RULE THIS SETS IS NOT ABOUT THIS CRITERION.** Two numbers are "
        "needed and they are not the same number: a FINE one to steer, which "
        "must fall whenever the design improves, and a COARSE one to judge, "
        "which is the property being claimed. The companion plan states exactly "
        "this for the check-set loop -- ratchet on (requirement, testpoint) "
        "pairs, accept per requirement -- and this is that prescription arriving "
        "as a defect in a driver that did not follow it. A criterion whose "
        "granularity is coarser than the edits being made is not a weak "
        "gradient; it is NO gradient, and it rejects correct work.\n\n"
        "This is the same shape as "
        "`conviction_count_is_not_a_descent_criterion`, from the other side: "
        "there the count is fine enough and points the wrong way, here it points "
        "the right way and is too coarse to move.\n\n"
        "**CORRECTED BY THE RUN THAT FOLLOWED, AND THE CORRECTION MATTERS MORE "
        "THAN THE DEFECT.** I wrote above that a criterion coarser than the edits "
        "\"is NO gradient, and it rejects correct work\". That is true of the "
        "per-output ratchet and FALSE as a general claim -- finer is not better. "
        "Over seven trials of one editor run, the raw CELL count and the "
        "(output, testpoint) PAIR count disagreed about whether the design had "
        "improved THREE TIMES:\n\n"
        "    trial  cells         pairs passing   latched\n"
        "      3    3,003->2,721  3,210->3,192    REFUSED\n"
        "      4    3,003->2,786  3,210->3,186    REFUSED\n"
        "      5    3,003->2,216  3,210->3,205    REFUSED\n"

        "Trial 5 is the sharpest: a **26% improvement in cells** that made the "
        "property worse. A cell ratchet would have taken all three.\n\n"
        "**AND THE REFUSALS COST NOTHING, ON EITHER MEASURE.** A refused commit "
        "keeps the staged buffer, trials 6 and 7 built on it, and the run ended "
        "at **1,758 cells -- lower than any of the three designs the cell "
        "ratchet would have accepted.** The coarser criterion was right three "
        "times out of three and lost nothing by being right.\n\n"
        "**SO THE RULE IS NOT \"RATCHET FINELY\". IT IS: RATCHET AT THE "
        "GRANULARITY OF THE PROPERTY BEING CLAIMED, NOT OF THE EVIDENCE.** A "
        "cell is evidence. A (output, testpoint) pair is the property -- this "
        "output is right in this situation. Per-output is coarser than the "
        "property and refuses real progress; per-cell is finer than the property "
        "and accepts real regressions. Both failure modes are measured here, on "
        "one criterion, in one run.\n\n"
        "**ONE DEFECT REMAINS AND IT IS IN THE BRIEF, NOT THE RATCHET.** The "
        "editor was told its score was cells and the loop latched on pairs, so "
        "three refusals looked arbitrary from where it sat -- it reported the "
        "discrepancy itself. The number an agent is asked to optimise must be "
        "the number that latches."
    )


def a_run_directory_written_by_two_agents_is_not_a_measurement() -> str:
    """A harness discipline finding, made twice in one session, both times mine.

    It is recorded here rather than absorbed because the failure mode is silent:
    the run directory afterwards contains a design, a state file and a score, all
    well-formed, and none of them describes the same moment.
    """
    return (
        "An editor run directory holds a staged buffer, an accepted design, a "
        "best-so-far design, a trial counter and a re-scored result. A commit "
        "rewrites several of them in sequence over minutes of simulation. **Two "
        "agents pointed at one such directory, or one agent plus an operator "
        "re-initialising it, produce a directory in which those files come from "
        "different moments** -- and nothing in it says so.\n\n"
        "Both instances here had the same tell and it is worth naming: the "
        "accepted design's SIZE matched neither the design the run started from "
        "nor the one the last recorded commit produced. A file that is not any "
        "of the versions the run is supposed to contain is the signature.\n\n"
        "**NO NUMBER FROM EITHER DIRECTORY IS QUOTED ANYWHERE IN THIS MODULE OR "
        "IN THE PLAN.** Both were archived unread and the run restarted from the "
        "unedited held-out design, serially, with exactly one agent. That is the "
        "only remedy: a partial result from a contended directory cannot be "
        "repaired by inspection, because the question is not what the files say "
        "but which moment each of them is from.\n\n"
        "It belongs beside the other harness rules this plan has had to learn by "
        "breaking them: select over the same corpus the score was taken over, "
        "re-score in a fresh directory rather than comparing a design against "
        "itself, and give every arm the same row list.\n\n"
        "**CORRECTED, AND THE CORRECTION IS THE USEFUL HALF. I FIRST WROTE THAT \"the "
        "discipline is one line -- one agent per run directory\", AND THEN BROKE IT A "
        "THIRD TIME WITHIN THE HOUR.** The rule was stated in every dispatch brief, "
        "in capitals, with the two previous failures named. The third instance was "
        "not an agent ignoring it: it was me stopping one of two registered agents "
        "and dispatching a new one into the directory the OTHER was still holding, "
        "having never enumerated the live writers. The freshly dispatched agent "
        "detected the collision itself, refused to commit, and said so -- which is "
        "the only reason the third instance was caught at all.\n\n"
        "**SO THE REMEDY IS NOT A RULE, IT IS A LOCK.** A rule that must be "
        "remembered by every operator and every agent on every dispatch is not a "
        "rule; it is a hope, and this one failed three times out of three. Every "
        "MUTATING driver command now takes an exclusive lock on the run directory "
        "and refuses with the holder's pid, command and start time; reads are "
        "unlocked so a reader can never block a writer; a lock whose pid is gone is "
        "reclaimed and the takeover is printed rather than done silently. Three "
        "destroyed runs is what it cost to prefer the rule to the mechanism."
    )


def a_body_is_judged_whole_and_its_obligations_are_not() -> str:
    """Every judgement on this plan is of a WHOLE BODY, and a requirement's
    sentence states several obligations.

    A body asserting three of them convicts a design if ANY of the three is
    violated, so ONE over-reaching obligation makes the body unsound and takes
    the other two down with it. This asks, without authoring anything, whether
    the adequate cell is reachable at obligation granularity where it is not at
    body granularity -- by partitioning each body's convictions by the DETAIL
    STRING it itself emitted.
    """
    return (
        "Measured over 547 authored bodies, 481 of which decide on both the "
        "known-good design and held-out L. The class a split can rescue is the "
        "UNSOUND AND DISCRIMINATING one -- it convicts the known-good design "
        "somewhere and the held-out design elsewhere:\n\n"
        "    bodies in that class                              307\n"
        "    requirements they span                    61 of 89 = 69%\n"
        "    requirements with an adequate body today  17 of 89 = 19%\n\n"
        "**69% AGAINST 19% IS THE SIZE OF THE PRIZE**, and it is the same "
        "anti-correlation this module is about, seen as a granularity question "
        "rather than as a distribution: the discrimination for two thirds of "
        "the specification is already authored, inside bodies whose soundness "
        "one obligation ruins.\n\n"
        "**THE MEASURED CEILING IS +4 REQUIREMENTS AND IT IS GOLDEN-SELECTED.** "
        "Keeping only the reasons a body fires with on the held-out design and "
        "never on the known-good one -- REQ-0016, REQ-0021, REQ-0074, REQ-0084 "
        "-- takes adequacy 17 -> 21 of 89, 19% -> 24%. Choosing WHICH reason to "
        "drop reads the known-good design, so this is a ceiling in the sense "
        "MAXSOUND is, never a score. The golden-free form -- keep a reason that "
        "objects to a minority of the candidate population, the minority rule "
        "applied per REASON instead of per BODY -- is not measured here.\n\n"
        "**AND THE CEILING IS ITSELF A FLOOR, BECAUSE THE INSTRUMENT IS BLIND TO "
        "78% OF ITS OWN POPULATION.** 239 of the 307 bodies emit ONE message for "
        "every conviction they ever make, so a body asserting several "
        "obligations behind one string cannot be cut along them by anything "
        "reading its output. At the requirement level the instrument sees 24 of "
        "the 61 eligible requirements = 39%.\n\n"
        "    of the 24 it can see, a reason fires only on the held-out design  9 = 38%\n"
        "    of those 9, requirements with no adequate body today             4\n\n"
        "**WHAT BLINDS IT IS THE DETAIL STRING THE AUTHOR CHOSE, NOT THE "
        "CHECK.** That is a reporting defect and it is free to fix: require "
        "every objection to name the obligation it fires on, which costs an "
        "author nothing and takes this instrument from 39% coverage to 100%.\n\n"
        "**AND EVEN THE OPTIMISTIC EXTRAPOLATION DOES NOT REACH A MAJORITY.** At "
        "the observed 38% over all 61 eligible requirements the split would "
        "reach roughly 31 of 89 = 35%, against the 45 a majority needs. That is "
        "an ESTIMATE and not a measurement -- the 37 requirements the instrument "
        "cannot see may split at a different rate, and a body whose obligations "
        "share one `if` cannot be cut at all whatever it prints.\n\n"
        "This is `a_ratchet_on_counts_refuses_an_improvement_it_cannot_see` at "
        "the other end of the pipeline. There a criterion coarser than the edits "
        "being made rejects correct work; here a criterion coarser than the "
        "obligations being asserted rejects correct assertions. Both say the "
        "same thing: the unit you JUDGE at should not be forced to be the unit "
        "you AUTHOR at.\n\n"
        "**THE FOUR WERE READ RATHER THAN TRUSTED, AND THREE MECHANISMS APPEAR.** "
        "REQ-0016 and REQ-0074 each hold two `return (False, ...)` sites and cut "
        "by deleting one. REQ-0084 holds two independent loops its own comments "
        "label `Case 1` and `Case 2`. REQ-0021 is different -- one verdict over a "
        "conjunction of two asserted outputs, which cuts by dropping a conjunct "
        "rather than a branch. All four are real cuts.\n\n"
        "**AND THE ONE FALSE POSITIVE WAS EXCLUDED BY SYNTACTIC LUCK, WHICH IS THE "
        "SHARPEST THING HERE.** REQ-0039 emits `outputs changed without a rising "
        "clk edge: [a, b, c]` -- ONE obligation whose message varies with which "
        "signals witnessed it, and it convicts the known-good design on 342 of 348 "
        "testpoints. REQ-0021 emits `asserted dcram_we=1, tag_we=1` -- TWO "
        "obligations whose message varies with which one fired. The instrument "
        "kept the second and dropped the first because one used brackets and the "
        "other used a comma-join. That is a formatting accident, not a principle, "
        "so the +4 is not robust either.\n\n"
        "**WHICH MAKES THE PRESCRIPTION NARROWER AND STRONGER THAN 'PRINT MORE'.** "
        "The obligation an objection fires on must be a STRUCTURED FIELD the check "
        "returns, not a phrase inside a message written for a human to read. As "
        "prose it is unreadable for 78% of the population and misreadable for the "
        "rest."
    )


def the_editors_dataflow_slice_was_dead_in_every_run_here() -> str:
    """A thirteenth counting-shaped defect, mine, found by a subagent rather
    than by any number looking wrong.

    The companion document names the dataflow slice as the editor's answer to
    the one problem a whole-module view creates -- *"`focus(req_uid)`. Slice
    from one requirement's ports at a time"* -- and every editor run measured on
    this plan was driven through a harness in which it returned nothing.
    """
    return (
        "Every driver command is a fresh process that rebuilds the edit session "
        "from `state.json`. All three drivers here test `s.focused` to decide "
        "whether to build the slice -- **about thirty lines BEFORE the line that "
        "reads `focused` out of `state.json`.** So `s.focused` is the "
        "constructor default at the moment it is tested, `blocks_by_id` is empty "
        "on every invocation, and `blocks` and `readblock` return nothing and "
        "`unknown block_id`.\\n\\n"
        "**THE EDITOR HAD NO DATAFLOW SLICE IN ANY RUN ON THIS PLAN** -- not the "
        "ceiling runs, not the golden-free rule runs, not the 21-, 111- or "
        "117-check runs. What it had was the `focus` call's own output, which is "
        "computed in-process and therefore correct, and nothing afterwards. Every "
        "editor here read the whole module and worked from it.\\n\\n"
        "**IT WAS FOUND BY A SUBAGENT, NOT BY A NUMBER LOOKING WRONG**, which is "
        "the same signature as the twelve before it: the harness ran clean, "
        "printed plausible output, and answered a question nobody had asked. An "
        "empty block list reads exactly like a slice that legitimately found "
        "nothing.\\n\\n"
        "**AND THE CONFOUND IS CONSTANT ACROSS ARMS, WHICH IS THE ONE PIECE OF "
        "GOOD NEWS.** Every run was degraded identically, so the comparisons "
        "BETWEEN check sets stand. What does not stand is any absolute reading: "
        "every `DIFFERS` on this plan was produced by an editor missing the tool "
        "the architecture puts at the centre of its evidence, so they are "
        "pessimistic by an unknown amount.\\n\\n"
        "**AND FIXING IT COSTS COMPARABILITY, WHICH HAS TO BE PAID RATHER THAN "
        "AVOIDED.** A fixed driver running one new arm cannot be compared with "
        "arms run against the broken one. The honest course is to re-run the "
        "arms that carry the conclusion, not to leave a tool broken for the sake "
        "of a table."
    )


def the_loop_descended_through_the_reference_designs_own_floor() -> str:
    """The consensus reference used as a DESCENT criterion for a repair loop,
    run to the same conditions as the check-set runs.

    `the_consensus_is_an_oracle_even_though_it_is_not_a_ranking` establishes that
    the known-good design scores 2,073 of 240,573 unanimous cells -- 0.86% --
    because seven readers of one specification share misreadings. That figure was
    written down in advance as the FLOOR: a design scoring below it has matched
    the population where the population is wrong.
    """
    return (
        "One Sonnet editor, held-out design L unedited, 348-testpoint suite, "
        "14-trial budget, the shipped `_EditSession` policy, one writer in the "
        "run directory. The editor is handed an OBSERVED expected value -- what "
        "all seven independent implementations produce at that sample -- instead "
        "of objections from a check set.\n\n"
        "    consensus cells disagreeing   9,857 -> 1,758 in 7 of 14 trials\n"
        "    THE KNOWN-GOOD DESIGN'S OWN SCORE           2,073\n\n"
        "**THE LOOP DESCENDED THROUGH THE FLOOR, AND THAT IS PROOF OF "
        "NON-EQUIVALENCE BEFORE ANY MITER RUNS.** The known-good design scores "
        "2,073 against this reference. A design scoring 1,758 therefore agrees "
        "with the seven on at least 315 cells where the known-good design does "
        "NOT, so it cannot be the known-good design -- by arithmetic, exactly as "
        "a design scoring zero against a set that convicts the known-good design "
        "seven times cannot be it. The miter agrees: `DIFFERS`, three pins "
        "green, 210 of 348 testpoints.\n\n"
        "**AND THE PROXY MOVED SEVERAL TIMES FASTER THAN THE TRUTH.** Over the "
        "same seven trials the criterion fell 82% while the actual divergence "
        "from the known-good design fell 25% by testpoints (279 -> 210) and 13% "
        "by cells (4,450 -> 3,890). Different denominators, so the percentages "
        "are not directly comparable -- but the loop reduced its own objective "
        "far faster than it reduced its distance from correctness, which is what "
        "Goodharting looks like when the criterion is honest and merely "
        "incomplete.\n\n"
        "**THIS REMOVES THE COMPANION DOCUMENT'S OWN EXPLANATION FOR THE "
        "EDITOR'S WEAKNESS.** That document names the loop's weakest point as "
        "*\"expected/actual is reconstructed, not observed ... a fabricated "
        "expected value would make it CONFIDENT in a wrong theory\"*. Here it is "
        "OBSERVED -- seven agents who never saw each other's work -- and the "
        "design still ends `DIFFERS`. Being real rather than reconstructed is "
        "not what was missing.\n\n"
        "**WHAT A LOOP AUTHOR TAKES FROM IT: A DESCENT CRITERION NEEDS A FLOOR, "
        "AND THE FLOOR HAS TO BE KNOWN.** This one has a floor that is knowable "
        "in advance, which no check set's ever is -- and the loop still walked "
        "past it, because nothing stops a criterion being satisfied harder than "
        "correctness satisfies it. Stop on the floor, not on the trial budget, "
        "whenever the floor can be computed."
    )


def the_consensus_route_is_bounded_by_the_specification_not_the_editor() -> str:
    """Where the divergence that SURVIVES a consensus-driven loop actually sits.

    Raw edges, not transactional rows: the transactional view compresses each
    design independently, so row i of one design is not row i of another, while
    raw edges share an index because every design was driven by one stimulus.
    """
    return (
        "The design the consensus loop produced, re-scored at raw edges against "
        "the known-good design over 252,510 (edge, declared output) cells, with "
        "each cell classified by whether the seven independent implementations "
        "agree there:\\n\\n"
        "                        cells    of all   still wrong    rate\\n"
        "    the seven AGREE   238,559      94%          1,718    0.7%\\n"
        "    the seven SPLIT    13,951       6%          3,405   24.4%\\n\\n"
        "**66% OF WHAT IS STILL WRONG IS WHERE THE POPULATION CANNOT AGREE, A "
        "12.0x CONCENTRATION** -- and those are precisely the cells the "
        "consensus criterion is SILENT on, by construction. A unanimous "
        "reference has nothing to say where there is no unanimity.\\n\\n"
        "**SO THE ROUTE IS EXHAUSTED BY THE SPECIFICATION RATHER THAN BY THE "
        "EDITOR.** Even a perfect consensus-driven loop could address at most "
        "the 34% of the residue that lies in agreed cells. The other 66% sits "
        "where `split_cells_are_a_specification_finding` measured a targeted "
        "reader reproducing the population's own wrong answer 7 times in 9, so "
        "no instrument drawn from this text resolves it -- not a check, not a "
        "consensus, not a better editor.\\n\\n"
        "**AND IT EXPLAINS THE FLOOR RESULT MECHANICALLY.** The loop drove the "
        "error rate on cells the criterion CAN see down to 0.7%, which is below "
        "the 0.86% at which the reference itself is wrong -- it over-fitted the "
        "agreeable part of the design's behaviour -- while the disagreeable part "
        "stayed wrong at 24.4%. Descending through the floor and stalling at "
        "`DIFFERS` are one event seen from two sides.\\n\\n"
        "**ONE FIGURE HERE WAS NOT PRE-REGISTERED AND MUST NOT BE USED AS A "
        "TIEBREAK.** At raw edges this design is wrong on 5,123 cells against "
        "10,926 for the design the 117-check loop produced. That looks decisive "
        "for the consensus criterion and is a THIRD measure, computed afterwards "
        "as the input to this analysis. The pre-registered pair -- testpoints "
        "differing and transactional cells -- reads 210 against 236 and 3,890 "
        "against 3,533, which is MIXED, and mixed is what stands."
    )


def two_criteria_on_one_harness_land_the_same_design_in_the_same_place() -> str:
    """The comparison the whole session was arranged to make.

    Every earlier head-to-head on this plan compared runs that differed in the
    harness as well as the criterion -- the dataflow slice was dead in all of
    them, and the drivers ratchet differently. This pair shares a harness: the
    same held-out design unedited, the same 348-testpoint suite, the same
    14-trial budget, one writer under a lock, and a WORKING slice on both.
    """
    return (
        "    criterion                     testpoints of 348   cells   trials\\n"
        "    the design, unedited                279 = 80%     4,450      --\\n"
        "    117 CHECKS, 50 of 89 = 56%          206 = 59%     3,866   8/14\\n"
        "    THE CONSENSUS OF SEVEN              210 = 60%     3,890   7/14\\n\\n"
        "**FOUR TESTPOINTS AND TWENTY-FOUR CELLS APART. THEY ARE "
        "INDISTINGUISHABLE.** Both end `DIFFERS` with three pins green. A "
        "golden-free check set spanning a majority of the specification and an "
        "OBSERVED expected value from seven independent implementations drive "
        "the same held-out design to the same place, within 1.2%.\\n\\n"
        "**AND THE CONSENSUS CRITERION IS TWICE AS GOOD AT THE THING IT "
        "MEASURES, WHICH BOUGHT NOTHING.** On the cells where the seven agree -- "
        "the only cells it scores -- it leaves the design wrong 0.7% of the time "
        "against the check set's 1.3%. That advantage does not appear in the "
        "grade at all, because both designs' remaining wrongness is "
        "concentrated where the seven CANNOT agree: 66% of the consensus "
        "residue and 56% of the check set's.\\n\\n"
        "**SO THE CRITERION IS NOT THE BINDING CONSTRAINT, AND THAT IS THE "
        "SESSION'S RESULT.** Every route this plan has tried -- more span, "
        "better selection, narrowing, strengthening, volume, an ensemble of "
        "checks, an ensemble of designs, an observed expected value -- optimises "
        "something computed from the specification, and the specification "
        "underdetermines the cells where these designs are actually wrong.\\n\\n"
        "TWO CONFOUNDS, BOTH NAMED, BOTH POINTING THE SAME WAY. The check-set "
        "loop ratchets per CHECK where the consensus loop ratchets per (output, "
        "testpoint) PAIR, which handicaps the check set -- so if anything it is "
        "the stronger of the two, and it still only ties. And the check-set arm "
        "spent 8 trials to the consensus arm's 7, which is close enough not to "
        "explain four testpoints.\\n\\n"
        "**WHAT THE SLICE WAS WORTH, PRICED BY THE SAME PAIR.** The identical "
        "117-check set on the broken harness reached 236 testpoints and 10,926 "
        "raw-edge cells in 4 trials; on the fixed one, 206 and 6,903 in 8. "
        "Better on both, and confounded with the trial count -- so the slice is "
        "worth something and how much is not separable here."
    )


def the_floor_on_any_spec_derived_pipeline_is_146_of_348_testpoints() -> str:
    """What the grade would still read for a pipeline that extracted everything
    the specification determines.

    Grant a spec-derived criterion its best case -- suppose it drove the design
    to be correct on every cell the seven independent readings AGREE on, which
    no run here comes near. Where they disagree it has no opinion to drive with:
    a check convicting there is as likely wrong as right, and a consensus is
    silent by construction.
    """
    return (
        "Per testpoint, on the design the consensus loop produced, at raw edges "
        "over declared outputs:\\n\\n"
        "    testpoints differing anywhere                168 = 48%\\n"
        "    ... at a cell the seven AGREE on              84 = 24%   reachable\\n"
        "    ... at a cell the seven CANNOT agree on      146 = 42%   THE FLOOR\\n\\n"
        "**ONLY 22 OF 348 TESTPOINTS = 6% DIFFER EXCLUSIVELY AT CELLS A "
        "SPEC-DERIVED CRITERION HAS AN OPINION ABOUT.** Every other differing "
        "testpoint contains at least one cell the specification, read seven "
        "independent times, does not determine.\\n\\n"
        "**SO EQUIVALENCE IS NOT REACHABLE BY STEERING FROM THIS "
        "SPECIFICATION.** Not by a wider check set, not by more adequate checks, "
        "not by an ensemble, not by an observed expected value, not by more "
        "trials or a better editor -- every one of those is computed from the "
        "text, and the text is silent where the design is wrong.\\n\\n"
        "**ONE PRECISION, BECAUSE THE CLAIM IS EASY TO OVERSTATE.** This bounds "
        "what a criterion can STEER, not what a design can ACHIEVE. A design may "
        "be right in a split cell by luck, or because its author happened to "
        "guess as the reference did -- 94% of cells are agreed and the population "
        "is right on 99.1% of those. What no check set, ensemble or consensus "
        "can do is DRIVE it there, having no opinion to drive with.\\n\\n"
        "**AND IT IS A TRAJECTORY, NOT TWO ENDPOINTS.** The share of remaining "
        "wrongness sitting in split cells rises monotonically as the loops do "
        "their work -- 37% on the unedited design, 56% after the 117-check loop, "
        "66% after the consensus loop -- while the agreed-cell wrongness falls "
        "9,140 -> 3,066 -> 1,718. The loops clear what the specification "
        "determines and stall on what it does not, which is the mechanism rather "
        "than a correlation.\\n\\n"
        "**WHAT WOULD CHANGE IT IS UNCHANGED FROM WHAT THIS MODULE ALREADY "
        "SAYS**: a decision on the underdetermined cells from outside the "
        "specification-and-reader loop. The disagreement map localises them at "
        "10-12x and is the artifact to put in front of whoever can make that "
        "decision. It is not an instrument this pipeline can build."
    )


def two_spec_only_instruments_stacked_still_stop_at_the_floor() -> str:
    """The strongest spec-only configuration this plan can build, run to 27 of
    30 trials, graded on the same instrument as every other arm.

    Unanimity over seven independently written implementations gives a dense
    gradient and is right 99.1% where it speaks, but is SILENT on the 6% of
    cells the seven split on -- and that silence is the whole of the measured
    floor. The 117 requirement-derived checks are the only other spec-only
    instrument that says anything there. Both were put in one ratchet.
    """
    return (
        "    criterion                    testpoints of 348   cells   trials\\n"
        "    the design, unedited               279 = 80%     4,450      --\\n"
        "    consensus alone                    210 = 60%     3,890    7/14\\n"
        "    117 checks alone                   206 = 59%     3,866    8/14\\n"
        "    BOTH, stacked                      205 = 59%     3,608   27/30\\n\\n"
        "**`DIFFERS`, three pins green.** Stacking a second spec-only instrument "
        "on the first bought ONE testpoint over either alone, on nearly four "
        "times the trial budget.\\n\\n"
        "**AND THE SPLIT RESIDUE SAYS WHY, FOR THE FOURTH TIME.** The share of "
        "remaining wrongness sitting in cells the seven CANNOT agree on rises "
        "monotonically as the criterion gets stronger -- 37% unedited, 56% after "
        "the checks alone, 66% after the consensus alone, **71% after both** -- "
        "while the error rate on cells they CAN agree on falls to 0.5%. Each "
        "instrument clears what it can see; stacking them clears more of the "
        "visible region and nothing of the invisible one.\\n\\n"
        "**THE GOODHART MEASUREMENT, WITH A LARGE SAMPLE.** Trials 11-27 -- "
        "seventeen of them, on an editor explicitly told not to stop early -- "
        "improved BOTH proxies substantially and moved the grade backwards:\\n\\n"
        "                        proxy: cells   proxy: checks   GRADE: testpoints\\n"
        "    after trial 10             1,924         8 of 117            204\\n"
        "    after trial 27             1,693         6 of 117            205\\n\\n"
        "-12% and -25% on what the loop optimises, +1 on what it is judged by. "
        "Once the region a spec-derived criterion can see is exhausted, further "
        "descent on it is uncorrelated with correctness -- which is the same "
        "shape as `conviction_count_is_not_a_descent_criterion`, now with 17 "
        "trials behind it instead of a trajectory.\\n\\n"
        "**A MAJORITY VOTE CANNOT FILL THE SILENCE, AND THAT WAS MEASURED "
        "BEFORE THIS RUN RATHER THAN ASSUMED.** In the cells where the seven "
        "split, the majority value equals the known-good design's **38.4% of "
        "the time** -- below chance, so a majority criterion would steer AWAY "
        "in 62% of the cells where it speaks. The breakdown is worse than the "
        "headline: at 5-of-7 agreement the majority is right **12.3%** of the "
        "time, meaning the two dissenters are right 87.7%. Unanimity's refusal "
        "to speak there is therefore OPTIMAL for a population criterion, not "
        "conservative, and the floor is a property of the specification rather "
        "than of the choice of vote."
    )


def stacking_two_criteria_needs_weights_and_mine_had_none() -> str:
    """A defect in the combined criterion, mine, found by reading what the loop
    actually shipped rather than by any number looking wrong.

    `_EditSession.commit` latches on a COUNT of passing units. Putting two
    instruments in that count without weighting them makes the ratio of their
    unit counts the exchange rate between them -- silently.
    """
    return (
        "    (output, testpoint) pair units   3,480\\n"
        "    per-output units                    10\\n"
        "    CHECK units                        117   = 3.2% of the total\\n\\n"
        "**ONE CHECK WEIGHS THE SAME AS ONE OUTPUT ON ONE TESTPOINT** -- 1/29 "
        "of the cell-derived mass. The checks were nominally in the ratchet and "
        "effectively powerless, which is the mechanism behind the combined run "
        "beating the check-only run by a single testpoint.\\n\\n"
        "**AND IT SHIPPED A DESIGN VIOLATING A SOUND CHECK, DELIBERATELY.** On "
        "one trial the editor added a live cache-inhibit guard to `tag_we`, "
        "gained ~11 cells, and broke REQ-0034 -- a check all six of whose "
        "members spare the known-good design. It attempted the revert THREE "
        "times, in three forms, and **the ratchet refused every one**, because "
        "returning the pair-units cost more than the single check unit regained. "
        "The editor documented the trade and could not act on it. The arithmetic "
        "preferred cells and there was no way for it to say otherwise.\\n\\n"
        "**SO A COMBINED CRITERION IS A WEIGHTING DECISION AND MUST BE MADE "
        "EXPLICITLY.** Summing two instruments does not combine them; it prices "
        "one in units of the other at whatever ratio their cardinalities "
        "happen to have. The sparse instrument -- the one carrying the semantic "
        "content, and the only one that speaks where the dense one is silent -- "
        "is exactly the one that loses under an unweighted sum, because sparse "
        "is what it is FOR.\\n\\n"
        "This is the third granularity finding here and the first about "
        "composition rather than resolution. "
        "`a_ratchet_on_counts_refuses_an_improvement_it_cannot_see` says ratchet "
        "at the granularity of the property; this says that when two properties "
        "share a ratchet, their relative weight is a design parameter and "
        "leaving it implicit sets it to an accident of counting."
    )


def a_finished_run_cannot_be_asked_what_its_ratchet_refused() -> str:
    """A harness gap of mine, found by trying to price a one-line change and
    discovering the finished run could not answer.

    `stacking_two_criteria_needs_weights_and_mine_had_none` records that the
    combined criterion weighted its two instruments by the accident of their
    cardinalities. The obvious next question is a counterfactual -- WHICH of the
    finished run's commits would a different weighting have latched, and which
    would it have refused -- and it costs nothing to ask if the run kept the
    per-commit numbers. It did not.
    """
    return (
        "**WHAT A FINISHED RUN ON THIS PLAN RETAINS, in full:**\\n\\n"
        "    state.json    the CURRENT counters -- trials used, last latched\\n"
        "                  score, best score. No history.\\n"
        "    report.json   the LAST review. Overwritten by every commit.\\n"
        "    best.v        the design. No provenance.\\n\\n"
        "So a 27-trial run records 27 decisions and keeps ONE. The accept "
        "criterion is the object under study on this plan, and its own "
        "decisions are the one thing not written down.\\n\\n"
        "**THE COST IS EXACT AND WAS PAID.** Re-weighting the two instruments "
        "is one line of arithmetic. Pricing it against the run it was written "
        "for should have been a replay over recorded numbers -- no simulation, "
        "no model call, seconds. Instead it needs a fresh 30-trial run: a full "
        "348-testpoint suite per commit, plus an editor. The change is trivial "
        "and the measurement is not, entirely because of what was not kept.\\n\\n"
        "**AND IT SILENTLY BOUNDS WHAT CAN BE CLAIMED ABOUT EVERY ARM ALREADY "
        "RUN.** Four arms landed at 205, 206, 210 and 205 testpoints of 348. "
        "Whether that band is a property of the specification, of the design "
        "space, or of a ratchet refusing correct work in all four is a question "
        "about the refused commits -- and not one of the four runs can be asked "
        "it. The band is reported as measured; its CAUSE is not attributable "
        "from the artifacts those runs left.\\n\\n"
        "**THE REMEDY IS ONE APPEND PER COMMIT, and it is not a rule.** A "
        "ratchet that decides is a ratchet that must log what it decided and on "
        "what evidence: the proposed unit counts, the latched unit counts, the "
        "verdict, and the per-instrument numbers on both sides. Anything less "
        "makes the loop's own accept criterion the only unaudited component of "
        "a pipeline built to audit criteria.\\n\\n"
        "This is the same shape as the phantom-baseline defect this plan "
        "already records -- `req_results.json` rewritten by every review "
        "including rolled-back ones, so nothing ever latched and the tell was a "
        "timestamp. Both are the loop failing to distinguish what it CONSIDERED "
        "from what it ACCEPTED. That one produced wrong numbers; this one "
        "produces no numbers at all, which is harder to notice."
    )


def weighting_the_two_instruments_equally_changes_nothing_at_the_grade() -> str:
    """The last untried configuration in this space, run to a graded result.

    `stacking_two_criteria_needs_weights_and_mine_had_none` records the defect:
    two instruments summed into one pass-count, priced against each other at
    whatever ratio their cardinalities happened to have. This is that defect
    fixed -- each check emitted as 30 units so the 117 checks weigh what the
    3,490 cell units weigh -- and everything else held identical.
    """
    return (
        "**THE WEIGHTING WORKED, MECHANICALLY, AND IT IS ON THE RECORD THIS "
        "TIME.** Between trials 5 and 6 the editor broke a sound check and "
        "fixed it forward, and the per-commit log shows what the ratchet did "
        "with that: cells 2,710 -> 2,728 -- EIGHTEEN WORSE -- objecting checks "
        "8 -> 7, and **the commit latched**. That is the exact trade the "
        "unweighted run attempted three times and had refused. The editor "
        "reports zero refusals across nine commits: 'every fix I made was net "
        "positive under the 30-units-per-check weighting, so I never needed to "
        "fight the scoreboard.'\\n\\n"
        "**AND THE GRADE DID NOT MOVE. 205 OF 348, AGAINST THE UNWEIGHTED "
        "RUN'S 205 OF 348.**\\n\\n"
        "    criterion                    testpoints   cells   trials\\n"
        "    L, unedited                    279         4,450    --\\n"
        "    consensus alone                210         3,890    7 of 14\\n"
        "    117 checks alone               206         3,866    8 of 14\\n"
        "    both stacked, unweighted       205         3,608   27 of 30\\n"
        "    both stacked, EQUAL WEIGHT     205         3,696    9 of 30\\n\\n"
        "**THIS IS THE CLEANEST GOODHART INSTANCE ON THIS PLAN, BECAUSE THE TWO "
        "MEASURES MOVE IN OPPOSITE DIRECTIONS BETWEEN THE ARMS.** The proxy "
        "improved 22% -- 1,693 cells disagreeing with the consensus down to "
        "1,325 -- while true divergence got 2.4% WORSE, 3,608 differing cells "
        "up to 3,696, and the testpoint count was IDENTICAL. Earlier Goodhart "
        "findings here show a proxy falling faster than the grade; this shows "
        "a proxy falling while the grade rises, on the same instruments, the "
        "same starting design and the same suite.\\n\\n"
        "**WHAT IT COSTS AND WHAT IT DOES NOT BUY.** Nine trials against "
        "twenty-seven for the same grade, so the weighting is cheaper per unit "
        "of nothing. That is one sample per arm and one editor per arm, so the "
        "3x is NOT attributable to the weighting -- editor variance is "
        "uncontrolled and n = 1.\\n\\n"
        "**SO THE COMBINATION QUESTION IS CLOSED, and it closes on the "
        "pre-registered reading rather than on a retrofitted one.** Two "
        "spec-derived instruments, stacked, at every weighting anyone has "
        "reason to choose, land the same design in the same place. The 205-210 "
        "band across five arms is a property of what a specification-derived "
        "criterion can see, not of how its parts are priced."
    )


def the_fifth_contradiction_claim_is_the_fifth_refutation() -> str:
    """The editor's soundness judgement, audited for the fifth time, and the
    audit splits its two claims in opposite directions.

    Golden is the audit instrument and nothing else: it runs after the grade,
    selects nothing, repairs nothing, and reaches no prompt.
    """
    return (
        "The weighted run's editor made two claims about the check set. The "
        "structural one is the kind this plan has now refuted five times:\\n\\n"
        "    REQ-0087.shipping wants dc_addr == start_addr while hitmiss_eval\\n"
        "    is high; REQ-0087.control, REQ-0029.t2 and REQ-0030.* want\\n"
        "    dc_addr == saved_addr while biu_read or biu_write is high. On\\n"
        "    TP-9203 both hold at one edge and the two values differ, so no\\n"
        "    design satisfies both.\\n\\n"
        "**REFUTED IN ONE LINE, AS THE OTHER FOUR WERE. All five members spare "
        "the known-good design** -- 348, 348, 348, 256 and 279 decisions, zero "
        "convictions each -- so a design satisfying the whole group exists. The "
        "editor resolved the alleged tie 3-checks-to-1 and reported it as 'a "
        "trade, not a fix'; the audit says there was no trade to make.\\n\\n"
        "**AND ITS OTHER CLAIM IS CORRECT, WHICH IS WHY THE TALLY IS THE POINT "
        "RATHER THAN THE VERDICT.** REQ-0081.control and REQ-0081.merge@merge "
        "both convict the known-good design on TP-9202 edge 11, for the reason "
        "the editor gave: the check compares the entry row to the NEXT row and "
        "cannot distinguish 'incremented on entry' from 'correctly began "
        "receiving the first refill word'. That is the third independent "
        "editor to name REQ-0081, and all three were right.\\n\\n"
        "**RUNNING TALLY OVER FIVE RUNS: 9 of 36 = 25%.** 1 of 3, 1 of 5, 1 of "
        "5, 2 of 8, 2 of 7. An editor with the design, the trace and the "
        "requirement sentence in front of it, arguing with a check it has "
        "every incentive to be right about, is at one in four -- and it cannot "
        "tell its correct call from its incorrect one, since both arrive as "
        "the same confident structural argument. **No gate can distinguish "
        "them either**, which is why this is recorded as a bound on the "
        "editor-as-soundness-instrument route rather than as a defect list.\\n\\n"
        "One hedge is worth keeping: the editor flagged REQ-0015.v2@n3 as 'a "
        "hypothesis, not a finding' because it could not get the evidence. The "
        "audit says that check is SOUND. **It was right to decline**, and the "
        "hedge is the only part of its judgement that tracked the truth "
        "reliably."
    )


def a_criterion_only_corrects_where_it_beats_the_design_under_test() -> str:
    """The mechanism behind every arm landing in the same place, measured on
    five spec-only selectors at once instead of inferred from a trajectory.

    Two audits changed the question. The first says the answer is IN the
    population; the second says no rule over the population can extract it.
    """
    return (
        "**THE ANSWER IS IN THE POPULATION, WHICH THIS PLAN HAS BEEN ASSUMING "
        "WITHOUT CHECKING.** In the split cells -- the 6% the seven "
        "spec-derived designs cannot agree on, carrying 65% of what the best "
        "arm still gets wrong -- the right value is one of the seven values "
        "produced in **13,210 of 13,973 cells = 94.5%**. So the population "
        "contains the answer and the problem is SELECTION, not absence.\\n\\n"
        "**AND THE DISTRIBUTION IS BIMODAL, WHICH IS WHY NO VOTE WORKS.** Of "
        "the split cells, 24.5% have the right value in exactly ONE of the "
        "seven and 31.4% in exactly two -- while 31.1% have it in SIX of "
        "seven. The two regimes want opposite polarity, so any threshold wins "
        "one and loses the other, and a majority lands at the measured 38.4%.\\n\\n"
        "**DISSENT PREDICTS WHO HOLDS IT, AND THAT IS SPEC-ONLY.** Over the "
        "seven, the rate at which a design holds a minority value correlates "
        "with how often it is right in split cells at **r = +0.882** (n = 7, a "
        "shape rather than a statistic). The two dissenters -- 91.7% and 38.3% "
        "-- are the two most accurate, 63.7% and 63.9%; the five conformists "
        "sit at 34-39%. That is the outlier finding arriving inside the "
        "population: correctness makes a design dissent.\\n\\n"
        "**AND EVERY ONE OF THEM IS USELESS AS A CRITERION, FOR ONE REASON.** "
        "Scored on the design a loop actually has in front of it, restricted "
        "to the cells where each selector would OBJECT:\\n\\n"
        "    selector                  accuracy   objects on   PRECISION\\n"
        "    majority                    38.4%        9,822       19.2%\\n"
        "    minority                    56.0%        4,787       13.2%\\n"
        "    follow the top dissenter    63.7%        3,861       17.8%\\n"
        "    follow the 2nd dissenter    63.9%        6,217       30.8%\\n"
        "    anti-majority               56.1%        4,791       12.9%\\n\\n"
        "**NOT ONE REACHES 50%, so obeying any of them makes the design WORSE**, "
        "and the best accuracy in the table has the second-worst yield per "
        "objection.\\n\\n"
        "**THE REASON IS ARITHMETIC AND IT IS THE GENERAL LAW: A CRITERION "
        "CORRECTS ONLY WHERE ITS ACCURACY EXCEEDS THE DESIGN'S.** The design "
        "under test is already right on **77.5%** of split cells. On the cells "
        "where a 63.9%-accurate selector disagrees with a 77.5%-accurate "
        "design, the selector is usually the one that is wrong -- so its "
        "objections are mostly false, whatever its headline says.\\n\\n"
        "**AND THAT IS WHY FIVE ARMS LAND IN THE SAME PLACE.** A loop improves "
        "only where its criterion beats the design it is judging. Where the "
        "seven agree, the consensus is right 99.1% and beats it comfortably, "
        "and every arm drives the agreed-cell error to under 1%. Where they "
        "split, nothing spec-derived beats it -- not a vote, not a minority, "
        "not the best single member -- so the loop has nothing to say and the "
        "grade stops at the floor.\\n\\n"
        "**THIS QUALIFIES THIS PLAN'S OWN CONCLUSION.** The plan says the "
        "missing input is 'a decision on the underdetermined cells, from "
        "something outside the specification-plus-reader loop'. The first half "
        "is now refuted: the decision is INSIDE, 94.5% of the time. What is "
        "missing is an extractor, and extraction is hard for a reason the plan "
        "never named -- **the design under test is a competent reader of the "
        "same specification, and in the region that matters it is a BETTER one "
        "than any rule over the population that produced it.**"
    )


def the_loop_drove_the_design_past_its_own_criterion() -> str:
    """The sharpest thing measured on this plan, and it stopped a run I had
    just dispatched on reasoning this refutes.

    `a_criterion_only_corrects_where_it_beats_the_design_under_test` states the
    law in the split region, where the criterion is silent anyway. This applies
    the same test where the criterion actually SPEAKS.
    """
    return (
        "**I RESUMED A RUN BECAUSE ITS GRADIENT LOOKED UNEXHAUSTED, AND THE "
        "GRADIENT HAD INVERTED.** The editor stopped at 9 of 30 trials with "
        "1,325 cells still disagreeing with the consensus of seven. I read "
        "that as budget left on the table and dispatched a resume. Then the "
        "precision test was applied to the criterion itself:\\n\\n"
        "    at the 238,678 cells where the seven AGREE\\n"
        "      the consensus of seven is right      99.13%\\n"
        "      THE DESIGN UNDER TEST is right       99.30%\\n\\n"
        "**THE DESIGN HAS OVERTAKEN ITS OWN CRITERION**, and the objections it "
        "has left say so outright. Of the 1,314 cells where the two disagree "
        "-- every objection the loop had remaining:\\n\\n"
        "    the consensus is right, the design wrong     375   28.5%\\n"
        "    THE DESIGN IS RIGHT, THE CONSENSUS WRONG     773   58.8%\\n"
        "    both wrong                                   166   12.6%\\n\\n"
        "**TWICE AS OFTEN AS NOT, AN OBJECTION IS THE CRITERION BEING WRONG.** "
        "Driving those 1,325 to zero would have repaired 375 cells and broken "
        "773. The resume was stopped before it committed anything.\\n\\n"
        "**THE MECHANISM IS THAT ONE ACCURACY IS FIXED AND THE OTHER RISES.** "
        "A criterion built from a population is a fixed artifact: 99.13% is "
        "all the seven will ever be. The design's accuracy climbs as the loop "
        "works. They cross, and after the crossing every remaining objection "
        "is more likely wrong than right -- while the objection COUNT keeps "
        "falling, so the loop reads the whole descent as progress and has no "
        "way to see the inversion.\\n\\n"
        "**AND IT EXPLAINS THE ARM-TO-ARM GOODHART EXACTLY.** Between the "
        "unweighted and weighted stacked runs the proxy improved 22% while "
        "true divergence rose 2.4% and the grade did not move. That is not a "
        "coincidence of two arms; it is what descending past the crossing "
        "point looks like from inside.\\n\\n"
        "**THE PRESCRIPTION IS A STOPPING RULE, NOT A BETTER CRITERION.** A "
        "loop driven by a fixed-accuracy reference must stop when the artifact "
        "reaches that reference's accuracy, and everything after that is "
        "damage the loop scores as progress. In a benchmark the crossing is "
        "measurable. **In production it is not**, which makes the trial budget "
        "-- the crude device this plan has been treating as a cost -- the only "
        "protection against it.\\n\\n"
        "It also reframes 'the editor stopped early with budget unspent', "
        "which this plan has twice recorded as a weakness of a run. On this "
        "evidence the editor stopped at very nearly the right moment, for "
        "reasons it could not have articulated, and my correction of it was "
        "the error."
    )


def a_consensus_cannot_outrank_a_competent_reader_at_any_size() -> str:
    """The population lever, refuted without paying for it, and the crossing
    point located in the run that crossed it.

    `the_loop_drove_the_design_past_its_own_criterion` measures the inversion
    and names the fixed-versus-rising mechanism. The obvious remedy is to make
    the fixed side less fixed: 99.13% is a property of SEVEN designs, and the
    goal puts oracle regeneration explicitly in scope. This prices that remedy
    on the designs already in hand before a single new one is generated.
    """
    return (
        "**HEADROOM -- the criterion's accuracy minus the design's, on the "
        "cells the criterion speaks about -- MEASURED AT EVERY POPULATION SIZE "
        "FROM TWO TO SEVEN.** Averaged over subsets, against the design nine "
        "trials of the weighted run produced:\\n\\n"
        "    designs   coverage   consensus   the design there   HEADROOM\\n"
        "        2       97.9%     97.161%        98.498%        -1.337%\\n"
        "        3       96.9%     97.775%        98.702%        -0.926%\\n"
        "        4       96.1%     98.257%        98.873%        -0.615%\\n"
        "        5       95.5%     98.642%        99.029%        -0.387%\\n"
        "        6       94.9%     98.933%        99.171%        -0.238%\\n"
        "        7       94.5%     99.131%        99.298%        -0.167%\\n\\n"
        "**NEGATIVE AT EVERY SIZE, AND THE GAP CLOSES WITHOUT EVER CROSSING.** "
        "Each added design removes about 35% of the remaining deficit, so "
        "thirteen designs projects to -0.016% and twenty to -0.001%. The curve "
        "is asymptotic to zero FROM BELOW. **Generating more designs cannot "
        "restore the criterion's authority**, and that is now measured rather "
        "than assumed -- six generations and six suite runs unspent.\\n\\n"
        "**AND THE REASON IS VISIBLE IN THE COLUMN NOBODY WOULD HAVE WATCHED.** "
        "The design's own accuracy on the surviving cells rises too, 98.498% to "
        "99.298%, in lockstep. Unanimity SELECTS FOR EASY CELLS, and a design "
        "written from the same specification is a competent reader of exactly "
        "those. Both curves are driven by the same hidden variable -- how hard "
        "the cell is to read correctly -- so growing the population moves them "
        "together and never apart.\\n\\n"
        "**THE CROSSING IS REAL AND IT IS NOW LOCATED.** The same measurement "
        "against the UNEDITED held-out design, same population, same suite:\\n\\n"
        "                          consensus   the design   HEADROOM\\n"
        "    L, unedited            99.163%      96.160%     +3.003%\\n"
        "    after 9 trials         99.131%      99.298%     -0.167%\\n\\n"
        "The criterion began as a far better reader than the design and was "
        "overtaken. Interpolating the run's own per-commit log between its two "
        "measured endpoints puts the crossing near **1,780 disagreeing cells, "
        "between trials 7 and 8** -- so the editor stopped ONE TRIAL after the "
        "point where its criterion stopped being right. That is the first time "
        "this plan can say when a run should have stopped, and it is only "
        "sayable because the per-commit log was kept.\\n\\n"
        "**WHAT IT WOULD TAKE, STATED AS A PROPERTY RATHER THAN A WISH.** A "
        "criterion that can drive a design to equivalence must be a BETTER "
        "READER than the design on the cells it speaks about, and stay one all "
        "the way down. No consensus over spec-derived designs is, at any size, "
        "because it is made of readers of the same text. The instrument that "
        "could be is one that reads the SENTENCES rather than voting over "
        "implementations -- which is what the checks are, and 117 of them "
        "objecting 7 times is not enough coverage to carry a design the rest of "
        "the way."
    )


def the_two_instruments_came_apart_and_only_one_was_overtaken() -> str:
    """The precision test applied to the OTHER instrument, and it is the first
    positive result in this region.

    Every finding above measures the consensus and concludes that spec-derived
    criteria are exhausted. That generalised from one instrument to a class
    without checking the other member of it.
    """
    return (
        "**THE SAME TEST, ON BOTH INSTRUMENTS, ON THE SAME DESIGN, RESTRICTED "
        "TO WHERE EACH WOULD ACTUALLY OBJECT:**\\n\\n"
        "    the consensus of seven     375 right of 1,314 objections   28.5%\\n"
        "    the 117 spec checks          5 SOUND of 7 objections       71.4%\\n\\n"
        "**ONE HAS INVERTED AND THE OTHER HAS NOT**, and 71.4% against 28.5% is "
        "not a margin that needs statistics.\\n\\n"
        "**THE MECHANISM SAYS WHY, AND IT PREDICTS THE SPLIT RATHER THAN "
        "EXCUSING IT.** A consensus is a vote over IMPLEMENTATIONS, so its "
        "accuracy tracks how hard a cell is to read -- which is the same "
        "variable that governs the design's accuracy, so the two move together "
        "and the design overtakes it. A check reads one requirement SENTENCE. "
        "Nothing ties its errors to the population's errors and nothing ties "
        "its accuracy to cell difficulty, so it is not overtaken by a design "
        "getting better at reading the same text.\\n\\n"
        "**AND THE EDITOR STOPPED BECAUSE IT DISBELIEVED THE ONE INSTRUMENT "
        "THAT WAS STILL RIGHT.** It reported the remaining objections as "
        "'check-methodology artifacts or genuine spec contradictions' and "
        "stopped with 21 trials unspent. The audit says 5 of the 7 are SOUND -- "
        "REQ-0015.v2@n3, REQ-0064.t1@n3, REQ-0073.shipping@narrow, "
        "REQ-0087.shipping and REQ-0088.shipping each decide on a design that "
        "satisfies the specification and convict it nowhere, so each objection "
        "is a real defect. Only REQ-0081's two bodies are unsound, and the "
        "editor was right about those. **It threw away five true objections "
        "along with two false ones, on one mis-diagnosis.**\\n\\n"
        "**SO THE PLAN'S OWN CONCLUSION NEEDS SPLITTING.** 'A spec-derived "
        "criterion cannot carry this design further' is TRUE of a consensus "
        "over designs and NOT SHOWN of checks over sentences. The gap for the "
        "checks is COVERAGE -- 117 of them produce 7 objections on a design "
        "wrong at 205 of 348 testpoints -- and coverage is the one thing the "
        "goal explicitly licenses regenerating.\\n\\n"
        "**WHAT IS CALIBRATED AND WHAT IS NOT, stated before the arm runs.** "
        "Choosing WHICH instrument to keep was decided by an audit against the "
        "known-good design; that is calibration, which the goal permits, and it "
        "is labelled. The criterion that then drives the editor reads only "
        "requirement sentences. No figure from a run built this way may be "
        "quoted as an uncalibrated golden-free score."
    )


def sequencing_the_two_instruments_breaks_the_band() -> str:
    """The first arm on this plan to leave the 205-210 band, and it is the
    measured law applied rather than another instrument.

    `the_two_instruments_came_apart_and_only_one_was_overtaken` measures that
    the consensus has inverted (28.5%) and the checks have not (71.4%). This is
    what follows if that is acted on: use each instrument only in the region
    where it is still the better reader.
    """
    return (
        "**RUN THE DENSE CRITERION UNTIL IT IS OVERTAKEN, THEN SWITCH.** The "
        "consensus carried the design from 279 differing testpoints to 205 and "
        "was measured overtaken doing it. Starting the CHECKS from exactly "
        "that point, with the cell units out of the latch:\\n\\n"
        "    arm                                 testpoints of 348   cells\\n"
        "    L, unedited                               279           4,450\\n"
        "    consensus alone                           210           3,890\\n"
        "    117 checks alone, from unedited L         206           3,866\\n"
        "    both stacked, unweighted                  205           3,608\\n"
        "    both stacked, equal weight                205           3,696\\n"
        "    CONSENSUS, THEN CHECKS AT THE CROSSING    186           3,052\\n\\n"
        "**186 of 348, against a band five arms could not leave.** All three "
        "miter pins green in the same process; `first_miss_err` is repaired to "
        "never differing.\\n\\n"
        "**AND SEQUENCE IS THE WHOLE OF IT, WHICH THE ARMS ABOVE ISOLATE.** The "
        "same 117 checks driven from the UNEDITED design reach 206. The same "
        "two instruments SUMMED, at either weighting, reach 205. Only using "
        "each where it still has headroom reaches 186 -- so this is not a "
        "better criterion, it is the same two criteria applied in the order "
        "their accuracies dictate.\\n\\n"
        "**THE VERDICT IS STILL `DIFFERS`, AND THE PRE-REGISTRATION SAYS WHERE "
        "THIS LANDS.** The target was TWO objections, because REQ-0081's two "
        "bodies convict the known-good design and the other five spare it, so "
        "two is what a correct design scores against this set. The run reached "
        "**five**: REQ-0081's two unsound ones, plus **three SOUND objections "
        "still standing** -- REQ-0015.v2@n3, REQ-0064.t1@n3 and "
        "REQ-0087.shipping. That is the pre-registered 'partial' band.\\n\\n"
        "**SO THE CHECKS HAD NOT RUN OUT EITHER: 3 of 5 remaining objections "
        "are real, and the editor stopped with 8 of 21 trials unspent.** Their "
        "precision on this design is 60%, still above the 50% at which an "
        "instrument starts doing harm. The binding constraint here is not the "
        "criterion's authority and not the budget -- it is that 117 checks "
        "produce five objections on a design differing at 186 testpoints, and "
        "the editor reported a genuine repair (an off-by-one in the "
        "refill-completion count) that moved the check count by ZERO.\\n\\n"
        "**THAT IS A COVERAGE NUMBER, AND COVERAGE IS THE ONE THING THE GOAL "
        "LICENSES REGENERATING.** It is also the first time on this plan that "
        "the remaining gap has been attributed to something with a known "
        "remedy rather than to a property of specifications."
    )


def the_soundness_filter_selects_exactly_the_silent_checks() -> str:
    """#99 measured on one fresh round, at total separation, with the split
    made by a rule that never saw the design.

    Every earlier statement of this is distributional -- a corpus scored, a
    conviction count tabulated. This is 42 checks authored in one round by one
    standard, partitioned by the best golden-free soundness filter on this plan,
    and then asked the only question that matters for a repair loop.
    """
    return (
        "**THE GAP ROUND.** 21 behavioural requirements the 117-check set does "
        "not touch, two independent draws each, authored STRICT because this "
        "plan measured the soundness boundary findable from the over-strict "
        "side (7 of 47) and not from the weak side (0 of 34). Integrity: 42 of "
        "42 answered, 0 broken, 0 bodies shared across requirements.\\n\\n"
        "**THE MINORITY RULE SPLIT THEM 9 / 31**, keeping a check that convicts "
        "at most two of the seven spec-derived designs -- the filter this plan "
        "measures at 59-of-59 precision against a 31% base rate. Then each half "
        "was decided over the design the checks-only arm produced:\\n\\n"
        "                                   checks   OBJECT   decide and PASS\\n"
        "    KEPT by the minority rule         9        0            9\\n"
        "    marked for NARROWING             31       27            4\\n\\n"
        "**NINE OF NINE SILENT, TWENTY-SEVEN OF THIRTY-ONE OBJECTING.** The "
        "admissible checks have nothing to say about the design; every check "
        "with something to say is inadmissible.\\n\\n"
        "**AND THE MECHANISM IS THE SAME COUPLING MEASURED TWICE ALREADY.** A "
        "soundness filter built on a population of spec-derived designs selects "
        "for checks that SPARE spec-derived designs -- and the design under "
        "test is one. The filter cannot distinguish 'spares a correct design' "
        "from 'spares this design', because on this evidence they are the same "
        "predicate. That is `a_criterion_only_corrects_where_it_beats_the_"
        "design_under_test` arriving at the SELECTION step rather than the "
        "scoring step, and it is why the filter's excellent precision buys "
        "nothing: it is precise about the wrong population.\\n\\n"
        "**WHAT THE ROUND BOUGHT AND WHAT IT DID NOT.** Span goes 47 -> 52 of "
        "89 = 58%, and 47 -> 52 of 68 behavioural = 76%. Objections on the "
        "design go up by ZERO. **That is the volume round's result reproduced "
        "on a targeted population with a better standard** -- +3 requirements "
        "and +0 objections then, +5 and +0 now -- and it is the third time span "
        "and signal have come apart on this plan.\\n\\n"
        "**SO SPAN IS NOT THE METRIC, AND THIS IS THE CLEANEST DEMONSTRATION "
        "OF IT.** A set can be grown to cover more of a specification by adding "
        "checks selected for soundness, and gain no ability whatever to say "
        "that a wrong design is wrong. The narrowing round is the only route "
        "from the objecting side to the admissible one, and its measured rate "
        "is about 15%."
    )


def narrowing_crosses_the_boundary_without_landing_on_it() -> str:
    """The coverage route closed with a mechanism rather than a tally, and it
    is the strength round's finding arriving from the opposite direction.

    `the_soundness_filter_selects_exactly_the_silent_checks` measures the gap
    round splitting 0-of-9 admissible-and-objecting against 27-of-31
    objecting-and-inadmissible. Narrowing is the only route between those
    states. This is that route, run.
    """
    return (
        "**31 OVER-STRICT CHECKS, NARROWED, WITH THE ADMISSIBLE OBJECTION THIS "
        "PLAN VALIDATED** -- *your check objects to N of seven independently "
        "written implementations of this specification* -- and a leak check "
        "showing 0 lines of the reference design's source, 0 testpoint ids, 0 "
        "equivalence verdicts and 0 occurrences of the word 'golden' across all "
        "31 prompts. Integrity: 31 of 31 answered, 0 broken, 0 shared bodies.\\n\\n"
        "    outcome                                    checks   convictions\\n"
        "    narrowed to death -- admissible, SILENT       9      7 -> 0\\n"
        "    still over-strict                            22      7 -> 7, 6 -> 5\\n"
        "    ADMISSIBLE AND OBJECTING                      0        --\\n\\n"
        "**ZERO OF THIRTY-ONE, AGAINST A MEASURED FIRST-ATTEMPT RATE OF 15%.** "
        "And the conviction column is the finding rather than the count: **every "
        "check that became admissible went from SEVEN convictions to ZERO.** Not "
        "one landed at one or two. There is no gradual narrowing here -- a check "
        "either demands something all seven independent implementations violate, "
        "or it demands nothing.\\n\\n"
        "**THAT IS THE STRENGTH ROUND'S RESULT FROM THE OPPOSITE DIRECTION.** "
        "That round pushed 34 sound-and-blind checks to assert more: 34 of 34 "
        "crossed the boundary and 0 landed in between. This pushes 31 "
        "over-strict checks to assert less: 9 of 9 that moved crossed it "
        "completely. **Both directions overshoot, and the target between them is "
        "measured empty on 65 attempts.**\\n\\n"
        "**SO THE COVERAGE ROUTE IS CLOSED, AND IT CLOSES ON A TRANSFORMATION "
        "RATHER THAN A YIELD.** The residue after the sequenced run was "
        "attributed to coverage -- 117 checks producing five objections on a "
        "design differing at 186 of 348 testpoints -- and coverage is what the "
        "goal licenses regenerating. It was regenerated, on a targeted "
        "population, at the standard this plan's own measurements prescribe, "
        "with both rounds' integrity clean. Span went 47 -> 52 of 89 = 58%, "
        "and objections went 5 -> 5.\\n\\n"
        "**WHAT A SECOND NARROWING ROUND IS WORTH, PRICED RATHER THAN GUESSED.** "
        "22 checks are still over-strict, and this plan measured a second "
        "attempt on the same check at 1 of 28 = 4%. The observed jump -- 7 to 0 "
        "with nothing between -- predicts that whatever moves will overshoot as "
        "the first nine did. Expected yield is about one check, and the shape "
        "says it will not be an admissible objecting one."
    )


def the_editor_could_not_aim_at_what_it_was_judged_by() -> str:
    """The sixteenth counting-shaped defect on this plan, mine, and the first
    one that plausibly explains a run stopping early rather than a number
    reading wrong.

    The checks-only arm stopped with three SOUND objections standing and eight
    of twenty-one trials unspent, reporting that it could not isolate the
    remaining defect "without a waveform (unavailable in this harness)".
    """
    return (
        "**THE EDITOR WAS JUDGED BY 117 CHECKS AND COULD AIM AT TEN OUTPUTS.** "
        "The driver latched on the checks and nothing else -- the consensus cell "
        "units were deliberately out of the ratchet -- but `views()` still "
        "returned one pseudo-requirement per declared OUTPUT and nothing for the "
        "checks, and the check verdicts entered `req_results` under synthetic "
        "`chk:<key>` ids that no view matched. Three consequences, all live in "
        "the run:\\n\\n"
        "  * `focus <check>` returned 'Unknown requirement', so the dataflow "
        "slice could only ever start from a CONSENSUS output -- the instrument "
        "that arm had removed.\\n"
        "  * `explain <check>` failed identically, making the span, the boundary "
        "trace and the perturbation `explain_failure` already computes "
        "unreachable for every check.\\n"
        "  * `failing` listed outputs, not checks.\\n\\n"
        "**THE WAVEFORM WAS THERE.** It was keyed to a requirement id the "
        "session had no view for, so the editor's report is literally accurate "
        "about its experience and wrong about the cause -- and neither it nor "
        "any gate could have told the difference.\\n\\n"
        "**THE FIX IS ONE VIEW PER CHECK**, carrying the check's key as its uid, "
        "the requirement's own SENTENCE as its text, and "
        "`ports_read(oracle, contract)` as its ports -- which is exactly "
        "`dynamic_slice`'s input shape, so the slice starts from the ports that "
        "check watches. On one failing check that is fifteen ports including "
        "five probes, against the single output it could name before.\\n\\n"
        "**AND THE FIRST ATTEMPT AT THE FIX DID NOT WORK, FOR THE REASON THIS "
        "PLAN HAS ALREADY RECORDED ONCE.** The views were built inside "
        "`review()` -- which `focus` and `explain` never run. Every CLI call is "
        "a fresh process, so the views existed only during a commit and every "
        "other command still saw ten outputs. That is the same fresh-process "
        "fact that left the dataflow slice dead in every run on this plan, "
        "arriving in a different function. It has to be built where the SESSION "
        "is built, not where the verdicts are.\\n\\n"
        "**WHAT THIS DOES AND DOES NOT CLAIM.** It does not claim the editor "
        "would have converged. It claims that the run which stopped at five "
        "objections with eight trials left was aiming a requirement-oriented "
        "slice at a requirement it could not name, and that the single-variable "
        "re-run is the only way to find out what that cost. Reporting the "
        "earlier stop as a property of the editor, without this, would have "
        "been reporting my harness as a finding."
    )


def five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck() -> str:
    """The first failure on this plan located in the SEARCH rather than in the
    criterion, and it is the sharpest statement here about the editor as the
    goal's validator.

    Run with check-aware `focus`/`explain`, same criterion, same design, same
    budget as the arm that stopped at five objections.
    """
    return (
        "**THE RUN MADE NO PROGRESS: 5 objections to 5, two of twenty-one "
        "trials, both commits rejected and discarded.** What it produced is the "
        "diagnosis.\\n\\n"
        "**COMMIT 1 CHANGED `dc_addr` TO SATISFY REQ-0087.shipping. IT DID -- "
        "AND BROKE FOUR OTHERS**: REQ-0029.t2, REQ-0030.band@band, "
        "REQ-0030.control and REQ-0087.control, taking the count 5 -> 8. The "
        "editor concluded that REQ-0087.shipping and REQ-0087.control 'are "
        "compiled from the same sentence but demand opposite values of dc_addr "
        "... no memoryless formula satisfies both'.\\n\\n"
        "**THE AUDIT SAYS ALL FIVE SPARE THE KNOWN-GOOD DESIGN** -- 348, 348, "
        "348, 256 and 279 decisions, zero convictions each. **A design "
        "satisfying all five exists and is that one.** The set is sound and "
        "JOINTLY SATISFIABLE, the design satisfies four and fails one, and the "
        "single-step edit that fixes the one breaks the other four.\\n\\n"
        "**SO THIS IS A SEARCH FAILURE, NOT AN ORACLE FAILURE, AND IT IS THE "
        "FIRST ONE ON THIS PLAN.** Every earlier negative here is about a "
        "criterion -- inverted, silent, over-strict, or precise about the wrong "
        "population. This one has a criterion that is sound, jointly "
        "satisfiable and correctly objecting, and the editor cannot reach the "
        "satisfying design because every local move that clears one demand "
        "violates four. It is a local optimum, and the loop has no mechanism "
        "for leaving one: `commit` judges the whole suite, so a repair that "
        "must pass through a worse intermediate state can never latch.\\n\\n"
        "**AND THE CONTRADICTION CLAIM IS NOW REPRODUCIBLE, WHICH MAKES IT A "
        "PROPERTY RATHER THAN AN ANECDOTE.** Two independent Sonnet editors, "
        "given different tooling, both concluded the REQ-0087 group is "
        "mutually unsatisfiable, and both are wrong by the same one-line audit. "
        "That is the sixth structural-contradiction claim on this plan and the "
        "sixth refutation -- but the first where two editors reached the same "
        "false claim independently, so it is a systematic misreading of this "
        "requirement rather than one agent's error.\\n\\n"
        "**TWO THINGS THAT QUALIFY THE RUN, BOTH MINE.** The evidence fix was "
        "PARTIAL: the driver runs the suite with `trace=False` and never "
        "populates `rows` for a check, so `explain` returned the requirement "
        "sentence, the verdict and the span but NOT the boundary trace, the "
        "suspect blocks' internals or the perturbation analysis -- the three "
        "things that would have shown the editor WHY its edit broke four "
        "checks. It reported the gap precisely rather than treating it as a "
        "dead end. And the editor read the check BODIES from disk. That is "
        "admissible -- they are spec-derived artifacts and contain nothing from "
        "the known-good design -- but it changes the experiment from 'can an "
        "editor repair from objections' to 'from objections plus the criterion's "
        "source', and the two are not the same question."
    )


def three_dropped_values_and_one_root_cause() -> str:
    """The evidence path, completed -- and the three defects between the editor
    and the evidence were all the same mistake in three functions.

    `the_editor_could_not_aim_at_what_it_was_judged_by` fixed the first. The
    editor's next report named the remaining two precisely, and neither was a
    missing capability: both were values computed and then dropped.
    """
    return (
        "**`explain_failure` HAS RENDERED ALL FIVE PARTS OF ITS ANNOTATION SINCE "
        "IT WAS WRITTEN. THE DRIVER WAS FEEDING IT THREE EMPTY ARGUMENTS.**\\n\\n"
        "    what was missing        why                          the fix\\n"
        "    the boundary trace      `_Res(rows=)` never set      pass the rows\\n"
        "    the perturbation        emitted only `if rows`       the same rows\\n"
        "    the block internals     `vcd_by_tp` never populated  map by filename\\n\\n"
        "**ONE ROOT CAUSE, THREE FUNCTIONS, AND IT IS THE SAME ONE THIS PLAN HAS "
        "ALREADY RECORDED TWICE: every CLI call is a fresh process.** The rows "
        "were computed in `review()` and thrown away one line later. "
        "`req_accepted.json` round-trips `ok`, `edge`, `detail` and `tp_uid` and "
        "nothing else, so a reloaded `_Res` has no rows even when the review "
        "that produced them succeeded. And the suite had written **349 "
        "waveforms** to disk while the payload told the editor 'this run dumped "
        "no waveform' -- which is why an editor spent a whole run reading "
        "boundary ports and source, and said so.\\n\\n"
        "**THE ROWS DID NOT NEED PERSISTING.** They are derivable from the trace "
        "the loader already reads, so the fix is to rebuild rather than store "
        "them -- and the waveforms needed nothing but a filename map.\\n\\n"
        "**AND THE FIFTH PART SAYS SOMETHING NO EDITOR ON THIS PLAN HAS SEEN.** "
        "On the check two independent editors called unsatisfiable, the "
        "perturbation analysis reports:\\n\\n"
        "    NO single-value change at the deciding edge satisfies this check,\\n"
        "    so the defect is TEMPORAL -- the ordering or the timing, not a\\n"
        "    wrong value at one edge.\\n\\n"
        "**BOTH EDITORS TREATED IT AS A FORMULA PROBLEM** -- 'no memoryless "
        "formula satisfies both' -- and made memoryless edits to `dc_addr`. The "
        "instrument that would have told them the class of defect was built, "
        "was correct, and was unreachable because three values were dropped "
        "between the review and the prompt.\\n\\n"
        "**SO THE HONEST READING OF THE TWO EARLIER STOPS IS THAT NEITHER "
        "MEASURED THE EDITOR.** They measured a loop that judged by checks and "
        "could not aim at one, then a loop that could aim but had nothing to "
        "show. Only the run after this one is evidence about whether a Sonnet "
        "editor can repair from a sound spec-derived criterion, and reporting "
        "either earlier stop as an editor result would have been reporting my "
        "harness as a finding."
    )


def the_editor_oscillates_between_two_clauses_of_one_sentence() -> str:
    """The first run on this plan where the editor was BOTH judged by checks it
    could aim at AND handed the evidence to aim with -- so the first that is
    evidence about the editor rather than about my harness.

    `three_dropped_values_and_one_root_cause` closed the evidence path and said
    the run after it would be the measurement. This is that run's first four
    trials, scored by re-deciding the 117 checks over each design's own traces
    rather than by reading the run's bookkeeping.
    """
    return (
        "**FOUR COMMITS, ALL REJECTED, AND THE ACCEPTED DESIGN IS BYTE-IDENTICAL "
        "TO THE ONE THE RUN STARTED FROM.** Not a stalled loop -- a ratchet doing "
        "exactly its job, on a design that sits at a point the editor cannot "
        "leave in one step.\\n\\n"
        "**THE SPECIFICATION STATES TWO OBLIGATIONS ABOUT ONE WIRE, AND THIS "
        "DESIGN SATISFIES EXACTLY ONE OF THEM AT A TIME.** REQ-0087 carries both "
        "in a single sentence -- *drive dc_addr to start_addr during hit/miss "
        "evaluation and to saved_addr during post-evaluation BIU transfers* -- "
        "and REQ-0029 and REQ-0030 restate them separately:\\n\\n"
        "    clause A  start_addr WHILE EVALUATING      REQ-0029, REQ-0087.shipping\\n"
        "    clause B  saved_addr DURING THE TRANSFER   REQ-0030 (5 bodies), REQ-0087.control\\n\\n"
        "    accepted   (biu_read || biu_write) ? saved_addr_r : start_addr\\n"
        "               satisfies B, fails A          -> 5 objections of 117\\n"
        "    staged     (hitmiss_eval_r || in_idle) ? start_addr : saved_addr_r\\n"
        "               satisfies A, fails B          -> 8 objections of 117\\n\\n"
        "Every attempt clears `REQ-0087.shipping` and introduces `REQ-0029.t2`, "
        "`REQ-0030.band@band`, `REQ-0030.control` and `REQ-0087.control`. **One "
        "objection traded for four.**\\n\\n"
        "**AND THE RATCHET IS NOT MISCALIBRATED, WHICH HAD TO BE CHECKED BEFORE "
        "THE OSCILLATION COULD BE BLAMED ON THE EDITOR.** REQ-0030 carries five "
        "bodies against REQ-0029's one, so a body-count latch could have been "
        "encoding an authoring accident as a preference between two obligations "
        "the specification weights equally. It is not: at REQUIREMENT "
        "granularity the trade is 4 failing to 6, worse by the same sign. The "
        "refusal is correct at both granularities.\\n\\n"
        "**SO THIS IS THE OSCILLATION THE GOAL ASKS ABOUT, ON RTL REPAIR, WITH A "
        "SOUND SPEC-ONLY CRITERION AND A COMPLETE EVIDENCE PATH** -- and it is "
        "not the criterion swapping failure modes, which is what every earlier "
        "oscillation on this plan turned out to be. Both clauses are real, both "
        "are stated, and a correct design meets both; the design meets one, and "
        "one memoryless edit can only move which.\\n\\n"
        "**THE INSTRUMENT HAD ALREADY SAID SO AND WAS NOT ACTED ON.** The "
        "perturbation analysis reports on this exact check that *no single-value "
        "change at the deciding edge satisfies it, so the defect is TEMPORAL*. "
        "Both rejected edits are memoryless mux rewrites, and the second differs "
        "from the first mainly by which registered flag it reads. **That is now "
        "a fact about the editor rather than about the harness, which is what "
        "closing the evidence path bought.**"
    )


def a_committing_design_is_not_stable_while_the_commit_runs() -> str:
    """Mine, caught by a diff that went empty between two reads.

    The lesson is not the file layout; it is that a run's artifacts have a
    meaning ONLY at rest, and this plan's instruments read them while moving.
    """
    return (
        "**`dut.v` IS REWRITTEN DURING A COMMIT AND ROLLED BACK WHEN THE RATCHET "
        "REFUSES, SO A MID-FLIGHT READ RETURNS A CANDIDATE THAT MAY NEVER HAVE "
        "BEEN ACCEPTED.** I read it between a commit's start and its verdict, "
        "found it changed, concluded the design had moved, and started grading "
        "it. Thirty seconds later the same file was back to the baseline.\\n\\n"
        "**THE TELL WAS A DIFF THAT WENT EMPTY.** `diff L_afterCHK.v "
        "loopEV/dut.v` printed fifteen lines, then nothing, with no edit of mine "
        "in between -- which is not something a settled run does.\\n\\n"
        "**THREE ARTIFACTS OF THIS RUN MEAN DIFFERENT THINGS AND ONLY ONE IS THE "
        "ACCEPTED DESIGN:**\\n\\n"
        "    dut.v      the accepted design AT REST; a candidate mid-commit\\n"
        "    staged.v   the staged buffer, which SURVIVES a rejection by design\\n"
        "    best.v     written by `note_best`, which tracks the CELL count --\\n"
        "               an instrument this arm removed from the ratchet\\n"
        "    run1/      overwritten by every review, so it describes whichever\\n"
        "               text was last simulated, not the one that latched\\n\\n"
        "**SO A DESIGN MUST BE READ WITH THE RUN QUIESCENT AND SCORED IN ITS OWN "
        "CLEAN DIRECTORY**, which this plan already required for the second "
        "reason and had not stated for the first. The cost here was one wasted "
        "scoring run, caught before any number from it was reported -- and the "
        "same defect reported would have been a design movement that never "
        "happened."
    )


def a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget() -> str:
    """The population rule's blind spot, found by an editor spending three of
    six trials trying to satisfy a demand no design in this build can meet.

    This is the first instrument on the plan that removes an over-strict check
    WITHOUT reading a known-good design and without a population vote.
    """
    return (
        "**TWO OF THE FIVE OBJECTIONS WERE ON A STATE THIS BUILD CANNOT ENTER, "
        "AND THE GOLDEN-FREE SOUNDNESS RULE KEPT BOTH.**\\n\\n"
        "    in_srefill4 true on   0 of 27,335 edges, over 9 independent designs\\n"
        "    k-induction           UNREACHABLE, sby PASS, unbounded\\n"
        "    control in_lrefill3   REACHABLE, counterexample -- the prover is\\n"
        "                          not proving everything unreachable\\n"
        "    the specification     'an OPTIONAL store-miss refill WHEN\\n"
        "                          OR1200_DC_STORE_REFILL is enabled'\\n"
        "    build_config          OR1200_DC_STORE_REFILL: false\\n\\n"
        "So the absence is spec-licensed and formally proved: `UNREACHABLE`, "
        "not `DESIGN_MISSING_STATE`.\\n\\n"
        "**AND THE MINORITY RULE CANNOT SEE IT, WHICH IS THE FINDING.** Both "
        "checks convict 2 of 7 spec-derived designs, so *convicts at most two* "
        "KEEPS them at its 59-of-59 precision. The mechanism: **a check on an "
        "unreachable state mostly ABSTAINS, and abstention is not conviction, so "
        "silence is scored as soundness.** Every population rule on this plan "
        "counts convictions, so every one of them is blind to exactly this "
        "class -- and the class is not rare, it is whatever the build "
        "configuration switches off.\\n\\n"
        "**THE COST IS NOT A WASTED OBJECTION. IT IS A WRONG STEER, AND IT TOOK "
        "HALF THE BUDGET.** Commits 1, 2 and 3 of six all `define`d "
        "`OR1200_DC_STORE_REFILL` -- the editor changing the BUILD "
        "CONFIGURATION to reach a state its checks demanded. Three trials, zero "
        "repairs, and one of them cost twelve new objections. An over-strict "
        "check does not merely fail to help; it can drive the editor to "
        "contradict the configuration the specification itself fixes.\\n\\n"
        "**AND THE CHECKS READ NO PROBE**, which is why they fire at all: they "
        "infer 'SREFILL4 entry' from a port pattern that occurs in other "
        "states. That is the lossy proxy the probe architecture exists to "
        "remove, appearing as an unsatisfiable demand rather than as a false "
        "alarm.\\n\\n"
        "**THE SCREEN, AND EVERY LEG OF IT IS GOLDEN-FREE:** a requirement "
        "leaves the denominator when the spec licenses the absence by a quoted "
        "span, the config key is off, a prover says the state is unreachable ON "
        "THE DESIGN UNDER TEST, and the requirement is ENTIRELY about it. The "
        "last leg is what keeps REQ-0026, REQ-0002, REQ-0036 and REQ-0088 in: "
        "they name SREFILL4 as one branch beside a live LREFILL3 clause.\\n\\n"
        "    criterion as run      5 objections of 117 checks over 54 requirements\\n"
        "    after the screen      3 objections of 114 checks over 52 requirements\\n"
        "    span                  52 of 89 = 58%, A MAJORITY\\n\\n"
        "**AND THE THREE THAT REMAIN ARE REAL** -- REQ-0015.v2@n3, "
        "REQ-0064.t1@n3, REQ-0087.shipping -- so for the first time on this "
        "plan every objection the editor is asked to clear is one some design "
        "in this build could clear."
    )


def six_designs_satisfy_the_group_three_editors_called_unsatisfiable() -> str:
    """The 'mutually unsatisfiable' claim, refuted constructively rather than
    by argument -- with witnesses, from the spec-derived population alone.

    Three editors in succession have stopped on this group and reported that no
    design can satisfy it. Each was reasoning from its own failed attempts.
    """
    return (
        "**SIX OF SEVEN INDEPENDENTLY WRITTEN SPEC-DERIVED DESIGNS SATISFY ALL "
        "SEVEN dc_addr CHECKS AT ONCE.** B, C, D, E, F and H pass every one of "
        "`REQ-0087.shipping`, `REQ-0087.control`, `REQ-0029.t2`, "
        "`REQ-0030.control`, `REQ-0030.band@band`, `REQ-0030.shipping` and "
        "`REQ-0030.merge@merge`. G fails four. The design under repair fails "
        "**exactly one** -- `REQ-0087.shipping`.\\n\\n"
        "**SO THE GROUP IS JOINTLY SATISFIABLE, AND THE PROOF IS SIX WITNESSES "
        "RATHER THAN AN ARGUMENT.** Every previous refutation of this claim on "
        "the plan was an audit saying the checks spare a known-good design, "
        "which is admissible only as an audit. This one reads nothing but "
        "designs the specification produced, so it is a golden-free refutation "
        "of a golden-free claim.\\n\\n"
        "**AND IT RECLASSIFIES THE FAILURE.** The editor is ONE check away from "
        "a point six of its siblings occupy. That is not an oracle defect, not "
        "an over-strict demand and not a contradiction in the set -- it is a "
        "SEARCH failure, in a place where the target is known to be occupied "
        "and known to be one step from where the loop is standing.\\n\\n"
        "**THREE EDITORS HAVE NOW MADE THE SAME WRONG CALL**, each from its own "
        "failed attempts and each stating it as a property of the checks. The "
        "pattern is worth naming: an editor that cannot find a satisfying edit "
        "concludes none exists, and nothing in the loop can contradict it, "
        "because the loop shows it only its own trajectory. **The population "
        "can contradict it, cheaply, and no editor has ever been shown that** "
        "-- the same seven designs the soundness rule already reads are sitting "
        "unused as an existence proof."
    )


def seven_readings_seven_designs_and_the_soundness_sufficiency_trade() -> str:
    """The session's central measurement, with a formal instrument on both ends
    and golden appearing only in the audit column.

    Sufficiency -- does the set FORCE equivalence -- had never been measurable
    here. It is, without a reference: if two designs both satisfy the set and
    are not equivalent to each other, the set does not force equivalence.
    """
    return (
        "**SEVEN INDEPENDENTLY WRITTEN SPEC-DERIVED DESIGNS FALL INTO SEVEN "
        "EQUIVALENCE CLASSES.** All 21 pairs return `DIFFERS` under a bounded "
        "reset-constrained miter that reads no known-good design. The "
        "specification is compatible with at least seven distinct behaviours, "
        "and that is measured on the designs themselves rather than inferred "
        "from cell disagreement.\\n\\n"
        "**SO A CRITERION ACCEPTING EXACTLY ONE IS DOING THE MOST A CORRECT "
        "CRITERION COULD.** That settles a reading the plan could not settle "
        "before: 'the set rejects 6 of 7' is DISCRIMINATION, not "
        "over-strictness, because at most one of seven mutually inequivalent "
        "designs can match any reference.\\n\\n"
        "**AND SOUNDNESS DOES NOT SURVIVE CONJUNCTION.** The minority rule "
        "bounds each CHECK at two convictions of seven, at 59-of-59 precision. "
        "A design is rejected when ANY of 114 members objects, so rejections "
        "UNION:\\n\\n"
        "    worst single check convicts        3 of 7\\n"
        "    the 114-check SET rejects          6 of 7\\n\\n"
        "Every per-check soundness filter on this plan is blind to this by "
        "construction, and eight requirements do all the rejecting.\\n\\n"
        "**THE TRADE, BOTH ENDS MEASURED, GOLDEN ONLY IN THE AUDIT:**\\n\\n"
        "    set                    checks  span   accepts  *audit*  objects to\\n"
        "                                          of 7             the design\\n"
        "    screened                 114   58%      1      *10*        3\\n"
        "    UNANIMOUS (convicts 0)    89   47%      7      *0*         2\\n\\n"
        "**THE UNANIMITY RULE IS THE FIRST GOLDEN-FREE RULE HERE THAT PREDICTS "
        "SOUNDNESS RATHER THAN BEING HANDED IT.** Dropping every check that "
        "convicts even one of the seven removes **10 of the 10** checks that "
        "convict the reference -- **100% recall**, at 40% precision -- and the "
        "surviving 89 convict the reference **zero** times, verified directly "
        "with a probe-liveness guard. MAXSOUND was perfectly sound too and was "
        "SELECTED BY golden, so it was a ceiling; this is selected by the "
        "population and the audit merely confirms it.\\n\\n"
        "**AND EACH END FAILS THE GOAL IN THE OPPOSITE WAY, WHICH IS THE POINT."
        "** The screened set convicts the reference ten times, so zero "
        "objections is UNREACHABLE for a correct design and its accepted design "
        "B is measured `DIFFERS`. The unanimous set accepts all seven -- seven "
        "equivalence classes at once -- so it cannot force equivalence at all. "
        "**Over-strictness and vacuity as one defect with two signs, now at SET "
        "level, with a formal equivalence instrument on both ends instead of a "
        "proxy.**\\n\\n"
        "**WHAT MAKES THE UNANIMOUS SET WORTH RUNNING ANYWAY:** it is the first "
        "set on this plan that is simultaneously sound on the reference (0), "
        "discriminating on the design under repair (2 objections), and "
        "reachable -- zero objections is a state a correct design occupies. On "
        "every earlier set, terminating at zero was a certificate of "
        "NON-equivalence by arithmetic."
    )


def no_sound_subset_of_this_corpus_forces_equivalence() -> str:
    """Exhaustive over the SCORED corpus, with a witness pair.

    **CORRECTED, AND THE WORD DOING THE DAMAGE IS "CORPUS".** The argument
    below is valid and its conclusion was overstated: it enumerates the 114
    checks that were SCORED, and 477 further bodies over the 26 uncovered
    behavioural requirements existed on disk having never been decided against
    anything. Scoring them produced 14 checks that spare the reference AND
    convict B -- so the witness pair is removed and the exhaustive step no
    longer closes. See `a_proof_is_exhaustive_only_over_what_it_enumerated`.

    What survives unchanged: no sound subset of the checks that WERE scored
    forces equivalence, and no threshold on population convictions separates
    a reference-sparing check from a reference-convicting one.
    """
    return (
        "**THE CEILING SET IS EVERY CORPUS CHECK THAT SPARES THE REFERENCE** -- "
        "104 checks over 49 requirements, the 89 that convict none of the seven "
        "spec-derived designs plus the 15 that convict some and spare the "
        "reference. Verified: 104 decide on the reference, **0 convict it**.\\n\\n"
        "    designs it accepts of the seven      B, and only B\\n"
        "    B against the reference              *DIFFERS* (miter, three pins green)\\n\\n"
        "**SO THE REFERENCE PASSES, B PASSES, AND THEY ARE NOT EQUIVALENT.** "
        "That is sufficiency refuted with a WITNESS PAIR rather than left "
        "untestable, and the argument generalises in one step: any SOUND subset "
        "of this corpus is a subset of the 104, B satisfies all 104, so B "
        "satisfies every sound subset. **No sound subset of this corpus forces "
        "equivalence.** Exhaustive, no further runs required.\\n\\n"
        "**AND NO GOLDEN-FREE RULE RECOVERS THE CEILING EITHER**, which closes "
        "the other half. Splitting the 25 checks that convict at least one of "
        "the seven by whether they also convict the reference:\\n\\n"
        "    convicts 1 of 7    16 checks    5 convict the reference, 11 do not\\n"
        "    convicts 2 of 7     8 checks    4 convict the reference,  4 do not\\n"
        "    convicts 3 of 7     1 check     1 convicts the reference\\n\\n"
        "The split is near-even at every level, so **no threshold on population "
        "convictions separates a check that spares the reference from one that "
        "convicts it.** The ceiling set is selected BY the reference and is a "
        "ceiling, not a score.\\n\\n"
        "**WHAT THIS LEAVES.** Selection over this corpus is closed as a route "
        "to a set that forces equivalence -- not 'has not worked yet' but "
        "cannot, because the best sound set the corpus admits accepts two "
        "inequivalent designs. The remedy has to be NEW CHECKS separating B "
        "from the reference. Authoring those from the reference's behaviour is "
        "the control leak `oracles_stage.py:66-73` forbids, and nothing "
        "golden-free identifies that particular gap -- the seven designs are "
        "SEVEN equivalence classes and none of them is the reference, so the "
        "population cannot point at it either.\\n\\n"
        "**THE HONEST SCOPE.** This is one design, one corpus of 259 bodies and "
        "one population of seven. It says selection is exhausted HERE; it does "
        "not say a richer corpus could not contain a separating check."
    )


def a_proof_is_exhaustive_only_over_what_it_enumerated() -> str:
    """A retraction of this module's own strongest claim, and the cheapest
    measurement of the session is what forced it.

    The claim was not wrong about its population. It was wrong about which
    population it had.
    """
    return (
        "**THE CLAIM WAS THAT NO SOUND SUBSET OF THE CORPUS FORCES EQUIVALENCE**, "
        "argued exhaustively: the ceiling set is every check that spares the "
        "reference, it accepts design B, B differs from the reference, and any "
        "sound subset is a subset of the ceiling -- so B satisfies all of them. "
        "The argument is valid. Its premise was that the ceiling enumerated "
        "every sound check there is.\n\n"
        "**IT ENUMERATED EVERY SCORED CHECK.** The 26 behavioural requirements "
        "the ceiling did not cover had **477 distinct authored bodies on disk, "
        "not one of which had ever been decided against any design.** They were "
        "absent from the corpus the score was taken over, so the ceiling was "
        "never complete and the exhaustive step never closed.\n\n"
        "    scoring them, 7 designs x 348 testpoints, no model calls:\n"
        "      decide on some design                              350 of 477\n"
        "      spare the reference (audit, computed LAST)          59\n"
        "      **spare the reference AND convict design B**        **14, over 7 requirements**\n\n"
        "**FOURTEEN CHECKS REMOVE THE WITNESS PAIR.** REQ-0013, 0014, 0020, "
        "0022, 0032, 0037 and 0077 each carry a body that a correct design "
        "satisfies and B does not, so the sound set containing them rejects B "
        "and the impossibility argument no longer has its witness.\n\n"
        "**AND THE SET THIS BUILDS IS THE FIRST HERE THAT IS SOUND, WIDE AND "
        "ABLE TO REJECT.** Every check in either corpus that decides on the "
        "reference and spares it -- 104 scored plus 59 recovered = 163, over 59 "
        "of 87 requirements = 68%, audit 0:\n\n"
        "    objections at init, of 163\n"
        "      the reference                       0\n"
        "      the eight spec-derived designs      11 to 22 -- **ALL EIGHT REJECTED**\n\n"
        "Every previous set failed on exactly one of the three legs: rule B "
        "convicted the reference, so zero objections was unreachable for a "
        "correct design and terminating there was a certificate of "
        "NON-equivalence; MAXSOUND and the 104-check ceiling were sound and "
        "accepted a wrong design at zero. This one leaves zero reachable only "
        "for something no design in the population is.\n\n"
        "**WHAT DOES NOT CHANGE, AND IT IS THE HALF THAT MATTERS FOR A "
        "GOLDEN-FREE PIPELINE.** The 14 checks convict 4 to 7 of the 7 designs; "
        "the golden-free minority rule keeps at most 2 and therefore keeps "
        "**ZERO of them.** So the recovered corpus moves the CEILING and not "
        "the reachable-without-a-reference set, which is this module's central "
        "anti-correlation confirmed a third time on fresh bodies.\n\n"
        "**THE DISCIPLINE, WHICH IS THE PORTABLE PART.** An exhaustive argument "
        "is exhaustive over the population it enumerated, and 'the corpus' and "
        "'the corpus that was scored' are different sets. Selecting over a "
        "different corpus than the score is a defect this experiment has made "
        "eight times and has always caught as an inflated result; here the sign "
        "is reversed -- the score was taken over a SUBSET -- and it produced an "
        "impossibility instead. **A negative result needs its denominator "
        "checked exactly as hard as a positive one, and this one did not get "
        "it.**"
    )


def a_missing_body_reads_as_a_check_that_passed() -> str:
    """Caught before it ran, by reading the scorer rather than its output.

    The sixteenth counting-shaped defect on this plan, and the second in the
    same file -- whose docstring already names the defect class.
    """
    return (
        "`chkscore.py` takes its check SET from an environment variable and "
        "loaded its BODIES from a hardcoded filename, then looped:\n\n"
        "    body = BODIES.get(key)\n"
        "    if not body:\n"
        "        continue          # <- a check with no body is not scored\n\n"
        "**SO SCORING A 163-CHECK SET WHOSE BODIES LIVE IN TWO FILES WOULD HAVE "
        "DECIDED 104 OF THEM AND REPORTED THE RESULT UNDER THE 163's NAME.** "
        "Not an error, not a warning: 59 checks silently absent, and since the "
        "criterion is 'no check objects', **every absent check reads exactly "
        "like a check that passed.** A design rejected by 14 recovered checks "
        "would have scored zero objections and been reported as accepted.\n\n"
        "The file's own docstring already names this class -- *'a number that "
        "reads as a result and is measuring something else'* -- for the SET "
        "variable, one line above the BODIES variable that had the same defect. "
        "Fixed by parameterising the body source and REFUSING when any check in "
        "the set has no body, rather than skipping it.\n\n"
        "**THE GENERAL RULE: A SCORER MUST REFUSE AN INCOMPLETE DENOMINATOR, "
        "NEVER SKIP IT.** `drive9.review` learned the same rule from the "
        "opposite direction, refusing a suite that produced 8 of 348 traces -- "
        "a missing testpoint is a check that was never given its evidence, not "
        "a check that passed. Both are the same sentence about a different "
        "kind of gap."
    )


def a_recovered_check_catches_a_design_the_scored_set_almost_accepted() -> str:
    """The enlarged set tested against an EDITED design rather than an unchecked
    one, which is the only version of the test that can be Goodharted.

    Every earlier "does this set discriminate" measurement here was against
    designs written from the specification and never repaired. Those are easy:
    nothing has optimised against the checks. This one is against a design an
    editor spent seven trials driving down against 104 of the 163.
    """
    return (
        "An RTL editor was run against the 104-check scored ceiling from an "
        "unchecked spec-derived design, seven trials. Its ACCEPTED design, "
        "re-measured in a clean run directory with all three miter pins green "
        "in the same process:\n\n"
        "    against the 104 it was edited on      1 objection\n"
        "    **against the 163 with the recovered checks added**   **2**\n"
        "    testpoints differing from the reference              178 of 348 = 51%\n"
        "    miter                                               *DIFFERS*\n\n"
        "**THE EXTRA OBJECTION IS A RECOVERED CHECK** -- `REQ-0037`, one of the "
        "477 bodies that sat on disk unscored. It spares the reference, it "
        "convicts 5 of the 7 spec-derived designs, and it fires on a design "
        "seven trials of editing had driven to a single objection against the "
        "set it was being edited on.\n\n"
        "**SO THE RECOVERED CORPUS ADDS DISCRIMINATION AGAINST AN OPTIMISED "
        "DESIGN, NOT ONLY AGAINST NAIVE ONES.** That is the form of the claim "
        "worth having: a check set is only interesting where a loop has already "
        "pushed a design to satisfy everything else it says.\n\n"
        "**AND THE GOLDEN-FREE RULE REJECTS THAT CHECK.** Convicting 5 of 7 "
        "puts it far outside the minority rule's threshold of 2. So the check "
        "carrying the discrimination here is, once more, exactly the kind no "
        "rule reading only spec-derived designs will keep -- and one objection "
        "is discrimination, not sufficiency: the design still differs from the "
        "reference on 51% of testpoints."
    )


def the_accepted_design_is_not_the_last_one_simulated() -> str:
    """Two artifacts of one loop disagreed, and reading the wrong one produced a
    wrong number in each direction within the same hour.

    Recorded because the fix is not a code change -- the harness already refuses
    this -- it is knowing which file answers which question.
    """
    return (
        "A run directory holds three descriptions of 'the design' and they are "
        "not the same design:\n\n"
        "    dut.v               the ACCEPTED RTL. `commit` restores it byte for\n"
        "                        byte when a batch does not latch\n"
        "    run1/.../results    the traces of whatever was LAST SIMULATED --\n"
        "                        for a rejected commit, the CANDIDATE\n"
        "    best.v              selected by `note_best` on the CELL count, an\n"
        "                        instrument the checks-only arm removed from its\n"
        "                        own ratchet\n\n"
        "**MEASURED ON ONE LOOP, ONE HOUR, BOTH DIRECTIONS.** The accepted "
        "design carried 1 objection of 104. Scoring `run1` gave 3 -- the "
        "rejected candidate -- and the timestamp gap made it look as though the "
        "accepted-verdict file was stale, so the true number was called stale "
        "and the candidate's number reported as the correction. A clean suite "
        "run on `dut.v` restored the original: **1 of 104, and 2 of 163.**\n\n"
        "**THE TELL WAS THAT THE TWO DISAGREED IN BOTH DIRECTIONS AT ONCE** -- "
        "three checks objecting only in one reading, one check objecting only "
        "in the other. A stale file is behind; it does not also object to "
        "something the fresh one clears. Two sets differing in both directions "
        "are two different designs, never one design seen at two times.\n\n"
        "**THE RULE, AND THE HARNESS ALREADY STATES IT:** grade the accepted "
        "design in its OWN clean directory, never from the loop's working run "
        "directory, because that directory is overwritten by every review and "
        "describes whichever text was last simulated. The instruction existed, "
        "was written for exactly this, and was skipped because scoring the "
        "existing traces was faster."
    )


def three_editors_called_a_sound_set_self_contradictory() -> str:
    """The failure mode that ends these runs, now on its third reproduction --
    and the one-line refutation is not available without the reference.

    This is not a finding about a bad editor. All three were right that they
    could not find a joint reading, and wrong about what that implied.
    """
    return (
        "Three RTL editors, three different check sets, one conclusion: **the "
        "remaining objections are checks that contradict each other, so no "
        "design can satisfy them all.** Each time it is refutable in a single "
        "line, because every member of each set was selected by *decides on the "
        "reference and spares it*:\n\n"
        "    the reference satisfies all N of them AT ONCE\n"
        "    => no subset of the set is jointly unsatisfiable\n"
        "    => for every pair called contradictory, a joint reading exists\n\n"
        "On the 50-check ceiling an editor called `REQ-0032` and `REQ-0069` *a "
        "contradiction baked into the check set*; on the 163-check set another "
        "reported *three genuine, textually-evidenced conflicts between check "
        "variants that cannot both be satisfied*. Both false, same way.\n\n"
        "**AND IT IS EXPENSIVE RATHER THAN MERELY WRONG.** The ceiling run "
        "terminated with 8 of 14 trials unspent on this basis. The budget is "
        "not spent on the design; it is spent adjudicating the oracle set, and "
        "then abandoned.\n\n"
        "**WHY NO PROMPT FIXES IT.** From inside, *I cannot find a reading in "
        "which both hold* and *there is no such reading* are the same "
        "observation. The brief already says in as many words not to dismiss a "
        "check as unsatisfiable, and says to find the reading in which both "
        "hold. All three editors had that instruction and reached the "
        "conclusion anyway, with budget remaining.\n\n"
        "**THE PART THAT MATTERS FOR A GOLDEN-FREE PIPELINE, AND IT IS THE "
        "SHARP ONE.** The refutation above reads the reference. Nothing else "
        "here can supply it:\n\n"
        "    checks each satisfied by >=1 of 7 spec-derived designs   161 of 163\n"
        "    **designs in the population satisfying ALL 163**          **0**\n\n"
        "Per-check satisfiability does not compose -- 161 checks each having "
        "some design that satisfies it says nothing about whether one design "
        "satisfies them together, and here no design in the population does. "
        "**So *this set is jointly satisfiable* is exactly the fact the "
        "editor needs, and exactly the fact a golden-free pipeline cannot "
        "give it.**\n\n"
        "**AND THE WITNESS IS CIRCULAR.** The only golden-free evidence that a "
        "set is jointly satisfiable is a design satisfying all of it -- which "
        "is the artifact the loop is trying to produce. It cannot be an input "
        "to producing it. That is a structural gap in the golden-free story, "
        "not a missing instrument someone could go and build.\n\n"
        "**WHAT IS ADMISSIBLE, AND IT IS WEAKER.** A per-check population fact "
        "-- *N of seven independently written implementations satisfy this "
        "check* -- reads no reference and is true of 161 of the 163. It tells "
        "an editor that a check is individually achievable. It does not tell it "
        "the set is jointly achievable, and the difference is precisely where "
        "all three runs stopped."
    )


def the_gradient_holds_on_a_set_that_rejects_everything() -> str:
    """The 163-check run, reported under the reading its pre-registration fixed
    BEFORE dispatch -- which is not the reading its numbers invite.

    The numbers are the best on this plan. The pre-registration says they do not
    answer the question the run was built to answer, and that is the reading
    that governs.
    """
    return (
        "A Sonnet editor, 21 trials, on the 163-check set -- sound (audit 0), "
        "68% span, and objecting to all eight spec-derived designs. Started "
        "from an unchecked design written from the specification and never "
        "repaired. Re-measured in a clean run directory, three miter pins green "
        "in the same process:\n\n"
        "    at init          22 objections   279 of 348 testpoints (80%)   4,450 cells\n"
        "    after 19 trials   **5**          **190 of 348 (55%)**          **3,287**\n"
        "    grade            ***DIFFERS***\n\n"
        "**OBJECTIONS FELL 77%, DIVERGENCE 32%, CELLS 26% -- ALL THREE TOGETHER.** "
        "That has happened once before here and never on a set of this size. On "
        "a set where zero objections is reachable by a correct design and no "
        "design in the population reaches it, the accept criterion and the "
        "grade move the same way for 19 consecutive trials.\n\n"
        "**AND IT IS NOT A RESULT ABOUT THE SET, BY THE RULE FIXED BEFORE IT "
        "RAN.** The pre-registration named three outcomes; this is the third -- "
        "*an editor that stalls above zero with trials left measures the EDITOR, "
        "not the set.* It stopped at 5 objections with **2 trials unspent.** So "
        "the question the run was built to decide -- can this set drive a design "
        "to equivalence -- is still open. It is not the strongest negative and "
        "it is not a positive, and the temptation to bank the best numbers on "
        "the plan as one is exactly what the pre-registration exists to "
        "refuse.\n\n"
        "**FOUR OF THE FIVE REMAINING OBJECTIONS ARE RECOVERED CHECKS** -- "
        "bodies that had never been decided against any design before this "
        "round. Three are variants of one requirement firing at the same "
        "testpoint and edge, so the five objections are three distinct defects. "
        "Together with the same corpus catching a design already driven to one "
        "objection on the scored ceiling, **the checks doing the discriminating "
        "at the END of a long run are overwhelmingly the ones that were sitting "
        "unused**, which is where a Goodharted design would otherwise look "
        "finished.\n\n"
        "**AND THE BLINDNESS RESIDUE SHOWS UP AS A PORT, NOT A STATISTIC.** "
        "`first_hit_ack` is the worst output at init (1,063 differing cells) and "
        "ends at 938 -- essentially untouched, while every other output moved. A "
        "set spanning 68% of the specification left the single largest source of "
        "divergence almost unaddressed. That is this plan's 3.9%-of-exposed-"
        "decisions figure with a name on it."
    )


def blindness_has_a_golden_free_instrument_that_ranks_but_cannot_certify() -> str:
    """The first golden-free instrument here that strongly tracks a property
    that matters -- and the cell that would make it a certificate is n=8.

    Completeness has never had an instrument on this plan. This is one, and the
    honest reading is that it aims work rather than approving it.
    """
    return (
        "**THE CONSTRUCTION NEEDS NO REFERENCE.** Golden-based blindness asks "
        "whether a check decides where a port it reads is WRONG and passes -- "
        "and 'wrong' needs the reference. But the property a complete set must "
        "have is not *objects to wrong values*, it is *forces agreement*, so "
        "the reference drops out:\n\n"
        "    a check that PASSES TWO DESIGNS which DIFFER on a port it reads\n"
        "    is blind to that difference, whichever of the two is right\n\n"
        "The pair is the witness. Nine designs -- seven written independently "
        "from the specification and two produced by editors -- give 36 pairs, "
        "and every differing pair a check passes is a hole in the set with a "
        "testpoint and a port named.\n\n"
        "**MEASURED AGAINST THE REFERENCE-BASED ARTICLE, on 143 checks that "
        "read a real output:**\n\n"
        "                              golden: BLIND   not-blind\n"
        "      golden-free BLIND            118           17\n"
        "      golden-free CLEAN              3            5\n\n"
        "    Spearman(blind pairs, blind decisions)   **+0.908**\n"
        "    precision of the flag                    118/135 = 87%\n"
        "    **purity of the CLEAN cell**             **5/8 = 62%, n=8**\n\n"
        "**+0.908 IS BY A WIDE MARGIN THE STRONGEST GOLDEN-FREE CORRELATION ON "
        "THIS PLAN.** Six re-weightings of the corpus-as-an-order route reached "
        "nothing above +0.3 and the discriminating checks ordered designs "
        "BACKWARDS at -0.54. This ranks the residue that actually blocks the "
        "loop, and it reads no reference.\n\n"
        "**AND IT IS A PRIORITISER, NOT A CERTIFICATE, WHICH IS THE WHOLE "
        "DISTINCTION.** For approving a set the useful guarantee is the "
        "converse of precision: if it says CLEAN, is the check really not "
        "blind? That cell is 5 of 8. Worse, all five correct CLEANs are checks "
        "that NEVER DECIDE where their port is wrong -- clean by SILENCE, not "
        "by strength -- so the cell that would certify completeness is filled "
        "by exactly the checks that assert nothing. That is over-strictness and "
        "vacuity as one defect with two signs, arriving in the completeness "
        "instrument.\n\n"
        "**WHY THE CLEAN CELL CANNOT BE FIXED BY MORE DESIGNS ALONE.** A check "
        "reads CLEAN when no pair in the population differs on its ports. With "
        "a finite population that means *these designs happen to agree there*, "
        "which is the shared-misreading blind spot: the population agrees where "
        "the specification is clear and agrees WRONGLY where it is ambiguous. "
        "So the clean cell inherits precisely the failure that closed the "
        "consensus route.\n\n"
        "**WHAT IT IS GOOD FOR, STATED NARROWLY.** Ranking which checks to "
        "re-author, and handing each one a concrete admissible objection -- a "
        "pair, a testpoint, a port and two values -- which is the first "
        "COMPLETENESS objection this pipeline has ever been able to emit. "
        "Whether an author can act on it is a separate question with its own "
        "pre-registration."
    )


def a_witness_makes_blindness_authorable_and_does_not_break_the_trade() -> str:
    """The blindness round, against its own pre-registered bar -- which it
    misses -- and against the strength round, which it beats.

    Both readings are true at once and the pre-registered one governs what
    happens next.
    """
    return (
        "40 of the blindest checks, one per requirement, re-authored with the "
        "golden-free objection this pipeline has never been able to emit: *you "
        "passed design A and design B at testpoint T, they differ there on port "
        "P which you read, at least one is wrong and you said nothing.* 39 "
        "usable; integrity clean, 0 unchanged, 0 duplicates, leak check 0.\n\n"
        "**THE PRE-REGISTERED MEASURE IS A PAIR: sound AND strictly less "
        "blind.**\n\n"
        "    SOUND (spares the reference)          17 of 39\n"
        "    LESS BLIND                            24 of 39\n"
        "    **WIN = both**                        **6 of 39 = 15%**\n"
        "    the cost: became UNSOUND              22 = 56%   (strength round 68%)\n\n"
        "**THE BAR WAS 8 AND IT LANDED ON 6, so by the rule fixed before the "
        "round ran this is the middle band: real but weak, record the rate, do "
        "NOT rebuild the set on it.**\n\n"
        "**AND IT IS THE FIRST LEVER TO BEAT THE STRENGTH ROUND, WHICH IS THE "
        "OTHER TRUE THING.** Same author family, same direction of travel "
        "(assert more of the sentence), differing only in whether a concrete "
        "witness was attached:\n\n"
        "    STRENGTH   untargeted, 'assert every obligation'   **0 of 34**\n"
        "    BLINDNESS  a pair, a testpoint, a port, two values  **6 of 39**\n"
        "    two-sided Fisher exact                              **p = 0.0271**\n\n"
        "So the strength round's 0-of-34 was not a fact about asserting more. "
        "**It was a fact about asserting more with nothing to aim at**, and "
        "targeting is the variable -- which is what the narrowing round already "
        "suggested from the opposite direction and this confirms with a "
        "different objection.\n\n"
        "**A HEADLINE THAT HAD TO BE DEFLATED BEFORE IT WAS REPORTED.** Blind "
        "pairs over the round fall **26%**, which reads as the round working. "
        "Split by whether the check stayed sound:\n\n"
        "    SOUND checks     42,158 -> 38,529   **-9%**\n"
        "    UNSOUND checks   44,315 -> 25,474   **-43%**\n\n"
        "**A CHECK THAT CONVICTS THE REFERENCE CONVICTS MORE DESIGNS, SO IT "
        "PASSES FEWER PAIRS, SO ITS BLINDNESS FALLS FOR THE WRONG REASON.** "
        "Most of the -26% is over-strictness wearing completeness's clothes, "
        "and the honest reduction is -9%. `REQ-0001` is the pure case: 4,264 "
        "blind pairs to ZERO, with 168 convictions of the reference. Quoting "
        "the aggregate would have been the failure-mode swap this plan has "
        "retracted nine headlines for, in a metric built this session.\n\n"
        "**WHAT IT SETTLES.** Blindness IS authorable against -- the objection "
        "is admissible, emittable and acted on. It does not break the trade: "
        "22 checks bought their completeness with soundness, and the six that "
        "did not are 15% of the attempt. The completeness residue is reducible "
        "at roughly the rate every other authoring lever on this plan has "
        "measured, and by the same mechanism it always fails -- most authors "
        "asked to assert more cross the soundness boundary instead of "
        "approaching it."
    )


def blindness_is_correlated_across_checks_so_strengthening_one_adds_nothing() -> str:
    """Why every authoring round on this plan plateaus, measured at set level
    for the first time -- and a correction to the metric I used to measure it.

    The per-check score said the round worked. The set-level score says its
    contribution was exactly zero, and the two are not in tension: they are
    measuring different things and only one of them is completeness.
    """
    return (
        "**FIRST, THE METRIC WAS WRONG AND ITS FAILURE IS THE CLUE.** Blindness "
        "was scored per check -- *does it decide where a port it reads is wrong "
        "and pass* -- and 17 checks each measured LESS blind than the body it "
        "came from were added to the set. Blind checks went **121 to 136** and "
        "the objection rate on exposed decisions went **0.8% to 0.7%.** A set "
        "cannot get worse by gaining a check: rejection is a union, so a metric "
        "that falls when you add one is measuring the denominator, not the "
        "set.\n\n"
        "**THE SET-LEVEL QUESTION IS DISCRIMINATION.** For every pair of "
        "designs and every testpoint where they disagree on a real output, does "
        "SOME check object to at least one of them? That composes correctly -- "
        "adding a check can only close holes -- and it is golden-free, since "
        "the disagreement is the whole evidence.\n\n"
        "    (pair, testpoint) cells where two designs DISAGREE     5,656\n"
        "    the 163-check set objects to at least one              2,435\n"
        "    **SET BLINDNESS**                                      **3,221 = 56.9%**\n"
        "    the same, after adding the 17                          **3,221 = 56.9%**\n\n"
        "**IDENTICAL, AND VERIFIED RATHER THAN ACCEPTED**, because byte-identical "
        "numbers across an edit are this plan's own signature for a harness "
        "defect. Asked directly: the added checks object at 163 (design, "
        "testpoint) cells, the base set objects at 486, and the cells the added "
        "checks reach that the base set does not is **ZERO**. A strict "
        "subset.\n\n"
        "**SO THE ROUND'S CONTRIBUTION TO COMPLETENESS IS NOT SMALL, IT IS "
        "NIL** -- 39 model calls, 6 checks that are genuinely sound and "
        "genuinely less blind, and the set discriminates exactly as it did "
        "before.\n\n"
        "**THE MECHANISM, AND IT EXPLAINS THE WHOLE PLATEAU.** The witness "
        "pointed each author at a place its own check was silent. The authors "
        "complied -- the rewrites do object more. But every cell they object at "
        "was already covered by a DIFFERENT check in the set. Strengthening a "
        "check moves it toward what the set already says; it does not extend "
        "the set into where the set is silent.\n\n"
        "**BLINDNESS IS CORRELATED ACROSS CHECKS, and that is the check-level "
        "form of this module's oldest finding.** Independently written designs "
        "agree wrongly where the specification is ambiguous; independently "
        "written CHECKS are silent in the same places, for the same reason -- "
        "they are all readings of the same text by the same kind of reader. The "
        "56.9% the set cannot see is not 163 separate blind spots that could be "
        "closed one at a time. It is one blind spot with 163 checks in front of "
        "it.\n\n"
        "**WHAT FOLLOWS FOR AUTHORING.** Per-check improvement is the wrong "
        "target and every round here has optimised it: repair, strength, "
        "narrowing, volume, two-sided, and now blindness. A round should be "
        "scored on cells the SET newly reaches, which is a number that has "
        "never been reported for any of them -- and for this one it is zero."
    )


def no_body_in_this_corpus_closes_a_set_hole_soundly() -> str:
    """Selection measured against the SET metric, over the whole corpus, with
    no model calls -- and it closes the completeness route as the ceiling run
    closed the soundness one.

    The holes are closable. Closing one soundly is what nothing here can do.
    """
    return (
        "**THE SET IS BLIND ON 3,221 OF 5,656 DISAGREEING (pair, testpoint) "
        "CELLS = 56.9%, AND THE HOLES ARE UNIFORM.** 196 of 348 testpoints "
        "carry one, the twenty worst hold 14% of them, and every declared "
        "output runs between 43% and 76% uncaught -- `first_hit_ack` best at "
        "43%, `biu_write` worst at 76%. There is no cluster to aim a round "
        "at.\n\n"
        "**AND THAT RULES OUT THE STIMULUS BEFORE A CALL IS SPENT.** Every one "
        "of these cells is a testpoint the suite already runs, on which two "
        "designs already produce different values. The evidence is present and "
        "the set is silent on it, so no stimulus round closes any of them -- "
        "which is the goal's stimulus clause answered with a measurement "
        "rather than an estimate.\n\n"
        "**SO: CAN ANY BODY IN THE CORPUS CLOSE ONE?** 431 bodies the set does "
        "not use, decided over nine designs:\n\n"
        "    reach a cell the set cannot see              **296** -- the holes ARE closable\n"
        "      CONVICT the reference                       288\n"
        "      never DECIDE on it -- sound by silence        2\n"
        "      soundness unmeasured                          6\n"
        "      **DECIDE on the reference AND spare it**    **0**\n\n"
        "**NOT ONE BODY IN THIS CORPUS CLOSES A SET HOLE WHILE BEING "
        "DEMONSTRABLY SOUND.** Selection is exhausted for COMPLETENESS exactly "
        "as the ceiling run exhausted it for soundness, and the trade at set "
        "level is not 288 against 2 -- it is total.\n\n"
        "**A CORRECTION MADE INSIDE THIS MEASUREMENT, AND IT IS THE ONE THIS "
        "MODULE NAMES IN CAPITALS.** The first filter kept bodies whose audit "
        "says *convicts the reference: false*, which two bodies satisfied, and "
        "a 165-check set was built on them. Both have *decides: false* -- they "
        "never decide on the reference at all, so they are sound BY SILENCE, "
        "which is not sound. The set was withdrawn. `SOUND` requires the check "
        "to decide there AND never convict, and the first half is load-bearing "
        "precisely so that a silent check cannot buy a completeness result.\n\n"
        "**WHAT REMAINS OPEN, STATED NARROWLY.** This closes SELECTION over the "
        "corpus against the set metric. It does not close AUTHORING -- but the "
        "blindness round is the evidence on that, and its contribution to the "
        "same metric was zero. Two routes, two zeroes, on the measure that "
        "composes."
    )


def convicting_none_of_the_population_is_the_soundness_rule() -> str:
    """The best golden-free selection rule measured on this plan, and a
    retraction of the one it replaces.

    Applied to the FULL corpus rather than the fifth of it that had been
    scored, the minority rule loses its perfect precision -- and the threshold
    that keeps it is not the one the plan has been quoting.
    """
    return (
        "**THE RULE THAT WAS BEING QUOTED: *convicts at most 2 of the "
        "population* -- measured at 59 of 59 sparing the reference, 100% "
        "precision, and called the best golden-free soundness instrument "
        "here.** Re-run over all 594 bodies instead of the 114 that had been "
        "scored, it keeps 167 checks and **22 of them convict the reference: a "
        "13% false-reject rate.** The perfect precision does not survive the "
        "corpus growing; 13 of the 22 come from bodies never previously "
        "scored.\n\n"
        "**AND THE PROFILE SHOWS THE THRESHOLD WAS IN THE WRONG PLACE:**\n\n"
        "    convicts 0 of 7    126 checks   **0 convict the reference =  0%**\n"
        "    convicts 1 of 7     23 checks    11 convict the reference = 48%\n"
        "    convicts 2 of 7     18 checks    11 convict the reference = 61%\n\n"
        "**A CHECK CONVICTING NONE OF SEVEN INDEPENDENTLY WRITTEN "
        "IMPLEMENTATIONS SPARES THE REFERENCE, 126 FOR 126. ONE CONVICTION AND "
        "IT IS A COIN FLIP.** The step is at zero, not at two, and it is sharp "
        "rather than monotone -- which is why a threshold fitted at 2 on a "
        "smaller corpus read as perfect and is not.\n\n"
        "**THE SET IT SELECTS IS THE STRONGEST GOLDEN-FREE ARTIFACT HERE.**\n\n"
        "    checks                                   126\n"
        "    span                                     49 of 87 = 56%\n"
        "    objections on HELD-OUT design L           **11**\n"
        "    objections on two edited designs           1 each\n"
        "    *audit, computed last*                    ***0, measured***\n\n"
        "Sound AND discriminating on a design held out of its own selection, "
        "with the soundness PREDICTED golden-free rather than checked "
        "afterwards. Every earlier rule bought span with false rejects (rule B: "
        "52% at 10%) or bought soundness by being handed the answer (the "
        "ceilings are reference-selected).\n\n"
        "**WHAT IT STILL CANNOT DO, AND IT IS STRUCTURAL.** Selecting *convicts "
        "none of the population* guarantees every population member passes. The "
        "set accepts all seven by construction, so it cannot force equivalence "
        "among them, and 'all accepted designs are mutually equivalent' is "
        "self-certification rather than a result. The rule predicts SOUNDNESS "
        "without a reference; nothing here predicts SUFFICIENCY without one.\n\n"
        "**AND IT RE-DATES A RUN IN FLIGHT.** An editor was dispatched against "
        "the 167-check version before its audit was computed -- correctly, "
        "since the audit must come last. That audit is 13%, so the reference "
        "itself scores 22 against that set and a design reaching zero on it "
        "cannot be the reference. Terminating there would be a certificate of "
        "NON-equivalence, which is the rule-B arithmetic exactly. The 126-check "
        "set is the one to carry forward."
    )


def the_golden_free_soundness_rule_costs_essentially_all_discrimination() -> str:
    """The trade, measured at SET level on a metric that composes, with both
    ends built and scored the same way.

    This module has measured the soundness/discrimination anti-correlation nine
    ways per check. This is the first time both ends exist as SETS and are
    scored on the same golden-free completeness number.
    """
    return (
        "Two sets, each audited at zero false rejects, differing only in what "
        "SELECTED them:\n\n"
        "    set     selected by            span   *audit*   **set blindness**\n"
        "    CEIL2   the REFERENCE           68%    *0%*      **56.9%**\n"
        "    ZERO    the POPULATION only     56%    *0%*      **99.8%**\n\n"
        "Set blindness is the golden-free completeness number: of 5,656 (pair, "
        "testpoint) cells where two spec-derived designs disagree, how many does "
        "no check in the set object to. **The golden-free set sees 12 of "
        "5,656.**\n\n"
        "**AND THE MECHANISM IS THE RULE ITSELF, NOT A WEAKNESS IN IT.** The "
        "rule that predicts soundness perfectly without a reference is *convicts "
        "NONE of the seven*, measured 126 for 126 sparing the reference. A check "
        "convicting none of the population is, by the definition of the rule, a "
        "check that does not discriminate on the population. **Selecting for "
        "predictable soundness IS selecting for blindness**; the two are the "
        "same predicate read twice.\n\n"
        "**SO THE ANSWER TO WHETHER COMPLETENESS CAN BE ASSURED GOLDEN-FREE IS "
        "MEASURED, AND IT IS NO ON THIS CORPUS.** The instrument that ranks "
        "blindness golden-free is excellent -- Spearman +0.908 -- and the rule "
        "that predicts soundness golden-free is perfect at n=126. Composing "
        "them yields a set that is sound, wide enough to span 56% of the "
        "specification, and blind to 99.8% of the disagreements it is shown.\n\n"
        "**WHAT SURVIVES, AND IT IS NARROW BUT REAL.** The ZERO set still "
        "objects **11 times to design L, held out of the seven that selected "
        "it** -- the both-cell, reached by a rule that read no reference. Sound "
        "and discriminating on unseen designs is a property this plan has "
        "measured at 3-5% per check and never before obtained from a "
        "golden-free rule at set level. It is a real capability and it is two "
        "orders of magnitude short of forcing equivalence.\n\n"
        "**PRE-REGISTERED, BEFORE THE EDITOR ON THIS SET REPORTS.** A set seeing "
        "12 of 5,656 disagreements should be easy to satisfy: the prediction is "
        "that the editor drives 11 objections to zero in few trials and the "
        "miter still says `DIFFERS`. If that happens it is NOT a new negative "
        "-- it is this number restated, and must be reported as the expected "
        "consequence rather than as a fresh finding."
    )


def an_editor_cannot_locate_over_strictness_even_when_it_is_there() -> str:
    """The fourth measurement of this, and the first against a labelled answer
    on a set that genuinely contains over-strict checks.

    The previous three runs are weaker evidence than they look: those sets were
    sound, so the editor's suspicion was false by construction and refuting it
    took no instrument. This run gave it a real target.
    """
    return (
        "An editor ran 6 trials on a 167-check set, took it from 30 objections "
        "to 10, and reported two of the survivors as check defects rather than "
        "design defects: `REQ-0015` and `REQ-0064`, on the argument that their "
        "vectors change an input mid-transaction and compare against the "
        "post-change value where a real bus latches at acceptance.\n\n"
        "**THAT SET REALLY DOES CONTAIN OVER-STRICT CHECKS -- 22 of the 167 "
        "convict the reference -- so unlike every previous instance the "
        "suspicion was not wrong in principle.** Scored against the labelled "
        "audit:\n\n"
        "    checks that convict the reference        22, over 9 requirements\n"
        "      REQ-0002 0021 0025 0027 0072 0079 0081 0083 0085\n"
        "    the editor named                          REQ-0015, REQ-0064\n"
        "    of those, over-strict                     **0**\n"
        "    of the 22, named by the editor            **0**\n\n"
        "**ZERO PRECISION AND ZERO RECALL, WITH A REAL TARGET PRESENT.** Both "
        "checks it accused spare the reference; not one of the nine "
        "requirements whose checks actually are over-strict appears in its "
        "report.\n\n"
        "**THIS IS WHAT MAKES THE EARLIER RUNS INTERPRETABLE.** Three editors "
        "on three SOUND sets each concluded the remaining checks contradicted "
        "each other, and each was refuted in one line because the reference "
        "satisfies every member. That refutation shows the conclusion was "
        "false; it does not show the editor could not have been right somewhere "
        "else. Here it could have been -- and it was not.\n\n"
        "**WHAT THIS RUN SHOWS IS THAT THIS EDITOR DID NOT LOCATE IT.** The "
        "suspicion is well founded roughly 13% of the time on this set and "
        "this identification is at chance or worse.\n\n"
        "**AND THE GENERALISATION I DREW FROM IT -- *editors cannot locate "
        "over-strictness* -- IS RETRACTED.** A later run on a 201-check set "
        "holding 38 over-strict members named seven and was right about all "
        "seven, partitioning its surviving objections exactly. See "
        "`an_editor_can_locate_over_strictness_when_it_tests_the_claim`. What "
        "stands here is the measurement, not the conclusion: pooled over five "
        "runs editors have named 12 checks and been right about 8, and the "
        "spread between 0-of-2 and 7-of-7 is what needs explaining rather than "
        "an average.\n\n"
        "**THE DIFFERENCE IS NOT THE EDITOR, IT IS WHETHER THE CLAIM WAS "
        "TESTED.** This one argued from the shape of the vectors. That one "
        "implemented the design each check demanded, committed it, and read "
        "what broke -- and reported the claim only when the experiment "
        "survived. From inside, a check an editor cannot satisfy and a check "
        "no design can satisfy present identically to REASONING; they do not "
        "present identically to an EDIT."
    )


def set_blindness_predicts_how_far_an_editor_gets() -> str:
    """A matched pair, and the first golden-free number here that PREDICTS
    editor progress rather than describing a set after the fact.

    The prediction was written down before the second run was dispatched, and
    the run landed on it.
    """
    return (
        "Two editors, **the same unchecked starting design**, the same model, "
        "the same brief and budget. The only difference is which set drove "
        "them, and the sets differ in the golden-free completeness number:\n\n"
        "    set                      blindness   objections      testpoints differing\n"
        "    CEIL2 163, ref-selected    56.9%     22 -> 5  (-77%)   279 -> 190  (**-32%**)\n"
        "    ZERO  126, golden-free     99.8%     11 -> 1  (-91%)   279 -> 271  (** -3%**)\n"
        "    both grades: *DIFFERS*, three pins green in the same process\n\n"
        "**THE GOLDEN-FREE SET SPENT 91% OF ITS OBJECTIONS AND MOVED THE DESIGN "
        "3%.** The reference-selected set spent less of its criterion and moved "
        "the design ten times further. Set blindness is not a description of a "
        "set after the fact -- it says in advance how much of a design's "
        "divergence a loop driven by that set will close.\n\n"
        "**AND IT WAS PRE-REGISTERED.** Before the second run was dispatched "
        "the prediction on record was that a set objecting to 12 of 5,656 "
        "disagreements would be cheap to satisfy, so objections going to nearly "
        "zero with the grade unmoved would be that number restated rather than "
        "a fresh negative. That is what happened, which is the difference "
        "between a metric and a post-hoc story.\n\n"
        "**THIS IS THE PROXY THE GOAL ASKS FOR.** A metric chosen by how well "
        "it facilitates the RTL editor succeeding, computable from spec-derived "
        "designs alone, and validated against editor progress on a matched "
        "pair. Every earlier proxy here was scored on how well it described "
        "CHECKS; this one is scored on what the loop achieves.\n\n"
        "**THE TRIAL COUNTS ARE AN OUTPUT, NOT A CONFOUND -- AND SAY SO.** The "
        "golden-free run used 10 of 21 trials and the other 19 of 21. Neither "
        "stopped for budget: each stopped when its criterion ran out of things "
        "to say. A blinder set stops giving feedback sooner, so unequal effort "
        "is part of what blindness causes rather than an artefact confounding "
        "it. Stated because equal effort would be the natural thing to demand "
        "of a matched pair.\n\n"
        "**SCOPE, AND IT IS TWO RUNS.** One design, one starting point, two "
        "sets. The relationship is monotone in the right direction with a large "
        "gap, and two points do not establish a slope. What they do establish "
        "is that the number is not inert: a set at 99.8% and a set at 56.9% "
        "produce visibly different loops from identical inputs."
    )


def blindness_and_soundness_are_one_golden_free_knob() -> str:
    """The completeness/false-reject trade, measured as a curve rather than
    argued from two points -- and the reference-selected set sits off it.

    Eight sets from one selection rule that never reads the reference. The
    audit is computed last and feeds nothing.
    """
    return (
        "One golden-free knob -- **keep a check that convicts at most t of the "
        "seven independently written spec-derived designs** -- swept end to "
        "end. t = 0, 2 and 7 reproduce three sets that were built separately "
        "and byte-for-byte, which is what says the sweep is the same "
        "instrument. The intermediate thresholds had never been scored.\n\n"
        "    t   checks   reqs of 87   SET BLINDNESS   *audit: convict the reference*\n"
        "    0     126      55 = 63%      99.8%          *  0 =  0.0%*\n"
        "    1     149      63 = 72%      93.5%          * 11 =  7.4%*\n"
        "    2     167      68 = 78%      66.5%          * 22 = 13.2%*\n"
        "    3     171      68 = 78%      64.2%          * 23 = 13.5%*\n"
        "    4     179      69 = 79%      61.9%          * 27 = 15.1%*\n"
        "    5     188      70 = 80%      52.7%          * 27 = 14.4%*\n"
        "    6     201      71 = 82%      40.4%          * 38 = 18.9%*\n"
        "    7     464      73 = 84%       0.0%          *299 = 64.4%*\n\n"
        "**BLINDNESS FALLS AND THE AUDIT RISES ACROSS THE WHOLE SWEEP.** "
        "Completeness and soundness are not two properties a better rule could "
        "optimise jointly -- golden-free, on this corpus, they are ONE KNOB "
        "read in two directions. Reaching the completeness floor costs a set "
        "that convicts a correct design with two checks in three.\n\n"
        "**AND THE CUMULATIVE TABLE OVERSTATES HOW ORDERLY THAT IS, WHICH IS A "
        "CORRECTION TO THE FIRST VERSION OF THIS FINDING.** The thresholds "
        "NEST, so the audit COUNT cannot fall as t grows -- its monotonicity is "
        "a property of the construction and carries no information. The audit "
        "RATE is not monotone either: it dips at t = 5. The informative "
        "decomposition is per bucket rather than cumulative:\n\n"
        "    the check convicts   checks   convict the reference\n"
        "    0 of 7                 126      0 =   0.0%\n"
        "    1 to 6 of 7             75     38 =  50.7%\n"
        "    7 of 7                 263    261 =  99.2%\n\n"
        "**THE RULE IS EXACT AT BOTH ENDS AND A COIN FLIP IN BETWEEN.** "
        "Convicting none of the population spares the reference 126 times out "
        "of 126; convicting all of it convicts the reference 261 times out of "
        "263. In the middle band it has NO SIGNAL AT ALL, at 50.7%.\n\n"
        "**AND THE MIDDLE BAND IS EXACTLY WHERE THE BLINDNESS REDUCTION "
        "LIVES.** Those 75 checks are everything between the sound-and-blind "
        "set and t = 6, and they carry blindness from 99.8% to 40.4%. So the "
        "trade is not a smooth price to pay: it is a region where the "
        "golden-free rule stops discriminating altogether, and every point "
        "inside it is bought blind.\n\n"
        "**AND THE REFERENCE-SELECTED SET IS OFF THE CURVE, WHICH IS THE PART "
        "THAT MATTERS.** CEIL2 is 163 checks at **56.9% blind with an audit of "
        "zero**. No golden-free threshold reaches that point: getting to 52.7% "
        "golden-free costs 14.4% false rejection. The reference is doing work "
        "here that no rule over the population reproduces.\n\n"
        "**THE MECHANISM IS ARITHMETIC RATHER THAN A TENDENCY, AND IT CLOSES "
        "EXACTLY.** 161 of CEIL2's 163 checks are inside t = 6, and t = 6 "
        "holds exactly 38 audit failures. CEIL2's other two are the only two "
        "checks in the whole corpus that convict all seven and still spare "
        "the reference, so CEIL2 is t = 6 with its 38 audit failures removed "
        "and those two added, with nothing left over. Removing the 38 takes "
        "blindness from 40.4% back to 56.9%. **Those 38 checks close 933 "
        "disagreement cells, 16.5 points of blindness, and nothing sound "
        "replaces them**, which is the no-sound-hole-closer finding restated "
        "where it costs something.\n\n"
        "**WHAT IT ANSWERS.** The question was how to assure a set's "
        "completeness without a reference. The answer on this corpus is that "
        "you cannot: every golden-free step toward completeness is a step into "
        "false rejection, and the obstruction is a measured monotone trade "
        "rather than a missing instrument.\n\n"
        "**SCOPE.** One design, one corpus of 594 bodies, one population of "
        "seven. The rule is one knob -- a different golden-free rule could in "
        "principle find a different frontier, and eleven have been tried "
        "without one doing so. What is established is the shape of THIS "
        "rule's frontier and that the reference-selected point is not on it."
    )


def a_complete_set_is_an_undrivable_one() -> str:
    """The second opposition, and it is independent of soundness: the set that
    sees every disagreement cannot tell the designs apart by its own count.

    Measured on the population before the editor run was dispatched, and
    recorded as an amendment to that run's pre-registration.
    """
    return (
        "Set blindness says whether SOME check objects somewhere in a "
        "disagreeing cell. It says nothing about whether the objection COUNT "
        "orders designs -- and on the set that reaches the completeness floor "
        "it does not:\n\n"
        "    set                       blindness   population objections   spread / mean\n"
        "    ZERO 126, golden-free       99.8%            0 -  0                --\n"
        "    CEIL2 163, ref-selected     56.9%           11 - 22              69%\n"
        "    T6   201, golden-free       40.4%           22 - 38              50%\n"
        "    MIN  464, the floor          0.0%          285 - 301           **5.4%**\n\n"
        "**EIGHT DESIGNS THAT DIFFER FROM EACH OTHER ACROSS A LARGE FRACTION "
        "OF THE SUITE ARE SEPARATED BY SIXTEEN CHECKS OF FOUR HUNDRED AND "
        "SIXTY-FOUR.** The cause is structural rather than incidental: the "
        "0.0% blindness is bought by admitting 288 bodies that convict a "
        "correct design, and a check that convicts a correct design convicts "
        "nearly every design, so it contributes a constant to every score.\n\n"
        "**SO COMPLETENESS AND DRIVABILITY ARE OPPOSED, INDEPENDENTLY OF "
        "SOUNDNESS.** A loop descending the count of a complete set is "
        "descending a signal with a 5% dynamic range. That is a second reason "
        "the completeness floor is not somewhere to drive from, and it is not "
        "the same reason as the audit.\n\n"
        "**IT WAS RECORDED BEFORE THE RUN THAT WOULD HAVE BEEN READ AS "
        "SOUNDNESS.** The pre-registration for the floor-set editor run named "
        "two hypotheses, blindness and soundness. This measurement supplies a "
        "third explanation for a poor result there, so the negative band was "
        "amended in advance to say the run cannot separate them -- rather than "
        "attributing the outcome to soundness after seeing it.\n\n"
        "**WHAT IT DOES NOT SAY.** Spread is not the only way a set can steer: "
        "a weighting, a per-requirement fold or a subset view could recover a "
        "gradient the raw count does not have. What is measured is that the "
        "RAW COUNT -- which is what every loop on this plan has descended -- "
        "carries almost no information on a complete set."
    )


def an_unspent_budget_is_not_evidence_about_the_set() -> str:
    """Two editor runs stopped after one trial for a reason that has nothing to
    do with the checks, and from outside it looked exactly like a loop that had
    run out of things to fix.

    Observed twice in one session, on two different sets.
    """
    return (
        "A commit runs the whole suite and takes several minutes -- longer "
        "than a foreground command may run in the agent driving the loop. Both "
        "editors handled that by backgrounding the commit and **ending their "
        "turn to wait for it**. The completion notice is delivered to whatever "
        "dispatched the agent, not to the agent, so ending the turn ends the "
        "RUN. One stopped at trial 2 of 21 and one at trial 0 of 21.\n\n"
        "**AND THE RUN DIRECTORY LOOKS IDENTICAL TO A LOOP THAT FINISHED "
        "EARLY BECAUSE IT WAS SATISFIED.** Trials unspent, a latched design, a "
        "sensible objection count. Nothing in the artifacts distinguishes *the "
        "criterion stopped saying useful things* from *the harness stopped the "
        "agent*, and the first has been read off an unspent budget on this "
        "plan more than once.\n\n"
        "**SO AN UNSPENT BUDGET IS NOT A FACT ABOUT THE CHECK SET UNLESS THE "
        "RUN RECORDS WHY IT STOPPED.** Here the agents' own words were the "
        "only tell -- *\"I'll stop issuing commands now and wait for the "
        "background notification\"* -- which is a transcript artefact and not "
        "something the loop's own record captures.\n\n"
        "**THE FIX IS IN THE BRIEF, NOT THE HARNESS -- AND THE FIRST FIX I "
        "WROTE DOWN WAS THE WRONG ONE.** I prescribed backgrounding the "
        "commit and polling the loop's status inside the turn. Both agents "
        "were given that and **both stopped again the same way**, because a "
        "poll loop still leaves work outstanding across a turn boundary and "
        "an agent asked to wait will end the turn to do it.\n\n"
        "**THE FIX THAT WORKS REMOVES THE WAIT INSTEAD OF MANAGING IT:** run "
        "the commit as an ORDINARY FOREGROUND COMMAND with an explicit long "
        "timeout on the call. A commit here is four to six minutes against a "
        "ten-minute maximum, so it was never necessary to background it at "
        "all -- the timeout DEFAULT, not the runtime, is what made it look "
        "impossible. The call blocks and returns the result, and nothing is "
        "left in flight for a turn boundary to drop.\n\n"
        "**THE GENERAL FORM, WHICH IS THE PART WORTH KEEPING.** A loop whose "
        "unit of work outlasts the DEFAULT command timeout will be broken by "
        "any recipe that answers *how do I wait*, and fixed only by one that "
        "answers *how do I not have to*. Measure the unit against the "
        "maximum before reaching for concurrency.\n\n"
        "**WHAT THIS DOES NOT RETRACT.** The two earlier runs that stopped "
        "with budget left each stated a reason at the time -- one reached zero "
        "objections, the other argued the remaining objections were check "
        "defects -- so neither is an instance of this. What is retracted is "
        "the general inference: *trials left over* is evidence about the set "
        "only when the run says, in its own record, what it stopped for."
    )


def an_editor_can_locate_over_strictness_when_it_tests_the_claim() -> str:
    """The retraction of `an_editor_cannot_locate_over_strictness_even_when_it_
    is_there`, on a run with a larger labelled target and one procedural change.

    Scored against the survivors it could actually have accused, not against
    the whole set -- the base rate that flatters the result is the wrong one.
    """
    return (
        "A 201-check set holding **38 members that convict the reference**. An "
        "editor took a held-out design from 39 objections to 11 over 13 trials "
        "and reported seven survivors as demanding more than their own "
        "sentences license, each with the sentence quoted.\n\n"
        "    of the 11 objections still standing on the graded design\n"
        "      UNSOUND -- convict the reference        7\n"
        "      SOUND   -- the reference satisfies them 4\n"
        "    the editor accused                        7\n"
        "    correct                                   **7**\n"
        "    false accusations                         **0**\n\n"
        "**IT PARTITIONED THE SURVIVORS EXACTLY.** Every unsound one named, "
        "every sound one left alone.\n\n"
        "**AND THE BASE RATE THAT MATTERS IS 64%, NOT 19%.** Over the whole set "
        "the over-strict share is 19%, and quoting that would make 7-of-7 look "
        "far more impressive than it is: the editor could only accuse checks it "
        "SAW OBJECTING, and a check that convicts a correct design convicts "
        "most designs, so the survivors are enriched. Against the survivor rate "
        "seven random accusations score 4.5. Against the exact partition, "
        "choosing 7 of 11 at random lands all seven **1 time in 330 -- "
        "p = 0.003**.\n\n"
        "**THE FOUR IT DID NOT ACCUSE, IT GOT RIGHT IN A SECOND WAY.** It "
        "reported those as conflicts it could not resolve rather than as "
        "over-reach. The reference satisfies all four, so no such conflict "
        "exists and its diagnosis is wrong -- but the claim it made is about "
        "ITS OWN SEARCH, not about the checks, and it declined to convict them. "
        "That is the distinction three earlier editors collapsed.\n\n"
        "**THE VARIABLE IS THE PROCEDURE, NOT THE MODEL.** The run this "
        "retracts argued from the shape of the vectors. This one implemented "
        "the design each suspect check demanded, committed it, read what broke, "
        "and reported the claim only when the experiment survived -- three "
        "structurally distinct attempts on one of them. Its brief asked for "
        "exactly that: do not dismiss a check, and if you still believe it "
        "after real effort, write it down with the sentence quoted.\n\n"
        "**SO AN EDITOR IS AN INSTRUMENT FOR SOUNDNESS AND THE GATES ARE NOT, "
        "FOR A REASON THAT IS NOT ABOUT INTELLIGENCE.** It is the only party in "
        "this pipeline that can BUILD the design a check demands and observe "
        "the consequence. A gate reads text or replays a fixed design; it "
        "cannot run the experiment. Twelve routes have failed to separate "
        "sound from over-strict without a reference, and every one of them was "
        "a way of READING checks.\n\n"
        "**SCOPE, AND IT IS ONE RUN.** n = 11 survivors, one design, one set, "
        "one editor. The partition is exact and p = 0.003, and a second run is "
        "what would turn a procedure into a method. What it already settles is "
        "the negative it replaces: locating over-strictness from inside the "
        "loop is not impossible, and the earlier zero was a property of a run "
        "rather than of editors."
    )


def a_golden_free_set_did_not_out_drive_the_reference_selected_one() -> str:
    """The pre-registered test of blindness against soundness, at matched
    drivability. It landed in the middle band.
    """
    return (
        "Two sets, the same unchecked starting design, the same model, brief "
        "and 21-trial budget. The variable is 16.5 points of set blindness, "
        "and the cost of buying them golden-free is 38 checks that convict a "
        "correct design:\n\n"
        "    set                     blindness  *audit*  objections   testpoints differing\n"
        "    CEIL2 163, ref-selected   56.9%    *  0*    22 -> 5      279 -> 190  (**-32%**)\n"
        "    T6    201, golden-free    40.4%    * 38*    39 -> 11     279 -> 200  (**-28%**)\n"
        "    both grades: *DIFFERS*, three pins green in the same process\n\n"
        "**THE LESS BLIND SET DROVE THE DESIGN VERY SLIGHTLY LESS FAR.** The "
        "pre-registered bands were: better than -32% means blindness dominates; "
        "-32% to -20% means comparable; worse than -20% or rising means "
        "soundness dominates. **-28% is the middle band**, and the reading "
        "fixed in advance was that the extra completeness bought nothing the "
        "unsound checks did not take back.\n\n"
        "**SO THE MATCHED PAIR'S SLOPE DOES NOT EXTEND.** Blindness separated "
        "99.8% from 56.9% by a factor of ten in divergence closed. From 56.9% "
        "to 40.4% it separates nothing -- and this is the first point on that "
        "curve where the two sets differ in soundness as well, which is exactly "
        "what a golden-free rule must accept to get there.\n\n"
        "**WHAT IT DOES NOT SAY.** It does not refute set blindness as a "
        "proxy: the ZERO/CEIL2 gap stands, and a single point cannot "
        "distinguish *blindness saturates near 50%* from *the audit cost "
        "exactly cancelled the gain*. Separating those needs a set that is "
        "40% blind AND sound, which this corpus does not contain -- that is "
        "the same wall, met from a third direction.\n\n"
        "**AND THE RUN IS NOT A NULL RESULT.** 39 objections to 11, 200 of 348 "
        "testpoints still differing, and the editor spent 13 of its 21 trials. "
        "The goal's terminal condition is not met: no set measured here drives "
        "a spec-derived design to equivalence, and the four graded runs land at "
        "271, 200, 190 and -- for the completeness floor -- pending."
    )


def completeness_bought_with_unsoundness_drives_a_design_worse() -> str:
    """Four graded editor runs, one starting design, four sets spanning the
    whole blindness range. The completeness floor is beaten by a set 57 points
    blinder, and that settles what a golden-free completeness push is worth.

    Every band was pre-registered before its run was dispatched.
    """
    return (
        "Four Sonnet editors, **the same arbitrary unchecked design**, the same "
        "brief and 21-trial budget, four sets. Blindness is golden-free; the "
        "audit is computed last and fed nothing:\n\n"
        "    set                     blindness  *audit*   objections     testpoints differing\n"
        "    ZERO  126, sound          99.8%    *  0 = 0%*  11 ->   1     279 -> 271  ( -3%)\n"
        "    CEIL2 163, sound          56.9%    *  0 = 0%*  22 ->   5     279 -> **190**  (**-32%**)\n"
        "    T6    201, golden-free    40.4%    * 38 = 19%* 39 ->  11     279 -> 200  (-28%)\n"
        "    MIN   464, the floor       0.0%    *299 = 64%* 295 -> 277    279 -> 241  (-14%)\n"
        "    all four grades: *DIFFERS*, three pins green in the same process\n\n"
        "**RANKED BY WHAT THE EDITOR ACHIEVED: CEIL2, T6, MIN, ZERO. BLINDNESS "
        "DOES NOT ORDER THEM.** The set that sees every disagreement in the "
        "population came third, beaten by one 57 points blinder.\n\n"
        "**SPLIT BY SOUNDNESS AND IT RESOLVES CLEANLY.** Among the two sets "
        "that convict no correct design, blindness predicts exactly as the "
        "matched pair said: 99.8% closes 3%, 56.9% closes 32%. Among the two "
        "bought with false rejection it inverts: 40.4% closes 28% and 0.0% "
        "closes 14%. **Blindness helps while soundness is held and stops "
        "helping the moment it is spent.**\n\n"
        "**SO THE GOAL'S COMPLETENESS PUSH IS ANSWERED, AND THE ANSWER IS "
        "NO.** Reducing blindness residue makes a set a better driver only "
        "along the sound frontier, and golden-free there is only one point on "
        "that frontier this corpus reaches -- 99.8%. Every step toward "
        "completeness without a reference admits checks that convict correct "
        "designs, and those cost more than the completeness gains.\n\n"
        "**THE COST IS VISIBLE AS LOST WORK, NOT ONLY AS A RATE.** On the "
        "floor set the editor found a real defect -- a refill servicing three "
        "words where the requirement states four, worth about 970 consensus "
        "cells in one change -- and the commit was refused every time it was "
        "tried, by two checks that are in the audit's unsound list. A set at "
        "64% false rejection does not merely accept wrong designs; it rejects "
        "right repairs.\n\n"
        "**AND THE FLOOR SET'S NUMBER CANNOT BE ATTRIBUTED TO SOUNDNESS "
        "ALONE**, which was recorded before it ran. Its objection count spans "
        "5.4% over the whole population, so its gradient is nearly flat "
        "independently of its audit -- and the run showed that live, moving "
        "the count 6% while divergence moved 14%. Its band was pre-registered "
        "as uninterpretable between the two causes and it is reported that "
        "way.\n\n"
        "**WHAT IS NOT CLAIMED.** No run reached equivalence, so this orders "
        "four failures rather than finding a winner. Four points, one design, "
        "one corpus; the two sound points are the matched pair already on "
        "record and the two unsound ones are new."
    )


def a_second_accusation_run_carried_no_information() -> str:
    """The editor named five over-strict checks and was right about all five,
    and it is worth almost nothing. Recorded so the pair is not quoted as two
    confirmations.
    """
    return (
        "On the 201-check set an editor partitioned its 11 surviving "
        "objections exactly -- seven unsound named, four sound spared, "
        "p = 0.003. The obvious next question is whether that reproduces, and "
        "a second run named five checks on the 464-check floor set and was "
        "right about all five.\n\n"
        "**IT IS NOT A SECOND CONFIRMATION AND MUST NOT BE QUOTED AS ONE.**\n\n"
        "    set   survivors   of those UNSOUND   named   right   p by chance\n"
        "    T6         11        7 = **64%**       7       7      **0.003**\n"
        "    MIN       277      259 = **94%**       5       5        0.71\n\n"
        "**ON A SET WHERE 94% OF THE SURVIVING OBJECTIONS ARE OVER-STRICT, "
        "BEING RIGHT FIVE TIMES IS THE EXPECTED OUTCOME** -- 4.7 of 5 at "
        "chance. The first run was informative for the opposite reason: its "
        "set is 81% sound, so a wrong accusation was the likely result and the "
        "exact partition was not.\n\n"
        "**THE GENERAL RULE, WHICH IS THE PART TO KEEP.** An accusation's "
        "denominator is the population the accuser could have drawn from -- "
        "here the checks it saw objecting, not the whole set. Quoting the "
        "whole-set rate would have read 19% for the first run and 64% for the "
        "second, flattering both and inverting which one carries evidence.\n\n"
        "**SO THE REPLICATION IS STILL OWED.** It needs a mostly-sound set "
        "where a wrong accusation is the default outcome, which is what the "
        "first run had and the second did not."
    )


def the_leak_rule_named_source_and_the_traces_were_next_door() -> str:
    """An integrity hazard in all four graded runs, found while building a
    fifth experiment where it would have been an answer key.

    Checked rather than assumed: both editor transcripts were searched.
    """
    return (
        "Every editor run here carries an absolute rule -- do not go looking "
        "for a reference implementation, nothing under the benchmark tree, no "
        "Verilog file the tools did not hand you, no other loop directory. "
        "**It names SOURCE, and the reference's recorded TRACES sat in a "
        "directory the loop legitimately reads.**\n\n"
        "The driver takes its stimulus from `SUITESRC`, which pointed at "
        "`p4G/suite` -- and `p4G/suite/results` holds the reference's 348 "
        "recorded traces. An editor had a reason to be in that directory and "
        "no rule against going one level deeper, where the answer to every "
        "question it was asked is written out per testpoint.\n\n"
        "**IT WAS NOT WALKED THROUGH, AND THAT IS CHECKED RATHER THAN "
        "ARGUED.** Both editor transcripts were searched: **zero accesses to "
        "`p4G/suite/results`**. What they did read under `p4G` is the stimulus "
        "(`suite/tests`, `manifest.json`) and the witness -- both spec-derived "
        "pipeline artifacts the loop replays against anyway, neither the "
        "reference. Every `benchmarks/` occurrence is the rule text itself or "
        "a path constant inside the driver they read.\n\n"
        "**AND THE GRADES CORROBORATE IT.** Four runs ended at 271, 241, 200 "
        "and 190 of 348 testpoints differing. A run that had read the "
        "reference's traces could have matched them far more closely; nothing "
        "in the outcomes looks like it.\n\n"
        "**THE FIX IS A SANITISED STIMULUS SOURCE, AND IT COSTS NOTHING.** "
        "The driver copies only `suite/tests` and `manifest.json` out of "
        "`SUITESRC`, so a directory holding exactly those two runs the loop "
        "identically with the traces nowhere in reach. The rule is also "
        "extended to say recorded behaviour is as forbidden as source.\n\n"
        "**THE GENERAL FORM.** A leak rule that names artifacts by KIND -- *an "
        "implementation* -- misses them by ROLE. A trace file is the same "
        "information in another format, and it is the format a checking "
        "pipeline necessarily keeps lying around. State the rule over what an "
        "artifact ENCODES, then check the transcripts rather than trusting "
        "the wording."
    )


def the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty() -> str:
    """A pre-registered experiment that cleared its top band, and a control run
    afterwards that says the band was set against the wrong null.

    The result is reported as not claimable. The defect is mine and it is the
    same shape as a dozen others here: a denominator that looks right.
    """
    return (
        "The question was whether an agent with an editor's tools can decide "
        "soundness -- the thing twelve routes have failed to do without a "
        "reference. Twenty checks from a 201-check set, **ten that convict the "
        "reference and ten that do not**, drawn by hash and shuffled, with the "
        "key sealed. Pre-registered: >= 16 correct means the capability is "
        "real, <= 13 means chance.\n\n"
        "    CORRECT 16 of 20, no UNSURE          binomial p = 0.0059\n"
        "      OVER-STRICT calls   8, right 7      precision 88%\n"
        "      unsound found       7 of 10         recall 70%\n\n"
        "**IT CLEARED THE TOP BAND, AND THE BAND IS NOT CLAIMABLE.**\n\n"
        "**THE CONTROL: SEVEN OF THE TEN SOUND ITEMS NEVER CONVICT ANY DESIGN "
        "AT ALL.** A check with no reachable `False` is sound trivially, and "
        "spotting it needs only the source -- the agent said so itself for "
        "four of them, one of which it noticed cannot convict because it "
        "throws and the harness reports `ok=None`. So half the sample was "
        "free, and the 50% coin the p-value is computed against does not "
        "exist.\n\n"
        "**ON THE THIRTEEN ITEMS WHERE THE ANSWER IS NOT VISIBLE IN THE TEXT "
        "-- ten unsound and three sound-and-deciding -- IT SCORED 10.** "
        "Answering `OVER-STRICT` to all thirteen also scores 10. **No "
        "measurable lift on the part of the task that was the task.**\n\n"
        "**THE DEFECT IS IN MY SAMPLER AND IT IS THE FAMILIAR SHAPE.** It "
        "required each item to DECIDE on the reference, which correctly "
        "excludes a check that never fires -- and admits one that fires and "
        "only ever returns True. Balanced by label, unbalanced by difficulty, "
        "and the imbalance runs entirely one way. **The fix is one clause: "
        "every sampled check must convict at least one of the nine "
        "spec-derived designs**, so no item is answerable from whether a "
        "`False` path exists.\n\n"
        "**WHAT SURVIVES IS THE SAME NARROW THING THE EARLIER RUN SHOWED.** "
        "Precision on the OVER-STRICT calls is 7 of 8, and the one false "
        "accusation is a check that convicts none of the nine. That is a "
        "DETECTOR with good precision and 70% recall, which the "
        "pre-registration already named as the smaller claim to report if the "
        "pattern repeated. It repeated.\n\n"
        "**AND THE INSTRUMENT WAS NOT THE ONE UNDER TEST.** The agent spent "
        "**zero** of its 25 commit trials. It executed each check against "
        "hand-built traces instead of building RTL and observing what broke -- "
        "cheaper and more general, and not what the earlier run did, so this "
        "does not replicate that run's method either. Tested items scored 85% "
        "against untested 71%, on 13 and 7 items with the trivial ones split "
        "across both, which settles nothing.\n\n"
        "**SO THE REPLICATION IS STILL OWED, FOR THE THIRD TIME.** Three "
        "attempts: one informative (exact partition, p = 0.003), one at a 94% "
        "base rate, one against a null a sampler defect invalidated."
    )


def authoring_at_a_named_hole_closes_cells_that_selection_cannot() -> str:
    """The first positive of the session on the goal's central axis, and it
    refutes a generalisation I drew from the corpus three findings earlier.

    Pre-registered as a PAIR -- blindness down AND audit zero -- because
    blindness bought with false rejection is measured to drive designs worse.
    """
    return (
        "Every set measured here was a SELECTION over 594 bodies authored in "
        "earlier sessions, and over that corpus the answer is flat: of 431 "
        "unused bodies, 296 close a set hole and **every one convicts the "
        "reference**; 0 decide-and-spare. I let that harden into a claim about "
        "the problem. It is a claim about the corpus.\n\n"
        "**37 checks authored AT A NAMED HOLE** -- a (pair, testpoint, port) "
        "cell where two spec-derived designs disagree on a declared output and "
        "no check in the sound 163-check set objects to either. The author gets "
        "the port, the testpoint, both designs' rows and its requirement's "
        "sentence. Golden-free by construction: the disagreement between two "
        "spec-written designs is the whole evidence, and at most one can be "
        "right.\n\n"
        "    integrity   37 of 37 returned, 37 compile, 0 duplicate bodies,\n"
        "                0 identical to any existing corpus body\n"
        "    vacuous     6      object on no cell at all\n"
        "    over-strict 25     convict 5 to 7 of the 7-design population\n"
        "    ACCEPTED     6     decide, and convict at most 3 of 7\n\n"
        "**THE PAIR, AND BOTH HALVES LANDED:**\n\n"
        "    set                          checks   SET BLINDNESS   *audit*\n"
        "    CEIL2, the sound base          163       56.9%        *0*\n"
        "    CEIL2 + the six authored       169       **55.1%**    ***0***\n"
        "    cells closed                                102\n\n"
        "**102 CELLS CLOSED AT AN AUDIT OF ZERO.** Small -- 1.8 points of "
        "3,221 holes -- and it is the thing selection cannot do at any price. "
        "The one previous authoring round closed **exactly zero** new cells: "
        "its 17 accepted checks were a strict subset of what the base already "
        "caught. Naming the cell is the difference.\n\n"
        "**SO `no_body_in_this_corpus_closes_a_set_hole_soundly` STANDS AND THE "
        "GENERALISATION I BUILT ON IT DOES NOT.** The corpus contains no sound "
        "hole-closer; a sound hole-closer is nonetheless writable. Every "
        "blindness-versus-audit figure here is a curve over SELECTIONS, and "
        "authoring moves off that curve.\n\n"
        "**THE RATE, WITH THE DENOMINATOR CORRECTED FOR MY OWN DEFECT.** 6 of "
        "37 = 16%, which is the 15% the previous round got and the 3% every "
        "earlier round got -- naming the cell did not change how often an "
        "author lands. At least 8 targets were mis-assigned, because "
        "`mkhole.py` paired a requirement to a hole when its TEXT MENTIONED "
        "THE PORT rather than when its sentence GOVERNED THE CELL; against ~29 "
        "answerable targets it is 21%. Both numbers, never one.\n\n"
        "**WHAT IT DOES NOT ESTABLISH.** 102 of 3,221 is 3% of the residue, "
        "and these are the cells a first pass reaches -- there is no reason to "
        "think the rate holds as the easy ones are consumed. It is a positive "
        "RATE, not a complete set, and only an editor run says whether a set "
        "built this way reaches the goal's terminal condition. What is settled "
        "is the direction: the lever is authoring, the residue is addressable "
        "at zero audit cost, and the corpus was the limit rather than the "
        "problem."
    )


def six_authored_checks_drove_a_design_further_than_any_selection() -> str:
    """The fifth graded editor run, and the first where the criterion reached
    ZERO on a set whose audit is also zero and broad enough to be worth
    reaching.

    Reported as the goal's pair, because the headline is a negative and the
    body is a positive: the design is NOT equivalent, and it is the closest any
    set here has driven one.
    """
    return (
        "Same starting design as the four graded runs before it -- `gen/L.v`, "
        "written from the specification by an agent forbidden to open any "
        "other, held out of every selection. Same Sonnet editor through the "
        "shipped `_EditSession` policy, same 21-trial budget. The set is "
        "**CEIL2's 163 sound checks plus the six authored at named holes**: "
        "169 checks, **set blindness 55.1%, audit ZERO**. Graded in its own "
        "clean directory from `dut.v`, three pins green in the same process.\n\n"
        "    run   set                checks  blind  *audit*  objections  "
        "testpoints differing of 348\n"
        "    1     ZERO                 126   99.8%   *0*      11 -> 1      "
        "279 -> 271  (78%)\n"
        "    2     MIN                  464    0.0%  *64%*    295 -> 277    "
        "279 -> 241  (69%)\n"
        "    3     T6                   201   40.4%  *19%*     39 -> 11     "
        "279 -> 200  (57%)\n"
        "    4     CEIL2                163   56.9%   *0*      22 -> 5      "
        "279 -> 190  (55%)\n"
        "    **5   CEIL2 + the six**    169   55.1%   *0*      24 -> **0**  "
        "279 -> **151  (43%)**\n\n"
        "**IT IS `DIFFERS`, AND IT IS THE BEST-DRIVEN DESIGN ON THIS PLAN BY "
        "39 TESTPOINTS.** Divergence fell 46% from the start point against the "
        "next-best set's 32%, and the criterion terminated at zero rather than "
        "stalling with objections standing.\n\n"
        "**AND ZERO STILL DOES NOT MEAN EQUIVALENT, ON A SET THAT SPARES THE "
        "REFERENCE EVERYWHERE.** This is the second time zero has been reached "
        "at an audit of zero. The first was MAXSOUND, where the explanation "
        "was thinness. Here the set is 169 checks over a sound base and the "
        "explanation is stated as a golden-free number: **3,119 of 5,656 "
        "disagreement cells -- 55.1% -- are invisible to it.** A design can "
        "satisfy every check and still sit 151 testpoints from the reference "
        "because the checks cannot see the other 55%. Blindness and the "
        "residual divergence are the same fact measured two ways, and only the "
        "first is golden-free.\n\n"
        "**THE SIX ARE ATTRIBUTABLE, AND THE TEST HAS NO RUN VARIANCE IN IT.** "
        "Comparing run 4 with run 5 compares two editor samples. So the six "
        "were scored directly against the design **run 4 itself produced**:\n\n"
        "    the six authored checks, on each graded accepted design\n"
        "      L_afterHOLE   0 of 6      L_afterZERO   1 of 6\n"
        "      L_afterSOUND  0 of 6      L_afterT6     2 of 6\n"
        "      L_afterSD     1 of 6      **L_afterFULL  2 of 6**\n"
        "      L_afterMIN    4 of 6\n\n"
        "**TWO OF THE SIX CONVICT THE DESIGN CEIL2's OWN RUN STOPPED ON**, "
        "naming a concrete edge each -- `REQ-0029@dc_addr` at TP-9203 edge 22 "
        "(`dc_addr` not driven from `start_addr` during hit/miss evaluation) "
        "and `REQ-0087@biu_read` at TP-0033 edge 5 (`biu_read` low during miss "
        "evaluation). Those are defects the 163-check set that produced that "
        "design could not see, found by checks that convict the reference "
        "nowhere. **That is the blindness residue closing, on a fixed design, "
        "with no editor in the loop.**\n\n"
        "**BLINDNESS DID NOT PREDICT THE IMPROVEMENT, WHICH CORRECTS THE "
        "READING OF THE CURVE.** Runs 4 and 5 differ by **1.8 points of "
        "blindness** and by **39 testpoints of drive**. So at the margin the "
        "aggregate number is not the thing that moved -- six specific checks "
        "aimed at named cells were. Blindness remains the right target and is "
        "measured here to be a poor unit of account for small changes to a "
        "set: report the cells closed and which they were, not the percentage "
        "alone.\n\n"
        "**WHAT IS NOT ESTABLISHED.** One run per set, so the 190-versus-151 "
        "comparison is directional and the 2-of-6 is the part that stands "
        "without it. Run 5 spent 10 of 21 trials and stopped because its "
        "criterion was met, so the remaining 151 testpoints are not evidence "
        "the editor could not go further -- they are evidence the set stopped "
        "asking. And 55.1% blindness at 169 checks against 0.0% at 464 with an "
        "audit of 64% is the same trade as ever: authoring is the only route "
        "measured to move blindness at zero audit cost, and six checks bought "
        "1.8 points of it."
    )


def the_authoring_round_was_capped_by_a_regex_not_by_the_holes() -> str:
    """Why the first authoring round could not have a second: its target
    population was exhausted, and the thing that exhausted it was a lexical
    shortcut over an artifact the pipeline already computes properly.

    Purely mechanical -- two set sizes and their inclusion. No model call, no
    reference, nothing to pre-register.
    """
    return (
        "The authoring round that closed 102 cells drew 37 targets. Drawing "
        "again, against the same targeting and the enlarged set's 3,119 "
        "remaining holes, yields **ONE**. So it was never a sample of the "
        "residue -- it was the whole reach of the instrument, and the "
        "instrument stopped.\n\n"
        "**WHAT DID THE STOPPING.** A target is a (requirement, port) pair: a "
        "port two spec-derived designs disagree on, and a requirement whose "
        "sentence is the author's authority for saying which is wrong. The "
        "pairing was a regex -- *does this behavioural requirement's TEXT "
        "contain the port's name*. `normalized.json`, which the pipeline "
        "already produces from specification and contract alone, answers the "
        "same question structurally, in `activation` / `observable` / "
        "`observed_via`:\n\n"
        "    port              lexical   normalized    new\n"
        "    biu_read                5           38     33\n"
        "    saved_addr              7           32     25\n"
        "    biu_write               4           26     22\n"
        "    burst                   3           26     23\n"
        "    dc_addr                 3           26     23\n"
        "    first_miss_ack          3           23     20\n"
        "    dcram_we                5           21     16\n"
        "    first_hit_ack           5           20     15\n"
        "    tag_we                  2           16     14\n"
        "    first_miss_err          1            9      8\n"
        "    **TOTAL**             **38**     **237**  **199**\n\n"
        "**THE REGEX REACHED 16% OF WHAT THE PIPELINE ALREADY KNEW, AND THE "
        "NORMALIZED MAP IS A STRICT SUPERSET** -- their union is 237, so every "
        "pair the text names the normalization names too, plus 199 more.\n\n"
        "**AND ONE SHORTCUT PRODUCED BOTH DIRECTIONS OF ERROR.** It "
        "over-matched: a requirement that MENTIONS a port need not have an "
        "obligation GOVERNING it, which is why at least 8 of the 37 targets "
        "were unanswerable and the round's rate had to be quoted twice, 6 of "
        "37 and 6 of ~29. It under-matched: 199 requirements with a normalized "
        "obligation on a hole port were never asked at all. A lexical proxy "
        "for a structural relation is wrong in both directions at once.\n\n"
        "**WHAT THIS DOES AND DOES NOT REVISE.** The round's own numbers are "
        "unchanged -- 6 accepted, 102 cells closed, audit zero, and two of the "
        "six convict the design the base set's own editor stopped on. What is "
        "revised is what they were a rate OF: not 16% of an open population "
        "but 16% of a nearly closed one. **`authoring_at_a_named_hole_closes_"
        "cells_that_selection_cannot` said the corpus was the limit rather "
        "than the problem; this says the same of the targeting.** Whether the "
        "wider population authors at the same rate is a separate measurement "
        "and is not claimed here.\n\n"
        "**THE GENERAL FORM, because this is the third time on this plan.** An "
        "instrument that looked like a sampler was a census. The tell is "
        "cheap and was available before any call: **draw the sample twice.** "
        "A population that yields 37 and then 1 is not one you are sampling, "
        "and no rate measured on it projects."
    )
