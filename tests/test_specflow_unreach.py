"""M7: formal discharge, both directions, on real SymbiYosys.

Both failure directions are loop-level and nearly undiagnosable from inside the
loop, which is why they are pinned here rather than discovered later:

* a **false discharge** silently shrinks the denominator and accepts unverified
  spec;
* a **missed discharge** makes G7 permanently unsatisfiable and the loop spins.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from specflow.unreach import (
    classify,
    discharge_all,
    discharge_bin,
    read_sby_status,
    render_cover_probe,
    write_sby,
)

needs_sby = pytest.mark.skipif(
    not (shutil.which("sby") and shutil.which("yosys")),
    reason="SymbiYosys not installed",
)

CONTRACT = {
    "module_name": "Gated",
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
        {"name": "never", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": False},
}

# `never` is tied low by construction, so a bin on `never == 1` is genuinely
# unreachable; a bin on `y == 1` plainly is not.
RTL = """\
module Gated (
  input  wire a,
  input  wire b,
  output wire y,
  output wire never
);
  assign y     = a & b;
  assign never = 1'b0;
endmodule
"""


@pytest.fixture
def rtl(tmp_path) -> Path:
    path = tmp_path / "gated.sv"
    path.write_text(RTL, encoding="utf-8")
    return path


# ---------------------------------------------------------------- pure parts


def test_classify_distinguishes_proof_from_witness():
    # PASS on the negated condition means the condition can never hold.
    assert classify("PASS", timed_out=False) == "unreachable"
    assert classify("FAIL", timed_out=False) == "reachable"


def test_a_timeout_is_never_a_proof():
    # A timeout proves nothing. Reading it as a proof would drop a reachable bin
    # from the denominator on the strength of a slow solver.
    assert classify("", timed_out=True) == "timeout"
    assert classify("PASS", timed_out=True) == "timeout"


def test_unknown_is_distinct_from_error():
    assert classify("UNKNOWN", timed_out=False) == "unknown"
    assert classify("ERROR", timed_out=False) == "error"


def test_only_a_proof_disposes():
    from specflow.unreach import Discharge

    assert Discharge("BIN-0", "unreachable").disposes
    for status in ("reachable", "unknown", "timeout", "error", "skip"):
        assert not Discharge("BIN-0", status).disposes


def test_sby_writer_is_parameterised(tmp_path):
    path = write_sby(
        tmp_path / "p.sby", sources=[tmp_path / "a.sv"], top="CoverProbe",
        depth=7, engine="smtbmc z3",
    )
    text = path.read_text()
    assert "depth 7" in text and "prep -top CoverProbe" in text and "a.sv" in text


def test_probe_asserts_the_negated_condition():
    src = render_cover_probe(dut_module="Gated", contract=CONTRACT, condition_sv="never == 1'b1")
    assert "assert (!(never == 1'b1))" in src
    assert "Gated dut" in src


def test_missing_status_file_is_not_a_verdict(tmp_path):
    assert read_sby_status(tmp_path / "absent") == ""
    assert classify("", timed_out=False) == "unknown"


def test_empty_condition_is_skipped_not_proved(tmp_path, rtl):
    d = discharge_bin(
        bin_uid="BIN-0", condition_sv="   ", rtl_path=rtl, dut_module="Gated",
        contract=CONTRACT, workdir=tmp_path / "w",
    )
    assert d.status == "skip" and not d.disposes


# ---------------------------------------------------------------- real proofs


@needs_sby
def test_an_unreachable_bin_is_discharged_with_a_proof(tmp_path, rtl):
    d = discharge_bin(
        bin_uid="BIN-0001", condition_sv="never == 1'b1", rtl_path=rtl,
        dut_module="Gated", contract=CONTRACT, workdir=tmp_path / "w",
    )
    assert d.status == "unreachable", d.reason
    assert d.disposes
    # The proof and its assumption set are recorded: an exclusion proved under a
    # wrong constraint environment is indistinguishable from a real one.
    assert d.proof_type == "k_induction"
    assert d.assumptions


@needs_sby
def test_a_reachable_bin_is_not_discharged(tmp_path, rtl):
    """The direction that matters most. A gate that discharges anything would
    quietly accept unverified spec."""
    d = discharge_bin(
        bin_uid="BIN-0000", condition_sv="y == 1'b1", rtl_path=rtl,
        dut_module="Gated", contract=CONTRACT, workdir=tmp_path / "w",
    )
    assert d.status == "reachable", d.reason
    assert not d.disposes


@needs_sby
def test_discharge_all_returns_only_proofs(tmp_path, rtl):
    out = tmp_path / "dispositions.json"
    disposed = discharge_all(
        uncovered=["BIN-0000", "BIN-0001"],
        conditions={"BIN-0000": "y == 1'b1", "BIN-0001": "never == 1'b1"},
        rtl_path=rtl, dut_module="Gated", contract=CONTRACT,
        workdir=tmp_path / "w", out_path=out,
    )
    assert set(disposed) == {"BIN-0001"}
    # Every attempt is recorded, including the ones that did not dispose, so a
    # missed discharge is visible rather than silent.
    assert out.exists()
    assert "BIN-0000" in out.read_text()


@needs_sby
def test_a_discharged_bin_stops_blocking_the_gate(tmp_path, rtl):
    """End to end: discharge feeds G7 and turns EXTEND_TB into ACCEPT."""
    from specflow.coverage import build_report
    from specflow.gate import evaluate
    from specflow.schema import TestpointResult

    results = {
        "TP-0000": TestpointResult(
            tp_uid="TP-0000", status="PASS", checks_invoked=("CHK-0",),
            bins_hit=("BIN-0000",),
        )
    }
    denom = ["BIN-0000", "BIN-0001"]

    before = evaluate(results=results, report=build_report(denominator=denom, results=results))
    assert before.outcome == "EXTEND_TB"

    disposed = discharge_all(
        uncovered=["BIN-0001"], conditions={"BIN-0001": "never == 1'b1"},
        rtl_path=rtl, dut_module="Gated", contract=CONTRACT, workdir=tmp_path / "w",
    )
    after = evaluate(
        results=results,
        report=build_report(denominator=denom, results=results, dispositions=disposed),
    )
    assert after.outcome == "ACCEPT"
