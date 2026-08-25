"""A reference model checked against nothing has not been checked.

THE FALSE GREEN HAS TWO INDEPENDENT CAUSES AND BOTH WERE MEASURED LIVE.

    y-i2c  the oracle stage died on a mid-stream drop: `run_chipverilog`
           declared `--max-output-tokens default=48000` and passed it
           unconditionally, so the body cap became `min(64000, 48000)` = the
           ceiling, which turns off continuation AND widening at once.

    z-i2c  the oracle stage died on ONE gateway 500, on
           `variant_REQ-0028_trigger`, one of ~600 variant calls, 1h40m in.

Different causes, identical presentation: no `oracles.json`, a reference model
built anyway, and `refmodel_gate.json` reading `ok: true, errors: 0` -- not
because the model was good but because AN EMPTY ORACLE SET HAS NO FAILURES IN
IT. Fixing the first cause did nothing about the second, which is the whole
reason this is tested at the gate rather than at either cause.

`run_fanout` raising an item's exception to its caller is correct and stays --
"a stage that silently dropped an item would produce an artifact with a hole in
it". The defect was `integration.build_artifacts` catching it as a WARNING.
"""

from __future__ import annotations

from specflow.integration import _oracle_stage_issues
from specflow.schema import has_errors


class _Set:
    def __init__(self, trusted):
        self.trusted = trusted


def test_a_stage_that_did_not_complete_is_a_gate_error():
    """z-i2c's case: the exception reaches the gate instead of the log."""
    issues = _oracle_stage_issues("RuntimeError('gateway 500')", None)
    assert has_errors(issues), "a warning let the run report success"
    assert "gateway 500" in issues[0].message, (
        "the reason has to name the call that killed the stage")
    assert issues[0].path == "oracles.stage.incomplete"


def test_an_empty_trusted_set_is_a_gate_error_too():
    """The stage can also succeed and produce nothing, which decides just as
    little. Zero failures there means nothing was asked."""
    issues = _oracle_stage_issues("", _Set([]))
    assert has_errors(issues)
    assert issues[0].path == "oracles.stage.empty"


def test_a_real_oracle_set_is_not_an_error():
    """The guard must not fire on the ordinary path, or every run blocks."""
    assert _oracle_stage_issues("", _Set(["an oracle"])) == []


def test_a_reused_set_that_was_never_loaded_is_not_accused():
    """`oracle_set is None` with no failure recorded is the `--reuse` path that
    raised `_Reused` before assigning. Only a recorded failure convicts."""
    assert _oracle_stage_issues("", None) == []
