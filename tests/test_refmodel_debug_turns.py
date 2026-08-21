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


Q_MOVES = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["q"] != 0:
            return (True, row["edge"], "q moved")
    return (False, None, "q never moved")
'''
INERT = ('from specflow.refmodel.base import RefModel\n\n\n'
         'class Model(RefModel):\n'
         '    OUTPUT_PORTS = ["q", "ack"]\n\n'
         '    def reset(self):\n        self.n = 0\n        self.k = 0\n\n'
         '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
Q_ONLY = ('def step(self, i):\n'
          '    if not hasattr(self, "n"):\n        self.reset()\n'
          '    self.n = self.mask(self.n + i.get("a", 0), 8)\n'
          '    return {"q": self.n, "ack": 0}')


def _pair(ack: str, q: str):
    """A two-oracle round whose verdicts AGREE with the oracles.

    Gate 1 discards an oracle its author contradicts, so a scripted judge whose
    verdict disagrees with what the model does would be screened out -- which
    is the gate working, and makes for a test that measures nothing.
    """
    return JudgeResult(verdicts=[
        _verdict(ack, uid="REQ-0000"),
        _verdict(q, oracle_source=Q_MOVES, uid="REQ-0001"),
    ])


class _Port:
    """A judge port for the reconciliation call.

    `reconcile` re-asks the judge about each verdict its own oracle
    contradicts, so a test that produces a conflict must supply an answer or it
    is testing the absence of one.
    """

    def __init__(self, answer: str | None = None):
        self.answer = answer
        self.calls: list[str] = []

    def complete(self, *, stage, round_, prompt):
        self.calls.append(stage)
        return self.answer or json.dumps({
            "verdict": "not_met", "reason": "unresolved",
            "oracle": {"tp_uids": ["TP-0000"], "clause": "c", "source": ACK},
        })


def _turns(judge, debugger, *, source=BROKEN, max_turns=2, run_dir=None,
           control=None, port=None):
    # `_debug_turns` imports run_judge from the judge module at call time, so
    # that module is the seam -- patching `compose` would do nothing.
    import specflow.refmodel.judge as judge_mod
    original = judge_mod.run_judge
    judge_mod.run_judge = judge
    try:
        return compose._debug_turns(
            source=source, contract=CONTRACT, contract_json=CONTRACT_JSON,
            requirements=REQS, covers={"REQ-0000": ["step"]},
            judge_port=port or _Port(), base="step", testplan=PLAN,
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


CONTRADICTORY = '''
def decide(trace):
    _ = trace[0]["outputs"]["ack"]
    return (True, 0, "passes regardless")
'''


def test_a_verdict_its_own_oracle_contradicts_is_sent_back_to_the_judge():
    """The oracle is the verdict written executably, so the judge settles it.

    Discarding instead would throw away a usable oracle over a translation bug
    -- a quarter of them, on the run this was built for.
    """
    judge = _Judge([JudgeResult(verdicts=[_verdict("not_met",
                                                   oracle_source=CONTRADICTORY)])])
    port = _Port()          # answers with an oracle that DOES fail the model
    debugger = _Debugger([])
    _turns(judge, debugger, max_turns=1, port=port)
    assert port.calls == ["reconcile_REQ-0000"], "the conflict must be re-asked"
    assert debugger.sessions, "and the repaired oracle should reach the session"
    assert [o.req_uid for o in debugger.sessions[0].oracles] == ["REQ-0000"]


def test_an_unresolved_conflict_still_ends_in_a_discard():
    """Reconciliation is one attempt, not an argument the judge always wins."""
    judge = _Judge([JudgeResult(verdicts=[_verdict("not_met",
                                                   oracle_source=CONTRADICTORY)])])
    # The judge answers with the SAME contradiction: not_met, oracle passes.
    port = _Port(json.dumps({
        "verdict": "not_met", "reason": "still disagreeing",
        "oracle": {"tp_uids": ["TP-0000"], "clause": "c",
                   "source": CONTRADICTORY},
    }))
    debugger = _Debugger([])
    _turns(judge, debugger, max_turns=1, port=port)
    assert not debugger.sessions, (
        "an oracle that still contradicts its verdict must not drive the loop"
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
    judge = _Judge([_pair("not_met", "not_met"), _pair("not_met", "met")])
    _turns(judge, _Debugger([("step", Q_ONLY)]), max_turns=2, run_dir=tmp_path,
           source=INERT)
    for turn in (0, 1):
        base = tmp_path / "specflow" / "judge" / f"r{turn}"
        assert (base / "verdicts.json").exists()
        assert (base / "oracles" / "REQ-0000.py").exists()
        trust_report = json.loads((base / "trust.json").read_text())
        assert set(trust_report) == {"rates", "discarded", "sensitivity",
                                     "unresolved_conflicts",
                                     "control_unexercised", "stimulus"}
        assert trust_report["rates"]["trusted"] >= 1
        # The stimulus is measured every turn, beside the rates it explains:
        # an inert testpoint makes every oracle naming it unjudgeable, and the
        # resulting UNKNOWNs read as findings about the judge if nothing says
        # otherwise.
        assert set(trust_report["stimulus"]) >= {
            "testpoints", "inert", "inert_fraction", "inert_testpoints",
            "requirements_left_unjudgeable"}
        assert trust_report["stimulus"]["testpoints"] >= 1


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


def test_the_verdicts_returned_describe_the_model_returned():
    """The invariant the loop owes its caller.

    Satisfying every trusted oracle is NOT the requirements being met: oracles
    are a subset, screening having discarded some, and each is a necessary
    condition the judge wrote rather than its whole verdict. So the model a
    debug turn produces must be JUDGED before it is handed back -- otherwise a
    turn that fixed everything still reports as blocked, and one that broke
    something no oracle covers still reports as clean.
    """
    seen = []

    class _Recording(_Judge):
        def __call__(self, **kwargs):
            seen.append(kwargs["source"])
            return super().__call__(**kwargs)

    # One turn of budget. The edit lands, and the loop must judge the result.
    judge = _Recording([
        JudgeResult(verdicts=[_verdict("not_met")]),
        JudgeResult(verdicts=[_verdict("met")]),
    ])
    source, issues = _turns(judge, _Debugger([("step", GOOD_STEP)]), max_turns=1)

    assert len(seen) == 2, "the edited model was never judged"
    assert seen[-1] == source, "the final judging pass must be on what is returned"
    assert not issues, "and its verdicts are what the caller receives"


def test_a_turn_that_changes_nothing_does_not_pay_for_another_judging_pass():
    """~77 model calls to rediscover verdicts already in hand."""
    judge = _Judge([JudgeResult(verdicts=[_verdict("not_met")])] * 4)
    source, issues = _turns(judge, _Debugger([]), max_turns=3)
    assert judge.turns == 1
    assert source == BROKEN and issues


def test_exhausting_the_budget_still_judges_the_last_model():
    """The boundary case: the extra pass is not slack, it is the invariant."""
    seen = []

    class _Recording(_Judge):
        def __call__(self, **kwargs):
            seen.append(kwargs["source"])
            return super().__call__(**kwargs)

    judge = _Recording([_pair("not_met", "not_met"),
                        _pair("not_met", "met"),
                        _pair("not_met", "met")])
    source, _ = _turns(judge, _Debugger([("step", Q_ONLY), ("step", GOOD_STEP)]),
                       max_turns=2, source=INERT)
    assert len(seen) == 3, "two debug turns, and a judging pass after each plus one"
    assert seen[-1] == source, "the model handed back is the model last judged"
