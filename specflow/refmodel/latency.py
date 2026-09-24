"""A check that asserts a latency the requirement never stated.

**THE SPECIFICATION SAYS "AFTER", AND THE CHECK READS THE SAME ROW.** "busy is
cleared after a STOP condition is detected"; "sto_condition = sSDA & ~dSDA &
sSCL"; "hold clk_en low while slave_wait is asserted". None of these states a
latency, and a design that registers its response -- the response arriving one
clock after the condition that causes it -- implements every one of them
faithfully. A check that reads the response on the very row its condition
occurs admits only the other, zero-latency reading.

Measured on `full2` against the known-good i2c design, with the pipeline's own
rules: REQ-0035 requires `busy` low on the row `sto_condition` rises (golden
clears it one row later); REQ-0051 requires `clk_en` low on the row
`slave_wait` rises (golden, one row later); REQ-0067/0110 require
`sto_condition` on the row its equation first holds (golden registers it).
Every spec-derived population member computes these on the same row -- 13 of 13
START events in all seven -- so no population instrument can see it.

**SO THE TEST IS MECHANICAL AND DESIGN-FREE.** Take a trace the check PASSES on
(any runnable spec-derived design serves, the way `oracle_liveness` uses one),
make the signals the requirement observes arrive ONE CLOCK LATER -- exactly the
trace a registered implementation of the same design would record -- and replay
the check. If it now fails, it rests on a latency the requirement never stated.

Licensed where the requirement states the timing: `licenses_a_cycle_count`
("immediately", "on the next clock", "within N cycles") and the explicit
same-cycle words below. Reads no known-good design and no verdict about one.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .oracles import RequirementOracle, decide, shift_probe, transactional_view
from .temporal import licenses_a_cycle_count

#: Words that DO state a zero-latency relation, beyond a cycle count.
_SAME_CYCLE = re.compile(
    r"\b(asynchronous(ly)?|combinational(ly)?|same (clock|cycle)|"
    r"without (any )?delay|in the same (clock|cycle)|immediately)\b", re.I)

PREFIX = "latency:"


def licensed(requirement_text: str) -> bool:
    """Does the requirement's own sentence state the response's timing?"""
    text = requirement_text or ""
    return licenses_a_cycle_count(text) or bool(_SAME_CYCLE.search(text))


def lagged(raw_rows: list[dict], names: Sequence[str]) -> list[dict]:
    """`raw_rows` with each named output arriving one clock later.

    RAW rows, one per clock edge -- lagging after the transactional view would
    move a value by one distinct STATE, which is not what a register does.
    """
    out = raw_rows
    for name in names:
        out = shift_probe(out, name, -1)
    return out


def observed_names(oracle: RequirementOracle, observable: Sequence[str]) -> list[str]:
    """The requirement's observables that this check actually reads."""
    src = oracle.source or ""
    return [n for n in dict.fromkeys(observable or ())
            if n and re.search(rf"\b{re.escape(str(n))}\b", src)]


def fragile(oracle: RequirementOracle, raw_rows_by_tp: Mapping[str, list[dict]],
            observable: Sequence[str], requirement_text: str, *,
            testpoints: Sequence[str] | None = None,
            transactional: bool = True) -> str:
    """Why this check rests on an unstated latency, or `""` if it does not.

    Replays on `testpoints` (default: the check's own `tp_uids`) only where the
    check PASSES as recorded; a testpoint it fails or abstains on says nothing
    about latency. Never raises.
    """
    if licensed(requirement_text):
        return ""
    names = observed_names(oracle, observable)
    if not names:
        return ""
    view = transactional_view if transactional else (lambda rows: rows)
    for tp in (testpoints if testpoints is not None else oracle.tp_uids):
        raw = raw_rows_by_tp.get(tp)
        if not raw:
            continue
        try:
            if decide(oracle, view(raw)).ok is not True:
                continue
            late = decide(oracle, view(lagged(raw, names)))
        except Exception:  # noqa: BLE001 -- a check that cannot run is another gate's
            continue
        if late.ok is False:
            return (f"{PREFIX} this check passes on {tp} but FAILS when "
                    f"{', '.join(names)} arrive one clock later -- which is "
                    f"exactly what a design that registers "
                    f"{'them' if len(names) > 1 else 'it'} records. The "
                    f"requirement states no latency, so that design is a "
                    f"faithful implementation and the check must not convict "
                    f"it. Do not read the response on the same row as the "
                    f"condition that causes it: open a window on the condition "
                    f"and require the response within it (e.g. `eventually`), "
                    f"or accept it on that row or the next. Late reading: "
                    f"{late.detail}")
    return ""


def refuser(witness: str, contract: dict, stimulus_by_tp: Mapping[str, list],
            normalized_by_uid: Mapping[str, dict], text_by_uid: Mapping[str, str],
            *, base: str, transactional: bool = True):
    """`why(uid, oracle) -> str`: `fragile` against one substrate design.

    The substrate is replayed once per testpoint and cached, because the same
    trace serves every check that names it. `stimulus_by_tp` is read at CALL
    time, so testpoints the stage stages after this was built are replayed when
    first asked for. `None` when there is no substrate to replay.
    """
    if not (witness or "").strip():
        return None
    from .oracles import replay

    cache: dict[str, list] = {}

    def rows(tps):
        out = {}
        for tp in tps:
            if tp not in cache:
                steps = stimulus_by_tp.get(tp)
                try:
                    cache[tp] = (list(replay(witness, contract, steps, base=base).rows)
                                 if steps else [])
                except Exception:  # noqa: BLE001
                    cache[tp] = []
            out[tp] = cache[tp]
        return out

    def why(uid: str, oracle: RequirementOracle) -> str:
        shape = normalized_by_uid.get(uid) or {}
        return fragile(oracle, rows(oracle.tp_uids), shape.get("observable") or [],
                       str(text_by_uid.get(uid) or ""), transactional=transactional)

    return why
