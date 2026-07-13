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
from .sim_reviewer import _has_multidriven_warning, _require_executable
from .trace_slicer import _extract_writes as _extract_rtl_writes
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


_PAST_RE = re.compile(r"\$past\(\s*(\w+)")


def _extract_prop_signal_refs(sim_body: str, io_names: set[str]) -> list[str]:
    """Identifier tokens in an (already-renamed) property body that are actual
    mock-DUT port names — filters out numeric literals, $past/$isunknown etc.,
    and local names. Called AFTER _rename_body, so short child-local names are
    already prefixed and directly comparable against io_names.

    Used to enrich the assert-failure message with concrete runtime values —
    the adapted analog of RTLEditor's (expected, actual) value pairs. TBEditor
    has no second oracle trace to diff against (this is a boolean assert-fired
    check, not a value-mismatch check against a golden reference), so a VCD-
    based alignment diagnosis isn't meaningful here; reporting what the
    referenced signals actually held at fail time is the adapted equivalent.
    """
    tokens = set(re.findall(r"\b([A-Za-z_]\w*)\b", sim_body))
    return sorted(t for t in tokens if t in io_names)


def _extract_prop_past_refs(sim_body: str, io_names: set[str]) -> list[str]:
    """Ports referenced via $past(...) in an already-renamed property body."""
    tokens = set(_PAST_RE.findall(sim_body))
    return sorted(t for t in tokens if t in io_names)


def _fmt_spec(width: Any) -> str:
    try:
        wi = int(width)
    except (TypeError, ValueError):
        wi = 1
    return "%0b" if wi <= 1 else "%0h"


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

    # The mock must be a drop-in for the real module INCLUDING its parameter
    # port list: the TB instantiates it as `<module> #(.N(N)) dut (...)`, and
    # Verilator rejects a parameter override on a module that declares none.
    # (Observed live: alignment surrendered on exactly this compile error while
    # the TB's own child model went unchecked.)
    param_lines: list[str] = []
    params = contract_obj.get("parameters", [])
    if isinstance(params, list):
        for pr in params:
            if not isinstance(pr, dict) or not pr.get("name"):
                continue
            ptype = str(pr.get("type") or "int").strip() or "int"
            if ptype in ("string",):
                default = pr.get("default", '""')
            else:
                default = pr.get("default", "0")
            param_lines.append(f"  parameter {ptype} {pr['name']} = {default}")

    if param_lines:
        lines: list[str] = [f"module {module_name} #("]
        lines.append(",\n".join(param_lines))
        lines.append(") (")
    else:
        lines = [f"module {module_name} ("]
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

    io_width_by_name = {p["name"]: p.get("width", 1) for p in io if isinstance(p, dict) and p.get("name")}

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

            # Value-enriched failure message — the adapted analog of RTLEditor's
            # (expected, actual) value pairs (see _extract_prop_signal_refs).
            ref_signals = _extract_prop_signal_refs(sim_body, io_names)
            past_signals = _extract_prop_past_refs(sim_body, io_names)
            value_parts: list[str] = []
            value_args: list[str] = []
            for sig in ref_signals:
                value_parts.append(f"{sig}={_fmt_spec(io_width_by_name.get(sig, 1))}")
                value_args.append(sig)
            for sig in past_signals:
                value_parts.append(f"$past({sig})={_fmt_spec(io_width_by_name.get(sig, 1))}")
                value_args.append(f"$past({sig})")
            if value_parts:
                fmt_str = "child assumption violated: " + " ".join(value_parts)
                msg_expr = "$sformatf(" + ", ".join([f'"{fmt_str}"'] + value_args) + ")"
            else:
                msg_expr = '"child assumption violated"'

            lines.append(f"  // assume-as-assert: {cname}.{name}")
            lines.append(f"  always @({clk_edge} {p_clk}) if (!{p_rst}) begin")
            lines.append(f'    assert ({sim_body}) else asserter_log("{cname}.{name}", {msg_expr});')
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
    writes: List[str]  # identifiers this block WRITES (<= or = LHS) — dataflow slicing
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
        writes = sorted(_extract_rtl_writes(code))

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
                writes=writes,
                code=code,
            )
        )
        i = end + 1

    return sections


_MODULE_HDR_RE = re.compile(r"^\s*module\s+\w+")
_DECL_LINE_RE = re.compile(
    r"^\s*(parameter|localparam|logic|reg|wire|int|integer|bit|time"
    r"|byte|shortint|longint|real|string)\b"
)
_COMMENT_OR_BLANK_RE = re.compile(r"^\s*(//.*)?$")


def _find_declarations_section(
    tb_code: str, first_proc_start_line: int | None
) -> TbSection | None:
    """The module-scope declaration block, exposed as its own editable section.

    Neither TBEditor's ``_parse_tb_sections`` nor RTLEditor's
    ``trace_slicer.parse_rtl_blocks`` treats bare declarations (outside any
    always/initial/task/function) as an editable region — both only recognize
    procedural blocks. Observed live: a repair that needed a new edge-detect
    register (to resolve a genuine cross-block FSM/timing coupling) had no
    section to declare it in, and was twice rejected by _lint_tb as an
    "undeclared variable" error — the model correctly diagnosed the fix but
    had no reachable place to put it. This exposes the declaration block
    (module header -> first procedural section) as its own section so
    replace_section can extend it; any dangling reference left by removing a
    still-used declaration is caught by the existing _lint_tb rollback gate,
    same safety net every other section already relies on.
    """
    lines = tb_code.splitlines()
    n = len(lines)
    hdr_idx = next((i for i, ln in enumerate(lines) if _MODULE_HDR_RE.match(ln)), None)
    if hdr_idx is None:
        return None

    depth = 0
    header_end = None
    for j in range(hdr_idx, n):
        depth += lines[j].count("(") - lines[j].count(")")
        if depth <= 0 and ";" in lines[j]:
            header_end = j
            break
    if header_end is None:
        return None

    start = header_end + 1
    limit = min(first_proc_start_line - 1, n) if first_proc_start_line is not None else n

    end = start - 1
    saw_decl = False
    for k in range(start, limit):
        line = lines[k]
        if _DECL_LINE_RE.match(line):
            saw_decl = True
            end = k
        elif _COMMENT_OR_BLANK_RE.match(line):
            continue
        else:
            break

    if not saw_decl or end < start:
        return None

    code = "\n".join(lines[start : end + 1])
    refs = sorted(set(re.findall(r"\b([A-Za-z_]\w*)\b", code)))
    return TbSection(
        id="declarations",
        kind="declarations",
        start_line=start + 1,
        end_line=end + 1,
        trigger="",
        refs=refs,
        writes=[],
        code=code,
    )


def _suspect_sections(sections: list[TbSection], driven_signals: list[str]) -> list[TbSection]:
    """Sections that reference at least one child-driven signal.

    Coarse fallback selector: used only when property-seeded slicing
    (``_tb_backward_slice``) has no seed signals to work from (e.g. a fatal
    compile error line with no parseable property id) — see ``_refresh_sections``.
    """
    if not driven_signals:
        return sections
    suspects = [s for s in sections if any(sig in s.refs for sig in driven_signals)]
    return suspects if suspects else sections


def _build_tb_driver_map(sections: list[TbSection]) -> Dict[str, list[TbSection]]:
    """signal -> sections that WRITE it. Direct structural port of
    trace_slicer.build_driver_map, adapted to TbSection.
    """
    drivers: Dict[str, list[TbSection]] = {}
    for s in sections:
        for w in s.writes:
            drivers.setdefault(w, []).append(s)
    return drivers


def _tb_backward_slice(
    *,
    seed_signals: list[str],
    drivers: Dict[str, list[TbSection]],
    continuous_drivers: Dict[str, "_ContinuousDriver"] | None = None,
    max_depth: int = 3,
) -> list[TbSection]:
    """Coarse backward slice from seed signals via the TB driver graph.

    Direct structural port of trace_slicer.dynamic_slice: instead of a blanket
    "does this section merely MENTION a child-driven signal" filter
    (_suspect_sections), this walks backward from the SPECIFIC signals the
    currently-violated property references, through what each driving
    section itself reads (refs minus its own writes), the same way RTLEditor's
    suspect blocks are causally linked to the specific failing output rather
    than to every output the RTL happens to touch.

    A seed/frontier signal is very often the PORT itself (e.g.
    ``booth_controller_ready``), which is typically driven by a continuous
    ``assign <port> = <shadow_reg>;`` (see _find_continuous_drivers), not
    directly by a procedural section — build_driver_map only tracks
    PROCEDURAL writes, so without this, the walk dead-ends at the port and
    never reaches the always-block that actually drives the shadow register.
    When a frontier signal has a continuous (not procedural) driver, the walk
    continues through that assign's RHS identifiers instead of stopping —
    the continuous-assign line itself is never added as a "section" (it isn't
    editable via replace_section; _driver_conflict_notes already handles
    surfacing it to the model separately).
    """
    continuous_drivers = continuous_drivers or {}
    frontier = set(seed_signals)
    seen_signals = set(frontier)
    seen_sections: dict[str, TbSection] = {}

    for _ in range(max(1, int(max_depth))):
        next_frontier: set[str] = set()
        for sig in frontier:
            for section in drivers.get(sig, []):
                seen_sections[section.id] = section
                reads = set(section.refs) - set(section.writes)
                for r in reads:
                    if r not in seen_signals:
                        seen_signals.add(r)
                        next_frontier.add(r)
            cd = continuous_drivers.get(sig)
            if cd is not None:
                for r in re.findall(r"\b([A-Za-z_]\w*)\b", cd.rhs):
                    if r not in seen_signals:
                        seen_signals.add(r)
                        next_frontier.add(r)
        frontier = next_frontier
        if not frontier:
            break

    return list(seen_sections.values())


def _violated_property_signals(
    violation_log: str, child_assumes: dict[str, Any], io_names: set[str],
) -> list[str]:
    """Signals referenced by the property(ies) currently failing, per the
    violation log's ``ASSERTER_FAIL: <cname>.<pname> t=...`` lines — the seed
    set for ``_tb_backward_slice``. Falls back to an empty list (letting the
    caller fall back to the blanket ``_suspect_sections`` filter) when no
    property id is parseable, e.g. a fatal compile error with no assertions
    reached yet.
    """
    signals: set[str] = set()
    for m in _ASSERTER_FAIL_RE.finditer(violation_log):
        prop_id = m.group("id")
        if "." not in prop_id:
            continue
        cname, pname = prop_id.split(".", 1)
        ca = child_assumes.get(cname)
        if not isinstance(ca, dict):
            continue
        rename = _child_rename_map(io_names, cname)
        for prop in ca.get("properties", []) or []:
            if not isinstance(prop, dict) or prop.get("name") != pname:
                continue
            body = _rename_body(str(prop.get("body", "")), rename)
            signals.update(_extract_prop_signal_refs(body, io_names))
            signals.update(_extract_prop_past_refs(body, io_names))
    return sorted(signals)


_ASSIGN_RE = re.compile(r"^\s*assign\s+(\w+)\s*=\s*(.+?);\s*$", re.MULTILINE)


@dataclass(frozen=True)
class _ContinuousDriver:
    line: int   # 1-based
    rhs: str    # the exact expression on the assign's right-hand side


def _find_continuous_drivers(tb_code: str) -> Dict[str, _ContinuousDriver]:
    """Map signal -> its (first) continuous ``assign``'s line and RHS.

    ``_parse_tb_sections`` only recognizes procedural blocks (initial/always/
    task/function); a bare ``assign x = y;`` at module scope is invisible to
    it. Without this, a repair that must satisfy a property named after a
    port that already has a continuous driver elsewhere has no way to know
    that — it writes a NEW procedural driver for the same port and creates a
    multi-driver conflict (observed live: booth_reset_coherent, multiple
    live drives, always on `<child>_iteration_complete`-shaped signals).
    Lint-and-rollback catches the resulting BLKANDNBLK error, but the model
    then has nothing new to act on and just repeats the same mistake until
    it stalls — because the pre-existing driver was never shown to it.

    Capturing the RHS (not just the line number) matters: a first version of
    this note only pointed at the line ("go see what it reads from"), but a
    bare `assign` line isn't a readable section either — the model correctly
    avoided the multi-driver conflict but then stalled anyway, unable to
    dereference its own pointer (observed live, bundle 20260709T190451Z:
    "without access to the specific assign statements at lines 97 and 119...
    I cannot provide the precise fix"). Naming the RHS directly removes that
    second hop.
    """
    lines = tb_code.splitlines()
    drivers: Dict[str, _ContinuousDriver] = {}
    for i, line in enumerate(lines):
        m = _ASSIGN_RE.match(line)
        if m and m.group(1) not in drivers:
            drivers[m.group(1)] = _ContinuousDriver(line=i + 1, rhs=m.group(2).strip())
    return drivers


def _driver_conflict_notes(
    section: TbSection,
    continuous_drivers: Dict[str, _ContinuousDriver],
    driven_signals: list[str],
    driver_map: Dict[str, list["TbSection"]] | None = None,
) -> list[str]:
    """Warn about child-driven signals this section references that already
    have a continuous driver elsewhere — the fix belongs on the driver's
    source (typically a shadow reg), not a second direct write to the port.

    ``driver_map`` (signal -> sections that WRITE it, built over ALL sections
    in the file, not just the suspect-filtered subset — the true driving
    section may not itself reference a child-driven port and so wouldn't be
    classified "suspect") lets this name WHICH section already writes the
    shadow register, not just its name. Observed live, twice: the model saw
    "write to controller_ready_reg" and, with no pointer to WHERE that
    register is already written, added a brand-new, redundant driver for it
    inside the section it happened to be looking at — producing a real
    MULTIDRIVEN conflict on the shadow register itself, repeating the mistake
    before exhausting its budget. Four cases, verified against a real archived
    fixture (tests/stage_eval/fixtures/authored/tb_lint_multidriven_cross_file/):
    no existing writer (legitimately new — must not claim a nonexistent
    section), a single writer that IS this section (extend in place, not a
    circular pointer), a single writer elsewhere (name it, tell the model to
    read_section it first), and multiple writers (a pre-existing multi-driver
    condition independent of this edit — confirmed this genuinely occurs in
    that fixture; needs its own cautious phrasing, not an arbitrary pick).
    """
    notes: list[str] = []
    for sig in sorted(set(section.refs) & set(driven_signals) & continuous_drivers.keys()):
        d = continuous_drivers[sig]
        pointer = ""
        if driver_map is not None:
            writers = [s.id for s in driver_map.get(d.rhs, [])]
            if not writers:
                pointer = f" (no existing section writes `{d.rhs}` yet — write it here.)"
            elif len(writers) == 1 and writers[0] == section.id:
                pointer = f" `{d.rhs}` is already written IN THIS SECTION — extend the existing logic, do not add a second driver."
            elif len(writers) == 1:
                pointer = (
                    f" `{d.rhs}` is already written in section `{writers[0]}` — call "
                    f"read_section('{writers[0]}') to see its current logic and extend "
                    f"it there; do not add a new driver here."
                )
            else:
                pointer = (
                    f" `{d.rhs}` is ALREADY written in MULTIPLE sections "
                    f"({', '.join(writers)}) — this is already a multi-driver conflict "
                    f"independent of your edit; consider which of those sections' "
                    f"writes should be removed rather than adding a third."
                )
        notes.append(
            f"NOTE: '{sig}' already has a continuous driver at line {d.line} "
            f"(`assign {sig} = {d.rhs};`). Do NOT add another procedural driver "
            f"for '{sig}' itself in this section — that creates a multi-driver "
            f"conflict. Instead, write to `{d.rhs}` (the shadow register the "
            f"assign reads from).{pointer}"
        )
    return notes


def _expand_with_pointed_sections(
    suspects: list[TbSection],
    *,
    continuous_drivers: Dict[str, _ContinuousDriver],
    driven_signals: list[str],
    driver_map: Dict[str, list[TbSection]],
) -> list[TbSection]:
    """Union in every section a driver-conflict note would point at, so
    ``read_section``/``replace_section`` can actually reach it.

    Bug this fixes, observed live: the note correctly named an existing
    driver's section (e.g. "already written in section `always_0` — call
    read_section('always_0')"), the model followed that instruction exactly,
    and got back "ERROR: Unknown section_id 'always_0'" — because
    ``driver_map`` is built over ALL sections (so it can compute a correct
    pointer even for a non-suspect section), but ``sections_by_id`` (what the
    tools actually expose) was still the suspect-filtered subset alone. A
    note that points somewhere the tools then refuse to go is worse than no
    pointer at all — it burns real trials on the discovery. Fix: for every
    suspect section, for every driven signal it references with a continuous
    driver, pull in whichever section(s) actually write that driver's shadow
    register.
    """
    expanded: dict[str, TbSection] = {s.id: s for s in suspects}
    for s in suspects:
        for sig in set(s.refs) & set(driven_signals) & continuous_drivers.keys():
            rhs = continuous_drivers[sig].rhs
            for writer in driver_map.get(rhs, []):
                expanded[writer.id] = writer
    return list(expanded.values())


def _lint_tb(tb_path: str, mock_dut_path: str | None = None) -> Tuple[bool, str]:
    """Verilator lint-only on the testbench (plus the mock DUT, if given).

    Missing-module errors are ignored (relevant when mock_dut_path is None).
    Also rejects %Warning-MULTIDRIVEN (see sim_reviewer._has_multidriven_warning):
    an edit that leaves a signal driven by two blocks with different clocking
    is a genuine correctness defect, not a style nit — observed live accepting
    such an edit that didn't fix the target property and left the TB
    architecturally worse, silently consuming a repair trial for nothing.
    build_mock_dut's own generated scaffolding never legitimately produces
    this warning (verified: every generated driver is single-source), so
    there is no benign case here to protect against, unlike RTLEditor's
    glue-RTL path (sim_reviewer.check_syntax deliberately does NOT apply this
    same tightening — see that function's docstring).

    IMPORTANT: linting tb_path alone (without mock_dut_path) MISSES some
    MULTIDRIVEN cases that the full --binary build (mock_dut_review) does
    catch — verified directly: `--lint-only` on tb.sv in isolation cannot
    fully elaborate the design without the DUT instantiation resolved, so a
    real cross-block driver conflict silently produced ZERO warnings, while
    the exact same source linted together with mock_dut.sv (or built via
    --binary) correctly reports it. An edit that introduced this passed
    _lint_tb's gate and was wrongly accepted as fully aligned in a live replay
    before mock_dut_path was threaded through here — always pass it.
    Returns (is_ok, error_excerpt).
    """
    if shutil.which("verilator") is None:
        return True, ""
    srcs = f"{tb_path} {mock_dut_path}" if mock_dut_path else tb_path
    cmd = f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {srcs}"
    _ok, raw = run_bash_command(cmd, timeout=60, cwd=str(Path(tb_path).parent))
    try:
        obj = CommandResult.model_validate_json(raw)
        stdout, stderr = obj.stdout or "", obj.stderr or ""
        text = f"{stdout}\n{stderr}"
    except Exception:  # noqa: BLE001
        stdout, stderr = raw, ""
        text = raw
    error_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.lstrip().startswith("%Error")
        and "-MODMISSING:" not in ln
        and "Exiting due to" not in ln
    ]
    has_multidriven = _has_multidriven_warning(stdout, stderr)
    multidriven_lines = (
        [ln.strip() for ln in text.splitlines() if ln.lstrip().startswith("%Warning-MULTIDRIVEN")]
        if has_multidriven
        else []
    )
    is_ok = not error_lines and not has_multidriven and "syntax error" not in text.lower()
    return is_ok, "\n".join(error_lines + multidriven_lines)


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
    continuous_drivers: Dict[str, "_ContinuousDriver"] = field(default_factory=dict)
    # signal -> sections that WRITE it, over ALL sections in the file (not just
    # the suspect-filtered subset — see _driver_conflict_notes). Lets a note
    # name WHICH section already drives a shadow register, not just its name.
    driver_map: Dict[str, list["TbSection"]] = field(default_factory=dict)
    # Needed to re-derive violated_signals (below) from a fresh violation log.
    child_assumes: Dict[str, Any] = field(default_factory=dict)
    io_names: "set[str]" = field(default_factory=set)

    is_done: bool = False
    action_calls: int = 0
    sections_by_id: Dict[str, TbSection] | None = None
    violation_log: str = ""
    # Signals referenced by the CURRENTLY failing property(ies) — the seed set
    # for property-seeded suspect selection (_tb_backward_slice), recomputed
    # every time violation_log refreshes. Empty when no property id was
    # parseable (e.g. a fatal compile error before any assertion ran), in
    # which case _refresh_sections falls back to the blanket driven_signals
    # filter (_suspect_sections) — same "never return an empty list" guarantee
    # that filter already had on its own.
    violated_signals: List[str] = field(default_factory=list)
    # Snapshot of tb.sv text at its lowest-ever fail_count, so a regression
    # can be cheaply undone (revert_to_best) instead of costing several
    # trials of blind rediscovery. Observed live, twice, independently: the
    # model reaches a genuinely better state, then a later edit regresses it
    # and the better design (and the reasoning behind it) is never
    # recovered — e.g. a correct multi-cycle datapath model built over two
    # trials, discarded one trial later for a worse one-shot rewrite.
    best_fail_count: int | None = None
    best_tb_text: str | None = None

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
        self.violated_signals = _violated_property_signals(
            self.violation_log, self.child_assumes, self.io_names
        )
        if self.best_fail_count is None or fail_count < self.best_fail_count:
            self.best_fail_count = fail_count
            self.best_tb_text = self.read_tb()
        if is_aligned:
            self.is_done = True
        return {
            "is_aligned": is_aligned,
            "fail_count": fail_count,
            "violation_log_excerpt": self.violation_log,
        }

    def revert_to_best(self) -> Dict[str, Any]:
        """Restore tb.sv to its lowest-ever-fail_count snapshot and re-check.

        Costs a trial like replace_section does (action_calls increments) —
        cheap recovery, not a free exploration loop.
        """
        self.action_calls += 1
        if self.action_calls > self.max_trials:
            return {
                "is_action_executed": False,
                "error_msg": "Reached maximum alignment trials; refusing further edits.",
            }
        if self.best_tb_text is None:
            return {
                "is_action_executed": False,
                "error_msg": "No best-known state recorded yet (run_alignment_check hasn't run).",
            }
        if self.read_tb() == self.best_tb_text:
            return {
                "is_action_executed": False,
                "error_msg": f"Already at the best-known state (fail_count={self.best_fail_count}).",
            }
        self.write_tb(self.best_tb_text)
        check_result = self.run_alignment_check()
        self._refresh_sections()
        return {"is_action_executed": True, **check_result}

    def list_suspect_sections(self) -> list[dict[str, Any]]:
        if self.sections_by_id is None:
            return []
        result = []
        for s in self.sections_by_id.values():
            entry: dict[str, Any] = {
                "id": s.id,
                "kind": s.kind,
                "trigger": s.trigger,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            notes = (
                _driver_conflict_notes(s, self.continuous_drivers, self.driven_signals, self.driver_map)
                if s.kind != "declarations"
                else []
            )
            if notes:
                entry["notes"] = notes
            result.append(entry)
        return result

    def read_section(self, section_id: str) -> str:
        if not self.sections_by_id or section_id not in self.sections_by_id:
            return f"ERROR: Unknown section_id '{section_id}'. Use list_suspect_sections() first."
        s = self.sections_by_id[section_id]
        lines = s.code.splitlines()
        body = "\n".join(f"{s.start_line + i}: {ln}" for i, ln in enumerate(lines)) + "\n"
        notes = (
            _driver_conflict_notes(s, self.continuous_drivers, self.driven_signals, self.driver_map)
            if s.kind != "declarations"
            else []
        )
        if notes:
            body = "\n".join(notes) + "\n\n" + body
        return body

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

        is_ok, lint_excerpt = _lint_tb(self.tb_path, self.mock_dut_path)
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
            tb_text = self.read_tb()
            all_sections = _parse_tb_sections(tb_text)
            continuous_drivers = _find_continuous_drivers(tb_text)
            # Built over ALL sections (not just the suspect subset) so
            # _driver_conflict_notes can find the true driving section even
            # when it isn't itself "suspect" (references no child-driven
            # port directly). Was previously only computed inside the
            # `if self.violated_signals:` branch below and discarded — hoisted
            # here so it's always available and persisted on self.
            drivers = _build_tb_driver_map(all_sections)
            suspects: list[TbSection] = []
            if self.violated_signals:
                suspects = _tb_backward_slice(
                    seed_signals=self.violated_signals,
                    drivers=drivers,
                    continuous_drivers=continuous_drivers,
                )
            if not suspects:
                # No violated-property signals parseable yet (or the slice found
                # nothing), or no property has failed at all — fall back to the
                # coarse "mentions a child-driven signal" filter, which itself
                # falls back to ALL sections if even that finds nothing. Never
                # returns an empty suspect list.
                suspects = _suspect_sections(all_sections, self.driven_signals)
            suspects = _expand_with_pointed_sections(
                suspects,
                continuous_drivers=continuous_drivers,
                driven_signals=self.driven_signals,
                driver_map=drivers,
            )
            # Always reachable, not suspect-filtered: a fix needing new
            # persistent state (an edge-detect register, a shadow counter)
            # has to be able to find this section without it ever showing up
            # as "referencing a child-driven signal" on its own merits.
            decl_start = min((s.start_line for s in all_sections), default=None)
            decl_section = _find_declarations_section(tb_text, decl_start)
            if decl_section is not None:
                suspects = [*suspects, decl_section]
            self.sections_by_id = {s.id: s for s in suspects}
            self.continuous_drivers = continuous_drivers
            self.driver_map = drivers
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = r"""You are TBEditor, an expert in SystemVerilog testbench
debugging, specialized in composition (glue) node testbenches.

Goal: use tool calls to edit the testbench's INLINE CHILD BEHAVIORAL MODEL —
the always blocks/tasks that stand in for a not-yet-built child module,
driving its output ports — so that it satisfies each child's own formal
assume properties. Prefer a small, targeted change when the bug is local; if
a section's current approach is fundamentally the wrong design for the
property (not just a local mistake), rewrite that section's logic coherently
rather than patching around a design that can't work — do not water down a
proper fix just to keep the diff small.

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
5a. If a fix needs NEW persistent state (e.g. an edge-detect register to
   distinguish "signal held from before" vs. "signal just asserted", a
   shadow counter, etc.), a 'declarations' section is available:
   read_section('declarations') to see the existing module-scope
   declarations, then replace_section('declarations', ...) to add your new
   one there before wiring it up in the relevant always block. Do not try to
   reference a register you never declared anywhere — that is a lint error
   and wastes a trial.
5b. If replace_section's result shows fail_count went UP compared to the
   check before it (a regression), do not try to manually reconstruct the
   previous design from memory — call revert_to_best() to cheaply restore
   the testbench to its own best-ever state (lowest fail_count reached so
   far this session) before trying a different edit.
6. Always respect the alignment check result. Keep repairing as long as
   violations exist — do not conclude PROPERTY_SUSPECT as a first resort.

When done, finish by calling generate_response with a structured plain-string
response in EXACTLY this format:

  If you fixed the child model:
    generate_response(response="TB_ALIGNED: <one-line summary of what you changed>\nPROPERTY: <the specific child assumption the original model violated>\nFIX_RATIONALE: <how the change now satisfies it>")

  If you believe the property itself is unsatisfiable as stated (rare — only
  after real attempts, not as a first resort):
    generate_response(response="PROPERTY_SUSPECT: <one-line summary>\nPROPERTY: <the property>\nREASON: <why it looks unsatisfiable>\nATTEMPTED: <the distinct edits you already tried via replace_section and what happened to each>")
    You must have already made at least 2 distinct replace_section attempts
    targeting this property's signals, with the violation persisting unchanged
    or worsening after both, before this response will be accepted. Citing
    fewer than 2 real attempts will be rejected and you will be asked to try
    a real edit first.

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
4) Make a targeted change via replace_section(section_id, new_code) — small
   if you're fixing a local bug, a coherent rewrite of that section if its
   current design can't satisfy the property at all. If the fix needs new
   persistent state, use replace_section('declarations', ...) first (see
   system prompt rule 5a) rather than referencing an undeclared register.
5) Call run_alignment_check() and iterate.

Use tools:
- list_suspect_sections()
- read_section(section_id)
- replace_section(section_id, new_code)  # section_id may be 'declarations'
- run_alignment_check()
- revert_to_best()  # restore your own best-ever state after a regression

When all properties hold (or you conclude a property is unsatisfiable), call
generate_response using the structured format from the system prompt.
"""

_CONTINUE_MSG = (
    "Continue aligning. If violations remain, pick 1 suspect section (or "
    "'declarations' if you need to add new state) and call "
    "read_section(section_id), then call replace_section(section_id, new_code) "
    "once — small if it's a local bug, a coherent rewrite if the section's "
    "design can't satisfy the property — then run_alignment_check()."
)

# Code-level gate, not just a prompt instruction: a prompt-only "please try
# harder first" is exactly the kind of soft constraint this parity effort is
# moving away from (see _SYSTEM_PROMPT rule 6 and the PROPERTY_SUSPECT format
# — both prompt-level asks). This message is substituted for _CONTINUE_MSG
# whenever the model claims PROPERTY_SUSPECT with fewer than 2 real
# replace_section attempts on record (self._session.action_calls), forcing at
# least 2 genuine edit attempts before the escape hatch can be used.
_PROPERTY_SUSPECT_REJECTED_MSG = (
    "You concluded PROPERTY_SUSPECT, but you have not yet made 2 distinct "
    "replace_section attempts targeting this property's signals (only {n} so "
    "far). That conclusion is not accepted yet. Try a real edit first: call "
    "list_suspect_sections(), then read_section(section_id) for the most "
    "relevant one, then replace_section(section_id, new_code), then "
    "run_alignment_check(). Only return to PROPERTY_SUSPECT after at least 2 "
    "such attempts, citing what you tried and what happened to each."
)

_MIN_ACTION_CALLS_FOR_PROPERTY_SUSPECT = 2


def _gate_continue_message(resp: Any, action_calls: int) -> str:
    """Pure gate logic for the PROPERTY_SUSPECT escape hatch (parity item 3).

    Returns the corrective rejection message if `resp` claims PROPERTY_SUSPECT
    with fewer than _MIN_ACTION_CALLS_FOR_PROPERTY_SUSPECT real replace_section
    attempts on record; otherwise the normal continuation message. Does not
    affect TB_ALIGNED responses — those terminate via self._session.is_done,
    which only a genuinely passing run_alignment_check() sets, never this gate.
    """
    if _response_claims_property_suspect(resp) and action_calls < _MIN_ACTION_CALLS_FOR_PROPERTY_SUSPECT:
        return _PROPERTY_SUSPECT_REJECTED_MSG.format(n=action_calls)
    return _CONTINUE_MSG


# NOTE: this used to also gate justification-capture in chat()'s main loop
# (`if self._session.is_done or _response_is_terminal(response): ...`). That was a
# bug: a bare substring match over the FULL response text fires even when the model
# merely narrates "TB_ALIGNED" mid-reasoning on a non-final turn, and the `and not
# _justification` guard downstream meant a later, real completion could never
# overwrite the false-early capture. Fixed by gating justification-capture on
# `self._session.is_done` alone (the real ground-truth boolean), mirroring
# rtl_editor.py, which never had a text-substring check in that path at all. This
# function is now used ONLY by the PROPERTY_SUSPECT action-count gate below — do not
# reintroduce it into the justification-capture conditions.
def _response_is_terminal(msg: Any) -> bool:
    content = str(getattr(msg, "content", "") or "")
    return bool(re.search(r"\bTB_ALIGNED\b|\bPROPERTY_SUSPECT\b", content))


def _response_claims_property_suspect(msg: Any) -> bool:
    content = str(getattr(msg, "content", "") or "")
    return bool(re.search(r"\bPROPERTY_SUSPECT\b", content))


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
        # 6 (RTLEditor's default, shared via the same sliding-window
        # mechanism) collapses memory to [first prompt] + [last 6 messages]
        # between every trial -- a single ReAct sub-loop (max_iters=10)
        # commonly emits more than 8 messages on its own, so this window was
        # observed live to collapse within a single trial. TBEditor's task
        # (multi-trial coupled-section FSM/timing repair) needs continuity
        # across several trials' worth of reasoning about WHY a design
        # choice was made -- unlike RTLEditor's typical single-local-bug-fix
        # task, which rarely depends on remembering prior trials. Observed
        # live: a genuinely correct multi-cycle datapath model (reaching the
        # run's best fail_count) was abandoned one trial later and never
        # rebuilt, with the registers it declared left unused for the rest
        # of the run -- consistent with the model having lost the reasoning
        # for why it built that design, not having reconsidered it.
        memory_window: int = 50,
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
        toolkit.register_tool_function(self._tool_revert_to_best)

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

    async def _tool_revert_to_best(self) -> ToolResponse:
        """Restore the testbench to its lowest-ever fail_count state, then re-check.

        Use this after an edit made fail_count HIGHER instead of trying to
        manually reconstruct a design you already had.
        """
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        result = await asyncio.to_thread(self._session.revert_to_best)
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
            continuous_drivers=_find_continuous_drivers(tb_code),
            child_assumes=child_assumes,
            io_names=io_names,
            sections_by_id={s.id: s for s in suspects},
        )

        try:
            check = self._session.run_alignment_check()
        except FileNotFoundError as e:
            return False, tb_code, 0, f"TB alignment skipped: {e}"

        # Now that violation_log/violated_signals are known, refresh the
        # suspect list once so the model's very FIRST list_suspect_sections()
        # call already benefits from property-seeded selection, not just after
        # its first edit (which is when _refresh_sections was previously first
        # invoked, via replace_section).
        self._session._refresh_sections()

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
        prev_action_calls_for_stall = int(self._session.action_calls)

        def _update_stall_tracking() -> None:
            nonlocal stall_count, prev_fail_for_stall, prev_action_calls_for_stall
            # A turn only counts toward "stalling" if an edit was actually
            # attempted (action_calls increased). Otherwise a model that
            # spends turns exploring (list/read sections) without ever
            # calling replace_section gets cut off by stall detection before
            # making a single attempt — observed live (booth_reset_coherent,
            # bundle 20260711T074901Z): trials_used=0, stall exit after just
            # 2 non-productive turns, no replace_section call ever made.
            if self._session.action_calls == prev_action_calls_for_stall:
                prev_fail_for_stall = self._session.last_fail_count
                prev_action_calls_for_stall = self._session.action_calls
                return
            if self._session.last_fail_count < prev_fail_for_stall:
                stall_count = 0
            else:
                stall_count += 1
            prev_fail_for_stall = self._session.last_fail_count
            prev_action_calls_for_stall = self._session.action_calls

        response = await self._agent(Msg("user", first_prompt, role="user"))
        _last_content = str(getattr(response, "content", "") or "")
        if self._session.is_done:
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
            next_msg = _gate_continue_message(response, self._session.action_calls)
            response = await self._agent(Msg("user", next_msg, role="user"))
            _last_content = str(getattr(response, "content", "") or "")
            if self._session.is_done and not _justification:
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
