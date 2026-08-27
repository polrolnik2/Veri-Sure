"""The debug loop's spend has to reach the ledger.

Every other stage writes a `usage` block to `agent_io`. This one calls the model
directly through `SyncRefModelDebugger`, so it wrote nothing at all, and a run's
recorded cost was its fan-outs only. `get_model_usage` already existed and only
the verilog-eval harness called it -- the counters were kept in memory and
dropped.

The gap was visible from outside before it was visible from inside: a ledger
built from `agent_io` put 99.5% of output tokens on the small model, and the
actual bill did not resemble that at all.
"""

from __future__ import annotations

import json

from specflow.refmodel import compose
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "y", "dir": "output", "width": 1},
]}

SRC = """
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': 0}          # WRONG on purpose: the oracle must fail, or
                                 # the loop converges and never calls the
                                 # debugger, and zero is the correct answer.
"""

ORACLE = ("def decide(trace):\n"
          "    for r in trace:\n"
          "        if r['outputs']['y'] != r['inputs']['a']:\n"
          "            return False, r['edge'], 'y != a'\n"
          "    return True, 0, 'ok'\n")


class _Counting:
    """A debugger that spends and reports, like the real one now does."""

    def __init__(self):
        self._spent = (0, 0)

    def debug(self, session):
        self._spent = (self._spent[0] + 1000, self._spent[1] + 250)
        return session.best(), 0, "did nothing, cost something"

    def usage(self):
        return self._spent


class _Silent:
    """An older debugger with no counter at all."""

    def debug(self, session):
        return session.best(), 0, "no counter"


def _run(tmp_path, debugger):
    compose._debug_turns(
        source=SRC, contract=CONTRACT, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y follows a"}],
        covers={"step": ["REQ-0001"]},
        oracles=[RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                                   clause="y follows a", source=ORACLE)],
        base="step", testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp={"TP-0000": [{"a": 0}, {"a": 1}]},
        run_dir=tmp_path, debugger=debugger, max_turns=1,
        control_source=None, normalized=None, item_port=None,
    )
    turns = sorted((tmp_path / "specflow" / "judge").glob("r*/trust.json"))
    return json.loads(turns[-1].read_text())


def test_the_loops_tokens_reach_the_turn_artifact(tmp_path):
    blob = _run(tmp_path, _Counting())
    assert blob["debug_tokens"]["output"] > 0, (
        "the loop spent tokens and the ledger says zero")
    assert blob["debug_tokens"]["input"] > 0
    # CACHED IS ALWAYS PRESENT, even at zero. A key that appears only when the
    # gateway reported one is a key a reader cannot distinguish from a cache
    # that stopped working, which is the whole failure this ledger exists to
    # make visible.
    assert "cached" in blob["debug_tokens"]
    assert blob["debug_tokens"]["cached"] <= blob["debug_tokens"]["input"], (
        "cached tokens are a SUBSET of input tokens, not a separate column")


def test_a_two_element_usage_still_reports_what_it_has(tmp_path):
    """A debugger built against the older `(input, output)` signature must
    degrade to `cached: 0`, not raise inside the loop."""
    from specflow.refmodel.compose import _tokens

    class _Old:
        def usage(self):
            return (500, 40)

    assert _tokens(_Old()) == {"input": 500, "cached": 0, "output": 40}

    class _New:
        def usage(self):
            return (500, 300, 40)

    assert _tokens(_New()) == {"input": 500, "cached": 300, "output": 40}


def test_a_debugger_without_a_counter_reports_a_hole_not_a_guess(tmp_path):
    """Zero, never an estimate. A guessed number in a cost ledger is worse than
    a hole, because a hole is visibly a hole."""
    blob = _run(tmp_path, _Silent())
    assert blob["debug_tokens"] == {"input": 0, "cached": 0, "output": 0}


def test_a_turn_that_raised_still_counts_what_it_spent():
    """In `finally`, because a ledger that counts only successful turns
    understates exactly the runs worth investigating."""
    import inspect

    from eda_agent.refmodel_editor import SyncRefModelDebugger

    body = inspect.getsource(SyncRefModelDebugger.debug)
    assert "finally:" in body
    assert "editor.usage()" in body
