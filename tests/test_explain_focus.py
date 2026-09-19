"""`explain` and `focus`, and the requirement plumbing they stand on.

The gap these close: `req_uid` appeared nowhere in the editor's report path, so
the agent got check ids, the whole spec as undifferentiated background, and a
prompt asking it to name "the specific contract requirement that was violated".
B21 is what that cost -- with names only the debugger invented a timing theory
and broke the contract's 1-cycle latency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


from eda_agent.explain import (RequirementView, _boundary, _edge_time,
                               _satisfying_perturbation, _transitions,
                               explain_failure, focus_slice,
                               load_requirement_views)

RTL = """\
module m(input clk, input a, output b, output c);
assign b = a;

always @(posedge clk) begin
  c <= a;
end

endmodule
"""

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "b", "dir": "output", "width": 1},
    {"name": "c", "dir": "output", "width": 1},
]}

TRACE = {"tp_uid": "TP-0000", "outputs": ["b", "c"], "edges": [
    {"edge": 0, "step": 0, "t": 100, "inputs": {"a": 0}, "dut": {"b": 0, "c": 0}},
    {"edge": 1, "step": 0, "t": 200, "inputs": {"a": 1}, "dut": {"b": 1, "c": 0}},
    {"edge": 2, "step": 1, "t": 300, "inputs": {"a": 1}, "dut": {"b": 1, "c": 1}},
    {"edge": 3, "step": 1, "t": 400, "inputs": {"a": 0}, "dut": {"b": 0, "c": 1}},
]}


@dataclass
class _Result:
    ok: bool | None = False
    edge: int | None = 3
    detail: str = "b fell while a was still high"
    tp_uid: str = "TP-0000"
    rows: list = None
    window_start: int | None = 1


def _rows():
    return [{"edge": e["edge"], "inputs": dict(e["inputs"]),
             "outputs": dict(e["dut"])} for e in TRACE["edges"]]


# -------------------------------------------------- the requirement plumbing


def test_the_view_joins_four_artifacts_that_were_never_joined(tmp_path):
    run = tmp_path / "run"
    (run / "specflow").mkdir(parents=True)
    (run / "specflow/requirements.json").write_text(json.dumps({"requirements": [
        {"uid": "REQ-0001", "text": "b shall follow a"}]}))
    (run / "specflow/normalized.json").write_text(json.dumps({"normalized": [
        {"req_uid": "REQ-0001", "activation": {"text": "while enabled",
                                               "inputs": {"a": 1}},
         "expectation": "b is high"}]}))
    (run / "specflow/oracles.json").write_text(json.dumps({"oracles": [
        {"req_uid": "REQ-0001", "clause": "b follows a", "tp_uids": ["TP-0000"],
         "source": "def decide(trace):\n    return (True, None, 'ok') if all("
                   "r['outputs']['b'] == r['inputs']['a'] for r in trace) "
                   "else (False, 0, 'b did not follow a')"}]}))
    views = load_requirement_views(run, CONTRACT)
    v = views["REQ-0001"]
    assert v.text == "b shall follow a"
    assert v.activation["inputs"] == {"a": 1}
    assert v.expectation == "b is high"
    assert "b" in v.ports, "ports_read must reach the view"
    brief = v.brief()
    assert brief["requirement"] and brief["when"] and brief["then"]


def test_a_missing_artifact_degrades_and_never_raises(tmp_path):
    """A loop that cannot read normalized.json should lose the activation and
    KEEP the requirement, not lose the requirement."""
    run = tmp_path / "run"
    (run / "specflow").mkdir(parents=True)
    (run / "specflow/requirements.json").write_text(json.dumps({"requirements": [
        {"uid": "REQ-0001", "text": "b shall follow a"}]}))
    views = load_requirement_views(run, CONTRACT)
    assert views["REQ-0001"].text == "b shall follow a"
    assert views["REQ-0001"].activation == {}


# ---------------------------------------------------------------- the span


def test_edge_time_is_READ_never_computed():
    """`edge * period_ns` would be wrong exactly where the agent is sent to
    look: stimulus steps carry holds, so the mapping is not uniform."""
    assert _edge_time(TRACE, 2) == 300
    assert _edge_time(TRACE, 99) is None
    assert _edge_time({"edges": [{"edge": 0}]}, 0) is None, "no stamp, no time"


def test_the_boundary_is_CONSECUTIVE_not_sampled():
    """The skew detectors compare row i against row i-N, so a scattered sample
    destroys exactly the structure they exist to find."""
    rows = _boundary(TRACE, ["b", "c"], 0, 3)
    assert [r["edge"] for r in rows] == [0, 1, 2, 3]
    assert rows[1]["b"] == 1 and rows[1]["t"] == 200


def test_transitions_are_reported_as_edges_not_levels():
    rows = _boundary(TRACE, ["b", "c"], 0, 3)
    tr = _transitions(rows, ["b", "c"])
    assert "b 0 -> 1 at t=200" in tr
    assert "c 0 -> 1 at t=300" in tr
    assert "b 1 -> 0 at t=400" in tr


# --------------------------------------------------------------- the slice


def test_focus_slices_from_one_requirements_ports():
    """§6.2(b): with 43 of 110 failing, the union of their ports is most of the
    port list and the slice returns most of the design."""
    only_b = {b.id for b in focus_slice(RTL, ["b"])}
    only_c = {b.id for b in focus_slice(RTL, ["c"])}
    assert only_b and only_c
    assert only_b != only_c, "different requirements must give different slices"


def test_focus_on_a_signal_nothing_drives_returns_nothing_rather_than_everything():
    assert focus_slice(RTL, ["nonexistent_signal"]) == []


# ------------------------------------------------------------- the annotation


def test_explain_carries_the_REQUIREMENT_not_only_the_checks_sentence():
    """The half the loop never had. `OracleResult.detail` is the check author's
    account of its own check; only the requirement says what the design owed."""
    view = RequirementView(req_uid="REQ-0001", text="b shall follow a",
                           activation={"text": "while enabled"},
                           expectation="b is high", ports=["b"],
                           source="def decide(trace):\n    return (False, 3, 'x')")
    out = explain_failure(view=view, result=_Result(rows=_rows()), trace=TRACE,
                          contract=CONTRACT, rtl_text=RTL)
    assert out["requirement"]["requirement"] == "b shall follow a"
    assert out["requirement"]["when"] == "while enabled"
    assert out["requirement"]["then"] == "b is high"
    assert out["check_said"] == "b fell while a was still high"


def test_explain_reports_a_SPAN_with_real_simulator_times():
    view = RequirementView(req_uid="REQ-0001", ports=["b"],
                           source="def decide(trace):\n    return (False, 3, 'x')")
    out = explain_failure(view=view, result=_Result(rows=_rows()), trace=TRACE,
                          contract=CONTRACT, rtl_text=RTL)
    assert out["span"]["opened_at_edge"] == 1 and out["span"]["objected_at_edge"] == 3
    assert out["span"]["opened_at_t"] == 200 and out["span"]["objected_at_t"] == 400
    assert "window_warning" not in out


def test_a_trace_with_no_time_stamp_SAYS_SO_rather_than_windowing_on_indices():
    """The silent failure the stamp exists to stop: an edge index fed to a
    filter over nanosecond timestamps collapses the window to the run's start
    and shows the agent the wrong ten cycles, with no error anywhere."""
    stale = {"edges": [{"edge": i, "inputs": {}, "dut": {"b": 0}} for i in range(4)]}
    view = RequirementView(req_uid="REQ-0001", ports=["b"],
                           source="def decide(trace):\n    return (False, 3, 'x')")
    out = explain_failure(view=view, result=_Result(rows=_rows()), trace=stale,
                          contract=CONTRACT, rtl_text=RTL)
    assert "window_warning" in out and "NOT timestamps" in out["window_warning"]


def test_the_perturbation_names_a_value_when_one_satisfies_the_check():
    """The replacement for expected/actual, and a statement about the CHECK
    rather than a fabricated reference value."""
    from specflow.refmodel.oracles import RequirementOracle
    oracle = RequirementOracle(
        req_uid="REQ-0001", clause="", tp_uids=[],
        source="def decide(trace):\n"
               "    bad = [r for r in trace if r['outputs']['b'] != r['inputs']['a']]\n"
               "    return (False, bad[0]['edge'], 'b != a') if bad else (True, None, 'ok')")
    rows = _rows()
    rows[3]["outputs"]["b"] = 1          # b=1 while a=0 -> the check fails at 3
    out = _satisfying_perturbation(oracle, rows, CONTRACT, 3)
    assert "driving b=0 at the deciding edge would satisfy this check" in out


def test_a_temporal_defect_is_NAMED_as_temporal():
    """When nothing flips it, saying so is the useful answer: it settles the
    distinction the debugger most often gets wrong."""
    from specflow.refmodel.oracles import RequirementOracle
    oracle = RequirementOracle(
        req_uid="REQ-0001", clause="", tp_uids=[],
        source="def decide(trace):\n    return (False, 0, 'always fails')")
    out = _satisfying_perturbation(oracle, _rows(), CONTRACT, 0)
    assert "TEMPORAL" in out and "not a wrong value" in out
