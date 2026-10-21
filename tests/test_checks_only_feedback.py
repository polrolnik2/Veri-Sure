"""The RTL Editor's checks-only feedback: the shipped checks, and nothing the model computed.

Under `feedback="model"` the editor is handed failure rows whose `expected=` is
the reference model's value, the model-vs-DUT testpoint verdict as its stop
condition and gradient, and the model's source as "the expected behaviour". The
model is one reading of the specification, not the specification. Under
`feedback="checks"` every one of those channels carries the shipped checks
instead; these cases pin that no model value survives, that the verdict and the
count come from the checks, and that the old mode is untouched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

#: A value only the MODEL side of a trace or record carries, so its appearance
#: anywhere in a checks payload is a leak.
MODEL_ONLY = 77

CONTRACT = {"io": [{"name": "cmd", "dir": "input", "width": 1},
                   {"name": "busy", "dir": "output", "width": 8},
                   {"name": "done", "dir": "output", "width": 1}]}

#: Fails at the first edge where `busy` is nonzero.
STRICT = ("def decide(trace):\n"
          "    for r in trace:\n"
          "        if r['outputs']['busy'] != 0:\n"
          "            return False, r['edge'], 'busy rose while idle'\n"
          "    return True, None, ''\n")
LAX = "def decide(trace):\n    return True, None, ''\n"


def _oracle(uid, src, tps=("TP-0000",)):
    from specflow.refmodel.oracles import RequirementOracle
    return RequirementOracle(req_uid=uid, clause=f"{uid} clause", source=src,
                             tp_uids=list(tps))


def _write(suite, tp, busy):
    """One testpoint's recording and its model-compare record, as `run_suite` writes them."""
    res = suite / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / f"{tp}.trace.json").write_text(json.dumps({
        "tp_uid": tp, "outputs": ["busy", "done"],
        "edges": [{"edge": i, "step": 0, "inputs": {"cmd": 1},
                   "dut": {"busy": b, "done": 0},
                   "model": {"busy": MODEL_ONLY, "done": 1}}
                  for i, b in enumerate(busy)]}), encoding="utf-8")
    (res / f"{tp}.json").write_text(json.dumps({
        "tp_uid": tp, "status": "FAIL", "checks_failed": ["CHK-0001"],
        "signals_failed": ["busy"],
        "mismatches": [{"check": "CHK-0001", "signal": "busy", "step": 0,
                        "got": busy[0], "expected": MODEL_ONLY, "ctx": {"cmd": 1}}]}),
        encoding="utf-8")


def _reviewer(tmp_path, monkeypatch, oracles, *, feedback, build_ok=True,
              failing=("TP-0000",)):
    """A reviewer whose `judge` is the model-compare verdict, without a simulator."""
    import specflow.integration as integ
    from eda_agent.explain import RequirementView
    from eda_agent.specflow_node import SpecflowReviewer

    verdict = SimpleNamespace(
        outcome="REPAIR_RTL" if failing else "ACCEPT", failing=list(failing),
        not_exercised=[], reason="" if build_ok else "build failed: syntax error")
    info = {"results": {tp: "FAIL" for tp in failing}, "uncovered": [],
            "build_ok": build_ok, "wave_vcd": None}
    monkeypatch.setattr(integ, "judge", lambda **_kw: (verdict, info))
    views = {o.req_uid: RequirementView(req_uid=o.req_uid,
                                        text=f"{o.req_uid}: busy stays low while idle")
             for o in oracles}
    return SpecflowReviewer(
        built=SimpleNamespace(suite_dir=tmp_path / "suite", refmodel_path=None, bins=[]),
        hdl_toplevel="dut", output_dir=tmp_path, oracles=oracles,
        contract=CONTRACT, feedback=feedback, requirements=views)


def test_a_checks_payload_carries_no_model_value(tmp_path, monkeypatch):
    """Every byte of what the editor receives, searched for the model's values."""
    _write(tmp_path / "suite", "TP-0000", [0, 0, 5, 5])
    _write(tmp_path / "suite", "TP-0001", [0, 3, 0, 0])
    rev = _reviewer(tmp_path, monkeypatch,
                    [_oracle("REQ-0001", STRICT, ("TP-0000", "TP-0001"))],
                    feedback="checks", failing=("TP-0000", "TP-0001"))
    is_pass, count, sim_output = rev.review()
    payload = json.loads(sim_output)

    assert str(MODEL_ONLY) not in sim_output
    assert "expected=" not in payload["stdout"]
    assert "testpoints" not in payload, "the model-compare testpoint verdict"
    assert is_pass is False
    assert count == 2, "one failing instance per testpoint"
    assert payload["requirements"]["failing"] == ["REQ-0001"]
    stdout = payload["stdout"]
    assert "REQ-0001: busy stays low while idle" in stdout
    assert "busy rose while idle -- TP-0000 at edge 2" in stdout
    assert "also: TP-0001 at edge 1" in stdout
    # the design's OWN values around the edge, and only the ports the check reads
    assert "edge 2: busy=5" in stdout
    assert "done=" not in stdout
    assert payload["trace"]["check_ports"] == ["busy"]
    assert payload["trace"]["fail_step"] is None


def test_checks_pass_when_no_check_fails_however_the_model_disagrees(tmp_path, monkeypatch):
    """The stop condition is the checks: the model-compare FAIL is not read."""
    _write(tmp_path / "suite", "TP-0000", [0, 0, 0])
    rev = _reviewer(tmp_path, monkeypatch, [_oracle("REQ-0001", STRICT)],
                    feedback="checks")
    is_pass, count, sim_output = rev.review()
    assert (is_pass, count) == (True, 0)
    assert json.loads(sim_output)["verdict"] == "ACCEPT"


def test_a_failed_build_is_not_a_pass_under_checks(tmp_path, monkeypatch):
    """No recording means every check abstains, and nothing objecting is not a pass."""
    (tmp_path / "suite" / "results").mkdir(parents=True)
    rev = _reviewer(tmp_path, monkeypatch, [_oracle("REQ-0001", STRICT)],
                    feedback="checks", build_ok=False, failing=())
    is_pass, count, sim_output = rev.review()
    payload = json.loads(sim_output)
    assert is_pass is False and count == 0
    assert payload["verdict"] == "BUILD_FAILED"
    assert "syntax error" in payload["stderr"]


def test_model_feedback_is_unchanged(tmp_path, monkeypatch):
    """The control arm: rows against the model, and the testpoint count."""
    _write(tmp_path / "suite", "TP-0000", [0, 0, 0])
    rev = _reviewer(tmp_path, monkeypatch, [_oracle("REQ-0001", LAX)], feedback="model")
    is_pass, count, sim_output = rev.review()
    payload = json.loads(sim_output)
    assert (is_pass, count) == (False, 1)
    assert f"expected={MODEL_ONLY}" in payload["stdout"]
    assert payload["testpoints"] == {"TP-0000": "FAIL"}
    assert "feedback" not in payload
    # the requirement surface is decided either way
    assert rev.req_results["REQ-0001"][0].ok is True


def test_an_unknown_feedback_is_refused(tmp_path):
    from eda_agent.specflow_node import SpecflowReviewer
    with pytest.raises(ValueError, match="feedback"):
        SpecflowReviewer(built=None, hdl_toplevel="dut", output_dir=tmp_path,
                         feedback="golden")


def test_describe_shows_the_checks_and_not_the_model(tmp_path, monkeypatch):
    _write(tmp_path / "suite", "TP-0000", [0, 4, 0])
    rev = _reviewer(tmp_path, monkeypatch,
                    [_oracle("REQ-0001", STRICT), _oracle("REQ-0002", LAX)],
                    feedback="checks")
    rev.review()
    text = rev.describe()
    assert "reference model (the expected behaviour)" not in text
    assert "NOT a reference model" in text
    assert "[REQ-0001] FAILS: REQ-0001: busy stays low while idle" in text
    assert "busy rose while idle" in text, "the failing check's source"
    assert "REQ-0002" not in text, "passing checks are not listed"


def test_describe_respects_its_budget():
    from eda_agent.specflow_node import describe_checks
    oracles = [_oracle(f"REQ-{i:04d}", STRICT) for i in range(50)]
    results = {o.req_uid: (SimpleNamespace(ok=False), {}) for o in oracles}
    text = describe_checks(oracles, results, max_chars=2000)
    assert len(text) <= 2000
    assert "further checks omitted" in text


def test_decide_rtl_is_the_fold_of_its_instances(tmp_path):
    from specflow.refmodel.oracles import _worst
    from specflow.refmodel.rtl_trace import (decide_rtl, decide_rtl_instances,
                                             load_traces)
    _write(tmp_path, "TP-0000", [0, 0, 5])
    _write(tmp_path, "TP-0001", [0, 0, 0])
    traces = load_traces(tmp_path / "results")
    oracles = [_oracle("REQ-0001", STRICT), _oracle("REQ-0002", LAX)]
    each = decide_rtl_instances(oracles, traces, CONTRACT)
    assert [u for u, _rs in each] == ["REQ-0001", "REQ-0002"]
    assert [r.ok for r in each[0][1]] == [False, True]
    assert decide_rtl(oracles, traces, CONTRACT) == [_worst(u, rs) for u, rs in each]


def test_the_editor_prompts_under_checks_name_no_expected_values():
    from eda_agent import rtl_editor as ed
    assert "ground truth" in ed.INIT_EDITION_PROMPT
    assert "ground truth" not in ed.INIT_EDITION_PROMPT_CHECKS
    assert "(expected vs actual) values when available" in ed.EXTRA_ORDER_PROMPT
    assert "(expected vs actual) values when available" not in ed.EXTRA_ORDER_PROMPT_CHECKS
    assert "<failing_scenarios> to find" not in ed.EXTRA_ORDER_PROMPT_CHECKS
    slots = ("{input_spec}", "{contract_json}", "{generated_tb}",
             "{sim_failed_log_excerpt}", "{kmap_hint}")
    assert all(s in ed.INIT_EDITION_PROMPT_CHECKS for s in slots)


def test_the_continue_prompt_names_the_count_it_has(tmp_path):
    from eda_agent.rtl_editor import _EditSession, _render_continue_debug_prompt
    kw = dict(tb_path=None, rtl_path=str(tmp_path / "rtl.sv"), output_dir=str(tmp_path),
              last_mismatch_cnt=3, sim_reviewer=None, max_trials=5)
    old = _render_continue_debug_prompt(_EditSession(**kw))
    assert "Current accepted state: 3 mismatches." in old
    new = _render_continue_debug_prompt(_EditSession(
        **kw, count_noun="failing check instances"))
    assert "Current accepted state: 3 failing check instances." in new
    assert "mismatches" not in new


def test_the_trace_report_slices_from_the_ports_the_checks_read(tmp_path):
    from eda_agent.trace_report import build_trace_report
    rtl = tmp_path / "rtl.sv"
    rtl.write_text(
        "module dut(input clk, input cmd, output reg busy, output reg done);\n"
        "  always @(posedge clk) busy <= cmd;\n"
        "  always @(posedge clk) done <= ~cmd;\n"
        "endmodule\n", encoding="utf-8")

    def roots(trace):
        log = json.dumps({"format": "specflow", "stdout": "", "stderr": "",
                          "trace": trace})
        _report, blocks = build_trace_report(rtl_path=rtl, sim_log_json=log,
                                             output_dir=tmp_path)
        return {w for b in blocks for w in b.writes}

    assert roots({"check_ports": ["busy"]}) == {"busy"}
    assert roots({}) == {"busy", "done"}, "no check ports: every output, as before"
