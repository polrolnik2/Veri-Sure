"""Testpoints asking for a reset the stimulus schema cannot express.

`_drivable` excludes clock and reset on purpose: the runtime owns them, and a
testcase toggling reset underneath would desynchronise `Env.reset()` from the
model's own `reset()`. S2 does not know that, so it writes testpoints whose
scenario is "assert reset mid-run and check the outputs clear" -- 37 of 167 on
the a-i2c run, covering 32 requirements, none of which could drive `rst` or
`nReset`.

Their oracles then reported "nReset was never asserted low in this trace", and
the loop read that as a failing model.

The whole value of this diagnostic is that it fires on the real thing and not
on the common phrasing that surrounds it, so most of these tests are about the
line between them.
"""

from __future__ import annotations

from specflow.testcase_agent import unrealisable_reset


def _tp(uid: str, stimulus: str) -> dict:
    return {"uid": uid, "stimulus": stimulus, "expected_response": "", "check_method": ""}


def test_it_says_nothing_when_no_testpoint_asks_for_a_reset():
    assert unrealisable_reset([_tp("TP-0", "drive cmd=1 and wait for cmd_ack")]) == []


def test_releasing_reset_is_not_asking_for_one():
    """The overwhelmingly common phrasing, and it describes the harness default.

    Matching it would fire on nearly every testpoint and mean nothing -- 138 of
    167 on a-i2c mention reset this way.
    """
    for phrasing in (
        "Start with nReset deasserted, rst=0, ena=1, clk_cnt large",
        "Release resets (nReset=1, rst=0). Bring up core: ena=1",
        "Start from reset released and idle: nReset=1, rst=0, ena=1",
        "Reset released, ena=1, clk_cnt=0. Drive the external bus non-idle",
    ):
        assert unrealisable_reset([_tp("TP-0", phrasing)]) == [], phrasing


def test_asserting_reset_is_reported():
    """Both the prose forms and the literal ones -- `nReset=0` IS the assertion."""
    for phrasing in (
        "Apply resets and bring DUT to idle with ena=1",
        "Apply asynchronous reset asserting nReset=0 for multiple cycles",
        "While the DUT is mid-operation, toggle rst=1 for one clk cycle",
        "assert rst=1 (synchronous reset) and keep nReset=1",
        "Initial conditions: assert asynchronous reset nReset=0 for 2 clk",
        "hold rst_n=0 during reset and observe the outputs clear",
    ):
        out = unrealisable_reset([_tp("TP-0", phrasing)])
        assert len(out) == 1, phrasing
        assert out[0].severity == "warning", "the stimulus agent did nothing wrong"


def test_it_names_the_testpoints_so_the_finding_is_actionable():
    out = unrealisable_reset([
        _tp("TP-0018", "Apply reset then idle"),
        _tp("TP-0029", "toggle rst=1 mid-operation"),
        _tp("TP-0100", "drive cmd=4 and wait"),
    ])
    assert len(out) == 1
    assert "TP-0018" in out[0].message and "TP-0029" in out[0].message
    assert "TP-0100" not in out[0].message
    assert "2 testpoint(s)" in out[0].message


def test_it_reads_every_prose_field_not_only_the_stimulus():
    """S2 splits the scenario across slots; the ask can land in any of them."""
    tp = {"uid": "TP-1", "stimulus": "bring up the core",
          "expected_response": "during reset all outputs are released",
          "check_method": ""}
    assert len(unrealisable_reset([tp])) == 1


def test_it_is_a_warning_so_it_cannot_fail_a_run_it_cannot_fix():
    """Regenerating the stimulus cannot help -- the schema forbids the step.

    Erroring here would block a run on something no repair round can resolve,
    which is the failure mode `latency_cycles` was demoted for.
    """
    out = unrealisable_reset([_tp("TP-0", "assert reset")])
    assert [i.severity for i in out] == ["warning"]


# --------------------------------------------------- divider starvation (#50)


def test_a_testpoint_that_cannot_complete_one_divider_tick_is_reported():
    from specflow.testcase_agent import SuiteStimulus, starved_by_divider

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "clk_cnt", "dir": "input", "width": 16},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
    ]}
    spec = SuiteStimulus(testpoints=[
        {"tp_uid": "TP-STARVED",
         "stimulus_steps": [{"inputs": {"clk_cnt": 1000, "cmd": 1}, "hold": 129}]},
        {"tp_uid": "TP-FINE",
         "stimulus_steps": [{"inputs": {"clk_cnt": 4, "cmd": 1}, "hold": 40}]},
    ])
    out = starved_by_divider(spec, contract)
    assert [i.path for i in out] == ["stimulus.TP-STARVED"]
    assert "1001" in out[0].message and i_ok(out[0])


def i_ok(issue) -> bool:
    return issue.severity == "warning"


def test_an_until_step_is_budgeted_by_its_timeout_not_treated_as_unbounded():
    """The overcount this function was written to replace.

    A hand count that summed `hold` and skipped `until` steps read 60 starved
    testpoints out of 167; the real figure under the step semantics the replay
    actually uses is 13.
    """
    from specflow.testcase_agent import SuiteStimulus, starved_by_divider

    contract = {"io": [
        {"name": "clk_cnt", "dir": "input", "width": 16},
        {"name": "q", "dir": "output", "width": 8},
    ]}
    too_short = SuiteStimulus(testpoints=[{"tp_uid": "TP-0", "stimulus_steps": [
        {"inputs": {"clk_cnt": 500}, "until": {"port": "q", "value": 1},
         "timeout": 100}]}])
    long_enough = SuiteStimulus(testpoints=[{"tp_uid": "TP-0", "stimulus_steps": [
        {"inputs": {"clk_cnt": 500}, "until": {"port": "q", "value": 1},
         "timeout": 2000}]}])
    assert len(starved_by_divider(too_short, contract)) == 1
    assert starved_by_divider(long_enough, contract) == []


def test_a_design_with_no_divider_is_never_flagged():
    from specflow.testcase_agent import SuiteStimulus, starved_by_divider

    contract = {"io": [{"name": "a", "dir": "input", "width": 4},
                       {"name": "q", "dir": "output", "width": 8}]}
    spec = SuiteStimulus(testpoints=[
        {"tp_uid": "TP-0", "stimulus_steps": [{"inputs": {"a": 1}, "hold": 1}]}])
    assert starved_by_divider(spec, contract) == []


def test_a_reset_step_does_not_count_against_the_divider_budget():
    """It drives no divider value and its edges are the harness's, not the test's."""
    from specflow.testcase_agent import SuiteStimulus, starved_by_divider

    contract = {"io": [{"name": "clk_cnt", "dir": "input", "width": 16},
                       {"name": "q", "dir": "output", "width": 8}]}
    spec = SuiteStimulus(testpoints=[{"tp_uid": "TP-0", "stimulus_steps": [
        {"reset": True, "hold": 2},
        {"inputs": {"clk_cnt": 2}, "hold": 30}]}])
    assert starved_by_divider(spec, contract) == []
