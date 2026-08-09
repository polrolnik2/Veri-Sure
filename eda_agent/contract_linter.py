from __future__ import annotations

import ast
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


def _parameter_defaults(obj: Any) -> dict[str, int]:
    """`{name: default}` for every declared parameter with an integer default."""
    out: dict[str, int] = {}
    for p in (obj or {}).get("parameters") or []:
        if not isinstance(p, dict):
            continue
        name, default = p.get("name"), _as_int(p.get("default"))
        if isinstance(name, str) and name.strip() and default is not None:
            out[name] = default
    return out


def _width_value(width: Any, params: dict[str, int]) -> int | None:
    """A port width, resolving parameter expressions like `WIDTH` or `MANT_WIDTH+1`.

    A DECOMPOSED contract's child-facing ports carry parameter expressions, not
    literals, because that is how the child declared them. `int(width)` returns
    None for every one of those, and the caller then reports an `error`-severity
    "Invalid width".

    Measured on the committed checkpoint at `c6d9485`: 24 to 65 such findings on
    EVERY composition contract in the corpus -- including all 28 glue draws from
    the three nodes that passed their gate. Linting a glue contract was therefore
    impossible; it would have rejected working composition wholesale. The
    contract already declares the parameters and their defaults, so nothing here
    is guessed -- the rule simply never read them.

    Evaluated over a whitelisted arithmetic subset (identifiers, integers,
    `+ - * // /`, parentheses, unary minus) via the AST, never `eval` on model
    output. An expression naming an undeclared parameter, or using anything
    outside that subset, returns None and is reported exactly as before.
    """
    direct = _as_int(width)
    if direct is not None:
        return direct
    if not isinstance(width, str) or not width.strip() or not params:
        return None
    try:
        tree = ast.parse(width.strip(), mode="eval")
    except SyntaxError:
        return None

    def ev(n: ast.AST) -> int | None:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value if isinstance(n.value, int) else None
        if isinstance(n, ast.Name):
            return params.get(n.id)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = ev(n.operand)
            return None if v is None else (v if isinstance(n.op, ast.UAdd) else -v)
        if isinstance(n, ast.BinOp) and isinstance(
            n.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div)
        ):
            a, b = ev(n.left), ev(n.right)
            if a is None or b is None:
                return None
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            return None if b == 0 else a // b
        return None

    return ev(tree)


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

# "two cycles later", "a two-cycle FIFO", "after exactly 2 cycles". Requires the
# count to be ADJACENT to "cycle(s)" so ordinary prose mentioning a number and a
# cycle in the same sentence does not trip it.
_PROSE_CYCLE_COUNT_RE = re.compile(
    r"\b(?P<n>zero|one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})[\s-]+cycles?\b",
    re.I,
)
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}
# A cycle count is only a LATENCY claim in the right company. Without this the
# check fires on "assert rst for one cycle", "hold start high for one cycle" and
# "stall for three cycles" — none of which say anything about latency, and all of
# which would then drive pointless `error`-severity revision rounds.
_LATENCY_CONTEXT_RE = re.compile(
    r"\blater\b|\blatency\b|\bdelay\b|\bpipelin|\bfifo\b|\bsampl|\boutput|\bresult"
    r"|\bappear|\bvalid\b|\bdeep\b|\bafter\b",
    re.I,
)


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
        # Prose that RESTATES the latency with a different number. F67's original
        # patterns catch prose that RELAXES a declared latency ("deeper pipelining
        # is permitted"); this catches prose that contradicts it outright.
        #
        # Found by re-minting the fp_adder root: `timing.latency_cycles` stayed 1
        # (pinned) while the freshly drawn guidance said "sample ... two cycles
        # later", "push into a two-cycle FIFO" and "zero after exactly two
        # cycles". A verifier following that builds a TB two cycles deep against
        # a 1-cycle contract — the same defect as B93, arrived at from the other
        # direction, and invisible to every check that existed.
        for m in _PROSE_CYCLE_COUNT_RE.finditer(text):
            if not _LATENCY_CONTEXT_RE.search(_clause_around(text, m.start(), m.end())):
                continue  # a cycle count, but not a latency claim
            word = (m.group("n") or "").lower()
            n = _NUMBER_WORDS.get(word, word)
            try:
                stated = int(n)
            except (TypeError, ValueError):
                continue
            if stated == budget:
                continue
            issues.append(ContractIssue(
                "error", path.lstrip("$."),
                f"This states a latency of {stated} cycle(s) while timing declares "
                f"latency_cycles={budget}. Downstream agents follow the prose, so a "
                f"testbench or design built from this samples at {stated} and is "
                f"scored at {budget} — every vector fails for a reason neither "
                f"artifact contains. Make the prose agree with the declared latency, "
                f"or change the declared latency.",
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


# Host-language tooling a SystemVerilog testbench cannot invoke. Deliberately a
# closed list of things that are unambiguously NOT SystemVerilog: a heuristic
# like "mentions a language name" would fire on legitimate prose such as
# "SystemVerilog functions".
_HOST_TOOLING_RE = re.compile(
    r"\bpython\b|\bnumpy\b|\bscipy\b|\bmatlab\b|\boctave\b|\bsoftfloat\b"
    r"|\bstruct\.(?:un)?pack\b|\bC\+\+\s*model\b|\bC\s+model\b|\.py\b",
    re.I,
)


def _infeasible_guidance(obj: dict) -> list[ContractIssue]:
    """Flag guidance the testbench cannot execute.

    `guidance` is consumed by agents that emit SystemVerilog compiled by
    Verilator. An instruction naming a host language or an external library
    cannot be followed by any of them, so it is not merely unhelpful — it
    occupies the slot where a followable instruction should have been, and the
    agent improvises exactly the thing the guidance existed to pin down.

    Measured across the runs in this repo: EIGHT contracts, spanning six
    different modules and several runs, carry host-language reference-model
    advice, and every one of them is under `guidance.verifier`:

        floating_point_adder   "Model expected results with a high-precision
                                IEEE-754 software reference (e.g., Python
                                struct.unpack/pack or softfloat)."
        stage_roundpack        "Build a reference model in Python using
                                struct.pack/unpack or numpy ..."
        fp_adder_pipeline      "Use a reference model (e.g., softfloat,
                                Verilator C++ model) ..."

    On the fp_adder root that line was the ONLY guidance about computing
    expected values, and five independently drawn oracles all hand-rolled the
    datapath instead — the failure this check exists to make visible.

    It says nothing about WHAT to use, only that what is named must be
    executable in the flow, so it stays clear of encoding problem-specific
    knowledge into the contract.
    """
    issues: list[ContractIssue] = []
    guidance = obj.get("guidance")
    if not isinstance(guidance, dict):
        return issues
    for section, val in guidance.items():
        entries = val if isinstance(val, list) else [val]
        for i, line in enumerate(entries):
            if not isinstance(line, str):
                continue
            m = _HOST_TOOLING_RE.search(line)
            if not m:
                continue
            issues.append(ContractIssue(
                "error", f"guidance.{section}[{i}]",
                f"This directs a downstream agent to use {m.group(0)!r}, which the "
                f"flow cannot execute: guidance is consumed by agents that emit "
                f"SystemVerilog compiled by Verilator, with no host-language "
                f"interpreter or external library available. An instruction nothing "
                f"can follow is worse than no instruction, because it takes the place "
                f"of one that could be followed. Restate it in terms the testbench "
                f"can evaluate directly, or drop it.",
            ))
    return issues


# `shortreal` and its two conversion functions. Verilator PROMOTES `shortreal`
# to 64-bit `real` and emits only a warning, so guidance naming it produces a
# testbench that lints clean, simulates, and is wrong on every row -- strictly
# worse than the host-language case above, which at least fails loudly.
#
# Measured on Verilator 5.051:
#   $shortrealtobits($bitstoshortreal(32'h3f800000) + $bitstoshortreal(32'h3f000000))
#     = 7e800000, where 1.0 + 0.5 is 3fc00000
#   agreement with true binary32 over 406 random operand pairs: 0.49%
_UNSUPPORTED_FLOAT_RE = re.compile(
    r"\$bitstoshortreal\b|\$shortrealtobits\b|\bshortreal\b", re.I
)


def _unsupported_float_guidance(obj: dict) -> list[ContractIssue]:
    """Flag guidance naming a float primitive Verilator does not implement.

    Separate from `_infeasible_guidance` because the failure mode is the
    opposite: host-language guidance cannot be followed at all, so a downstream
    agent has to improvise and the damage is visible. `shortreal` CAN be
    followed, compiles, runs, and yields garbage — the resulting oracle passes
    every acceptance check this flow has (`drives && lints`) while matching the
    true sum on 0.49% of rows.

    Walks every string in the contract, not just `guidance`: the trap is equally
    harmful in `test_plan` or a `timing` note, and unlike a latency claim it has
    no legitimate use anywhere.
    """
    issues: list[ContractIssue] = []

    def walk(node, path: str) -> None:
        if isinstance(node, str):
            m = _UNSUPPORTED_FLOAT_RE.search(node)
            if m:
                issues.append(ContractIssue(
                    "error", path,
                    f"This names {m.group(0)!r}, which Verilator does not implement: it "
                    f"promotes `shortreal` to 64-bit `real` and emits only a warning, so "
                    f"a testbench following this lints clean, simulates, and is wrong on "
                    f"every row (measured: 0.49% agreement with true binary32 over 406 "
                    f"operand pairs; 1.0 + 0.5 returns 7e800000 instead of 3fc00000). "
                    f"Use `real` with `$bitstoreal`/`$realtobits` instead — binary64 "
                    f"represents every binary32 value, and the exact sum of two of them, "
                    f"exactly.",
                ))
        elif isinstance(node, dict):
            for k, v in node.items():
                if k == "contract_sva":
                    continue
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(obj, "")
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
    # Read ONCE, outside the port walk: a decomposed contract can carry 60+
    # child-facing ports and every one of them would otherwise re-parse the
    # parameter list.
    params = _parameter_defaults(obj)

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
        w = _width_value(width, params)
        if w is None or w <= 0:
            hint = ""
            if isinstance(width, str) and width.strip() and not params:
                hint = (" — a parameter expression is only resolvable when the "
                        "contract declares `parameters` with integer defaults")
            issues.append(ContractIssue(
                "error", f"{ppath}.width", f"Invalid width for {name}: {width!r}{hint}"))
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
    issues.extend(_infeasible_guidance(obj))
    issues.extend(_unsupported_float_guidance(obj))

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

