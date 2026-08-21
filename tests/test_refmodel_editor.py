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
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.session import DebugSession
from tests.test_refmodel_session import (
    ACK,
    BROKEN,
    CONTRACT,
    GOOD_STEP,
    STIM,
    WORKING,
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
    editor._stall_rounds = kw.get("stall_rounds", 2)
    editor._session = None
    editor._agent = _StubAgent(session, script)
    editor.reset = lambda: None
    return asyncio.run(editor.debug(session))


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
    assert parsed[0]["req_uid"] == "REQ-0000"
    assert parsed[0]["status"] == "NOT MET"


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
    s = _session(model=WORKING)
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


def test_a_turn_with_nothing_failing_does_no_work():
    s = _session(model=WORKING)
    source, attempts, note = _drive(s, [("step", GOOD_STEP)])
    assert attempts == 0 and "nothing was failing" in note


def test_a_stalling_turn_gives_up_rather_than_grinding():
    """Only an actual ATTEMPT counts toward stalling.

    A turn spent reading and replaying is the agent working; cutting it off
    there is how a debugger gets stopped before its first edit.
    """
    useless = 'def step(self, i):\n    return {"q": 1, "ack": 0}'
    s = _session()
    _, attempts, _ = _drive(s, [("step", useless)] * 6, stall_rounds=2)
    assert attempts < 6, "it should stop once edits stop helping"


def test_an_agent_failure_ends_the_turn_without_killing_the_stage():
    class _Boom:
        async def __call__(self, msg):
            raise RuntimeError("model exploded")

    s = _session()
    editor = RefModelEditor.__new__(RefModelEditor)
    editor.max_attempts, editor._stall_rounds, editor._session = 6, 2, None
    editor._agent = _Boom()
    editor.reset = lambda: None
    source, _, note = asyncio.run(editor.debug(s))
    assert "ended early" in note
    assert source == BROKEN, "the model is handed back unchanged, not lost"
