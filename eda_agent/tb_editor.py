"""TB alignment pass: mature a testbench's child behavioral model against
child assumption SVA, using a mock DUT and Verilator — BEFORE the testbench
is handed to the RTL debug loop.

Motivation
----------
When a testbench is generated for a composition (glue) node, it must model
each child's behavior inline (no real child RTL exists yet). That inline
model is currently free-hand prose-derived code (from ``io_behavior``) with
no independent check that it actually satisfies the formal ``child_assumes``
SVA it is supposed to embody. A TB that drifts from those properties silently
poisons the self-TB gate: the glue RTL can be penalized for a TB bug, or
(worse) a genuinely broken glue can pass because the TB's child model never
exercised the property that would have caught it.

This module gives the TB a life of its own, decoupled from the (not-yet-built
or currently-under-debug) glue RTL:

1. Build a **mock DUT** — a module with the SAME name and port list as the
   real glue module, but with no real glue logic. Ports the glue drives
   *into* a child (child-input-mapped) are driven with per-cycle randomized
   stimulus (clk/rst are passed through, not randomized) — analogous to the
   ``(* anyseq *)`` treatment in the formal glue BMC, but realized via
   simulation. Ports the glue *receives* from a child (child-output-mapped —
   i.e. the ones the TB's own inline model drives, standing in for the
   missing child) get the child's assume SVA properties injected as runtime
   ``assert`` statements.
2. Compile the TB against this mock DUT with Verilator. If the TB's inline
   child model violates a property, that is a genuine TB bug — independent
   of whatever the real glue RTL ends up doing.
3. Iterate with the SAME four-tool structure RTLEditor uses on RTL (list
   suspect sections -> read a section -> replace it -> re-check -> repeat,
   bounded by max_trials with stall detection). Where RTLEditor holds the TB
   frozen and edits RTL blocks (always/assign, sliced from a VCD-correlated
   trace report), TBEditor holds the mock DUT frozen and edits TB sections
   (initial/always/task/function, sliced by a lightweight structural parser
   and filtered to those referencing a child-driven signal named in a
   violated property).

TBEditor              RTLEditor
─────────────────────  ────────────────────────────────
list_suspect_sections() list_suspect_blocks()
read_section(id)        read_block(id)
replace_section(id, sv) replace_block(id, sv)
run_alignment_check()   run_simulation()

The result is a TB whose child model is verified self-consistent with the
formal contract *before* it is used to gate the actual glue RTL — so the
self-TB gate is not spent debugging TB bugs disguised as RTL bugs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import ToolResponse

from .agents import GuidingToolkit, SafeReActAgent, clear_memory_safely
from .asserter import _ASSERTER_FAIL_RE  # reuse the same failure marker/regex
from .bash_tools import CommandResult, run_bash_command
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
from .sim_reviewer import _require_executable
from .utils import clip_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock DUT construction
# ---------------------------------------------------------------------------

# SVA temporal operators that are not valid inside a plain `assert(...)`
# expression (they are property-syntax, not expression-syntax). $past/$rose/
# $stable etc. ARE fine here — Verilator (unlike yosys's formal frontend)
# supports them directly in procedural code.
_TEMPORAL_RE = re.compile(r"(\|->|\|=>|##\d+|\[\*|\[\->|\[\=)")


def _to_sim_immediate(body: str) -> str | None:
    body = body.strip()
    if _TEMPORAL_RE.search(body):
        return None
    return body


def _child_rename_map(io_names: set[str], child_name: str) -> dict[str, str]:
    """Bare child port name -> prefixed glue port name, e.g. 'ready' -> 'booth_controller_ready'."""
    prefix = f"{child_name}_"
    return {name[len(prefix):]: name for name in io_names if name.startswith(prefix)}


def _rename_body(body: str, rename: dict[str, str]) -> str:
    for short, long in sorted(rename.items(), key=lambda x: -len(x[0])):
        body = re.sub(rf"\b{re.escape(short)}\b", long, body)
    return body


@dataclass(frozen=True)
class MockDutResult:
    mock_dut_sv: str
    checked_property_count: int
    skipped_temporal_count: int
    # Prefixed glue-input port names driven by the TB's own inline child
    # model — i.e. the signals a repair should focus on (used to mark TB
    # sections as "suspect").
    child_driven_signals: list[str]


def build_mock_dut(contract_obj: dict[str, Any], child_assumes: dict[str, Any]) -> MockDutResult:
    """Build a pin-compatible stub standing in for the (not-yet-correct) glue.

    Child-input-mapped ports (glue OUTPUT, e.g. ``booth_controller_start``) are
    driven with randomized per-cycle stimulus so the TB's child model is
    exercised broadly, not just on the happy path. Child-output-mapped ports
    (glue INPUT, e.g. ``booth_datapath_product``) are left as pure inputs
    (the TB drives them) and get that child's own assume properties injected
    as ``assert`` checks. True external ports are inert (tied to 0 if output).
    """
    module_name = str(contract_obj.get("module_name") or "glue")
    io = contract_obj.get("io", [])
    if not isinstance(io, list):
        io = []
    clocking = contract_obj.get("clocking", {}) if isinstance(contract_obj.get("clocking"), dict) else {}
    clk_info = clocking.get("clock", {}) if isinstance(clocking.get("clock"), dict) else {}
    rst_info = clocking.get("reset", {}) if isinstance(clocking.get("reset"), dict) else {}
    clk_name = clk_info.get("name") or "clk"
    clk_edge = clk_info.get("edge") or "posedge"
    if clk_edge not in ("posedge", "negedge"):
        clk_edge = "posedge"
    rst_name = rst_info.get("name") or "rst"

    io_names = {p["name"] for p in io if isinstance(p, dict) and p.get("name")}
    child_names = list(child_assumes.keys())

    def _width_str(w: Any) -> str:
        try:
            wi = int(w)
            return f" [{wi - 1}:0]" if wi > 1 else ""
        except (TypeError, ValueError):
            return f" [({w})-1:0]"

    port_lines: list[str] = []
    for p in io:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        d = p.get("dir", "input")
        port_lines.append(f"  {d} logic{_width_str(p.get('width', 1))} {p['name']}")

    lines: list[str] = [f"module {module_name} ("]
    lines.append(",\n".join(port_lines))
    lines.append(");")
    lines.append("")

    child_driven_signals: list[str] = []

    # Classify child-prefixed ports: which child they belong to, and whether
    # they are glue-output (drive randomly) or glue-input (leave to the TB).
    for cname in child_names:
        rename = _child_rename_map(io_names, cname)
        for short, long in rename.items():
            port = next((p for p in io if isinstance(p, dict) and p.get("name") == long), None)
            if port is None:
                continue
            d = port.get("dir", "input")
            if d != "output":
                child_driven_signals.append(long)  # glue-input: TB drives it
                continue
            if short == clk_info.get("name") or long.endswith(f"_{clk_name}"):
                lines.append(f"  assign {long} = {clk_name};")
            elif short == rst_info.get("name") or long.endswith(f"_{rst_name}"):
                lines.append(f"  assign {long} = {rst_name};")
            else:
                w = _width_str(port.get("width", 1))
                reg_name = f"_mock_rand_{long}"
                lines.append(f"  logic{w} {reg_name};")
                lines.append(f"  always @({clk_edge} {clk_name}) {reg_name} <= $urandom();")
                lines.append(f"  assign {long} = {reg_name};")

    # True external outputs (not child-prefixed): inert, tied to 0.
    child_prefixes = tuple(f"{c}_" for c in child_names)
    for p in io:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        if p.get("dir") != "output":
            continue
        if p["name"].startswith(child_prefixes):
            continue
        lines.append(f"  assign {p['name']} = '0;")

    lines.append("")
    lines.append("  // === child assume properties, checked against the TB's own inline model ===")
    lines.append("  localparam int unsigned TB_ALIGN_MAX_FAILS = 40;")
    lines.append("  int unsigned tb_align_fail_count = 0;")
    lines.append("  task automatic asserter_log(string id, string msg);")
    lines.append("    if (tb_align_fail_count < TB_ALIGN_MAX_FAILS) begin")
    lines.append('      $display("ASSERTER_FAIL: %s t=%0t %s", id, $time, msg);')
    lines.append("    end")
    lines.append("    tb_align_fail_count++;")
    lines.append("  endtask")
    lines.append("")

    checked = 0
    skipped = 0
    for cname, ca in child_assumes.items():
        rename = _child_rename_map(io_names, cname)
        props = ca.get("properties", []) if isinstance(ca, dict) else []
        for prop in props:
            if not isinstance(prop, dict):
                continue
            name = prop.get("name", "prop")
            body = prop.get("body", "")
            if not body:
                continue
            sim_body = _to_sim_immediate(body)
            if sim_body is None:
                lines.append(f"  // SKIPPED (temporal, not expressible as immediate assert): {cname}.{name}")
                skipped += 1
                continue
            sim_body = _rename_body(sim_body, rename)
            p_clk = prop.get("clk") or clk_name
            p_rst = prop.get("rst") or rst_name
            p_clk = rename.get(p_clk, p_clk) if p_clk not in io_names else p_clk
            p_rst = rename.get(p_rst, p_rst) if p_rst not in io_names else p_rst
            lines.append(f"  // assume-as-assert: {cname}.{name}")
            lines.append(f"  always @({clk_edge} {p_clk}) if (!{p_rst}) begin")
            lines.append(f'    assert ({sim_body}) else asserter_log("{cname}.{name}", "child assumption violated");')
            lines.append("  end")
            checked += 1

    lines.append("")
    lines.append("endmodule")
    mock_sv = "\n".join(lines) + "\n"
    return MockDutResult(
        mock_dut_sv=mock_sv,
        checked_property_count=checked,
        skipped_temporal_count=skipped,
        child_driven_signals=sorted(set(child_driven_signals)),
    )


def mock_dut_review(output_dir: str, *, tb_filename: str = "tb.sv", mock_filename: str = "mock_dut.sv", timeout_s: int = 90) -> Tuple[bool, int, str]:
    """Compile the TB against the mock DUT; count ASSERTER_FAIL markers.

    Returns (is_aligned, fail_count, raw_sim_output_json).
    """
    _require_executable("verilator")
    tb_path = f"{output_dir}/{tb_filename}"
    mock_path = f"{output_dir}/{mock_filename}"
    sim_bin = f"{output_dir}/tb_align.bin"
    if os.path.isfile(sim_bin):
        os.remove(sim_bin)

    cmd = (
        "verilator --binary -j 0 --sv --timing --assert -Wall -Wno-fatal "
        f"--Mdir obj_dir_tb_align -o {sim_bin} {tb_path} {mock_path}; "
        f"{sim_bin}"
    )
    cmd_ok, sim_output = run_bash_command(cmd, timeout=timeout_s, cwd=output_dir)
    try:
        obj = CommandResult.model_validate_json(sim_output)
        stdout = obj.stdout or ""
        stderr = obj.stderr or ""
    except Exception:  # noqa: BLE001
        stdout, stderr = sim_output, ""

    fail_count = 0
    for line in (stdout + "\n" + stderr).splitlines():
        if "ASSERTER_FAIL:" in line and _ASSERTER_FAIL_RE.search(line.strip()):
            fail_count += 1

    has_fatal = bool(re.search(r"^%Error", stdout, re.MULTILINE) or re.search(r"^%Error", stderr, re.MULTILINE))
    is_aligned = fail_count == 0 and not has_fatal
    return is_aligned, fail_count, sim_output


def _format_props_text(child_assumes: dict[str, Any], io_names: set[str]) -> str:
    blocks: list[str] = []
    for cname, ca in child_assumes.items():
        rename = _child_rename_map(io_names, cname)
        props = ca.get("properties", []) if isinstance(ca, dict) else []
        lines = [f"Child `{cname}` (signals already prefixed as `{cname}_*` in the TB):"]
        for prop in props:
            if not isinstance(prop, dict):
                continue
            body = _rename_body(str(prop.get("body", "")), rename)
            lines.append(f"  - {prop.get('name', 'prop')}: {body}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(none)"


# ---------------------------------------------------------------------------
# TB section slicer — structural mirror of trace_slicer's RTL block slicer.
# There is no VCD-backed structural analysis for a TB (it isn't itself
# simulated as a DUT); instead a lightweight parser splits the TB into
# top-level procedural blocks (initial/always*/final/task/function) and
# marks as "suspect" any that reference a child-driven signal.
# ---------------------------------------------------------------------------

_PROC_KW_RE = re.compile(
    r"^\s*(initial|always(?:_ff|_comb|_latch)?|final"
    r"|task(?:\s+automatic)?|function(?:\s+automatic)?(?:\s+\S+)?)\b",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TbSection:
    """A top-level procedural block in a testbench."""

    id: str          # e.g. "initial_0", "always_1", "task_check_outputs"
    kind: str        # "initial" | "always" | "always_ff" | "task" | "function" | ...
    start_line: int  # 1-based
    end_line: int    # 1-based, inclusive
    trigger: str     # "@(posedge clk)" etc.; empty for non-always blocks
    refs: List[str]  # identifiers referenced in this block (for suspect detection)
    code: str        # full source text of the block


def _count_depth_change(line: str) -> int:
    """Net begin-minus-end in a line (ignores strings/comments heuristically)."""
    code_part = re.sub(r"//.*", "", line)
    code_part = re.sub(r'"[^"]*"', '""', code_part)
    opens = len(re.findall(r"\bbegin\b", code_part))
    closes = len(re.findall(r"\bend\b", code_part))
    return opens - closes


def _parse_tb_sections(tb_code: str) -> list[TbSection]:
    """Parse a testbench into top-level procedural sections.

    Handles ``initial``, ``always*``, ``final``, ``task``, and ``function``
    blocks.  Task/function extent is bounded by ``endtask``/``endfunction``;
    all other blocks by ``begin``/``end`` depth tracking.
    """
    lines = tb_code.splitlines()
    n = len(lines)
    sections: list[TbSection] = []
    counters: dict[str, int] = {}

    i = 0
    while i < n:
        m = _PROC_KW_RE.match(lines[i])
        if m is None:
            i += 1
            continue

        first_word = m.group(1).split()[0]
        start = i

        if first_word in ("task", "function"):
            kind = first_word
            base = first_word
            terminator = re.compile(r".*\bend" + first_word + r"\b")
            name_m = re.search(
                r"\b(?:task|function)\s+(?:automatic\s+)?(?:\S+\s+)?(\w+)\s*[;(]",
                lines[i],
            )
            name = name_m.group(1) if name_m else None
            trigger = ""
            if terminator.match(lines[i]):
                end = i
            else:
                j = i + 1
                while j < n:
                    if terminator.match(lines[j]):
                        break
                    j += 1
                end = min(j, n - 1)
        else:
            kind = m.group(1).split()[0]
            base = "initial" if kind == "initial" else ("final" if kind == "final" else "always")
            name = None
            rest = lines[i][m.end():].strip()
            trigger = ""
            tr = re.match(r"@\s*\(([^)]*)\)", rest)
            if tr:
                trigger = f"@({tr.group(1).strip()})"
            if "begin" not in lines[i]:
                end = i
            else:
                depth = _count_depth_change(lines[i])
                if depth <= 0:
                    end = i
                else:
                    j = i + 1
                    while j < n:
                        depth += _count_depth_change(lines[j])
                        if depth <= 0:
                            break
                        j += 1
                    end = min(j, n - 1)

        code = "\n".join(lines[start : end + 1])
        refs = sorted(set(re.findall(r"\b([A-Za-z_]\w*)\b", code)))

        idx = counters.get(base, 0)
        counters[base] = idx + 1
        sid = f"{base}_{name}" if name else f"{base}_{idx}"

        sections.append(
            TbSection(
                id=sid,
                kind=kind,
                start_line=start + 1,
                end_line=end + 1,
                trigger=trigger,
                refs=refs,
                code=code,
            )
        )
        i = end + 1

    return sections


def _suspect_sections(sections: list[TbSection], driven_signals: list[str]) -> list[TbSection]:
    """Sections that reference at least one child-driven signal."""
    if not driven_signals:
        return sections
    suspects = [s for s in sections if any(sig in s.refs for sig in driven_signals)]
    return suspects if suspects else sections


def _lint_tb(tb_path: str) -> Tuple[bool, str]:
    """Verilator lint-only on the testbench in isolation.

    Missing-module errors are ignored (the mock DUT is a separate file).
    Returns (is_ok, error_excerpt).
    """
    if shutil.which("verilator") is None:
        return True, ""
    cmd = f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {tb_path}"
    _ok, raw = run_bash_command(cmd, timeout=60, cwd=str(Path(tb_path).parent))
    try:
        obj = CommandResult.model_validate_json(raw)
        text = f"{obj.stdout or ''}\n{obj.stderr or ''}"
    except Exception:  # noqa: BLE001
        text = raw
    error_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.lstrip().startswith("%Error")
        and "-MODMISSING:" not in ln
        and "Exiting due to" not in ln
    ]
    is_ok = not error_lines and "syntax error" not in text.lower()
    return is_ok, "\n".join(error_lines)


def _summarize_sim_log(sim_log_json: str, *, max_chars: int = 4000) -> str:
    try:
        obj = json.loads(sim_log_json)
        stdout = str(obj.get("stdout") or "")
        stderr = str(obj.get("stderr") or "")
    except Exception:  # noqa: BLE001
        stdout, stderr = sim_log_json, ""
    interesting = [ln for ln in stdout.splitlines() if "ASSERTER_FAIL:" in ln or "%Error" in ln]
    out = "\n".join(interesting).strip() or stdout
    if stderr.strip():
        out += "\n\n[stderr]\n" + stderr.strip()
    return clip_text(out, max_chars=max_chars)


# ---------------------------------------------------------------------------
# Session state (mirrors _EditSession in rtl_editor.py / _TBReviewSession)
# ---------------------------------------------------------------------------

@dataclass
class _TBAlignSession:
    tb_path: str
    mock_dut_path: str
    output_dir: str
    last_fail_count: int
    max_trials: int
    driven_signals: List[str] = field(default_factory=list)

    is_done: bool = False
    action_calls: int = 0
    sections_by_id: Dict[str, TbSection] | None = None
    violation_log: str = ""

    def read_tb(self) -> str:
        return Path(self.tb_path).read_text(encoding="utf-8")

    def write_tb(self, content: str) -> None:
        Path(self.tb_path).write_text(content, encoding="utf-8")

    def run_alignment_check(self) -> Dict[str, Any]:
        is_aligned, fail_count, sim_output = mock_dut_review(
            self.output_dir,
            tb_filename=os.path.basename(self.tb_path),
            mock_filename=os.path.basename(self.mock_dut_path),
        )
        self.last_fail_count = fail_count
        self.violation_log = _summarize_sim_log(sim_output)
        if is_aligned:
            self.is_done = True
        return {
            "is_aligned": is_aligned,
            "fail_count": fail_count,
            "violation_log_excerpt": self.violation_log,
        }

    def list_suspect_sections(self) -> list[dict[str, Any]]:
        if self.sections_by_id is None:
            return []
        return [
            {
                "id": s.id,
                "kind": s.kind,
                "trigger": s.trigger,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in self.sections_by_id.values()
        ]

    def read_section(self, section_id: str) -> str:
        if not self.sections_by_id or section_id not in self.sections_by_id:
            return f"ERROR: Unknown section_id '{section_id}'. Use list_suspect_sections() first."
        s = self.sections_by_id[section_id]
        lines = s.code.splitlines()
        return "\n".join(f"{s.start_line + i}: {ln}" for i, ln in enumerate(lines)) + "\n"

    def replace_section(self, section_id: str, new_code: str) -> Dict[str, Any]:
        if not self.sections_by_id or section_id not in self.sections_by_id:
            return {
                "is_action_executed": False,
                "error_msg": f"Unknown section_id '{section_id}'. Use list_suspect_sections() first.",
            }

        self.action_calls += 1
        if self.action_calls > self.max_trials:
            return {
                "is_action_executed": False,
                "error_msg": "Reached maximum alignment trials; refusing further edits.",
            }

        s = self.sections_by_id[section_id]
        old_text = self.read_tb()
        old_lines = old_text.splitlines()
        start_idx = s.start_line - 1
        end_idx = s.end_line - 1

        if start_idx < 0 or end_idx >= len(old_lines) or start_idx > end_idx:
            return {
                "is_action_executed": False,
                "error_msg": (
                    f"Section {section_id} line range {s.start_line}-{s.end_line} "
                    f"is out of bounds (TB has {len(old_lines)} lines)."
                ),
            }

        new_lines = old_lines[:start_idx] + new_code.rstrip("\n").splitlines() + old_lines[end_idx + 1:]
        new_text = "\n".join(new_lines) + ("\n" if old_text.endswith("\n") else "")
        self.write_tb(new_text)

        is_ok, lint_excerpt = _lint_tb(self.tb_path)
        if not is_ok:
            self.write_tb(old_text)
            return {
                "is_action_executed": False,
                "error_msg": f"Testbench lint error — edit rolled back.\n{lint_excerpt}",
            }

        check_result = self.run_alignment_check()
        self._refresh_sections()
        return {"is_action_executed": True, **check_result}

    def _refresh_sections(self) -> None:
        try:
            all_sections = _parse_tb_sections(self.read_tb())
            suspects = _suspect_sections(all_sections, self.driven_signals)
            self.sections_by_id = {s.id: s for s in suspects}
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = r"""You are TBEditor, an expert in SystemVerilog testbench
debugging, specialized in composition (glue) node testbenches.

Goal: use tool calls to minimally edit the testbench's INLINE CHILD
BEHAVIORAL MODEL — the always blocks/tasks that stand in for a not-yet-built
child module, driving its output ports — so that it satisfies each child's
own formal assume properties.

The DUT you simulate against is a MOCK — a stub with the same ports as the
real glue module, NOT the real glue logic. It exists only to check your
testbench's own child model in isolation, independent of whatever the real
glue RTL ends up doing. Ports the mock drives (child-input-mapped, e.g. the
signals a real glue would send toward a child) are randomized per cycle to
exercise your model broadly. Ports your testbench drives (child-output-mapped
— what a real child would produce) are the ones checked against each child's
assume properties as runtime `assert` statements inside the mock.

Rules:
1. Do NOT modify the mock DUT.
2. Do NOT change stimulus for the TOP-LEVEL external ports (clk/rst/start/
   A/B/etc.) — leave that untouched.
3. Do NOT change the testbench's checking logic for the module's OWN
   (parent/glue) contract SVA or scoreboard — leave that untouched.
4. Only edit the inline child behavioral model sections that drive
   child-output-mapped ports (the ones named in the violated properties).
5. Verilator target: keep the TB compatible (no unsupported SVA, prefer
   simple procedural assertions and $past()).

When done, finish by calling generate_response with a structured plain-string
response in EXACTLY this format:

  If you fixed the child model:
    generate_response(response="TB_ALIGNED: <one-line summary of what you changed>\nPROPERTY: <the specific child assumption the original model violated>\nFIX_RATIONALE: <how the change now satisfies it>")

  If you believe the property itself is unsatisfiable as stated (rare):
    generate_response(response="PROPERTY_SUSPECT: <one-line summary>\nPROPERTY: <the property>\nREASON: <why it looks unsatisfiable>")

The `response` argument MUST be a plain string (not JSON, not a dict).
"""

_INIT_PROMPT = r"""The information below is given to help your repair:
1. The child assume properties (already renamed to the prefixed signal names
   used in this testbench, e.g. `booth_controller_ready`) — SOURCE OF TRUTH
   for what your inline child model must satisfy;
2. The current violation log from running the testbench against the mock DUT.

<child_assume_properties>
{props_text}
</child_assume_properties>

<violation_log_excerpt>
{violation_log_excerpt}
</violation_log_excerpt>
"""

_EXTRA_ORDER_PROMPT = r"""
Workflow (repeat until done):
1) Read the violation log to see which properties are failing.
2) Call list_suspect_sections() to see which TB blocks reference the
   child-driven signals involved in those properties.
3) Call read_section(section_id) for the most relevant one.
4) Make ONE small targeted change via replace_section(section_id, new_code).
5) Call run_alignment_check() and iterate.

Use tools:
- list_suspect_sections()
- read_section(section_id)
- replace_section(section_id, new_code)
- run_alignment_check()

When all properties hold (or you conclude a property is unsatisfiable), call
generate_response using the structured format from the system prompt.
"""

_CONTINUE_MSG = (
    "Continue aligning. If violations remain, pick 1 suspect section and call "
    "read_section(section_id), then call replace_section(section_id, new_code) "
    "once, then run_alignment_check()."
)


def _response_is_terminal(msg: Any) -> bool:
    content = str(getattr(msg, "content", "") or "")
    return bool(re.search(r"\bTB_ALIGNED\b|\bPROPERTY_SUSPECT\b", content))


# ---------------------------------------------------------------------------
# TBEditor agent
# ---------------------------------------------------------------------------

class TBEditor:
    """Iteratively aligns a testbench's inline child model to child_assumes SVA.

    Structural mirror of RTLEditor: same four-tool API shape, same session
    dataclass shape, same chat() procedure (first prompt + bounded loop with
    a sliding memory window and stall detection). Where RTLEditor holds the
    testbench frozen and edits RTL blocks, TBEditor holds a mock DUT frozen
    and edits TB sections.
    """

    def __init__(
        self,
        cfg: OpenAIConfig,
        *,
        max_trials: int = 15,
        memory_window: int = 6,
        stall_rounds: int = 2,
    ) -> None:
        self._cfg = cfg
        self.max_trials = int(max_trials)
        self._memory_window = int(memory_window)
        self._stall_rounds = max(1, int(stall_rounds))
        self._session: _TBAlignSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_suspect_sections)
        toolkit.register_tool_function(self._tool_read_section)
        toolkit.register_tool_function(self._tool_replace_section)
        toolkit.register_tool_function(self._tool_run_alignment_check)

        self._agent = SafeReActAgent(
            name="TBEditor",
            sys_prompt=_SYSTEM_PROMPT,
            model=make_openai_model(cfg),
            formatter=make_formatter(cfg.model),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def reset(self) -> None:
        clear_memory_safely(self._agent)
        self._session = None

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def _tool_list_suspect_sections(self) -> ToolResponse:
        """List TB sections that reference child-driven signals named in violated properties."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        sections = self._session.list_suspect_sections()
        return ToolResponse(content=[{"type": "text", "text": json.dumps(sections, indent=2)}])

    async def _tool_read_section(self, section_id: str) -> ToolResponse:
        """Read a TB section by section_id with 1-based line numbers."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        return ToolResponse(content=[{"type": "text", "text": self._session.read_section(section_id)}])

    async def _tool_replace_section(self, section_id: str, new_code: str) -> ToolResponse:
        """Replace a TB section, lint-check, re-check alignment (rollback on lint failure)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        result = await asyncio.to_thread(self._session.replace_section, section_id, new_code)
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_run_alignment_check(self) -> ToolResponse:
        """Run the mock-DUT alignment check; returns pass/fail and violation count."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        result = await asyncio.to_thread(self._session.run_alignment_check)
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    # ------------------------------------------------------------------
    # Main entry point (mirrors RTLEditor.chat)
    # ------------------------------------------------------------------

    async def chat(
        self,
        *,
        contract_json: str,
        tb_code: str,
        output_dir_per_run: str,
        max_trials: int | None = None,
    ) -> Tuple[bool, str, int, str]:
        """Returns (is_aligned, tb_code, used_trials, justification)."""
        self.reset()
        try:
            contract_obj = json.loads(contract_json)
        except Exception:  # noqa: BLE001
            return False, tb_code, 0, "contract_json did not parse; TB alignment skipped"

        child_assumes = contract_obj.get("child_assumes", {})
        if not isinstance(child_assumes, dict) or not child_assumes:
            return True, tb_code, 0, "no child_assumes present; TB alignment skipped"

        io = contract_obj.get("io", [])
        io_names = {p["name"] for p in io if isinstance(p, dict) and p.get("name")} if isinstance(io, list) else set()

        mock = build_mock_dut(contract_obj, child_assumes)
        if mock.checked_property_count == 0:
            return True, tb_code, 0, "no checkable (non-temporal) child properties; TB alignment skipped"

        session_max = int(max_trials) if max_trials is not None else self.max_trials
        if session_max < 0:
            session_max = 0

        tb_path = os.path.join(output_dir_per_run, "tb.sv")
        mock_path = os.path.join(output_dir_per_run, "mock_dut.sv")
        Path(mock_path).write_text(mock.mock_dut_sv, encoding="utf-8")
        Path(tb_path).write_text(tb_code, encoding="utf-8")

        all_sections = _parse_tb_sections(tb_code)
        suspects = _suspect_sections(all_sections, mock.child_driven_signals)

        self._session = _TBAlignSession(
            tb_path=tb_path,
            mock_dut_path=mock_path,
            output_dir=str(output_dir_per_run),
            last_fail_count=0,
            max_trials=session_max,
            driven_signals=mock.child_driven_signals,
            sections_by_id={s.id: s for s in suspects},
        )

        try:
            check = self._session.run_alignment_check()
        except FileNotFoundError as e:
            return False, tb_code, 0, f"TB alignment skipped: {e}"

        if self._session.is_done:
            return True, self._session.read_tb(), 0, (
                f"Initial TB already aligned with {mock.checked_property_count} child properties "
                f"({mock.skipped_temporal_count} skipped as non-immediate-expressible)."
            )

        props_text = _format_props_text(child_assumes, io_names)
        first_prompt = (
            f"{_INIT_PROMPT.format(props_text=props_text, violation_log_excerpt=check['violation_log_excerpt'])}\n\n"
            f"{_EXTRA_ORDER_PROMPT}\n\n"
            "Start by calling list_suspect_sections(), then read_section(section_id) "
            "for the most relevant one, then apply one replace_section(section_id, new_code), "
            "then run_alignment_check()."
        )
        try:
            Path(output_dir_per_run, "tb_align_prompt.txt").write_text(first_prompt + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

        _justification: str = ""
        _last_content: str = ""

        stall_count = 0
        prev_fail_for_stall = int(self._session.last_fail_count)

        def _update_stall_tracking() -> None:
            nonlocal stall_count, prev_fail_for_stall
            if self._session.last_fail_count < prev_fail_for_stall:
                stall_count = 0
            else:
                stall_count += 1
            prev_fail_for_stall = self._session.last_fail_count

        response = await self._agent(Msg("user", first_prompt, role="user"))
        _last_content = str(getattr(response, "content", "") or "")
        if self._session.is_done or _response_is_terminal(response):
            _justification = _last_content
        else:
            _update_stall_tracking()

        for _ in range(session_max):
            if self._session.is_done:
                break
            if self._session.action_calls >= self._session.max_trials:
                break
            if stall_count >= self._stall_rounds:
                break
            mem = self._agent.memory
            window = self._memory_window
            if window > 0 and len(mem.content) > window + 2:
                mem.content = [mem.content[0]] + mem.content[-(window):]
            response = await self._agent(Msg("user", _CONTINUE_MSG, role="user"))
            _last_content = str(getattr(response, "content", "") or "")
            if (self._session.is_done or _response_is_terminal(response)) and not _justification:
                _justification = _last_content
            if not self._session.is_done:
                _update_stall_tracking()

        if not _justification:
            for kw in ("TB_ALIGNED:", "PROPERTY_SUSPECT:"):
                idx = _last_content.find(kw)
                if idx != -1:
                    _justification = _last_content[idx:].strip()
                    break
        if not _justification:
            _justification = f"Exhausted budget; last violation count: {self._session.last_fail_count}."

        tb_code_out = self._session.read_tb()
        used = int(getattr(self._session, "action_calls", 0) or 0)
        return self._session.is_done, tb_code_out, used, _justification
