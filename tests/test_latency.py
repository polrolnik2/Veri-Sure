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
