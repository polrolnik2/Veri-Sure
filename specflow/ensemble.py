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
attack that residue directly.

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
        "first time both ends of that trade have been measured on one set."
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
