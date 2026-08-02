from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class ContractIssue:
    severity: str  # "error" | "warning"
    path: str
    message: str


def tb_instantiates_module(tb_code: str, module_name: str) -> bool:
    """Does this testbench actually drive `module_name`?

    A testbench that instantiates some OTHER module is not an oracle for this
    node -- it is a broken oracle, and every verdict it produces is about a
    design that was never simulated. Measured over the persisted corpus, 8 of
    34 cached oracles were in exactly that state: nodes named `fp_*` judged by
    testbenches driving `booth_composition`, `booth_multiplier`, or a generic
    `dut_top` stub. Two of them gated real glue attempts.

    Deliberately permissive: this decides whether to RETIRE an oracle, so a
    false positive throws away a good testbench. Anything ambiguous reads as
    "fine". Comments are stripped first so a commented-out instantiation does
    not count.
    """
    if not tb_code or not module_name:
        return False
    body = re.sub(r"//[^\n]*", "", tb_code)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return bool(
        re.search(
            rf"\b{re.escape(module_name)}\b\s*(?:#\s*\([^;]*?\))?\s*\w+\s*\(",
            body,
            re.S,
        )
    )


def _as_int(val: Any) -> int | None:
    try:
        return int(val)
    except Exception:  # noqa: BLE001
        return None


_COMPLETION_WORDS = frozenset({"valid", "ready", "ack", "done", "busy", "complete"})
_NAME_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")


def _has_completion_signal(outputs) -> bool:
    """Does any OUTPUT tell a consumer when the data outputs are usable?

    Names only -- the contract has no other handle on intent.

    Matching is per WORD, not by substring, and the split has to happen on
    underscores and camelCase rather than regex word boundaries: `_` is a word
    character, so `\\bvalid\\b` matches neither `valid_out` nor `data_valid` --
    i.e. exactly the two spellings the check exists to catch. Splitting first
    keeps `invalid_flag` out, which a substring search would wrongly accept as
    a handshake.
    """
    for name in outputs or []:
        parts = {p.lower() for p in _NAME_SPLIT_RE.split(str(name) or "") if p}
        if parts & _COMPLETION_WORDS:
            return True
    return False


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
                elif l > 1 and not _has_completion_signal(outputs):
                    # A latency beyond a registered output is only integrable if a
                    # consumer can learn when the value is ready -- either from a
                    # completion signal, or from a latency the spec states outright.
                    # With neither, every consumer must guess, and the guess that
                    # a registered interface implies one cycle is the obvious one.
                    #
                    # Measured on fp_adder (level-3): the spec offers `clk`, `rst`,
                    # `a`, `b`, `rnd_mode` -> `sum`, `exception_flags`, declares the
                    # outputs `output reg`, states no cycle count, and carries no
                    # valid/ready/done anywhere -- while its prose says "Consider a
                    # pipelined structure". The contract came back with a 3-cycle
                    # latency, which is self-consistent with the testbench generated
                    # FROM that contract and unusable to anything else.
                    issues.append(ContractIssue(
                        "warning", f"timing.{out}.latency_cycles",
                        f"latency_cycles={l} but the interface has no completion signal "
                        f"(no valid/ready/done/valid_out output). Nothing tells a consumer "
                        f"when {out} is ready, so a multi-cycle latency is unobservable "
                        f"from outside this module. Unless the spec names a specific cycle "
                        f"count, state the MINIMUM latency the function needs (0 for "
                        f"combinational, 1 for a registered output).",
                    ))

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

