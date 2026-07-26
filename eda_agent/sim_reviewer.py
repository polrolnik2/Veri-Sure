from __future__ import annotations

import os
import re
import shutil
from typing import Tuple

from .bash_tools import CommandResult, run_bash_command


def _require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise FileNotFoundError(f"Required executable '{name}' not found in PATH.")


def _verilator_has_fatal(stdout: str, stderr: str) -> bool:
    # Verilator typically reports as "%Error:" / "%Error-<TAG>:".
    fatal_re = re.compile(r"^%Error", re.MULTILINE)
    if fatal_re.search(stderr) or fatal_re.search(stdout):
        return True
    # Some toolchains may prefix with "Error:" without the % marker.
    text = f"{stdout}\n{stderr}".lower()
    return ("syntax error" in text) or ("error:" in text)


_MULTIDRIVEN_RE = re.compile(r"^%Warning-MULTIDRIVEN", re.MULTILINE)

# An explicit, self-declared overall PASS verdict in a form other than the two
# canonical markers ("SIMULATION PASSED", "Mismatches: N in M samples").
#
# Self-generated testbenches do not reliably emit either. The golden booth
# composition -- proven correct by
# tests/fixtures/golden_children/booth/verify.sh and printing
#
#     PASS: All 11 scenarios passed
#
# after eleven individual PASS lines -- was scored as a DESIGN FAILURE by this
# function purely because that phrasing was unrecognised. In a real run that
# spends the whole glue-retry budget redrawing a composition which already
# works, and the recorded failure_summary is whatever line the summariser
# happened to grab (observed: a bare "====" separator), so nothing in the log
# says the verdict was a scoring artefact.
#
# Deliberately narrow. A false POSITIVE certifies broken hardware, which is far
# worse than a false negative, so this requires an unambiguous whole-run
# claim -- "all ... passed", not a bare per-case "PASS" line -- and the caller
# additionally requires zero mismatches and no failure markers.
_EXPLICIT_PASS_RE = re.compile(
    r"^[^\S\n]*(?:PASS|SUCCESS)\b[^\n]*?\ball\b[^\n]*?\bpass(?:ed)?\b"
    r"|^[^\S\n]*ALL\s+(?:\d+\s+)?(?:TESTS?|SCENARIOS?|CASES?)\s+PASSED\b",
    re.IGNORECASE | re.MULTILINE,
)

_ANY_FAILURE_MARKER_RE = re.compile(
    r"\bSIMULATION\s+FAILED\b|^[^\S\n]*FAIL\b|\bassertion\s+failed\b|\bMISMATCH",
    re.IGNORECASE | re.MULTILINE,
)


def has_explicit_pass_verdict(stdout: str) -> bool:
    """True iff `stdout` declares an unambiguous whole-run PASS and nothing
    anywhere in it reports a failure."""
    if not stdout:
        return False
    return bool(_EXPLICIT_PASS_RE.search(stdout)) and not _ANY_FAILURE_MARKER_RE.search(stdout)


def _has_multidriven_warning(stdout: str, stderr: str) -> bool:
    """True iff Verilator flagged a signal with multiple driving blocks.

    NOT folded into `_verilator_has_fatal` — that function is shared by
    `check_syntax` AND `sim_review` (RTLEditor's actual pass/fail oracle), and
    real captured glue-RTL (tests/stage_eval/fixtures/stages/booth_multiplier/
    .../parent_0/rtl.sv) legitimately produces this warning from two
    textually-identical duplicate `assign` statements — inert, not a real
    race, and the run correctly proceeded. Tightening the shared fatal check
    would regress that already-passing real run. This is a narrow, opt-in
    helper each caller decides whether to treat as fatal for its own context
    (see tb_editor.py::_lint_tb, which does; sim_reviewer.py::check_syntax,
    which deliberately does not — TBEditor's mock-DUT scaffolding never
    legitimately produces this warning, so there's no benign case there to
    protect, unlike glue-RTL generation).
    """
    return bool(_MULTIDRIVEN_RE.search(stdout) or _MULTIDRIVEN_RE.search(stderr))


def check_syntax(rtl_path: str) -> Tuple[bool, str]:
    _require_executable("verilator")
    cmd = f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {rtl_path}"
    is_pass, sim_output = run_bash_command(cmd, timeout=60)
    sim_output_obj = CommandResult.model_validate_json(sim_output)
    stdout = sim_output_obj.stdout or ""
    stderr = sim_output_obj.stderr or ""

    # Be permissive about warnings: syntax check should fail only on actual errors.
    is_pass = bool(is_pass) and not _verilator_has_fatal(stdout, stderr)
    return is_pass, sim_output


def sim_review_mismatch_cnt(stdout: str) -> int:
    mismatch_cnt = 0
    if "SIMULATION FAILED" in stdout:
        re_str = r"SIMULATION FAILED - (\d*) MISMATCHES DETECTED"
        m = re.search(re_str, stdout)
        if m is not None:
            mismatch_cnt = int(m.group(1))
            return mismatch_cnt
    # Fallback for VerilogEval-style golden testbenches.
    m2 = re.search(r"^Mismatches:\s*(\d+)\s*in\s*(\d+)\s*samples$", stdout, re.MULTILINE)
    if m2:
        mismatch_cnt = int(m2.group(1))
    return mismatch_cnt


def sim_review(
    output_path_per_run: str,
    golden_rtl_path: str | None = None,
) -> Tuple[bool, int, str]:
    _require_executable("verilator")
    rtl_path = f"{output_path_per_run}/rtl.sv"
    sim_bin = f"{output_path_per_run}/sim_output.bin"
    tb_path = f"{output_path_per_run}/tb.sv"
    if golden_rtl_path is None:
        golden_rtl_path = ""
    if os.path.isfile(sim_bin):
        os.remove(sim_bin)

    # Build + run with Verilator.
    # Notes:
    # - Use --timing to support delays/event controls in testbenches.
    # - Use --trace so $dumpfile/$dumpvars can generate wave.vcd for debugging.
    # - Use --assert (or default-on in newer versions) for assertion support.
    srcs = f"{tb_path} {rtl_path} {golden_rtl_path}".strip()
    cmd = (
        "verilator --binary -j 0 --sv --timing --trace --assert -Wall -Wno-fatal "
        f"--Mdir obj_dir -o {sim_bin} {srcs}; "
        f"{sim_bin}"
    )
    cmd_ok, sim_output = run_bash_command(cmd, timeout=120, cwd=output_path_per_run)
    sim_output_obj = CommandResult.model_validate_json(sim_output)
    stdout = sim_output_obj.stdout or ""
    stderr = sim_output_obj.stderr or ""

    mismatch_cnt = sim_review_mismatch_cnt(stdout)
    if mismatch_cnt == 0 and re.search(r"assertion failed", f"{stdout}\n{stderr}", re.IGNORECASE):
        # Treat assertion failures as mismatches so the debugger loop can engage.
        mismatch_cnt = 1

    # Determine pass/fail primarily from the testbench's explicit result markers,
    # instead of the process return code. Some testbenches may exit non-zero
    # despite printing "SIMULATION PASSED" (or "Mismatches: 0 ...").
    # The canonical marker, or an unambiguous whole-run PASS verdict in another
    # phrasing (see _EXPLICIT_PASS_RE) with zero mismatches.
    has_pass_marker = "SIMULATION PASSED" in stdout or (
        mismatch_cnt == 0 and has_explicit_pass_verdict(stdout)
    )
    has_mismatch_summary = bool(
        re.search(r"^Mismatches:\s*\d+\s*in\s*\d+\s*samples$", stdout, re.MULTILINE)
    )
    # Only treat *harness* timeouts as fatal. Many VerilogEval testbenches print
    # "TIMEOUT" as a watchdog message even for successful runs (they still emit
    # the "Mismatches: ..." summary). The harness timeout is surfaced in stderr
    # by `run_bash_command` as "Timeout ... reached.".
    has_timeout_marker = "Timeout" in stderr

    # Treat warnings as non-fatal; only block on clear compile/runtime errors.
    has_fatal = _verilator_has_fatal(stdout, stderr)

    is_pass_by_log = has_pass_marker or (has_mismatch_summary and mismatch_cnt == 0)
    is_pass = is_pass_by_log and not (has_timeout_marker or has_fatal)

    # If the command timed out or crashed without printing any summary, keep it failed.
    if not is_pass and not (has_pass_marker or has_mismatch_summary) and cmd_ok:
        # cmd_ok with no markers is ambiguous; treat as failed and keep mismatch_cnt as-is.
        pass

    assert isinstance(sim_output, str) and isinstance(is_pass, bool)
    return is_pass, mismatch_cnt, sim_output


class SimReviewer:
    def __init__(
        self,
        output_path_per_run: str,
        golden_rtl_path: str | None = None,
    ):
        self.output_path_per_run = output_path_per_run
        self.golden_rtl_path = golden_rtl_path

    def review(self) -> Tuple[bool, int, str]:
        return sim_review(
            self.output_path_per_run,
            self.golden_rtl_path,
        )
