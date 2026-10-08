"""`decide(..., phase_free=...)`: a conviction a probe's unstated schedule can
undo is not evidence -- and an abstention under the shift is not a pass."""
from specflow.refmodel.oracles import decide, shift_probe
from specflow.refmodel.oracle_gen import RequirementOracle

#: "when the trigger input rises, `cond` (a probe) is high on that same row".
SAME_ROW = '''
def decide(trace):
    seen = False
    for i, r in enumerate(trace):
        if r["inputs"]["t"] == 1 and (i == 0 or trace[i-1]["inputs"]["t"] == 0):
            seen = True
            if r["outputs"]["cond"] != 1:
                return (False, i, "cond not high when t rose")
    return (True, None, "") if seen else (None, None, "t never rose")
'''

#: Reads `cond` as its TRIGGER: shifting it moves the activation, not a verdict.
TRIGGER = '''
def decide(trace):
    for i, r in enumerate(trace):
        if r["outputs"]["cond"] == 1:
            return (r["outputs"]["busy"] == 1, i, "busy low while cond high")
    return (None, None, "cond never rose")
'''


def _rows(t, cond, busy=None):
    busy = busy or [0] * len(t)
    return [{"edge": i, "inputs": {"t": a}, "outputs": {"cond": b, "busy": c}}
            for i, (a, b, c) in enumerate(zip(t, cond, busy))]


def _o(src):
    return RequirementOracle(req_uid="REQ-1", clause="c", source=src,
                             tp_uids=["TP-0"])


def test_a_registered_probe_is_not_convicted_for_its_schedule():
    """`cond` rises one row after `t`: a registered reading of the same equation."""
    rows = _rows([0, 1, 1, 1], [0, 0, 1, 1])
    assert decide(_o(SAME_ROW), rows).ok is False
    got = decide(_o(SAME_ROW), rows, phase_free=["cond"])
    assert got.ok is None and "PASSES with probe(s) cond read one row later" in got.detail


def test_a_combinational_probe_checked_as_registered_is_also_spared():
    rows = _rows([0, 1, 1, 1], [1, 0, 0, 0])
    assert decide(_o(SAME_ROW), rows, phase_free=["cond"]).ok is None


def test_a_probe_that_never_fires_is_still_convicted():
    """No schedule of `cond` makes this pass -- a real defect stays one."""
    rows = _rows([0, 1, 1, 1], [0, 0, 0, 0])
    assert decide(_o(SAME_ROW), rows, phase_free=["cond"]).ok is False


def test_an_abstention_under_the_shift_does_not_exonerate():
    """Shifting the TRIGGER probe past the end loses the activation: None, not
    True, so the conviction stands. Counting this as a pass leaked blindness."""
    rows = _rows([0, 0, 0], [0, 0, 1], busy=[0, 0, 0])
    assert decide(_o(TRIGGER), rows).ok is False
    assert decide(_o(TRIGGER), rows, phase_free=["cond"]).ok is False


def test_a_probe_the_check_does_not_read_is_not_shifted():
    rows = _rows([0, 1, 1, 1], [0, 0, 1, 1])
    assert decide(_o(SAME_ROW), rows, phase_free=["con", "busy"]).ok is False


def test_shift_probe_moves_one_probe_and_nothing_else():
    rows = _rows([0, 1, 0], [0, 1, 0], busy=[1, 0, 1])
    later = shift_probe(rows, "cond", 1)
    assert [r["outputs"]["cond"] for r in later] == [1, 0, 0], "clamped, not None"
    assert [r["outputs"]["busy"] for r in later] == [1, 0, 1]
    assert [r["inputs"]["t"] for r in later] == [0, 1, 0]


#: Asserts two conditions on every row; a registered design lags on BOTH.
BOTH = '''
def decide(trace):
    seen = False
    for i, r in enumerate(trace):
        a, b = r["inputs"]["a"], r["inputs"]["b"]
        if a or b:
            seen = True
        if r["outputs"]["ca"] != a or r["outputs"]["cb"] != b:
            return (False, i, "condition out of step")
    return (True, None, "") if seen else (None, None, "")
'''


def _two(a, b, ca, cb):
    return [{"edge": i, "inputs": {"a": w, "b": x}, "outputs": {"ca": y, "cb": z}}
            for i, (w, x, y, z) in enumerate(zip(a, b, ca, cb))]


def test_a_group_moves_together_where_one_probe_at_a_time_cannot():
    rows = _two([0, 1, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0], [0, 0, 1, 0, 0, 0],
                [0, 0, 0, 0, 1, 0])
    o = _o(BOTH)
    assert decide(o, rows, phase_free=["ca", "cb"]).ok is False
    assert decide(o, rows, phase_groups=[["ca", "cb"]]).ok is None
