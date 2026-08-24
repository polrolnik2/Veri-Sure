"""Step 4 end to end, offline: append a testpoint, attach it by activation.

No model call -- the generator is injected, so everything decidable about the
loop stays decidable with a stub.
"""

from __future__ import annotations

from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.session import DebugSession

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "ack", "dir": "output", "width": 1},
    ]
}

SOURCE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['ack']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'ack': 1 if i['cmd'] == 8 and i['ena'] else 0}
'''

#: Fires only when cmd==8 is driven; otherwise it cannot see its scenario.
WRITE_ORACLE = (
    "def decide(trace):\n"
    "    if not any(r['inputs']['cmd'] == 8 for r in trace):\n"
    "        return (None, None, 'no WRITE (cmd==8) in this trace')\n"
    "    for r in trace:\n"
    "        if r['inputs']['cmd'] == 8 and not r['outputs']['ack']:\n"
    "            return (False, r['edge'], 'ack low on WRITE')\n"
    "    return (True, None, 'ack high on WRITE')\n"
)

NORMALIZED = {
    "REQ-0000": {"activation": {"text": "a WRITE is issued", "inputs": {"cmd": 8, "ena": 1}},
                 "observable": ["ack"], "expectation": "ack rises"},
    # A second requirement needing the SAME condition -- it should be picked up
    # by a testpoint minted for the first.
    "REQ-0001": {"activation": {"text": "a WRITE is issued", "inputs": {"cmd": 8, "ena": 1}},
                 "observable": ["ack"], "expectation": "ack rises"},
    # State-dependent: cannot be matched mechanically, must NOT be attached.
    "REQ-0002": {"activation": {"text": "while the FSM is idle", "inputs": {}},
                 "observable": ["ack"], "expectation": "ack stays low"},
}


def _session(gen=None, **kw):
    oracles = [
        RequirementOracle(req_uid=u, tp_uids=["TP-0000"], clause="ack on WRITE",
                          source=WRITE_ORACLE)
        for u in ("REQ-0000", "REQ-0001", "REQ-0002")
    ]
    return DebugSession(
        SOURCE, CONTRACT, {"TP-0000": [{"cmd": 0, "ena": 1}]}, oracles,
        base="step", normalized=NORMALIZED,
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0000@1"]}],
        stimulus_gen=gen, requirements={}, **kw)


def _write_steps(req, hint):
    return [{"cmd": 8, "ena": 1}, {"cmd": 8, "ena": 1}]


def test_the_starting_state_is_unexercised_not_failing():
    """The distinction the whole tool rests on: nothing is accusing the model."""
    s = _session()
    assert [r.unexercised() for r in s.results] == [True, True, True]
    assert s.failing() == []


def test_adding_stimulus_moves_an_unexercised_oracle_to_a_real_verdict():
    s = _session(gen=_write_steps)
    out = s.add_stimulus("REQ-0000", "issue a WRITE with ena high")
    assert "error" not in out, out
    assert out["added"].startswith("TP-")
    r = next(x for x in s.results if x.req_uid == "REQ-0000")
    assert not r.unexercised(), "the scenario is staged, so the oracle must decide"
    assert r.ok is True


def test_a_new_testpoint_attaches_by_activation_not_by_requester():
    """One good scenario discharges every requirement it stages. Scoping it to
    the requester would waste it; attaching it to everything is what step 0
    refuted."""
    s = _session(gen=_write_steps)
    out = s.add_stimulus("REQ-0000", "issue a WRITE")
    assert set(out["attached_to"]) == {"REQ-0000", "REQ-0001"}
    assert "REQ-0002" not in out["attached_to"], (
        "a state-dependent activation cannot be matched mechanically and must "
        "not be attached on a guess"
    )


def test_nothing_existing_is_modified():
    """Append-only. The original testpoint and its steps survive untouched,
    which is what makes a grown evidence set unable to lose ground."""
    s = _session(gen=_write_steps)
    before = dict(s.stimulus_by_tp)
    s.add_stimulus("REQ-0000", "issue a WRITE")
    for tp, steps in before.items():
        assert s.stimulus_by_tp[tp] == steps
    assert len(s.stimulus_by_tp) == len(before) + 1


def test_identical_stimulus_is_not_appended_twice():
    """Each testpoint becomes its own simulator process in the rendered suite."""
    s = _session(gen=_write_steps)
    assert "error" not in s.add_stimulus("REQ-0000", "issue a WRITE")
    second = s.add_stimulus("REQ-0002", "issue a WRITE")
    assert "error" in second and "identical" in second["error"]


def test_a_generator_that_produces_nothing_is_reported_not_raised():
    """A debug turn that cannot get stimulus has learned something; it has not
    crashed."""
    s = _session(gen=lambda req, hint: [])
    out = s.add_stimulus("REQ-0000", "something impossible")
    assert "error" in out and "no steps" in out["error"]


def test_a_generator_that_raises_is_contained():
    def boom(req, hint):
        raise RuntimeError("gateway exploded")
    s = _session(gen=boom)
    out = s.add_stimulus("REQ-0000", "x")
    assert "error" in out and "gateway exploded" in out["error"]


def test_the_testplan_grows_so_the_rendered_suite_gets_the_testpoint():
    s = _session(gen=_write_steps)
    out = s.add_stimulus("REQ-0000", "issue a WRITE")
    added = [t for t in s.testplan if t["uid"] == out["added"]]
    assert added and added[0]["covers"] == ["REQ-0000@1"]


# ------------------------------------------------- not starving the route

#: Fails outright on SOURCE under this stimulus: cmd is 0, so ack stays low.
ALWAYS_ACK = (
    "def decide(trace):\n"
    "    for r in trace:\n"
    "        if not r['outputs']['ack']:\n"
    "            return (False, r['edge'], 'ack was low')\n"
    "    return (True, None, 'ack held high')\n"
)


def _mixed(**kw):
    """One failing oracle and two unexercised ones -- both routes have work."""
    oracles = [
        RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                          clause="ack on WRITE", source=WRITE_ORACLE),
        RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                          clause="ack on WRITE", source=WRITE_ORACLE),
        RequirementOracle(req_uid="REQ-0003", tp_uids=["TP-0000"],
                          clause="ack is always high", source=ALWAYS_ACK),
    ]
    return DebugSession(
        SOURCE, CONTRACT, {"TP-0000": [{"cmd": 0, "ena": 1}]}, oracles,
        base="step", normalized=NORMALIZED,
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0000@1"]}],
        stimulus_gen=_write_steps, requirements={}, **kw)


def test_a_stalled_model_route_hands_the_turn_to_stimulus():
    """Measured on h-i2c: VIOLATES fell 9, 7, 5 over three turns and never
    reached zero, so `add_stimulus` was never once reached and NOT_EXERCISED
    sat at 18 throughout. "Nothing left to do" is not "nothing failing"."""
    from specflow.refmodel.session import MODEL, STIMULUS

    moving = _mixed(model_route_stalled=False)
    assert moving.failing(), "something IS failing"
    assert any(r.unexercised() for r in moving.results)
    assert moving.route == MODEL, "a route still producing keeps the turn"

    dry = _mixed(model_route_stalled=True)
    assert dry.failing(), "still failing, and the turn goes to stimulus anyway"
    assert dry.route == STIMULUS
    assert "error" not in dry.add_stimulus("REQ-0000", "issue a WRITE")


def test_a_stalled_route_with_nothing_unexercised_stays_on_the_model():
    """Handing the turn to a route with no work on it would waste it."""
    from specflow.refmodel.session import MODEL

    s = DebugSession(
        SOURCE, CONTRACT, {"TP-0000": [{"cmd": 0, "ena": 1}]},
        [RequirementOracle(req_uid="REQ-0003", tp_uids=["TP-0000"],
                           clause="ack is always high", source=ALWAYS_ACK)],
        base="step", normalized=NORMALIZED,
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0003@1"]}],
        stimulus_gen=_write_steps, requirements={}, model_route_stalled=True)
    assert not any(r.unexercised() for r in s.results)
    assert s.route == MODEL


def test_an_appended_testpoint_reaches_the_caller_that_renders_the_suite(
        monkeypatch):
    """Both halves of an appended testpoint must travel together.

    `stimulus_by_tp` already reaches the caller -- the session never copies that
    dict -- but the testplan was copied, so `render_suite` would get stimulus
    for a testpoint it was not rendering and the scenario the loop paid a model
    call to stage would be dropped from the suite in silence.
    """
    from specflow.refmodel import compose

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "ack", "dir": "output", "width": 1},
    ]}
    oracle = RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                               clause="ack on WRITE", source=WRITE_ORACLE)
    #: The caller's objects, exactly as `integration` holds them.
    testplan = [{"uid": "TP-0000", "covers": ["REQ-0000@1"]}]
    stimulus = {"TP-0000": [{"cmd": 0, "ena": 1}]}

    # The loop builds its own generator from `item_port`; substitute the
    # vectors it would have asked a model for.
    import specflow.testcase_agent as tca
    monkeypatch.setattr(tca, "stimulus_for_scenario",
                        lambda **_kw: [{"cmd": 8, "ena": 1}, {"cmd": 8, "ena": 1}])

    staged: dict = {}

    class _Stages:
        def debug(self, session):
            staged["out"] = session.add_stimulus(
                "REQ-0000", "issue a WRITE with ena high")
            return session.source, 1, ""

    compose._debug_turns(
        source=SOURCE, contract=contract, contract_json="{}",
        requirements=[{"uid": "REQ-0000", "text": "ack on WRITE"}],
        covers={"step": ["REQ-0000"]}, oracles=[oracle], base="step",
        testplan=testplan, stimulus_by_tp=stimulus, run_dir=None,
        debugger=_Stages(), max_turns=1, control_source=None,
        normalized=NORMALIZED, item_port=None,
    )
    assert "error" not in staged.get("out", {}), staged
    added = [t["uid"] for t in testplan if t["uid"] != "TP-0000"]
    assert added, "the caller's testplan never saw the appended testpoint"
    assert added[0] in stimulus, "and its stimulus must travel with it"


def test_appended_testpoints_are_persisted_so_reuse_does_not_lose_them(tmp_path):
    """The artifacts on disk must not disagree with the suite rendered from the
    same objects. A `--reuse` re-entry reads the files, so without this it
    silently loses every scenario the loop paid a model call to stage."""
    import json

    from specflow.integration import _persist_grown

    sf = tmp_path / "specflow"
    sf.mkdir(parents=True)
    testplan = [{"uid": "TP-0000"}, {"uid": "TP-0200"}]
    stimulus = {"TP-0000": [{"a": 0}], "TP-0200": [{"a": 1}]}

    _persist_grown(tmp_path, testplan, stimulus, before=(1, 1))
    plan = json.loads((sf / "testplan.json").read_text())
    stim = json.loads((sf / "stimulus.json").read_text())
    assert [e["uid"] for e in plan["elements"]] == ["TP-0000", "TP-0200"]
    assert {t["tp_uid"] for t in stim["testpoints"]} == {"TP-0000", "TP-0200"}


def test_nothing_is_rewritten_when_nothing_grew(tmp_path):
    """A file that did not get longer has nothing to say, and rewriting it
    would churn an artifact `--reuse` re-gates."""
    sf = tmp_path / "specflow"
    sf.mkdir(parents=True)
    (sf / "testplan.json").write_text("SENTINEL", encoding="utf-8")

    from specflow.integration import _persist_grown

    _persist_grown(tmp_path, [{"uid": "TP-0000"}], {"TP-0000": []}, before=(1, 1))
    assert (sf / "testplan.json").read_text() == "SENTINEL"
