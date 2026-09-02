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
                 include_dirs: Sequence[Path | str] = (),
                 stager: "SpecflowStimulusStager | None" = None,
                 oracles: Sequence[Any] = (), contract: dict | None = None):
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
        #: Published to after every run, so `add_stimulus`'s "must currently be
        #: uncovered" gate is never reading a stale set.
        self._stager = stager
        #: THE FROZEN ORACLE SET, and the contract `ports_read` needs. Held here
        #: because the per-requirement verdict has to be recomputed on the
        #: recording each run writes, and this is the only object that knows a
        #: run just happened.
        self._oracles = list(oracles)
        self._contract = dict(contract or {})
        #: The waveform the LAST run dumped, when one was. Only `explain`'s
        #: block-internals half needs it, so None degrades that half and
        #: nothing else.
        self.vcd_path = None
        #: `{tp_uid: wave.vcd}` from the last run. Empty when nothing was
        #: dumped. One waveform per testpoint, because that is how `run_suite`
        #: writes them -- one simulator process each.
        self.vcd_by_tp: dict = {}
        #: `{req_uid: (OracleResult, trace_dict)}` from the LAST run.
        #:
        #: THIS IS THE LINK THAT WAS MISSING. `_EditSession.req_results` has
        #: always existed and `explain`/`list_failing_requirements` have always
        #: read it, and nothing anywhere wrote it -- so the requirement surface
        #: was registered as tools, described in the prompt, and permanently
        #: empty: `list_failing_requirements()` returned `[]` however many
        #: requirements were failing, and `explain(uid)` could only hand back
        #: the requirement's text with "no per-requirement result is available".
        #: The verdicts existed the whole time; the testpoint-level judge simply
        #: never carried them across.
        self.req_results: dict = {}

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
        self.vcd_path = Path(wave) if wave else None
        tr = trace_summary(self._built.suite_dir, Path(wave) if wave else None)
        self.req_results = self._decide_requirements()

        # THE SET `add_stimulus` GATES ON MUST BE THE SET THE AGENT IS SHOWN.
        #
        # This used to come from `_uncovered_requirements(verdict.not_exercised,
        # ...)`, and `gate.evaluate` returns on its FIRST matching branch:
        #
        #     if failing:
        #         return GateVerdict("REPAIR_RTL", failing=failing, ...)
        #
        # -- with `not_exercised` left at its default. A debug session has
        # failing testpoints by definition, so that branch always wins,
        # `not_exercised` is always empty, and `_uncovered_requirements` returns
        # an empty set every round. `add_stimulus` was therefore REFUSING EVERY
        # REQUEST for the whole of any session it could be useful in; it could
        # only have worked once nothing failed, when there is nothing to stage.
        #
        # MEASURED on run 8, the first run whose agent ever reached the tool:
        # four calls, four refusals -- REQ-0076 twice, REQ-0078, REQ-0004, all
        # of them uids `list_failing_requirements` had just listed as UNCOVERED
        # in the same session. The agent was handed a list and told every entry
        # on it was "not currently uncovered".
        #
        # `req_results` is the per-requirement tri-state the whole surface
        # already reports, and it is what `_uncovered_requirements`'s own
        # docstring called "the exact answer" it could not reach. It can now.
        # The old testpoint fold stays only as a fallback for a backend that
        # decides nothing per requirement.
        if self._stager is not None:
            self._stager.uncovered = (
                {u for u, (r, _t) in (self.req_results or {}).items()
                 if getattr(r, "ok", None) is None}
                or _uncovered_requirements(verdict.not_exercised,
                                           self._built.suite_dir))

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

    def _decide_requirements(self) -> dict:
        """Decide the frozen oracle set on the recording this run just wrote.

        `judge` answers per TESTPOINT; the debugger is asked to repair per
        REQUIREMENT. `decide_rtl` is the join, and it needs nothing new: every
        `{tp}.trace.json` is already written unconditionally by `Env.finish`,
        and the oracle set is already frozen on disk.

        Never raises. A missing recording, an oracle that will not import, a
        contract that did not load -- each of those costs the requirement
        surface and must not cost the run, because the testpoint-level verdict
        this reviewer returns is correct with or without it.
        """
        if not self._oracles:
            return {}
        try:
            from specflow.refmodel.rtl_trace import decide_rtl, load_traces
            traces = load_traces(Path(self._built.suite_dir) / "results")
        except Exception:  # noqa: BLE001
            logger.debug("no traces to decide requirements against", exc_info=True)
            return {}
        try:
            results = decide_rtl(self._oracles, traces, self._contract)
        except Exception:  # noqa: BLE001
            logger.debug("deciding the frozen oracles failed", exc_info=True)
            return {}
        # EACH TESTPOINT HAS ITS OWN WAVEFORM, so publish the map too. A single
        # `session.vcd_path` cannot be right for every requirement -- `run_suite`
        # writes `wave_{iteration}_{module}.vcd` per testpoint, one process each
        # -- and reading the wrong testpoint's waveform is worse than reading
        # none, because it looks like data. Same pairing the trace already gets.
        self.vcd_by_tp = self._waves_by_tp()
        # Paired with the trace it judged, because `explain` reads simulator
        # TIME out of it -- an `OracleResult.edge` is a row index, and feeding
        # an index to a filter over nanosecond timestamps collapses the VCD
        # window to the start of the run with no error anywhere.
        return {r.req_uid: (r, traces.get(r.tp_uid) or {}) for r in results}

    def _waves_by_tp(self) -> dict:
        """`{tp_uid: wave.vcd}` for whatever this run dumped.

        Empty when the suite ran with `trace=False`, which is a real state and
        not an error -- `explain` says so rather than showing an empty
        internals section as though the blocks had nothing to report.
        """
        out: dict = {}
        suite = Path(self._built.suite_dir)
        found: dict = {}
        for wave in suite.glob("wave_*_test_TP*.vcd"):
            _, it, mod = wave.stem.split("_", 2)        # wave_0_test_TP0007
            digits = mod.replace("test_TP", "")
            if not (digits.isdigit() and it.isdigit()):
                continue
            uid = f"TP-{digits}"
            # LATEST ITERATION WINS, compared as a NUMBER. Sorting the names as
            # strings puts "wave_10_" before "wave_2_", so a tenth trial's
            # waveform would silently lose to the second's -- and the agent
            # would be shown a waveform eight commits out of date while every
            # other field described the current design.
            if int(it) >= found.get(uid, -1):
                found[uid] = int(it)
                out[uid] = wave
        return out


def _frozen_oracles(run_dir: Path | str) -> list:
    """The frozen `RequirementOracle`s, or an empty list.

    Degrades rather than raises: with no oracle set the reviewer still returns
    its testpoint verdict, and only the per-requirement surface goes quiet --
    which is the state every run was in before this was wired.
    """
    try:
        from specflow.refmodel.oracles import RequirementOracle
        data = json.loads((Path(run_dir) / "specflow" / "oracles.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError):
        return []
    out = []
    for o in data.get("oracles") or []:
        try:
            out.append(RequirementOracle(
                req_uid=str(o["req_uid"]), clause=str(o.get("clause") or ""),
                source=str(o["source"]), tp_uids=list(o.get("tp_uids") or [])))
        except (KeyError, TypeError):
            continue
    return out


def _uncovered_requirements(not_exercised, suite_dir: Path) -> set[str]:
    """Requirements every one of whose testpoints decided nothing.

    `GateVerdict.not_exercised` is TESTPOINT-keyed -- `gate.py` builds it from
    `results`, which `run_suite` keys by tp_uid -- and `add_stimulus` needs
    requirement uids. The map is the testplan's own `covers`, so no inference is
    involved beyond the join.

    UNDER-APPROXIMATES ON PURPOSE. A requirement is listed only when EVERY
    testpoint covering it came back NOT_EXERCISED; one exercised testpoint takes
    it off the list even if others abstained. That is the safe direction: it can
    refuse to stage a requirement that would have benefited, and it can never
    let the agent stage one that already has evidence -- which is the failure
    that would turn this tool into a way of burying a verdict under new
    testpoints.

    The exact answer needs per-REQUIREMENT verdicts to reach this arm at all,
    which is the same gap that leaves the debugger unable to name the
    requirement behind a failing check.
    """
    idle = set(not_exercised or ())
    if not idle:
        return set()
    try:
        manifest = json.loads(
            (Path(suite_dir) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    covers: dict[str, list[str]] = {}
    for entry in manifest.get("testpoints") or manifest.get("elements") or []:
        # A manifest may list testpoints as bare uid STRINGS, which carry no
        # `covers` and so cannot be joined at all. `entry.get` raised
        # AttributeError on those -- out of `review()`, out of `commit()` -- so
        # the fallback was not merely useless on that shape but fatal.
        if not isinstance(entry, dict):
            continue
        tp = entry.get("tp_uid") or entry.get("uid") or ""
        for c in entry.get("covers") or []:
            covers.setdefault(str(c).split("@")[0], []).append(tp)
    return {req for req, tps in covers.items() if tps and all(t in idle for t in tps)}


class SpecflowStimulusStager:
    """The stimulus route for the RTL debug loop, on the specflow backend.

    `refmodel_editor` has had `add_stimulus` since #80 and the RTL editor never
    did, so on this arm an UNCOVERED requirement was a finding the agent was
    shown and could not act on. That is not a cosmetic gap: whether a check is
    covered depends on WHAT THE DESIGN DOES -- an oracle abstains when its
    activation never occurred -- so an uncovered requirement can be the symptom
    of the very bug being hunted. #98 is the case on record: a two-tick command
    handshake meant brief `cmd` pulses never left IDLE and everything downstream
    abstained. Dropping those would have locked the bug in.

    THE DIFFERENCE FROM THE REFMODEL ARM, and the reason this is a separate
    class rather than a reuse: there, `session.add_stimulus` appends and calls
    `refresh()`, which re-decides the oracles in Python. Here the new testpoint
    has to be SIMULATED, so the suite is re-rendered into the same `suite_dir`
    the reviewer already runs -- and the next `commit()` picks it up with no
    other wiring.

    APPEND-ONLY, like its counterpart. Nothing existing is edited, so a grown
    evidence set can only move a verdict toward worse: `_worst` ranks failing
    above anything a new testpoint could contribute. That is what makes the tool
    safe to hand an agent whose score falls with the failing count.
    """

    def __init__(self, *, run_dir: Path, contract: dict, bins,
                 suite_dir: Path, model_port, budget: int = 6):
        self.run_dir = Path(run_dir)
        self.contract = contract
        self.bins = bins or []
        #: NOT a constructor argument, and that is the point: re-rendering with
        #: an empty check list would silently strip every check from the suite,
        #: which reads downstream as a design that suddenly passes everything.
        #: They are loaded from the coverage model the original render used, and
        #: a missing one REFUSES the stage rather than rendering without them.
        self._checks: list[dict] | None = None
        self.suite_dir = Path(suite_dir)
        self.port = model_port
        self.budget = int(budget)
        self.added: list[str] = []
        #: Requirement uids the last suite run decided NOTHING about. Set by the
        #: reviewer after each run; empty means the gate cannot be applied, and
        #: an empty gate is a REFUSAL rather than a waiver -- inventing a target
        #: is exactly what the refmodel arm's "must already be unexercised" rule
        #: exists to prevent.
        self.uncovered: set[str] = set()

    def add_stimulus(self, req_uid: str, what_the_scenario_needs: str) -> dict:
        from specflow.ids import PREFIX_TESTPLAN, mint, next_index
        from specflow.tb.render import render_suite
        from specflow.testcase_agent import stimulus_for_scenario

        if len(self.added) >= self.budget:
            return {"error": f"stimulus budget spent ({self.budget} testpoints "
                             f"added); the remaining uncovered requirements need "
                             f"a testplan fix, not more steps"}
        if req_uid not in self.uncovered:
            return {"error": f"{req_uid} is not currently uncovered. This tool "
                             f"only stages a scenario nothing reaches -- a "
                             f"FAILING requirement is evidence about the design "
                             f"and adding stimulus cannot discharge it."}

        if self._checks is None:
            cov = self.run_dir / "specflow/coverage_model.json"
            try:
                self._checks = json.loads(cov.read_text(encoding="utf-8")).get("checks") or []
            except (OSError, ValueError, AttributeError):
                return {"error": (
                    "the coverage model could not be read, so re-rendering the "
                    "suite would drop every check from it. Refusing rather than "
                    "producing a suite that passes because it stopped looking.")}

        tp_path = self.run_dir / "specflow/testplan.json"
        st_path = self.run_dir / "specflow/stimulus.json"
        req_path = self.run_dir / "specflow/requirements.json"
        try:
            testplan = json.loads(tp_path.read_text(encoding="utf-8"))
            testplan = testplan.get("elements") or testplan.get("testplan") or testplan
            stim = json.loads(st_path.read_text(encoding="utf-8"))
            reqs = json.loads(req_path.read_text(encoding="utf-8"))["requirements"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {"error": f"could not read the testplan artifacts: {exc!r}"}

        req = next((r for r in reqs if r.get("uid") == req_uid), {})
        try:
            steps = stimulus_for_scenario(
                requirement=req, what_the_scenario_needs=what_the_scenario_needs,
                contract=self.contract, port=self.port,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"stimulus generation failed: {exc!r}"}
        if not steps:
            return {"error": "the generator produced no steps"}

        by_tp = {t["tp_uid"]: t["stimulus_steps"] for t in stim.get("testpoints", [])}

        # RENDER THE SUITE THAT EXISTS, PLUS ONE -- not every testpoint the
        # stimulus file happens to hold.
        #
        # `stimulus.json` and `testplan.json` are the FULL artifacts; a run may
        # deliberately be built over a subset of them. This re-rendered from the
        # full set, so adding one testpoint silently restored every testpoint
        # the run had excluded.
        #
        # MEASURED on run 10: three `add_stimulus` calls took the suite from 224
        # testpoints to 334 -- the 331 in the stimulus file plus the 3 added. The
        # run's pass and coverage counts were therefore taken on a LARGER suite
        # than its own baseline, than run 8, and than the golden reference, and
        # no comparison across that boundary means anything. A tool that adds
        # one scenario must add one scenario.
        try:
            live = json.loads((Path(self.suite_dir) / "manifest.json").read_text(
                encoding="utf-8")).get("testpoints") or []
        except (OSError, ValueError):
            live = []
        live_uids = {str(t.get("tp_uid") or t.get("uid") or "") if isinstance(t, dict)
                     else str(t) for t in live}
        if live_uids:
            by_tp = {k: v for k, v in by_tp.items() if k in live_uids}
            testplan = [t for t in testplan
                        if str(t.get("tp_uid") or t.get("uid") or "") in live_uids]
        # Byte-identical to something already present buys nothing and costs a
        # simulator process on every future run, not just this one.
        key = json.dumps(steps, sort_keys=True)
        if any(json.dumps(v, sort_keys=True) == key for v in by_tp.values()):
            return {"error": "identical to stimulus already in the suite"}

        uid = mint(PREFIX_TESTPLAN, next_index(
            [str(t.get("tp_uid") or t.get("uid") or "") for t in testplan]
            + list(by_tp), PREFIX_TESTPLAN))
        testplan.append({
            "uid": uid, "tp_uid": uid, "covers": [f"{req_uid}@1"],
            "stimulus": what_the_scenario_needs, "expected_response": "",
            "dimension": "D2_control_flow",
        })
        by_tp[uid] = steps
        stim.setdefault("testpoints", []).append(
            {"tp_uid": uid, "stimulus_steps": steps})

        try:
            render_suite(testplan=testplan, bins=self.bins, checks=self._checks,
                         contract=self.contract, out_dir=self.suite_dir,
                         stimulus_by_tp=by_tp)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"the suite would not re-render with it: {exc!r}"}

        # ONLY after the render succeeded. A testplan on disk naming a testpoint
        # the suite does not contain is the failure mode #126 already cost a run
        # to: frozen artifacts pointing at testpoints that do not exist, whose
        # checks then abstain and discard every call that produced them.
        tp_path.write_text(json.dumps({"elements": testplan}, indent=2) + "\n",
                           encoding="utf-8")
        st_path.write_text(json.dumps(stim, indent=2) + "\n", encoding="utf-8")
        self.added.append(uid)
        return {"added": uid, "steps": len(steps), "covers": req_uid,
                "budget_left": self.budget - len(self.added),
                "now": ("the suite has been re-rendered; the next commit() runs "
                        "this testpoint and will say whether it covered "
                        f"{req_uid}")}


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
    max_repairs: int = 5,
    refmodel_max_repairs: int | None = None,
    #: Edit attempts per debug turn. Zero disables the agentic path entirely and
    #: the stage falls back to prose-driven regeneration, which is what every
    #: run did before this existed.
    refmodel_debug_attempts: int = 30,
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
    #: Adequacy feedback rounds. 1 means: debug, mutate the shipped model, send
    #: the oracles that caught nothing back to be strengthened, then debug ONCE
    #: MORE against the strengthened set -- two reference models in total.
    #:
    #: Shipped at 1 rather than 0 because the alternative is measuring a set
    #: and acting on none of it: n-i2c reported 46 CONFORMS of which only 6
    #: could be shown to discriminate, and nothing was done about the other 40.
    #:
    #: Safe to default only now the illegal-mutant filter exists
    #: (`adequacy._unbuildable`). Before it, 19 of n-i2c's 20 inadequacy
    #: findings cited the same mutant putting the literal 2 on a one-bit port,
    #: and a strengthening round would have rewritten 20 oracles to catch a
    #: value no hardware can produce -- returning them over-strict, which the
    #: over-strictness gate then rejects. Enabling this before that filter would
    #: have realised the oscillation risk on the first round.
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

    # THE STIMULUS ROUTE for the RTL debug loop. Without it an uncovered
    # requirement reaches the debugger as a finding it cannot act on -- and
    # since coverage depends on what the design DOES, an uncovered requirement
    # can be the symptom of the very bug being hunted (#98).
    contract = json.loads(contract_json) if contract_json else {}
    stager = SpecflowStimulusStager(
        run_dir=output_dir_per_run,
        contract=contract,
        bins=built.bins,
        suite_dir=built.suite_dir, model_port=model_port,
    )
    reviewer = SpecflowReviewer(
        built=built, hdl_toplevel=top, output_dir=output_dir_per_run,
        extra_sources=extra_sources, include_dirs=include_dirs,
        stager=stager,
        # The frozen checks, so every run also answers PER REQUIREMENT and the
        # editor's requirement surface has something to read.
        oracles=_frozen_oracles(output_dir_per_run), contract=contract,
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

        # THE REQUIREMENT VIEW. Assembled from artifacts that all already
        # existed and were never joined -- requirements.json for the text,
        # normalized.json for the activation and expectation, oracles.json for
        # the frozen check, the contract for the ports it reads. Without it the
        # debugger sees check ids and is asked to name the requirement behind
        # them, which is what B21 measured the cost of.
        from .explain import load_requirement_views
        views = load_requirement_views(output_dir_per_run, contract)
        editor = RTLEditor(cfg, sim_reviewer=reviewer, max_trials=remaining,
                           stimulus_stager=stager, requirements=views,
                           contract=contract)
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
