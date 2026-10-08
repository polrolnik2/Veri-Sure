"""M8: the hard-gated loop, including the two rigged cases that gate M9.

M9 deletes the SystemVerilog fallback, so the replacement must be shown to
converge on *both* loop outcomes: a fixable bug and an unfixable gap. A system
that handles only the first hangs on the second, and by then there is nothing to
fall back to.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.loop import run_loop
from specflow.testcase_agent import append_testcase, gate as tc_gate
from specflow.testcase_agent import parse_response as tc_parse

from .test_specflow_render import DATASET, GOLDEN, build_suite  # noqa: F401

needs_verilator = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)

CONTRACT = {
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
    ]
}


def _bins(suite_dir: Path) -> list[dict]:
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))
    return [{"uid": u} for u in manifest["bins"]]


# ---------------------------------------------------------- testcase agent


def test_agent_supplies_stimulus_not_code():
    spec = tc_parse(json.dumps({
        "reasoning": "r", "targets": ["BIN-0000"],
        "stimulus_steps": [{"a": 1, "b": 1}], "notes": "n",
    }))
    assert tc_gate(spec, bin_uid="BIN-0000", contract=CONTRACT,
                   uncovered={"BIN-0000"}) == []


def test_a_value_that_does_not_fit_its_port_blocks():
    spec = tc_parse(json.dumps({
        "targets": ["BIN-0000"], "stimulus_steps": [{"a": 7, "b": 0}],
    }))
    issues = tc_gate(spec, bin_uid="BIN-0000", contract=CONTRACT,
                     uncovered={"BIN-0000"})
    assert any("does not fit" in i.message for i in issues)


def test_an_undriven_input_blocks():
    spec = tc_parse(json.dumps({
        "targets": ["BIN-0000"], "stimulus_steps": [{"a": 1}],
    }))
    issues = tc_gate(spec, bin_uid="BIN-0000", contract=CONTRACT,
                     uncovered={"BIN-0000"})
    assert any("does not drive" in i.message for i in issues)


def test_the_tool_cannot_invent_a_target():
    """Monotonicity: the bin must already be uncovered in the gate's own report,
    so the agent cannot aim this at something to make its life easier."""
    spec = tc_parse(json.dumps({
        "targets": ["BIN-9999"], "stimulus_steps": [{"a": 1, "b": 1}],
    }))
    issues = tc_gate(spec, bin_uid="BIN-9999", contract=CONTRACT,
                     uncovered={"BIN-0000"})
    assert any("not currently reported uncovered" in i.message for i in issues)


def test_an_output_port_cannot_be_driven():
    spec = tc_parse(json.dumps({
        "targets": ["BIN-0000"], "stimulus_steps": [{"a": 1, "b": 1, "sum": 0}],
    }))
    issues = tc_gate(spec, bin_uid="BIN-0000", contract=CONTRACT,
                     uncovered={"BIN-0000"})
    assert any("not an input port" in i.message for i in issues)


def test_appended_testcases_are_frozen_and_never_rewritten(tmp_path):
    path = tmp_path / "testcases.json"
    append_testcase(testcases_path=path, uid="TC-0000", targets=["BIN-0"], module="m0")
    rows = append_testcase(
        testcases_path=path, uid="TC-0001", targets=["BIN-1"], module="m1"
    )
    assert [r["uid"] for r in rows] == ["TC-0000", "TC-0001"]
    assert all(r["frozen"] for r in rows)


def test_unparseable_agent_output_blocks():
    spec = tc_parse("no json here")
    assert tc_gate(spec, bin_uid="BIN-0", contract=CONTRACT, uncovered={"BIN-0"})


# ---------------------------------------------------------------- the loop


@needs_verilator
def test_loop_accepts_a_correct_design_immediately(tmp_path):
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    outcome = run_loop(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, bins=_bins(suite),
    )
    assert outcome.accepted, outcome.history
    assert outcome.iterations == 1


@needs_verilator
def test_rigged_bug_is_found_and_fixed(tmp_path):
    """One of the two outcomes M9 depends on: a fixable bug converges."""
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    broken = tmp_path / "dut.sv"
    broken.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum = a | b;\n  assign cout = a & b;\nendmodule\n",
        encoding="utf-8",
    )
    repairs: list[int] = []

    def repair(*, failing, results, iteration):
        repairs.append(iteration)
        broken.write_text(GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
        return True

    outcome = run_loop(
        rtl_path=broken, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, bins=_bins(suite), repair_rtl=repair,
    )
    assert outcome.accepted, outcome.history
    assert repairs == [0], "the loop should have repaired exactly once"


@needs_verilator
def test_rigged_stall_terminates_rather_than_spinning(tmp_path):
    """The other outcome: an unfixable gap must STALL within budget.

    A hard gate every iteration is the variant most likely to spin, so this is
    the test that decides whether the loop can be trusted without a fallback.
    """
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    broken = tmp_path / "dut.sv"
    broken.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum = a | b;\n  assign cout = a & b;\nendmodule\n",
        encoding="utf-8",
    )
    attempts: list[int] = []

    def useless_repair(*, failing, results, iteration):
        attempts.append(iteration)
        return True  # claims progress, changes nothing

    outcome = run_loop(
        rtl_path=broken, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, bins=_bins(suite),
        repair_rtl=useless_repair, max_iterations=8, stall_patience=2,
    )
    assert not outcome.accepted
    assert outcome.verdict.outcome == "STALLED"
    # It must give up well inside the budget rather than exhausting it.
    assert outcome.iterations < 8, outcome.history


@needs_verilator
def test_a_repair_that_reports_no_change_stops_the_loop(tmp_path):
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    broken = tmp_path / "dut.sv"
    broken.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum = a | b;\n  assign cout = a & b;\nendmodule\n",
        encoding="utf-8",
    )
    outcome = run_loop(
        rtl_path=broken, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, bins=_bins(suite),
        repair_rtl=lambda **kw: False,
    )
    assert outcome.verdict.outcome == "STALLED"
    assert outcome.iterations == 1


@needs_verilator
def test_build_failure_does_not_read_as_a_design_failure(tmp_path):
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    bad = tmp_path / "bad.sv"
    bad.write_text("module RefModule( this is not verilog\n", encoding="utf-8")
    outcome = run_loop(
        rtl_path=bad, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, bins=_bins(suite), repair_rtl=lambda **kw: False,
    )
    assert not outcome.accepted
    assert "build failed" in outcome.history[0]
