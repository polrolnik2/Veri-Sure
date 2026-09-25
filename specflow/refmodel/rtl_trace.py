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

SAMPLING AGREES ON BOTH SIDES, WHICH IS WHAT MAKES THIS SOUND, and the model's
form decides which side of the edge both read on. A model written as
`outputs` + `advance` (`RefModel.outputs`) is sampled the way SVA samples,
PREPONED: `oracles.replay` records `outputs()` before `advance()`, and `Env`
reads the DUT after its inputs settle and before the `RisingEdge`
(`Env._edge`). A model written as one `step` keeps the older post-edge
recording on both sides: after `model.step()`, and after `RisingEdge` plus
`Timer(1, "step")`. Every trace says which in its `sampling` field, so a check
does not silently mean something different depending on which side it is
decided against. See `docs/sva-divergence.md`, D10.
"""

from __future__ import annotations

import json
from dataclasses import replace
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


def over_width_ports(rows: list[dict], contract: dict) -> dict[str, int]:
    """Ports whose recorded value does not FIT the width the contract declares.

    **THE THIRD WAY A VALUE ARRIVES UNCOMPARABLE, AND THE ONLY ONE THAT LOOKS
    LIKE A NUMBER.** `unknown_ports` catches a missing port (`None`) and a
    4-state X (a string). This catches a perfectly good integer that is the
    wrong QUANTITY: the contract declares `fscl` a 1-bit flag, golden binds a
    3-bit filter register of the same name, and `row["outputs"]["fscl"] == 1` is
    then False for six of its eight values. The check convicts a correct design
    for a comparison that was never about the same thing.

    MEASURED on golden i2c under `full2`'s own stimulus -- five of the sixteen
    probes that bind exceed their declared width:

        cscl  csda        declared 1, observed 0..3   two-stage synchronizers
        fscl  fsda        declared 1, observed 0..7   three-sample histories
        filter_cnt        declared 1, observed 0..3   the filter counter

    and nineteen ports stay inside their declaration, so this is not a blanket
    objection to the contract's widths -- it is five named quantities.

    and REQ-0102's verdict reads "expected (1, 1), observed (3, 3)" -- the whole
    failure, printed, in a check nobody wrote wrong.

    THE GUARD ALREADY EXISTED ON THE OTHER PATH. `Env.sample` refuses a sample
    wider than `PROBE_WIDTHS` declares, so the Python reference-model route has
    been protected since the width guard landed; the RTL TRACE route, which is
    the one the audit column is measured on, had nothing. One defect, two paths,
    guarded once.

    A declared width of 0 or a missing one is not a claim, so it is not
    enforced. Booleans are excluded for the same reason `unknown_ports`
    excludes them -- `isinstance(True, int)`.
    """
    widths = {str(e.get("name")): int(e.get("width") or 0)
              for e in (contract.get("io") or []) if e.get("name")}
    bad: dict[str, int] = {}
    for row in rows:
        for port, value in (row.get("outputs") or {}).items():
            w = widths.get(port, 0)
            if w < 1 or isinstance(value, bool) or not isinstance(value, int):
                continue
            if value > (1 << w) - 1 or value < 0:
                bad[port] = bad.get(port, 0) + 1
    return bad


def declared_width_gap(trace: dict, contract: dict) -> dict[str, tuple[int, int]]:
    """Ports the SIMULATOR reported wider than the contract declares.

    **THE ONLY WAY TO CATCH A WIDE REGISTER THAT READS ZERO.**
    `over_width_ports` decides from values, which is everything a trace alone
    could tell -- and a flag that is low and an 18-bit register that is zero are
    the same number. Measured on the known-good i2c design: `idle` is declared
    `width: 1`, is an 18-bit register, reads 0 on every one of 482 testpoints,
    and REQ-0100 convicts the design for `idle` not being 1. No value-based test
    can see that.

    `Env.finish` now records `len(handle)` per sampled signal into the trace's
    `widths` map, so the fact is available where the verdict is computed. A trace
    without one predates this and yields nothing, which is the same answer
    `unknown_ports` gives for a trace predating `stimulus_digest`: unverifiable
    and verified are different facts.

    Returns `port -> (declared, sampled)`.
    """
    widths = trace.get("widths")
    if not isinstance(widths, dict):
        return {}
    declared = {str(e.get("name")): int(e.get("width") or 0)
                for e in (contract.get("io") or []) if e.get("name")}
    out: dict[str, tuple[int, int]] = {}
    for port, sampled in widths.items():
        d = declared.get(str(port), 0)
        try:
            got = int(sampled)
        except (TypeError, ValueError):
            continue
        if d >= 1 and got > d:
            out[str(port)] = (d, got)
    return out


def check_stimulus(traces_by_tp: dict[str, dict],
                   stimulus_by_tp: dict[str, list]) -> dict[str, str]:
    """Which testpoints' traces were NOT driven by the stimulus given.

    Returns `tp_uid -> what disagrees`, empty when everything matches. A
    testpoint present in only one of the two is reported, because a trace set
    that is missing half the scenarios is the other way this goes wrong.

    THE FAILURE THIS EXISTS FOR IS SILENT. Both `traces_by_tp` and
    `stimulus_by_tp` are keyed by `tp_uid`, and uids are minted per requirement
    rather than per run -- so scoring one run's oracles against a trace set
    rendered from a different run's stimulus succeeds, folds cleanly, and
    produces a conviction rate about a scenario the oracles were never written
    for. It cost a full analysis to find, and it left no evidence at all in the
    verdicts it produced.

    A trace with no `stimulus_digest` predates the fingerprint and cannot be
    checked; that is reported as its own reason rather than passed silently,
    because "unverifiable" and "verified" are different facts.
    """
    from ..tb.runtime import stimulus_digest

    out: dict[str, str] = {}
    for uid in sorted(set(traces_by_tp) | set(stimulus_by_tp)):
        trace, steps = traces_by_tp.get(uid), stimulus_by_tp.get(uid)
        if trace is None:
            out[uid] = "the stimulus names this testpoint; no trace was recorded"
        elif steps is None:
            out[uid] = "a trace exists for a testpoint this stimulus does not name"
        elif not trace.get("stimulus_digest"):
            out[uid] = ("the trace carries no stimulus_digest, so it predates "
                        "the fingerprint and cannot be matched")
        elif trace["stimulus_digest"] != stimulus_digest(steps):
            out[uid] = (f"driven by different stimulus: the trace records "
                        f"{trace['stimulus_digest']}, this stimulus is "
                        f"{stimulus_digest(steps)}")
    return out


def decide_rtl(
    oracles: list[RequirementOracle],
    traces_by_tp: dict[str, dict],
    contract: dict,
    *,
    side: str = "dut",
    transactional: bool = True,
    stimulus_by_tp: dict[str, list] | None = None,
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
    if stimulus_by_tp is not None:
        # RAISES, and deliberately. A verdict computed against the wrong
        # recording is not a weaker measurement, it is a measurement of
        # something else, and every way of reporting it short of refusing to
        # produce it has already been tried and read as a real result.
        wrong = check_stimulus(traces_by_tp, stimulus_by_tp)
        named = {tp for o in oracles for tp in o.tp_uids}
        wrong = {k: v for k, v in wrong.items() if k in named}
        if wrong:
            sample = "; ".join(f"{k}: {v}" for k, v in list(wrong.items())[:3])
            raise ValueError(
                f"{len(wrong)} of the {len(named)} testpoint(s) these oracles "
                f"name were not recorded from this stimulus -- {sample}"
                + (" ..." if len(wrong) > 3 else ""))

    #: **WIDTH IS A PROPERTY OF THE DESIGN, NOT OF ONE TESTPOINT, SO IT IS
    #: DECIDED ONCE OVER THE WHOLE RECORDING.** A 3-bit `fscl` reads 0 or 1 on
    #: plenty of testpoints and 0..7 on others. Asking per testpoint would make
    #: the same check abstain where the register happened to go high and convict
    #: where it happened not to -- a verdict that depends on the stimulus rather
    #: than on whether the quantity is comparable at all. One value above the
    #: declared width anywhere proves the signal is wider than declared for this
    #: design, and it is refused everywhere.
    wide_anywhere: dict[str, int] = {}
    for _t in traces_by_tp.values():
        for _p, _n in over_width_ports(rows_from(_t, side=side), contract).items():
            wide_anywhere[_p] = wide_anywhere.get(_p, 0) + _n
        #: **AND BY DECLARATION, WHERE THE TRACE RECORDS WHAT THE SIMULATOR
        #: REPORTED.** A wide register reading 0 is invisible to the value test
        #: above -- `idle` on the known-good i2c design is 18 bits, declared 1,
        #: and reads 0 on all 482 testpoints. Counted as every row of that trace,
        #: because the whole recording of that port is the wrong quantity rather
        #: than some rows of it.
        _n_rows = len(_t.get("edges") or [])
        for _p in declared_width_gap(_t, contract):
            wide_anywhere[_p] = wide_anywhere.get(_p, 0) + _n_rows

    out: list[OracleResult] = []
    #: **EVERY RECORDED TRACE, NOT THE ONES `tp_uids` NAMES -- AND THIS HAD TO
    #: MOVE WITH THE STAGE'S SCOPE OR NEITHER SHOULD HAVE MOVED.** The oracle
    #: stage screens a check by replaying it wherever the stimulus goes,
    #: because a cell at TP-0400 can only be separated by a check replayed at
    #: TP-0400 -- blindness 97% -> 12.8% on the probe run's own designs. If the
    #: suite that ships then ran each check on the two testpoints its testplan
    #: entry happens to name, the stage would be rejecting checks as
    #: over-strict for firing where the product never asks them: span paid for
    #: a number the product does not have.
    #:
    #: The reverse is the worse half. A check screened narrowly and shipped
    #: wide convicts a correct design somewhere nothing looked, which is the
    #: audit failure this pipeline exists to avoid.
    #:
    #: A check decides where its activation holds and abstains elsewhere; that
    #: is what `ok=None` is for, and it is a fact about the trace where
    #: `covers` is a model's opinion about relevance.
    scope = sorted(traces_by_tp)
    for oracle in oracles:
        reads = ports_read(oracle, contract)
        results: list[OracleResult] = []
        #: Still reported per NAMED testpoint: `render_suite` emits a test for
        #: it, so a named testpoint that produced no trace is a hole in the
        #: recording and not an abstention.
        for tp in oracle.tp_uids:
            if traces_by_tp.get(tp) is None:
                results.append(OracleResult(
                    oracle.req_uid, ok=None, tp_uid=tp,
                    detail=f"{tp} produced no trace, so it decided nothing"))
        for tp in scope:
            trace = traces_by_tp.get(tp)
            if trace is None:
                continue
            rows = rows_from(trace, side=side)
            if transactional:
                rows = transactional_view(rows)
            result = decide(oracle, rows)
            blind = {p: n for p, n in unknown_ports(rows).items() if p in reads}
            #: **A VALUE OF THE WRONG WIDTH IS AS UNCOMPARABLE AS A MISSING
            #: ONE**, and it is the case that looks like data -- see
            #: `over_width_ports`. Folded in here rather than into `rows_from`,
            #: which is a pure reshape and must stay one: anything it invented
            #: would be a fact about the adapter.
            wide = {p: n for p, n in wide_anywhere.items() if p in reads}
            if result.ok is False and not result.broken and (blind or wide):
                why = []
                if blind:
                    why.append("could not resolve " + ", ".join(
                        f"{p} on {n} row(s)" for p, n in sorted(blind.items())))
                if wide:
                    why.append("recorded " + ", ".join(
                        f"{p} wider than its declared width on {n} row(s)"
                        for p, n in sorted(wide.items())))
                result = OracleResult(
                    oracle.req_uid, ok=None, edge=result.edge, rows=rows,
                    detail=(f"the check failed, but the trace "
                            f"{' and '.join(why)} -- so this is not evidence "
                            f"about the design. Original detail: "
                            f"{result.detail}"))
            # WHICH testpoint's trace produced this. `decide` judges a row list
            # and has no idea where it came from, so without stamping it here
            # `_worst` folds several testpoints into one result that cannot say
            # which one it is about -- and a caller wanting the recording behind
            # a conviction (`explain`, every waveform tool) has to show all of
            # them or guess.
            results.append(replace(result, tp_uid=tp))
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
