"""An agentic debug turn over a reference model.

The structural mirror of `RTLEditor`, one level up: instead of repairing RTL
against a testbench, this repairs the REFERENCE MODEL against the mini-oracles
the judge wrote for each requirement.

Why it exists. The judge is a good detector -- an inert model it once certified
77/77 met is now rejected on 93% of requirements -- and a poor instructor. Its
findings reach the generator as prose, one `Issue.message` per requirement, and
a round carrying 72 of them in a 185 kB brief produces a REWRITE rather than a
repair: the liveness trace 3 -> 1 -> 4 across rounds is a model being
regenerated, not edited, and round 0's work is discarded every time.

So the judge stops being the repair channel and becomes the acceptance test.
Its oracles are a failing test suite; this drives an agent at them with tools
until they pass. Attempts are pure Python -- `specflow/refmodel/base.py` imports
nothing from cocotb -- so an attempt costs milliseconds against a judge turn's
~77 model calls, and "a few attempts per turn" is genuinely cheap.

All the decidable behaviour lives in `specflow.refmodel.session.DebugSession`,
which needs no agent and is tested offline. This file is the tools and the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import ToolResponse

from specflow.refmodel.session import DebugSession

from .agents import GuidingToolkit, SafeReActAgent, clear_memory_safely
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You repair a Python REFERENCE MODEL of a hardware design so that it satisfies a
set of requirement oracles.

The reference model is the thing a testbench compares a real design against. If
it is wrong, correct designs get marked broken and broken ones get accepted, so
it is worth more than the design.

Each oracle decides ONE requirement mechanically: it replays the model over that
requirement's own stimulus and returns met / not met with the edge it decided
on. They were written by a judge that read the specification, and each has
already been screened -- it agrees with its author's verdict, it fires when the
model is mutated, and where a known-good model exists it accepts that model. You
CANNOT edit them. Satisfy them by fixing the model.

Work like this:

  1. `list_oracles()` to see what is failing.
  2. `explain(req_uid)` on one of them. This gives you the requirement, the
     specification text it was drawn from, the judge's reasoning, the oracle's
     own source, the stimulus, and which methods claim to implement it.
  3. `run_oracle(req_uid)` to see the model actually running that scenario, edge
     by edge. This is where a wrong clock generation becomes visible -- an
     output diverges many edges after the cause, so read the internals leading
     up to the failing edge, not just the failing edge. Its `activity` field
     describes the WHOLE replay while the trace shows one window: use
     `first_change` to jump to where an output actually moves, and treat
     `inert: true` as "this testpoint cannot be satisfied by editing".

A status of NOT EXERCISED is not a defect in the model, and no edit will
discharge one -- the oracle never saw the situation its clause is about. It is
not something to leave alone either. Call `add_stimulus(req_uid, "...")` and
describe what has to happen; the harness generates the vectors, gates them and
adds a new testpoint. Then the oracle either decides -- possibly against the
model, which is a real finding you can then fix -- or reports that your scenario
still did not stage it, which tells you the description was not concrete enough.

ONE ROUTE PER TURN, and the harness picks it, not you. A turn with anything
failing is a MODEL turn: `add_stimulus` refuses, because a failing oracle is
evidence about the model that adding stimulus cannot discharge. A turn with
nothing failing is a STIMULUS turn: `replace_method` refuses, because there is
no finding to act on and an edit made then could not be attributed to anything.
The prompt below tells you which turn this is. It is not a suggestion you can
argue with -- the tool returns an error.

Some findings come back with `checked: false` and NO EXECUTABLE CHECK. The
judge reached a verdict but no oracle survived screening for it, so nothing can
decide it mechanically. The verdict is unchanged and it is still worth reading
-- `explain` gives the reasoning -- but it is one reader's opinion of the source
and was never confirmed. Treat it as a lead: check whether the reasoning holds
against what the model actually does, and if it does not, LEAVE THE MODEL ALONE
and say so. Editing to satisfy an unverified opinion is how a correct model
gets broken. Fix the checked failures first; they are the ones with evidence.
  4. `read_model(method)` on the method that should be doing the work.
  5. `replace_method(name, code)` with the whole corrected `def`.

Then check what happened and continue.

Some things that will save you attempts:

  - ONE FIX AT A TIME. An edit that changes several things cannot be attributed
    when the failing count moves, and cannot be undone selectively.
  - The failing count going UP means the edit was wrong. Say so and put it back.
  - `mask(value, width)` exists on the base class. An unbounded Python integer
    where hardware would wrap is the single most common defect in these models.
  - If an oracle looks WRONG to you -- it demands something the specification
    does not say -- say so plainly in your final message rather than contorting
    the model to satisfy it. That is a real outcome and a useful one.

**Nothing failing is not done.** An oracle reports NOT EXERCISED when its
scenario never occurred, and that is not a passing requirement -- it is an
unverified one, which is worse than a failing one because nothing is even
claiming to check it. On a STIMULUS turn there is nothing failing BY
CONSTRUCTION, so treating that as finished would end every stimulus turn before
it began.

You are done when every oracle CONFORMS, or when the tools stop giving you
moves: `replace_method` closed and `add_stimulus` refusing because the budget is
spent. Until then keep going. Finish with a plain sentence saying what you
changed and why, and if oracles are still short of conforming, say which and
what stopped you.
"""


def _text(payload: Any) -> ToolResponse:
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return ToolResponse(content=[{"type": "text", "text": body}])


def _no_session() -> ToolResponse:
    return _text("ERROR: no active debug session.")


class RefModelEditor:
    """Drive one debug turn against a frozen oracle set."""

    def __init__(
        self,
        cfg: OpenAIConfig,
        *,
        max_attempts: int = 6,
        stall_rounds: int = 2,
    ):
        #: Edit actions, not conversation turns. An attempt is one
        #: `replace_method`; reading and replaying are free and should be.
        self.max_attempts = max(1, int(max_attempts))
        #: Consecutive attempts with no reduction in the failing count before
        #: giving up. Deliberately small: a turn that is not converging should
        #: hand back so the next JUDGE turn can re-read the model, which is a
        #: better use of budget than more attempts against a stale oracle set.
        self._stall_rounds = max(1, int(stall_rounds))
        self._session: DebugSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_oracles)
        toolkit.register_tool_function(self._tool_explain)
        toolkit.register_tool_function(self._tool_run_oracle)
        toolkit.register_tool_function(self._tool_read_model)
        toolkit.register_tool_function(self._tool_replace_method)
        toolkit.register_tool_function(self._tool_run_all)
        toolkit.register_tool_function(self._tool_add_stimulus)

        self._agent = SafeReActAgent(
            name="RefModelDebugger",
            sys_prompt=SYSTEM_PROMPT,
            model=make_openai_model(cfg),
            formatter=make_formatter(cfg.model),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def reset(self) -> None:
        clear_memory_safely(self._agent)
        self._session = None

    # --------------------------------------------------------------- tools

    async def _tool_list_oracles(self) -> ToolResponse:
        """List every requirement oracle and whether the model satisfies it.

        Returns req_uid, the clause it decides, the testpoints it replays, and
        the current status with the edge it decided on.
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(self._session.list_oracles))

    async def _tool_explain(self, req_uid: str) -> ToolResponse:
        """Everything known about one requirement, in one call.

        The requirement text, the specification passages it was drawn from, the
        judge's reasoning, the oracle's own source, the concrete stimulus, and
        the methods claimed to implement it.

        Args:
            req_uid: the requirement, e.g. "REQ-0031".
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(self._session.explain, req_uid))

    async def _tool_run_oracle(
        self, req_uid: str, from_edge: int = 0, rows: int = 60
    ) -> ToolResponse:
        """Replay one requirement's scenario against the model, edge by edge.

        Use this to localise. An output usually diverges many edges after the
        cause, so read the edges leading up to the failure.

        READ `activity` BEFORE THE TRACE. It covers the whole replay, not the
        window: `first_change` gives the edge each output first moves on, so
        page straight there instead of reading from edge 0. If `inert` is true
        the testpoint never moves the model at all, and no edit can make its
        oracle pass -- say so and move to another requirement rather than
        spending attempts on it.

        Args:
            req_uid: the requirement, e.g. "REQ-0031".
            from_edge: first edge to show; page forward when the trace is long.
            rows: how many edges to show.
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(
            self._session.run_oracle, req_uid, from_edge, rows))

    async def _tool_add_stimulus(
        self, req_uid: str, what_the_scenario_needs: str
    ) -> ToolResponse:
        """Stage a scenario the current stimulus never reaches.

        ONLY for a requirement showing NOT EXERCISED. That status means the
        oracle never saw the situation its clause is about, so the model is not
        being accused of anything and no edit can discharge it -- the testplan
        is what is missing. This is how you say so.

        You describe WHAT MUST HAPPEN, in prose, the way a test plan does:
        "issue a WRITE command with ena=1 and hold it until cmd_ack", "assert
        nReset low for several edges", "drive sda_i low while the controller has
        released SDA". You do NOT write vectors -- the harness generates them,
        gates them, and adds a NEW testpoint. Nothing existing is changed, so
        this can only add evidence, never remove any.

        The new testpoint is also attached to every OTHER requirement whose
        activation it happens to stage, so one good scenario can discharge
        several. Check the result's `attached_to`.

        If the result says the requirement is still NOT EXERCISED, the scenario
        you described did not stage it -- describe it more concretely rather
        than repeating. The budget is small and shared across the whole turn.

        Args:
            req_uid: the requirement, e.g. "REQ-0031". Must be NOT EXERCISED.
            what_the_scenario_needs: what has to happen, concretely, in prose.
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(
            self._session.add_stimulus, req_uid, what_the_scenario_needs))

    async def _tool_read_model(self, method: str = "") -> ToolResponse:
        """Read the reference model, line-numbered.

        Args:
            method: one method name, or empty for the whole model.
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(
            self._session.read_model, method or None))

    async def _tool_replace_method(self, method: str, new_code: str) -> ToolResponse:
        """Replace one method of the model with a corrected version.

        Give the WHOLE `def`, including the signature. The edit is rejected
        without being scored if it does not parse, renames the method, or leaves
        a declared output unwritten -- those are defects in the edit rather than
        evidence about the model.

        Args:
            method: the method to replace, e.g. "_advance_fsm".
            new_code: the complete replacement `def`.
        """
        if self._session is None:
            return _no_session()
        result = await asyncio.to_thread(
            self._session.replace_method, method, new_code)
        return _text(result)

    async def _tool_run_all(self) -> ToolResponse:
        """Re-decide every oracle, and report whether the outputs move at all."""
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(self._session.run_all))

    # ---------------------------------------------------------------- loop

    async def debug(self, session: DebugSession) -> tuple[str, int, str]:
        """Run one debug turn. Returns `(best_source, attempts, note)`.

        The returned source is the session's BEST, never merely its last: a turn
        that wandered downhill hands back where it was highest. That is the
        direct answer to a repair round that regenerated an inert model and then
        built the next round on it.
        """
        self._session = session
        self.reset()
        self._session = session

        failing = [r.req_uid for r in session.failing()]
        if not failing:
            return session.best(), 0, "nothing was failing when the turn began"

        note = ""
        best_seen = len(failing)
        stalled = 0
        try:
            response = await self._agent(Msg("user", _opening(session), role="user"))
            note = str(getattr(response, "content", "") or "")
            for _ in range(self.max_attempts):
                if session.all_met():
                    break
                edits = len(session.history)
                if edits >= self.max_attempts:
                    break
                if stalled >= self._stall_rounds:
                    break
                response = await self._agent(
                    Msg("user", _continue(session), role="user"))
                note = str(getattr(response, "content", "") or "")
                current = len(session.failing())
                if current < best_seen:
                    best_seen = current
                    stalled = 0
                elif len(session.history) > edits:
                    # Only an actual ATTEMPT counts toward stalling. A turn spent
                    # reading and replaying is the agent working, and cutting it
                    # off there is how a debugger gets stopped before its first
                    # edit -- observed live in tb_editor.
                    stalled += 1
        except Exception as exc:  # noqa: BLE001 -- a turn must not kill the stage
            log.warning("reference-model debug turn failed: %r", exc)
            note = f"the debug turn ended early: {exc!r}"

        return session.best(), len(session.history), note


def _opening(session: DebugSession) -> str:
    rows = session.list_oracles()
    failing = [r for r in rows if r["status"] == "NOT MET"]
    lines = [
        f"The reference model fails {len(failing)} of {len(rows)} requirement "
        f"oracles.",
        "",
        "Failing:",
    ]
    for r in failing[:40]:
        where = f" (decided at edge {r['edge']})" if r["edge"] is not None else ""
        lines.append(f"  {r['req_uid']}: {r['clause']}{where}")
        if r["detail"]:
            lines.append(f"      observed: {r['detail']}")
    if len(failing) > 40:
        lines.append(f"  ... and {len(failing) - 40} more; list_oracles() has all.")
    state = session.run_all()
    if state["distinct_output_states"] == 1:
        lines += [
            "",
            "The model's outputs NEVER MOVE across the whole stimulus. That is "
            "the first thing to fix: a model with constant outputs satisfies "
            "nothing and cannot tell any design from any other.",
        ]
    lines += ["",
              f"This is a {session.route.upper()} turn: "
              + ("edit the model; `add_stimulus` is closed."
                 if session.route == "model" else
                 "nothing is failing, so `replace_method` is closed. Stage the "
                 "scenarios the unexercised oracles are waiting for."),
              "Start with `explain` on one of them."]
    return "\n".join(lines)


def _continue(session: DebugSession) -> str:
    """Restate where things stand, rather than saying "keep going".

    Same reasoning as `rtl_editor._render_continue_debug_prompt`: the agent
    needs the outcome of its last action and the current baseline, not an
    exhortation.
    """
    failing = session.failing()
    last = session.history[-1] if session.history else None
    lines = []
    if last is None:
        lines.append("No edit has been made yet.")
    elif last.accepted:
        lines.append(
            f"Your edit to `{last.method}` was accepted: failing went "
            f"{last.failing_before} -> {last.failing_after}."
        )
        if last.failing_after > last.failing_before:
            lines.append(
                "That made things WORSE. Consider putting it back before "
                "trying something else."
            )
    else:
        lines.append(f"Your edit to `{last.method}` was REJECTED: {last.reason}")
    lines += ["", f"This is a {session.route.upper()} turn.",
              f"{len(failing)} oracle(s) still failing:"]
    for r in failing[:20]:
        lines.append(f"  {r.req_uid}: {r.detail or '(no detail)'}")
    return "\n".join(lines)


class SyncRefModelDebugger:
    """The `RefModelDebugger` Protocol `specflow` expects, over the async editor.

    `run_specflow_node` is async and calls `build_artifacts` synchronously, so
    the stage runs INSIDE a live event loop. `asyncio.run` raises there, so the
    turn goes to a worker thread with a loop of its own. This is the only reason
    the class exists: specflow stays synchronous and imports no AgentScope, and
    the editor stays async because AgentScope is.
    """

    def __init__(self, cfg: OpenAIConfig, *, max_attempts: int = 6):
        self._cfg = cfg
        self._max_attempts = max_attempts

    def debug(self, session: DebugSession) -> tuple[str, int, str]:
        import concurrent.futures

        def _run() -> tuple[str, int, str]:
            # A fresh editor per turn: the oracle set it was briefed on is gone,
            # and carrying that conversation into the next turn would have the
            # agent reasoning about findings that no longer hold.
            editor = RefModelEditor(self._cfg, max_attempts=self._max_attempts)
            return asyncio.run(editor.debug(session))

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_run).result()
        except Exception as exc:  # noqa: BLE001 -- a turn must not kill the stage
            log.warning("reference-model debug turn could not run: %r", exc)
            return session.best(), len(session.history), f"debug unavailable: {exc!r}"
