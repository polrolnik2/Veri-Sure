"""The agent wrapper around a debug session.

Only what the wrapper itself adds is tested here -- the session's behaviour is
covered offline in `test_refmodel_session.py`. What the wrapper adds is the
tool surface, the prompts, and the loop's exits, and each has a way of going
wrong that no session test would catch.
"""

from __future__ import annotations

import asyncio
import inspect
import json

from eda_agent.refmodel_editor import SYSTEM_PROMPT, RefModelEditor, _continue, _opening
from specflow.refmodel.oracles import OracleResult, RequirementOracle
from specflow.refmodel.session import DebugSession
from tests.test_refmodel_session import (
    ACK,
    BROKEN,
    CONTRACT,
    GOOD_STEP,
    Q_MOVES,
    STIM,
    WORKING,
    _oracle,
)


def _session(model=BROKEN, oracles=None) -> DebugSession:
    return DebugSession(
        model, CONTRACT, STIM,
        oracles or [RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                                      clause="ack pulses once", source=ACK)],
        base="step",
        requirements=[{"uid": "REQ-0000", "text": "ack must pulse"}],
        verdicts={"REQ-0000": "not_met"},
        covers={"REQ-0000": ["step"]},
    )


class _StubAgent:
    """Stands in for the ReAct agent: runs a script of edits, then replies."""

    def __init__(self, session, script, reply="done"):
        self.session = session
        self.script = list(script)
        self.reply = reply
        self.calls = 0

    async def __call__(self, msg):
        self.calls += 1
        if self.script:
            method, code = self.script.pop(0)
            self.session.replace_method(method, code)
        return type("_R", (), {"content": self.reply})()


def _drive(session, script, **kw) -> tuple[str, int, str]:
    editor = RefModelEditor.__new__(RefModelEditor)     # no live model client
    editor.max_attempts = kw.get("max_attempts", 6)
    editor._session = None
    editor._agent = _StubAgent(session, script)
    editor.reset = lambda: None
    return asyncio.run(editor.debug(session))


def _drive_counting(session, script, **kw):
    """`(result, calls)` -- how many times the AGENT was actually invoked.

    Needed because "the turn did no work" and "the turn did work that changed
    nothing" produce the same `(source, attempts, note)`, and the bug being
    pinned below is precisely that the agent was never called.
    """
    editor = RefModelEditor.__new__(RefModelEditor)
    editor.max_attempts = kw.get("max_attempts", 6)
    editor._session = None
    agent = _StubAgent(session, script)
    editor._agent = agent
    editor.reset = lambda: None
    return asyncio.run(editor.debug(session)), agent.calls


# ------------------------------------------------------------- tool surface


def test_every_tool_is_registered_and_documented():
    """AgentScope derives the tool schema from the signature and docstring.

    An undocumented tool reaches the model as a name with no description, which
    is indistinguishable from a tool that does nothing.
    """
    tools = [n for n, _ in inspect.getmembers(RefModelEditor, inspect.isfunction)
             if n.startswith("_tool_")]
    assert set(tools) == {
        "_tool_list_oracles", "_tool_explain", "_tool_run_oracle",
        "_tool_read_model", "_tool_replace_method", "_tool_run_all",
        # Eighth: undo. `best()` protects what the TURN hands back; without a
        # revert the agent could only overwrite a bad edit, never take it out,
        # so every later edit reasoned about a model it had already broken.
        # `TBEditor` exposes the same move. It became load-bearing when the
        # stall cutoff was deleted: a turn now spends its whole budget.
        "_tool_revert_to_best",
        # Seventh: an oracle reporting NOT EXERCISED is not a defect in the
        # model, and until this existed the turn had no instrument to act on
        # one -- 30 of 67 requirements on f-i2c were in exactly that state.
        "_tool_add_stimulus",
    }
    for name in tools:
        fn = getattr(RefModelEditor, name)
        assert (fn.__doc__ or "").strip(), f"{name} has no docstring"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_there_is_no_tool_that_edits_an_oracle():
    """A loop able to weaken what measures it will take that path."""
    tools = [n for n, _ in inspect.getmembers(RefModelEditor, inspect.isfunction)
             if n.startswith("_tool_")]
    assert not [n for n in tools if "oracle" in n and
                any(v in n for v in ("replace", "write", "set", "edit", "remove"))]


def test_a_tool_without_a_session_says_so_rather_than_raising():
    editor = RefModelEditor.__new__(RefModelEditor)
    editor._session = None
    out = asyncio.run(editor._tool_list_oracles())
    assert "no active debug session" in out.content[0]["text"]


def test_tools_return_readable_json():
    editor = RefModelEditor.__new__(RefModelEditor)
    editor._session = _session()
    out = asyncio.run(editor._tool_list_oracles())
    parsed = json.loads(out.content[0]["text"])
    assert parsed["acting_on"][0]["req_uid"] == "REQ-0000"
    assert parsed["acting_on"][0]["status"] == "NOT MET"


def test_the_board_lists_only_what_the_turn_can_act_on_and_counts_the_rest():
    """The `list_suspect_blocks` discipline: the failure decides what is shown.

    All 104 oracles used to arrive on every call -- ~40 KB -- and the turn acts
    on a handful. What is not shown is COUNTED, never hidden: a truncated list
    that does not say it was truncated reads as the whole population.
    """
    s = _session()
    s._results = [
        OracleResult("REQ-0000", ok=False, edge=3, detail="ack stayed low"),
        OracleResult("REQ-0001", ok=True, edge=1),
        OracleResult("REQ-0002", ok=None),
    ]
    s.oracles = list(s.oracles) + [
        RequirementOracle(req_uid="REQ-0001", clause="c1", tp_uids=["TP-0000"],
                          source=s.oracles[0].source),
        RequirementOracle(req_uid="REQ-0002", clause="c2", tp_uids=["TP-0000"],
                          source=s.oracles[0].source),
    ]
    board = s.board()
    # Detail for BOTH kinds of work, failing first on a model turn. The
    # unexercised one is acted on too: `add_stimulus` is open on every turn, and
    # putting REQ-0002 under "this turn cannot act on them" talked the agent out
    # of the one tool that was never closed.
    assert [r["req_uid"] for r in board["acting_on"]] == ["REQ-0000", "REQ-0002"]
    assert board["acting_on"][0]["detail"] == "ack stayed low"
    # ...and every requirement that ALREADY CONFORMS named, not merely counted.
    # The agent must know REQ-0001 is met before it edits the method that
    # satisfies it, and a census cannot tell it which one that is.
    assert board["not_acting_on"] == {"met": ["REQ-0001"]}
    assert "an edit can BREAK" in board["note"]
    assert "explain(req_uid)" in board["note"]


def test_a_stimulus_turn_leads_with_the_unexercised_and_still_shows_the_rest():
    """The route is an ORDER, not a filter. Same set either way."""
    s = _session()
    s._results = [
        OracleResult("REQ-0000", ok=False, edge=3, detail="ack stayed low"),
        OracleResult("REQ-0002", ok=None),
    ]
    s.oracles = list(s.oracles) + [
        RequirementOracle(req_uid="REQ-0002", clause="c2", tp_uids=["TP-0000"],
                          source=s.oracles[0].source),
    ]
    s.route = "stimulus"
    assert s.focus() == ["REQ-0002", "REQ-0000"]
    s.route = "model"
    assert s.focus() == ["REQ-0000", "REQ-0002"]


def test_the_board_names_every_requirement_even_when_it_details_none_of_them():
    """Nothing may be invisible. `list_suspect_blocks` summarises each item and
    `read_block` fetches the body; the summary half is what makes the detail
    half safe to withhold."""
    s = _session()
    s._results = [OracleResult("REQ-0000", ok=True, edge=1)]
    board = s.board()
    named = {u for uids in board["not_acting_on"].values() for u in uids}
    assert board["acting_on"] == [] and named == {"REQ-0000"}


# ------------------------------------------------------------------ prompts


def test_the_opening_prompt_names_what_is_failing_and_why():
    text = _opening(_session())
    assert "REQ-0000" in text and "ack pulses once" in text
    assert "1 of 1" in text


def test_the_opening_prompt_leads_with_inertness_when_the_model_is_inert():
    inert = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "ack"]\n\n'
             '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
    assert "NEVER MOVE" in _opening(_session(model=inert))


def test_the_continue_prompt_restates_the_outcome_not_an_exhortation():
    """Same reasoning as rtl_editor's continue prompt."""
    s = _session()
    assert "No edit has been made yet" in _continue(s)

    s.replace_method("step", GOOD_STEP)
    text = _continue(s)
    assert "was accepted" in text and "1 -> 0" in text

    s2 = _session()
    s2.replace_method("step", "def step(self, i):\n    return {")
    assert "REJECTED" in _continue(s2)


def test_the_continue_prompt_calls_out_an_edit_that_made_things_worse():
    # Two oracles, one already failing, so the turn has a model route at all --
    # a session with nothing failing takes the stimulus route (I8).
    s = _session(oracles=[_oracle(), _oracle(Q_MOVES, "REQ-0001")])
    s.replace_method("step", 'def step(self, i):\n    return {"q": 0, "ack": 0}')
    assert "WORSE" in _continue(s)


def test_the_system_prompt_states_the_rules_that_save_attempts():
    for phrase in ("ONE FIX AT A TIME", "CANNOT edit them", "mask(",
                   "list_oracles", "replace_method"):
        assert phrase in SYSTEM_PROMPT, phrase


# --------------------------------------------------------------------- loop


def test_a_turn_that_fixes_everything_stops_early():
    s = _session()
    source, attempts, _ = _drive(s, [("step", GOOD_STEP)])
    assert s.all_met()
    assert attempts == 1, "it must not keep spending attempts after succeeding"
    assert "ack" in source


def test_a_turn_returns_the_best_source_not_the_last():
    """A turn that wandered downhill hands back where it was highest.

    Two oracles, both failing on an inert model. The first edit fixes one; the
    second undoes it. The turn must return the intermediate source, which no
    variable in the loop is holding by the time it ends.
    """
    q_moves = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["q"] != 0:
            return (True, row["edge"], "q moved")
    return (False, None, "q never moved")
'''
    inert = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "ack"]\n\n'
             '    def reset(self):\n        self.n = 0\n        self.k = 0\n\n'
             '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
    q_only = ('def step(self, i):\n'
              '    if not hasattr(self, "n"):\n        self.reset()\n'
              '    self.n = self.mask(self.n + i.get("a", 0), 8)\n'
              '    return {"q": self.n, "ack": 0}')
    back_to_inert = 'def step(self, i):\n    return {"q": 0, "ack": 0}'

    s = _session(model=inert, oracles=[
        RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                          clause="ack pulses once", source=ACK),
        RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                          clause="q moves", source=q_moves),
    ])
    assert len(s.failing()) == 2

    source, _, _ = _drive(s, [("step", q_only), ("step", back_to_inert)])
    assert len(s.failing()) == 2, "the last edit really did undo the progress"
    assert "self.n" in source, "the turn must return the version that fixed q"
    assert source != inert


def test_a_turn_with_neither_route_open_does_no_work():
    """Nothing failing AND nothing unexercised: there is genuinely no input.

    This used to assert only the first half, and that reading is what made the
    stimulus route unreachable -- the guard it pinned returned before the agent
    ran on every turn with nothing failing, which is exactly the turn
    `add_stimulus` is for. The counter-case is the test below.
    """
    s = _session(model=WORKING)
    assert not s.failing() and not s.undecided(), "the premise for this one"
    _source, attempts, note = _drive(s, [("step", GOOD_STEP)])
    assert attempts == 0
    assert "nothing is failing and nothing is unexercised" in note


def test_a_turn_with_nothing_failing_but_work_to_stage_runs_the_agent():
    """The case the old assertion swallowed, asserted on AGENT INVOCATIONS.

    Measured on q-i2c: turns 2 and 3 are one second apart in their artifact
    timestamps -- no model call happens in a second. Five runs staged zero
    testpoints because control returned here before the agent existed, so what
    has to be pinned is that the agent is reached, not what it then produced.
    """
    s = _session(model=WORKING)
    s._results = [
        type(r)(req_uid=r.req_uid, ok=None, edge=None, detail="not staged")
        for r in s.results]
    assert not s.failing(), "nothing is failing"
    assert s.undecided(), "and something is unexercised"
    assert s.stimulus_budget > len(s.added), "with budget to stage it"

    (_source, _attempts, _note), calls = _drive_counting(s, [])
    assert calls >= 1, "the agent must be invoked when there is stimulus to stage"


def test_a_turn_with_no_input_at_all_still_costs_no_model_call():
    """The counter-case, so the guard is narrowed rather than deleted."""
    s = _session(model=WORKING)
    assert not s.failing() and not s.undecided()
    (_source, attempts, note), calls = _drive_counting(s, [])
    assert calls == 0 and attempts == 0
    assert "nothing is failing and nothing is unexercised" in note


def test_a_spent_stimulus_budget_with_nothing_failing_is_also_no_input():
    s = _session(model=WORKING)
    s._results = [
        type(r)(req_uid=r.req_uid, ok=None, edge=None, detail="not staged")
        for r in s.results]
    s.stimulus_budget = 0
    (_source, _attempts, note), calls = _drive_counting(s, [])
    assert calls == 0
    assert "stimulus budget is spent" in note


def test_a_turn_that_is_not_improving_keeps_its_budget():
    """NON-IMPROVING EDITS ARE NOT A REASON TO STOP. This is the inverse of a
    test that used to assert the opposite, and the reason it flipped.

    There was a cutoff at two consecutive non-improving ATTEMPTS. Two things
    made it worse than the number suggests. It counted individual edits, where
    `RTLEditor`'s equivalent counts outer rounds of up to ten model calls each
    -- same number, an order of magnitude apart in what it permits. And the
    turn cleared its memory on entry, so the ruled-out hypotheses went with it
    and the next turn re-derived and re-stalled on the same two.

    `RTLEditor` states the argument against it directly: "Crossing a valley
    takes several consecutive non-improving rounds by definition, so a stall
    limit tuned for a monotone search will cut the search off before it can get
    anywhere." This loop has no rollback guard forcing monotonicity, so every
    valley crossing scored as a stall.

    The cutoff bought nothing: `best()` already guarantees a turn cannot hand
    back worse than it started with, whatever it does in between.
    """
    useless = 'def step(self, i):\n    return {"q": 1, "ack": 0}'
    s = _session()
    _, attempts, _ = _drive(s, [("step", useless)] * 6)
    assert attempts == 6, "the whole edit budget is spent on a hard requirement"


def test_nothing_named_stall_survives():
    """The knob is deleted, not defaulted off.

    A parameter whose only correct setting is off is a parameter that will be
    turned back on by someone reading the signature rather than this test.
    """
    import inspect as _i

    from eda_agent import refmodel_editor as mod

    assert "stall" not in _i.signature(RefModelEditor.__init__).parameters
    assert "_stall_rounds" not in _i.getsource(mod.RefModelEditor.debug)


def test_an_agent_failure_ends_the_turn_without_killing_the_stage():
    class _Boom:
        async def __call__(self, msg):
            raise RuntimeError("model exploded")

    s = _session()
    editor = RefModelEditor.__new__(RefModelEditor)
    editor.max_attempts, editor._session = 6, None
    editor._agent = _Boom()
    editor.reset = lambda: None
    source, _, note = asyncio.run(editor.debug(s))
    assert "ended early" in note
    assert source == BROKEN, "the model is handed back unchanged, not lost"


def test_the_stop_rule_and_the_route_rule_cannot_both_fire():
    """The prompt used to say "stop when nothing is failing" while also saying a
    turn with nothing failing IS the stimulus turn -- telling the agent to stop
    at exactly the moment the stimulus route opened. Three runs, zero
    testpoints added, by two opposite causes.

    Asserted on fragments that do not cross a line wrap: a phrase spanning a
    wrapped line has silently passed here before.
    """
    assert "Stop when `list_oracles()` shows nothing failing" not in SYSTEM_PROMPT
    for phrase in ("Nothing failing is not done",
                   "every oracle CONFORMS",
                   "budget spent"):
        assert phrase in SYSTEM_PROMPT, phrase


def test_the_prompt_does_not_claim_add_stimulus_refuses():
    """It no longer does, and a prompt saying so trains the agent not to try.

    On q-i2c the agent called `add_stimulus` twice, was refused both times, and
    closed the turn reporting "stimulus staging was unavailable because this
    turn was the model-repair route" -- it believed the prose. The refusal is
    gone; the prose has to go with it or the belief outlives the code.
    """
    assert "`_tool_add_stimulus` is ALWAYS available" in SYSTEM_PROMPT
    assert "`_tool_add_stimulus` refuses" not in SYSTEM_PROMPT
    assert ("`_tool_replace_method` refuses on a turn with nothing failing"
            in SYSTEM_PROMPT)


# --------------------------------------------------- context across turns


def test_the_turn_does_not_clear_its_own_conversation():
    """`debug()` used to call `self.reset()` on entry.

    That threw away the reasoning, not just the tokens. `TBEditor` records the
    same loss from a memory window: "a genuinely correct multi-cycle datapath
    model, reaching the run's best fail_count, was abandoned one trial later
    and never rebuilt ... consistent with the model losing the reasoning for
    why it built that design." Both siblings default `memory_window=0`, and a
    per-turn reset is a window of zero applied at the worst moment.
    """
    import inspect as _i

    src = _i.getsource(RefModelEditor.debug)
    assert "self.reset()" not in src


def test_the_conversation_is_carried_from_one_turn_to_the_next():
    """A fresh EDITOR per turn is required -- each turn runs under its own
    `asyncio.run` and the model client is loop-bound. A fresh CONVERSATION is
    not, and the reason given for it expired when the oracle set was frozen:
    `run_debug_turns` raises if the set drifts, so it is invariant across turns.
    """
    class _Mem:
        def __init__(self):
            self.content = []

    class _Agent:
        def __init__(self):
            self.memory = _Mem()

    editor = RefModelEditor.__new__(RefModelEditor)
    editor._agent = _Agent()
    editor.restore_memory(["turn-1 said this"])
    assert editor.snapshot_memory() == ["turn-1 said this"]


def test_a_carry_failure_does_not_kill_the_turn():
    class _Hostile:
        memory = property(lambda self: (_ for _ in ()).throw(RuntimeError("no")))

    editor = RefModelEditor.__new__(RefModelEditor)
    editor._agent = _Hostile()
    editor.restore_memory(["x"])          # must not raise
    assert editor.snapshot_memory() == []


def test_a_clipped_response_declares_the_cut():
    """The backstop, not the strategy. "A truncated list that does not say it
    was truncated reads as the whole population" (`rtl_editor.py:236-243`)."""
    from eda_agent.refmodel_editor import TOOL_MAX_CHARS, _clip

    out = _clip("x" * (TOOL_MAX_CHARS * 2))
    assert "characters cut from the middle" in out
    assert len(out) < TOOL_MAX_CHARS * 2
    assert _clip("short") == "short"


def test_every_tool_the_prompt_NAMES_is_a_tool_that_exists():
    """The prompt told the agent to call tools by names nothing answers to.

    `Toolkit.register_tool_function` takes the name from `func.__name__`, so the
    schema carries `_tool_add_stimulus` while the prompt said `add_stimulus`.
    An agent following the prose gets

        ToolError: 'add_stimulus' is not an available tool

    burns the round trip, and re-issues against the schema. `GuidingToolkit`
    makes that recoverable rather than fatal, which is exactly why it went
    unnoticed -- and the tool the prose pushed hardest is the one that never
    fired in five runs.

    `RTLEditor` has this right: its prompt says `_tool_read_block(block_id)`
    (`rtl_editor.py:409, :428`), matching what it registers. This pins the same
    property for the sibling that diverged.
    """
    import re

    from eda_agent import refmodel_editor as RE

    registered = {n for n in dir(RE.RefModelEditor) if n.startswith("_tool_")}
    assert registered, "no tools found -- the check would pass vacuously"
    bare = {n[len("_tool_"):] for n in registered}

    surfaces = [RE.SYSTEM_PROMPT]
    named = set()
    for text in surfaces:
        for m in re.finditer(r"`?\b(\w+)\(", text):
            named.add(m.group(1))
    offenders = sorted(named & bare)
    assert not offenders, (
        f"the prompt calls {offenders} but the toolkit registers them as "
        f"_tool_-prefixed; an agent following the prose gets ToolError")
