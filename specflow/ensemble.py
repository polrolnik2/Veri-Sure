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
