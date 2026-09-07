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
satisfies rather than on objections it has left.

WHY ALL OF THAT FAILS IS MEASURED AND IS NOT A PROPERTY OF ANY INSTRUMENT HERE.
On the cells the population cannot agree on, a reader asked ONE targeted question
-- one cell, one port, the specification and the input sequence, no design at all
-- scores WORSE than the population it was meant to beat, and reproduces the
population's exact wrong answer on most of the cells it gets wrong. The
correlated error belongs to the specification-and-reader pair, not to the
design-writing task, so no change of instrument, ordering or granularity
decorrelates it. `split_cells_are_a_specification_finding` carries the numbers
and the one thing that follows from them.
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
    design's errors are different readings of an ambiguous sentence. Use this to
    REJECT a check that can never fail. Do not read a pass as evidence the check
    is any good.
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
