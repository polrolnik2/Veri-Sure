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

An oracle failing a gate is DISCARDED, never repaired. Its requirement keeps its
blocking verdict and falls back to prose for that turn. Repairing an oracle
would mean deciding which of the judge and the oracle was right, which is the
judgement the loop exists to avoid making silently.
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

    def rates(self) -> dict[str, int]:
        """Four counts, each accusing something different.

        `malformed`/`disagreed` say the judge does not mean what it says;
        `convicted` says it demands nothing; `over_strict` says it demands too
        much; a high `unknown` says the STIMULUS is too thin to qualify oracles
        at all -- a finding about the testplan, not about the judge.
        """
        reasons = list(self.discarded.values())
        return {
            "trusted": len(self.trusted),
            "malformed": sum(1 for r in reasons if r.startswith("malformed:")),
            "disagreed": sum(1 for r in reasons if r.startswith("disagreed:")),
            "convicted": sum(1 for r in reasons if r.startswith("vacuous:")),
            "over_strict": sum(1 for r in reasons if r.startswith("over-strict:")),
            "unknown": sum(1 for v in self.sensitivity.values() if v == UNKNOWN),
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
        if not decide(oracle, run.rows).ok:
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
        expected_pass = verdicts.get(uid) == "met"
        if result.ok != expected_pass:
            discarded[uid] = (
                f"disagreed: its author said {verdicts.get(uid)!r} but the oracle "
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
            if not verdict.ok:
                discarded[uid] = (
                    f"over-strict: the known-good control fails it"
                    f"{' at edge ' + str(verdict.edge) if verdict.edge is not None else ''}"
                    f" -- {verdict.detail}"
                )
                continue

        # -- gate 2: an oracle that already fails is firing; only test passers.
        if result.ok:
            level, detail = sensitivity(
                oracle, source, contract, stimulus_by_tp, base=base, limit=limit)
            sens[uid] = level
            if level == CONVICTED:
                discarded[uid] = f"vacuous: {detail}"
                continue
        else:
            sens[uid] = SENSITIVE

        trusted.append(oracle)

    return Screened(trusted=trusted, discarded=discarded, sensitivity=sens)


def failing(results: list[OracleResult]) -> list[OracleResult]:
    """The oracles a session still has to satisfy. Broken ones do not count."""
    return [r for r in results if not r.ok and not r.broken]
