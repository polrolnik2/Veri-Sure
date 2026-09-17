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

**THAT PARAGRAPH WAS WRITTEN HERE AND THEN VIOLATED IN THE NEXT MODULE.** The
selection work built this rule a second time in `specflow/selection.py` and put
`audit`, `Report` and the blindness metric beside it. Both are merged back here
and the scoring instruments now live in `specflow.scoring`, which imports from
this module and is imported by nothing in it -- so the separation is enforced by
the import graph rather than by this docstring.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from math import log as _log

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
    #: raised everywhere and decided nowhere -- a defect in the CHECK, which is
    #: a different fact from a check that ran and found no occasion to speak.
    broken: bool
    #: h(c) -- how many designs it objected to.
    convicts: int
    #: N, carried so no conviction count can be read without its denominator.
    population: int


def conviction(
    oracle: RequirementOracle,
    designs: Mapping[str, RowSource],
    testpoints: Sequence[str],
) -> Conviction:
    """Decide one check against every design. Reads no known-good design."""
    decides = False
    broke = False
    convicts = 0
    for source in designs.values():
        objected = False
        for tp in testpoints:
            rows = source(tp)
            if rows is None:
                continue
            verdict = decide(oracle, rows)
            if verdict.broken:
                #: A CHECK THAT RAISES IS NOT A CHECK THAT WAS SILENT. Folding
                #: the two loses the distinction this project names in capitals
                #: one stage earlier, so it is carried and reported separately.
                broke = True
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
        broken=broke and not decides,
        convicts=convicts,
        population=len(designs),
    )



Rows = Sequence[Mapping[str, object]]
#: `decide_on(rows) -> bool | None` -- True when the check CONVICTS those rows,
#: False when it decides and spares them, None when it never decided. The
#: tri-state is load-bearing: None is not a pass.
DecideOn = Callable[[Rows], "bool | None"]
#: `gate(key) -> str | None` -- why this check is unusable, or None. Supplied by
#: the caller so this module needs none of the pipeline's heavy imports; build
#: the real one with `pipeline_gates`.
Gate = Callable[[str], "str | None"]

#: The threshold the sweep measured a step at. Not a tuning parameter: the rule
#: is exact at 0 and at `len(population)`, and carries no signal between them.
ZERO = 0


@dataclass(frozen=True)
class Ruleset:
    """Which legs are on. Golden-free by construction -- no field names a
    reference, and `select` has no parameter that could carry one.
    """

    #: Keep a check convicting at most this many of the population.
    max_convictions: int = ZERO
    #: How many population members the check must DECIDE on. **0 turns the leg
    #: off and admits sound-by-silence**, which is the conflation the module
    #: docstring names; it exists so a sweep can measure what the leg costs.
    #:
    #: 1 is the weakest form that is not off, and it is the default because it
    #: is what the measured rule had. It is NOT free of the conflation it
    #: guards: a check deciding on one of seven spares the other six by
    #: silence. Measured on the set this module reproduces, exactly two of 126
    #: are in that position and both are checks on a state `build_config`
    #: compiles out -- see `a_compiled_out_state_reads_as_sound_for_free`.
    #: Raising this to a majority removes them and has not been scored.
    min_decides: int = 1
    #: Run the caller's gate before the population is consulted. The gates are
    #: text-and-replay instruments the pipeline already ships and none reads a
    #: reference, so composing them changes nothing about admissibility.
    use_gates: bool = True
    #: Below this a "population" is a couple of opinions rather than a
    #: consensus and the rule's rationale does not apply. A caller wanting a
    #: smaller one must say so HERE, which puts the concession in the call
    #: rather than in a comment. **It should gate on EFFECTIVE size** --
    #: `PopulationShape.effective_size` -- because five near-clones are one
    #: opinion five times, and four designs one per cluster reached 1.5% where
    #: seven reached 0%.
    min_population: int = MIN_POPULATION
    #: **THE ONLY WAY PAST THE "rejects nothing" REFUSAL, AND IT EXISTS FOR ONE
    #: CALLER.** `sweep` reports the endpoint `t = N` on purpose: it is the
    #: whole corpus, and it is what the filter is measured AGAINST. A caller
    #: setting this outside a sweep has turned the over-strictness leg off and
    #: is running the DECIDES clause under a second name.
    allow_vacuous_threshold: bool = False
    #: **KEEP A CHECK WHOSE OBJECTIONS LAND WHERE THE POPULATION SPLITS.**
    #: `placement` is `(share of SPLIT testpoints it speaks on) - (share of
    #: AGREED testpoints it speaks on)`, so it runs +1 for a check that objects
    #: only where the designs differ, -1 for one that objects only where they
    #: agree, and **0 for a check that objects everywhere OR nowhere**. This is
    #: a MINIMUM: a completeness leg wants the high end.
    #:
    #: **AND THAT IS THE OPPOSITE SIGN TO THE RECORDED RULE, WHICH IS A
    #: RETRACTION -- see `placement_selected_a_blunderbuss_set_and_the_blindness_
    #: number_was_polarity_uncorrected` in `scoring`.** The recorded
    #: `placement < 0.0017` at 20.8% blindness is the best triple on that board
    #: and it does not survive polarity correction: it keeps the 126 `t = 0`
    #: checks, which score 0 by objecting to nothing, plus 25 of which **24
    #: convict all seven designs**, which score ~0 by objecting to everything. A
    #: check convicting both sides of a pair SEPARATES NEITHER -- it closes the
    #: cell only under the recorded predicate "no check objects to either".
    #:
    #: The TELL is golden-free either way -- it reads only the check's own
    #: verdicts and which testpoints split. `None` leaves the leg off, which is
    #: the default, because no threshold for this direction has been measured:
    #: the recorded plateau (0.0005-0.003) belongs to the other sign and does
    #: not transfer.
    min_placement: float | None = None

    def __post_init__(self) -> None:
        if self.max_convictions < 0:
            raise ValueError("max_convictions cannot be negative")
        if self.min_decides < 0:
            raise ValueError("min_decides cannot be negative")
        if self.min_population < 1:
            raise ValueError("min_population must admit at least one design")


@dataclass(frozen=True)
class Verdict:
    """One check's fate, with everything that decided it."""

    key: str
    kept: bool
    #: How many population members it convicted, and how many it decided on.
    #: `decided` is why a silent check is distinguishable from a sparing one.
    convicts: int = 0
    decided: int = 0
    #: The leg that dropped it: "gate", "broken", "silent", "over_strict",
    #: "placement",
    #: or "" if kept.
    reason: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Selection:
    """A set, and the rule that built it. Carries no reference information."""

    ruleset: Ruleset
    verdicts: tuple[Verdict, ...]
    population_size: int

    def __post_init__(self) -> None:
        keys = [v.key for v in self.verdicts]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "duplicate keys in the verdicts; a rejection would be silently "
                "overwritten and the kept/dropped halves would stop "
                "partitioning the corpus"
            )

    def summary(self) -> str:
        """The only rendering, and it cannot omit the parameters. PRECISION IS
        PARAMETER-BOUND: the rule was measured at 59 of 59 at threshold 2 of
        THIRTEEN designs over 259 bodies, and at 66% at threshold 2 of NINE over
        502. Same rule, different instruments."""
        return (
            f"{len(self.kept)} of {len(self.verdicts)} kept "
            f"(convicts <= {self.ruleset.max_convictions} of "
            f"{self.population_size})"
        )

    @property
    def kept(self) -> tuple[str, ...]:
        return tuple(v.key for v in self.verdicts if v.kept)

    @property
    def dropped(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if not v.kept)

    def span(self, requirement_of: Callable[[str], str]) -> set[str]:
        """The requirements the kept checks cover."""
        return {requirement_of(k) for k in self.kept}

    def by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in self.dropped:
            out[v.reason] = out.get(v.reason, 0) + 1
        return out


def convictions(decide_on: DecideOn,
                population: Iterable[Rows]) -> tuple[int, int, int]:
    """`(convicted, decided, broken)` over the population.

    All three are returned because a check convicting 0 of 7, a check deciding
    on none of them, and a check that RAISED on all of them are the same
    number under the rule and three different facts about the check. `select`
    uses the second and third to tell them apart.
    """
    convicted = decided = broke = 0
    for rows in population:
        try:
            got = decide_on(rows)
        except Exception:
            #: A CHECK THAT RAISES IS NOT A CHECK THAT WAS SILENT. The first
            #: implementation carried this distinction and the second dropped
            #: it, so a body that crashed on every design read as "sound,
            #: convicts nobody" and the rule at low `t` KEPT it.
            broke += 1
            continue
        if got is None:
            continue
        decided += 1
        convicted += bool(got)
    return convicted, decided, broke


def select(
    corpus: Mapping[str, DecideOn],
    population: Sequence[Rows],
    *,
    ruleset: Ruleset | None = None,
    gate: Gate | None = None,
    #: Required when `Ruleset.max_placement` is set, and meaningless otherwise.
    #: `placement` is a statement about WHERE a check speaks relative to where
    #: the population splits, so it cannot be computed from the flat rows the
    #: other legs use -- it needs the shape and the per-check objection map.
    #: Both are golden-free; passing them adds no reference to this signature.
    shape: "PopulationShape | None" = None,
    objections: Mapping[str, "ObjectionMap"] | None = None,
) -> Selection:
    """Keep the checks the rule keeps. Reads only spec-derived designs.

    `corpus` maps a check key to its decider; `population` is the independently
    written designs. **There is no reference parameter and there must never be
    one** -- an audit is `audit(selection, ...)`, computed afterwards, and it
    feeds nothing back here.

    THE ORDER OF THE LEGS IS DELIBERATE. The gate runs FIRST, before any
    population replay, because a malformed check has no meaningful conviction
    count and letting it score one wastes the population's evidence on a body
    that cannot be used whatever it says.

    **AND KEEPING A CHECK HERE IS NOT A CLAIM THAT IT IS ANY GOOD.** At
    `max_convictions = 0` this predicts SOUNDNESS at 126 of 126 and selects, by
    the same predicate, for a set blind to 99.8% of the disagreements it is
    shown. Report `set_blindness` beside the span or the number is half a result.
    """
    rules = ruleset or Ruleset()
    #: **THE LEG REFUSES TO RUN WITHOUT ITS INPUTS RATHER THAN SKIPPING.** A
    #: placement bound that silently does nothing because the caller forgot the
    #: shape would report a `placement < t` set that never applied the rule --
    #: the exact shape of defect `over_strict: 0` was, where a leg that had not
    #: run read as a leg that found nothing.
    if rules.min_placement is not None and (shape is None or objections is None):
        raise ValueError(
            "min_placement is set but `shape` and `objections` were not given, "
            "so the leg cannot be computed; pass both or leave the leg off")
    n = len(population)
    #: THE REFUSALS THE SECOND IMPLEMENTATION DROPPED. Each answers "can this
    #: instrument support a number at all", and each was in the first one.
    if not corpus:
        raise ValueError("no checks; '0 of 0 kept' is not a selection")
    if n < rules.min_population:
        raise ValueError(
            f"population is {n}; the minority rule needs at least "
            f"{rules.min_population} independently written designs for "
            "'most authors agree' to mean anything"
        )
    if rules.max_convictions >= n and not rules.allow_vacuous_threshold:
        raise ValueError(
            f"max_convictions {rules.max_convictions} of {n} rejects nothing "
            "for over-strictness, so the rule would be the DECIDES clause "
            "wearing a second name"
        )
    out: list[Verdict] = []
    for key, decide_on in corpus.items():
        if rules.use_gates and gate is not None:
            why = gate(key)
            if why:
                out.append(Verdict(key, False, reason="gate", detail=why))
                continue
        hits, decided, broke = convictions(decide_on, population)
        if broke and not decided:
            out.append(Verdict(
                key, False, hits, decided, "broken",
                f"raised on all {broke} designs it was run against and decided "
                "nowhere, which is a defect in the CHECK rather than a fact "
                "about the stimulus"))
            continue
        if decided < rules.min_decides:
            out.append(Verdict(
                key, False, hits, decided, "silent",
                f"decides on {decided} of {len(population)} population "
                f"members, below the {rules.min_decides} required, so sparing "
                f"the rest is silence rather than evidence"))
            continue
        if hits > rules.max_convictions:
            out.append(Verdict(
                key, False, hits, decided, "over_strict",
                f"convicts {hits} of {len(population)} independently written "
                f"designs, above the threshold of {rules.max_convictions}"))
            continue
        if rules.min_placement is not None:
            assert shape is not None and objections is not None
            spoke = tells(objections.get(key, {}), shape).placement
            if spoke < rules.min_placement:
                out.append(Verdict(
                    key, False, hits, decided, "placement",
                    f"placement {spoke:+.4f} is below {rules.min_placement}: it "
                    f"does not speak preferentially where the population "
                    f"SPLITS, so its objections do not land on the differences "
                    f"this set exists to adjudicate. A check objecting "
                    f"everywhere scores ~0 here and separates no pair"))
                continue
        out.append(Verdict(key, True, hits, decided))
    #: **A GATED CHECK NEVER CONSULTED THE POPULATION**, so it is not evidence
    #: about whether the population split -- and it does not need filtering out,
    #: because the gate leg `continue`s BEFORE `convictions` runs and a gate
    #: verdict therefore carries `decided = 0` and `convicts = 0`. Neither term
    #: below can be moved by one.
    #:
    #: A filter was added here for that reason and was DEAD: the whole suite
    #: passed with it removed, and the mutation that neutralised it survived.
    #: It is written as an invariant instead, so that moving the gate AFTER the
    #: population replay -- which would give gate verdicts real conviction
    #: counts -- breaks here rather than silently re-arming the guard.
    assert all(v.decided == 0 and v.convicts == 0
               for v in out if v.reason == "gate"), (
        "a gated verdict carries conviction evidence; the clone guard below "
        "now counts checks that never consulted the population")
    if any(v.decided for v in out) and not any(0 < v.convicts < n for v in out):
        #: THE POPULATION NEVER SPLIT, so the rule's premise -- that most
        #: independent authors agree -- was never exercised. Every check
        #: convicted all of them or none, which is what N copies of ONE design
        #: look like from in here. This module cannot know WHICH designs a
        #: caller passed; it can know the population carried no disagreement,
        #: and that is the shape a cloned reference would take.
        raise ValueError(
            f"no check split the population of {n}: every conviction count is "
            "0 or N, so these designs are behaviourally indistinguishable on "
            "this corpus and the minority rule measured nothing"
        )
    return Selection(rules, tuple(out), n)


# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Bucket:
    """Checks convicting exactly this many of the population."""

    convicts: int
    checks: int


def buckets(corpus: Mapping[str, DecideOn],
            population: Sequence[Rows]) -> tuple[Bucket, ...]:
    """The PER-BUCKET profile, which is the informative decomposition.

    **A CUMULATIVE SWEEP TABLE OVERSTATES HOW ORDERLY THE TRADE IS, AND THIS IS
    THE CORRECTION TO THE FIRST VERSION OF THAT FINDING.** The thresholds NEST,
    so a cumulative audit COUNT cannot fall as `t` grows -- its monotonicity is
    a property of the construction and carries no information at all. The audit
    RATE is not monotone either; it dips partway along. Per bucket the structure
    is visible and is not a smooth price:

        the check convicts   checks   convict the reference
        0 of 7                 126      0 =   0.0%
        1 to 6 of 7             75     38 =  50.7%
        7 of 7                 263    261 =  99.2%

    **AND THE MIDDLE BAND IS EXACTLY WHERE THE BLINDNESS REDUCTION LIVES** --
    those 75 checks carry blindness from 99.8% to 40.4%. So every point inside
    the band is bought at a rule with no signal, 50.7%, which is the coin flip.
    """
    tally: dict[int, int] = {}
    for decide_on in corpus.values():
        hits, decided, _ = convictions(decide_on, population)
        if not decided:
            continue
        tally[hits] = tally.get(hits, 0) + 1
    return tuple(Bucket(c, tally[c]) for c in sorted(tally))


def sweep(corpus: Mapping[str, DecideOn], population: Sequence[Rows], *,
          ruleset: Ruleset | None = None,
          gate: Gate | None = None) -> tuple[Selection, ...]:
    """One `Selection` per threshold, `t = 0` to `len(population)`.

    Reading it: the counts NEST, so read `buckets` for what each step actually
    added rather than differencing this.
    """
    base = ruleset or Ruleset()
    #: The last bucket is `t = N`, which rejects nothing for over-strictness and
    #: is therefore the WHOLE CORPUS -- the thing every other bucket is measured
    #: against. `select` refuses that threshold by default, so the sweep says so
    #: explicitly here rather than the refusal being quietly absent.
    return tuple(
        select(corpus, population,
               ruleset=replace(base, max_convictions=t,
                               allow_vacuous_threshold=t >= len(population)),
               gate=gate)
        for t in range(len(population) + 1))


# --------------------------------------------------------------------------
# REPORTING ONLY. Nothing below may be called from `select`, and `select` has
# no parameter that would let it.
# --------------------------------------------------------------------------

def refutable(decide_on: DecideOn, population: Iterable[Rows],
              mutants: Iterable[Rows]) -> bool:
    """The check spares every population member and convicts some mutant.

    **REPORT WITH IT; NEVER SELECT WITH IT, AND THAT IS MEASURED RATHER THAN
    CAUTIOUS.** Used as a selection leg -- drop a check that convicts no
    candidate -- it discards 21% of the entire measured yield: of 14 sound
    checks that caught a design held out of the population, THREE convict none
    of it, because the population is simply RIGHT about those requirements. A
    check that never objects also never mis-steers a repair loop, so keeping it
    costs nothing and dropping it costs the three.

    And a pass here is weak in the other direction too: of 19 checks this
    promoted, 19 spare the reference and ZERO catch a from-scratch design wrong
    on 61% of the suite. A mutant is an operator substitution; a real design's
    errors are different readings of an ambiguous sentence.
    """
    if any(decide_on(rows) for rows in population):
        return False
    return any(decide_on(rows) for rows in mutants)


def soundness_and_blindness_are_one_knob() -> str:
    """Why `max_convictions` cannot be tuned to get both, measured as a curve.

    Kept as code rather than a comment so it is found by whoever reaches for the
    idea, which is the natural one and is refuted.
    """
    return (
        "One golden-free knob -- keep a check convicting at most t of seven "
        "independently written spec-derived designs -- swept end to end, with "
        "the audit computed last:\n\n"
        "    t   checks   reqs of 87   SET BLINDNESS   *audit*\n"
        "    0     126      55 = 63%      99.8%        *  0 =  0.0%*\n"
        "    1     149      63 = 72%      93.5%        * 11 =  7.4%*\n"
        "    2     167      68 = 78%      66.5%        * 22 = 13.2%*\n"
        "    4     179      69 = 79%      61.9%        * 27 = 15.1%*\n"
        "    6     201      71 = 82%      40.4%        * 38 = 18.9%*\n"
        "    7     464      73 = 84%       0.0%        *299 = 64.4%*\n\n"
        "**BLINDNESS FALLS AND THE AUDIT RISES ACROSS THE WHOLE SWEEP.** "
        "Completeness and soundness are not two properties a better rule could "
        "optimise jointly -- golden-free, on this corpus, they are ONE KNOB "
        "read in two directions.\n\n"
        "**AND THE REFERENCE-SELECTED SET IS OFF THE CURVE, WHICH IS THE PART "
        "THAT MATTERS.** The largest perfectly sound set the reference can "
        "pick is 163 checks at 56.9% blind with an audit of ZERO. No "
        "golden-free threshold reaches that point: getting to 52.7% blind "
        "costs 14.4% false rejection. The mechanism closes exactly rather than "
        "being a tendency -- 161 of those 163 checks are inside t = 6, t = 6 "
        "holds exactly 38 audit failures, and the other two are the only two "
        "checks in the corpus convicting all seven and still sparing the "
        "reference. So the reference-selected set IS t = 6 with its 38 audit "
        "failures removed and those two added, nothing left over. Those 38 "
        "close 933 disagreement cells, 16.5 points of blindness, **and nothing "
        "sound replaces them.**\n\n"
        "**SO COMPLETENESS CANNOT BE ASSURED GOLDEN-FREE ON THIS CORPUS.** "
        "Every golden-free step toward it is a step into false rejection, and "
        "the obstruction is a measured monotone trade rather than a rule "
        "nobody has thought of yet."
    )


# --------------------------------------------------------------------------
# THE PIPELINE'S OWN GATES, composed as the rule's first leg.
#
# Every gate below already ships and already blocks in `oracles_stage`, and
# none of them reads a reference -- they are text against text, or replay
# against the witness and its variants. So composing them costs no
# admissibility: a check this drops would have been dropped by the stage too.
# What the composition buys is that the DROP IS RECORDED AND ATTRIBUTED, where
# the stage's disposition loop absorbs it into a repair round.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GateLegs:
    """Which shipped gates run. Each is separately switchable so an experiment
    can price one leg at a time, which is the discipline that caught the last
    three levers measuring something other than what they claimed.
    """

    #: Static and text-only: the body compiles, `decide` has arity 1, `strong`
    #: is stated, the named testpoints exist, and it reads a declared OUTPUT.
    #: The last clause is load-bearing -- a check over the stimulus alone can
    #: be failed by no design, and 11 such bodies were found across four runs,
    #: eight ABANDONED and one TRUSTED AND FROZEN.
    well_formed: bool = True
    #: Two texts, no implementation: does the check test its requirement.
    #: `not-assertable` accuses the SPECIFICATION and is kept separate below,
    #: because dropping a check for it silently shrinks the denominator.
    correspondence: bool = True
    #: The check catches a mutant of the witness, so it CAN fail.
    vacuity: bool = True
    #: ON, and a previous version of this file had it off for a reason that
    #: does not survive reading `liveness.py`. **`DEAD_ORACLE` IS A FLOOR, NOT
    #: A GRADIENT.** It is the last branch after `LIVE` (a near perturbation
    #: moves it, or it is already failing), `DEAD_STIMULUS` (only a far one
    #: does -- explicitly NOT a rejection, the check demonstrably can fail) and
    #: `UNKNOWN` (it never decided, which is the stimulus's business). What is
    #: left means *no legal value of any port it reads changes its verdict
    #: anywhere* -- a constant function, which is not a check.
    #:
    #: So it is on the same side as `well_formed`, not opposite it: a constant
    #: body convicts nobody, so the threshold rule at low `max_convictions`
    #: keeps it PREFERENTIALLY. Liveness catches that class, and catches bodies
    #: `well_formed` cannot see because they are syntactically fine and
    #: semantically constant. It costs no model call.
    #:
    #: The misattribution worth worrying about is already handled upstream: the
    #: `UNKNOWN` branch exists so a never-triggered check does not land here,
    #: added after z-i2c measured all 11 `DEAD_ORACLE` verdicts to be checks
    #: returning None everywhere, nine re-asked and nine returned unchanged,
    #: NONE of them the author's.
    liveness: bool = True

    @classmethod
    def corpus_path(cls) -> "GateLegs":
        """**A3: THE GATES THAT RUN WHILE A CORPUS IS BEING BUILT.**

        Every rejecting gate shrinks the corpus and SELECTION IS MEANT TO BE
        THE FILTER, so only the free structural floors run here:

            well_formed   static, no model call. Removes 5 of the 126-check
                          set at ZERO span cost -- 9 of 464 overall.
            liveness      a FLOOR, not a gradient: a constant function, which
                          the threshold rule at low `max_convictions` keeps
                          preferentially. No model call.

        **`correspondence` IS DROPPED, and it is the expensive one.** 147 of
        149 `ORACLE_INVALID` dispositions across six runs are correspondence
        off-target, spanning 1 to 51 requirements per run (1% to 46%), Spearman
        -0.771 against the TRUSTED rate -- most of the 3.3x run-to-run spread,
        from a judge measured at 1.3x lift that went 0-for-6 on timing and once
        prescribed the defect idiom to a working check. One model call per body
        to shrink the corpus by an amount that correlates with getting worse.

        **`vacuity` is dropped for cost, not for merit**: it needs mutants of
        the witness, and the corpus path is meant to be free. `must_fail` is
        open and measured in F2.

        BOTH STILL RUN ON THE SHIPPING PATH. This is the corpus-building
        configuration, not a weakening of what ships.
        """
        return cls(well_formed=True, correspondence=False,
                   vacuity=False, liveness=True)

    @classmethod
    def shipping_path(cls) -> "GateLegs":
        """Everything on -- what a run that keeps ONE body per requirement
        needs, because nothing downstream will filter for it."""
        return cls()


def pipeline_gates(
    oracles: Mapping[str, object],
    contract: dict,
    testplan: list[dict],
    *,
    legs: GateLegs | None = None,
    variants: list | None = None,
    stimulus_by_tp: Mapping[str, list[dict]] | None = None,
    reviews: Mapping[str, object] | None = None,
    traces: Mapping[str, list[dict]] | None = None,
    witness: str = "",
    drop_not_assertable: bool = False,
) -> Gate:
    """A `Gate` over the pipeline's shipped instruments, keyed like the corpus.

    `oracles` maps the same keys `select` will use to `RequirementOracle`
    objects. Everything else is what that gate needs and is optional: a leg with
    nothing to run on is SKIPPED rather than failing the check, because a
    missing artifact is a fact about the harness and convicting a check for it
    is the conflation `must_fail` had to be repaired for twice.

    `drop_not_assertable` is False on purpose. A `not-assertable` verdict says
    the REQUIREMENT states no obligation, so dropping the check removes a
    requirement from the denominator on a judge's say-so -- measured once at 12
    of 12 such verdicts being checks that simply never fired, with the judge
    converting "this author wrote no check" into "this requirement cannot be
    asserted". Route it; do not let it shrink the span.
    """
    from specflow.refmodel import correspondence as _corr  # noqa: PLC0415
    from specflow.refmodel import liveness as _liv  # noqa: PLC0415
    from specflow.refmodel import trust as _trust  # noqa: PLC0415
    from specflow.refmodel import variants as _var  # noqa: PLC0415
    from specflow.refmodel.oracles import well_formed as _wf  # noqa: PLC0415

    on = legs or GateLegs()
    stim = dict(stimulus_by_tp or {})

    def gate(key: str) -> str | None:
        oracle = oracles.get(key)
        if oracle is None:
            # A key with no body is NOT a check that passed. It is a missing
            # artifact, and reading it as a pass is how a dropped body became a
            # silent acceptance once already.
            return "no body for this key"
        if on.well_formed:
            why = _wf(oracle, contract, testplan)
            if why:
                return f"malformed: {why}"
        if on.correspondence and reviews is not None:
            review = reviews.get(key)
            if review is not None:
                off = _corr.rejects(review)
                if off and (drop_not_assertable
                            or not off.startswith("not-assertable:")):
                    return off
        replayable = any(stim.get(tp) for tp in getattr(oracle, "tp_uids", ()))
        if on.vacuity and variants and replayable:
            level, detail, _ = _var.must_fail(
                oracle, variants, contract, stim, conforming=witness)
            if level == _trust.CONVICTED:
                return f"vacuous: {detail}"
        if on.liveness and traces:
            record = _liv.liveness_of(oracle, dict(traces), contract)
            if record.get("verdict") == _liv.DEAD_ORACLE:
                return f"dead: {record.get('detail') or '(no detail)'}"
        return None

    return gate


def the_gates_and_the_rule_reject_different_checks() -> str:
    """What composing the shipped gates with the threshold rule is for.

    Stated because the obvious reading -- that the gates are a weaker version of
    the rule and composing them is belt and braces -- is wrong in both
    directions, and the second direction is the one that matters.
    """
    return (
        "**THE TWO LEGS ASK DIFFERENT QUESTIONS AND THE OVERLAP IS NOT THE "
        "POINT.** The threshold rule asks whether a check convicts designs that "
        "were written to satisfy the specification, which is a claim about "
        "OVER-STRICTNESS. The shipped gates ask whether the body compiles, "
        "names an output, tests its own requirement, and can fail at all -- "
        "claims about WELL-FORMEDNESS and VACUITY. A check can pass every gate "
        "and convict all seven designs, and a check can convict none of them "
        "and contain no check at all.\n\n"
        "**AND THE SECOND CASE IS WHY THE GATES MUST RUN FIRST.** An "
        "unconditional `return (None, ...)` convicts zero of the population and "
        "is kept by the rule at t = 0 on exactly the evidence that keeps a good "
        "check there. Measured: 32 of 68 bodies in one authoring round were "
        "that, and 22 of 23 silent bodies in another. The `require_decides` leg "
        "catches the ones that never decide; `well_formed` catches the ones "
        "that decide and asserted nothing. Without both, the strongest "
        "golden-free rule here selects dead bodies preferentially, because a "
        "dead body is the cheapest way to convict nobody.\n\n"
        "**WHAT THE COMPOSITION DOES NOT BUY IS ADMISSIBILITY.** None of these "
        "gates reads a reference and neither does the rule, before or after. "
        "The set is golden-free either way; composing them changes which checks "
        "are in it, not what may be said about it.\n\n"
        "**AND `liveness` IS ON THE SAME SIDE, WHICH A PREVIOUS VERSION OF "
        "THIS TEXT GOT BACKWARDS.** It was defaulted off here on the argument "
        "that it reads verdict movement as proof a check is alive while the "
        "rule reads conviction as proof it over-reaches, so the maximally live "
        "check is the maximally over-strict one. That describes a gradient, and "
        "`DEAD_ORACLE` is a FLOOR: it fires only when no legal value of any "
        "port the check reads changes its verdict anywhere, after `LIVE`, "
        "`DEAD_STIMULUS` and `UNKNOWN` have each taken the cases they own. What "
        "it rejects is a constant function, which is the same class "
        "`require_decides` and `well_formed` exist for and the class this rule "
        "selects for hardest. It costs no model call and it is on by default.\n\n"
        "**`must_fail` IS THE ONE THAT IS ACTUALLY DEBATABLE**, and it is left "
        "on pending measurement rather than settled. It demands the check "
        "convict a MUTANT of one witness -- stronger than a verdict moving "
        "under legal values, measured confounded with over-strictness "
        "(sensitivity 0.95 among checks that convict the reference against 0.52 "
        "among sound ones), and its mutant supply saturates at about twelve "
        "parents. That shape is a gradient toward strictness, not a floor."
    )


def a_compiled_out_state_reads_as_sound_for_free() -> str:
    """What `min_decides = 1` still lets through, measured on the set this
    module reproduces rather than supposed.

    Found by re-deciding the selected set against the population from traces --
    a question the cached artifact could not answer, because it stores objecting
    testpoints only and so cannot tell "spared it" from "never ran on it".
    """
    return (
        "**THE LEG IS INERT ON THIS CORPUS AND THAT IS THE FIRST HALF OF THE "
        "RESULT.** Of the 126 checks the rule keeps at t = 0 -- the set audited "
        "at zero false rejects, 126 of 126 sparing the reference -- **ZERO "
        "decide on none of the seven.** So the headline is not contaminated by "
        "sound-by-silence: those checks spare the population by evidence. The "
        "leg guards a conflation that is real elsewhere (one adequacy headline "
        "counted a check deciding 0 testpoints on the reference and 1 on a "
        "held-out design) and it removes nothing here.\n\n"
        "**AND THE PROFILE IS NOT UNIFORM, WHICH IS THE SECOND HALF:**\n\n"
        "    decides on 7 of 7   124 checks\n"
        "    decides on 1 of 7     2 checks\n\n"
        "**BOTH OF THE TWO ARE CHECKS ON A STATE `build_config` COMPILES OUT.** "
        "They spare six of seven designs by silence and convict none of the "
        "seventh, so the rule scores them exactly as it scores a check that "
        "watched every design and objected nowhere. A check on an unreachable "
        "state is sound for free, and the golden-free rule cannot see the "
        "difference -- it has no access to whether the state exists.\n\n"
        "**SO `min_decides = 1` IS THE WEAKEST FORM THAT IS NOT OFF, AND IT IS "
        "THE DEFAULT BECAUSE IT IS WHAT THE MEASURED RULE HAD, NOT BECAUSE IT "
        "IS THE RIGHT ONE.** Raising it to a majority removes these two and has "
        "NOT been scored: it would also remove any check whose requirement is "
        "genuinely reachable on only some of the population, and nothing here "
        "says how many of those there are. Sweep it before adopting it.\n\n"
        "**AND THE AUDIT DOES NOT CATCH THEM EITHER**, which is why this needed "
        "measuring rather than reasoning about. Both spare the reference, so "
        "they sit inside a set whose false-reject rate is a measured zero while "
        "contributing nothing any design could ever fail."
    )


def the_packaged_rule_reproduces_the_measured_sweep() -> str:
    """The refactor's own pin: the module and the scripts agree everywhere.

    Recorded because a rule moved from two lines of inline set arithmetic into a
    package is exactly where a threshold goes off by one or a corpus drifts, and
    this project has made that class of error eight times. It always looks like
    a result first, so the reproduction is run before anything is claimed.
    """
    return (
        "Driven over the ORIGINAL artifacts -- the cached per (check, design) "
        "objection map and the check list the scripts selected over, not a "
        "re-globbed corpus, which is the drift `load_corpus` exists to stop:\n\n"
        "    t   checks   requirements   set blindness   *audit*\n"
        "    0     126      55            5644 = 99.8%   *  0 =  0.0%*\n"
        "    1     149      63            5287 = 93.5%   * 11 =  7.4%*\n"
        "    2     167      68            3764 = 66.5%   * 22 = 13.2%*\n"
        "    3     171      68            3632 = 64.2%   * 23 = 13.5%*\n"
        "    4     179      69            3503 = 61.9%   * 27 = 15.1%*\n"
        "    5     188      70            2978 = 52.7%   * 27 = 14.4%*\n"
        "    6     201      71            2286 = 40.4%   * 38 = 18.9%*\n"
        "    7     464      73               0 =  0.0%   *299 = 64.4%*\n\n"
        "**EVERY CELL MATCHES**, plus the per-bucket decomposition (126 / 75 / "
        "263), the 5,656-cell blindness denominator recomputed from traces over "
        "nine designs and 348 testpoints, and the per-threshold audit "
        "alignment.\n\n"
        "**WHAT IT DOES AND DOES NOT ESTABLISH.** It establishes that the "
        "packaged rule, sweep, bucket profile and blindness computation are the "
        "ones that were measured. It does NOT re-derive the decides: the "
        "objection map was cached by the original run, so a defect in `decide` "
        "itself would reproduce faithfully here. That is the right scope -- "
        "this refactor moved the SELECTION, not the replay -- and it is stated "
        "so nobody reads it as an end-to-end validation.\n\n"
        "**AND ONE LEG COULD NOT BE REPRODUCED BECAUSE IT IS NEW.** The "
        "original rule had no `min_decides`, and the cache cannot supply it: it "
        "stores objecting testpoints only, so a spared design and an "
        "un-decided one are the same empty set. That leg was measured "
        "separately by re-deciding from traces -- see "
        "`a_compiled_out_state_reads_as_sound_for_free`."
    )


# --------------------------------------------------------------------------
# THE OTHER TELLS IN THE CONVICTION MATRIX. All golden-free by construction --
# every one reads the check's own verdicts on spec-derived designs and the
# population's own agreement pattern, and `tells` has no parameter that could
# carry a reference, the same structural guarantee `select` has.
#
# MEASURED, AND THE ANSWER IS ONE SIGNAL RATHER THAN NINE. See
# `the_conviction_matrix_carries_one_signal_not_nine`. They are kept because
# one of them buys closure two and a half times more cheaply than the rule
# does -- as a COMPLETENESS instrument, which is not what its name suggests
# and not what the others were being tried for.
# --------------------------------------------------------------------------

#: `objections[design] -> the testpoints this check objected at on that design`.
#: An empty set is a design the check SPARED or never decided on; the two are
#: indistinguishable here, which is why `min_decides` is a leg of `select` and
#: not a tell.
ObjectionMap = Mapping[str, "frozenset[str] | set[str]"]


@dataclass(frozen=True)
class PopulationShape:
    """What the population looks like BEFORE any check is scored.

    Built once per population and passed to every check. `B2` requires this to
    be computed and reported whatever the selection result is: k1's precision at
    `t = 0` moves from 126-for-126 to 6.2% when one design leaves, so a
    conviction count without the shape beside it is not interpretable.
    """

    designs: tuple[str, ...]
    testpoints: tuple[str, ...]
    #: testpoints where the designs do NOT all agree
    split: frozenset[str]
    #: design -> share of `split` where it sits off the majority
    dissent: Mapping[str, float]
    #: design -> cluster id, so behavioural clones collapse to one opinion
    cluster: Mapping[str, int]
    #: testpoint -> the design pairs that disagree there
    pairs: Mapping[str, tuple[tuple[str, str], ...]]

    def __post_init__(self) -> None:
        missing = [d for d in self.designs
                   if d not in self.dissent or d not in self.cluster]
        if missing:
            raise ValueError(
                f"{len(missing)} designs have no dissent rate or cluster: "
                f"{missing[:3]}; a tell weighted by a structure that does not "
                "cover the population would silently weight them at zero"
            )
        if not self.split:
            #: NO DISAGREEMENT, NO TELLS. Every tell here is a statement about
            #: where a check speaks relative to where the population differs.
            #: With nothing to differ about they all collapse to constants, and
            #: a constant reads as a clean result. This is `population.select`'s
            #: clone guard arriving one layer up.
            raise ValueError(
                f"no testpoint splits the population of {len(self.designs)}: "
                "these designs are behaviourally indistinguishable here, so "
                "every tell below is a constant and none of them measured "
                "anything"
            )

    @property
    def agreed(self) -> frozenset[str]:
        return frozenset(self.testpoints) - self.split

    def effective_size(self) -> int:
        """Distinct opinions, not headcount. `MIN_POPULATION` should gate on
        this: five near-clones are one opinion five times, and four designs one
        per cluster reached 1.5% where seven reached 0%."""
        return len(set(self.cluster.values()))


@dataclass(frozen=True)
class TellProfile:
    """Eight readings of one check's conviction matrix. Carries no reference."""

    #: how many designs it convicted -- THE SHIPPED RULE, here for comparison
    count: int
    #: (design, testpoint) objections as a share of the whole matrix
    mass: float
    #: share of its objections landing where the population is UNANIMOUS.
    #: Structurally zero inside any `t < len(designs)` set: objecting where all
    #: designs agree convicts all of them, so such a check has `count = N` and
    #: the threshold has already removed it. 198 of t=6's 201 read exactly 0.
    split_purity: float
    #: of the disagreeing pair cells it closes, the share where it objects to
    #: BOTH sides rather than picking one
    indiscriminacy: float
    #: `count` with each design weighted by 1 - its own dissent rate, so a
    #: conviction of the population's outlier costs less than one of its centre
    dissent_weighted: float
    #: `count` with behavioural clones collapsed
    cluster_count: int
    #: 1 - normalised entropy of the mass across designs. **CONFOUNDED WITH
    #: SILENCE**: a check that objects to nothing has no mass, hence no
    #: entropy, hence concentration 0, so selecting the LOW side selects the
    #: silent checks and reads a perfect audit for the worst possible reason.
    concentration: float
    #: how much more often it speaks where the population DISAGREES than where
    #: it agrees. Measured under the name `targeting_diff`; renamed because it
    #: turned out to measure objection PLACEMENT, and to be a completeness
    #: instrument rather than a soundness one.
    placement: float


#: `author(index, spec, contract) -> design source`. **THE ISOLATION IS THE
#: SIGNATURE.** An author receives the specification and the contract and
#: nothing else -- there is no parameter through which another design, a
#: reference, or a previous member could reach it, which is the same structural
#: guarantee `select` has against the reference. An author that opens a file is
#: outside what this type can prevent and inside what `B3` forbids.
Author = Callable[[int, str, Mapping[str, object]], str]


@dataclass(frozen=True)
class Population:
    """N independently written designs, and how they were produced."""

    #: name -> source. Names are positional (`d0`, `d1`, ...) because a name
    #: carrying provenance -- "the good one", "the control" -- is how a
    #: selection over them stops being blind.
    designs: Mapping[str, str]
    #: How many authors were asked, including any whose output was refused.
    asked: int

    def __post_init__(self) -> None:
        if len(set(self.designs.values())) != len(self.designs):
            raise ValueError(
                f"{len(self.designs)} designs but "
                f"{len(set(self.designs.values()))} distinct sources: "
                "identical text is one opinion repeated, and a population of "
                "clones makes the minority rule a false-reject filter against "
                "whatever they all are")


def produce_population(author: Author, *, spec: str,
                       contract: Mapping[str, object],
                       size: int = MIN_POPULATION) -> Population:
    """**B1: ASK `size` AUTHORS, INDEPENDENTLY, AND REFUSE A PILE OF CLONES.**

    The producer that did not exist. `MIN_POPULATION` has been in this module
    the whole time and the pipeline's generator is single-design with no flag
    asking for more, so the rule this module implements had nothing to read.

    **WHAT THIS DOES AND DOES NOT GUARANTEE.** It guarantees the authors cannot
    see each other THROUGH THIS FUNCTION -- each call gets the index, the spec
    and the contract, and the accumulating designs are never passed on. It does
    not guarantee independence: authors served by one model from one prompt are
    correlated however carefully they are isolated, which is exactly why the
    population's structure has to be MEASURED afterwards by `characterise`
    rather than assumed here. On k1 that measurement found one design off the
    majority at 86% of split testpoints and seven designs collapsing to three
    opinions.

    **THE TRACE HALF IS NOT HERE.** Selection reads conviction profiles, which
    need each design suite-run. That is the existing runner's job and it needs
    a simulator, so this function returns SOURCES and the caller runs them.
    """
    if size < 2:
        raise ValueError(
            f"size {size}; a population needs at least two designs for "
            "'where do they disagree' to have an answer")
    designs: dict[str, str] = {}
    for i in range(size):
        source = author(i, spec, dict(contract))
        if not (source or "").strip():
            raise ValueError(
                f"author {i} returned nothing; a population silently short of "
                "its size is how a headcount stops matching the rate computed "
                "from it")
        designs[f"d{i}"] = source
    return Population(designs=designs, asked=size)


def characterise(rows_by_design: Mapping[str, Mapping[str, Rows]],
                 outputs: Sequence[str], *,
                 clone_distance: float = 0.25) -> PopulationShape:
    """**B2: CHARACTERISE BEFORE SELECTING.** Build the shape from traces.

    A population is not a bag of N designs, and k1 is the worked example: the
    five largest pair distances all involve one design, B/D/E sit 6% from each
    other, and every subset of the seven that audits at exactly zero contains
    the outlier. A conviction count without this beside it is not
    interpretable, so this is the step that has to run FIRST.

    `clone_distance` is the single-link threshold at which two designs collapse
    into one opinion. 0.25 is what k1's structure supports -- B/D/E/H at
    6.3-16% merge, C and F and G stand alone -- and it is a parameter rather
    than a constant because the right value is a property of the population,
    not of the rule.

    Reads only spec-derived designs. No reference, and no parameter for one.
    """
    designs = tuple(sorted(rows_by_design))
    if len(designs) < 2:
        raise ValueError(
            f"{len(designs)} design(s); a population needs at least two for "
            "'where do they disagree' to have an answer")
    testpoints = tuple(sorted(
        {tp for rows in rows_by_design.values() for tp in rows}))

    def value(rows: Rows | None, i: int, port: str) -> object:
        if rows is None or i >= len(rows):
            return None
        return str((rows[i].get("outputs") or {}).get(port))

    split: set[str] = set()
    off_majority: dict[str, set[str]] = {d: set() for d in designs}
    for tp in testpoints:
        have = [d for d in designs if rows_by_design[d].get(tp) is not None]
        if len(have) < 2:
            continue
        width = min(len(rows_by_design[d][tp]) for d in have)
        for i in range(width):
            for port in outputs:
                seen: dict[object, list[str]] = {}
                for d in have:
                    seen.setdefault(value(rows_by_design[d][tp], i, port),
                                    []).append(d)
                if len(seen) < 2:
                    continue
                split.add(tp)
                top = max(seen.values(), key=len)
                for d in have:
                    if d not in top:
                        off_majority[d].add(tp)
    if not split:
        raise ValueError(
            f"no testpoint splits the population of {len(designs)}: these "
            "designs are behaviourally indistinguishable on this suite, so "
            "nothing computed from them measures a population")

    dissent = {d: len(off_majority[d]) / len(split) for d in designs}

    pairs: dict[str, tuple[tuple[str, str], ...]] = {}
    apart: dict[tuple[str, str], int] = {}
    for tp in sorted(split):
        found = []
        have = [d for d in designs if rows_by_design[d].get(tp) is not None]
        for x, a in enumerate(have):
            for b in have[x + 1:]:
                ra, rb = rows_by_design[a][tp], rows_by_design[b][tp]
                width = min(len(ra), len(rb))
                if any(value(ra, i, p) != value(rb, i, p)
                       for i in range(width) for p in outputs):
                    found.append((a, b))
                    apart[(a, b)] = apart.get((a, b), 0) + 1
        if found:
            pairs[tp] = tuple(found)

    #: single-link clustering on PAIR DISTANCE -- the share of testpoints on
    #: which two designs disagree WITH EACH OTHER -- so behavioural clones
    #: collapse to one opinion and `effective_size` stops being a headcount.
    #: FOUR designs one-per-cluster reached 1.5% where seven reached 0%: spread
    #: buys precision, headcount does not.
    #:
    #: **THIS USED TO CLUSTER ON THE OFF-MAJORITY SIGNATURE and that was a
    #: different metric wearing this one's rationale.** The k1 numbers quoted
    #: here -- B/D/E/H merging at 6.3-16% -- are pair distances, and on k1 the
    #: two metrics happened to agree, so the substitution was invisible. On
    #: i2c's five designs they disagree completely: d0 and d2 are off the
    #: majority at largely the SAME testpoints, which makes their signatures
    #: near-identical while they disagree with each other on 65.6% of
    #: testpoints, and single-link chaining then collapsed all five into ONE
    #: cluster -- `effective_size` 1 for a population whose members differ
    #: everywhere. Being off the majority together is not being the same
    #: design, and only the pair distance answers "is this a second opinion".
    def distance(a: str, b: str) -> float:
        key = (a, b) if (a, b) in apart or a < b else (b, a)
        return apart.get(key, 0) / len(testpoints)

    groups = [{d} for d in designs]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if any(distance(a, b) < clone_distance
                       for a in groups[i] for b in groups[j]):
                    groups[i] |= groups[j]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    cluster = {d: i for i, g in enumerate(groups) for d in g}

    return PopulationShape(
        designs=designs, testpoints=testpoints, split=frozenset(split),
        dissent=dissent, cluster=cluster, pairs=pairs)


def the_dead_checks_do_not_run_at_all_and_a_shipped_gate_already_rejects_them() -> str:
    """STEP 1a, CORRECTED. The first version of this finding said the dead
    checks were silent; they crash.

    I classified them by whether the ports they read ever move, concluded they
    were authoring-logic defects for the repair round, and committed that. Then
    I asked the question I should have asked first -- do they ABSTAIN or do they
    RAISE -- and the answer changes the owner entirely.
    """
    return (
        "**39 OF 42 DEAD CHECKS NEVER EXECUTE, AND ONE MISSING KEYWORD ACCOUNTS "
        "FOR ALL OF THEM.**\n\n"
        "    module      dead   raise on every trace   abstain\n"
        "    k1-dcfsm       6              6              0\n"
        "    c1-i2c        36             28              8\n\n"
        "Every raiser on i2c carries one message:\n\n"
        "    TypeError: sequence() missing 1 required keyword-only argument: 'strong'\n\n"
        "and on k1 the same defect in `eventually`. This is the failure the "
        "package already has on record -- 'h2-i2c is on record with 22 of 96 "
        "frozen oracles dying that way', and '26 of a reported 31% convicts "
        "golden rate was checks that never executed'.\n\n"
        "**AND THE GATE THAT CATCHES IT ALREADY SHIPS -- IT JUST POSTDATES EVERY "
        "RECORDED RUN.** `c124dde`, '`strong` is required outright, and the "
        "omission is caught before replay', landed 2026-09-07; a2-i2c, c1-i2c, "
        "d1-i2c and k1-dcfsm were frozen 2026-08-27 to 09-03. So this is a "
        "STALE-ARTIFACT finding, not a live pipeline defect: no run since has "
        "been able to freeze one of these. Re-running the frozen "
        "sets through TODAY's `well_formed`:\n\n"
        "    module      TRUSTED   rejected now   of which dead   live checks lost\n"
        "    k1-dcfsm         36          6            6 of  6          **0**\n"
        "    c1-i2c          110         33           33 of 36          **0**\n\n"
        "It rejects 39 of the 42 dead and **not one check that decides**. So "
        "Step 1's bar -- dead fraction under 10% on both modules -- is cleared "
        "by a static gate that exists, with no model call, no new blocking leg "
        "and no repair round: i2c 32.7% -> 2.7%, k1 16.7% -> 0%.\n\n"
        "**WHAT THE FIRST VERSION GOT RIGHT AND WRONG.** Right: staging is the "
        "wrong owner, and more so than argued -- it mints STIMULUS for a check "
        "that cannot run. Right: the rise test at "
        "`oracles_stage.py:2814-2834` is unusable, because "
        "`reachability.waiting_on` returns `[]` without probes and every run "
        "contract declares none. **Wrong: 'they have moving evidence and stay "
        "silent anyway, an author defect for the repair round.'** They do have "
        "moving evidence and it is irrelevant, because they never look at it. "
        "The owner is a static gate, not an authoring round.\n\n"
        "**THE REAL RESIDUE IS SMALL AND IS THE HONEST TARGET.** After "
        "`well_formed`, 3 checks on i2c and 0 on k1 decide nothing. That -- not "
        "a third of the corpus -- is what a decides-nowhere leg would be for.\n\n"
        "**AND IT RE-READS EVERY FROZEN FIGURE.** c1-i2c's '110 TRUSTED' is 77 "
        "checks the current static gate would admit; 30% of a frozen set is "
        "rejected by the pipeline's own screen. Audit figures are unaffected -- "
        "every audit here already skips `broken` verdicts -- but span and "
        "corpus-size figures over these sets are counting checks that do not "
        "run."
    )


def liveness_is_measured_against_the_witness_and_is_wrong_on_both_modules() -> str:
    """STEP 0. Recompute liveness from the POPULATION's traces and cross-tab it
    against the verdict each run actually shipped.

    Pre-registered before either module was scored: if the two agree within a
    few points on BOTH modules, i2c's false-live rate is a module artifact and
    the dead-check work is unnecessary. They do not agree on either.
    """
    return (
        "**A THIRD OF A TRUSTED SET DECIDES NOTHING, AND THE INSTRUMENT THAT "
        "SHOULD CATCH IT IS WRONG ON BOTH MODULES.**\n\n"
        "    module      said LIVE   false-live   dead on pop   its recall\n"
        "    k1-dcfsm         32        *12.5%*        16.7%         33.3%\n"
        "    c1-i2c          101        *28.7%*        32.7%         19.4%\n\n"
        "*false-live* is the share of checks the run called LIVE that decide "
        "nothing on ANY design of an independently written population; *recall* "
        "is the share of the genuinely dead the run caught.\n\n"
        "**THE CAUSE IS THE EVIDENCE, NOT THE THRESHOLD.** `liveness_of` "
        "replays the WITNESS -- a second reading of the same requirements by "
        "the same author -- and perturbs its recorded rows. A check can be "
        "moved there and be unmovable on every real design, and nothing in the "
        "stack ever looks at a second design: variants are the witness with one "
        "method swapped, and liveness perturbs the witness's own trace.\n\n"
        "**AND THE ONLY BLOCKING LEG CANNOT SEE THIS CLASS AT ALL.** "
        "`liveness.py:300-326` routes 'never decided anywhere' to `UNKNOWN` "
        "deliberately -- calling it a scenario finding rather than a defect -- "
        "while `oracles_stage.py:1406-1411` blocks on `DEAD_ORACLE` only. The "
        "dead-weight class is not mis-thresholded; it is structurally outside "
        "the gate.\n\n"
        "**THE POPULATION IS WHAT MAKES THIS MEASURABLE, AND IT IS FREE.** The "
        "same N traces that selection needs also give liveness a real answer, "
        "so a population is one artifact with two uses and this one does not "
        "depend on the selection rule working."
    )


def effective_size_measured_clone_distance_not_shared_dissent() -> str:
    """F3 found this LIVE, on the module it was meant to replicate onto.

    `characterise` clustered on the off-majority SIGNATURE while its own
    rationale quoted PAIR DISTANCES. On k1 the two agree, so the substitution
    was invisible for as long as k1 was the only population.
    """
    return (
        "**`effective_size` REPORTED 1 FOR FIVE DESIGNS THAT DISAGREE WITH EACH "
        "OTHER EVERYWHERE.** i2c's population, authored independently from the "
        "specification, has these pair distances:\n\n"
        "    d0-d2  65.6%     d2-d3  44.4%\n"
        "    d0-d1  58.6%     d1-d4  37.2%\n"
        "    d0-d3  58.6%     d3-d4  37.2%\n"
        "    d2-d4  48.9%     d0-d4  36.6%\n"
        "    d1-d2  46.5%     d1-d3   6.0%\n\n"
        "Only `d1-d3` is under the 25% clone threshold, so the answer is four "
        "clusters. The committed code returned **one**.\n\n"
        "**THE CAUSE: TWO DIFFERENT METRICS, ONE RATIONALE.** The clustering "
        "distance was `len(off_majority[a] ^ off_majority[b]) / testpoints` -- "
        "how differently two designs dissent FROM THE MAJORITY -- while the "
        "comment beside it cited k1's B/D/E/H merging at 6.3-16%, which are "
        "PAIR distances from the population survey. Being off the majority at "
        "the same testpoints is not being the same design: d0 and d2 dissent "
        "at largely the same places and disagree with each other on 65.6% of "
        "them, their signatures nearly coincide, and single-link chaining then "
        "swallowed all five.\n\n"
        "**WHY k1 DID NOT SHOW IT.** On k1 the two metrics agree, and the fixed "
        "code reproduces k1's recorded structure exactly -- effective size 4, "
        "clusters {B, D, E, H} / {C} / {F} / {G}, which is the one-per-cluster "
        "set the survey recorded. A second module is the only thing that could "
        "separate them, which is precisely what F3 was for.\n\n"
        "**AND THE GUARD THAT SHOULD HAVE CAUGHT IT DID NOT EXIST.** Thirty-"
        "seven population tests passed against both metrics, because every one "
        "of them used a population where the two coincide. The test that "
        "separates them is four designs where two share an off-majority "
        "signature and differ from each other at every testpoint; it fails "
        "against the old metric and passes against the new."
    )


def refuse_unusable_population(shape: PopulationShape, *,
                               max_dissent_share: float = 0.5,
                               min_effective: int = MIN_POPULATION) -> None:
    """**B2's GATE, not its report.** Refuse to select over a population whose
    structure invalidates the rule.

    Two conditions, both measured rather than supposed:

    **ONE DESIGN'S DISSENT DOMINATES.** k1's G is off-majority at 78% of split
    cells, and every subset auditing at exactly zero contains it -- so the
    rule's precision there is that design rather than the population's
    agreement. Above `max_dissent_share` the conviction count is measuring the
    outlier.

    **THE EFFECTIVE SIZE IS BELOW THE FLOOR.** `MIN_POPULATION` counts designs;
    five near-clones are one opinion five times. The floor belongs on the
    cluster-collapsed count, which is what this checks.
    """
    worst = max(shape.dissent, key=lambda d: shape.dissent[d])
    if shape.dissent[worst] > max_dissent_share:
        raise ValueError(
            f"design {worst} is off the population majority at "
            f"{shape.dissent[worst]:.0%} of split testpoints, above "
            f"{max_dissent_share:.0%}: a conviction count over this population "
            "measures that design rather than the population's agreement, and "
            "on k1 exactly this shape produced a 126-for-126 that fell to 6.2% "
            "when the outlier left")
    effective = shape.effective_size()
    if effective < min_effective:
        raise ValueError(
            f"{len(shape.designs)} designs collapse to {effective} distinct "
            f"opinion(s), below {min_effective}: headcount is not what buys "
            "precision, spread is")


def tells(objections: ObjectionMap, shape: PopulationShape) -> TellProfile:
    """Every tell the conviction matrix carries, for one check.

    **THERE IS NO REFERENCE PARAMETER AND THERE MUST NEVER BE ONE.** These are
    selection-side instruments; the audit is computed afterwards from a set that
    is already built.
    """
    hit = {d: set(objections.get(d, ())) for d in shape.designs}
    convicted = [d for d in shape.designs if hit[d]]
    mass = sum(len(hit[d]) for d in shape.designs)
    cells = len(shape.designs) * len(shape.testpoints)

    agreed = shape.agreed
    at_agreed = sum(1 for d in shape.designs for tp in hit[d] if tp in agreed)

    one = both = 0
    for tp, prs in shape.pairs.items():
        for a, b in prs:
            ha, hb = tp in hit.get(a, ()), tp in hit.get(b, ())
            if ha and hb:
                both += 1
            elif ha or hb:
                one += 1

    if mass:
        shares = [len(hit[d]) / mass for d in convicted]
        entropy = -sum(p * _log(p) for p in shares if p > 0)
        ceiling = _log(len(shape.designs))
        concentration = 1.0 - entropy / ceiling if ceiling else 1.0
    else:
        concentration = 0.0

    spoke = {tp for d in shape.designs for tp in hit[d]}
    n_split = len(shape.split) or 1
    n_agreed = len(agreed) or 1
    placement = (len(spoke & shape.split) / n_split
                 - len(spoke - shape.split) / n_agreed)

    return TellProfile(
        count=len(convicted),
        mass=mass / cells if cells else 0.0,
        split_purity=at_agreed / mass if mass else 0.0,
        indiscriminacy=both / (one + both) if (one + both) else 0.0,
        dissent_weighted=sum(1.0 - shape.dissent[d] for d in convicted),
        cluster_count=len({shape.cluster[d] for d in convicted}),
        concentration=concentration,
        placement=placement,
    )


def the_conviction_matrix_carries_one_signal_not_nine() -> str:
    """P3/P4/P5, run over 464 bodies, 7 designs and 5,656 disagreement cells.

    Nine tells were enumerated, three had numbers, six had never been computed.
    The question was whether the matrix holds several independent readings. It
    does not.
    """
    return (
        "**EVERY TELL THAT PREDICTS CONVICTING THE REFERENCE IS THE CONVICTION "
        "COUNT WEARING A DIFFERENT NAME, AND THE TWO THAT ARE GENUINELY "
        "INDEPENDENT OF IT CARRY NO SIGNAL AT ALL.**\n\n"
        "Spearman against the count, on t=6's 201 checks:\n\n"
        "    dissent_weighted  +0.997      split_purity    +0.124\n"
        "    cluster_count     +0.988      port_targeting  +0.045\n"
        "    mass              +0.977\n"
        "    placement         +0.934\n"
        "    concentration     +0.870\n"
        "    indiscriminacy    +0.779\n\n"
        "and the two on the right -- the only two under 0.2 -- flag 5 of 38 and "
        "11 of 38 reference-convicting checks where chance is 7.2.\n\n"
        "**THE DECIDING TEST IS WITHIN A STRATUM, NOT ACROSS ONE.** Between "
        "conviction counts every tell tracks the count, because a check that "
        "objects more objects more. Holding the count fixed and asking each "
        "tell to sort that stratum's reference-convicting checks into its "
        "suspicious half: pooled over the strata with at least 12 members "
        "(count 0, 1, 2 and 6), every tell lands **14 to 19 of 33 where chance "
        "is 16.5.** Nothing separates.\n\n"
        "**THE TWO RE-WEIGHTINGS DESIGNED TO CORRECT FOR THE OUTLIER DO NOT.** "
        "`dissent_weighted` and `cluster_count` exist because k1's population "
        "is dominated by one design at 78% dissent. At matched size they score "
        "16 of 38 and 20 of 38 against the plain count's 18; McNemar on the "
        "discordant picks gives p = 0.727. Counting the outlier less does not "
        "buy precision.\n\n"
        "**COMPOSITION (P4) AND A MODEL (P5) BOTH FAIL THEIR PRE-REGISTERED "
        "BARS.** Best pairwise composition, with a floor of 10 flagged checks, "
        "is 3.82x (indiscriminacy AND placement, 13 of 18) against a best "
        "single of 3.48x -- an improvement inside the noise of an 18-check "
        "sample. A leave-one-REQUIREMENT-out logistic over all nine features "
        "reaches **3.06x (22 of 38), permutation p = 0.005 against 200 "
        "relabellings** -- real signal, below the 3.35x bar it had to beat, and "
        "beaten by a single feature. At N = 13 it scores 8 where the bare "
        "count scores 11.\n\n"
        "**WHAT THIS DOES NOT ESTABLISH.** The stratum test has 33 positives "
        "spread over three usable strata; it can refute a large second signal "
        "and cannot exclude a modest one. And every figure is one module's "
        "population -- F3 is what would tell a rule from an accident."
    )


def two_tells_were_pre_registered_backwards() -> str:
    """Three defects in the P3 instrument, each caught by a number that was
    impossible rather than merely disappointing.

    Recorded because all three produce a clean-looking result, and two of them
    produce a result in the RIGHT direction for the thing being argued.
    """
    return (
        "**DEFECT ONE: A ZERO THAT WAS THE INSTRUMENT, NOT THE TELL.** "
        "`concentration` and `placement` were pre-registered with their "
        "suspicious side on the LOW end and both scored **0 of 38** where "
        "chance is 7.2 -- a binomial p of 0.0003 in the wrong tail, which is "
        "signal pointing the other way rather than no signal. Reversed they "
        "score 18 and 25 of 38. For `concentration` the reason is a confound "
        "worth keeping in the docstring: a check objecting to nothing has no "
        "mass, hence no entropy, hence concentration zero, so the low side "
        "selects the SILENT checks, which are sound by silence and audit "
        "perfectly for the worst available reason.\n\n"
        "**DEFECT TWO: THE RANKS WERE NOT DETERMINISTIC.** "
        "`sorted(set_of_keys, key=...)` breaks ties in set-iteration order, "
        "which Python randomises per process. The conviction count is an "
        "integer 0..6 over 201 checks, so a matched-size cut at N = 38 lands "
        "inside a tie block -- **4 of 18 checks tied at count 2, and 33 of 42 "
        "tied for `cluster_count`** -- and the same data gave 19 hits in one "
        "run and 20 in the next. Every rank now carries the key as a second "
        "sort term and every tie block straddling the cut is printed.\n\n"
        "**DEFECT THREE: A COMPOSITION RANKING WITH NO SIZE FLOOR.** Ranking "
        "pairs by the better of union and intersection precision promoted "
        "intersections of **2 to 4 checks reading 1.00 precision, printed as "
        "5.29x** -- the same illusion as the recorded 2.64x on 2 of 2. A floor "
        "of 10 removes 18 of them and the best honest composition is 3.82x.\n\n"
        "**AND ONE TELL IS STRUCTURALLY ZERO WHERE IT WAS BEING MEASURED.** "
        "`split_purity` asks whether a check objects where the population is "
        "unanimous -- but objecting where all seven agree convicts all seven, "
        "so such a check has count 7 and every `t < 7` set has already "
        "excluded it. **198 of t=6's 201 read exactly 0.** It is not a weak "
        "tell inside a threshold set; it is not a tell there at all.\n\n"
        "**AND A FOURTH DEFECT IN THE INSTRUMENT THAT CHECKS THE INSTRUMENTS.** "
        "The mutation harness reported the `placement` sign mutant as "
        "SURVIVING. It had not: that mutation reorders two terms and is "
        "therefore **byte-identical in length**, CPython invalidates a cached "
        "`.pyc` on (mtime, size), and a restore-then-mutate cycle completing "
        "inside one second matches both. The stale bytecode ran and the test "
        "passed. Run directly the same test fails in 0.04s. The harness now "
        "clears `__pycache__` and runs with bytecode off -- and the episode is "
        "recorded because a mutation harness that silently reuses the "
        "unmutated code reports every test as worthless in exactly the cases "
        "where the mutation was smallest."
    )
