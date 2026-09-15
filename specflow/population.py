"""Population-based selection -- the one soundness signal measured to work here.

The oracle stage has to decide whether a check is OVER-STRICT (it convicts a
design that satisfies its requirement) without a known-good design, which exists
only in a benchmark. Every text-side and gate-side attempt at that question has
been measured at or near chance. What does carry signal is a fact about a
POPULATION of designs written independently from the same specification:

    a requirement that MOST competent independent implementations violate is
    more likely one the CHECK has misread than one all those authors got wrong.

So: count how many of the population a check convicts, and drop it above a
threshold. That is the whole rule, and it is admissible everywhere -- it reads
only spec-derived artifacts.

TWO CLAUSES, AND THE FIRST IS LOAD-BEARING.

    DECIDES    the check returned True or False on at least one design
    NOT OVER-STRICT   it convicted at most `threshold` of them

Written as "convicts few" alone the rule is satisfied vacuously by a check that
never decides at all, which is soundness by silence rather than by evidence --
the same conflation `stage_unexercised` names in capitals, arriving in the
selector instead of in the staging loop. Recomputing one headline adequacy
figure without the first clause counted a check that decides 0 testpoints on the
reference and exactly 1 on a held-out design. `Conviction.decides` exists so that
cannot happen quietly, and `select` rejects on it by name.

PRECISION IS PARAMETER-BOUND AND THE PARAMETERS TRAVEL WITH THE NUMBER. The rule
was measured at 59 of 59 on its reject side at threshold 2 of THIRTEEN designs
over a 259-body corpus, and at 66% at threshold 2 of NINE over 502 bodies. Those
are the same rule and different instruments. `Selection.summary` therefore prints
`(threshold, population, corpus)` on every line it produces, and there is no
accessor that yields a rate without them.

WHAT IS DELIBERATELY ABSENT. Nothing here reads a known-good design, and no
function in this module computes a false-reject rate. That is structural rather
than stylistic: a control may REJECT an oracle and may never REPAIR one, and the
moment an audit lives beside a selector somebody wires the audit INTO the
selector and the grade stops being independent. Audit the kept set somewhere
else, afterwards, with something that cannot call back into this file.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from specflow.refmodel.oracles import RequirementOracle, decide

#: A design, for this module's purposes, is a way to get rows for a testpoint.
#: `None` means that design has no recording for it, which is not a verdict.
RowSource = Callable[[str], list[dict] | None]

#: Below this a "population" is a couple of opinions, not a consensus, and the
#: rule's rationale -- most independent authors agreeing -- does not apply.
MIN_POPULATION = 5


@dataclass(frozen=True)
class Conviction:
    """What one check did against the population. Never a verdict on its own."""

    req_uid: str
    #: decided True or False on at least one design. NOT "failed to convict".
    decides: bool
    #: h(c) -- how many designs it objected to.
    convicts: int
    #: N, carried so no conviction count can be read without its denominator.
    population: int


@dataclass(frozen=True)
class Selection:
    """The kept set, its parameters, and why every rejection happened."""

    threshold: int
    population: int
    corpus: int
    kept: tuple[str, ...]
    #: key -> the FIRST clause that rejected it, so the reasons partition.
    rejected: Mapping[str, str]

    def summary(self) -> str:
        """The only rendering, and it cannot omit the parameters."""
        return (
            f"{len(self.kept)} of {self.corpus} kept "
            f"(convicts <= {self.threshold} of {self.population})"
        )

    def why(self) -> dict[str, int]:
        """Rejections by clause. A cause holding nearly all the mass is a defect
        in the instrument, not a finding about the corpus -- count them so that
        is visible rather than inferred."""
        out: dict[str, int] = {}
        for reason in self.rejected.values():
            out[reason] = out.get(reason, 0) + 1
        return out


def conviction(
    oracle: RequirementOracle,
    designs: Mapping[str, RowSource],
    testpoints: Sequence[str],
) -> Conviction:
    """Decide one check against every design. Reads no known-good design."""
    decides = False
    convicts = 0
    for source in designs.values():
        objected = False
        for tp in testpoints:
            rows = source(tp)
            if rows is None:
                continue
            verdict = decide(oracle, rows)
            if verdict.broken:
                continue
            if verdict.ok is not None:
                decides = True
            if verdict.ok is False:
                objected = True
                break
        convicts += objected
    return Conviction(
        req_uid=oracle.req_uid,
        decides=decides,
        convicts=convicts,
        population=len(designs),
    )


def select(
    oracles: Iterable[tuple[str, RequirementOracle]],
    designs: Mapping[str, RowSource],
    testpoints: Sequence[str],
    *,
    threshold: int,
) -> Selection:
    """Keep a check iff it DECIDES and convicts at most `threshold` designs.

    Refuses rather than returning a number when the instrument cannot support
    one: too small a population, or a threshold that admits everything.
    """
    n = len(designs)
    if n < MIN_POPULATION:
        raise ValueError(
            f"population is {n}; the minority rule needs at least "
            f"{MIN_POPULATION} independently written designs for "
            "'most authors agree' to mean anything"
        )
    if threshold >= n:
        raise ValueError(
            f"threshold {threshold} of {n} rejects nothing for over-strictness, "
            "so the rule would be the DECIDES clause wearing a second name"
        )
    if threshold < 0:
        raise ValueError(f"threshold {threshold} is negative")
    if not testpoints:
        raise ValueError("no testpoints; every check would read as silent")

    kept: list[str] = []
    rejected: dict[str, str] = {}
    corpus = 0
    for key, oracle in oracles:
        corpus += 1
        got = conviction(oracle, designs, testpoints)
        if not got.decides:
            #: SILENT, not sound. A check that never decides has shown nothing.
            rejected[key] = "decides nowhere"
        elif got.convicts > threshold:
            rejected[key] = f"convicts {got.convicts} of {n}"
        else:
            kept.append(key)
    return Selection(
        threshold=threshold,
        population=n,
        corpus=corpus,
        kept=tuple(kept),
        rejected=rejected,
    )
