"""Telemetry extraction: the columns, and the two ways a table can lie.

A spreadsheet is where a number goes to lose its provenance. Both failure modes
this pins have already happened here: a figure rendered as 0 when it was never
measured, and two runs compared across a difference no column recorded.
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "benchmarks"))

import telemetry  # noqa: E402


def _meta(usage, model="gpt-5-mini", effort="medium"):
    return {"served_model": model, "continuations": 0,
            "generate_kwargs": {"reasoning": {"effort": effort}},
            "usage": usage}


def _run(tmp_path, name="t-i2c"):
    run = tmp_path / name
    (run / "agent_io").mkdir(parents=True)
    (run / "specflow").mkdir(parents=True)
    return run


def _write(p, obj):
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_an_absent_artifact_leaves_the_cell_EMPTY_not_zero(tmp_path):
    """THE FIRST WAY A TABLE LIES, and this project has done it.

    "not measured" and "measured as zero" are different findings. A cache rate
    of 0% means the cache is not working; an empty cell means nobody looked.
    Rendering the second as the first is how a stage that was never
    instrumented gets reported as a stage that failed.
    """
    run = _run(tmp_path)
    row = telemetry.row_for(run, pathlib.Path("."))
    for col in ("cache_hit_pct", "trusted", "golden_pass", "syntax_pass",
                "functional_pass", "debug_cached", "adequate"):
        assert row[col] == "", f"{col} should be empty, got {row[col]!r}"


def test_a_debug_loop_without_the_third_counter_reports_no_rate(tmp_path):
    """The specific case: `debug_tokens` predating the cached counter has no
    `cached` key at all. Writing 0 there would claim a measured 0% cache rate
    on the largest line in the ledger -- 46.1M input tokens on a2-i2c."""
    run = _run(tmp_path)
    (run / "specflow" / "judge" / "r0").mkdir(parents=True)
    _write(run / "specflow" / "judge" / "r0" / "trust.json",
           {"debug_tokens": {"input": 10723949, "output": 53131}})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["debug_input"] == 10723949
    assert row["debug_cached"] == "", "an absent counter is not a zero one"
    assert row["debug_cache_hit_pct"] == ""

    # And with the counter present, the rate IS computed.
    _write(run / "specflow" / "judge" / "r0" / "trust.json",
           {"debug_tokens": {"input": 1000, "cached": 400, "output": 50}})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["debug_cached"] == 400 and row["debug_cache_hit_pct"] == 40.0


def test_the_two_models_are_separate_columns(tmp_path):
    """THE SECOND WAY A TABLE LIES: a confound with no column.

    `--full-strength-stages` defaults to refmodel,witness, so a run genuinely
    uses two models. One column holding "gpt-5-mini,gpt-5.6-luna" cannot be
    compared against another run's, which is the entire job of the column.
    """
    run = _run(tmp_path)
    io = run / "agent_io"
    _write(io / "normalize_REQ-0001_r0_meta.json",
           _meta({"input_tokens": 2000, "input_tokens_details": {"cached_tokens": 1000},
                  "output_tokens": 100}))
    _write(io / "refmodel_r0_meta.json",
           _meta({"input_tokens": 5000, "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens": 900}, model="gpt-5.6-luna", effort="xhigh"))
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["small_model"] == "gpt-5-mini" and row["small_effort"] == "medium"
    assert row["big_model"] == "gpt-5.6-luna" and row["big_effort"] == "xhigh"
    assert row["calls"] == 2 and row["input_tokens"] == 7000
    assert row["cache_hit_pct"] == round(100 * 1000 / 7000, 1)


def test_syntax_and_functional_come_from_their_own_artifacts(tmp_path):
    """The pair a paper reports, and `flow` beside them because for most tasks
    the functional verdict is an EQUIVALENCE result, not a testbench pass
    rate."""
    run = _run(tmp_path)
    _write(run / "baseline.json", {"rtl_bytes": 6222,
                                   "compile_gate": {"status": "pass"}})
    _write(run / "score.json", {"status": "function_fail", "flow": "equivalence",
                                "proof_type": "bounded_seq",
                                "compile_gate_status": "pass",
                                "reason": "mismatch at cycle 12"})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["syntax_pass"] == "pass" and row["produced_rtl"] == "yes"
    assert row["functional_pass"] == "no" and row["verdict"] == "function_fail"
    assert row["flow"] == "equivalence" and row["proof_type"] == "bounded_seq"


def test_no_rtl_at_all_is_not_the_same_as_rtl_that_will_not_compile(tmp_path):
    """Collapsing them loses the difference between 'the pipeline made nothing'
    and 'the pipeline made something wrong' -- and the first is the shape a
    transport failure takes while still exiting 0."""
    run = _run(tmp_path)
    _write(run / "baseline.json",
           {"compile_gate": {"status": "fail",
                             "reason": "no candidate RTL was produced"}})
    (run / "leaf_exception.txt").write_text("429 BUDGET_EXCEEDED", encoding="utf-8")
    (run / "done").write_text("0\n", encoding="utf-8")
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["produced_rtl"] == "no" and row["syntax_pass"] == "fail"
    # The tell the exit code does not give: done_rc is 0 on a total failure.
    assert row["done_rc"] == "0" and row["leaf_exception"] == "yes"


def test_a_timeout_is_not_a_functional_failure(tmp_path):
    """`score_chipverilog` excludes solver timeouts from function_fail for the
    reason its own comment gives -- a timeout proves nothing about the
    candidate. The column stays empty rather than convicting."""
    run = _run(tmp_path)
    _write(run / "score.json", {"status": "timeout", "reason": "exceeded 2400s"})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["verdict"] == "timeout" and row["functional_pass"] == ""


def test_rerunning_a_run_REPLACES_its_row(tmp_path):
    """Telemetry is taken while a run is still going, so the same run is
    extracted repeatedly. Appending would leave several rows for one run and no
    way to tell which is current."""
    run = _run(tmp_path)
    out = tmp_path / "telemetry.csv"
    telemetry.main(["--run", str(run), "--csv", str(out)])
    _write(run / "score.json", {"status": "pass"})
    telemetry.main(["--run", str(run), "--csv", str(out)])
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1, "one row per run, not one per extraction"
    assert rows[0]["functional_pass"] == "yes"


def test_the_miss_is_self_tb_pass_crossed_with_a_golden_fail(tmp_path):
    """THE NUMBER THE MISS RATE IS BUILT ON.

    `self_tb_pass` is the pipeline's verdict on its own testbench and
    `functional_pass` is the held-out verifier's. Neither alone says anything
    about the other: a run reporting only the first reports its own opinion of
    itself, which is exactly the inert-testbench failure the project exists to
    prevent. The cross is what makes the failure countable.
    """
    def _row(sim, status):
        run = _run(tmp_path, f"t-{sim}-{status}")
        # `rtl_bytes` is not decoration: a self-TB verdict only exists if
        # there was RTL to run it against, and the extractor gates on it.
        _write(run / "baseline.json", {"is_sim_pass": sim, "rtl_bytes": 6222,
                                       "compile_gate": {"status": "pass"}})
        _write(run / "score.json", {"status": status})
        return telemetry.row_for(run, pathlib.Path("."))

    assert _row(True, "function_fail")["tb_agreement"] == "miss"
    assert _row(True, "pass")["tb_agreement"] == "agree_pass"
    assert _row(False, "function_fail")["tb_agreement"] == "agree_fail"
    # The opposite error keeps its own name: a self-TB stricter than the
    # verifier costs a good design rather than passing a bad one.
    assert _row(False, "pass")["tb_agreement"] == "self_tb_over_strict"


def test_a_run_that_never_simulated_is_not_a_self_tb_failure(tmp_path):
    """"did not pass" and "was never asked" are different, and only the first
    belongs in a miss rate's denominator."""
    run = _run(tmp_path)
    _write(run / "baseline.json", {"compile_gate": {"status": "fail"}})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["self_tb_pass"] == "" and row["tb_agreement"] == ""


def test_arm_a_records_its_cost_in_baseline_not_agent_io(tmp_path):
    """Arm A writes no agent_io/ -- per-call recording is a specflow port
    feature and arm A is the specflow-deleted tree. Left unhandled, every arm A
    cost cell is blank beside a populated arm B row, which reads as "cost 0" in
    the one comparison the two arms exist for."""
    run = _run(tmp_path)
    _write(run / "baseline.json",
           {"model": "gpt-5.6-luna", "reasoning_effort": "xhigh",
            "is_sim_pass": True, "rtl_bytes": 6222,
            "compile_gate": {"status": "pass"},
            "tokens": {"eda_agent_input": 62437, "eda_agent_output": 56352}})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["input_tokens"] == 62437 and row["output_tokens"] == 56352
    assert row["small_model"] == "gpt-5.6-luna"
    # Arm A's ledger has no cached field; that is absence, not a measured zero.
    assert row["cached_tokens"] == "" and row["cache_hit_pct"] == ""


def test_a_run_killed_before_simulating_has_NO_self_tb_verdict(tmp_path):
    """`is_sim_pass` is present even when the self-TB never ran: the leaf
    handler sets it False on ANY exception. So a run killed in transport
    records "the self-TB failed", and that would enter a miss rate's
    denominator as a genuine failure.

    Live: a-fpu_exceptions-2 died on openai.APIConnectionError after the
    architect call, produced no rtl.sv, and logged self_tb_pass=no.
    """
    run = _run(tmp_path)
    _write(run / "baseline.json",
           {"is_sim_pass": False, "rtl_bytes": 0,
            "compile_gate": {"status": "fail",
                             "reason": "no candidate RTL was produced"}})
    (run / "leaf_exception.txt").write_text("APIConnectionError", encoding="utf-8")
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["self_tb_pass"] == "", "nothing was simulated, so there is no verdict"
    assert row["tb_agreement"] == ""
    assert row["produced_rtl"] == "no" and row["leaf_exception"] == "yes"


def test_a_real_self_tb_failure_on_real_rtl_still_reads_no(tmp_path):
    """The counter-case, so the guard above cannot swallow a genuine failure."""
    run = _run(tmp_path)
    _write(run / "baseline.json",
           {"is_sim_pass": False, "rtl_bytes": 4210,
            "compile_gate": {"status": "pass"}})
    _write(run / "score.json", {"status": "pass"})
    row = telemetry.row_for(run, pathlib.Path("."))
    assert row["self_tb_pass"] == "no"
    assert row["tb_agreement"] == "self_tb_over_strict"
