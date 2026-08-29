"""Decide the frozen oracle set against a SIMULATED DUT, not a Python model.

Nothing here samples anything. `Env._record` (`tb/runtime.py:689`) already
captures, per clock edge, the DUT's outputs, the reference model's outputs, the
step index and the stimulus in force; `Env.finish` (`:856`) already writes them
to `{tp_uid}.trace.json`. That file IS the row shape an oracle decides over --
`{"edge", "inputs", "outputs"}` -- with the two sides' outputs under different
keys. This module is the reshape, and the guard that has to come with it.

WHY IT IS WORTH HAVING. Every check the pipeline writes has only ever been
decided against a Python reference model. The same frozen set pointed at real
RTL answers a question no instrument here has asked: does a check written from
the specification hold on a design that is known to be correct? A check the
GOLDEN RTL fails is over-strict, and that is a defect in the check, discovered
without a model in the loop and without a single model call.

SAMPLING AGREES ON BOTH SIDES, WHICH IS WHAT MAKES THIS SOUND. `oracles.replay`
records outputs after `model.step()`; `Env` samples after `RisingEdge` plus
`Timer(1, "step")` (`tb/runtime.py:591`), one simulator time step, deliberately,
because a read in the same delta as the edge returns the previous cycle's value.
Both are post-edge, so a check does not silently mean something different
depending on which side it is decided against. (SVA samples PREPONED, i.e.
before the edge -- see `docs/sva-divergence.md`, D10. That difference matters
only if these checks are ever emitted as real SVA.)
"""

from __future__ import annotations

import json
from pathlib import Path

from .oracles import (OracleResult, RequirementOracle, _worst, decide,
                      ports_read, transactional_view)

#: The two sides `{tp_uid}.trace.json` carries per edge. `dut` is the simulated
#: design; `model` is the reference model the runtime advanced in lockstep, and
#: deciding against it reproduces what `replay` would have said -- which is what
#: makes a DUT-versus-model comparison on one trace an apples-to-apples one.
SIDES = ("dut", "model")


def rows_from(trace: dict, *, side: str = "dut") -> list[dict]:
    """One recorded trace -> the row list an oracle decides over.

    A pure reshape: `{"edge", "inputs", <side>}` becomes
    `{"edge", "inputs", "outputs"}`. Nothing is dropped, recomputed or
    inferred, because anything this function invented would be a fact about the
    adapter rather than about the design.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    return [
        {"edge": e["edge"],
         "inputs": dict(e.get("inputs") or {}),
         "outputs": dict(e.get(side) or {})}
        for e in trace.get("edges") or []
    ]


def load(path: Path | str, *, side: str = "dut") -> list[dict]:
    """`rows_from` over a `{tp_uid}.trace.json` on disk."""
    return rows_from(json.loads(Path(path).read_text(encoding="utf-8")),
                     side=side)


def unknown_ports(rows: list[dict]) -> dict[str, int]:
    """Ports carrying a value that is not an integer, and how many rows do.

    TWO DIFFERENT UNKNOWNS ARRIVE THE SAME WAY and both must stop a conviction.
    `Env.sample` (`tb/runtime.py:603`) returns `None` for a port the design does
    not expose, and `_plain` (`:254`) falls through every int conversion and
    returns `str(value)` for anything else -- which is how a 4-state X reaches
    here, as the string `'xxxx'` rather than a number.

    Either way `row["outputs"][port] == 1` is False, so a check reading that
    port CONVICTS THE DESIGN FOR A VALUE IT COULD NOT COMPARE. That is the
    failure `oracles.decide`'s tri-state exists to prevent, arriving from the
    trace side instead of the stimulus side.

    MEASURED, AND LATENT UNDER VERILATOR. On a full golden i2c run all 25,864
    DUT cells were integers: Verilator is 2-state by default, so X does not
    appear. This guard is for the missing-port case, which is real today, and
    for a 4-state simulator, which is not what this repo runs. It is cheap and
    it is not doing nothing -- but its X half has never fired, and should not be
    reported as if it had.
    """
    bad: dict[str, int] = {}
    for row in rows:
        for port, value in (row.get("outputs") or {}).items():
            if not isinstance(value, int) or isinstance(value, bool):
                bad[port] = bad.get(port, 0) + 1
    return bad


def decide_rtl(
    oracles: list[RequirementOracle],
    traces_by_tp: dict[str, dict],
    contract: dict,
    *,
    side: str = "dut",
    transactional: bool = True,
) -> list[OracleResult]:
    """Decide every oracle over recorded traces instead of a replayed model.

    The counterpart of `decide_all`, and deliberately the same shape: one
    `OracleResult` per requirement, folded across its testpoints by the same
    `_worst`, so a verdict here means exactly what a verdict there means.

    A CONVICTION THAT RESTS ON AN UNKNOWN VALUE IS DOWNGRADED TO AN ABSTENTION,
    and only a conviction is. A `False` from an oracle reading a port the trace
    could not resolve is not evidence about the design; a `True` needs no
    rescuing, and a `None` is already an abstention. The downgrade is scoped by
    `ports_read`, so an oracle reading only resolved ports keeps its `False`
    even when some other port in the same trace is unknown -- the alternative
    silences a whole testpoint because one signal the check never mentions was
    missing.
    """
    out: list[OracleResult] = []
    for oracle in oracles:
        reads = ports_read(oracle, contract)
        results: list[OracleResult] = []
        for tp in oracle.tp_uids:
            trace = traces_by_tp.get(tp)
            if trace is None:
                results.append(OracleResult(
                    oracle.req_uid, ok=None,
                    detail=f"{tp} produced no trace, so it decided nothing"))
                continue
            rows = rows_from(trace, side=side)
            if transactional:
                rows = transactional_view(rows)
            result = decide(oracle, rows)
            blind = {p: n for p, n in unknown_ports(rows).items() if p in reads}
            if result.ok is False and not result.broken and blind:
                named = ", ".join(f"{p} on {n} row(s)" for p, n in sorted(blind.items()))
                result = OracleResult(
                    oracle.req_uid, ok=None, edge=result.edge, rows=rows,
                    detail=(f"the check failed, but the trace could not resolve "
                            f"{named} -- so this is not evidence about the "
                            f"design. Original detail: {result.detail}"))
            results.append(result)
        out.append(_worst(oracle.req_uid, results))
    return out


def load_traces(results_dir: Path | str) -> dict[str, dict]:
    """Every `{tp_uid}.trace.json` a suite run wrote, keyed by tp_uid."""
    out: dict[str, dict] = {}
    for path in sorted(Path(results_dir).glob("*.trace.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        uid = data.get("tp_uid") or path.name.split(".")[0]
        out[uid] = data
    return out
