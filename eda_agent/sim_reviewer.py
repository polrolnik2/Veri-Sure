from __future__ import annotations

import os
import re
import shutil
from typing import Sequence, Tuple

from .bash_tools import CommandResult, run_bash_command


def _require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise FileNotFoundError(f"Required executable '{name}' not found in PATH.")


# A compiler/simulator diagnostic, which always carries a source location:
#   tb.sv:412:9: error: ...        gcc/clang/verilator style
#   %Error-MODMISSING: ...         verilator's own tagged form
# Deliberately NOT a bare "error:" substring. The design under test prints to
# the same stream, so a testbench emitting a diagnostic of its own -- e.g.
# `$display("INTERNAL ERROR: walking-ones expected_pp has %0d ones", n)`, which
# a real persisted booth oracle does -- was being read as a BUILD failure and
# forced an unconditional fail. That made the testbench's own instrumentation
# capable of vetoing its design, which is backwards.
_TOOLCHAIN_ERROR_RE = re.compile(
    r"^[^\n]*?:\d+:(?:\d+:)?\s*error\b|^%Error", re.IGNORECASE | re.MULTILINE
)


def _verilator_has_fatal(stdout: str, stderr: str) -> bool:
    # Verilator typically reports as "%Error:" / "%Error-<TAG>:".
    fatal_re = re.compile(r"^%Error", re.MULTILINE)
    if fatal_re.search(stderr) or fatal_re.search(stdout):
        return True
    text = f"{stdout}\n{stderr}"
    if "syntax error" in text.lower():
        return True
    return bool(_TOOLCHAIN_ERROR_RE.search(text))


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
#
# The leading class is `[\s*=#~+-]*`, not `[^\S\n]*`, because testbenches
# routinely decorate their summary line and the whitespace-only anchor silently
# rejected every decorated form. Measured over the 30 persisted composed
# oracles, five could never print a marker this function accepts, and two of
# those printed exactly
#
#     *** ALL TESTS PASSED ***
#
# so composed_sim was MATHEMATICALLY unable to return pass for those nodes
# regardless of the RTL. Only banner punctuation is allowed in -- letters and
# digits still cannot precede the claim, so "NOT ALL TESTS PASSED" and
# "0 ALL TESTS PASSED" remain rejected.
_EXPLICIT_PASS_RE = re.compile(
    r"^[\s*=#~+-]*(?:PASS|SUCCESS)\b[^\n]*?\ball\b[^\n]*?\bpass(?:ed)?\b"
    r"|^[\s*=#~+-]*ALL\s+(?:\d+\s+)?(?:TESTS?|SCENARIOS?|CASES?)\s+PASSED\b",
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


def check_syntax(
    rtl_path: str,
    extra_sources: "Sequence[str]" = (),
    include_dirs: "Sequence[str]" = (),
) -> Tuple[bool, str]:
    """Lint `rtl_path`, optionally alongside pre-made modules it instantiates.

    A hierarchical DUT linted on its own reports `Cannot find file containing
    module` for every child, which is fatal -- so without `extra_sources` a
    correct hierarchical design is rejected before it is ever simulated, for a
    reason that is about the lint invocation rather than the design.
    """
    _require_executable("verilator")
    incs = " ".join(f"-I{d}" for d in include_dirs)
    extras = " ".join(str(s) for s in extra_sources)
    cmd = (
        f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert "
        f"{incs} {rtl_path} {extras}".replace("  ", " ")
    )
    is_pass, sim_output = run_bash_command(cmd, timeout=60)
    sim_output_obj = CommandResult.model_validate_json(sim_output)
    stdout = sim_output_obj.stdout or ""
    stderr = sim_output_obj.stderr or ""

    # Be permissive about warnings: syntax check should fail only on actual errors.
    is_pass = bool(is_pass) and not _verilator_has_fatal(stdout, stderr)
    return is_pass, sim_output


# NB: distinct from _MULTIDRIVEN_RE above, which is a presence test for lint_tb.
# Defining a second _MULTIDRIVEN_RE shadowed that one and silently disarmed the
# testbench multidriven lint -- caught only by running the full unit tier.
_MULTIDRIVEN_SIGNAL_RE = re.compile(r"%Warning-MULTIDRIVEN:.*?signal '([^']+)'", re.S)


def multidriven_signals(rtl_path: str) -> set[str]:
    """Signals with more than one continuous driver, per Verilator.

    `check_syntax` is deliberately permissive about warnings, which is right for
    WIDTHTRUNC and friends but wrong for this one: two continuous drivers on the
    same signal is not a style preference, it is a design error that synthesis
    rejects and that simulates as X or as a silent last-writer-wins.

    Measured on the recorded fp_adder tree, output_registers glue:

        parent_1  assign valid_out ... x1   (a fresh draw -- correct)
        parent_0  assign valid_out ... x2
        parent_2  assign valid_out ... x3

    The count GROWS across debug attempts. The model's replacement text
    re-declares statements that also live outside the block being replaced, the
    splice duplicates them, and nothing rejects the result -- so each edit
    corrupts the file a little more while the harness reports the attempt as
    syntactically fine.

    Returns a SET so callers can compare before and after an edit and reject
    only what that edit introduced, rather than refusing to work on RTL that
    arrived already broken.
    """
    try:
        ok, out = check_syntax(rtl_path)
        obj = CommandResult.model_validate_json(out)
        text = (obj.stdout or "") + "\n" + (obj.stderr or "")
    except Exception:  # noqa: BLE001
        return set()
    return set(_MULTIDRIVEN_SIGNAL_RE.findall(text))



def overdriven_signals(text: str) -> set[str]:
    r"""Signals more than one block in THIS TEXT drives. Pure Python, no Verilator.

    `multidriven_signals` is a regex over Verilator's MULTIDRIVEN warning, and
    THAT WARNING STOPS AT THE MODULE BOUNDARY. Measured against Verilator 5.038
    under the exact flags `check_syntax` uses (`--lint-only --sv --timing -Wall
    -Wno-fatal --assert`):

        output c;  assign c = a; assign c = ~a;   fires ("multiple
                                                  combinational drivers")
        always @(posedge clk1) c <= a;            fires ("different clocking")
        always @(posedge clk2) c <= b;

        wire w;  assign w = a; assign w = b;      SILENT. exit 0, no warning
        always @(posedge clk) c <= a;             SILENT. exit 0, no warning
        always @(posedge clk) c <= b;

    So the guard sees duplicate drivers on PORTS and goes blind on INTERNAL
    signals -- which is where the editor does its work. §7.1 describes it as
    catching "an edit giving a signal a SECOND continuous driver"; for an
    internal wire, the commonest shape of that edit, it cannot.

    MEASURED, and it latched. Across three live editor sessions the committed
    i2c design carried `assign scl_sync` TWICE (the ChipVerilog candidate it
    started from has one). `scl_sync` is read by the clock divider's reload
    condition, and in the sixth session the two drivers came to disagree --
    `scl_oen & ~sSCL & dSCL` against `cSCL[1] & ~scl_i & scl_oen` -- which in
    Verilog resolves to X wherever they differ. Every commit passed the guard.
    Worse, the agent spent two rounds editing the two copies SEPARATELY,
    refining what it took to be one expression, because nothing it could call
    would say the signal had two drivers.

    Parsing the text settles it, the same way `undriven_signals` settles the
    mirror question, and costs nothing -- so this can run on every staged edit
    rather than only where a Verilator call is affordable.

    Multiple writes from ONE block are not a finding: a reg assigned in two
    branches of a single always block has one driver.
    """
    from .trace_slicer import parse_rtl_blocks

    try:
        blocks = parse_rtl_blocks(text)
    except Exception:  # noqa: BLE001
        return set()
    n: dict[str, int] = {}
    for b in blocks:
        for w in set(b.writes):
            n[w] = n.get(w, 0) + 1
    return {w for w, c in n.items() if c > 1}


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
