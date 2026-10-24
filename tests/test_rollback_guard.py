"""The rollback guard, its escape hatch, and what happens when it is off.

The guard reverts any RTL edit that increases the mismatch count. That is a
sensible default and it is also, exactly, a hill-climber: a repair needing
several parts to land together regresses at every partial step, so each one is
rejected and the loop stalls at whatever local minimum it reached first.

Two things are pinned here.

The escape hatch was already written -- accept a small increase when the FIRST
failure moves later -- but it reads `fail_time`, and on the specflow backend
`_extract_fail_time_from_sim_log_json` matched only two Verilog-testbench
regexes against `stdout` and so returned None every time. Both sides None makes
the comparison dead and the guard unconditionally greedy. Live on
i2c_master_bit_ctrl that showed up as four consecutive rollbacks and a stall at
91 failing testpoints with `prev_fail_time=None, new_fail_time=None` recorded on
every one.

And with the guard off, the loop may end part way up a hill it was allowed to
climb. Returning that would make "no guard" lose by construction rather than on
the merits, so the best point seen is checkpointed and restored.
"""

from __future__ import annotations

import json

import pytest

from eda_agent.rtl_editor import (
    _EditSession,
    _extract_fail_time_from_sim_log_json,
    resolve_rollback_guard,
)


def _specflow_payload(*, fail_step, mismatches: int = 3) -> str:
    return json.dumps({
        "format": "specflow",
        "stdout": f"SUMMARY: {mismatches} mismatches across 2 testpoints; "
                  f"first at stimulus step {fail_step}",
        "verdict": "REPAIR_RTL",
        "trace": {"fail_step": fail_step, "total_mismatches": mismatches},
    })


# ------------------------------------------------------- fail_time extraction

def test_fail_step_is_read_from_the_specflow_payload():
    """The bug: this returned None, which made the escape hatch unreachable."""
    assert _extract_fail_time_from_sim_log_json(_specflow_payload(fail_step=7)) == 7


def test_fail_step_zero_is_a_value_not_a_missing_reading():
    """`0` is the earliest step, not 'unknown' -- a falsy-test here would
    reintroduce exactly the None-means-dead-comparison bug for the commonest
    case, since most runs fail at step 0."""
    assert _extract_fail_time_from_sim_log_json(_specflow_payload(fail_step=0)) == 0


def test_absent_fail_step_is_still_none():
    payload = json.dumps({"format": "specflow", "stdout": "", "trace": {}})
    assert _extract_fail_time_from_sim_log_json(payload) is None


def test_verilog_payload_still_uses_the_stdout_regexes():
    """The SystemVerilog path must not regress -- it has no `format` key."""
    payload = json.dumps({"stdout":
        "Hint: Output 'q' has 4 mismatches. First mismatch occurred at time 120."})
    assert _extract_fail_time_from_sim_log_json(payload) == 120


# ------------------------------------------------------ best-so-far behaviour

def _session(tmp_path, *, guard: bool) -> _EditSession:
    rtl = tmp_path / "rtl.sv"
    rtl.write_text("start", encoding="utf-8")
    return _EditSession(
        tb_path=None, rtl_path=str(rtl), output_dir=str(tmp_path),
        last_mismatch_cnt=10, sim_reviewer=None, max_trials=5,
        rollback_on_regression=guard,
    )


def test_best_tracks_the_minimum(tmp_path):
    s = _session(tmp_path, guard=False)
    assert s.note_best(10, "a") is True
    assert s.note_best(12, "worse") is False      # uphill does not overwrite
    assert s.note_best(4, "b") is True
    assert s.note_best(9, "c") is False
    assert (s.best_mismatch_cnt, s.best_rtl) == (4, "b")


def test_a_tie_keeps_the_earlier_rtl(tmp_path):
    """Crossing a plateau should return where it first arrived, not wherever it
    happened to stop -- otherwise a run that wanders across equal-scoring
    variants reports its last coin-flip as the result."""
    s = _session(tmp_path, guard=False)
    s.note_best(5, "first")
    s.note_best(5, "second")
    assert s.best_rtl == "first"


def test_restore_best_rewrites_the_file(tmp_path):
    s = _session(tmp_path, guard=False)
    s.note_best(4, "the good one")
    s.write_rtl("a worse one the loop ended on")
    assert s.restore_best() is True
    assert s.read_rtl() == "the good one"


def test_restore_best_is_a_noop_when_already_best(tmp_path):
    s = _session(tmp_path, guard=True)
    s.note_best(4, "x")
    s.write_rtl("x")
    assert s.restore_best() is False


def test_restore_best_with_nothing_recorded_is_safe(tmp_path):
    """A session that never simulated must not blank the RTL on the way out."""
    s = _session(tmp_path, guard=False)
    assert s.restore_best() is False
    assert s.read_rtl() == "start"


def test_guard_defaults_on(tmp_path):
    """The guard is the default and this change must not silently flip it."""
    assert _session(tmp_path, guard=True).rollback_on_regression is True
    rtl = tmp_path / "r2.sv"
    rtl.write_text("x", encoding="utf-8")
    plain = _EditSession(
        tb_path=None, rtl_path=str(rtl), output_dir=str(tmp_path),
        last_mismatch_cnt=1, sim_reviewer=None, max_trials=1,
    )
    assert plain.rollback_on_regression is True


# ------------------------------------------------------------ the env switch

@pytest.mark.parametrize("value,expected", [
    ("off", False), ("0", False), ("false", False), ("no", False),
    ("OFF", False), (" off ", False),
    ("on", True), ("1", True), ("", True), ("typo", True), ("offf", True),
])
def test_env_switch_turns_the_guard_off(value, expected):
    """Exercises the real resolver, not a copy of its logic in the test.

    Note the negative cases: an empty string and a typo both leave the guard ON.
    A mistake in this variable must fail safe INTO the guard, because the
    failure mode of accidentally disabling it is a run that quietly keeps
    regressions.
    """
    assert resolve_rollback_guard(None, {"EDA_ROLLBACK_GUARD": value}) is expected


def test_unset_env_leaves_the_guard_on():
    assert resolve_rollback_guard(None, {}) is True


@pytest.mark.parametrize("explicit", [True, False])
def test_explicit_argument_beats_the_environment(explicit):
    """A caller that passed a value must get it regardless of the environment,
    or the CLI flag becomes advisory whenever .env.local disagrees."""
    hostile = {"EDA_ROLLBACK_GUARD": "off" if explicit else "on"}
    assert resolve_rollback_guard(explicit, hostile) is explicit


def test_editor_defaults_to_the_environment(monkeypatch):
    """The constructor path itself, not just the helper."""
    import inspect
    from eda_agent.rtl_editor import RTLEditor
    src = inspect.getsource(RTLEditor.__init__)
    assert "resolve_rollback_guard(rollback_guard)" in src
