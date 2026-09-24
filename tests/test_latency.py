"""`refmodel.latency.fragile`: a check resting on a latency nobody stated."""
from specflow.refmodel import latency as L
from specflow.refmodel.oracle_gen import RequirementOracle

#: "busy is cleared after STOP": reads busy on the SAME row as `stop`.
SAME_ROW = '''
def decide(trace):
    seen = False
    for r in trace:
        if r["outputs"]["stop"] == 1:
            seen = True
            if r["outputs"]["busy"] != 0:
                return (False, r["edge"], "busy not cleared at STOP")
    return (True, None, "") if seen else (None, None, "no STOP")
'''

#: The same obligation with a window: busy low on the STOP row or the next.
WINDOWED = '''
def decide(trace):
    seen = False
    for i, r in enumerate(trace):
        if r["outputs"]["stop"] == 1:
            seen = True
            nxt = trace[i + 1] if i + 1 < len(trace) else r
            if r["outputs"]["busy"] != 0 and nxt["outputs"]["busy"] != 0:
                return (False, r["edge"], "busy never cleared after STOP")
    return (True, None, "") if seen else (None, None, "no STOP")
'''


def _raw(stop, busy, clk=None):
    clk = clk or list(range(len(stop)))
    return [{"edge": i, "inputs": {"c": c}, "outputs": {"stop": s, "busy": b}}
            for i, (s, b, c) in enumerate(zip(stop, busy, clk))]


def _o(src):
    return RequirementOracle(req_uid="REQ-1", clause="c", source=src, tp_uids=["TP-0"])


#: A combinational design: busy falls on the STOP row.
ROWS = {"TP-0": _raw([0, 0, 1, 0, 0], [1, 1, 0, 0, 0])}


def test_a_same_row_check_is_flagged():
    why = L.fragile(_o(SAME_ROW), ROWS, ["busy"], "busy is cleared after STOP")
    assert why.startswith(L.PREFIX) and "busy" in why


def test_a_windowed_check_is_not():
    assert L.fragile(_o(WINDOWED), ROWS, ["busy"], "busy is cleared after STOP") == ""


def test_a_stated_latency_licenses_the_same_row():
    assert L.fragile(_o(SAME_ROW), ROWS, ["busy"],
                     "busy is cleared immediately when STOP is detected") == ""
    assert L.fragile(_o(SAME_ROW), ROWS, ["busy"],
                     "busy is cleared asynchronously by STOP") == ""


def test_an_observable_the_check_does_not_read_is_not_lagged():
    assert L.fragile(_o(SAME_ROW), ROWS, ["cmd_ack"], "x after y") == ""


def test_a_testpoint_the_check_fails_on_says_nothing_about_latency():
    bad = {"TP-0": _raw([0, 0, 1, 0, 0], [1, 1, 1, 1, 1])}
    assert L.fragile(_o(SAME_ROW), bad, ["busy"], "busy is cleared after STOP") == ""


def test_lagging_moves_one_clock_on_raw_rows():
    late = L.lagged(ROWS["TP-0"], ["busy"])
    assert [r["outputs"]["busy"] for r in late] == [1, 1, 1, 0, 0]
    assert [r["outputs"]["stop"] for r in late] == [0, 0, 1, 0, 0]


# ------------------------------------------------------------- wired into the stage

def test_a_latency_discard_routes_back_to_the_author():
    from specflow.refmodel import verdict as V
    assert V.of_discard(L.PREFIX + " anything") == "ORACLE_INVALID"


def test_the_refuser_replays_each_testpoint_once_and_needs_a_substrate(monkeypatch):
    from specflow.refmodel import oracles as O
    assert L.refuser("", {}, {}, {}, {}, base="step") is None

    calls = []

    def _replay(src, contract, steps, *, base):
        calls.append(tuple(steps))
        return type("R", (), {"rows": ROWS["TP-0"]})()

    monkeypatch.setattr(O, "replay", _replay)
    why = L.refuser("design", {}, {"TP-0": [1]}, {"REQ-1": {"observable": ["busy"]}},
                    {"REQ-1": "busy is cleared after STOP"}, base="step")
    assert why("REQ-1", _o(SAME_ROW)).startswith(L.PREFIX)
    assert why("REQ-1", _o(WINDOWED)) == ""
    assert len(calls) == 1, "the substrate is replayed once per testpoint"


def test_admitted_pool_drops_a_refused_corpus_body():
    from types import SimpleNamespace

    from specflow.oracles_stage import admitted_pool
    anchor = _o(WINDOWED)
    oset = SimpleNamespace(trusted=[anchor], corpus={"REQ-1": [
        SimpleNamespace(source=SAME_ROW), SimpleNamespace(source=WINDOWED + "\n# v2\n")]})
    contract = {"io": [{"name": "stop", "dir": "output", "width": 1},
                       {"name": "busy", "dir": "output", "width": 1}]}
    plan = [{"uid": "TP-0"}]
    base_pool = admitted_pool(oset, contract, plan)
    refused = admitted_pool(oset, contract, plan,
                            refuse=lambda uid, o: ("latency:" if "not cleared at STOP"
                                                   in o.source else ""))
    assert len(refused) == len(base_pool) - 1
    assert all("not cleared at STOP" not in o.source for o in refused)


def test_the_stage_gates_rescues_and_swaps_through_the_same_refuser():
    """SOURCE-LEVEL PINS -- a call site inside `run_oracle_stage` has been
    deleted on this branch without failing a behavioural test more than once."""
    import inspect

    from specflow import integration, oracles_stage as S
    stage = inspect.getsource(S.run_oracle_stage)
    assert "_late = _latency.refuser(" in stage
    fold = stage.index("why = _late(uid, held[uid])")
    assert "rejected[uid] = quotable[uid] = why" in stage[fold:fold + 200]
    assert stage.index("for uid, detail in dead_now.items():") < fold
    assert "refuse=_late)" in stage
    assert "if _late is not None and _late(uid, body):" in stage
    assert S._latency.PREFIX in S._RESCUABLE
    build = inspect.getsource(integration.build_artifacts)
    assert "refuse=_refuse)" in build
