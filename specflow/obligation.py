"""Did the stimulus ever stage the situation a requirement is about?

Today that question is answered by the ORACLE, which reports `ok=None` when its
clause's scenario never occurs (`oracles.decide`). On `f-i2c` r0 that was 30 of
67 oracles, and it is the pipeline's dominant failure -- but it is also the
oracle testifying about itself, which is the thing under suspicion. An oracle
that names the wrong testpoints and an oracle whose testpoints genuinely stage
nothing produce the same report.

This asks the same question from the other side, and never consults the oracle.
The inputs are the requirement's `activation` (from `normalize.py`) and the
testpoints S2 attached to it via `covers` -- a claim made before any oracle
existed. So a disagreement between this and the oracle is informative, which is
the entire point of computing it separately.

**Three outcomes, because two would lie.** How much can be established depends
on what kind of activation the requirement has:

* an **input-only** activation ("cmd is WRITE and ena is 1") is decidable
  outright, by reading the stimulus steps. No model, no replay, no doubt.
* a **state-dependent** activation ("while the FSM is idle", "after arbitration
  is lost") has no machine-readable predicate -- `activation.text` is prose. It
  cannot be confirmed. It CAN be refuted: if no port the requirement is about
  ever moves during the whole replay, the scenario did not occur, whatever the
  prose says. That is a necessary condition, checked against the model rather
  than against the oracle.
* everything else is UNKNOWN, and saying so is the point. A gate that reported
  "fired" because it could not prove otherwise would be the vacuous-oracle
  disease one level up, and this codebase already refuses that trade in
  `trust.sensitivity` (UNKNOWN over convicted) and in `scenario_trace` (a short
  timeout is not a defect).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import NormalizedRequirement
from .tb.runtime import is_reset_step, normalise_step

#: The three outcomes. UNKNOWN is not a soft NOT_FIRED: collapsing them would
#: read a prose activation as a thin testplan.
FIRED, NOT_FIRED, UNKNOWN = "fired", "not_fired", "unknown"


@dataclass(frozen=True)
class Obligation:
    """One requirement's activation, rendered as something checkable."""

    req_uid: str
    text: str
    #: input port -> required value. Empty means state-dependent.
    inputs: dict[str, int] = field(default_factory=dict)
    #: The ports the requirement is about, used for the refutation leg.
    observable: tuple[str, ...] = ()

    @property
    def decidable(self) -> bool:
        """Whether this can be CONFIRMED, as opposed to only refuted."""
        return bool(self.inputs)


@dataclass(frozen=True)
class Check:
    req_uid: str
    tp_uid: str
    status: str
    detail: str = ""


def obligations(normalized: list[NormalizedRequirement]) -> list[Obligation]:
    """One per requirement that has a boundary observable.

    An UNOBSERVABLE requirement gets none. There is nothing to stage: no
    stimulus can make an internal counter visible, so asking whether the
    stimulus staged it would report a stimulus defect for a specification one.
    """
    return [
        Obligation(
            req_uid=n.req_uid,
            text=n.activation.text,
            inputs=dict(n.activation.inputs or {}),
            observable=tuple(n.observable),
        )
        for n in normalized
        if n.req_uid and not n.unobservable
    ]


def _driven_values(steps: list[dict]) -> dict[str, set[int]]:
    """Every value each input is actually driven to across a step list.

    Reset steps drive nothing -- the runtime owns the pins and sequences them on
    both sides (`testcase_agent.py:440-449`) -- so they contribute no values,
    but they are not skipped silently either: see `_reset_asserted`.
    """
    out: dict[str, set[int]] = {}
    for raw in steps:
        if is_reset_step(raw):
            continue
        inputs, _hold, _until, _timeout = normalise_step(raw)
        for name, value in inputs.items():
            try:
                out.setdefault(str(name), set()).add(int(value))
            except (TypeError, ValueError):
                continue
    return out


def _reset_asserted(steps: list[dict]) -> bool:
    return any(is_reset_step(raw) for raw in steps)


def _moves(rows: list[dict], ports: tuple[str, ...]) -> bool:
    """Do any of these output ports change value across the replay?

    The refutation leg. Deliberately weak in one direction only: movement does
    not prove the scenario occurred, but its absence proves it did not, because
    a requirement about an output that never moves cannot have been exercised.
    """
    if not ports or not rows:
        return False
    first = {p: rows[0]["outputs"].get(p) for p in ports}
    return any(
        row["outputs"].get(p) != first[p]
        for row in rows for p in ports
    )


def check_static(
    ob: Obligation, steps: list[dict], *,
    reset_ports: frozenset[str] | dict[str, int] = frozenset(),
) -> Check | None:
    """Decide an input-only obligation from the steps alone. No model.

    Returns None when the obligation is not input-only, so a caller can tell
    "this stimulus does not stage it" from "this cannot be answered here".

    A reset port at its ACTIVE value is satisfied by a reset step rather than by
    a driven value, because reset is not drivable -- the runtime sequences it on
    both sides at once, which is why `_drivable` excludes it.

    A reset port at its IDLE value needs NOTHING. "while not in reset" is the
    state every trace starts in and stays in unless a reset step says otherwise,
    so requiring a step for it demands the opposite of what the requirement
    asks. This used to fire on any value at all, and on a2-i2c it sent five
    requirements -- REQ-0021, 0043, 0079, 0086, 0087 -- chasing a reset step
    none of them wanted: every complaint was `nReset=1` or `rst=0`, the inactive
    levels, while the functional values they actually needed were never the
    miss. Two of the five eventually added the step, satisfied this check, and
    still abstained, so the diagnosis had been pointing away from the cause the
    whole time. A signal that aims a retry at the wrong thing is worse than no
    signal.

    `reset_ports` may be a plain set of names, or -- from
    `ports.asserted_resets` -- a mapping of name to the value that ASSERTS it.
    Membership works either way; only the mapping form can tell an asserted
    reset from an idle one, so a caller that supplies a set keeps the old
    all-values behaviour and is no worse off than before.
    """
    if not ob.decidable:
        return None
    driven = _driven_values(steps)
    active = reset_ports if isinstance(reset_ports, dict) else {}
    missing: list[str] = []
    for name, want in ob.inputs.items():
        if name in reset_ports:
            wants_asserted = want == active.get(name, want)
            if wants_asserted and not _reset_asserted(steps):
                missing.append(f"{name}={want} (no reset step)")
            continue
        if want not in driven.get(name, set()):
            seen = sorted(driven.get(name, set()))
            missing.append(f"{name}={want} (driven: {seen or 'never'})")
    if missing:
        return Check(ob.req_uid, "", NOT_FIRED,
                     f"the stimulus never drives {'; '.join(missing)}")
    return Check(ob.req_uid, "", FIRED,
                 f"the stimulus drives {ob.inputs}")


def check_replay(ob: Obligation, rows: list[dict]) -> Check:
    """Refute a state-dependent obligation, or admit it cannot be decided.

    Never returns FIRED. Movement on the observable ports is a necessary
    condition for the scenario, not a sufficient one, and reporting it as
    sufficient would let a testpoint that merely wiggles an output count as
    having staged a specific case.
    """
    if not _moves(rows, ob.observable):
        return Check(ob.req_uid, "", NOT_FIRED,
                     f"none of {list(ob.observable)} moves anywhere in this "
                     f"replay, so the requirement's own behaviour never occurs")
    return Check(ob.req_uid, "", UNKNOWN,
                 f"{list(ob.observable)} move, but the activation "
                 f"({ob.text!r}) is about design state and has no "
                 f"machine-readable form, so firing cannot be confirmed")


def worst(checks: list[Check]) -> str:
    """One status per requirement, over the testpoints attached to it.

    FIRED anywhere wins: a requirement staged by one of its testpoints is
    staged, whatever the others could not do. UNKNOWN beats NOT_FIRED, because
    a testpoint that might have staged it is not evidence that nothing did --
    the same reasoning `_worst` (`oracles.py:373`) applies one level down, and
    the same reason `trust.sensitivity` reports UNKNOWN rather than convicting.
    """
    if not checks:
        return UNKNOWN
    seen = {c.status for c in checks}
    if FIRED in seen:
        return FIRED
    if UNKNOWN in seen:
        return UNKNOWN
    return NOT_FIRED


def by_requirement(testplan: list[dict]) -> dict[str, list[str]]:
    """`req_uid -> tp_uids`, from S2's `covers` rather than from any oracle.

    This is what makes the obligation check independent of the judge: `covers`
    was written before any oracle existed, so a disagreement between the two is
    evidence rather than a tautology. `covers` holds "REQ-0007@1"; the revision
    is not part of the key (`judge.py:780-784` does the same).
    """
    out: dict[str, list[str]] = {}
    for tp in testplan or []:
        uid = str(tp.get("uid") or "")
        if not uid:
            continue
        for ref in tp.get("covers") or []:
            out.setdefault(str(ref).split("@", 1)[0], []).append(uid)
    return out


def report(
    *,
    obligations_: list[Obligation],
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    replay_rows: dict[str, list[dict]] | None = None,
    reset_ports: frozenset[str] | dict[str, int] = frozenset(),
) -> dict:
    """Every obligation checked against the testpoints S2 attached to it.

    `replay_rows` is `tp_uid -> trace rows`, supplied by the caller because it
    already has them: `_debug_turns` replays every testpoint for
    `stimulus_liveness` (`compose.py:346`), and replaying them again here would
    double the cost of a turn for no new information. Absent it, only the
    input-only obligations are decided and the rest report UNKNOWN -- which is
    the correct answer for a caller with no model in hand.
    """
    attached = by_requirement(testplan)
    per_req: dict[str, str] = {}
    details: dict[str, list[dict]] = {}

    for ob in obligations_:
        checks: list[Check] = []
        for tp in attached.get(ob.req_uid, []):
            steps = stimulus_by_tp.get(tp)
            if not steps:
                continue
            static = check_static(ob, steps, reset_ports=reset_ports)
            if static is not None:
                checks.append(Check(ob.req_uid, tp, static.status, static.detail))
                continue
            rows = (replay_rows or {}).get(tp)
            if rows is None:
                checks.append(Check(ob.req_uid, tp, UNKNOWN,
                                    "no replay available for this testpoint"))
                continue
            dynamic = check_replay(ob, rows)
            checks.append(Check(ob.req_uid, tp, dynamic.status, dynamic.detail))
        per_req[ob.req_uid] = worst(checks)
        details[ob.req_uid] = [
            {"tp_uid": c.tp_uid, "status": c.status, "detail": c.detail}
            for c in checks
        ]

    counts = {FIRED: 0, NOT_FIRED: 0, UNKNOWN: 0}
    for status in per_req.values():
        counts[status] = counts.get(status, 0) + 1
    return {
        "counts": counts,
        # Reported apart because it bounds what this gate can ever say: a run
        # where most activations are prose is a run where most of the answer is
        # UNKNOWN, and that is a finding about normalization, not about the
        # stimulus.
        "decidable": sum(1 for o in obligations_ if o.decidable),
        "total": len(obligations_),
        "by_requirement": per_req,
        "checks": details,
    }
