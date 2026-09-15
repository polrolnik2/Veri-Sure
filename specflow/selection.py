"""Build a check set by SELECTION over a corpus, reading no reference design.

WHAT THIS REPLACES, AND WHY. A set can be assembled two ways. The oracle stage
assembles one by DISPOSITION: each check is authored, gated, repaired up to five
times, staged, and whatever ends `TRUSTED` is the set. This module assembles one
by SELECTION: author a corpus once, then keep the checks a mechanical rule keeps.

The difference is not stylistic, it is variance. Disposition rates measured over
six runs of this pipeline span 3.3x -- 86.6% down to 26.1% -- and the whole
spread is present within ONE module, so it is run-to-run variance in the repair
and staging loops rather than difficulty of the design. Selection has no loop:
given a corpus and a population it is a pure function, and it returns the same
set every time. That is the property this module exists to supply.

**AND DISPOSITION IS NOT A QUALITY MEASURE ANYWAY, WHICH IS THE SHARPER
REASON.** Of one run's 33 production-`TRUSTED` behavioural checks, 18 convict a
design that satisfies the specification once they are decided suite-wide, and 11
of those 18 were hidden by the stage scoring each check only on the testpoints
its testplan named. `TRUSTED` is what the loop concluded; it is not what the
check does.

THE RULE, AND IT IS ONE KNOB.

    keep a check that DECIDES on the population and convicts at most `t` of it

Measured over 464 bodies against seven independently written spec-derived
designs, with the reference consulted only afterwards:

    the check convicts   checks   convict the reference
    0 of 7                 126      0 =   0.0%
    1 to 6 of 7             75     38 =  50.7%
    7 of 7                 263    261 =  99.2%

**EXACT AT BOTH ENDS AND A COIN FLIP IN BETWEEN.** At `t = 0` the rule predicts
soundness 126 times out of 126 without reading the reference, which is the
strongest golden-free result on this corpus. The set it builds spans 55 of 87
requirements = 63%, audits at zero, and objects 11 times to a design held out of
the seven that selected it -- sound AND discriminating on an unseen design, from
a rule that read no reference.

**AND `t = 0` SELECTS FOR BLINDNESS, WHICH IS THE SAME PREDICATE READ TWICE.**
A check convicting none of the population is, by the rule's own definition, a
check that does not discriminate on the population. The set at `t = 0` is blind
to 99.8% of the disagreements between spec-derived designs; at `t = 6` blindness
is 40.4% and the audit is 18.9%. Anyone reaching for "tighten `t` to get
soundness AND widen it to get completeness" is reaching for two ends of one
knob. `soundness_and_blindness_are_one_knob` carries the sweep.

WHAT IS STRUCTURAL HERE RATHER THAN ADVISORY.

* **`select` takes no reference.** There is no parameter that could carry one.
  That is the same structural guarantee `oracle_gen.build_prompt` has against
  seeing a design, and it is why an audit cannot leak into a selection by
  accident -- `audit` is a separate function taking a `Selection` that is
  already built.
* **`SOUND` requires the check to DECIDE.** Written as "convicts nothing" the
  predicate is satisfied by a check that never ran, which is sound by silence
  rather than by evidence. Recomputing one headline without this counted an
  extra check that decides 0 testpoints on the reference and 1 on a held-out
  design.
* **A span is reported with its audit or not at all.** `Report` carries both and
  has no accessor for either alone. Nine headlines on this work were retracted
  for quoting reach without its false-reject rate.

WHAT MUST NOT BE ADDED, each measured rather than supposed.

* **Do not add a refutable leg to the selection.** "Drop a check that convicts
  no candidate" discards 21% of the entire measured yield: of 14 sound checks
  that caught a held-out design, three convict none of the population, which is
  the population being RIGHT rather than the check being dead. `refutable` is
  exported for REPORTING and `select` does not call it.
* **Do not use the population's agreed value as an expected value.** At every
  agreement threshold a design wrong on 61% of the suite scores at or below the
  reference, because the population's errors correlate through the ambiguity of
  the specification they were all written from. See `ensemble`.
* **Do not read zero objections as done.** On a set carrying even one check the
  reference fails, zero is proof of NON-equivalence by arithmetic. Stop a loop
  on a trial budget. See `ensemble.zero_objections_can_be_incompatible_with_
  correctness`.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from math import log as _log

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

    def __post_init__(self) -> None:
        if self.max_convictions < 0:
            raise ValueError("max_convictions cannot be negative")
        if self.min_decides < 0:
            raise ValueError("min_decides cannot be negative")


@dataclass(frozen=True)
class Verdict:
    """One check's fate, with everything that decided it."""

    key: str
    kept: bool
    #: How many population members it convicted, and how many it decided on.
    #: `decided` is why a silent check is distinguishable from a sparing one.
    convicts: int = 0
    decided: int = 0
    #: The leg that dropped it: "gate", "silent", "over_strict", or "" if kept.
    reason: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Selection:
    """A set, and the rule that built it. Carries no reference information."""

    ruleset: Ruleset
    verdicts: tuple[Verdict, ...]
    population_size: int

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


def convictions(decide_on: DecideOn, population: Iterable[Rows]) -> tuple[int, int]:
    """`(convicted, decided)` over the population.

    Both halves are returned because a check convicting 0 of 7 and a check
    deciding on none of them are the same number under the rule and different
    facts about the check. `select` uses the second to tell them apart.
    """
    convicted = decided = 0
    for rows in population:
        got = decide_on(rows)
        if got is None:
            continue
        decided += 1
        convicted += bool(got)
    return convicted, decided


def select(
    corpus: Mapping[str, DecideOn],
    population: Sequence[Rows],
    *,
    ruleset: Ruleset | None = None,
    gate: Gate | None = None,
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
    out: list[Verdict] = []
    for key, decide_on in corpus.items():
        if rules.use_gates and gate is not None:
            why = gate(key)
            if why:
                out.append(Verdict(key, False, reason="gate", detail=why))
                continue
        hits, decided = convictions(decide_on, population)
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
        out.append(Verdict(key, True, hits, decided))
    return Selection(rules, tuple(out), len(population))


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
        hits, decided = convictions(decide_on, population)
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
    return tuple(
        select(corpus, population,
               ruleset=replace(base, max_convictions=t), gate=gate)
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
