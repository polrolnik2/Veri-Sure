"""The staging budget is sized per STATE, not per check.

The old sizing gave every silent check its own allocation. That is right only if
every abstention is a separate stimulus problem, and the k1 triage says it is
not: eight of them were dependents of ONE state the design compiles out, and
they spent 24 attempts between them discovering that eight times over.

One testpoint that reaches P serves every check waiting on P, so the allocation
belongs to the state.
"""
from __future__ import annotations

from specflow import reachability as R

PROBES = ["in_idle", "in_cload", "in_srefill4"]


def _rows(states: list[str]) -> list[dict]:
    return [{"edge": i, "inputs": {}, "outputs": {p: 1 if p == st else 0
                                                 for p in PROBES}}
            for i, st in enumerate(states)]


POOL = R.observed({"tp_0001": _rows(["in_idle", "in_cload"])}, PROBES)


def _norm(*, opens_on=(), until=(), observable=()) -> dict:
    return {"activation": {"opens_on": [{k: 1} for k in opens_on],
                           "until": [{k: 1} for k in until],
                           "aborts_on": [], "sustains": [], "inputs": {}},
            "observable": list(observable)}


def test_the_window_probe_is_read_from_the_activation() -> None:
    assert R.waiting_on(_norm(opens_on=["in_srefill4"]), PROBES) == ["in_srefill4"]
    assert R.waiting_on(_norm(until=["in_cload"]), PROBES) == ["in_cload"]
    # A check whose ASSERTED EFFECT is a state needs it reached just as surely
    # as one whose window is -- a transition obligation states its effect ON the
    # state, and the scope rule is a default rather than a prohibition.
    assert R.waiting_on(_norm(observable=["in_srefill4"]), PROBES) == ["in_srefill4"]
    # A declared OUTPUT is not a probe and does not gate reachability.
    assert R.waiting_on(_norm(observable=["burst"]), PROBES) == []


def test_eight_checks_on_one_unobserved_state_share_one_allocation() -> None:
    """The k1 case, exactly: 8 SREFILL4 dependents get 3 attempts, not 24."""
    waiting = {f"REQ-{i:04d}": ["in_srefill4"] for i in range(8)}
    assert R.budget_for(waiting, POOL, per_state=3, cap=400) == 3


def test_a_check_naming_no_probe_keeps_its_own_allocation() -> None:
    """That bucket is not empty -- 10 of k1's 25 abstainers name no state.

    Nothing in this change reaches them, so nothing about their budget moves.
    """
    waiting = {"REQ-A": [], "REQ-B": [], "REQ-C": []}
    assert R.budget_for(waiting, POOL, per_state=3, cap=400) == 9


def test_a_check_waiting_on_an_OBSERVED_state_costs_nothing() -> None:
    """It does not schedule at all.

    The state was reached and the check stayed silent anyway, which is a defect
    in the check. It routes to the check author, or takes the reproducer another
    testpoint already produced. Neither spends a discovery attempt.
    """
    waiting = {"REQ-A": ["in_cload"], "REQ-B": ["in_idle"]}
    assert R.budget_for(waiting, POOL, per_state=3, cap=400) == 3  # the floor


def test_the_mixed_case_adds_states_and_legacy_checks() -> None:
    waiting = {"REQ-A": ["in_srefill4"], "REQ-B": ["in_srefill4"],
               "REQ-C": ["in_nowhere"], "REQ-D": [], "REQ-E": ["in_cload"]}
    pool = dict(POOL, in_nowhere=[])
    # two unobserved states + one legacy check = 3 allocations
    assert R.budget_for(waiting, pool, per_state=3, cap=400) == 9


def test_the_cap_still_binds() -> None:
    waiting = {f"REQ-{i:04d}": [f"in_s{i}"] for i in range(500)}
    pool = {f"in_s{i}": [] for i in range(500)}
    assert R.budget_for(waiting, pool, per_state=3, cap=400) == 400


# --------------------------------------------------------------------------
# The end-to-end shape: what the loop actually spends.
# --------------------------------------------------------------------------

CONTRACT = {
    "module_name": "dcfsm",
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "rst", "dir": "input", "width": 1},
        {"name": "go", "dir": "input", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
        {"name": "in_idle", "dir": "probe", "width": 1},
        {"name": "in_cload", "dir": "probe", "width": 1},
        {"name": "in_srefill4", "dir": "probe", "width": 1},
    ],
    "clocking": {"is_sequential": True,
                 "clock": {"name": "clk", "edge": "posedge"},
                 "reset": {"name": "rst", "active": "high", "synchronous": False}},
}

#: Reaches IDLE and CLOAD; never reaches SREFILL4 -- the k1 case, where the
#: state its eight dependents wait on is compiled out of the design.
WITNESS = """
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['busy']
    PROBE_PORTS = ['in_idle', 'in_cload', 'in_srefill4']
    LATENCY_CYCLES = 0

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = 'IDLE'
        self._sync()

    def _sync(self):
        self.in_idle = self.state == 'IDLE'
        self.in_cload = self.state == 'CLOAD'
        self.in_srefill4 = False

    def step(self, inputs):
        if inputs.get('rst'):
            self.reset()
        elif inputs.get('go'):
            self.state = 'CLOAD'
        else:
            self.state = 'IDLE'
        self._sync()
        return {'busy': 1 if self.state == 'CLOAD' else 0}
"""

STEPS = [{"inputs": {"rst": 1, "go": 0}, "hold": 2, "reset": True},
         {"inputs": {"rst": 0, "go": 1}, "hold": 3}]

#: A check that waits for SREFILL4. It can never decide, because the witness
#: never enters it -- which is the whole point of the fixture.
BODY = ("def decide(trace):\n"
        "    for r in trace:\n"
        "        if r['outputs'].get('in_srefill4'):\n"
        "            return (True, r['edge'], 'reached')\n"
        "    return (None, None, 'in_srefill4 never rose')\n")


def test_eight_dependents_of_one_state_spend_one_shared_budget(monkeypatch) -> None:
    """The k1 arithmetic, end to end: 3 stimulus calls, not 8 x 3 = 24.

    Every one of the eight checks waits on the same unobserved state, and a
    stimulus author cannot reach it because the design does not have it. Under
    the old per-check sizing each check discovered that separately and the loop
    reported eight independent stimulus findings for one fact.
    """
    from specflow import oracles_stage as OS
    from specflow import testcase_agent
    from specflow.refmodel.oracles import RequirementOracle

    calls = {"n": 0}

    def _mock_author(**kw):
        calls["n"] += 1
        return list(STEPS)

    # `stage_unexercised` imports the author inside the function, so the patch
    # target is the module it imports FROM.
    monkeypatch.setattr(testcase_agent, "stimulus_for_scenario", _mock_author)

    uids = [f"REQ-{i:04d}" for i in range(8)]
    held = {u: RequirementOracle(req_uid=u, clause="", source=BODY,
                                 tp_uids=["TP-0000"]) for u in uids}
    requirements = [{"uid": u, "text": "while in SREFILL4, busy is high",
                     "unit_kind": "behavioural"} for u in uids]
    normalized = {u: _norm(opens_on=["in_srefill4"]) for u in uids}
    normalized = {u: {**n, "activation": {**n["activation"],
                                          "text": "while in SREFILL4"}}
                  for u, n in normalized.items()}
    testplan = [{"uid": "TP-0000", "covers": [f"{u}@1" for u in uids]}]
    stimulus_by_tp = {"TP-0000": list(STEPS)}

    abandoned, record = OS.stage_unexercised(
        held=held, unexercised={u: "in_srefill4 never rose" for u in uids},
        requirements=requirements, normalized=normalized, contract=CONTRACT,
        testplan=testplan, stimulus_by_tp=stimulus_by_tp, witness=WITNESS,
        port=None, base="step", attempts=3, budget=None, final=True)

    # One unobserved state, three attempts per state.
    assert calls["n"] == 3, f"{calls['n']} stimulus calls, expected 3"

    # EVERY dependent is dispositioned, not just the one that spent the
    # allocation. A budget that is per state with a record that is per check
    # would leave the other seven recording "nothing was attempted" and blocking
    # as NOT_EXERCISED -- strictly worse than the per-check budget it replaced.
    assert set(abandoned) == set(uids), sorted(set(uids) - set(abandoned))
    assert set(record) == set(uids)

    # And they cite the SAME attempts, because the same three testpoints were
    # minted on all their behalf and every one of them was replayed against each.
    staged = {u: sorted(t["staged"] for t in record[u]["attempts"]
                        if t.get("staged")) for u in uids}
    assert len({tuple(v) for v in staged.values()}) == 1, staged
    assert len(staged[uids[0]]) == 3
    inherited = [u for u in uids
                 if any(t.get("shared_with") for t in record[u]["attempts"])]
    assert len(inherited) == 7, inherited


def test_without_probes_the_budget_is_unchanged(monkeypatch) -> None:
    """The control. A contract declaring no probe pays exactly what it did.

    The per-state budget is an improvement where the evidence exists, and must
    not become a way to under-fund staging where it does not.
    """
    from specflow import oracles_stage as OS
    from specflow import testcase_agent
    from specflow.refmodel.oracles import RequirementOracle

    plain = {**CONTRACT,
             "io": [p for p in CONTRACT["io"] if p.get("dir") != "probe"]}
    witness = WITNESS.replace(
        "PROBE_PORTS = ['in_idle', 'in_cload', 'in_srefill4']", "PROBE_PORTS = []")

    calls = {"n": 0}

    def _mock_author(**kw):
        calls["n"] += 1
        return list(STEPS)

    monkeypatch.setattr(testcase_agent, "stimulus_for_scenario", _mock_author)

    uids = [f"REQ-{i:04d}" for i in range(8)]
    held = {u: RequirementOracle(req_uid=u, clause="", source=BODY,
                                 tp_uids=["TP-0000"]) for u in uids}
    OS.stage_unexercised(
        held=held, unexercised={u: "never fired" for u in uids},
        requirements=[{"uid": u, "text": "busy is high",
                       "unit_kind": "behavioural"} for u in uids],
        normalized={u: _norm() for u in uids}, contract=plain,
        testplan=[{"uid": "TP-0000", "covers": [f"{u}@1" for u in uids]}],
        stimulus_by_tp={"TP-0000": list(STEPS)}, witness=witness,
        port=None, base="step", attempts=3, budget=None, final=True)

    assert calls["n"] == 24, f"{calls['n']} stimulus calls, expected 8 x 3 = 24"
