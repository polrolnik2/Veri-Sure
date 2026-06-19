from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ContractIssue:
    severity: str  # "error" | "warning"
    path: str
    message: str


def _as_int(val: Any) -> int | None:
    try:
        return int(val)
    except Exception:  # noqa: BLE001
        return None


def lint_contract_json(contract_json_text: str) -> tuple[list[ContractIssue], dict[str, Any] | None]:
    """Best-effort semantic lint for the Architect contract JSON.

    This is intentionally lightweight: it catches the most common contract
    issues that cause downstream interface/timing drift.
    """
    issues: list[ContractIssue] = []
    try:
        obj = json.loads(contract_json_text)
    except Exception as e:  # noqa: BLE001
        return [ContractIssue("error", "$", f"Invalid JSON: {type(e).__name__}: {e}")], None

    if not isinstance(obj, dict):
        return [ContractIssue("error", "$", "Contract must be a JSON object.")], None

    module_name = obj.get("module_name")
    if not isinstance(module_name, str) or not module_name.strip():
        issues.append(ContractIssue("error", "module_name", "Missing/invalid module_name (must be non-empty string)."))

    io = obj.get("io")
    if not isinstance(io, list) or not io:
        issues.append(ContractIssue("error", "io", "Missing/invalid io (must be a non-empty list)."))
        return issues, obj

    seen_names: set[str] = set()
    inputs: set[str] = set()
    outputs: set[str] = set()

    for idx, p in enumerate(io):
        ppath = f"io[{idx}]"
        if not isinstance(p, dict):
            issues.append(ContractIssue("error", ppath, "Port entry must be an object."))
            continue
        name = p.get("name")
        direction = p.get("dir")
        width = p.get("width", 1)
        if not isinstance(name, str) or not name.strip():
            issues.append(ContractIssue("error", f"{ppath}.name", "Missing/invalid port name."))
            continue
        if name in seen_names:
            issues.append(ContractIssue("error", f"{ppath}.name", f"Duplicate port name: {name}"))
        seen_names.add(name)
        if direction not in {"input", "output", "inout"}:
            issues.append(ContractIssue("error", f"{ppath}.dir", f"Invalid dir for {name}: {direction!r}"))
        w = _as_int(width)
        if w is None or w <= 0:
            issues.append(ContractIssue("error", f"{ppath}.width", f"Invalid width for {name}: {width!r}"))
        if direction == "input":
            inputs.add(name)
        elif direction == "output":
            outputs.add(name)

    # parameters is optional (many modules have none) but, when present, each
    # entry must carry a usable name so the Coder can declare it verbatim.
    parameters = obj.get("parameters")
    if parameters is not None:
        if not isinstance(parameters, list):
            issues.append(ContractIssue("error", "parameters", "parameters must be a list."))
        else:
            seen_params: set[str] = set()
            for idx, pp in enumerate(parameters):
                path = f"parameters[{idx}]"
                if not isinstance(pp, dict):
                    issues.append(ContractIssue("error", path, "Parameter entry must be an object."))
                    continue
                pname = pp.get("name")
                if not isinstance(pname, str) or not pname.strip():
                    issues.append(ContractIssue("error", f"{path}.name", "Missing/invalid parameter name."))
                    continue
                if pname in seen_params:
                    issues.append(ContractIssue("error", f"{path}.name", f"Duplicate parameter name: {pname}"))
                seen_params.add(pname)

    clocking = obj.get("clocking")
    if clocking is not None and isinstance(clocking, dict):
        is_seq = clocking.get("is_sequential")
        if is_seq is True:
            clk = clocking.get("clock")
            if not isinstance(clk, dict) or not isinstance(clk.get("name"), str) or not clk.get("name"):
                issues.append(ContractIssue("error", "clocking.clock", "Sequential design requires clocking.clock.name."))
            else:
                clk_name = str(clk.get("name"))
                if clk_name not in inputs:
                    issues.append(ContractIssue("warning", "clocking.clock.name", f"Clock {clk_name} not found as input port."))
            rst = clocking.get("reset")
            if rst is not None and isinstance(rst, dict) and isinstance(rst.get("name"), str) and rst.get("name"):
                rst_name = str(rst.get("name"))
                if rst_name not in inputs:
                    issues.append(ContractIssue("warning", "clocking.reset.name", f"Reset {rst_name} not found as input port."))

    timing = obj.get("timing")
    if timing is not None and not isinstance(timing, dict):
        issues.append(ContractIssue("warning", "timing", "timing should be an object mapping output->timing info."))
    if isinstance(timing, dict):
        for out in sorted(outputs):
            tinfo = timing.get(out)
            if tinfo is None:
                issues.append(ContractIssue("warning", f"timing.{out}", "Missing timing entry for output; latency may be ambiguous."))
                continue
            if not isinstance(tinfo, dict):
                issues.append(ContractIssue("warning", f"timing.{out}", "Timing entry should be an object."))
                continue
            lat = tinfo.get("latency_cycles")
            if lat is None:
                issues.append(ContractIssue("warning", f"timing.{out}.latency_cycles", "Missing latency_cycles."))
            else:
                l = _as_int(lat)
                if l is None or l < 0:
                    issues.append(ContractIssue("error", f"timing.{out}.latency_cycles", f"Invalid latency_cycles: {lat!r}"))

    # Guidance is optional but helps downstream. Flag missing keys as warnings.
    guidance = obj.get("guidance")
    if guidance is None or not isinstance(guidance, dict):
        issues.append(ContractIssue("warning", "guidance", "Missing guidance block (verifier/coder/debugger)."))
    else:
        for k in ["verifier", "coder", "debugger"]:
            v = guidance.get(k)
            if v is None:
                issues.append(ContractIssue("warning", f"guidance.{k}", "Missing guidance list."))
            elif not isinstance(v, list):
                issues.append(ContractIssue("warning", f"guidance.{k}", "Guidance should be a list of strings."))

    return issues, obj


def render_contract_issues(issues: list[ContractIssue]) -> str:
    if not issues:
        return ""
    lines: list[str] = []
    for it in issues:
        lines.append(f"- [{it.severity}] {it.path}: {it.message}")
    return "\n".join(lines) + "\n"

