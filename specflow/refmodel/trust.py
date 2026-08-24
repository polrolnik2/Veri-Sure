"""Whether a requirement oracle has earned the right to drive a repair loop.

An oracle is generated code and gets no more benefit of the doubt than the model
does. Three gates, all offline, all cheap, all run the moment the judge returns
and before any debug attempt is spent:

1. **Agreement** -- the oracle reproduces its own author's verdict on the very
   model that verdict was about.
2. **Sensitivity** -- mutate the model and check the oracle fires. An oracle
   that passes everything demands nothing.
3. **Not over-strict** -- a known-good control model must satisfy it.

Gate 2 is the one that generalises: it needs no golden RTL and no control, so it
is the only evidence available on a design where nothing known-good exists.

An oracle failing a gate is discarded from THIS screening and, where the failure
is one the judge can settle, recorded in `conflicts` for a reconcile call. It is
never silently rewritten here: repairing an oracle in the harness would mean
deciding which of the judge and the oracle was right, which is the judgement the
loop exists to avoid making on its own. Asking its author is not that.

Every gate produces a reconcilable conflict, because every one of them is the
same kind of finding. The oracle is the judge's verdict written executably, so
an oracle that contradicts that verdict (gate 1), that cannot see its own
scenario, that no correct implementation satisfies (gate 3), or that nothing
could ever fail (gate 2) is the judge misstating its own belief. Discarding it
without asking leaves the requirement blocking and hands the reference model a
prose failure caused by the check rather than by the model -- which is the
reference model being blamed for the judge's mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import mutate_model
from .oracles import (
    OracleResult,
    RequirementOracle,
    decide,
    ports_read,
    replay,
    well_formed,
)

#: Mutants tried per oracle. Bounded because this runs per oracle per turn -- 77
#: of them on i2c_master_bit_ctrl -- and the evidence saturates quickly: an
#: oracle that survives eight in-scope mutants is not going to be convicted by a
#: ninth.
MUTANT_LIMIT = 8

#: In-scope mutants required before an oracle may be convicted of vacuity.
#: One is not evidence: a mutant can change the projection and still satisfy a
#: perfectly good oracle -- flip `k == 3` to `k != 3` and an "ack pulses" oracle
#: is MORE satisfied, not less. Convicting on that single observation discards
#: sound oracles. Below this, the honest answer is UNKNOWN.
MIN_IN_SCOPE = 3

#: Gate-2 outcomes. UNKNOWN is not a discard, and keeping it distinct from
#: CONVICTED is the whole point: collapsing them reads a thin stimulus as a bad
#: judge.
SENSITIVE = "sensitive"
CONVICTED = "convicted"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Screened:
    """What survived, and an accusation for everything that did not."""

    trusted: list[RequirementOracle] = field(default_factory=list)
    #: req_uid -> why it was discarded.
    discarded: dict[str, str] = field(default_factory=dict)
    #: req_uid -> SENSITIVE | CONVICTED | UNKNOWN, for every oracle gate 2 ran on.
    sensitivity: dict[str, str] = field(default_factory=dict)
    #: req_uid -> what the disagreement WAS, in enough detail for the judge to
    #: settle it. Separate from `discarded` because a disagreement is the one
    #: failure that is worth another call: the oracle is the verdict written
    #: executably, so the two disagreeing means the translation is wrong, not
    #: that the oracle is untrustworthy in itself.
    conflicts: dict[str, str] = field(default_factory=dict)
    #: req_uid -> why gate 3 had nothing to say: the control never reaches this
    #: clause's scenario either. NOT a discard and NOT over-strictness -- it is
    #: the stimulus that is thin, and saying otherwise blames the oracle for it.
    unexercised: dict[str, str] = field(default_factory=dict)
    #: req_uid -> whether the oracle PASSED the model, for every oracle that
    #: reached the end of screening. `screen` already computes this at gate 1
    #: and used to throw it away, so a caller wanting to know which trusted
    #: oracles currently fail had to replay everything a second time.
    decisions: dict[str, bool] = field(default_factory=dict)
    #: Whether gate 3 ran at all -- i.e. whether a control model was supplied.
    #: Recorded because without it `over_strict: 0` is unreadable, and reads as
    #: the reassuring half of an ambiguity it has no right to.
    control_available: bool = False

    def rates(self) -> dict[str, int | None]:
        """Five counts, each accusing something different.

        `malformed`/`disagreed` say the judge does not mean what it says;
        `convicted` says it demands nothing; `over_strict` says it demands too
        much; a high `unknown` says the STIMULUS is too thin to qualify oracles
        at all -- a finding about the testplan, not about the judge.

        `over_strict` is None, never 0, when no control was supplied. The
        distinction is not pedantic: on the a-i2c run it reported 0 with the
        gate switched off, and the true figure measured afterwards was 22 of 54.
        Ten of the eighteen oracles that run's debug agent failed to discharge
        were ones no correct model could satisfy, and a 0 in this field is what
        made that look like the agent's failure rather than the gate's absence.
        """
        reasons = list(self.discarded.values())
        return {
            "trusted": len(self.trusted),
            "malformed": sum(1 for r in reasons if r.startswith("malformed:")),
            "disagreed": sum(1 for r in reasons if r.startswith("disagreed:")),
            "convicted": sum(1 for r in reasons if r.startswith("vacuous:")),
            "over_strict": (
                sum(1 for r in reasons if r.startswith("over-strict:"))
                if self.control_available else None
            ),
            "unknown": sum(1 for v in self.sensitivity.values() if v == UNKNOWN),
            #: The oracle's own scenario never occurred in the stimulus it
            #: named -- a testplan finding, counted apart from every gate.
            "unexercised": sum(1 for r in reasons if r.startswith("unexercised:")),
            "control_unexercised": len(self.unexercised),
        }


def _project(rows: list[dict], ports: set[str]) -> tuple:
    """The trace reduced to what one clause is about.

    Comparing whole traces would count any mutant that changed anything, so an
    oracle watching `cmd_ack` would be convicted for staying silent when a
    divider was mutated. Convicting it there would push oracles toward watching
    everything, which gate 3 then punishes as over-strict -- the two gates would
    pull in opposite directions and no oracle could satisfy both.
    """
    return tuple(
        tuple(sorted((p, row["outputs"].get(p)) for p in ports))
        for row in rows
    )


def _steps_for(oracle: RequirementOracle, stimulus_by_tp: dict) -> list[dict]:
    """One testpoint's steps -- the first this oracle names that has any."""
    for tp in oracle.tp_uids:
        steps = stimulus_by_tp.get(tp)
        if steps:
            return steps
    return []


def sensitivity(
    oracle: RequirementOracle,
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    limit: int = MUTANT_LIMIT,
) -> tuple[str, str]:
    """`(verdict, detail)` -- does this oracle fire when the model goes wrong?

    Only meaningful for an oracle that currently PASSES. One that already fails
    the model has demonstrated it fires, so it is sensitive by construction and
    no mutant needs to be built to prove it.

    Two filters keep the gate honest, and they exclude different things:

    * sites are restricted to lines this stimulus actually EXECUTES, so a mutant
      the scenario could never reach is never proposed;
    * a mutant counts only if it changes the trace PROJECTED onto the ports this
      oracle reads, so one that changes behaviour this clause is not about is
      dropped.

    The second subsumes the equivalent-mutant problem `qualify.py` names for G8
    -- an equivalent mutant changes no projection at all.
    """
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps:
        return UNKNOWN, "no stimulus to mutate against"

    ports = ports_read(oracle, contract)
    if not ports:
        return UNKNOWN, "the oracle reads no declared port"

    baseline = replay(source, contract, steps, base=base)
    if baseline.error:
        return UNKNOWN, f"the model {baseline.error}"
    reference = _project(baseline.rows, ports)

    lines = mutate_model.executed_lines(source, contract, steps, base=base)
    in_scope = 0
    for mutant in mutate_model.mutants(source, lines=lines, limit=limit):
        run = replay(mutant.source, contract, steps, base=base)
        if run.error:
            # A mutant that breaks the model outright tests nothing about the
            # oracle -- every oracle "fails" a model that will not run.
            continue
        if _project(run.rows, ports) == reference:
            continue                      # invisible to this clause: not evidence
        in_scope += 1
        if decide(oracle, run.rows).failed():
            return SENSITIVE, f"killed by {mutant.description}"
    if in_scope < MIN_IN_SCOPE:
        return UNKNOWN, (
            f"only {in_scope} mutant(s) changed anything this oracle can see; "
            f"{MIN_IN_SCOPE} are needed before silence means vacuity"
        )
    return CONVICTED, f"passed all {in_scope} mutants it could observe"


def screen(
    oracles: list[RequirementOracle],
    verdicts: dict[str, str],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    testplan: list[dict],
    *,
    base: str,
    control_source: str | None = None,
    limit: int = MUTANT_LIMIT,
) -> Screened:
    """Run the three gates over a whole turn's oracles.

    Ordered by cost, cheapest first, so an oracle rejected on book-keeping never
    pays for a mutation sweep: well-formedness is static, agreement and
    over-strictness are one replay each, sensitivity is up to `limit` replays.
    """
    trusted: list[RequirementOracle] = []
    discarded: dict[str, str] = {}
    sens: dict[str, str] = {}
    conflicts: dict[str, str] = {}
    unexercised: dict[str, str] = {}
    decisions: dict[str, bool] = {}

    for oracle in oracles:
        uid = oracle.req_uid

        why = well_formed(oracle, contract, testplan)
        if why:
            discarded[uid] = f"malformed: {why}"
            continue

        steps = _steps_for(oracle, stimulus_by_tp)
        if not steps:
            discarded[uid] = "malformed: no stimulus recorded for any testpoint it names"
            continue

        run = replay(source, contract, steps, base=base)
        if run.error:
            discarded[uid] = f"malformed: the model {run.error}"
            continue
        result = decide(oracle, run.rows)
        if result.broken:
            discarded[uid] = f"malformed: {result.broken}"
            continue

        # -- gate 1: does it reproduce the verdict it shipped with?
        #
        # An oracle that cannot SEE its scenario is a third outcome, and it
        # disagrees with any verdict at all: a judge that called a requirement
        # met or not_met claimed to have observed something its own check then
        # could not find. That is worth a reconcile call, not a discard -- most
        # often the tp_uids are wrong, which the judge can fix.
        said = verdicts.get(uid)
        expected_pass = said == "met"
        if result.unexercised():
            conflicts[uid] = (
                f"You judged this {said!r}, but your oracle reports that its "
                f"scenario never occurs in the stimulus for {oracle.tp_uids}: "
                f"{result.detail or '(no detail)'}. Either it names the wrong "
                f"testpoints, or the verdict was not based on this trace."
            )
            discarded[uid] = (
                f"unexercised: its author said {said!r} but the oracle's "
                f"scenario never occurs in the stimulus it named"
            )
            continue
        if result.ok != expected_pass:
            where = f" at edge {result.edge}" if result.edge is not None else ""
            conflicts[uid] = (
                f"You judged this {said!r}. Your oracle "
                f"{'PASSES' if result.ok else 'FAILS'} the same model"
                f"{where}: {result.detail or '(no detail)'}"
            )
            discarded[uid] = (
                f"disagreed: its author said {said!r} but the oracle "
                f"{'passes' if result.ok else 'fails'} that same model"
            )
            continue

        # -- gate 3: a known-good model must satisfy it.
        if control_source is not None:
            ctl = replay(control_source, contract, steps, base=base)
            if ctl.error:
                discarded[uid] = f"malformed: the control {ctl.error}"
                continue
            verdict = decide(oracle, ctl.rows)
            if verdict.broken:
                discarded[uid] = f"malformed: {verdict.broken}"
                continue
            if verdict.unexercised():
                # The control never reaches this clause's situation either, so
                # the gate has nothing to say. Reported, not discarded -- the
                # same call gate 2 makes with UNKNOWN, and for the same reason.
                unexercised[uid] = (
                    f"the control never reaches this clause's scenario: "
                    f"{verdict.detail}"
                )
            elif verdict.failed():
                where = (f" at edge {verdict.edge}"
                         if verdict.edge is not None else "")
                discarded[uid] = (
                    f"over-strict: the known-good control fails it{where}"
                    f" -- {verdict.detail}"
                )
                # Reconcilable, like a gate-1 disagreement and for the same
                # reason: the oracle is this verdict written executably, so an
                # oracle no correct implementation can satisfy is the judge
                # misstating its own belief. Discarding it silently leaves the
                # requirement blocking and hands the reference model a prose
                # failure caused by the check rather than by the model.
                conflicts[uid] = (
                    f"Your oracle FAILS a KNOWN-GOOD reference implementation of "
                    f"this design{where}: {verdict.detail or '(no detail)'}. A "
                    f"correct design does not do what you are demanding, so the "
                    f"demand is wrong -- you are testing an implementation detail, "
                    f"an exact timing the spec does not fix, or a signal this "
                    f"clause is not about."
                )
                continue

        # -- gate 2: an oracle that already fails is firing; only test passers.
        if result.ok:
            level, detail = sensitivity(
                oracle, source, contract, stimulus_by_tp, base=base, limit=limit)
            sens[uid] = level
            if level == CONVICTED:
                discarded[uid] = f"vacuous: {detail}"
                conflicts[uid] = (
                    f"Your oracle is VACUOUS: {detail}. It passes models that "
                    f"are provably wrong, so it cannot tell a correct design "
                    f"from a broken one and proves nothing about this "
                    f"requirement. Check the specific behaviour the clause "
                    f"states, at the edge it states it."
                )
                continue
        else:
            sens[uid] = SENSITIVE

        decisions[uid] = bool(result.ok)
        trusted.append(oracle)

    return Screened(trusted=trusted, discarded=discarded, sensitivity=sens,
                    conflicts=conflicts, unexercised=unexercised,
                    decisions=decisions, control_available=control_source is not None)


def failing(results: list[OracleResult]) -> list[OracleResult]:
    """The oracles a session still has to satisfy. Broken ones do not count."""
    return [r for r in results if r.failed()]
