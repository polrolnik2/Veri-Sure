"""`benchmarks/golden_check.py`'s own tally, isolated from the RTL build.

`_score` compiles and cosimulates real RTL before it ever counts anything, so
a unit test for its COUNTING has to go around that -- `_tally` is the pure
part, extracted for exactly this.
"""

from __future__ import annotations

import json

from benchmarks.golden_check import _tally


def _write(d, name, **fields):
    (d / name).write_text(json.dumps(fields), encoding="utf-8")


def test_trace_json_is_not_counted_as_a_second_testpoint(tmp_path):
    """Measured live on or1200_ctrl: `render_suite` writes `{tp}.trace.json`
    beside `{tp}.json` unconditionally now, and it carries no `status` --
    `specflow/run.py`'s `_read_results` already guards the identical glob for
    the identical reason. Before this guard, `_tally`'s equivalent counted
    both, so 8 real passes out of 31 real testpoints reported as 8/62.
    """
    _write(tmp_path, "TP-0000.json", tp_uid="TP-0000", status="PASS")
    _write(tmp_path, "TP-0000.trace.json", tp_uid="TP-0000", edges=[])
    _write(tmp_path, "TP-0001.json", tp_uid="TP-0001", status="FAIL",
           signals_failed=["ex_insn"])
    _write(tmp_path, "TP-0001.trace.json", tp_uid="TP-0001", edges=[])

    row = _tally(tmp_path)
    assert row["total"] == 2, row
    assert row["passed"] == 1, row


def test_a_directory_with_no_trace_files_is_unaffected(tmp_path):
    """The inert default: every run this was measured on before tracing
    became unconditional still counts exactly as it did."""
    _write(tmp_path, "TP-0000.json", tp_uid="TP-0000", status="PASS")
    _write(tmp_path, "TP-0001.json", tp_uid="TP-0001", status="FAIL",
           signals_failed=["sig_trap"])

    row = _tally(tmp_path)
    assert row == {"passed": 1, "total": 2,
                   "by_signal": {"sig_trap": 1}, "sole": {"sig_trap": 1}}
