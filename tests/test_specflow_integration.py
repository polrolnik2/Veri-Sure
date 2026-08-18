"""M9: the bridge into eda_agent's node-level run.

Everything here is a pure function of a run directory plus a model port, so the
integration is testable without the orchestrator -- which matters because the
orchestrator that drives composition nodes is not vendored in this repository.
"""

from __future__ import annotations

import json
import os
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


def test_specflow_is_the_default_backend():
    """The SystemVerilog testbench path is retired: specflow is what runs."""
    from eda_agent.top_agent import TopAgentConfig

    assert TopAgentConfig().tb_backend == "specflow"
    assert TopAgentConfig().specflow_model_port == "file"


def test_top_agent_no_longer_depends_on_tb_generator():
    """The retired module must not be reachable from an import of top_agent.

    Its import is local to `_run_instance`, so `tb_generator.py` is dead code and
    deleting the file cannot break this module.
    """
    import ast
    from pathlib import Path

    src = Path("eda_agent/top_agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.iter_child_nodes(tree):  # module scope only
        if isinstance(node, ast.ImportFrom):
            assert "tb_generator" not in (node.module or "")
        elif isinstance(node, ast.Import):
            assert all("tb_generator" not in a.name for a in node.names)


def test_the_testbench_prompt_corpus_is_gone():
    """TB_4_SHOT_EXAMPLES taught the defects the harness then compensated for --
    no [TEST] markers and one global first_mismatch_time across all four
    examples. It has no place on a backend that emits checks from a model."""
    import eda_agent.prompts as prompts

    assert not hasattr(prompts, "TB_4_SHOT_EXAMPLES")
    assert not hasattr(prompts, "GLUE_TB_EXAMPLE")
    # Still shared with rtl_generator, so it stays.
    assert hasattr(prompts, "FAILED_TRIAL_PROMPT")


def test_specflow_node_reviewer_matches_the_simreviewer_shape():
    """RTLEditor is parameterised on a reviewer, so the adapter is the seam that
    lets the editor keep working with a different oracle underneath it."""
    import inspect

    from eda_agent.sim_reviewer import SimReviewer
    from eda_agent.specflow_node import SpecflowReviewer

    assert hasattr(SpecflowReviewer, "review")
    assert (
        inspect.signature(SpecflowReviewer.review).return_annotation
        == inspect.signature(SimReviewer.review).return_annotation
    )


@needs_verilator
def test_the_suite_runs_outside_pytest(tmp_path):
    """The suite must run when nothing has arranged `sys.path` for it.

    This is the difference between "tested" and "has been run". cocotb sets the
    simulator subprocess's `PYTHONPATH` from the *parent's* `sys.path`
    (`cocotb_tools/runner.py:248`), discarding anything passed via `extra_env`.

    The trap is that `sys.path` can carry *relative* entries. A plain
    `python -c` puts `''` on it, which resolves to the parent's cwd -- the
    repository -- so `import specflow` succeeds in the parent. cocotb then
    passes that same `''` down, where it resolves to the *simulator's* cwd,
    which is the test directory. The generated `ref_model.py` does
    `from specflow.refmodel.base import RefModel` and dies with
    `ModuleNotFoundError: No module named 'specflow'`.

    Under pytest this never happens: pytest puts an absolute rootdir on
    `sys.path`, so every test here passed while a production node would have
    failed. Hence a subprocess with cwd set and no absolute path entry -- the
    exact shape that breaks. Verified to fail when `_ensure_importable` is
    disabled.
    """
    import subprocess
    import sys
    import textwrap

    run_dir = _run_dir(tmp_path)
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from specflow.integration import build_artifacts, judge
        run = Path({str(run_dir)!r})
        built = build_artifacts(
            run_dir=run, spec=(run / "prompt.txt").read_text(),
            contract_json=(run / "contract.json").read_text(), model_port="replay")
        assert built.ok, built.reason
        verdict, _ = judge(
            rtl_path=Path({str(GOLDEN)!r}), hdl_toplevel="RefModule",
            suite_dir=built.suite_dir, refmodel_path=built.refmodel_path,
            bins=built.bins)
        print("VERDICT:" + verdict.outcome)
        """
    )
    # cwd=REPO so `import specflow` resolves through the relative '' entry, which
    # is exactly the entry that means something different in the child.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO, env=env,
        capture_output=True, text=True,
    )
    assert "VERDICT:ACCEPT" in proc.stdout, (
        f"suite did not run outside pytest\nstdout:\n{proc.stdout[-2000:]}"
        f"\nstderr:\n{proc.stderr[-2000:]}"
    )
