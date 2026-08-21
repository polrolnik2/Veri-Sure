"""The turn structure: judge, screen, debug, repeat -- with no live model.

The loop is worth testing offline because its failure modes are all silent. A
turn that discards every oracle and proceeds anyway, a turn that hands back a
worse model than it received, a screening step that runs after the agent has
already spent its attempts -- none of those raise, and all of them would leave
the run looking like it worked.
"""

from __future__ import annotations

import json
from pathlib import Path

from specflow.refmodel import compose
from specflow.refmodel.judge import JudgeResult, RequirementVerdict
from specflow.refmodel.oracles import RequirementOracle
from tests.test_refmodel_session import ACK, BROKEN, CONTRACT, GOOD_STEP, STIM, WORKING

CONTRACT_JSON = json.dumps(CONTRACT)
REQS = [{"uid": "REQ-0000", "text": "ack must pulse"}]
PLAN = [{"uid": "TP-0000"}]


def _verdict(verdict="not_met", *, oracle_source=ACK, uid="REQ-0000"):
    return RequirementVerdict(
        req_uid=uid, verdict=verdict, reason="ack is hardwired to 0",
        oracle=RequirementOracle(req_uid=uid, tp_uids=["TP-0000"],
                                 clause="ack pulses once", source=oracle_source),
    )


class _Judge:
    """Returns a scripted JudgeResult per turn, and counts the turns."""

    def __init__(self, script):
        self.script = list(script)
        self.turns = 0

    def __call__(self, **kwargs):
        self.turns += 1
        return self.script.pop(0) if self.script else JudgeResult(verdicts=[])


class _Debugger:
    """Applies a scripted edit to whatever session it is handed."""

    def __init__(self, script):
        self.script = list(script)
        self.sessions = []

    def debug(self, session):
        self.sessions.append(session)
        if self.script:
            method, code = self.script.pop(0)
            session.replace_method(method, code)
        return session.best(), len(session.history), "done"


def _turns(judge, debugger, *, source=BROKEN, max_turns=2, run_dir=None,
           control=None):
    # `_debug_turns` imports run_judge from the judge module at call time, so
    # that module is the seam -- patching `compose` would do nothing.
    import specflow.refmodel.judge as judge_mod
    original = judge_mod.run_judge
    judge_mod.run_judge = judge
    try:
        return compose._debug_turns(
            source=source, contract=CONTRACT, contract_json=CONTRACT_JSON,
            requirements=REQS, covers={"REQ-0000": ["step"]},
            judge_port=object(), base="step", testplan=PLAN,
            stimulus_by_tp=STIM, run_dir=run_dir, debugger=debugger,
            max_turns=max_turns, control_source=control,
        )
    finally:
        judge_mod.run_judge = original


def test_a_turn_that_satisfies_everything_stops_judging():
    """The judge is ~77 model calls; one more than needed is the expensive kind."""
    judge = _Judge([
        JudgeResult(verdicts=[_verdict("not_met")]),
        JudgeResult(verdicts=[_verdict("met")]),
    ])
    debugger = _Debugger([("step", GOOD_STEP)])
    source, issues = _turns(judge, debugger, max_turns=5)
    assert judge.turns == 2, "it must not keep judging after the verdicts pass"
    assert not issues
    assert "self.k == 3" in source


def test_the_debug_session_only_ever_sees_screened_oracles():
    """The gates run BEFORE the agent, so no attempt is spent on a bad oracle."""
    # This oracle contradicts its own author: the judge said not_met, it passes.
    contradictory = _verdict("not_met", oracle_source='''
def decide(trace):
    _ = trace[0]["outputs"]["ack"]
    return (True, 0, "passes regardless")
''')
    judge = _Judge([JudgeResult(verdicts=[contradictory])])
    debugger = _Debugger([])
    _turns(judge, debugger, max_turns=1)
    assert not debugger.sessions, (
        "every oracle was discarded, so there was nothing to debug against -- "
        "the turn must not build a session with an empty oracle set"
    )


def test_a_turn_with_no_trusted_oracle_falls_back_to_prose():
    """Today's behaviour, so a judge that cannot write oracles costs nothing."""
    broken_oracle = _verdict("not_met", oracle_source="def decide(trace):\n    return 1/0\n")
    judge = _Judge([JudgeResult(verdicts=[broken_oracle])])
    source, issues = _turns(judge, _Debugger([]), max_turns=3)
    assert source == BROKEN, "the model is handed back untouched"
    assert issues, "the blocking verdict still reaches the caller as prose"
    assert judge.turns == 1, "and it does not burn further judging turns"


def test_the_session_is_given_the_judges_reasoning_and_the_requirement():
    judge = _Judge([JudgeResult(verdicts=[_verdict("not_met")])])
    debugger = _Debugger([])
    _turns(judge, debugger, max_turns=1)
    session = debugger.sessions[0]
    assert session.verdicts["REQ-0000"] == "not_met"
    assert session.reasons["REQ-0000"]["reason"] == "ack is hardwired to 0"
    assert session.requirements["REQ-0000"]["text"] == "ack must pulse"
    assert session.covers["REQ-0000"] == ["step"]


def test_each_turn_persists_its_own_oracles_and_screening(tmp_path: Path):
    judge = _Judge([
        JudgeResult(verdicts=[_verdict("not_met")]),
        JudgeResult(verdicts=[_verdict("not_met")]),
    ])
    _turns(judge, _Debugger([]), max_turns=2, run_dir=tmp_path)
    for turn in (0, 1):
        base = tmp_path / "specflow" / "judge" / f"r{turn}"
        assert (base / "verdicts.json").exists()
        assert (base / "oracles" / "REQ-0000.py").exists()
        trust_report = json.loads((base / "trust.json").read_text())
        assert set(trust_report) == {"rates", "discarded", "sensitivity"}
        assert trust_report["rates"]["trusted"] == 1


def test_the_control_gate_reaches_the_screening(tmp_path: Path):
    """An oracle a known-good model fails is over-strict, not a model defect."""
    inert_control = ('from specflow.refmodel.base import RefModel\n\n\n'
                     'class Model(RefModel):\n'
                     '    OUTPUT_PORTS = ["q", "ack"]\n\n'
                     '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
    judge = _Judge([JudgeResult(verdicts=[_verdict("not_met")])])
    debugger = _Debugger([])
    _turns(judge, debugger, max_turns=1, run_dir=tmp_path, control=inert_control)
    report = json.loads(
        (tmp_path / "specflow" / "judge" / "r0" / "trust.json").read_text())
    assert report["rates"]["over_strict"] == 1
    assert not debugger.sessions


def test_a_debug_turn_never_returns_a_worse_model():
    """The session's best is what propagates, whatever the agent last did."""
    judge = _Judge([
        JudgeResult(verdicts=[_verdict("not_met")]),
        JudgeResult(verdicts=[_verdict("not_met")]),
    ])
    ruin = 'def step(self, i):\n    return {"q": 0, "ack": 0}'
    source, _ = _turns(judge, _Debugger([("step", GOOD_STEP), ("step", ruin)]),
                       source=BROKEN, max_turns=2)
    assert "self.k == 3" in source, (
        "turn 1 fixed it; turn 2 ruined it and must hand back its own best"
    )


def test_the_next_turn_judges_the_model_the_last_one_produced():
    seen = []

    class _Recording(_Judge):
        def __call__(self, **kwargs):
            seen.append(kwargs["source"])
            return super().__call__(**kwargs)

    judge = _Recording([
        JudgeResult(verdicts=[_verdict("not_met")]),
        JudgeResult(verdicts=[_verdict("not_met")]),
    ])
    _turns(judge, _Debugger([("step", GOOD_STEP)]), max_turns=2)
    assert seen[0] == BROKEN
    assert seen[1] != BROKEN and "self.k == 3" in seen[1], (
        "a turn judging the model it already replaced would measure nothing"
    )


def test_run_refmodel_without_a_debugger_is_unchanged():
    """The stage must degrade to today's behaviour when none is supplied."""
    import inspect
    src = inspect.getsource(compose.run_refmodel)
    assert "debugger is None" in src, (
        "the in-gate judge path must still be reachable"
    )
    assert "debugger: RefModelDebugger | None = None" in src


def test_working_model_needs_no_debug_session():
    judge = _Judge([JudgeResult(verdicts=[_verdict("met")])])
    debugger = _Debugger([])
    source, issues = _turns(judge, debugger, source=WORKING, max_turns=3)
    assert source == WORKING and not issues and not debugger.sessions
