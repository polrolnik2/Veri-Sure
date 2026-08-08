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


# Prose that RELAXES a latency the same contract states as a number. Each of
# these tells the designer the declared figure is a floor rather than a budget.
_LATENCY_RELAXING_RES = (
    re.compile(r"deeper\s+pipelin", re.I),
    re.compile(r"(?:more|additional|extra|further)\s+pipelin", re.I),
    re.compile(r"pipelin\w*\s+(?:is|are)\s+(?:permitted|allowed|acceptable|optional)", re.I),
    re.compile(r"latency\s+(?:may|can)\s+(?:vary|differ|be\s+(?:higher|greater|longer))", re.I),
    re.compile(r"any\s+latency", re.I),
)

# Prose that DENIES the permission, so the same words carry the opposite sense.
# Deliberately narrow: it matches a negated PERMISSION, not any negation. The
# real conflict reads "Deeper pipelining is permitted but not required", which
# contains "not" and must still fire; the fix this linter recommends reads
# "additional pipeline stages are NOT permitted", which must not. A general
# negation check cannot separate those, and getting it wrong in the permissive
# direction means the linter flags the exact wording it just asked for.
_NEGATED_PERMISSION_RE = re.compile(
    r"(?:\bnot\b|\bn't\b)\s+(?:be\s+)?(?:permitted|allowed|acceptable|used)"
    r"|\bno\s+(?:additional|extra|more|further)\s+pipelin"
    r"|\b(?:forbidden|prohibited|disallowed)\b",
    re.I,
)

# Sampling guidance that offers the OPPOSITE clock edge as an equivalent.
_OPPOSITE_EDGE = {"posedge": "negedge", "negedge": "posedge"}

_SENTENCE_SPLIT_RE = re.compile(r"[.;\n]")


def _clause_around(text: str, start: int, end: int) -> str:
    """The clause containing [start, end) — negation does not cross a `;` or `.`."""
    left = max((m.end() for m in _SENTENCE_SPLIT_RE.finditer(text, 0, start)), default=0)
    m = _SENTENCE_SPLIT_RE.search(text, end)
    return text[left:m.start() if m else len(text)]


def _prose_strings(node: Any, path: str = "$", _depth: int = 0):
    """Every string value in the contract, with a JSON-ish path, prose only.

    Walks the whole object rather than a fixed key list because the statements
    that caused B93 lived in three different places -- `timing.sum.notes`,
    an `io[].notes`, and a free-form `guidance` bullet -- and a checker that
    inspects only the field it expects the conflict in is a checker that reports
    "no conflict" for "did not look".
    """
    if _depth > 12:
        return
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _prose_strings(v, f"{path}.{k}", _depth + 1)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _prose_strings(v, f"{path}[{i}]", _depth + 1)


def _latency_prose_conflicts(obj: dict, timing: Any, outputs) -> list[ContractIssue]:
    """Flag prose that overrides the contract's own `latency_cycles`.

    A latency figure is only a budget if nothing else in the contract says it is
    optional. When the prose disagrees with the number, the designer follows the
    prose -- it is the part written in the language the requirement is reasoned
    about in -- and the number becomes decoration.

    Measured on the fp_adder root (run `fp_adder_e2e`). The contract declared
    `latency_cycles: 1` on both outputs, then said:

        "Deeper pipelining is permitted but not required by the interface."
        "Drive inputs on posedge clk; sample outputs on the following posedge
         (or negedge to avoid race)."

    The golden testbench drives, waits ONE posedge and samples -- so deeper
    pipelining is not in fact permitted, and an output registered on negedge
    lands half a cycle after the sample point. Four independent glue redraws
    each built `always_ff @(posedge clk)` inputs into `always_ff @(negedge clk)`
    outputs, scoring 168/173/168/168 of 181, and each was FOLLOWING ITS
    CONTRACT. Nothing downstream could catch it: the self-TB is generated from
    the same contract, so it samples on the same wrong edge and agrees.

    Only fires when a latency is actually declared -- with no number there is
    nothing for the prose to contradict, and "pipelining is permitted" is then a
    legitimate degree of freedom rather than a conflict.
    """
    issues: list[ContractIssue] = []
    if not isinstance(timing, dict):
        return issues
    declared = {}
    for out in sorted(outputs or ()):
        tinfo = timing.get(out)
        if isinstance(tinfo, dict):
            lat = _as_int(tinfo.get("latency_cycles"))
            if lat is not None and lat >= 0:
                declared[out] = lat
    if not declared:
        return issues

    budget = max(declared.values())
    edge = ""
    clocking = obj.get("clocking")
    if isinstance(clocking, dict) and isinstance(clocking.get("clock"), dict):
        edge = str(clocking["clock"].get("edge") or "").lower()
    other = _OPPOSITE_EDGE.get(edge, "")

    for path, text in _prose_strings(obj):
        if path.startswith("$.contract_sva"):
            continue  # harness-injected, not the Architect's prose
        for rx in _LATENCY_RELAXING_RES:
            m = rx.search(text)
            if m:
                if _NEGATED_PERMISSION_RE.search(_clause_around(text, m.start(), m.end())):
                    continue  # "additional pipeline stages are NOT permitted" — compliant
                issues.append(ContractIssue(
                    "error", path.lstrip("$."),
                    f"This states extra pipelining is permitted, but timing declares "
                    f"latency_cycles={budget}. A consumer with no completion signal "
                    f"samples at the DECLARED latency, so any extra stage is read as a "
                    f"wrong value, not as a slower correct one. Either raise "
                    f"latency_cycles and add a completion signal, or say the declared "
                    f"latency is a HARD budget: \"exactly {budget} cycle(s); additional "
                    f"pipeline stages are NOT permitted\".",
                ))
                break
        if other and re.search(rf"\b{other}\b", text, re.I):
            issues.append(ContractIssue(
                "error", path.lstrip("$."),
                f"This mentions {other} while clocking.clock.edge is {edge}. Registering "
                f"or sampling an output on {other} shifts it half a cycle from the "
                f"{edge} the consumer samples on, which reads as a FULL transaction of "
                f"extra latency and fails every vector. Drive and observe on {edge} only.",
            ))
    return issues


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

    issues.extend(_latency_prose_conflicts(obj, timing, outputs))

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

