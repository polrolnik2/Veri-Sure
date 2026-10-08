"""The contract a pipeline stage is given: the specification's STRUCTURED facts.

A contract written by a model carries two kinds of content. The structured
fields -- ports, directions, widths, idle values, clocking and reset, a latency
the spec states, an encoding imported from the design's defines header, probes
-- are checked by gates and drive the testbench. The prose -- functional
summary, corner cases, test plan, guidance, every `notes` field -- is a
paraphrase of the specification that no gate reads.

Measured on the luna6 runs, the paraphrase was the only description of the
behaviour most stages had: normalize, S2, S3, stimulus, the witness, the seven
population designs, the reference model and the check author were given the
requirements and the contract, not the specification. A paraphrase that drifts
or drops an exception therefore became the specification for every design and
check at once, where no population-based instrument can see it.

So every stage now receives the specification itself (`fanout.spec_section`),
and the contract is reduced to what is not prose. A port's `notes` is replaced
by the specification's own port-list entry, verbatim, so the consumers that read
it (`compose`, `oracle_gen`, `reachability`) read the spec rather than a summary.
"""
from __future__ import annotations

import copy
from typing import Any

from .encoding import port_entry

#: Top-level keys that are prose, in full.
PROSE = ("functional_summary", "corner_cases", "test_plan", "guidance")

#: Per-port keys kept. Everything a gate, the testbench or a probe consumer reads.
_PORT_KEYS = ("name", "dir", "width", "idle_value", "role", "encoding",
              "encoding_complete", "encoding_source")

_RESET_KEYS = ("name", "active", "type")


def _reset(r: Any) -> Any:
    return {k: r[k] for k in _RESET_KEYS if k in r} if isinstance(r, dict) else r


def structured(contract: dict, spec: str) -> dict:
    """`contract` reduced to its structured facts; a new dict, the input untouched."""
    c = copy.deepcopy(contract)
    for k in PROSE:
        c.pop(k, None)
    params = []
    for p in c.get("parameters") or []:
        if isinstance(p, dict):
            params.append({k: p[k] for k in ("name", "default", "type") if k in p})
    c["parameters"] = params
    io = []
    for p in c.get("io") or []:
        if not isinstance(p, dict):
            continue
        if p.get("dir") == "probe":
            io.append(p)  # [P]'s own table: name, width, spec_term -- keep whole
            continue
        q = {k: p[k] for k in _PORT_KEYS if k in p}
        said = port_entry(spec, str(p.get("name") or ""))
        if said:
            q["notes"] = " ".join(said.split())
        io.append(q)
    c["io"] = io
    clk = c.get("clocking")
    if isinstance(clk, dict):
        out: dict = {}
        if "is_sequential" in clk:
            out["is_sequential"] = clk["is_sequential"]
        if isinstance(clk.get("clock"), dict):
            out["clock"] = {k: clk["clock"][k] for k in ("name", "edge") if k in clk["clock"]}
        if "reset" in clk:
            out["reset"] = _reset(clk["reset"])
        if isinstance(clk.get("additional_resets"), list):
            out["additional_resets"] = [_reset(r) for r in clk["additional_resets"]]
        if isinstance(clk.get("enable"), dict):
            out["enable"] = {k: clk["enable"][k] for k in ("name", "active") if k in clk["enable"]}
        c["clocking"] = out
    timing = c.get("timing")
    if isinstance(timing, dict):
        kept = {}
        for out_name, t in timing.items():
            lat = t.get("latency_cycles") if isinstance(t, dict) else None
            if isinstance(lat, int) and not isinstance(lat, bool):
                kept[out_name] = {"latency_cycles": lat}
        c["timing"] = kept
    return c
