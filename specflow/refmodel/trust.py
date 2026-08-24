"""What an oracle is decided and projected with.

This was the screening module -- three gates run over the judge's oracles the
moment it returned, before any debug attempt was spent on them. Screening now
belongs to `specflow/oracles_stage.py`, which runs before the reference model
exists rather than inside the loop repairing it, and mutation adequacy belongs
to `refmodel/adequacy.py`, which runs after that loop converges rather than
during it. Both moved for the same measured reason: a gate that re-runs against
a design being edited gives an answer that moves with the design.

What is left here is the shared machinery neither of them should re-derive --
deciding one oracle across every testpoint it names, and projecting a trace onto
the ports one clause is about.
"""

from __future__ import annotations


from .oracles import (
    OracleResult,
    RequirementOracle,
    decide_all,
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
    """One testpoint's steps -- the first this oracle names that has any.

    Still one, and only used where one is the right number: the sensitivity
    sweep needs a single scenario to mutate against, and running the whole
    mutant set once per named testpoint would multiply the most expensive gate
    for evidence that saturates after the first.

    Gate 1 and gate 3 use `_decide_over` instead. They ask whether the ORACLE
    holds, and an oracle that names three testpoints is making a claim about all
    three.
    """
    for tp in oracle.tp_uids:
        steps = stimulus_by_tp.get(tp)
        if steps:
            return steps
    return []


def _decide_over(
    oracle: RequirementOracle,
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    transactional: bool = False,
) -> OracleResult:
    """Decide one oracle across EVERY testpoint it names that has stimulus.

    Screening used to decide against the first named testpoint alone, so an
    oracle unexercised on TP-A and satisfied on TP-B was discarded having never
    been replayed on TP-B. Measured on `f-i2c` r0 that explained none of the
    residue -- 26 of the 30 discarded oracles name exactly one testpoint, so
    "first named" was "only named" -- but it is a real defect for the ones that
    name more, and it is the difference between screening asking the question
    the oracle actually poses and asking a narrower one.

    Testpoints with NO recorded stimulus are skipped rather than reported as
    broken. `decide_all` reports them, correctly for its own purpose, and
    `_worst` ranks broken first -- so routing through it unchanged would let one
    stimulus-less testpoint discard an oracle whose other testpoints decide it
    perfectly well. That is the same poisoning `_steps_for` already tolerates by
    skipping, and the tolerance is worth keeping.
    """
    named = [tp for tp in oracle.tp_uids if stimulus_by_tp.get(tp)]
    if not named:
        return OracleResult(
            oracle.req_uid, ok=False,
            broken="no stimulus recorded for any testpoint it names")
    scoped = oracle.model_copy(update={"tp_uids": named})
    return decide_all([scoped], source, contract, stimulus_by_tp, base=base,
                      transactional=transactional)[0]


def failing(results: list[OracleResult]) -> list[OracleResult]:
    """The oracles a session still has to satisfy. Broken ones do not count."""
    return [r for r in results if r.failed()]
