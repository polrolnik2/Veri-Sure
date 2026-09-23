"""THE TRIPLE, COMPUTED BY THE RUN THAT EARNED IT.

Every span, blindness and audit figure on this branch was taken afterwards, by
a driver, against inputs the driver chose -- which is how a run came to be
scored against a contract that was not the one in force, and against a
nine-design yardstick that predates the probes 82 of its 96 checks read. A
number a run cannot produce about itself is a number nobody can reproduce.

So this is a stage. It reads the artifacts the run already wrote, it is pure
replay and set arithmetic, and it writes `scorecard.json` beside them.

    span        TRUSTED checks / requirements that state an OBSERVABLE
                obligation.
    blindness   disagreement cells no accepted check separates, at
                `(testpoint, pair)` resolution, over the run's own population.
    audit       accepted checks that convict the control / accepted checks the
                control can judge.

**THE DENOMINATOR FOR SPAN IS NOT THE MINTED COUNT, AND THE REASON IS
MECHANICAL.** `normalize` returns `observable: []` together with an
`unobservable_reason` for a span of specification text that states no boundary
effect -- "This span is scaffolding rather than a standalone requirement", "the
statement specifies no port behavior". On the probe run that is 16 of 151, and
ALL SIXTEEN were abandoned: not one carried a check, and none ever could. A
suite is not less complete for failing to check a heading. Dividing by them
reports the spec's typography as a verification gap.

It is normalize's own evidence and not a classifier's label, which is why it is
the rule here rather than `unit_kind == "scaffolding"`: that label disagrees
with the evidence on 4 of 151 (three scaffolding units did carry a check, and
one interface unit had no observable).

**THE CONTROL IS READ HERE AND NOWHERE ELSE.** `audit_control` is a separate
parameter from `refmodel_control` precisely so that the non-leak is structural:
this module has no author, no prompt and no repair path, and nothing it
computes is returned to a stage that could act on it. A control may REJECT an
oracle and may never REPAIR one; here it does not even reject, it only scores.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import probes as P
from . import variety as V
from .refmodel.compose import choose_base
from .refmodel.oracle_gen import RequirementOracle
from .refmodel.oracles import decide, replay, transactional_view

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scorecard:
    """What a run claims about itself, with every denominator named.

    Rates are `None` rather than 0.0 when the denominator is empty. A run with
    no control has no audit figure, and reporting 0.0% there is the class of
    number this tree has retracted twice.
    """

    requirements_minted: int = 0
    requirements_observable: int = 0
    requirements_behavioural: int = 0
    trusted: int = 0
    span: float | None = None

    cells: int = 0
    blind: int = 0
    blindness: float | None = None
    population: int = 0

    control_judges: int = 0
    control_convicted_by: int = 0
    audit: float | None = None

    effective_size: int = 0
    accepted_designs: int = 0
    notes: list[str] = field(default_factory=list)

    def meets(self, *, span: float, blindness: float, audit: float) -> bool:
        """All three at once, with an absent figure counting as NOT met.

        A target is a conjunction and is reported as one: two of the three is
        the shape of every claim this project has had to withdraw.
        """
        return (self.span is not None and self.span > span
                and self.blindness is not None and self.blindness < blindness
                and self.audit is not None and self.audit <= audit)


def _rows_for(source: str, contract: dict, stimulus_by_tp: dict, *,
              base: str, transactional: bool) -> tuple[dict, tuple[str, ...]]:
    """`(testpoint -> rows, probes this design does not declare)`."""
    rows: dict[str, list] = {}
    absent: tuple[str, ...] = ()
    for tp, steps in (stimulus_by_tp or {}).items():
        if not steps:
            continue
        try:
            rep = replay(source, contract, steps, base=base)
        except Exception as exc:  # noqa: BLE001
            logger.info("scorecard: replay failed at %s (%r)", tp, exc)
            continue
        if rep.error:
            continue
        rows[tp] = list(transactional_view(rep.rows) if transactional
                        else rep.rows)
        absent = tuple(rep.unavailable)
    return rows, absent


def _verdicts(oracles: dict, rows: dict, absent: tuple[str, ...]) -> dict:
    """`uid -> testpoint -> verdict` for one design. Abstentions left out."""
    out: dict[str, dict[str, bool]] = {}
    for uid, oracle in oracles.items():
        per: dict[str, bool] = {}
        for tp, trace in rows.items():
            try:
                v = decide(oracle, trace, unavailable=absent)
            except Exception:  # noqa: BLE001
                continue
            if not v.broken and v.ok is not None:
                per[tp] = v.ok
        out[uid] = per
    return out


def score(*, oracles: list[dict], normalized: list[dict] | dict,
          stimulus_by_tp: dict, contract: dict, population: list[str],
          requirements: list[dict] | None = None,
          audit_control: str | None = None,
          transactional: bool = True) -> Scorecard:
    """The triple, from artifacts a completed run wrote. No model calls."""
    forms = (list(normalized.values()) if isinstance(normalized, dict)
             else list(normalized or []))
    minted = len(forms)
    observable = {str(f.get("req_uid")) for f in forms
                  if (f.get("observable") or [])}
    #: **THE DENOMINATOR IS THE BEHAVIOURAL REQUIREMENTS.** S1 classifies each
    #: authorial unit it mints, and only one of the three kinds is a claim
    #: about behaviour a check could ever decide. On this module's own run:
    #: 120 behavioural, 19 scaffolding, 9 interface, and 119 of the 120
    #: behavioural ones carry an observable port while all but one of the
    #: others do not.
    #:
    #: Scaffolding is a heading or a list marker -- normalize returns
    #: `observable: []` for it with "This span is scaffolding rather than a
    #: standalone requirement" -- and an interface unit states what ports the
    #: module declares, which the contract already fixes. A suite is not less
    #: complete for failing to check either, and dividing by them reports the
    #: specification's typography as a verification gap.
    #:
    #: `observable != []` is kept and reported beside it: it is normalize's own
    #: evidence rather than a classifier's label, and where the two disagree a
    #: reader can see it.
    behavioural = {str(r.get("uid")) for r in (requirements or [])
                   if r.get("unit_kind") == "behavioural"}
    denominator = behavioural or observable
    notes: list[str] = []
    if not behavioural and requirements:
        notes.append("no requirement is classified `behavioural`, so span "
                     "falls back to the ones stating an observable obligation")
    elif not requirements:
        notes.append("no requirements were supplied, so span falls back to the "
                     "forms stating an observable obligation rather than to "
                     "the behavioural ones")
    if minted and not observable:
        notes.append("no requirement states an observable obligation, so span "
                     "has no denominator and is reported as absent")

    held = {str(o["req_uid"]): RequirementOracle(
        req_uid=str(o["req_uid"]), tp_uids=list(o.get("tp_uids") or []),
        clause=str(o.get("clause") or ""), source=str(o["source"]))
        for o in (oracles or []) if o.get("source")}
    #: A check for a requirement with no observable is not counted in the
    #: numerator either -- the denominator's rule has to apply to both ends or
    #: it is not a rate. On the probe run this removes nothing: all 16 such
    #: requirements were abandoned.
    counted = {u for u in held if u in denominator}

    base = choose_base(contract)
    outputs = [str(p.get("name")) for p in (contract.get("io") or [])
               if p.get("dir") == "output" and p.get("name")]

    #: **THE STAGE'S OWN INSTRUMENT, NOT A SECOND ONE.** This built its own
    #: replay table and disagreed with the screen that produced the set: the
    #: two differ on a testpoint whose replay reports an error, which this
    #: skipped and `_population_rows` keeps the partial rows of. Measured on
    #: the same artifact: 29,496 cells and 49.1% blind here against 22,315 and
    #: 55.1% there. A scorecard that cannot reproduce the number its own stage
    #: screened against is the defect this module exists to remove, one level
    #: up.
    from .oracles_stage import _population_rows, _population_tables

    rows_by_design = _population_rows(
        list(population or []), contract, stimulus_by_tp, base=base,
        transactional=transactional)
    cells = V.cells(rows_by_design, outputs) if len(rows_by_design) >= 2 else ()
    if len(rows_by_design) < 2:
        notes.append(
            f"{len(rows_by_design)} design(s) replayed: fewer than two is not a "
            f"population, so there are no disagreement cells and blindness is "
            f"reported as absent rather than as 0%")
    #: **A POPULATION THAT AGREES EVERYWHERE IS A BROKEN INPUT, NOT A CLEAN
    #: MEASUREMENT, AND THIS SAID NOTHING.** Two or more designs and zero
    #: disagreement cells is either designs that are identical or a contract
    #: with no outputs. Both are defects upstream; neither is a suite that
    #: cannot be blind.
    #:
    #: Measured on the run that found it: a resumed run replayed ONE recorded
    #: witness for all seven population members and wrote seven byte-identical
    #: files. The card reported `population 7` and `0/0 cells = n/a` on
    #: adjacent lines and remarked on neither, so a span and an audit were
    #: published over an instrument that had silently become a constant.
    #:
    #: The distinct-source count is what names it: 7 designs and 1 distinct
    #: source is a sentence a reader can act on, where "0 cells" is not.
    elif not cells:
        distinct = len({str(src) for src in (population or [])})
        notes.append(
            f"{len(rows_by_design)} design(s) replayed and they disagree "
            f"NOWHERE, which no real population does -- {distinct} distinct "
            f"source(s) among {len(population or ())}, and "
            f"{len(outputs)} declared output(s). Blindness has no denominator "
            f"and is absent; span and audit beside it were computed against "
            f"this same population and should be read as provisional")

    _v, by_tp, _obj = _population_tables(
        held, list(population or []), contract, stimulus_by_tp, base=base,
        transactional=transactional)
    blind = V.blind_at(cells, by_tp) if cells else ()

    #: Distinct VERDICT VECTORS, never a count of checks: "admitting or
    #: authoring more checks is worth nothing if they cluster with the ones
    #: already there."
    effective = len({json.dumps(
        sorted((tp, tuple(sorted(col.items()))) for tp, col in t.items()),
        default=str) for t in by_tp.values() if t})
    accepted = [d for d in sorted(rows_by_design)
                if not any(ok is False for t in by_tp.values()
                           for tp, col in t.items() for n, ok in col.items()
                           if n == d)]

    judges = convicted = 0
    if audit_control:
        crows, cabs = _rows_for(audit_control, contract, stimulus_by_tp,
                                base=base, transactional=transactional)
        for uid, per in _verdicts(
                {u: o for u, o in held.items() if u in counted},
                crows, cabs).items():
            if not per:
                continue
            judges += 1
            if any(ok is False for ok in per.values()):
                convicted += 1
        #: **THE GAP IS THE CONTROL'S, NOT THE CHECKS'.** A probe is a
        #: `dir: "probe"` entry in the contract, so a design is REQUIRED to
        #: expose it. The old note said "the control can judge N of M accepted
        #: checks; the rest name state it does not expose" -- which reports the
        #: control's missing interface as a limit of the CHECK SET. It is the
        #: other way round: the checks name state the contract declares, and
        #: the control predates probes and implements none of it.
        #:
        #: Measured by pointing the frozen set at a module that declares the
        #: contract's ports and ties every output to a constant: 14 pass, 0
        #: FAIL, 108 abstain of 122. A design that does nothing at all,
        #: passing, on exactly this mechanism -- which is why the gap is named
        #: as non-conformance rather than left to read as an abstention.
        declared = P.declared_probes(contract)
        missing = tuple(n for n in declared if n in cabs)
        if missing:
            notes.append(
                f"the control is NOT contract-conformant: {len(missing)} of "
                f"the {len(declared)} declared probe(s) are not exposed by it "
                f"({', '.join(missing[:6])}"
                f"{', ...' if len(missing) > 6 else ''}), so the "
                f"{len(counted) - judges} check(s) reading them can say "
                f"nothing about it")
        if judges < len(counted):
            notes.append(
                f"audit is over the {judges} of {len(counted)} accepted "
                f"check(s) the control can be judged on, and says so rather "
                f"than reporting a rate over a denominator it does not have")
    else:
        notes.append("no control was supplied, so audit is absent, not 0%")

    return Scorecard(
        requirements_minted=minted,
        requirements_observable=len(observable),
        requirements_behavioural=len(behavioural),
        trusted=len(counted),
        span=(len(counted) / len(denominator)) if denominator else None,
        cells=len(cells),
        blind=len(blind),
        blindness=(len(blind) / len(cells)) if cells else None,
        population=len(rows_by_design),
        control_judges=judges,
        control_convicted_by=convicted,
        audit=(convicted / judges) if judges else None,
        effective_size=effective,
        accepted_designs=len(accepted),
        notes=notes,
    )


def write(run_dir: Path, card: Scorecard) -> Path:
    """`scorecard.json`, beside the artifacts it scores."""
    path = Path(run_dir) / "specflow" / "scorecard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(card), indent=2), encoding="utf-8")
    return path


def render(card: Scorecard) -> str:
    """One block, with every denominator visible beside its rate."""
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.1f}%"

    lines = [
        f"SPAN       {card.trusted}/"
        f"{card.requirements_behavioural or card.requirements_observable} "
        f"behavioural = {pct(card.span)}   ({card.requirements_minted} minted, "
        f"{card.requirements_observable} state an observable obligation)",
        f"BLINDNESS  {card.blind}/{card.cells} cells = {pct(card.blindness)}   "
        f"(population {card.population}, effective_size {card.effective_size})",
        f"AUDIT      {card.control_convicted_by}/{card.control_judges} "
        f"judgeable = {pct(card.audit)}",
        f"ACCEPTS    {card.accepted_designs} of {card.population} design(s)",
    ]
    lines += [f"  note: {n}" for n in card.notes]
    return "\n".join(lines)
