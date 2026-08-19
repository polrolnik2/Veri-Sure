"""M5: the renderer, G5, and the two-sided G6 control on real RTL.

The two-sided control is the point. Passing golden RTL proves the suite is not
over-constrained (no false FAIL); failing a tied-off DUT proves it is not
vacuous (no false PASS). Neither direction alone is sufficient, and the research
called the absence of the second the largest reporting gap in the field.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.model_io import ReplayPort
from specflow.refmodel.compose import run_refmodel, write_artifacts
from specflow.run import reconcile, run_suite
from specflow.s1_requirements import run_s1
from specflow.s2_testplan import run_s2
from specflow.s3_coverage import run_s3
from specflow.schema import has_errors
from specflow.tb.render import default_stimulus, gate_g5, render_suite

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "specflow" / "hadd"
DATASET = REPO / "benchmarks" / "verilogeval-v2-ext" / "dataset_spec-to-rtl"
GOLDEN = DATASET / "Prob024_hadd_ref.sv"

needs_verilator = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)


def build_suite(tmp_path: Path):
    """Run the whole chain off the recorded fixture and render the suite."""
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract_json = (run_dir / "contract.json").read_text(encoding="utf-8")
    contract = json.loads(contract_json)
    port = ReplayPort(root=run_dir / "agent_io")

    s1 = run_s1(spec=spec, contract_json=contract_json, port=port)
    reqs = [r.model_dump() for r in s1.output.requirements]
    s2 = run_s2(requirements=reqs, contract_json=contract_json, port=port)
    tps = [e.model_dump() for e in s2.output.elements]
    s3 = run_s3(testplan=tps, contract_json=contract_json, port=port)
    bins = [b.model_dump() for b in s3.output.bins]
    checks = [c.model_dump() for c in s3.output.checks]

    rm, source = run_refmodel(
        requirements=reqs, contract_json=contract_json, port=port,
        workdir=run_dir / "check",
    )
    assert rm.ok
    model_path = write_artifacts(run_dir, rm, source)

    suite = run_dir / "suite"
    manifest = render_suite(
        testplan=tps, bins=bins, checks=checks, contract=contract, out_dir=suite
    )
    return suite, manifest, bins, checks, model_path, contract


# ---------------------------------------------------------------- rendering


def test_one_module_per_testpoint(tmp_path):
    suite, manifest, _, _, _, _ = build_suite(tmp_path)
    assert len(manifest.modules) == len(manifest.testpoints) == 8
    for name in manifest.modules:
        assert (suite / "tests" / f"{name}.py").exists()


def test_rendered_testcase_contains_no_expected_value(tmp_path):
    """Expected values come from the reference model, never from the testcase.

    A testcase that hard-codes a number is an oracle that cannot notice a design
    change, so the renderer must never emit one.
    """
    suite, manifest, _, _, _, _ = build_suite(tmp_path)
    for name in manifest.modules:
        src = (suite / "tests" / f"{name}.py").read_text(encoding="utf-8")
        assert "env.expect(stim)" in src
        # The only literals are the stimulus and the UIDs.
        assert "expected =" in src and "expected = {" not in src


def test_g5_accepts_the_rendered_suite(tmp_path):
    suite, manifest, bins, checks, _, _ = build_suite(tmp_path)
    assert gate_g5(out_dir=suite, manifest=manifest, bins=bins, checks=checks) == []


def test_g5_catches_a_check_that_is_never_emitted(tmp_path):
    # A check in the model but not in the suite could never fail. This is the
    # vacuity guarantee made structural.
    suite, manifest, bins, checks, _, _ = build_suite(tmp_path)
    checks.append({"uid": "CHK-9999", "covers": [], "signals": ["sum"], "expr": "x"})
    issues = gate_g5(out_dir=suite, manifest=manifest, bins=bins, checks=checks)
    assert has_errors(issues)
    assert any("CHK-9999" in i.path for i in issues)


def test_g5_catches_a_missing_module(tmp_path):
    suite, manifest, bins, checks, _, _ = build_suite(tmp_path)
    (suite / "tests" / f"{manifest.modules[0]}.py").unlink()
    assert has_errors(gate_g5(out_dir=suite, manifest=manifest, bins=bins, checks=checks))


def test_default_stimulus_is_exhaustive_when_small():
    contract = {"io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
    ]}
    assert len(default_stimulus(contract)) == 4


def test_default_stimulus_falls_back_to_sampling_when_large():
    contract = {"io": [{"name": "x", "dir": "input", "width": 16}]}
    stim = default_stimulus(contract, limit=32)
    assert len(stim) == 32


# ------------------------------------------------- G6: the two-sided control


@needs_verilator
def test_suite_passes_golden_rtl(tmp_path):
    """Not over-constrained: a correct design must survive it."""
    suite, manifest, _, _, model_path, _ = build_suite(tmp_path)
    outcome = run_suite(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path,
    )
    assert outcome.build_ok, outcome.build_log
    assert outcome.failing == [], outcome.failing
    assert len(outcome.results) == len(manifest.testpoints)
    assert all(r.status == "PASS" for r in outcome.results.values())


@needs_verilator
def test_suite_fails_a_tied_off_dut(tmp_path):
    """Not vacuous: a suite that passes a known-bad design has dead checks."""
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    tied = tmp_path / "tied.sv"
    tied.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum = 1'b0;\n  assign cout = 1'b0;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    outcome = run_suite(
        rtl_path=tied, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path,
    )
    assert outcome.build_ok, outcome.build_log
    assert outcome.failing, "a tied-off DUT passed; the suite is vacuous"


@needs_verilator
def test_all_failing_scenarios_are_reported_in_one_run(tmp_path):
    """Every testpoint reports independently, and every mismatch inside one
    testpoint is recorded rather than dying on the first."""
    suite, manifest, _, _, model_path, _ = build_suite(tmp_path)
    broken = tmp_path / "broken.sv"
    # Two independent bugs: sum is ORed instead of XORed, cout is inverted.
    broken.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum  = a | b;\n  assign cout = ~(a & b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    outcome = run_suite(
        rtl_path=broken, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path,
    )
    assert outcome.build_ok, outcome.build_log

    # Every testpoint still produced a record despite earlier ones failing.
    assert len(outcome.results) == len(manifest.testpoints)
    assert reconcile(outcome, {"testpoints": manifest.testpoints}) == []

    # Both bugs are visible, not just the first one hit.
    signals = {
        m["check"] for r in outcome.results.values() for m in r.mismatches
    }
    assert len(signals) >= 2, f"only {signals} reported; failures are being masked"

    # And a single testpoint records more than one mismatch.
    assert any(len(r.mismatches) > 1 for r in outcome.results.values())


def test_expect_dispatches_on_what_the_model_implements():
    """A sequential model must be driven through `step`, not `evaluate`.

    `compose.choose_base` decides the entry point from the contract and the
    generated model implements exactly that one. The runtime used to re-derive
    the choice from `LATENCY_CYCLES > 1`, so a sequential model with latency 0
    or 1 -- which `choose_base` still routes to `step`, since it also keys on
    `clocking.is_sequential` and completion signals -- fell through to
    `evaluate`, which such a model does not define.

    The base class raised `NotImplementedError` and every testpoint crashed
    before writing a record: 23 of 23 on i2c_master_bit_ctrl. specflow's
    sequential path had never once run, and the whole test suite stayed green
    throughout, because the only fixture is a combinational half adder.
    """
    from specflow.refmodel.base import RefModel
    from specflow.tb.runtime import Env

    class Sequential(RefModel):
        OUTPUT_PORTS = ["q"]
        LATENCY_CYCLES = 0          # the value that used to route to evaluate
        def step(self, i):
            return {"q": i["d"]}

    class Combinational(RefModel):
        OUTPUT_PORTS = ["y"]
        def evaluate(self, i):
            return {"y": i["a"] ^ 1}

    env = Env(None, "TP-0001", None, "results")   # only `expect` is under test

    env.ref = Sequential()
    assert env.expect({"d": 1}) == {"q": 1}, "sequential model not driven via step"

    env.ref = Combinational()
    assert env.expect({"a": 1}) == {"y": 0}, "combinational model must still work"


@needs_verilator
def test_a_waveform_is_produced_for_the_repair_agent(tmp_path):
    """The single largest gap measured in what the repair agent receives.

    On the last run that reached the debugger, `trace_report` came back with
    `fail_time=None`, `fail_outputs=0`, `input_window=0` and
    `alignment_diagnosis=0` -- every field it derives from a waveform -- because
    this backend dumped none. The agent could see which testpoints failed and
    nothing whatever about when.

    Tracing is two-sided and both halves are required: `--trace` at compile time
    defines `VM_TRACE`, and the harness then looks for `--trace` in argv at run
    time before it opens a file. Passing it as a plusarg instead made the model
    exit with "Unknown runtime argument", which is the failure this pins.
    """
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    outcome = run_suite(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path,
    )
    assert outcome.build_ok, outcome.build_log
    assert outcome.wave_vcd is not None, "no waveform was produced"
    assert outcome.wave_vcd.exists() and outcome.wave_vcd.stat().st_size > 0
    assert "$var" in outcome.wave_vcd.read_text(errors="replace")[:20000], (
        "the dump exists but declares no signals"
    )


@needs_verilator
def test_tracing_can_be_turned_off(tmp_path):
    """It costs simulation time and disk on every repair iteration, so the
    switch has to work in both directions."""
    suite, _, _, _, model_path, _ = build_suite(tmp_path)
    outcome = run_suite(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=suite,
        refmodel_path=model_path, trace=False,
    )
    assert outcome.build_ok, outcome.build_log
    assert outcome.wave_vcd is None
