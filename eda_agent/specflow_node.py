"""Node execution on the specflow backend.

Written as its own path rather than threaded through `_run_instance`'s
SystemVerilog-shaped control flow. That flow is organised around a single
monolithic `tb.sv` -- three mutually exclusive generation branches, a lint-repair
loop, a mock-DUT alignment pass and a log-marker verdict -- and none of those
steps has a counterpart here. Interleaving would have produced a function whose
branches were half dead on either backend.

Kept from the original path: the contract, `RTLGenerator`, and `RTLEditor` for
repair. Replaced: the oracle, the verdict, and the failure payload the repair
agent receives.

`RTLEditor` is reused rather than rewritten: it is parameterised on a reviewer
object, and `SpecflowReviewer` below has the same three-value shape as
`SimReviewer.review()`, so the editor's `run_simulation` tool keeps working while
the oracle underneath it becomes the cocotb suite and the Python reference model.

That reuse needed one change to the editor, which an earlier version of this
docstring claimed it did not. `RTLEditor.chat` also read `<run>/tb.sv` off disk
to fill its `generated_tb` prompt slot -- a file this backend never writes -- so
the first repair iteration died with `FileNotFoundError` and the specflow repair
loop had never run at all. The editor now takes the oracle text as a parameter;
`describe_oracle` renders it from the reference model and the failing testplan
elements.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence, Tuple

from .config import OpenAIConfig
from .refmodel_editor import SyncRefModelDebugger
from .rtl_editor import RTLEditor
from .rtl_generator import RTLGenerator
from .sim_reviewer import check_syntax

logger = logging.getLogger(__name__)

# The SystemVerilog path clipped the testbench at 8000 characters, a budget
# sized for a monolithic blob that was mostly boilerplate. What specflow sends
# instead is the reference model: dense, and every line of it is specification.
# Truncating it at 8000 would hand the agent half a specification and let it
# infer the rest from the RTL, which is exactly the wrong direction.
_TB_TEXT_CHARS = 16000


def _load_testplan(run_dir: Path) -> list[dict] | None:
    """Testplan elements, for naming what each failing testpoint was checking."""
    path = Path(run_dir) / "specflow" / "testplan.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        data = data.get("elements") or data.get("testplan") or []
    return data if isinstance(data, list) else None


def _where(m: dict) -> str:
    """Where in the run the DUT first left the model's output sequence.

    A state index, not a cycle and not a stimulus vector. The checks compare
    run-length-encoded output states, so "@state7" means the DUT's seventh
    distinct output state is not the model's seventh -- how many cycles each was
    held is deliberately not part of the question.

    This replaces `_collapse`, which existed only because a vector held N cycles
    produced N byte-identical mismatch rows that had to be folded back into one
    with a step range. Comparing sequences instead of instants means each check
    yields at most one row, so there is nothing left to collapse.
    """
    at = m.get("step")
    return f"@state{at}" if isinstance(at, int) else ""


def format_failures(
    payload: list[dict], *, per_testpoint: int = 6, limit: int = 160,
    trace: dict | None = None,
) -> str:
    """Turn per-testpoint records into the repair agent's prompt payload.

    Deliberately not a log excerpt. `rtl_editor` receives a keyword-filtered
    slice of simulator stdout today, and the recorded failure of that approach
    was 210 MISMATCH lines carrying two actual values. Here every line already
    names the check, both values, and the stimulus that produced them -- and
    every failing testpoint is present, not only the first one hit.

    The budget is **per testpoint**, which is the whole point. A single global
    cap of 40 spent all 40 rows on the first failing testpoint: on
    i2c_master_bit_ctrl that left 21 of 22 testpoints reduced to a header and
    "... further mismatches omitted", so the agent knew which outputs diverged
    and had not one concrete value for any of them. A wide, shallow view of
    every failure beats a deep view of one, because the repair agent's first job
    is to find the pattern across them.
    """
    if not payload:
        return ""

    lines: list[str] = []
    if trace:
        # Ahead of the per-testpoint detail on purpose: "which output is wrong
        # most often, and from which step" is the question a repair agent asks
        # first, and it is answerable across the whole failure set rather than
        # one testpoint at a time.
        outs = ", ".join(f"{d['sig']}x{d['mismatches']}" for d in trace.get("fail_outputs") or [])
        lines.append(
            f"SUMMARY: {trace.get('total_mismatches')} mismatches across "
            f"{len(trace.get('failing_testpoints') or [])} testpoints"
            + (f"; first at stimulus step {trace['fail_step']}"
               if trace.get("fail_step") is not None else "")
            + (f"; diverging outputs {outs}" if outs else "")
        )
        if trace.get("wave_vcd"):
            lines.append(f"WAVEFORM: {trace['wave_vcd']}")
        lines.append("")
    shown = 0
    for entry in payload:
        checks = ", ".join(entry.get("failed_checks") or [])
        sigs = ", ".join(entry.get("failed_signals") or [])
        head = f"[{entry['testpoint']}] FAIL -- checks {checks}"
        # The diverging signals, named up front. One check covers every signal
        # the coverage model listed for it, so the check UID alone does not say
        # which output is wrong -- and that is the whole question a repair agent
        # is trying to answer.
        lines.append(head + (f" -- diverging outputs: {sigs}" if sigs else ""))
        rows = entry.get("mismatches") or []
        here = 0
        for m in rows:
            if here >= per_testpoint or shown >= limit:
                # No silent caps: say how many were dropped and where the whole
                # set is, so a truncated list is never read as the population.
                lines.append(
                    f"  ... {len(rows) - here} further mismatch(es) for this "
                    f"testpoint omitted; all are in results/{entry['testpoint']}.json"
                )
                break
            ctx = ", ".join(f"{k}={v}" for k, v in (m.get("ctx") or {}).items())
            sig = ", ".join(m.get("signals") or []) or m.get("signal")
            head = " ".join(
                x for x in (str(m.get("check")), sig, _where(m)) if x
            )
            lines.append(
                f"  {head}: expected={m.get('expected')} got={m.get('got')}"
                + (f" on {ctx}" if ctx else "")
            )
            # The reason carries the cases a value pair cannot state: a design
            # that stopped producing states early, or produced more than the
            # model has. Those have no diverging signal to name, so without it
            # the line would read "expected=None got=None" and say nothing.
            reason = m.get("reason")
            if reason and not m.get("signals") and not m.get("signal"):
                lines.append(f"    {reason}")
            for t in m.get("timeouts") or []:
                lines.append(f"    timeout: {t}")
            shown += 1
            here += 1
    return "\n".join(lines)


class SpecflowReviewer:
    """`SimReviewer`-shaped adapter over the specflow verdict.

    Returns `(is_pass, mismatch_cnt, sim_output)` so `RTLEditor` is unchanged.
    `mismatch_cnt` is the count of *failing testpoints*, which is what the
    editor's rollback judgement compares round to round -- a count that falls as
    repairs land, exactly as the mismatch count did.
    """

    def __init__(self, *, built, hdl_toplevel: str, output_dir: Path,
                 extra_sources: Sequence[Path | str] = (),
                 include_dirs: Sequence[Path | str] = ()):
        self._built = built
        self._top = hdl_toplevel
        self._dir = Path(output_dir)
        # Pre-made children the candidate instantiates. Held on the reviewer
        # because every repair iteration re-elaborates, so supplying them once
        # at generation time would not be enough.
        self._extra = list(extra_sources)
        self._incs = list(include_dirs)
        self._iteration = 0
        self.golden_rtl_path = None  # rtl_editor getattrs this

    def review(self) -> Tuple[bool, int, str]:
        from specflow.integration import failure_payload, judge, trace_summary

        verdict, info = judge(
            rtl_path=self._dir / "rtl.sv",
            hdl_toplevel=self._top,
            suite_dir=self._built.suite_dir,
            refmodel_path=self._built.refmodel_path,
            bins=self._built.bins,
            iteration=self._iteration,
            extra_sources=self._extra,
            include_dirs=self._incs,
        )
        self._iteration += 1

        payload = failure_payload(self._built.suite_dir)
        wave = info.get("wave_vcd")
        tr = trace_summary(self._built.suite_dir, Path(wave) if wave else None)
        stdout = format_failures(payload, trace=tr) or verdict.reason

        # A build failure is reported as such rather than as failing testpoints,
        # so the editor is not sent after RTL logic for a lowering error.
        sim_output = json.dumps(
            {
                # `rtl_editor._summarize_sim_log_json` exists to pull signal out
                # of raw simulator stdout. This payload *is* the signal, already
                # selected and budgeted, and running the SV filter over it threw
                # away every value row -- the filter requires the literal word
                # "mismatch" in a line, and these read "expected=1 got=0".
                "format": "specflow",
                "stdout": stdout,
                "stderr": "" if info.get("build_ok") else verdict.reason,
                "verdict": verdict.outcome,
                "testpoints": info.get("results", {}),
                "uncovered": info.get("uncovered", []),
                # The temporal half. Without this the repair agent gets which
                # testpoints failed and nothing about when or where to look --
                # measured on the last run to reach the debugger, `fail_time`,
                # `fail_outputs`, `input_window` and `alignment_diagnosis` were
                # all null or zero while the data sat on disk unread.
                "trace": tr,
            },
            indent=2,
        )
        return verdict.outcome == "ACCEPT", len(verdict.failing), sim_output


async def run_specflow_node(
    *,
    cfg: OpenAIConfig,
    spec: str,
    contract_json: str,
    output_dir_per_run: Path,
    rtl_gen: RTLGenerator,
    sim_max_retry: int = 4,
    debug_max_trials: int = 30,
    model_port: str = "replay",
    port_settings: object | None = None,
    max_repairs: int = 3,
    refmodel_max_repairs: int | None = None,
    #: Edit attempts per debug turn. Zero disables the agentic path entirely and
    #: the stage falls back to prose-driven regeneration, which is what every
    #: run did before this existed.
    refmodel_debug_attempts: int = 6,
    #: Judging passes. Each is ~one model call per requirement, so this is the
    #: expensive budget; attempts inside a turn are pure Python and nearly free.
    refmodel_judge_turns: int = 3,
    #: Source of a known-good reference model for this design, for trust gate 3.
    #: Read here rather than passed as text so the caller only has to know where
    #: its controls live. It is never shown to the debugger or the generator.
    refmodel_control: Path | str | None = None,
    #: Generate a second oracle set from the requirements alone and screen it
    #: beside the judge's, reporting both in `trust.json`. Read-only: the
    #: judge's oracles still drive the loop, so a run with this on is still a
    #: valid regression test of a run with it off.
    #: Requirement-only oracles drive the loop; the judge stops deciding.
    variants: bool = False,
    correspondence: bool = False,
    adequacy_rounds: int = 0,
    reconsider_rounds: int = 0,
    advisory_verdicts: frozenset[str] = frozenset(),
    extra_sources: Sequence[Path | str] = (),
    include_dirs: Sequence[Path | str] = (),
    reuse: bool = False,
    divide_s1: bool = True,
    fanout: bool = True,
) -> Tuple[bool, str, dict[str, Any]]:
    """Build the oracle, generate RTL, repair until the gate accepts.

    Returns `(accepted, rtl_code, detail)`.
    """
    from specflow.integration import build_artifacts, describe_oracle

    output_dir_per_run = Path(output_dir_per_run)
    detail: dict[str, Any] = {"backend": "specflow", "history": []}

    # The oracle is built first and must be certified before any RTL exists.
    # Generating RTL against an uncertified oracle would be repairing toward a
    # standard nothing verified -- and it is also what keeps the reference model
    # independent, since there is no rtl.sv in existence while it is written.
    built = build_artifacts(
        run_dir=output_dir_per_run,
        spec=spec,
        contract_json=contract_json,
        model_port=model_port,
        port_settings=port_settings,
        max_repairs=max_repairs,
        refmodel_max_repairs=refmodel_max_repairs,
        reuse=reuse,
        divide_s1=divide_s1,
        fanout=fanout,
        # The reference model is repaired by EDITING it against the judge's
        # oracles rather than by regenerating it from the judge's prose. This is
        # the only place holding both a specflow model port and an OpenAIConfig,
        # which is why the construction happens here and not in `specflow/`.
        refmodel_debugger=(
            SyncRefModelDebugger(cfg, max_attempts=refmodel_debug_attempts)
            if refmodel_debug_attempts > 0 else None
        ),
        refmodel_judge_turns=refmodel_judge_turns,
        refmodel_control=(
            Path(refmodel_control).read_text(encoding="utf-8")
            if refmodel_control and Path(refmodel_control).is_file() else None
        ),
        variants=variants,
        correspondence=correspondence,
        adequacy_rounds=adequacy_rounds,
        reconsider_rounds=reconsider_rounds,
        advisory_verdicts=advisory_verdicts,
    )
    detail["artifacts"] = {"ok": built.ok, "stage": built.stage, "reason": built.reason}
    if getattr(built, "cache", None) is not None:
        # Reported next to the verdict rather than only on disk: a cache that
        # stopped working costs ~30x while every artifact still validates, so it
        # has to land where someone already looks.
        detail["cache"] = built.cache.to_dict()
        if built.cache.failing():
            logger.warning("prompt cache below threshold:\n%s", built.cache.render())
    if not built.ok:
        logger.error("specflow artifacts failed at %s: %s", built.stage, built.reason)
        return False, "", detail

    contract = json.loads(contract_json) if contract_json.strip() else {}
    top = str(contract.get("module_name") or "TopModule")
    rtl_path = output_dir_per_run / "rtl.sv"

    ok, rtl_code = await rtl_gen.chat(
        input_spec=spec,
        testbench="",  # the suite is not a prompt input on this backend
        interface="",
        rtl_path=str(rtl_path),
        contract_json=contract_json,
    )
    if not ok or not rtl_code.strip():
        detail["history"].append("RTL generation produced nothing")
        return False, rtl_code, detail

    rtl_path.write_text(rtl_code, encoding="utf-8")
    syntax_ok, syntax_log = check_syntax(
        str(rtl_path), [str(p) for p in extra_sources], [str(p) for p in include_dirs]
    )
    if not syntax_ok:
        detail["syntax"] = syntax_log
        detail["history"].append("RTL failed syntax check")
        return False, rtl_code, detail

    reviewer = SpecflowReviewer(
        built=built, hdl_toplevel=top, output_dir=output_dir_per_run,
        extra_sources=extra_sources, include_dirs=include_dirs,
    )
    remaining = int(debug_max_trials)

    for iteration in range(max(1, sim_max_retry)):
        is_pass, failing, sim_output = reviewer.review()
        verdict = json.loads(sim_output)["verdict"]
        detail["history"].append(f"iter {iteration}: {verdict} ({failing} failing)")
        detail["verdict"] = verdict

        if is_pass:
            return True, rtl_path.read_text(encoding="utf-8"), detail

        if verdict != "REPAIR_RTL":
            # EXTEND_TB and STALLED are not RTL problems, and reporting them as
            # one is what sends a repair agent after the wrong artifact.
            return False, rtl_path.read_text(encoding="utf-8"), detail

        if remaining <= 0:
            detail["history"].append("debug budget exhausted")
            return False, rtl_path.read_text(encoding="utf-8"), detail

        editor = RTLEditor(cfg, sim_reviewer=reviewer, max_trials=remaining)
        _, repaired, used, _ = await editor.chat(
            spec=spec,
            output_dir_per_run=str(output_dir_per_run),
            sim_failed_log=sim_output,
            sim_mismatch_cnt=failing,
            contract_json=contract_json,
            max_trials=remaining,
            # There is no `tb.sv` on this backend. Supplying the oracle
            # explicitly is what the editor needs; reading that path
            # unconditionally is what killed this loop before it ever ran.
            tb_text=describe_oracle(
                suite_dir=built.suite_dir,
                refmodel_path=built.refmodel_path,
                testplan=_load_testplan(output_dir_per_run),
                max_chars=_TB_TEXT_CHARS,
            ),
            tb_clip_chars=_TB_TEXT_CHARS,
        )
        remaining -= max(1, int(used))
        if repaired.strip():
            rtl_path.write_text(repaired, encoding="utf-8")
        else:
            detail["history"].append("repair produced no change")
            return False, rtl_path.read_text(encoding="utf-8"), detail

    return False, rtl_path.read_text(encoding="utf-8"), detail
