from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import List, Tuple

from .bash_tools import CommandResult, run_bash_command
from .architect_agent import ArchitectAgent
from .rtl_editor import RTLEditor
from .contract_linter import lint_contract_json, render_contract_issues
from .config import OpenAIConfig
from .model import UsageBreakdown, get_model_usage
from .rtl_generator import RTLGenerator
from .sim_reviewer import SimReviewer
from .tb_editor import TBEditor
from .tb_generator import TBGenerator

logger = logging.getLogger(__name__)

# Verilator error text is sometimes too cryptic for the TB lint-repair loop to
# act on (a recorded run regenerated the identical declaration-after-statement
# defect 4 times because the excerpt only said `expecting "'{"`). Each
# (pattern, hint) pair appends a plain-English translation to the excerpt
# before it is fed back to the Verifier; add new translations here.
_LINT_EXCERPT_TRANSLATIONS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"""unexpected IDENTIFIER, expecting "'\{\""""),
        "HINT: `syntax error, unexpected IDENTIFIER, expecting \"'{\"` at a line "
        "inside a task/begin block almost always means a DECLARATION (e.g. `time t;` "
        "/ `int n;`) appears AFTER a statement. SystemVerilog requires all local "
        "declarations at the TOP of the task/block body, before any statement. Move "
        "every declaration in the flagged tasks to the top of that task.",
    ),
]


def _augment_lint_excerpt(excerpt: str) -> str:
    """Append plain-English hints for known-cryptic Verilator errors in ``excerpt``.

    Pure function; returns the excerpt unchanged when no pattern matches.
    """
    hints = [hint for pattern, hint in _LINT_EXCERPT_TRANSLATIONS if pattern.search(excerpt)]
    if not hints:
        return excerpt
    return excerpt.rstrip("\n") + "\n\n" + "\n\n".join(hints) + "\n"


def _tb_is_acceptable(
    tb_text: str, module_name: str, contract_json: str
) -> tuple[bool, str]:
    """Is this testbench a plausible ORACLE, beyond merely linting clean?

    Lint-clean is necessary, not sufficient, and the gap is not theoretical.
    The repair loop below exits the moment Verilator is happy, and a generic
    stub is trivially happy:

        module tb_dut_top;
          ...
          $display("ERROR: No contract provided - testbench cannot verify DUT");
          $finish(1);
        endmodule

    Two nodes in the persisted corpus collapsed to exactly that after their
    real testbenches failed lint several times, and the stub then became the
    node's cached oracle and gated real glue attempts. So the loop needs a
    CONTENT invariant as well as a syntactic one.

    Pure, so the predicate is testable against the real persisted stubs without
    a model call. Returns (ok, reason) — `reason` is fed back to the generator.
    """
    if not tb_text or not tb_text.strip():
        return False, "the testbench is empty"

    from .contract_linter import tb_instantiates_module

    if not tb_instantiates_module(tb_text, module_name):
        return False, (
            f"the testbench never instantiates `{module_name}`. A testbench that "
            f"drives some other module is not an oracle for this one. Instantiate "
            f"`{module_name}` as the DUT and drive its real ports."
        )

    # A TB may legitimately leave some ports unread, but one that mentions
    # almost none of them is not exercising the interface it claims to check.
    try:
        ports = [
            p.get("name")
            for p in (json.loads(contract_json) or {}).get("io", [])
            if isinstance(p, dict) and p.get("name")
        ]
    except (ValueError, TypeError):
        ports = []
    if ports:
        seen = [p for p in ports if re.search(rf"\b{re.escape(p)}\b", tb_text)]
        if len(seen) * 2 < len(ports):
            missing = [p for p in ports if p not in seen][:6]
            return False, (
                f"the testbench references only {len(seen)} of {len(ports)} contract "
                f"ports (missing e.g. {', '.join(missing)}). Drive and check the "
                f"module's real interface."
            )
    return True, ""


def _append_child_rtl(testbench: str, child_rtl: dict[str, str] | None) -> str:
    """Append real child module source(s) into the testbench text.

    SystemVerilog allows multiple module definitions per file, so this makes
    the child modules resolvable wherever ``tb.sv`` is compiled (lint check,
    RTLEditor's debug loop, Asserter, final self-TB) with zero changes to any
    of those callers' file lists — they all just read ``tb.sv`` from disk.
    Pure function; returns ``testbench`` unchanged if ``child_rtl`` is empty.
    """
    if not child_rtl:
        return testbench
    return testbench.rstrip("\n") + "\n\n" + "\n\n".join(child_rtl.values()) + "\n"


def _is_absent_dut_artifact(line: str) -> bool:
    """True if this verilator error exists ONLY because the DUT was left out.

    A TB is linted alone on purpose, so `-MODMISSING` is expected. The two
    dotted-reference errors are the same artifact one step further in: once a
    testbench reaches INTO the DUT (`dut.some_port`), verilator cannot resolve
    the path without the module, and reports it as a hard error rather than as
    MODMISSING. Treating those as real syntax errors would fail every glue
    testbench carrying a hierarchical probe, and `_tb_has_syntax_error` would
    then silently swap the glue oracle for the golden TB -- turning added
    visibility into a lost verdict.
    """
    return (
        "-MODMISSING:" in line
        or line.startswith("%Error: Exiting due to")
        or "Dotted reference to instance that refers to missing module" in line
        or "in dotted variable/method:" in line
    )


def tb_lint_report(*, tb_path: Path) -> tuple[bool, str, str]:
    """Return (is_ok, excerpt, raw_json) from `verilator --lint-only` on the testbench.

    This lints the TB in isolation; missing DUT module definitions are expected and ignored.

Module-level so callers OUTSIDE this class get the SAME verdict. The
filtering is not incidental: warnings are ignored, `-MODMISSING` is ignored
(the DUT is deliberately absent when a TB is linted alone), and "Exiting due
to" is ignored. A caller that substitutes a generic syntax check gets a
different answer -- `check_syntax` on a lone oracle fails on a missing
trailing newline AND on the absent DUT, so every oracle looks broken, which
would disable the unified glue loop everywhere it gates.
    """
    if shutil.which("verilator") is None:
        return True, "", ""

    cmd = f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {tb_path}"
    _ok, out = run_bash_command(cmd, timeout=60, cwd=str(tb_path.parent))
    try:
        obj = CommandResult.model_validate_json(out)
    except Exception:  # noqa: BLE001
        return False, out, out

    stdout = obj.stdout or ""
    stderr = obj.stderr or ""
    text = f"{stdout}\n{stderr}"

    error_lines = [
        line.strip()
        for line in text.splitlines()
        if line.lstrip().startswith("%Error")
    ]
    real_error_lines = [
        line
        for line in error_lines
        if not _is_absent_dut_artifact(line)
    ]

    is_ok = not real_error_lines and ("syntax error" not in text.lower()) and ("malformed statement" not in text.lower())
    excerpt = "\n".join(real_error_lines).strip() or text.strip()
    if len(excerpt) > 6000:
        excerpt = excerpt[:6000] + "\n...<snip>...\n"
    return is_ok, excerpt + ("\n" if excerpt and not excerpt.endswith("\n") else ""), out


@dataclass(frozen=True)
class TopAgentConfig:
    sim_max_retry: int = 4
    is_ablation: bool = False
    contract_only: bool = True
    debug_max_trials: int = 15
    # Number of TB lint-repair attempts after the initial generation, in
    # non-golden mode (no golden TB fallback). The self-generated TB is the only
    # oracle there, so a single blind retry is too few for complex problems
    # (e.g. ArchXBench). Each retry feeds back the accumulated lint errors.
    tb_lint_max_retry: int = 4
    # Bounded repair loop that aligns a composition node's inline child
    # behavioral model against child_assumes SVA (via a mock-DUT + Verilator
    # check) BEFORE the TB is used to gate the real glue RTL. No-op when the
    # contract carries no child_assumes.
    tb_align_max_trials: int = 15
    # TBEditor gives up early if the property-violation count doesn't improve
    # for this many consecutive rounds — a separate cutoff from
    # tb_align_max_trials. Observed live (booth_reset_coherent): TBEditor
    # stopped at trial 6/15 via stall detection, never exhausting the trial
    # budget, so this (not tb_align_max_trials) is the lever that actually
    # bounds how much repair the alignment pass gets to attempt.
    tb_align_stall_rounds: int = 2


@dataclass(frozen=True)
class TopAgentResult:
    output_dir_per_run: str
    rtl_path: str
    tb_path: str
    if_path: str
    is_sim_pass: bool
    rtl_code: str
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    usage_breakdown: dict | None = None


class TopAgent:
    """Multi-agent RTL generation loop (Architect/Verifier/Coder/Debugger)."""

    def __init__(self, cfg: OpenAIConfig, *, config: TopAgentConfig | None = None) -> None:
        self.cfg = cfg
        self.config = config or TopAgentConfig()

    def _write_output(self, *, output_dir_per_run: Path, file_name: str, content: str) -> None:
        output_dir_per_run.mkdir(parents=True, exist_ok=True)
        (output_dir_per_run / file_name).write_text(content, encoding="utf-8")

    def _augment_dumpvars_with_dut_scope(self, testbench: str, *, module_name: str = "TopModule") -> str:
        """Best-effort: dump DUT internals into wave.vcd for trace-based debugging."""
        m = re.search(rf"\b{re.escape(module_name)}\b\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", testbench)
        if not m:
            return testbench
        inst = m.group(1)

        if re.search(rf"\\$dumpvars\\s*\\(\\s*0\\s*,\\s*{re.escape(inst)}\\s*\\)", testbench):
            return testbench

        lines = testbench.splitlines()
        insert_after = None
        for i, line in enumerate(lines):
            if "$dumpvars" in line:
                insert_after = i
                break
        if insert_after is None:
            for i, line in enumerate(lines):
                if "$dumpfile" in line:
                    insert_after = i
                    break
        if insert_after is None:
            return testbench

        indent = re.match(r"\s*", lines[insert_after]).group(0)  # type: ignore[union-attr]
        lines.insert(insert_after + 1, f"{indent}$dumpvars(0, {inst});")
        return "\n".join(lines) + ("\n" if testbench.endswith("\n") else "")

    def _augment_glue_port_probes(
        self,
        testbench: str,
        *,
        module_name: str,
        assembled_rtl_path: str | None,
    ) -> str:
        """Print the glue's CHILD-FACING ports every cycle, via hierarchical reference.

        A leaf debugger sees expected-vs-actual for every signal it can change,
        because `rtl.sv` IS the DUT and the testbench drives and prints its ports.
        A glue debugger does not: the testbench drives the WRAPPER, so it prints
        only the wrapper's external outputs, while the glue's child-facing ports
        are internal nodes one level down.

        Measured on stage_roundpack: 13 failing signals, of which 11 were
        child-facing and the testbench printed values for NONE. The glue drives
        13 of its 14 editable blocks into those ports, so it was editing almost
        entirely blind -- which is a far better explanation of "leaves converge,
        glue does not" than anything about tools or prompts.

        The wrapper connects each child-facing port to a same-named wire
        (`.special_case_unit_sign_in(special_case_unit_sign_in)`), so
        `<dut_inst>.<port>` reaches it. Emitted as one GLUEPROBE line per cycle
        so the values can be correlated with the mismatch times the testbench
        already reports.
        """
        if not assembled_rtl_path:
            return testbench
        try:
            asm = Path(assembled_rtl_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return testbench

        # In the UNIFIED glue solve, `module_name` is already the glue's own name
        # (`glue_spec_for_solve["module_name"] = f"{parent}_glue"`), so appending
        # `_glue` looks for `<parent>_glue_glue` and matches nothing -- the probe
        # then returns the testbench unchanged and the whole visibility fix is a
        # silent no-op. That is exactly how it shipped: the run produced a tb.sv
        # byte-identical to the oracle, with zero GLUEPROBE lines and no error.
        #
        # Derive both names instead of assuming which one was handed in:
        #   glue    -- the module instantiated inside the assembled composition
        #   wrapper -- what the TESTBENCH drives, and the scope the hierarchical
        #              reference must be rooted at
        if module_name.endswith("_glue"):
            glue_name, wrapper_name = module_name, module_name[: -len("_glue")]
        else:
            glue_name, wrapper_name = f"{module_name}_glue", module_name

        m = re.search(rf"\b{re.escape(glue_name)}\b\s+(\w+)\s*\((.*?)\);", asm, re.S)
        if not m:
            return testbench
        conn = m.group(2)
        # `.child_port(wire)` where the port is child-facing: `<child>_<signal>`
        ports = [
            g for g in re.findall(r"\.\s*(\w+)\s*\(", conn)
            if re.search(r"_(in|out)$", g) and g.count("_") >= 2
        ]
        # external ports of the parent are connected too; keep only those that are
        # NOT declared as ports of the testbench's own DUT interface, i.e. the ones
        # carrying a child module's name prefix.
        ports = [p for p in ports if not re.match(r"^(clk|rst|valid|sign|exp|sig|is|result)_", p)]
        if not ports:
            return testbench

        # Root the hierarchical reference at the module the TESTBENCH drives --
        # the wrapper -- not at the glue, which the testbench never names.
        inst = None
        mi = re.search(rf"\b{re.escape(wrapper_name)}\b\s+([a-zA-Z_]\w*)\s*\(", testbench)
        if mi:
            inst = mi.group(1)
        if not inst:
            return testbench
        if "GLUEPROBE" in testbench:
            return testbench

        clk = "clk" if re.search(r"\bclk\b", testbench) else None
        if not clk:
            return testbench

        fmt = " ".join(f"{p}=%h" for p in ports)
        args = ", ".join(f"{inst}.{p}" for p in ports)
        probe = (
            "\n// --- injected: child-facing port visibility for the glue debugger ---\n"
            "// The testbench drives the WRAPPER, so these ports are internal nodes it\n"
            "// would otherwise never print. Without them the glue agent edits blind.\n"
            f"always @(negedge {clk}) begin\n"
            f'    $display("GLUEPROBE t=%0t {fmt}", $time, {args});\n'
            "end\n"
        )
        idx = testbench.rfind("endmodule")
        if idx == -1:
            return testbench
        return testbench[:idx] + probe + testbench[idx:]

    def _tb_has_syntax_error(self, *, tb_path: Path) -> bool:
        """Return True if `tb_path` contains a real syntax error (not just missing module defs)."""
        if shutil.which("verilator") is None:
            # If the environment lacks Verilator, don't force golden TB fallback.
            return False

        cmd = f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {tb_path}"
        _ok, out = run_bash_command(cmd, timeout=60, cwd=str(tb_path.parent))
        try:
            obj = CommandResult.model_validate_json(out)
        except Exception:  # noqa: BLE001
            return False
        stdout = obj.stdout or ""
        stderr = obj.stderr or ""
        text = f"{stdout}\n{stderr}".lower()

        # Ignore the expected "TopModule is missing" error when linting a testbench
        # file in isolation. We only care about whether the testbench itself is broken
        # (or uses unsupported SV features) for golden TB fallback.
        error_lines = [
            line.strip()
            for line in f"{stdout}\n{stderr}".splitlines()
            if line.lstrip().startswith("%Error")
        ]
        real_error_lines = [
            line
            for line in error_lines
            if not _is_absent_dut_artifact(line)
        ]
        if real_error_lines:
            return True

        # If there were no "real" errors, treat syntax errors as broken TB.
        return ("syntax error" in text) or ("malformed statement" in text)

    def _tb_lint_report(self, *, tb_path: Path) -> tuple[bool, str, str]:
        """Instance-side alias for :func:`tb_lint_report`."""
        return tb_lint_report(tb_path=tb_path)

    async def _build_contract_json(
        self,
        *,
        architect: ArchitectAgent,
        spec: str,
        golden_tb_path: str | None,
        output_dir_per_run: Path,
        max_repairs: int = 2,
    ) -> str:
        """Generate contract.json and (best-effort) repair it until lint passes."""
        contract = await architect.chat(spec, golden_tb_path=golden_tb_path)
        contract_json = contract.model_dump_json(indent=2, exclude_none=True) + "\n"

        for repair_idx in range(max(0, int(max_repairs)) + 1):
            issues, _obj = lint_contract_json(contract_json)
            errors = [i for i in issues if i.severity == "error"]
            lint_report = render_contract_issues(issues)

            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="contract_lint.txt",
                content=lint_report or "(no issues)\n",
            )

            if not errors:
                break
            if repair_idx >= max_repairs:
                break

            revised = await architect.revise_contract(
                input_spec=spec,
                contract_json=contract_json,
                lint_errors=lint_report,
                golden_tb_path=golden_tb_path,
            )
            contract_json = revised.model_dump_json(indent=2, exclude_none=True) + "\n"

        self._write_output(output_dir_per_run=output_dir_per_run, file_name="contract.json", content=contract_json)
        return contract_json

    def _contract_only_context(self, contract_json: str) -> str:
        """Compact pseudo-spec for contract-only mode; avoids leaking ambiguous NL downstream."""
        if not self.config.contract_only:
            return ""
        try:
            obj = __import__("json").loads(contract_json)
        except Exception:  # noqa: BLE001
            return ""
        bullets = obj.get("functional_summary")
        if not isinstance(bullets, list) or not bullets:
            return ""
        items = [str(x) for x in bullets if isinstance(x, str) and x.strip()]
        if not items:
            return ""
        return "Contract-only context:\n" + "\n".join(f"- {s}" for s in items[:6]) + "\n"

    async def _run_instance(
        self,
        *,
        spec: str,
        output_dir_per_run: Path,
        golden_tb_path: str | None,
        golden_rtl_blackbox_path: str | None,
        contract_sva: list[dict] | None = None,
        child_assumes: dict | None = None,
        child_rtl: dict[str, str] | None = None,
        external_tb: str | None = None,
    ) -> Tuple[bool, str, int, int, dict | None]:
        """Run one instance of the full agent procedure.

        Returns ``(is_sim_pass, rtl_code, input_tokens, output_tokens,
        usage_breakdown_dict)``. The repair step is the standard RTLEditor debug
        loop; ``is_sim_pass`` (the self-TB verdict) is the per-node escalation
        signal consumed by the DAG OR-node.

        ``child_rtl`` (module_name -> real, already-verified RTL source):
        when given, TBGenerator instantiates these children directly instead
        of writing an inline behavioral stand-in, and the mock-DUT/TBEditor
        alignment pass is skipped entirely (there is no invented model to
        align — the TB wires real RTL). Only meaningful for children also
        present in ``child_assumes`` (their prefixed port names come from
        there); a name in ``child_rtl`` but not ``child_assumes`` is ignored.
        """
        architect = ArchitectAgent(self.cfg)
        tb_gen = TBGenerator(self.cfg)
        rtl_gen = RTLGenerator(self.cfg)
        sim_reviewer = SimReviewer(str(output_dir_per_run), golden_rtl_blackbox_path)
        rtl_edit = RTLEditor(self.cfg, sim_reviewer=sim_reviewer, max_trials=int(self.config.debug_max_trials))

        def build_breakdown() -> UsageBreakdown:
            return UsageBreakdown(
                architect=get_model_usage(architect._agent.model),
                tb_gen=get_model_usage(tb_gen._agent.model),
                rtl_gen=get_model_usage(rtl_gen._agent.model),
                rtl_edit=get_model_usage(rtl_edit._agent.model),
            )

        def finish(
            is_sim_pass: bool,
            rtl_code: str,
        ) -> Tuple[bool, str, int, int, dict | None]:
            breakdown = build_breakdown()
            total_in, total_out = breakdown.total
            return is_sim_pass, rtl_code, total_in, total_out, breakdown.to_dict()

        architect.reset()
        contract_json = await self._build_contract_json(
            architect=architect,
            spec=spec,
            golden_tb_path=golden_tb_path,
            output_dir_per_run=output_dir_per_run,
        )
        # Inject orchestrator-supplied contract SVA and child assumes into the
        # contract so they flow to all downstream agents as first-class fields.
        if contract_sva or child_assumes:
            try:
                _cobj = json.loads(contract_json)
                if contract_sva:
                    _cobj["contract_sva"] = contract_sva
                if child_assumes:
                    _cobj["child_assumes"] = child_assumes
                if child_rtl:
                    for _name in child_rtl:
                        if _name in _cobj.get("child_assumes", {}):
                            _cobj["child_assumes"][_name]["rtl_available"] = True
                contract_json = json.dumps(_cobj, indent=2) + "\n"
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="contract.json", content=contract_json)
            except Exception:  # noqa: BLE001
                pass
        try:
            contract_obj = json.loads(contract_json)
            module_name = str(contract_obj.get("module_name") or "TopModule")
        except Exception:  # noqa: BLE001
            module_name = "TopModule"
        try:
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="architect_prompt.txt",
                content=(getattr(architect, "last_prompt", "") or "") + "\n",
            )
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="architect_raw_output.txt",
                content=(getattr(architect, "last_raw_output", "") or "") + "\n",
            )
        except Exception:  # noqa: BLE001
            pass

        tb_gen.reset()
        tb_gen.set_golden_tb_path(golden_tb_path)
        tb_input_spec = self._contract_only_context(contract_json) if self.config.contract_only else spec

        if external_tb is not None:
            # An oracle was supplied, so generate nothing: this TB IS the gate.
            # Used for composition (glue) nodes, which are handed the parent's
            # own original-interface TB. Together with `child_rtl` (the real,
            # already-certified children appended below) the sim/debug loop
            # downstream is exactly the composed-simulation check — the glue is
            # written and repaired against the same assembly and the same
            # oracle that decides whether it certifies.
            #
            # This is NOT `golden_tb_path`, which still regenerates a TB and
            # only falls back to the golden text on a syntax error. Here the
            # supplied text is authoritative and never redrawn, so there is no
            # second, invented oracle anywhere in a composition's pipeline.
            testbench = self._augment_dumpvars_with_dut_scope(external_tb, module_name=module_name)
            # Give the glue debugger the same visibility a leaf debugger has by
            # construction: values for every port it can drive, not just the
            # wrapper's two external outputs.
            testbench = self._augment_glue_port_probes(
                testbench, module_name=module_name,
                assembled_rtl_path=golden_rtl_blackbox_path,
            )
            testbench = _append_child_rtl(testbench, child_rtl)
            interface = ""
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=testbench)
            tb_ok, tb_lint_excerpt, tb_lint_json = self._tb_lint_report(tb_path=output_dir_per_run / "tb.sv")
            if not tb_ok:
                # A supplied oracle that will not elaborate is a broken ORACLE,
                # not a broken design. There is no repair path here (we must not
                # rewrite the caller's gate), so surface it instead of letting
                # the Coder burn its budget against an unusable testbench.
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_lint_failed_log.json", content=tb_lint_json)
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_lint_failed_excerpt.txt", content=tb_lint_excerpt)
                logger.error("Supplied external TB does not lint; aborting this attempt:\n%s", tb_lint_excerpt)
                return finish(False, "")
        else:
            testbench, interface = await tb_gen.chat(tb_input_spec, contract_json=contract_json)
            testbench = self._augment_dumpvars_with_dut_scope(testbench, module_name=module_name)
            testbench = _append_child_rtl(testbench, child_rtl)
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=testbench)
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="if.sv", content=interface)
        # If we were given a golden TB and the LLM accidentally broke its syntax,
        # fall back to the original golden TB (plus our safe dumpvars augmentation).
        tb_path = output_dir_per_run / "tb.sv"
        if external_tb is not None:
            # Already linted above and authoritative by construction — neither
            # the golden fallback nor the Verifier repair loop may touch it.
            pass
        elif golden_tb_path and self._tb_has_syntax_error(tb_path=tb_path):
            golden_text = Path(golden_tb_path).read_text(encoding="utf-8")
            golden_text = self._augment_dumpvars_with_dut_scope(golden_text, module_name=module_name)
            golden_text = _append_child_rtl(golden_text, child_rtl)
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=golden_text)
            testbench = golden_text
        elif not golden_tb_path:
            # Non-golden mode: the self-generated TB is the only oracle (no golden
            # fallback), so lint it and give the Verifier a bounded repair loop.
            # Each retry feeds back the accumulated lint errors (set_tb_lint_error
            # appends), so the model sees the full history rather than one blind shot.
            tb_ok, tb_lint_excerpt, tb_lint_json = self._tb_lint_report(tb_path=tb_path)
            inv_ok, inv_reason = _tb_is_acceptable(testbench, module_name, contract_json)
            attempt = 0
            while (not tb_ok or not inv_ok) and attempt < self.config.tb_lint_max_retry:
                suffix = "" if attempt == 0 else f"_attempt{attempt}"
                self._write_output(output_dir_per_run=output_dir_per_run, file_name=f"tb_lint_failed_log{suffix}.json", content=tb_lint_json)
                self._write_output(output_dir_per_run=output_dir_per_run, file_name=f"tb_lint_failed_excerpt{suffix}.txt", content=tb_lint_excerpt)

                # A TB that lints clean but fails the ORACLE invariant gets the
                # invariant as its feedback, not a stale lint log — otherwise
                # the model is told to fix errors it has already fixed and
                # collapsing further to a stub looks like progress.
                feedback = _augment_lint_excerpt(tb_lint_excerpt) if not tb_ok else ""
                if not inv_ok:
                    logger.warning("Generated TB rejected by the oracle invariant: %s", inv_reason)
                    feedback = (feedback + "\n\n" if feedback else "") + (
                        "The testbench is not a usable ORACLE: " + inv_reason
                    )
                tb_gen.set_tb_lint_error(lint_log=feedback, previous_tb=testbench)
                testbench, interface = await tb_gen.chat(tb_input_spec, contract_json=contract_json)
                testbench = self._augment_dumpvars_with_dut_scope(testbench, module_name=module_name)
                testbench = _append_child_rtl(testbench, child_rtl)
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=testbench)
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="if.sv", content=interface)

                attempt += 1
                tb_ok, tb_lint_excerpt, tb_lint_json = self._tb_lint_report(tb_path=tb_path)
                inv_ok, inv_reason = _tb_is_acceptable(testbench, module_name, contract_json)

            if not tb_ok or not inv_ok:
                # Exhausted the repair budget: the TB still does not lint clean,
                # or it lints but is not an oracle. Both are unusable, and the
                # invariant failure is the more dangerous of the two because it
                # would otherwise be CACHED and gate every later attempt.
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_lint_failed_log_final.json", content=tb_lint_json)
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_lint_failed_excerpt_final.txt", content=tb_lint_excerpt)
                try:
                    self._write_output(
                        output_dir_per_run=output_dir_per_run,
                        file_name="verifier_prompt.txt",
                        content=(getattr(tb_gen, "last_prompt", "") or "") + "\n",
                    )
                    self._write_output(
                        output_dir_per_run=output_dir_per_run,
                        file_name="verifier_raw_output.txt",
                        content=(getattr(tb_gen, "last_raw_output", "") or "") + "\n",
                    )
                except Exception:  # noqa: BLE001
                    pass
                tb_lint_lesson = (
                    "TB generation failed: the testbench did not pass Verilator lint "
                    "after all repair attempts. The contract may be specifying constructs "
                    "that the Verifier cannot generate correctly.\n"
                    f"Lint errors:\n{tb_lint_excerpt}\n\n"
                    "Guidance: revise the contract to avoid constructs that produce these "
                    "lint errors. For example, avoid 8'sd-X signed literals (write -X instead), "
                    "avoid static variable initializers in function/task bodies, and avoid "
                    "SVA temporal operators (##, $past with non-constant delays)."
                )
                return finish(False, "")
        try:
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="verifier_prompt.txt",
                content=(getattr(tb_gen, "last_prompt", "") or "") + "\n",
            )
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="verifier_raw_output.txt",
                content=(getattr(tb_gen, "last_raw_output", "") or "") + "\n",
            )
        except Exception:  # noqa: BLE001
            pass

        # TB alignment pass (composition nodes only): before the TB is used to
        # gate the real glue RTL, verify its inline child behavioral model
        # actually satisfies child_assumes SVA, using a mock DUT + Verilator —
        # independent of whatever the (not-yet-correct) glue RTL does. A TB
        # bug here would otherwise silently poison the self-TB gate: either
        # penalizing correct glue RTL, or letting broken glue RTL pass because
        # the TB's child model never exercised the violated property.
        #
        # Skipped when child_rtl is given: the TB already wires REAL,
        # already-verified child RTL (see _append_child_rtl above) instead of
        # an inline behavioral stand-in, so there is no invented model to
        # align — child_assumes is only used above for prompt guidance (drive
        # instantiation, not a stand-in) and for contract_sva's assert side.
        # ...and equally when `external_tb` is set. That is the UNIFIED glue
        # loop, where the children are just as real -- they are compiled into
        # the assembled composition (`fixed.sv`) alongside the wrapper instead
        # of being spliced into the testbench text. The guard tested HOW the
        # children arrived rather than WHETHER they exist, so under `unified`
        # (which passes child_rtl=None by design) it ran anyway.
        #
        # There is nothing to align in that path: the composed testbench drives
        # the WRAPPER, so it contains no inline child model. The pass fabricated
        # a stub for a glue about to be generated, injected assumption asserts
        # built from model-authored expressions, and on stage_roundpack one of
        # them was `(...)[24]` -- a bit-select on a parenthesised expression,
        # illegal SystemVerilog -- so mock_dut.sv failed to compile, all 24
        # assertions were lost, and the agent spent a trial diagnosing a
        # testbench that was never at fault while being forbidden to touch the
        # file that was. Same warning on stage_addsub and stage_normalize with a
        # different illegal expression each time.
        #
        # Bottom-up composition is what makes this unnecessary: the children are
        # already CERTIFIED, so a check that the testbench's imagined children
        # match their contracts has nothing left to verify.
        if child_assumes and not child_rtl and external_tb is None:
            # Snapshot the pre-alignment draft (mirrors rtl_before_debug.sv)
            # so a post-mortem can attribute a defect to TBGenerator's own
            # draft vs. something TBEditor introduced/failed to resolve while
            # patching — otherwise unanswerable once tb.sv is overwritten below.
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_before_align.sv", content=testbench)
            tb_editor = TBEditor(
                self.cfg,
                max_trials=int(self.config.tb_align_max_trials),
                stall_rounds=int(self.config.tb_align_stall_rounds),
            )
            aligned, aligned_tb, tb_align_trials, tb_align_log = await tb_editor.chat(
                contract_json=contract_json,
                tb_code=testbench,
                output_dir_per_run=str(output_dir_per_run),
            )
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb_align_log.txt", content=tb_align_log + "\n")
            # Structured, machine-readable assurance record. The free-text log
            # alone cannot answer "was the TB's child model actually verified
            # against child_assumes?" — downstream consumers (gating policy,
            # stage evals, triage) need the verdict, not a narrative. aligned
            # False here means the self-TB gate is running on an UNVERIFIED
            # child model; the certificate consumer can decide what to do
            # with that, but it must be visible.
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="tb_align_verdict.json",
                content=json.dumps(
                    {
                        "aligned": bool(aligned),
                        "trials_used": int(tb_align_trials),
                        "max_trials": int(self.config.tb_align_max_trials),
                        "log_tail": tb_align_log[-2000:],
                    },
                    indent=2,
                ) + "\n",
            )
            if aligned_tb:
                testbench = aligned_tb
                self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=testbench)
            if not aligned:
                logger.warning(
                    "TB did not fully align with child_assumes after %d trial(s) (continuing with best effort): %s",
                    tb_align_trials, tb_align_log,
                )

        rtl_gen.reset()
        rtl_path = str(output_dir_per_run / "rtl.sv")
        rtl_input_spec = self._contract_only_context(contract_json) if self.config.contract_only else spec
        is_syntax_pass, rtl_code = await rtl_gen.chat(
            input_spec=rtl_input_spec,
            testbench=testbench,
            interface=interface,
            rtl_path=rtl_path,
            contract_json=contract_json,
        )
        if not is_syntax_pass:
            try:
                self._write_output(
                    output_dir_per_run=output_dir_per_run,
                    file_name="coder_prompt.txt",
                    content=(getattr(rtl_gen, "last_prompt", "") or "") + "\n",
                )
                self._write_output(
                    output_dir_per_run=output_dir_per_run,
                    file_name="coder_raw_output.txt",
                    content=(getattr(rtl_gen, "last_raw_output", "") or "") + "\n",
                )
            except Exception:  # noqa: BLE001
                pass
            return finish(False, rtl_code)
        self._write_output(output_dir_per_run=output_dir_per_run, file_name="rtl.sv", content=rtl_code)
        try:
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="coder_prompt.txt",
                content=(getattr(rtl_gen, "last_prompt", "") or "") + "\n",
            )
            self._write_output(
                output_dir_per_run=output_dir_per_run,
                file_name="coder_raw_output.txt",
                content=(getattr(rtl_gen, "last_raw_output", "") or "") + "\n",
            )
        except Exception:  # noqa: BLE001
            pass

        sim_log = ""
        is_sim_pass = False
        sim_mismatch_cnt = 0
        did_rtl_regen_after_mismatch = False
        did_fallback_to_golden_tb = False
        remaining_debug_trials = int(self.config.debug_max_trials)

        # Simulation + repair loop. The repair step is the standard trace-based
        # RTLEditor debug loop; the leaf's is_sim_pass is the escalation signal.
        for _ in range(max(1, int(self.config.sim_max_retry))):
            is_sim_pass, sim_mismatch_cnt, sim_log = await asyncio.to_thread(sim_reviewer.review)
            if is_sim_pass:
                return finish(True, rtl_code)

            if sim_mismatch_cnt <= 0:
                if golden_tb_path and not did_fallback_to_golden_tb:
                    # The Verifier may have introduced SV features unsupported by Verilator
                    # (or broken the TB) even if it remains syntactically valid.
                    # In that case, fall back to the original golden TB and retry.
                    try:
                        tb_before = (output_dir_per_run / "tb.sv").read_text(encoding="utf-8")
                        self._write_output(
                            output_dir_per_run=output_dir_per_run,
                            file_name="tb_before_golden_fallback.sv",
                            content=tb_before,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    try:
                        self._write_output(
                            output_dir_per_run=output_dir_per_run,
                            file_name="sim_failed_log_before_tb_fallback.json",
                            content=sim_log,
                        )
                    except Exception:  # noqa: BLE001
                        pass

                    golden_text = Path(golden_tb_path).read_text(encoding="utf-8")
                    golden_text = self._augment_dumpvars_with_dut_scope(golden_text, module_name=module_name)
                    self._write_output(output_dir_per_run=output_dir_per_run, file_name="tb.sv", content=golden_text)
                    testbench = golden_text
                    did_fallback_to_golden_tb = True
                    continue

                # Non-mismatch failures (harness timeout, runtime error) — no repair possible.
                self._write_output(
                    output_dir_per_run=output_dir_per_run,
                    file_name="sim_failed_log.json",
                    content=sim_log,
                )
                try:
                    _sim_log_obj = json.loads(sim_log)
                    _sim_excerpt = str(_sim_log_obj.get("stderr") or _sim_log_obj.get("stdout") or sim_log)
                except Exception:  # noqa: BLE001
                    _sim_excerpt = sim_log
                compile_lesson = (
                    "RTL simulation failed with a compile/lint error — no behavioral "
                    "mismatches were produced (the simulator could not execute at all).\n"
                    f"Failure excerpt:\n{_sim_excerpt[:800]}\n\n"
                    "Guidance: the contract may be specifying RTL constructs that the Coder "
                    "generates incorrectly. Clarify bit-widths, operator types, and "
                    "Verilator-compatible constructs."
                )
                return finish(False, rtl_code)

            # Give the Coder one shot to regenerate RTL from the failure log before
            # handing off to the trace-based debugger.  This fixes systematic
            # contract/timing misunderstandings faster than local patching.
            if not did_rtl_regen_after_mismatch:
                did_rtl_regen_after_mismatch = True
                try:
                    rtl_gen.set_failed_trial(sim_log, rtl_code, testbench)
                    is_syntax_pass2, rtl_code2 = await rtl_gen.chat(
                        input_spec=rtl_input_spec,
                        testbench=testbench,
                        interface=interface,
                        rtl_path=rtl_path,
                        contract_json=contract_json,
                    )
                    if is_syntax_pass2:
                        rtl_code = rtl_code2
                        self._write_output(output_dir_per_run=output_dir_per_run, file_name="rtl_regen_after_mismatch.sv", content=rtl_code)
                        self._write_output(output_dir_per_run=output_dir_per_run, file_name="rtl.sv", content=rtl_code)
                        try:
                            self._write_output(
                                output_dir_per_run=output_dir_per_run,
                                file_name="coder_prompt_regen_after_mismatch.txt",
                                content=(getattr(rtl_gen, "last_prompt", "") or "") + "\n",
                            )
                            self._write_output(
                                output_dir_per_run=output_dir_per_run,
                                file_name="coder_raw_output_regen_after_mismatch.txt",
                                content=(getattr(rtl_gen, "last_raw_output", "") or "") + "\n",
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        continue
                except Exception:  # noqa: BLE001
                    pass

            # Standard repair step: trace-based RTLEditor debug loop.
            # Snapshot the pre-debug state for diagnostics (the leaf harvests these).
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="rtl_before_debug.sv", content=rtl_code)
            self._write_output(output_dir_per_run=output_dir_per_run, file_name="sim_failed_log.json", content=sim_log)

            if remaining_debug_trials <= 0:
                return finish(False, rtl_code)

            rtl_edit.reset()
            is_sim_pass, rtl_code, used_trials, _edit_justification = await rtl_edit.chat(
                spec=(self._contract_only_context(contract_json) if self.config.contract_only else spec),
                output_dir_per_run=str(output_dir_per_run),
                sim_failed_log=sim_log,
                sim_mismatch_cnt=sim_mismatch_cnt,
                contract_json=contract_json,
                max_trials=remaining_debug_trials,
            )
            remaining_debug_trials = max(0, remaining_debug_trials - int(used_trials))
            if is_sim_pass:
                return finish(True, rtl_code)

        # Last check, in case the final edit improved but didn't re-run.
        is_sim_pass, _, _ = await asyncio.to_thread(sim_reviewer.review)
        return finish(is_sim_pass, rtl_code)

    async def _run_instance_ablation(
        self,
        *,
        spec: str,
        output_dir_per_run: Path,
    ) -> Tuple[bool, str, int, int]:
        rtl_gen = RTLGenerator(self.cfg)
        rtl_gen.reset()
        rtl_path = str(output_dir_per_run / "rtl.sv")
        is_syntax_pass, rtl_code = await rtl_gen.ablation_chat(input_spec=spec, rtl_path=rtl_path)
        self._write_output(output_dir_per_run=output_dir_per_run, file_name="rtl.sv", content=rtl_code)
        input_tokens, output_tokens = get_model_usage(rtl_gen._agent.model)
        return is_syntax_pass, rtl_code, input_tokens, output_tokens

    async def run(
        self,
        *,
        spec: str,
        output_dir_per_run: Path,
        golden_tb_path: str | None = None,
        golden_rtl_blackbox_path: str | None = None,
        contract_sva: list[dict] | None = None,
        child_assumes: dict | None = None,
        child_rtl: dict[str, str] | None = None,
        external_tb: str | None = None,
    ) -> TopAgentResult:
        output_dir_per_run = output_dir_per_run.expanduser().resolve()
        output_dir_per_run.mkdir(parents=True, exist_ok=True)

        tb_path = str(output_dir_per_run / "tb.sv")
        if_path = str(output_dir_per_run / "if.sv")
        rtl_path = str(output_dir_per_run / "rtl.sv")

        tag = output_dir_per_run / "properly_finished.tag"
        if tag.exists():
            tag.unlink()

        is_sim_pass = False
        rtl_code = ""
        input_tokens = 0
        output_tokens = 0
        usage_breakdown: dict | None = None
        error: str | None = None

        try:
            if self.config.is_ablation:
                is_sim_pass, rtl_code, input_tokens, output_tokens = await self._run_instance_ablation(
                    spec=spec, output_dir_per_run=output_dir_per_run
                )
            else:
                (
                    is_sim_pass,
                    rtl_code,
                    input_tokens,
                    output_tokens,
                    usage_breakdown,
                ) = await self._run_instance(
                    spec=spec,
                    output_dir_per_run=output_dir_per_run,
                    golden_tb_path=golden_tb_path,
                    golden_rtl_blackbox_path=golden_rtl_blackbox_path,
                    contract_sva=contract_sva,
                    child_assumes=child_assumes,
                    child_rtl=child_rtl,
                    external_tb=external_tb,
                )
            tag.write_text("1", encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"

        return TopAgentResult(
            output_dir_per_run=str(output_dir_per_run),
            rtl_path=rtl_path,
            tb_path=tb_path,
            if_path=if_path,
            is_sim_pass=is_sim_pass,
            rtl_code=rtl_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
            usage_breakdown=usage_breakdown,
        )
