"""What a failing check actually says, and where to look for it.

`focus` and `explain` from the plan's §6.1/§6.2, and the requirement plumbing
both of them stand on.

THE GAP THIS CLOSES. The RTL debug loop never learned which REQUIREMENT a
failing check came from. `req_uid` appeared nowhere in `trace_report.py`,
`sim_reviewer.py` or the editor's report path: the agent got rows reading
`CHK-0000 sda_oen: expected=1 got=0`, the contract, the whole specification as
undifferentiated background, and was then asked to name "the specific contract
requirement that was violated" -- a field it had to guess.

That is B21's failure mode. With names only, the debugger *"invented a timing
theory... rewrote `always_ff` to `always_comb` and broke the contract's 1-cycle
latency."* A requirement reading "when X, then Y within N cycles" is exactly the
datum that makes the theory unnecessary to invent, and it was sitting on disk
unread the whole time.

WHAT IS NOT SYNTHESISED HERE, deliberately. There is no witness replay and no
invented `expected` column. A fabricated expected value would be worse than
none: it would make the debugger CONFIDENT in the theory it currently only
guesses at. The `actual` half comes from the VCD; the `expected` half has no
source in an oracle, and §5.6 item 5 replaces it with a statement about the
CHECK instead -- which perturbation would have satisfied it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .trace_slicer import RtlBlock, build_driver_map, dynamic_slice, parse_rtl_blocks


@dataclass
class RequirementView:
    """One requirement, everything the debugger needs about it, in one place.

    Assembled from artifacts that all already existed and were never joined:
    `requirements.json` for the text, `normalized.json` for the activation and
    the response, `oracles.json` for the frozen check, and the contract for the
    ports that check reads.
    """

    req_uid: str
    text: str = ""
    activation: dict = field(default_factory=dict)
    expectation: str = ""
    clause: str = ""
    source: str = ""
    tp_uids: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)

    def brief(self) -> dict:
        """What the requirement OWES, in the requirement's own words."""
        act = self.activation or {}
        return {
            "req_uid": self.req_uid,
            "requirement": self.text,
            "when": act.get("text") or "",
            "activation_inputs": act.get("inputs") or {},
            "window_closes_on": act.get("until") or [],
            "then": self.expectation,
            "observable_at": self.ports,
        }


def load_requirement_views(run_dir: Path | str, contract: dict) -> dict[str, RequirementView]:
    """Join the four artifacts. Missing ones degrade, never raise.

    A debug loop that cannot read `normalized.json` should lose the activation
    and keep the requirement text, not lose the requirement.
    """
    from specflow.refmodel.oracles import RequirementOracle, ports_read

    run = Path(run_dir)

    def _load(rel: str, key: str | None = None):
        try:
            data = json.loads((run / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if key and isinstance(data, dict):
            return data.get(key) or []
        return data

    views: dict[str, RequirementView] = {}
    for r in _load("specflow/requirements.json", "requirements"):
        uid = str(r.get("uid") or "")
        if uid:
            views[uid] = RequirementView(req_uid=uid, text=str(r.get("text") or ""))
    for n in _load("specflow/normalized.json", "normalized"):
        uid = str(n.get("req_uid") or "")
        v = views.setdefault(uid, RequirementView(req_uid=uid)) if uid else None
        if v is not None:
            v.activation = n.get("activation") or {}
            v.expectation = str(n.get("expectation") or "")
    for o in _load("specflow/oracles.json", "oracles"):
        uid = str(o.get("req_uid") or "")
        if not uid:
            continue
        v = views.setdefault(uid, RequirementView(req_uid=uid))
        v.clause = str(o.get("clause") or "")
        v.source = str(o.get("source") or "")
        v.tp_uids = list(o.get("tp_uids") or [])
        try:
            v.ports = sorted(ports_read(RequirementOracle(
                req_uid=uid, clause=v.clause, source=v.source,
                tp_uids=v.tp_uids), contract))
        except Exception:  # noqa: BLE001
            v.ports = []
    return views


# ------------------------------------------------------------------- focus


def focus_slice(rtl_text: str, ports, *, max_depth: int = 3) -> list[RtlBlock]:
    """The dataflow slice from ONE requirement's ports.

    §6.2(b): the slice's value comes from starting at *the* failing signal, and
    with 43 of 110 requirements failing -- the measured figure against golden
    i2c RTL -- the union of their `ports_read` is most of the port list and
    `dynamic_slice` returns most of the design. Slicing from one requirement at
    a time is what keeps it a slice.

    `ports_read` returns exactly `dynamic_slice`'s input shape, so nothing is
    adapted between them.
    """
    blocks = parse_rtl_blocks(rtl_text)
    if not blocks:
        return []
    return dynamic_slice(fail_signals=list(ports),
                         drivers=build_driver_map(blocks), max_depth=max_depth)


# ----------------------------------------------------------------- explain


def _edge_time(trace: dict, edge: int | None) -> int | None:
    """Simulator time at a recorded edge, or None if the run predates the stamp.

    NEVER `edge * period_ns`. Stimulus steps carry holds and durations, so the
    mapping is not uniform, and a computed time would be wrong precisely where
    the agent is being sent to look.
    """
    if edge is None:
        return None
    for row in trace.get("edges") or []:
        if row.get("edge") == edge:
            t = row.get("t")
            return int(t) if isinstance(t, (int, float)) else None
    return None


def _boundary(trace: dict, ports, lo: int, hi: int, *, side: str = "dut") -> list[dict]:
    """The watched ports at every edge in the span. CONSECUTIVE, never sampled.

    The existing rule applies verbatim: the skew detectors compare row i against
    row i-N, so a scattered sample destroys exactly the structure they exist to
    find. This is free -- it is already-recorded data, and the VCD is not needed
    for it.
    """
    out = []
    for row in trace.get("edges") or []:
        e = row.get("edge")
        if not isinstance(e, int) or e < lo or e > hi:
            continue
        vals = dict(row.get(side) or {})
        vals.update({k: v for k, v in (row.get("inputs") or {}).items() if k in set(ports)})
        out.append({"edge": e, "t": row.get("t"),
                    **{p: vals.get(p) for p in ports if p in vals}})
    return out


def _transitions(rows: list[dict], ports) -> list[str]:
    """Where each watched signal CHANGED inside the span.

    A temporal check is about edges, not levels, so the transition list is the
    actionable datum -- a level dump makes the reader find them by eye.
    """
    out, prev = [], {}
    for row in rows:
        for p in ports:
            if p not in row:
                continue
            now = row[p]
            was = prev.get(p, "__unset__")
            if was != "__unset__" and was != now:
                at = f"t={row['t']}" if row.get("t") is not None else f"edge {row['edge']}"
                out.append(f"{p} {was} -> {now} at {at}")
            prev[p] = now
    return out


def _satisfying_perturbation(oracle, rows: list[dict], contract: dict,
                             edge: int | None) -> str:
    """What would have satisfied the CHECK, reconstructed FROM THE CHECK.

    The replacement for expected/actual, and it needs no second implementation:
    an oracle is a Python function, so drive each declared output it names to
    every other legal value at the deciding edge and re-decide. `liveness.py`
    already performs exactly this perturbation -- `_widths` for the declared
    outputs, `_targets` for each end of the range, `_perturb` to rewrite one row
    -- so only the reporting is new.

    OUTPUTS ONLY, and that is liveness's substantive choice rather than a
    filter: inputs are the STIMULUS, so changing one asks a different question
    of the design and an oracle that failed to notice would be right to. Only
    what the design produced is fair to perturb.

    AND WHEN NOTHING FLIPS IT, SAY SO PLAINLY. That is not a failure of the
    instrument: it tells the agent the defect is TEMPORAL rather than a wrong
    value, which is the distinction the debugger most often gets wrong and
    currently has nothing to settle it with.
    """
    try:
        from specflow.refmodel.liveness import _perturb, _targets, _widths
        from specflow.refmodel.oracles import decide, ports_read
    except Exception:  # noqa: BLE001
        return ""
    widths = _widths(contract)
    reads = ports_read(oracle, contract)
    hits: list[str] = []
    for port in sorted(p for p in reads if p in widths):
        for target in _targets(widths[port]):
            try:
                moved = _perturb(rows, port, widths[port], edge, target=target)
            except Exception:  # noqa: BLE001
                continue
            # None means nothing changed -- the port is absent, or every row
            # already carries the target. No evidence either way.
            if moved is None:
                continue
            try:
                if decide(oracle, moved).ok is True:
                    hits.append(f"driving {port}={target} at the deciding edge "
                                f"would satisfy this check")
                    break
            except Exception:  # noqa: BLE001
                continue
    if hits:
        return "; ".join(hits)
    return ("NO single-value change at the deciding edge satisfies this check, "
            "so the defect is TEMPORAL -- the ordering or the timing, not a "
            "wrong value at one edge.")


def _block_internals(vcd_path: Path | None, blocks: list[RtlBlock],
                     times: list[int], *, dut_instance: str = "",
                     max_signals: int = 12) -> dict[str, list]:
    """The SUSPECT BLOCKS' internal signals across the span. What the VCD adds.

    §5.6 item 3, and the one thing that IMPROVES on a Verilog mismatch table:
    that table reports boundary ports only, so the agent had to guess what the
    implicated block was doing. The recorded trace says the boundary
    misbehaved; the VCD says what the suspect blocks were doing while it did --
    which is the question `read_block` leaves the agent to answer from source
    alone.
    """
    if not vcd_path or not times or not blocks:
        return {}
    try:
        from .trace_report import (VCDVCD, _vcd_find_signal, _vcd_tv,
                                   _vcd_value_at)
    except Exception:  # noqa: BLE001
        return {}
    if VCDVCD is None or not Path(vcd_path).exists():
        return {}
    try:
        vcd = VCDVCD(str(vcd_path), store_tvs=True)
    except Exception:  # noqa: BLE001
        return {}
    names: list[str] = []
    for b in blocks:
        names.extend(list(b.writes) + list(b.reads))
    out: dict[str, list] = {}
    prefer = [f".{dut_instance}."] if dut_instance else None
    for leaf in sorted({n for n in names if n})[:max_signals]:
        try:
            full = _vcd_find_signal(vcd, leaf, prefer_substrings=prefer)
            if not full:
                continue
            tv = _vcd_tv(vcd, full)
            out[leaf] = [{"t": t, "v": _vcd_value_at(tv, t, inclusive=(t == 0))}
                         for t in times]
        except Exception:  # noqa: BLE001
            continue
    return out


def explain_failure(*, view: RequirementView, result, trace: dict,
                    contract: dict, rtl_text: str = "",
                    vcd_path: Path | None = None, dut_instance: str = "",
                    span_pad: int = 10) -> dict:
    """§5.6's annotation for one failing check. Five parts, one dict.

    A SPAN, not an instant, is the first of them and it is strictly more than
    `fail_time`: the activation opened somewhere and the check objected
    somewhere later, and naming that interval is what a human reads a waveform
    against. The temporal combinators already carry both ends.
    """
    from specflow.refmodel.oracles import RequirementOracle

    oracle = RequirementOracle(req_uid=view.req_uid, clause=view.clause,
                               source=view.source, tp_uids=view.tp_uids)
    rows = list(getattr(result, "rows", None) or [])
    edge = getattr(result, "edge", None)
    opened = getattr(result, "window_start", None)
    if opened is None:
        opened = max(0, (edge - span_pad)) if isinstance(edge, int) else 0
    lo, hi = (min(opened, edge), max(opened, edge)) if isinstance(edge, int) else (opened, opened)

    t_open, t_fail = _edge_time(trace, lo), _edge_time(trace, hi)
    boundary = _boundary(trace, view.ports, max(0, lo - 2), hi + 2)
    times = [r["t"] for r in boundary if isinstance(r.get("t"), int)]
    blocks = focus_slice(rtl_text, view.ports) if rtl_text else []

    out = {
        # WHAT THE DESIGN OWED, in the requirement's own words. This is the half
        # the loop never had, and the half B21 shows it inventing when absent.
        "requirement": view.brief(),
        "check_said": getattr(result, "detail", "") or "",
        "verdict": getattr(result, "ok", None),
        "testpoint": getattr(result, "tp_uid", "") or "",
        "span": {
            "opened_at_edge": lo, "objected_at_edge": hi,
            "opened_at_t": t_open, "objected_at_t": t_fail,
            "note": ("the interval this requirement governs; a transactional "
                     "view collapses runs, so an edge is where a state BEGAN"),
        },
        "boundary_ports": boundary,
        "transitions": _transitions(boundary, view.ports),
        "suspect_blocks": [b.id for b in blocks],
        "block_internals": _block_internals(vcd_path, blocks, times,
                                            dut_instance=dut_instance),
    }
    if rows:
        out["what_would_satisfy_it"] = _satisfying_perturbation(
            oracle, rows, contract, edge)
    if not times:
        out["window_warning"] = (
            "this trace carries no recorded simulator time, so the VCD window "
            "could not be built. Edge indices are NOT timestamps -- see "
            "`Env._record`'s time stamp; a run predating it cannot be windowed.")
    # A MISSING HALF MUST SAY SO. `_block_internals` returns {} both when the
    # suspect blocks had nothing worth showing and when there is NO WAVEFORM AT
    # ALL, and those are different facts. MEASURED on the first live editor run:
    # all five `explain` calls came back with `block_internals: {}` because the
    # suite had been run with `trace=False`, and nothing in the payload said so
    # -- so the agent spent the session reading boundary ports and source,
    # believing it had been shown everything. That is precisely the evidence
    # state B21 records the debugger inventing a timing theory from.
    if not out["block_internals"]:
        out["internals_warning"] = (
            "NO INTERNAL SIGNALS ARE SHOWN. "
            + ("this run dumped no waveform, so what the suspect blocks were "
               "doing across the span could not be read -- you are seeing "
               "BOUNDARY PORTS ONLY, and the block sources, and nothing about "
               "internal state" if not vcd_path else
               "the waveform carried none of the suspect blocks' signals under "
               f"the instance name searched ({dut_instance or 'unset'})"))
    return out
