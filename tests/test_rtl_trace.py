"""The RTL trace adapter: recorded simulation -> the rows an oracle decides over.

The load-bearing pin is the unknown-value one. Everything else here is shape.
"""

from __future__ import annotations

import json

import pytest

from specflow.refmodel.oracles import RequirementOracle, transactional_view
from specflow.refmodel.rtl_trace import (SIDES, decide_rtl, load, load_traces,
                                         rows_from, unknown_ports)

CONTRACT = {"io": [{"name": "cmd", "dir": "input", "width": 1},
                   {"name": "busy", "dir": "output", "width": 1},
                   {"name": "cmd_ack", "dir": "output", "width": 1}]}


def _trace(*edges) -> dict:
    """`(edge, cmd, dut_busy, dut_ack, model_busy)` -> a recorded trace."""
    return {"tp_uid": "TP-0000", "outputs": ["busy", "cmd_ack"], "edges": [
        {"edge": e, "step": 0, "inputs": {"cmd": c},
         "dut": {"busy": b, "cmd_ack": a}, "model": {"busy": m, "cmd_ack": a}}
        for e, c, b, a, m in edges]}


def _oracle(source: str, uid: str = "REQ-0001") -> RequirementOracle:
    return RequirementOracle(req_uid=uid, clause="c", source=source,
                             tp_uids=["TP-0000"])


# ------------------------------------------------------------------- shape


def test_rows_from_is_a_pure_reshape():
    """Nothing invented: `{edge, inputs, <side>}` -> `{edge, inputs, outputs}`.
    Anything this function computed would be a fact about the adapter."""
    rows = rows_from(_trace((0, 1, 0, 0, 0), (1, 1, 1, 0, 9)))
    assert rows == [
        {"edge": 0, "inputs": {"cmd": 1}, "outputs": {"busy": 0, "cmd_ack": 0}},
        {"edge": 1, "inputs": {"cmd": 1}, "outputs": {"busy": 1, "cmd_ack": 0}},
    ]


def test_the_model_side_is_readable_from_the_same_trace():
    """One simulation carries both sides, so DUT-versus-model is apples to
    apples on identical stimulus rather than two separate runs."""
    t = _trace((0, 1, 0, 0, 0), (1, 1, 1, 0, 9))
    assert rows_from(t, side="dut")[1]["outputs"]["busy"] == 1
    assert rows_from(t, side="model")[1]["outputs"]["busy"] == 9
    assert set(SIDES) == {"dut", "model"}
    with pytest.raises(ValueError):
        rows_from(t, side="internal")


def test_rows_compress_exactly_as_a_replayed_trace_does():
    """The adapter feeds `transactional_view` unchanged, so a check does not
    mean something different depending on which side produced the rows."""
    rows = rows_from(_trace((0, 1, 0, 0, 0), (1, 1, 0, 0, 0), (2, 1, 1, 0, 0)))
    view = transactional_view(rows)
    assert [r["held"] for r in view] == [2, 1]
    assert [r["edge"] for r in view] == [0, 2]


def test_load_and_load_traces_round_trip(tmp_path):
    (tmp_path / "TP-0000.trace.json").write_text(json.dumps(_trace((0, 1, 0, 0, 0))))
    assert load(tmp_path / "TP-0000.trace.json")[0]["outputs"] == {"busy": 0, "cmd_ack": 0}
    assert sorted(load_traces(tmp_path)) == ["TP-0000"]


# ------------------------------------------- the unknown-value guard (§17.3)


def test_unknown_ports_names_both_kinds_of_unresolved_value():
    """`Env.sample` returns None for a port the design does not expose;
    `_plain` returns `str(value)` for a 4-state X. Both reach here as non-ints
    and both make `== 1` False."""
    t = _trace((0, 1, 0, 0, 0))
    t["edges"][0]["dut"] = {"busy": None, "cmd_ack": "xxxx"}
    assert unknown_ports(rows_from(t)) == {"busy": 1, "cmd_ack": 1}
    assert unknown_ports(rows_from(_trace((0, 1, 0, 0, 0)))) == {}


def test_a_conviction_resting_on_an_unknown_value_is_downgraded():
    """THE LOAD-BEARING PIN. A check reading a port the trace could not resolve
    convicts the design for a value it could not compare -- the failure
    `decide`'s tri-state exists to prevent, arriving from the trace side. It
    must abstain, and it must say which port and how many rows."""
    t = _trace((0, 1, 0, 0, 0))
    t["edges"][0]["dut"]["busy"] = None
    # A REAL oracle subscripts the port by name, which is what `ports_read`
    # scans for. A fixture that convicts without naming the port tests nothing.
    src = ("def decide(trace):\n"
           "    for row in trace:\n"
           "        if row['outputs']['busy'] != 1:\n"
           "            return (False, row['edge'], 'busy was not 1')\n"
           "    return (True, None, 'ok')\n")
    [res] = decide_rtl([_oracle(src)], {"TP-0000": t}, CONTRACT)
    assert res.ok is None, "a conviction on an unresolved value is not evidence"
    assert "busy on 1 row(s)" in res.detail
    assert "busy was not 1" in res.detail, "the original detail survives"


def test_only_a_conviction_is_downgraded():
    """A True needs no rescuing and a None is already an abstention. Rescuing
    either would make the guard a way to launder a verdict."""
    t = _trace((0, 1, 0, 0, 0))
    t["edges"][0]["dut"]["busy"] = None
    for verdict, expect in ((True, True), (None, None)):
        src = ("def decide(trace):\n"
               "    _ = [r['outputs']['busy'] for r in trace]\n"
               f"    return ({verdict!r}, 0, 'seen')\n")
        [res] = decide_rtl([_oracle(src)], {"TP-0000": t}, CONTRACT)
        assert res.ok is expect


def test_an_oracle_reading_only_resolved_ports_keeps_its_conviction():
    """The counter-case, and the reason the guard is scoped by `ports_read`:
    silencing a whole testpoint because a signal the check never mentions was
    missing throws away real findings."""
    t = _trace((0, 1, 0, 0, 0))
    t["edges"][0]["dut"]["busy"] = None          # unknown, and never read
    src = ("def decide(trace):\n"
           "    for row in trace:\n"
           "        if row['outputs']['cmd_ack'] != 1:\n"
           "            return (False, row['edge'], 'cmd_ack should have pulsed')\n"
           "    return (True, None, 'ok')\n")
    [res] = decide_rtl([_oracle(src)], {"TP-0000": t}, CONTRACT)
    assert res.ok is False, "cmd_ack resolved fine; the finding stands"


# ---------------------------------------------------------------- the fold


def test_a_missing_trace_abstains_rather_than_convicting():
    """A testpoint that produced no trace is an evidence gap, not a defect."""
    src = "def decide(trace):\n    return (True, 0, 'ok')\n"
    o = RequirementOracle(req_uid="REQ-0001", clause="c", source=src,
                          tp_uids=["TP-0000", "TP-0404"])
    [res] = decide_rtl([o], {"TP-0000": _trace((0, 1, 0, 0, 0))}, CONTRACT)
    assert res.ok is True, "one testpoint passed; passing outranks unexercised"


def test_the_fold_is_the_same_one_replay_uses():
    """`_worst`, not a second ranking written here -- a verdict from RTL must
    mean exactly what a verdict from a replayed model means."""
    src = "def decide(trace):\n    return (False, 0, 'no')\n"
    o = RequirementOracle(req_uid="REQ-0001", clause="c", source=src,
                          tp_uids=["TP-0000", "TP-0001"])
    traces = {"TP-0000": _trace((0, 1, 0, 0, 0)),
              "TP-0001": _trace((0, 1, 0, 0, 0))}
    [res] = decide_rtl([o], traces, CONTRACT)
    assert res.ok is False, "failing on any testpoint is failing"
