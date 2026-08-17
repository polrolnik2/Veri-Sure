"""M6: all four G7 verdicts, on fixtures, with no simulator.

The loop is driven entirely by this verdict, so a wrong one makes the loop do the
wrong thing indefinitely. Because the gate is pure, every branch costs three JSON
fixtures to test -- so there is no excuse for not testing all of them before an
agent is attached and the signal gets muddied.
"""

from __future__ import annotations

import json

from specflow.coverage import (
    CHECK_FAILED,
    NO_TESTCASE,
    STIMULUS_GAP,
    UNREACHABLE_PROVED,
    build_report,
    freeze_denominator,
    parse_lcov_info,
)
from specflow.gate import StallTracker, evaluate
from specflow.schema import TestpointResult

BINS = [{"uid": "BIN-0000"}, {"uid": "BIN-0001"}]
DENOM = ["BIN-0000", "BIN-0001"]


def res(uid, status, bins=(), failed=()):
    return TestpointResult(
        tp_uid=uid, status=status, bins_hit=tuple(bins),
        checks_invoked=("CHK-0",), checks_failed=tuple(failed),
    )


def report(results, dispositions=None, testcases=None):
    return build_report(
        denominator=DENOM, results=results,
        dispositions=dispositions, testcases=testcases,
    )


# ---------------------------------------------------------------- verdicts


def test_accept_when_everything_passes_and_is_covered():
    results = {
        "TP-0000": res("TP-0000", "PASS", ["BIN-0000"]),
        "TP-0001": res("TP-0001", "PASS", ["BIN-0001"]),
    }
    v = evaluate(results=results, report=report(results))
    assert v.outcome == "ACCEPT"


def test_repair_rtl_when_a_check_fails():
    results = {
        "TP-0000": res("TP-0000", "FAIL", ["BIN-0000"], ["CHK-0"]),
        "TP-0001": res("TP-0001", "PASS", ["BIN-0001"]),
    }
    v = evaluate(results=results, report=report(results))
    assert v.outcome == "REPAIR_RTL"
    assert v.failing == ("TP-0000",)


def test_extend_tb_when_a_bin_is_uncovered():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    v = evaluate(results=results, report=report(results))
    assert v.outcome == "EXTEND_TB"


def test_stalled_when_no_progress_is_being_made():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    v = evaluate(results=results, report=report(results), stalled=True)
    assert v.outcome == "STALLED"


def test_build_failure_is_not_a_testpoint_failure():
    # Reporting a Verilator lowering error as a design failure is what sends the
    # repair agent after the wrong artifact.
    v = evaluate(results={}, report=report({}), build_ok=False, build_log="%Error: ...")
    assert v.outcome == "REPAIR_RTL"
    assert "build failed" in v.reason
    assert v.failing == ()


def test_failing_takes_precedence_over_uncovered():
    results = {"TP-0000": res("TP-0000", "FAIL", ["BIN-0000"], ["CHK-0"])}
    assert evaluate(results=results, report=report(results)).outcome == "REPAIR_RTL"


def test_a_disposed_bin_does_not_block_acceptance():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    rep = report(results, dispositions={"BIN-0001": {"status": "unreachable", "proof": "p"}})
    assert evaluate(results=results, report=rep).outcome == "ACCEPT"


def test_a_crashed_testpoint_does_not_vanish():
    """G6b. A record that never appeared must not read as covered."""
    results = {
        "TP-0000": res("TP-0000", "PASS", ["BIN-0000"]),
        "TP-0001": res("TP-0001", "PASS", ["BIN-0001"]),
    }
    v = evaluate(results=results, report=report(results), missing_records=["TP-0002"])
    assert v.outcome == "EXTEND_TB"
    assert "TP-0002" in v.not_exercised


# ---------------------------------------------------------------- denominator


def test_denominator_is_frozen_on_first_write(tmp_path):
    path = tmp_path / "denominator.json"
    assert freeze_denominator(BINS, path) == DENOM
    # A later, larger coverage model must NOT widen it -- that is the mechanism
    # that makes bin padding impossible rather than merely discouraged.
    grown = BINS + [{"uid": "BIN-9999"}]
    assert freeze_denominator(grown, path) == DENOM


# ---------------------------------------------------------------- categories


def test_categories_are_assigned_without_a_model():
    results = {
        "TP-0000": res("TP-0000", "FAIL", ["BIN-0000"], ["CHK-0"]),
    }
    rep = report(results, testcases=[{"uid": "TC-0", "targets": ["BIN-0000"]}])
    assert rep.statuses["BIN-0000"].category == CHECK_FAILED
    # Nothing targets BIN-0001, which is mechanical, not a judgement call.
    assert rep.statuses["BIN-0001"].category == NO_TESTCASE


def test_targeted_but_unhit_bin_is_the_ambiguous_category():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    rep = report(
        results,
        testcases=[{"uid": "TC-0", "targets": ["BIN-0000", "BIN-0001"]}],
    )
    # This is the only category that needs a model, and the one GoGoTB's agent
    # failed at for 16 of its 24 residual gaps.
    assert rep.statuses["BIN-0001"].category == STIMULUS_GAP


def test_proved_unreachable_is_its_own_category():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    rep = report(results, dispositions={"BIN-0001": {"status": "unreachable"}})
    assert rep.statuses["BIN-0001"].category == UNREACHABLE_PROVED
    assert rep.undisposed == []


# ---------------------------------------------------------------- stall


def test_stall_tracker_fires_only_after_repeated_idleness():
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    rep = report(results)
    t = StallTracker(patience=2)
    assert not t.observe(rep, results)   # progress: first sighting
    assert not t.observe(rep, results)   # idle 1
    assert t.observe(rep, results)       # idle 2 -> stalled


def test_stall_tracker_resets_on_progress():
    r1 = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    r2 = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"]),
          "TP-0001": res("TP-0001", "PASS", ["BIN-0001"])}
    t = StallTracker(patience=2)
    t.observe(report(r1), r1)
    t.observe(report(r1), r1)
    assert not t.observe(report(r2), r2)  # new bin covered -> not stalled


# ---------------------------------------------------------------- lcov


def test_lcov_info_yields_uncovered_lines(tmp_path):
    info = tmp_path / "m.info"
    info.write_text(
        "TN:verilator_coverage\nSF:/x/dut.sv\nDA:1,15\nDA:7,0\nDA:9,0\nend_of_record\n",
        encoding="utf-8",
    )
    assert parse_lcov_info(info) == {"/x/dut.sv": [7, 9]}


def test_lcov_file_with_full_coverage_is_omitted(tmp_path):
    info = tmp_path / "m.info"
    info.write_text("SF:/x/dut.sv\nDA:1,15\nend_of_record\n", encoding="utf-8")
    assert parse_lcov_info(info) == {}


def test_coverage_report_serialises(tmp_path):
    results = {"TP-0000": res("TP-0000", "PASS", ["BIN-0000"])}
    data = json.loads(report(results).to_json())
    assert data["denominator"] == DENOM
    assert data["bins"]["BIN-0000"]["hit"] is True
    assert data["bins"]["BIN-0001"]["hit"] is False
