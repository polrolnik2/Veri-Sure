"""M9: the bridge into eda_agent's node-level run.

Everything here is a pure function of a run directory plus a model port, so the
integration is testable without the orchestrator -- which matters because the
orchestrator that drives composition nodes is not vendored in this repository.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.integration import (
    build_artifacts,
    ensure_prompt_file,
    failure_payload,
    judge,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "specflow" / "hadd"
GOLDEN = (
    REPO / "benchmarks" / "verilogeval-v2-ext" / "dataset_spec-to-rtl"
    / "Prob024_hadd_ref.sv"
)

needs_verilator = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    return run_dir


def _build(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    return run_dir, build_artifacts(
        run_dir=run_dir,
        spec=(run_dir / "prompt.txt").read_text(encoding="utf-8"),
        contract_json=(run_dir / "contract.json").read_text(encoding="utf-8"),
        model_port="replay",
    )


# ---------------------------------------------------------------- spec file


def test_prompt_file_is_written_for_the_benchmark_path(tmp_path):
    # cli.py writes prompt.txt; run_verilog_eval_v2.py never did, so a benchmark
    # node had no spec on disk for specflow (or any replay) to read.
    run_dir = tmp_path / "run"
    path = ensure_prompt_file(run_dir, "the spec text")
    assert path.read_text(encoding="utf-8") == "the spec text\n"


def test_existing_prompt_file_is_not_clobbered(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "prompt.txt").write_text("original\n", encoding="utf-8")
    assert ensure_prompt_file(run_dir, "different").read_text() == "original\n"


# ---------------------------------------------------------------- build


def test_all_artifacts_build_from_the_recorded_fixture(tmp_path):
    run_dir, result = _build(tmp_path)
    assert result.ok, result.reason

    out = run_dir / "specflow"
    for name in ("requirements", "testplan", "coverage_model"):
        assert (out / f"{name}.json").exists()
    assert (out / "ref_model.py").exists()
    assert (out / "suite" / "manifest.json").exists()


def test_a_failing_gate_stops_the_chain_and_names_the_stage(tmp_path):
    """Exhaustion is a hard failure: a stage that could not be certified must
    not propagate a partial artifact downstream."""
    run_dir = _run_dir(tmp_path)
    # Corrupt S2's recorded reply so G2 cannot pass.
    (run_dir / "agent_io" / "s2_r0_response.txt").write_text(
        json.dumps({"reasoning": "r", "elements": []}), encoding="utf-8"
    )
    result = build_artifacts(
        run_dir=run_dir,
        spec=(run_dir / "prompt.txt").read_text(encoding="utf-8"),
        contract_json=(run_dir / "contract.json").read_text(encoding="utf-8"),
        model_port="replay",
        max_repairs=0,
    )
    assert not result.ok
    assert result.stage == "S2"
    assert "S2 gate failed" in result.reason
    # The downstream artifacts must not exist.
    assert not (run_dir / "specflow" / "coverage_model.json").exists()


# ---------------------------------------------------------------- judge


@needs_verilator
def test_judge_accepts_a_correct_design(tmp_path):
    run_dir, built = _build(tmp_path)
    assert built.ok, built.reason

    verdict, detail = judge(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=built.suite_dir,
        refmodel_path=built.refmodel_path, bins=built.bins,
    )
    assert verdict.outcome == "ACCEPT", verdict.reason
    assert detail["build_ok"]
    assert all(s == "PASS" for s in detail["results"].values())


@needs_verilator
def test_judge_is_three_valued_not_two(tmp_path):
    """The replacement for sim_review's bool.

    `is_pass=True, mismatch_cnt=0` today means both "everything was checked and
    passed" and "nothing ran". Here every testpoint carries its own status.
    """
    run_dir, built = _build(tmp_path)
    verdict, detail = judge(
        rtl_path=GOLDEN, hdl_toplevel="RefModule", suite_dir=built.suite_dir,
        refmodel_path=built.refmodel_path, bins=built.bins,
    )
    assert set(detail["results"].values()) <= {"PASS", "FAIL", "NOT_EXERCISED"}
    assert len(detail["results"]) == 8


@needs_verilator
def test_failure_payload_carries_values_and_stimulus(tmp_path):
    """What the repair agent receives instead of a scraped log.

    rtl_editor gets a keyword-filtered log excerpt today, and the recorded
    failure of that approach was 210 MISMATCH lines carrying two actual values.
    """
    run_dir, built = _build(tmp_path)
    broken = tmp_path / "broken.sv"
    broken.write_text(
        "module RefModule(input a, input b, output sum, output cout);\n"
        "  assign sum = a | b;\n  assign cout = a & b;\nendmodule\n",
        encoding="utf-8",
    )
    verdict, _ = judge(
        rtl_path=broken, hdl_toplevel="RefModule", suite_dir=built.suite_dir,
        refmodel_path=built.refmodel_path, bins=built.bins,
    )
    assert verdict.outcome == "REPAIR_RTL"

    payload = failure_payload(built.suite_dir)
    assert payload, "a failing run produced no payload"
    for entry in payload:
        assert entry["failed_checks"]
        for m in entry["mismatches"]:
            # Every mismatch is self-describing: which check, what was expected,
            # what was seen, and the stimulus that produced it.
            assert {"check", "got", "expected", "ctx"} <= set(m)
            assert m["ctx"], "a mismatch with no stimulus is not actionable"

    # Every failing testpoint is present, not just the first one hit.
    assert len(payload) == len(verdict.failing)


@needs_verilator
def test_build_error_is_reported_as_such(tmp_path):
    run_dir, built = _build(tmp_path)
    bad = tmp_path / "bad.sv"
    bad.write_text("module RefModule( not verilog\n", encoding="utf-8")
    verdict, detail = judge(
        rtl_path=bad, hdl_toplevel="RefModule", suite_dir=built.suite_dir,
        refmodel_path=built.refmodel_path, bins=built.bins,
    )
    assert not detail["build_ok"]
    assert "build failed" in verdict.reason
    # Crucially NOT attributed to any testpoint.
    assert verdict.failing == ()


def test_top_agent_config_exposes_the_backend_switch():
    """The flip to specflow must be a config change, not a code change."""
    from eda_agent.top_agent import TopAgentConfig

    assert TopAgentConfig().tb_backend == "sv"
    assert TopAgentConfig(tb_backend="specflow").tb_backend == "specflow"
