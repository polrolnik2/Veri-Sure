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

from specflow.refmodel.session import MODEL, DebugSession

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

  1. `_tool_list_oracles()` to see what is failing.
  2. `_tool_explain(req_uid)` on one of them. This gives you the requirement, the
     specification text it was drawn from, the judge's reasoning, the oracle's
     own source, the stimulus, and which methods claim to implement it.
  3. `_tool_run_oracle(req_uid)` to see the model actually running that scenario, edge
     by edge. This is where a wrong clock generation becomes visible -- an
     output diverges many edges after the cause, so read the internals leading
     up to the failing edge, not just the failing edge. Its `activity` field
     describes the WHOLE replay while the trace shows one window: use
     `first_change` to jump to where an output actually moves, and treat
     `inert: true` as "this testpoint cannot be satisfied by editing".

A status of NOT EXERCISED is not a defect in the model, and no edit will
discharge one -- the oracle never saw the situation its clause is about. It is
not something to leave alone either. Call `_tool_add_stimulus(req_uid, "...")` and
describe what has to happen; the harness generates the vectors, gates them and
adds a new testpoint. Then the oracle either decides -- possibly against the
model, which is a real finding you can then fix -- or reports that your scenario
still did not stage it, which tells you the description was not concrete enough.

THE TWO TOOLS ARE NOT SYMMETRIC, and the difference is worth understanding.

`_tool_add_stimulus` is ALWAYS available. Staging a scenario only ever ADDS evidence
-- nothing existing is edited -- so it cannot make a finding disappear, and a
requirement that gains a testpoint can only move toward a worse verdict, never
a better one. Do failing oracles FIRST when there are any, because a VIOLATES
is evidence you already have and costs no generation to act on. That is an
order to work in, not a door that is locked.

`_tool_replace_method` refuses on a turn with nothing failing, and that one IS a
locked door. With no oracle accusing the model, the only thing an edit can
achieve is to make some unexercised oracle's activation start occurring -- which
is editing the design so a check fires, rather than staging the scenario the
check is about. The prompt below tells you which turn this is.

Some findings come back with `checked: false` and NO EXECUTABLE CHECK. The
judge reached a verdict but no oracle survived screening for it, so nothing can
decide it mechanically. The verdict is unchanged and it is still worth reading
-- `_tool_explain` gives the reasoning -- but it is one reader's opinion of the source
and was never confirmed. Treat it as a lead: check whether the reasoning holds
against what the model actually does, and if it does not, LEAVE THE MODEL ALONE
and say so. Editing to satisfy an unverified opinion is how a correct model
gets broken. Fix the checked failures first; they are the ones with evidence.
  4. `_tool_read_model(method)` on the method that should be doing the work.
  5. `_tool_replace_method(name, code)` with the whole corrected `def`.

Then check what happened and continue.

Some things that will save you attempts:

  - ONE FIX AT A TIME. An edit that changes several things cannot be attributed
    when the failing count moves, and cannot be undone selectively.
  - The count of requirements still to satisfy going UP means the edit was
    wrong. Say so and put it back. That count includes the UNEXERCISED ones, so
    an edit that makes a failing requirement stop being exercised does not
    improve it -- a check that no longer fires has not been satisfied, it has
    been silenced, and the requirement is less verified than when it failed.
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
moves: nothing failing for `_tool_replace_method` to act on AND the `_tool_add_stimulus`
budget spent. Until then keep going. Finish with a plain sentence saying what you
changed and why, and if oracles are still short of conforming, say which and
what stopped you.
"""


#: Backstop only. Every tool below answers narrowly by construction -- this
#: catches the case where one does not, rather than being how size is managed.
#: `rtl_editor._clip_text` is the same idea and the same shape.
TOOL_MAX_CHARS = 24_000


def _clip(body: str, *, max_chars: int = TOOL_MAX_CHARS) -> str:
    """Head+tail with the cut declared.

    Declared because "a truncated list that does not say it was truncated reads
    as the whole population" (`rtl_editor.py:236-243`) -- a silent clip through
    a trace would have the agent reason about a scenario that does not end where
    it appears to.
    """
    if len(body) <= max_chars:
        return body
    half = max_chars // 2
    cut = len(body) - max_chars
    return (f"{body[:half]}\n"
            f"...<{cut} characters cut from the middle of this response; ask a "
            f"narrower question to see them>...\n{body[-half:]}")


def _text(payload: Any) -> ToolResponse:
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return ToolResponse(content=[{"type": "text", "text": _clip(body)}])


def _no_session() -> ToolResponse:
    return _text("ERROR: no active debug session.")


class RefModelEditor:
    """Drive one debug turn against a frozen oracle set."""

    def __init__(
        self,
        cfg: OpenAIConfig,
        *,
        max_attempts: int = 30,
    ):
        #: Edit actions, not conversation turns, and NOT model calls. An attempt
        #: is one `_tool_replace_method`; reading and replaying are free and should be.
        #:
        #: Was 6, which is a fifth of `RTLEditor`'s 30 (`rtl_editor.py:1031`) and
        #: under half of `TBEditor`'s 15 (`tb_editor.py:1305`) -- this loop had
        #: been running at a fraction of its siblings' budget for no stated
        #: reason. It went to 15, TBEditor's default, and now to 30, which is
        #: RTLEditor's: this loop repairs one model against every requirement's
        #: check at once, which is the harder of the two jobs, and a2-i2c's turn
        #: 3 was IDLE at 15 with 24 oracles still short of CONFORMS -- the turn
        #: had stopped finding moves, not run out of them.
        #:
        #: What this does NOT cap is model calls. Each `_agent(...)` below is a
        #: full ReAct sub-loop of `max_iters=10`, so a turn is up to
        #: `max_attempts * 10` calls sharing one context. Anything sized against
        #: this number -- a memory window, a stall count -- is sized against the
        #: wrong unit; `tb_editor.py:1310-1329` records a window of 6 collapsing
        #: inside a single trial for exactly this reason.
        self.max_attempts = max(1, int(max_attempts))
        self._session: DebugSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_oracles)
        toolkit.register_tool_function(self._tool_explain)
        toolkit.register_tool_function(self._tool_run_oracle)
        toolkit.register_tool_function(self._tool_read_model)
        toolkit.register_tool_function(self._tool_replace_method)
        toolkit.register_tool_function(self._tool_run_all)
        toolkit.register_tool_function(self._tool_add_stimulus)
        toolkit.register_tool_function(self._tool_revert_to_best)

        # Held so the turn's token usage can be read back. The wrapper counts
        # it either way; without a reference nothing ever asks, and this loop's
        # spend then never appears in any ledger -- which is exactly what
        # happened: `get_model_usage` exists and only the verilog-eval harness
        # calls it, so every debug turn on the specflow path was invisible.
        # One key for this agent, because one agent is one shared prefix:
        # the system prompt and the tool schema are identical on every
        # call of every turn of every run, and they are what caches.
        self._model = make_openai_model(cfg, cache_key="refmodel-debug")
        self._agent = SafeReActAgent(
            name="RefModelDebugger",
            sys_prompt=SYSTEM_PROMPT,
            model=self._model,
            formatter=make_formatter(cfg.model),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def reset(self) -> None:
        clear_memory_safely(self._agent)
        self._session = None

    # ------------------------------------------------------- memory carry
    #
    # The turn loop builds a fresh editor per turn -- it has to, because each
    # turn runs under its own `asyncio.run`, and an httpx client bound to a
    # closed loop is not reusable. So the CONVERSATION is carried instead of
    # the editor: same effect on context, none of the cross-loop hazard.

    def snapshot_memory(self) -> list:
        """The turn's conversation, to seed the next turn with.

        Never raises. Losing the carry costs the next turn its context; letting
        the loss propagate would cost the whole turn, including the edits it
        already made and the source it is about to hand back.
        """
        try:
            mem = getattr(self._agent, "memory", None)
            return list(getattr(mem, "content", None) or [])
        except Exception:  # noqa: BLE001 -- see the docstring
            log.warning("could not snapshot the turn's conversation")
            return []

    def restore_memory(self, msgs: list) -> None:
        """Seed this turn with the previous turn's conversation.

        No window, no summarisation. `RTLEditor` and `TBEditor` both default
        `memory_window=0` -- "no truncation, ever" -- having measured that
        cutting the middle breaks prefix caching (repricing the remainder as
        fresh tokens) and, separately, loses the reasoning behind a design the
        agent would otherwise have kept. What keeps this bounded is that the
        tools answer narrowly, not that the history is trimmed.
        """
        if not msgs:
            return
        try:
            mem = getattr(self._agent, "memory", None)
            if mem is None:
                return
            mem.content = list(msgs)
        except Exception:  # noqa: BLE001 -- a carry failure must not kill the turn
            log.warning("could not carry the previous turn's conversation")

    # --------------------------------------------------------------- tools

    async def _tool_list_oracles(self) -> ToolResponse:
        """Detail for the oracles THIS turn can act on; a line for the rest.

        `acting_on` carries the full record -- req_uid, the clause it decides,
        the testpoints it replays, the current status and the edge it decided on
        -- for the failing ones on a model turn, the unexercised ones on a
        stimulus turn. `methods_to_look_at_first` names what claims to implement
        them, which is where to read.

        `not_acting_on` names EVERY other requirement under its status. Those
        are the ones an edit can break, so check it before you change a method
        that several requirements share. Read any of them in full by name with
        _tool_explain(req_uid) or _tool_run_oracle(req_uid).
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(self._session.board))

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
        self, req_uid: str, from_edge: int = -1, rows: int = -1
    ) -> ToolResponse:
        """Replay one requirement's scenario against the model, edge by edge.

        Called with just a req_uid it shows a small window CENTRED ON THE EDGE
        THE ORACLE DECIDED, with the deciding testpoint first -- that edge is
        the finding, and the neighbours are there to show the approach to it.
        Widen or move the window with `from_edge` and `rows` when the cause is
        further back; every response says how many edges it did not show.

        READ `activity` BEFORE THE TRACE. It covers the whole replay, not the
        window: `first_change` gives the edge each output first moves on. If
        `inert` is true the testpoint never moves the model at all, and no edit
        can make its oracle pass -- say so and move to another requirement
        rather than spending attempts on it.

        Args:
            req_uid: the requirement, e.g. "REQ-0031".
            from_edge: first edge to show; omit to centre on the deciding edge.
            rows: how many edges to show; omit for the default window.
        """
        if self._session is None:
            return _no_session()
        # -1 is "not given": the schema these tools are described by does not
        # carry optionality, so a sentinel is what reaches the session as None.
        start = None if from_edge is None or from_edge < 0 else int(from_edge)
        span = None if rows is None or rows < 0 else int(rows)
        return _text(await asyncio.to_thread(
            self._session.run_oracle, req_uid, start, span))

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

    def usage(self) -> tuple[int, int, int]:
        """`(input, cached, output)` tokens, cumulative, or `(0, 0, 0)`.

        Zero when the wrapper does not expose counters, never an estimate: a
        guessed number in a cost ledger is worse than a hole, because a hole
        is visibly a hole.

        `cached` is a SUBSET of `input`. It is here because this loop is where
        the input total is large and its meaning most uncertain -- a turn
        re-sends a growing conversation up to `max_attempts * 10` times, which
        is either the best case for prompt caching or the worst case for cost,
        and the two look identical without this number.
        """
        from .model import get_model_cached, get_model_usage

        model = getattr(self, "_model", None)
        got = get_model_usage(model)
        return got[0], get_model_cached(model), got[1]

    async def _tool_read_model(self, method: str = "") -> ToolResponse:
        """Read ONE method of the reference model, line-numbered.

        Called with no method it lists the method names and marks the ones
        claimed to implement a requirement this turn can act on. There is no
        whole-file form: read the methods the finding points at.

        Args:
            method: one method name, or empty to list them.
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

    async def _tool_revert_to_best(self) -> ToolResponse:
        """Undo back to the best state this turn has reached.

        Use it when an edit made things worse and you would rather start again
        from the last good model than keep patching on top of a bad one. It can
        only move the model to a state already scored no worse, so it is always
        safe; it reports what moved back.
        """
        if self._session is None:
            return _no_session()
        return _text(await asyncio.to_thread(self._session.revert_to_best))

    async def _tool_run_all(self) -> ToolResponse:
        """Re-decide every oracle: the census, WHAT MOVED, and liveness.

        Read `changed_since_you_last_looked` first -- it is the only thing this
        call tells you that the board does not. It names the requirements that
        changed status since your last look and which way they went, so an edit
        that fixed one thing and broke another is visible as both.

        It does NOT return traces or per-requirement detail. Use run_oracle for
        the trace behind one, list_oracles for its clause and detail.
        """
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

        THE CONVERSATION IS NOT CLEARED HERE. It used to be, and that was the
        single largest thing this loop did wrong.

        Clearing threw away the reasoning, not just the tokens. `TBEditor`
        records the same loss from the other direction, where it came from a
        memory window rather than a reset: "a genuinely correct multi-cycle
        datapath model, reaching the run's best fail_count, was abandoned one
        trial later and never rebuilt, registers left unused for the rest of the
        run, consistent with the model losing the reasoning for why it built
        that design" (`tb_editor.py:1310-1329`). Both siblings now default
        `memory_window=0` -- no truncation, ever -- and a per-turn reset is a
        window of zero applied at the worst possible moment.

        It also cost tokens rather than saving them: a stable prefix is cached
        at 0.1x, while cache writes cost the same as an uncached call, so
        discarding the prefix each turn repriced the whole context as fresh.

        The reason the reset was here has expired. It was that the oracle set
        the agent had been briefed on was "gone" by the next turn -- true when
        oracles were regenerated per turn, false since they were frozen:
        `compose.run_debug_turns` raises if the set drifts under the loop. The
        set is invariant across turns by construction, and `_opening` restates
        the current verdicts anyway, exactly as `_render_continue_debug_prompt`
        does for `RTLEditor`.
        """
        self._session = session

        # NOTHING FAILING IS NOT NOTHING TO DO, AND THIS GUARD IS WHERE THAT
        # READING SURVIVED LONGEST.
        #
        # It used to be `if not failing: return` -- and a turn with nothing
        # failing IS the stimulus turn, so the agent was never invoked on one.
        # `_tool_add_stimulus` could therefore only ever be called from a MODEL turn,
        # where it refuses by design. Five runs, zero testpoints staged, and
        # three earlier fixes -- the prompt's stop rule, `_debug_turns`
        # returning on an idle turn, and `_opening` showing an empty list --
        # could none of them matter, because control never reached them.
        #
        # Measured on q-i2c: turns 2 and 3 are ONE SECOND apart in the artifact
        # timestamps. No model call happens in a second; those turns returned
        # here.
        #
        # The question is whether the turn has ANY input, and it no longer
        # depends on the route: `_tool_add_stimulus` stopped refusing off-route, so a
        # turn with something unexercised and budget left has work whichever
        # way the brief leads.
        failing = [r.req_uid for r in session.failing()]
        stageable = [r.req_uid for r in session.undecided()]
        budget_left = session.stimulus_budget - len(session.added)
        if not failing and not (stageable and budget_left > 0):
            why = ("nothing is failing and nothing is unexercised" if not stageable
                   else f"{len(stageable)} oracle(s) are unexercised and the "
                        f"stimulus budget is spent")
            return session.best(), 0, why

        note = ""
        # NO STALL CUTOFF. A run of non-improving edits is not evidence that the
        # agent cannot solve the requirement; on a hard one it is the search.
        #
        # There used to be one, at two consecutive non-improving ATTEMPTS. Two
        # things made it worse than it looks. It counted individual edits, where
        # `RTLEditor`'s equivalent counts outer rounds of up to ten model calls
        # each (`rtl_editor.py:1451-1453`) -- the same number, an order of
        # magnitude apart in what it permits. And the turn used to clear its
        # memory on entry, so the two ruled-out hypotheses were discarded twice
        # over: the turn stopped, then the reasoning that produced them went
        # with it, and the next turn re-derived and re-stalled on the same two.
        #
        # `RTLEditor`'s own comment makes the argument against keeping it here:
        # "Crossing a valley takes several consecutive non-improving rounds by
        # definition, so a stall limit tuned for a monotone search will cut the
        # search off before it can get anywhere." This loop has no rollback
        # guard forcing monotonicity, so every valley crossing looked like a
        # stall.
        #
        # `session.best()` is what the turn returns, so a turn that wanders
        # downhill still hands back its high-water mark -- which is what made
        # the cutoff look free. It was not: it bought nothing and cost the
        # search.
        try:
            response = await self._agent(Msg("user", _opening(session), role="user"))
            note = str(getattr(response, "content", "") or "")
            for _ in range(self.max_attempts):
                # `all_met` asks only about FAILING oracles, so it is true at
                # entry on a turn whose work is staging stimulus and would end
                # that turn before its first attempt -- the same mistake as the
                # guard above, one loop deeper.
                if not session.undecided() and session.all_met():
                    break
                if (session.all_met()
                        and session.stimulus_budget <= len(session.added)):
                    break
                if len(session.history) >= self.max_attempts:
                    break
                response = await self._agent(
                    Msg("user", _continue(session), role="user"))
                note = str(getattr(response, "content", "") or "")
        except Exception as exc:  # noqa: BLE001 -- a turn must not kill the stage
            log.warning("reference-model debug turn failed: %r", exc)
            note = f"the debug turn ended early: {exc!r}"

        return session.best(), len(session.history), note


def _opening(session: DebugSession) -> str:
    """Every turn sees BOTH kinds of work, and neither tool is ever closed.

    It used to open with "the reference model fails N of M oracles" and list the
    failing ones. On a stimulus turn N is zero by construction, so the brief read
    "fails 0 of 70", listed nothing, and then said "stage the scenarios the
    unexercised oracles are waiting for -- start with `_tool_explain` on one of them",
    where "them" was the empty list above. That was fixed by branching the brief
    on the route, which fixed the symptom and kept the premise: that a turn is
    EITHER a model turn or a stimulus turn, and the other tool is shut.

    The premise is wrong, and `_tool_add_stimulus`'s own docstring already says why.
    Staging APPENDS -- nothing existing is edited, `_worst` ranks failing above
    everything a new testpoint can add, and `distance` counts unexercised
    alongside failing -- so a grown evidence set can only move a verdict toward
    WORSE. There is no edit here that turns a VIOLATES into a NOT_EXERCISED, so
    adding evidence cannot confound the edits it sits beside. The tool stopped
    refusing off-route for exactly that reason; this removes the last place that
    still told the agent it had.

    What survives is the PREFERENCE, which is real: a failing oracle is evidence
    that already exists and costs no model call to act on, while staging spends
    one to find out whether a scenario can be reached at all. So the route still
    says where to start. It no longer says what is forbidden.
    """
    rows = session.list_oracles()
    failing = [r for r in rows if r["status"] == "NOT MET"]
    waiting = [r for r in rows if r["status"] == "NOT EXERCISED"]
    budget_left = max(0, session.stimulus_budget - len(session.added))

    lines = [
        f"The reference model fails {len(failing)} of {len(rows)} requirement "
        f"oracles, and {len(waiting)} more have never seen the situation they "
        f"are about. An unexercised requirement is UNVERIFIED, which is worse "
        f"than a failing one because nothing is even claiming to check it."
    ]
    for title, group in (("Failing:", failing),
                         ("Waiting for a scenario:", waiting)):
        lines += ["", title]
        for r in group[:40]:
            where = (f" (decided at edge {r['edge']})"
                     if r["edge"] is not None else "")
            lines.append(f"  {r['req_uid']}: {r['clause']}{where}")
            if r["detail"]:
                lines.append(f"      observed: {r['detail']}")
        if len(group) > 40:
            lines.append(f"  ... and {len(group) - 40} more; "
                         f"_tool_list_oracles() has all.")
        if not group:
            lines.append("  (none)")

    state = session.run_all()
    if state["distinct_output_states"] == 1:
        lines += [
            "",
            "The model's outputs NEVER MOVE across the whole stimulus. That is "
            "the first thing to fix: a model with constant outputs satisfies "
            "nothing and cannot tell any design from any other.",
        ]

    # BOTH TOOLS, EVERY TURN. The route is where to START, and the reason is
    # given so it can be overridden on evidence rather than obeyed as a rule.
    first = ("the failing oracles -- they are evidence you already have, and "
             "acting on them costs no model call"
             if session.route == MODEL else
             "the unexercised oracles -- nothing is claiming to check them")
    lines += [
        "",
        f"Start with {first}.",
        "`_tool_add_stimulus(req_uid, \"...\") is open on EVERY turn, on any "
        "requirement showing NOT EXERCISED: describe what has to happen and the "
        "harness generates and gates the vectors. Staging only ever ADDS "
        "evidence, so it cannot make a failing oracle pass and cannot confound "
        "an edit you make beside it.",
        "`_tool_replace_method(method, new_code)` edits the model, and is open "
        + ("now." if session.route == MODEL else
           "only while something is failing -- with no oracle accusing the "
           "model, the only thing an edit can achieve is to make an unexercised "
           "oracle's activation start occurring, which is editing the design so "
           "a check fires rather than staging the scenario the check is about."),
        f"Stimulus budget left this run: {budget_left}."
        if budget_left else
        "The stimulus budget for this run is spent; `_tool_add_stimulus` will say so.",
        "Start with `_tool_explain` on one of them.",
    ]
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
        # DISTANCE, not the failing count. Failing alone calls an edit that
        # stopped a scenario occurring an improvement, because a VIOLATES that
        # became a NOT_EXERCISED leaves the failing count and takes its evidence
        # with it. Distance counts both, so the conversion shows as no progress.
        lines.append(
            f"Your edit to `{last.method}` was accepted: {last.distance_before} "
            f"-> {last.distance_after} requirement(s) still to satisfy "
            f"(failing {last.failing_before} -> {last.failing_after}; the "
            f"difference is requirements nothing is exercising)."
        )
        if last.distance_after > last.distance_before:
            lines.append(
                "That made things WORSE. Consider putting it back before "
                "trying something else."
            )
        elif (last.distance_after == last.distance_before
              and last.failing_after < last.failing_before):
            lines.append(
                "The failing count fell and the distance did not, which means "
                "a requirement stopped being EXERCISED rather than starting to "
                "pass. That is evidence removed, not a defect fixed."
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

    def __init__(self, cfg: OpenAIConfig, *, max_attempts: int = 30):
        self._cfg = cfg
        self._max_attempts = max_attempts
        self._usage: tuple[int, int, int] = (0, 0, 0)
        #: The running conversation, carried turn to turn. See `debug` below.
        self._memory: list = []

    #: `(input, cached, output)` summed over every turn this debugger has run.
    #: Read by the stage so the loop's spend lands in the run's ledger instead
    #: of being counted in memory and dropped.
    #:
    #: THIS DROPPED `cached` AND RAISED WHILE DOING IT. `RefModelEditor.usage`
    #: has returned three values since the cached-token work landed, and this
    #: wrapper still declared two and unpacked two -- so `debug()` raised
    #: `ValueError: too many values to unpack` inside a `finally`, was caught by
    #: the "a turn must not kill the stage" handler, and lost the turn silently.
    #: Had the unpack succeeded, `compose._tokens` would have taken its
    #: two-element branch and reported `cached: 0` forever: a permanent 0% cache
    #: rate that looks exactly like caching that does not work.
    def usage(self) -> tuple[int, int, int]:
        return self._usage

    def debug(self, session: DebugSession) -> tuple[str, int, str]:
        import concurrent.futures

        def _run() -> tuple[str, int, str]:
            # A fresh EDITOR per turn, carrying the previous turn's
            # CONVERSATION. The two used to be the same decision and are not.
            #
            # The editor must be fresh: every turn runs under its own
            # `asyncio.run`, and the model client holds loop-bound resources
            # that do not survive the loop closing.
            #
            # The conversation must not be. The reason given for discarding it
            # -- "the oracle set it was briefed on is gone" -- was true when
            # oracles were regenerated per turn and has been false since they
            # were frozen: `compose.run_debug_turns` raises if the set drifts
            # under the loop, so it is invariant across turns by construction.
            # What actually changes is the model source and the verdicts, and
            # `_opening` restates both at the top of every turn.
            #
            # What discarding it cost: the agent re-derived, every turn, which
            # hypotheses it had already ruled out -- and then re-ruled them out
            # with the same attempts, on requirements it had already failed to
            # fix. See `RefModelEditor.debug` for the sibling measurement.
            editor = RefModelEditor(self._cfg, max_attempts=self._max_attempts)
            editor.restore_memory(self._memory)
            try:
                return asyncio.run(editor.debug(session))
            finally:
                self._memory = editor.snapshot_memory()
                # In `finally` because a turn that raised still spent tokens,
                # and a ledger that only counts successful turns understates
                # exactly the runs worth investigating.
                got_in, got_cached, got_out = editor.usage()
                self._usage = (self._usage[0] + got_in,
                               self._usage[1] + got_cached,
                               self._usage[2] + got_out)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_run).result()
        except Exception as exc:  # noqa: BLE001 -- a turn must not kill the stage
            log.warning("reference-model debug turn could not run: %r", exc)
            return session.best(), len(session.history), f"debug unavailable: {exc!r}"
