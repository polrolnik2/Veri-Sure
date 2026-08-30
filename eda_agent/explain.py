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
import re
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


#: Seconds per VCD time unit, for the units a `$timescale` may name.
_VCD_UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9,
              "ps": 1e-12, "fs": 1e-15}


def _readable(value: str | None) -> str | None:
    """A wide vector as binary AND decimal. `cnt` is a 16-bit counter.

    Verilator writes vectors as bit strings, so a counter reads
    `0000000000000011` -- correct, and hard to compare against the `clk_cnt=3`
    a requirement talks about. Narrow values stay as they are: `state` as
    `1011` is what a `case` arm is written against, and rendering it 11 would
    be worse.
    """
    if not value or len(value) <= 4 or set(value) - {"0", "1"}:
        return value
    return f"{value} ({int(value, 2)})"


def _vcd_ticks_per_ns(vcd_path: Path) -> float:
    """How many VCD time units make one nanosecond. 1.0 if it cannot be read.

    THE TRACE AND THE WAVEFORM COUNT TIME IN DIFFERENT UNITS, and nothing
    reconciled them. `Env._record` stamps each row with
    `get_sim_time("ns")`; Verilator writes `$timescale 1ps`. MEASURED on the
    second live editor run: the trace's last row is t=2440 and the waveform runs
    to 2,440,000 -- the same instant, a thousand ticks apart -- so every
    `_vcd_value_at(tv, 600)` was reading 600 PICOSECONDS into a 2.44-microsecond
    run, i.e. the first 0.02% of it. All 53 signals in the slice therefore came
    back holding their reset value, and the internals section was not merely
    mis-selected but WRONG.

    This is exactly the failure §5.6 predicted -- "silently collapses the window
    to the start of the run" -- surviving in the units dimension after it was
    fixed in the index dimension. There is no error at any point: a VCD lookup
    for a time before the first change legitimately returns the initial value.

    `vcdvcd` does not expose the timescale, so the header is read directly. A
    file whose header cannot be parsed returns 1.0, which is the identity and
    keeps a caller working on a waveform already in nanoseconds.
    """
    try:
        head = Path(vcd_path).read_bytes()[:4096].decode("utf-8", "replace")
    except OSError:
        return 1.0
    m = re.search(r"\$timescale\s*(\d+)\s*([munpf]?s)\s*\$end", head)
    if not m:
        return 1.0
    seconds = int(m.group(1)) * _VCD_UNITS.get(m.group(2), 1e-9)
    return (1e-9 / seconds) if seconds else 1.0


def _clocks_and_resets(contract: dict) -> set[str]:
    """Ports that are in every chain and explain nothing."""
    try:
        from specflow.ports import is_clock, is_reset
    except Exception:  # noqa: BLE001
        return set()
    return {str(p.get("name")) for p in (contract.get("io") or [])
            if p.get("name") and (is_clock(p["name"]) or is_reset(p["name"]))}


def _block_internals(vcd_path: Path | None, blocks: list[RtlBlock],
                     times: list[int], *, dut_instance: str = "",
                     roots: list[str] | None = None,
                     skip: set[str] | None = None) -> dict:
    """TRACE THE FAILING SIGNAL BACKWARDS, with every intermediate value.

    §5.6 item 3 asked for "the INTERNALS of the implicated blocks" and got a
    flat bag: `suspect_blocks` was a list of bare ids, `block_internals` a dict
    of signals, and nothing said which drove which or how any of them reached
    the signal that failed. The agent had to call `focus` separately and rebuild
    the dataflow by hand from `writes`/`reads` lists.

    `dynamic_slice` already walks the driver graph outward from the failing
    signals by depth -- and then throws the structure away, returning a flat set
    of blocks. This keeps it. The result is the chain a person actually reads a
    waveform along:

        depth 0   scl_oen   driven by A4   1, then 0 at 640, 1 at 720
        depth 1   state     driven by A4   0000, then 1011 at 640 ...   feeds scl_oen
        depth 1   cnt       driven by A2   3, then 2 at 610 ...         feeds scl_oen
        depth 2   clk_cnt   input                                       feeds cnt

    Every value is the waveform's own, at the waveform's own times. A signal is
    listed once, at the SHALLOWEST depth it was reached, because that is the
    shortest explanation of how it bears on the failure.

    `roots` are the signals the check convicted the design on -- its outputs.
    Falling back to every port it reads keeps a check with no declared output
    working, just with a wider root set.
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

    drivers: dict[str, list[RtlBlock]] = {}
    for b in blocks:
        for w in b.writes:
            drivers.setdefault(w, []).append(b)
    scale = _vcd_ticks_per_ns(Path(vcd_path))
    lo, hi = min(times), max(times)
    prefer = [f".{dut_instance}."] if dut_instance else None

    def sample(leaf: str):
        """`(value at window start, transitions inside it)` or None."""
        try:
            full = _vcd_find_signal(vcd, leaf, prefer_substrings=prefer)
            if not full:
                return None
            tv = _vcd_tv(vcd, full)
            return (_vcd_value_at(tv, int(round(lo * scale)), inclusive=True),
                    [{"t": int(round(t / scale)), "v": _readable(v)}
                     for t, v in tv if lo * scale < t <= hi * scale])
        except Exception:  # noqa: BLE001
            return None

    # THE CLOCK IS IN EVERY CHAIN AND EXPLAINS NOTHING. Every sequential block
    # reads it, so it enters at depth 1 of every walk and brings one transition
    # per edge -- 28 of them in a 140ns window, which is the noise that buries
    # the six signals that matter. Reset is the same. `skip` carries them from
    # the contract rather than guessing from names here.
    avoid = set(skip or ())
    known = {n for b in blocks for n in list(b.writes) + list(b.reads)
             if n and n not in avoid}
    frontier = [r for r in (roots or []) if r in known] or sorted(known)
    seen: set[str] = set(frontier)
    feeds: dict[str, str] = {}
    chain: list[dict] = []
    held: dict[str, dict] = {}
    depth = 0
    while frontier and depth < 8:
        nxt: list[str] = []
        for leaf in frontier:
            got = sample(leaf)
            who = [b.id for b in drivers.get(leaf, [])]
            row: dict = {"depth": depth, "signal": leaf,
                         "driven_by": (who[0] if len(who) == 1 else who or None)}
            if leaf in feeds:
                row["feeds"] = feeds[leaf]
            if got is None:
                # A `reads` set is extracted from identifiers, so it also holds
                # function names and macros that were never signals. One with
                # no waveform entry is a parse artefact, not a finding, and
                # listing it as "not present" only adds a row to read past.
                continue
            if got[1]:
                row["at_window_start"], row["changed"] = _readable(got[0]), got[1]
                if not who:
                    row["note"] = ("no block drives it and it MOVED, so the "
                                   "stimulus did: an input, not the design's doing")
                chain.append(row)
            else:
                # Constant across the window: no part of the explanation, but
                # worth having once -- a wrong localparam looks exactly like
                # this from the outside.
                entry = {"value": _readable(got[0]),
                         "driven_by": row["driven_by"]}
                if not who:
                    # Held still AND undriven says only that: it may be a
                    # localparam, or an input the stimulus never moved, and the
                    # block table cannot tell them apart. Claiming "input" here
                    # would assert more than is known.
                    entry["note"] = ("no block drives it and it never moved "
                                     "here: a constant, or an input the "
                                     "stimulus held")
                held[leaf] = entry
            for b in drivers.get(leaf, []):
                for r in b.reads:
                    if r and r not in seen and r not in avoid:
                        seen.add(r)
                        feeds[r] = leaf
                        nxt.append(r)
        frontier, depth = sorted(nxt), depth + 1
    out: dict = {}
    if chain:
        out["chain"] = chain
    if held:
        out["__held_constant__"] = held
    return out


def _why_uncovered(view: RequirementView, trace: dict) -> dict:
    """Why the check never fired, and what would make it.

    AN ABSTENTION HAS NO WINDOW, and `explain` was inventing one anyway. With no
    `edge` it fell back to `max(0, edge - span_pad)` -> 0 and reported a span
    from edge 0 to edge 0, under a note reading "the interval this requirement
    governs" -- which for a check that never fired is not merely unhelpful but
    false. MEASURED on run 5's 27 uncovered requirements: TWENTY have no edge at
    all, and every one of them got a fabricated span at the start of the trace.

    The actionable question for an abstention is not "where did it go wrong" but
    "why did the situation never arise, and what would produce it" -- which is
    exactly what `add_stimulus` needs to be told. So: the activation the
    requirement declares, and, per port it pins, the values the trace ACTUALLY
    carried. "wants cmd=4, saw only 0 and 1" is a scenario request already
    three-quarters written.
    """
    act = view.activation or {}
    wanted = dict(act.get("inputs") or {})
    rows = trace.get("edges") or []
    seen: dict[str, list] = {}
    for port in wanted:
        vals = []
        for r in rows:
            v = (r.get("inputs") or {}).get(port,
                 (r.get("dut") or {}).get(port))
            if v is not None and v not in vals:
                vals.append(v)
            if len(vals) > 12:
                break
        seen[port] = vals
    missing = {p: w for p, w in wanted.items()
               if isinstance(w, int) and w not in (seen.get(p) or [])}
    out = {
        "why": "this check never fired, so it says NOTHING about the design",
        "activation_needs": wanted,
        "activation_text": act.get("text") or "",
        "values_the_trace_carried": seen,
        "closes_on": act.get("until") or [],
    }
    if missing:
        out["never_reached"] = missing
        out["what_to_ask_for"] = (
            "the stimulus never drove "
            + ", ".join(f"{p}={v}" for p, v in sorted(missing.items()))
            + " on this testpoint. add_stimulus(req_uid, ...) with a scenario "
              "that does is the route; no edit to the design can discharge an "
              "uncovered requirement.")
    else:
        out["what_to_ask_for"] = (
            "every pinned input value does appear somewhere in this trace, so "
            "the activation is failing on TIMING or on a condition the trace "
            "cannot show -- an ordering, an edge, or an output the design never "
            "produced. Read `activation_text` and describe the sequence.")
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
    # AN ABSTENTION IS A DIFFERENT QUESTION and must not be answered with a
    # fabricated span. See `_why_uncovered`.
    if getattr(result, "ok", None) is None:
        return {"requirement": view.brief(),
                "verdict": None,
                "check_said": getattr(result, "detail", "") or "",
                "testpoint": getattr(result, "tp_uid", "") or "",
                "uncovered": _why_uncovered(view, trace)}
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
        # Not bare ids: what each block DRIVES, so the list can be read against
        # `block_internals` without a second tool call.
        "suspect_blocks": [{"id": b.id, "writes": list(b.writes)}
                           for b in blocks],
        # ROOTED AT WHAT THE CHECK CONVICTED THE DESIGN ON. A requirement reads
        # its activation's inputs too, and rooting the walk at those would trace
        # backwards from the STIMULUS, which explains nothing about the design.
        "block_internals": _block_internals(
            vcd_path, blocks, times, dut_instance=dut_instance,
            roots=[p["name"] for p in (contract.get("io") or [])
                   if p.get("dir") == "output" and p.get("name") in view.ports],
            skip=_clocks_and_resets(contract)),
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
    # `__held_constant__` alone is not internals: it means every signal the
    # suspect blocks touch held still across the whole span, which for a
    # temporal failure is itself the finding and must not read as a populated
    # view.
    if not (out["block_internals"].get("chain") or []):
        out["internals_warning"] = (
            "NO INTERNAL SIGNALS ARE SHOWN. "
            + ("this run dumped no waveform, so what the suspect blocks were "
               "doing across the span could not be read -- you are seeing "
               "BOUNDARY PORTS ONLY, and the block sources, and nothing about "
               "internal state" if not vcd_path else
               ("every signal the suspect blocks touch was CONSTANT across this "
                "span (listed under __held_constant__), which is itself a finding "
                "for a temporal check: nothing in these blocks moved while the "
                "requirement was being violated"
                if out["block_internals"].get("__held_constant__") else
                "the waveform carried none of the suspect blocks' signals under "
                f"the instance name searched ({dut_instance or 'unset'})")))
    return out
