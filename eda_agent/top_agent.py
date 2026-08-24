from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import traceback
from typing import Tuple

from .bash_tools import CommandResult, run_bash_command
from .architect_agent import ArchitectAgent
from .contract_linter import lint_contract_json, render_contract_issues
from .config import OpenAIConfig
from .model import UsageBreakdown, get_model_usage
from .rtl_generator import RTLGenerator
# NOTE: there is no `tb_generator` import. The SystemVerilog testbench path is
# retired: `tb_generator.py` and its prompt corpus are deleted, `_run_instance`
# is gone, and specflow builds the oracle instead. See
# docs/specflow-migration.md.

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
    (
        re.compile(
            r"isn't a constant|two-state constant|"
            r"Width of :\+ or :- bit slice range isn't a constant"
        ),
        "HINT: a part-select WIDTH and a replication COUNT must be compile-time "
        "constants in SystemVerilog. `x[hi:lo]` with a variable bound, "
        "`x[i +: n]` with a variable `n`, and `{n{1'b0}}` with a variable `n` are "
        "all illegal, however reasonable they look.\n"
        "  A VARIABLE amount is expressed as a SHIFT, not as a slice:\n"
        "    WRONG:  sig[shift_amt:0]        RIGHT:  sig >> shift_amt\n"
        "    WRONG:  {shift_amt{1'b0}}       RIGHT:  ('0 << shift_amt) / a mask\n"
        "    WRONG:  x[i +: n]  (n varies)   RIGHT:  (x >> i) & ((1<<n)-1) with n constant\n"
        "  A variable INDEX is fine when the WIDTH is fixed: `x[i +: 8]` is legal, "
        "`x[i +: n]` is not. Alignment and normalisation stages hit this constantly "
        "— they want a variable shift, so write a shift.",
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
    # Which testbench path builds the oracle.
    #   "sv"       -- TBGenerator writes one monolithic tb.sv (the original path)
    #   "specflow" -- spec -> requirements -> testplan -> coverage -> cocotb suite
    #                 with a Python reference model (see specflow/ and
    #                 docs/specflow-migration.md)
    # specflow's verdict is three-valued per testpoint and is written as data by
    # the runtime, rather than parsed from log markers -- see sim_reviewer's
    # _EXPLICIT_PASS_RE for why that distinction exists.
    tb_backend: str = "specflow"
    # How specflow's five agent calls reach a model. "file" emits each prompt and
    # stops so it can be answered by hand; "replay" reads recorded fixtures and
    # needs no model at all; "api" is the eventual HTTP path.
    specflow_model_port: str = "file"
    #: Every model-call switch for the specflow stages, as one explicit object.
    #: `None` means the defaults. Never read from the environment at call time:
    #: `load_env_file` overrides `os.environ` so a rotated key can reach a live
    #: session, which means any knob also taken from the environment is settled
    #: by whichever file a callee re-reads rather than by what the caller asked.
    specflow_port_settings: object | None = None
    # Pre-made modules the generated RTL may instantiate but does not define,
    # and the include directories their headers live in. A hierarchical DUT
    # cannot elaborate without them, and the resulting build error reads as a
    # defect in the generated RTL rather than a missing library. They are
    # libraries, never oracle inputs: the reference model still derives the
    # composed behaviour from the specification alone.
    specflow_extra_sources: tuple[str, ...] = ()
    specflow_include_dirs: tuple[str, ...] = ()
    #: Reuse certified specflow artifacts already in the run directory instead
    #: of regenerating them. The gates are always re-run on what is reused, so
    #: this skips the model calls, never the checks.
    specflow_reuse: bool = False
    #: S1 by division at authorial boundaries plus a per-unit classifier,
    #: instead of the generative decomposition. On by default; set False for an
    #: A/B against the generative arm on the same task, model and effort.
    specflow_divide_s1: bool = True
    #: One small call per item for S2, S3 and the reference model.
    specflow_fanout: bool = True
    #: Repair rounds for each specflow stage, and for the reference model
    #: specifically. The reference model gets its own because its feedback comes
    #: from a judge rather than a script, and it converges: 8 -> 4 -> 3 -> 2
    #: blocking verdicts over four rounds on i2c_master_bit_ctrl, still
    #: descending when the budget ran out.
    specflow_max_repairs: int = 3
    specflow_refmodel_max_repairs: int = 6
    #: Edit attempts per debug turn on the reference model. 0 disables the
    #: agentic path and falls back to prose-driven regeneration.
    specflow_refmodel_debug_attempts: int = 6
    #: Judging passes. Each is ~one call per requirement, so this is the
    #: expensive budget; the attempts inside a turn are pure Python.
    specflow_refmodel_judge_turns: int = 3
    #: Path to a known-good reference model for this design, for trust gate 3.
    #: Only the benchmark runners know where controls live, so this stays a
    #: path they set rather than something discovered here.
    specflow_refmodel_control: str | None = None
    #: Report a requirement-only oracle set beside the judge's. Read-only.
    specflow_compare_oracles: bool = False
    #: Requirement-only oracles drive the loop; the judge stops deciding.
    specflow_oracle_driven: bool = False
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

    async def _run_instance_specflow(
        self,
        *,
        spec: str,
        output_dir_per_run: Path,
        golden_tb_path: str | None = None,
        contract_sva: list[dict] | None = None,
        child_assumes: dict | None = None,
        child_rtl: dict[str, str] | None = None,
    ) -> Tuple[bool, str, int, int, dict | None]:
        """The default path: contract, then specflow's oracle, then RTL repair.

        Deliberately short. The SystemVerilog path's length came almost entirely
        from the testbench being one opaque artifact -- three generation
        branches, a lint-repair loop, a mock-DUT alignment pass, and a verdict
        recovered from log prose. Here the oracle is built and certified by
        gates before any RTL exists, and the verdict arrives as data.
        """
        from .specflow_node import run_specflow_node

        architect = ArchitectAgent(self.cfg)
        rtl_gen = RTLGenerator(self.cfg)

        architect.reset()
        # `golden_tb_path` reaches the ARCHITECT only, and only to pin the
        # interface: module name, port names, directions and widths. On the
        # benchmark path the generated RTL is compiled against the golden
        # testbench, so an inferred name that differs by one character fails
        # every node for a reason that has nothing to do with the design.
        #
        # It goes no further. `build_artifacts` receives `spec` and
        # `contract_json` and nothing else, so neither the requirements nor the
        # reference model can see golden -- which is the isolation property the
        # oracle depends on, and it is enforced by what is passed rather than by
        # an instruction.
        contract_json = await self._build_contract_json(
            architect=architect,
            spec=spec,
            golden_tb_path=golden_tb_path,
            output_dir_per_run=output_dir_per_run,
        )

        # Orchestrator-supplied fields, merged exactly as the original path did.
        if contract_sva or child_assumes or child_rtl:
            try:
                obj = json.loads(contract_json)
                if contract_sva:
                    obj["contract_sva"] = contract_sva
                if child_assumes:
                    obj["child_assumes"] = child_assumes
                if child_rtl:
                    for name in child_rtl:
                        obj.setdefault("child_assumes", {}).setdefault(name, {})[
                            "rtl_available"
                        ] = True
                contract_json = json.dumps(obj, indent=2)
                (output_dir_per_run / "contract.json").write_text(
                    contract_json, encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                logger.exception("failed to merge orchestrator fields into contract")

        accepted, rtl_code, detail = await run_specflow_node(
            cfg=self.cfg,
            spec=spec,
            contract_json=contract_json,
            output_dir_per_run=output_dir_per_run,
            rtl_gen=rtl_gen,
            sim_max_retry=self.config.sim_max_retry,
            debug_max_trials=self.config.debug_max_trials,
            model_port=self.config.specflow_model_port,
            port_settings=self.config.specflow_port_settings,
            extra_sources=self.config.specflow_extra_sources,
            include_dirs=self.config.specflow_include_dirs,
            reuse=self.config.specflow_reuse,
            divide_s1=self.config.specflow_divide_s1,
            fanout=self.config.specflow_fanout,
            max_repairs=self.config.specflow_max_repairs,
            refmodel_max_repairs=self.config.specflow_refmodel_max_repairs,
            refmodel_debug_attempts=self.config.specflow_refmodel_debug_attempts,
            refmodel_judge_turns=self.config.specflow_refmodel_judge_turns,
            refmodel_control=self.config.specflow_refmodel_control,
            compare_oracles=self.config.specflow_compare_oracles,
            oracle_driven=self.config.specflow_oracle_driven,
        )

        (output_dir_per_run / "specflow_node.json").write_text(
            json.dumps(detail, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        breakdown = UsageBreakdown(
            architect=get_model_usage(architect._agent.model),
            rtl_gen=get_model_usage(rtl_gen._agent.model),
        )
        total_in, total_out = breakdown.total
        return accepted, rtl_code, total_in, total_out, breakdown.to_dict()

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

        # Persist the spec at the node. `cli.py:74` writes prompt.txt for the
        # `run` subcommand, but `benchmarks/run_verilog_eval_v2.py` builds its
        # prompt separately and never wrote it -- so a benchmark node had no spec
        # on disk at all. specflow's S1 reads it, and it is what makes an offline
        # replay of a node possible.
        prompt_path = output_dir_per_run / "prompt.txt"
        if not prompt_path.exists():
            prompt_path.write_text(spec.rstrip() + "\n", encoding="utf-8")

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
            elif self.config.tb_backend == "specflow":
                (
                    is_sim_pass,
                    rtl_code,
                    input_tokens,
                    output_tokens,
                    usage_breakdown,
                ) = await self._run_instance_specflow(
                    spec=spec,
                    output_dir_per_run=output_dir_per_run,
                    golden_tb_path=golden_tb_path,
                    contract_sva=contract_sva,
                    child_assumes=child_assumes,
                    child_rtl=child_rtl,
                )
            else:
                raise ValueError(
                    f"unknown tb_backend {self.config.tb_backend!r}. The "
                    f"SystemVerilog testbench path has been retired -- "
                    f"tb_generator.py and its prompt corpus are deleted, and "
                    f"specflow is the only backend. See "
                    f"docs/specflow-migration.md."
                )
            tag.write_text("1", encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            # Recording the message on the result is not the same as reporting
            # it. Before this, a leaf whose TB stage raised returned normally
            # with `error` set, wrote no artifact and logged nothing, so the
            # re-decomposition that read its failure report got
            # "(no structured failure artifacts captured)" -- accurate, and
            # useless. Measured on fp_pack_invalid (run fp_adder_e2e,
            # 2026-08-03): two independent attempts, ~45 minutes each, both
            # leaving only the Architect's four files and no cause anywhere.
            #
            # Both halves are needed. The log line makes it diagnosable while
            # the run is alive; the artifact makes it diagnosable afterwards,
            # and is what `_harvest_failure` reads back into the digest.
            logger.exception("Leaf run failed for %s", output_dir_per_run.name)
            try:
                self._write_output(
                    output_dir_per_run=output_dir_per_run,
                    file_name="leaf_exception.txt",
                    content=f"{error}\n\n{traceback.format_exc()}",
                )
            except Exception:  # noqa: BLE001 — reporting a failure must not raise
                logger.debug("could not write leaf_exception.txt", exc_info=True)

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
