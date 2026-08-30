"""The seam between the specflow oracle and the RTL repair agent.

`run_specflow_node` reuses `RTLEditor`, which was written for the monolithic
SystemVerilog path. The reuse was believed to need no editor changes because the
editor is parameterised on a reviewer object -- but `chat()` also read
`<run>/tb.sv` off disk to fill its `generated_tb` prompt slot, and specflow never
writes that file. The first repair iteration died with `FileNotFoundError`, so
the specflow repair loop had never once run.

These cases pin both halves: the editor must not require the file, and what
specflow hands it instead must actually describe the oracle.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from specflow.integration import describe_oracle

REPO = Path(__file__).resolve().parents[1]


def _suite(tmp_path: Path, *, failing: list[str]) -> Path:
    suite = tmp_path / "suite"
    (suite / "results").mkdir(parents=True)
    for uid in ("TP-0001", "TP-0002", "TP-0003"):
        (suite / "results" / f"{uid}.json").write_text(
            json.dumps({
                "tp_uid": uid,
                "status": "FAIL" if uid in failing else "PASS",
                "checks_invoked": ["CHK-0001"],
                "checks_failed": ["CHK-0001"] if uid in failing else [],
                "bins_hit": ["BIN-0001"],
                "mismatches": ([{"check": "CHK-0001", "got": 0, "expected": 1, "ctx": {"a": 1}}]
                               if uid in failing else []),
            }),
            encoding="utf-8",
        )
    return suite


TESTPLAN = [
    {"uid": "TP-0001", "dimension": "D1", "stimulus": "drive a=1",
     "expected_response": "y goes high", "check_method": "compare y"},
    {"uid": "TP-0002", "dimension": "D2", "stimulus": "hold reset",
     "expected_response": "y stays low", "check_method": "compare y"},
    {"uid": "TP-0003", "dimension": "D3", "stimulus": "sweep a",
     "expected_response": "y tracks a", "check_method": "compare y"},
]


def test_editor_chat_does_not_require_a_systemverilog_testbench():
    """The signature change that unblocks the loop, asserted at the seam."""
    from eda_agent.rtl_editor import RTLEditor

    params = inspect.signature(RTLEditor.chat).parameters
    assert "tb_text" in params, "chat() cannot be driven without a tb.sv on disk"
    assert params["tb_text"].default is None, "the SV path must keep its behaviour"


def test_describe_oracle_leads_with_the_reference_model(tmp_path):
    """The model is the expected behaviour, so it comes first and comes whole."""
    suite = _suite(tmp_path, failing=["TP-0001"])
    model = tmp_path / "ref_model.py"
    model.write_text("class Model:\n    OUTPUT_PORTS = ['y']\n", encoding="utf-8")

    text = describe_oracle(suite_dir=suite, refmodel_path=model, testplan=TESTPLAN)

    assert "NOT a SystemVerilog testbench" in text
    assert "OUTPUT_PORTS = ['y']" in text
    # only the failing testpoint's plan is included -- the passing ones are noise
    assert "TP-0001" in text
    assert "TP-0002" not in text and "TP-0003" not in text
    assert "drive a=1" in text


def test_describe_oracle_never_truncates_the_model_to_fit_the_testplan(tmp_path):
    """Half a specification is worse than none: the agent would infer the rest
    from the RTL, which is the direction this pipeline exists to prevent."""
    suite = _suite(tmp_path, failing=["TP-0001", "TP-0002", "TP-0003"])
    model = tmp_path / "ref_model.py"
    body = "\n".join(f"    def _req_{i:04d}(self, i, o): o['y'] = {i}" for i in range(200))
    model.write_text("class Model:\n" + body + "\n", encoding="utf-8")

    text = describe_oracle(
        suite_dir=suite, refmodel_path=model, testplan=TESTPLAN,
        max_chars=len("class Model:\n" + body) + 400,
    )
    assert "_req_0199" in text, "the model was truncated to make room for the testplan"


def test_describe_oracle_survives_a_missing_model(tmp_path):
    suite = _suite(tmp_path, failing=[])
    text = describe_oracle(suite_dir=suite, refmodel_path=tmp_path / "nope.py")
    assert "unreadable" in text


@pytest.mark.parametrize("name", ["tb_text", "tb_clip_chars"])
def test_specflow_node_passes_the_oracle_through(name):
    """The call site, not just the signature: the node must actually supply it."""
    source = (REPO / "eda_agent" / "specflow_node.py").read_text(encoding="utf-8")
    call = source[source.index("await editor.chat("):]
    call = call[: call.index("\n        )")]
    assert f"{name}=" in call, f"specflow_node does not pass {name} to editor.chat"


# ------------------------------------- what actually reaches the repair agent


def _records(uids_and_rows):
    return [
        {
            "testpoint": uid,
            "failed_checks": [f"CHK-{uid[-4:]}"],
            "failed_signals": sorted({r["signal"] for r in rows}),
            "mismatches": rows,
        }
        for uid, rows in uids_and_rows
    ]


def _row(signal, step, got=0, expected=1, **ctx):
    return {"check": "CHK-0001", "signal": signal, "step": step,
            "got": got, "expected": expected, "ctx": ctx or {"a": 1}}


def test_every_failing_testpoint_carries_a_concrete_value():
    """The budget is per testpoint, not global.

    A single global cap of 40 spent all 40 rows on the first failing testpoint.
    On i2c_master_bit_ctrl that left 21 of 22 reduced to a header, so the agent
    knew which outputs diverged and had no value for any of them.
    """
    from eda_agent.specflow_node import format_failures

    payload = _records(
        (f"TP-{i:04d}", [_row("y", s, a=s) for s in range(30)]) for i in range(22)
    )
    text = format_failures(payload)
    carrying = 0
    current = None
    for line in text.splitlines():
        if line.startswith("["):
            current = line
        elif "expected=" in line and current is not None:
            carrying += 1
            current = None
    assert carrying == 22, f"only {carrying} of 22 testpoints carry a value"
    assert "omitted" in text, "a truncated list must say it was truncated"


def test_a_check_yields_one_row_and_needs_no_collapsing():
    """The redundancy `_collapse` existed to fold is gone at the source.

    A check used to be evaluated once per stimulus vector, so a vector held for
    N cycles produced N byte-identical mismatch rows and `format_failures` had
    to fold them back into one with a step range. A check now asks one question
    about the whole run -- did the DUT produce the model's sequence of output
    states -- and so contributes at most one row. Nothing is left to collapse,
    and `_collapse`/`_steps` were retired with the redundancy.
    """
    from eda_agent import specflow_node
    from eda_agent.specflow_node import format_failures

    assert not hasattr(specflow_node, "_collapse")
    assert not hasattr(specflow_node, "_steps")

    text = format_failures(_records([("TP-0001", [_row("y", 7)])]))
    value_lines = [x for x in text.splitlines() if "expected=" in x]
    assert len(value_lines) == 1, value_lines


def test_the_divergence_is_located_by_state_not_by_cycle():
    """`@state7` and not `@step7`, because the two are different claims.

    Durations are deliberately not compared, so the temporal coordinate is the
    index of the first output state that differs -- not a cycle number and not a
    stimulus vector. Printing it as `@step` would invite the agent to look for
    vector 7, which on a design holding a vector for many cycles is somewhere
    else entirely. The stimulus in force at that state travels in the context as
    `vector=`.
    """
    from eda_agent.specflow_node import format_failures

    row = dict(_row("y", 7), ctx={"vector": 2, "a": 1})
    text = format_failures(_records([("TP-0001", [row])]))
    assert "@state7" in text and "@step7" not in text
    assert "vector=2" in text


def test_a_run_that_stopped_early_says_so_rather_than_naming_a_signal():
    """Truncation is not attributable to one output, so it reports its reason.

    When the DUT runs out of output states the values are `None` on one side and
    there is no diverging signal to name -- the line would read
    `expected=None got=None` and say nothing. The reason carries it instead.
    """
    from eda_agent.specflow_node import format_failures

    row = {
        "check": "CHK-0001", "signal": None, "signals": [], "step": 3,
        "got": None, "expected": {"y": 1}, "ctx": {"vector": 1},
        "reason": "the design stopped after 3 output state(s); the model expected 5",
        "timeouts": ["step 1: waited 2000 edges for cmd_ack==1 and it never happened"],
    }
    text = format_failures([{
        "testpoint": "TP-0001", "failed_checks": ["CHK-0001"],
        "failed_signals": [], "mismatches": [row],
    }])
    assert "the design stopped after 3 output state(s)" in text
    assert "timeout: step 1: waited 2000 edges" in text


def test_the_structured_payload_is_not_run_through_the_systemverilog_filter():
    """The regression that emptied the excerpt.

    `_summarize_sim_log_json` recognises a value row only if the line contains
    the literal word "mismatch"; specflow rows read "expected=1 got=0". With
    nothing recognised it falls back to the *last 40 lines* -- a rule written
    for a build transcript, where the useful part is at the bottom. A structured
    report puts the first failing testpoints at the top, so on the real
    i2c_master_bit_ctrl payload the debugger received 22 headers and zero
    concrete values.

    Sized to reproduce that: more than 40 lines, values not only at the end.
    """
    import json as _json

    from eda_agent.rtl_editor import _summarize_sim_log_json
    from eda_agent.specflow_node import format_failures

    payload = _records(
        (f"TP-{i:04d}", [_row("y", s, a=s) for s in range(4)]) for i in range(22)
    )
    stdout = format_failures(payload)
    assert len(stdout.splitlines()) > 40 and stdout.count("expected=") >= 22

    filtered = _summarize_sim_log_json(_json.dumps({"stdout": stdout, "stderr": ""}))
    assert filtered.count("expected=") < stdout.count("expected="), (
        "the SV path no longer loses rows; this guard can be retired"
    )
    assert "TP-0000" not in filtered, "the tail-40 fallback no longer drops the head"

    passed = _summarize_sim_log_json(
        _json.dumps({"format": "specflow", "stdout": stdout, "stderr": ""})
    )
    assert passed.count("expected=") == stdout.count("expected=")
    assert "TP-0000" in passed and "TP-0021" in passed


def test_the_runtime_records_which_step_diverged():
    """Two identical context dicts at different points in a stimulus sequence
    are two different situations on a stateful design."""
    from specflow.tb.runtime import Scoreboard

    sb = Scoreboard()
    sb.check("CHK-0001", 0, 1, {"a": 1}, signal="y", step=4)
    assert sb.mismatches[0]["step"] == 4
    assert sb.mismatches[0]["signal"] == "y"


def test_the_payload_leads_with_a_cross_testpoint_summary():
    """"Which output is wrong most often, and from which step" is the question a
    repair agent asks first, and it is answerable across the whole failure set
    rather than one testpoint at a time. It was answerable nowhere."""
    from eda_agent.specflow_node import format_failures

    payload = _records((f"TP-{i:04d}", [_row("sda_oen", 3 + i)]) for i in range(3))
    trace = {"fail_step": 3, "total_mismatches": 3,
             "failing_testpoints": ["TP-0000", "TP-0001", "TP-0002"],
             "fail_outputs": [{"sig": "sda_oen", "mismatches": 3}],
             "wave_vcd": "/runs/x/wave_0.vcd"}
    text = format_failures(payload, trace=trace)
    head = text.splitlines()[0]
    assert "3 mismatches across 3 testpoints" in head
    assert "first at stimulus step 3" in head
    assert "sda_oenx3" in head
    assert "WAVEFORM: /runs/x/wave_0.vcd" in text


def test_trace_summary_reads_the_records_rather_than_a_log(tmp_path):
    """`eda_agent.trace_report` derives fail_time and fail_outputs by parsing a
    SystemVerilog testbench's mismatch log. This backend has no such log -- it
    has a structured record per testpoint, which is strictly better -- but
    nothing read it, so every one of those fields reached the agent null or
    zero while the data sat on disk."""
    from specflow.integration import trace_summary

    suite = _suite(tmp_path, failing=["TP-0001", "TP-0003"])
    # give the records a signal and a step, as the runtime now does
    for uid in ("TP-0001", "TP-0003"):
        p = suite / "results" / f"{uid}.json"
        d = json.loads(p.read_text())
        d["mismatches"] = [
            {"check": "CHK-0001", "signal": "busy", "step": 9, "got": 1,
             "expected": 0, "ctx": {"a": 1}},
            {"check": "CHK-0001", "signal": "al", "step": 4, "got": 1,
             "expected": 0, "ctx": {"a": 1}},
        ]
        p.write_text(json.dumps(d), encoding="utf-8")

    tr = trace_summary(suite, tmp_path / "wave_0.vcd")
    assert tr["total_mismatches"] == 4
    assert tr["fail_step"] == 4, "the earliest failing step, not the first seen"
    assert tr["fail_outputs"] == [
        {"sig": "al", "mismatches": 2}, {"sig": "busy", "mismatches": 2}
    ] or tr["fail_outputs"] == [
        {"sig": "busy", "mismatches": 2}, {"sig": "al", "mismatches": 2}
    ]
    assert tr["wave_vcd"].endswith("wave_0.vcd")
    assert sorted(tr["failing_testpoints"]) == ["TP-0001", "TP-0003"]


# --------------------------- the per-requirement verdict the judge never carried


def _reviewer(tmp_path, oracles, contract):
    """A `SpecflowReviewer` with only what `_decide_requirements` reads."""
    from types import SimpleNamespace

    from eda_agent.specflow_node import SpecflowReviewer
    return SpecflowReviewer(
        built=SimpleNamespace(suite_dir=tmp_path, refmodel_path=None, bins=[]),
        hdl_toplevel="dut", output_dir=tmp_path,
        oracles=oracles, contract=contract)


def _write_trace(results_dir, tp_uid, busy_by_edge):
    import json as _json
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{tp_uid}.trace.json").write_text(_json.dumps({
        "tp_uid": tp_uid, "outputs": ["busy"],
        "edges": [{"edge": i, "step": 0, "inputs": {"cmd": 1},
                   "dut": {"busy": b}, "model": {"busy": b}}
                  for i, b in enumerate(busy_by_edge)]}), encoding="utf-8")


def test_the_reviewer_decides_the_frozen_oracles_on_the_recording(tmp_path):
    """THE LINK THAT WAS MISSING, end to end on the reviewer.

    `judge` answers per TESTPOINT and the debugger repairs per REQUIREMENT, and
    nothing joined them: `_EditSession.req_results` was read by `explain` and
    `list_failing_requirements` and written by no code path at all. Every input
    already existed -- `Env.finish` writes `{tp}.trace.json` unconditionally and
    the oracle set is frozen on disk -- so this is a join, not new evidence.
    """
    from specflow.refmodel.oracles import RequirementOracle
    src = ("def decide(trace):\n"
           "    return all(r['outputs']['busy'] == 0 for r in trace)\n")
    o = RequirementOracle(req_uid="REQ-0001", clause="busy stays low",
                          source=src, tp_uids=["TP-0000"])
    contract = {"io": [{"name": "busy", "dir": "output", "width": 1}]}
    _write_trace(tmp_path / "results", "TP-0000", [0, 1, 0])

    rev = _reviewer(tmp_path, [o], contract)
    got = rev._decide_requirements()
    result, trace = got["REQ-0001"]
    assert result.ok is False
    assert result.tp_uid == "TP-0000"
    # Paired with the trace it judged: `explain` reads simulator TIME out of it,
    # and an OracleResult.edge is a row index, not a timestamp.
    assert trace["tp_uid"] == "TP-0000"


def test_no_oracles_costs_the_requirement_surface_and_not_the_run(tmp_path):
    """A backend with no frozen set still returns its testpoint verdict.

    Degrading is the point: the per-requirement surface goes quiet, which is
    the state every run was in before this was wired, and the run continues.
    """
    assert _reviewer(tmp_path, [], {})._decide_requirements() == {}


def test_a_build_that_never_simulated_says_so_rather_than_going_silent(tmp_path):
    """No recording is an ABSTENTION that names the missing testpoint.

    Not an empty dict: an empty surface and a surface saying "TP-0000 produced
    no trace" are different facts, and the first one reads to the agent as
    "nothing is wrong".
    """
    from specflow.refmodel.oracles import RequirementOracle
    o = RequirementOracle(req_uid="REQ-0001", clause="c",
                          source="def decide(trace):\n    return True\n",
                          tp_uids=["TP-0000"])
    result, trace = _reviewer(tmp_path, [o], {})._decide_requirements()["REQ-0001"]
    assert result.ok is None
    assert "TP-0000 produced no trace" in result.detail
    assert trace == {}


def test_frozen_oracles_load_from_the_run_directory(tmp_path):
    """And a run with no `oracles.json` yields an empty list, never an error."""
    import json as _json

    from eda_agent.specflow_node import _frozen_oracles
    assert _frozen_oracles(tmp_path) == []
    (tmp_path / "specflow").mkdir()
    (tmp_path / "specflow" / "oracles.json").write_text(_json.dumps({"oracles": [
        {"req_uid": "REQ-0001", "clause": "c", "source": "def decide(t): ...",
         "tp_uids": ["TP-0000"]},
        {"req_uid": "REQ-0002"},  # malformed: no source, skipped not fatal
    ]}), encoding="utf-8")
    got = _frozen_oracles(tmp_path)
    assert [o.req_uid for o in got] == ["REQ-0001"]
    assert got[0].tp_uids == ["TP-0000"]


def test_the_reviewer_maps_each_testpoints_waveform(tmp_path):
    """`run_suite` writes `wave_{iteration}_{module}.vcd`, one per testpoint.

    Publishing the map is what lets `explain` show the waveform belonging to
    the testpoint that actually produced the conviction, rather than whichever
    one the session happened to hold.
    """
    (tmp_path / "wave_0_test_TP0007.vcd").write_text("$end\n")
    (tmp_path / "wave_0_test_TP0223.vcd").write_text("$end\n")
    (tmp_path / "wave_0_test_NOTATP.vcd").write_text("$end\n")
    rev = _reviewer(tmp_path, [], {})
    got = rev._waves_by_tp()
    assert set(got) == {"TP-0007", "TP-0223"}
    assert got["TP-0007"].name == "wave_0_test_TP0007.vcd"


def test_no_waveforms_is_an_empty_map_and_not_an_error(tmp_path):
    """A suite run with `trace=False` dumps nothing, which is a real state."""
    assert _reviewer(tmp_path, [], {})._waves_by_tp() == {}


def test_the_wave_map_prefers_the_LATEST_iteration_numerically(tmp_path):
    """Sorting names as strings puts "wave_10_" before "wave_2_".

    A tenth trial's waveform would then silently lose to the second's, and the
    agent would be shown a waveform eight commits out of date while every other
    field in `explain` described the current design.
    """
    for it in (0, 2, 10):
        (tmp_path / f"wave_{it}_test_TP0007.vcd").write_text("$end\n")
    got = _reviewer(tmp_path, [], {})._waves_by_tp()
    assert got["TP-0007"].name == "wave_10_test_TP0007.vcd"
