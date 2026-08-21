"""A reset a testpoint can actually ask for.

Reset stays out of `_drivable` on purpose -- the runtime owns it so the DUT and
the reference model reset together and cannot diverge. The cost was that a
requirement ABOUT reset had no way to be exercised: on the a-i2c run 37 of 167
testpoints asked for a mid-run reset in prose, no step could deliver one, and
their oracles reported "nReset was never asserted low in this trace" as a model
defect.

`{"reset": true}` closes that without touching the invariant: the harness
sequences both sides, and the trace shows the reset asserted so an oracle can
see the event it is about.
"""

from __future__ import annotations

from specflow.ports import asserted_resets, pinned_inputs
from specflow.refmodel.oracles import replay
from specflow.tb.runtime import is_reset_step, normalise_step

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "nReset", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
    ]
}

#: Counts up, and `reset()` clears the count -- so a reset is visible in `q`.
COUNTER = '''from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]

    def reset(self):
        self.n = 0

    def step(self, i):
        if not hasattr(self, "n"):
            self.reset()
        self.n = self.mask(self.n + i.get("a", 0), 8)
        return {"q": self.n}
'''


def test_the_active_level_is_the_complement_of_the_idle_one():
    """`nReset` idles high, so asserting it means driving it low."""
    assert pinned_inputs(CONTRACT)["nReset"] == 1
    assert asserted_resets(CONTRACT)["nReset"] == 0


def test_an_explicit_idle_value_is_honoured_in_both_directions():
    """A contract that declares its own polarity must not be second-guessed."""
    contract = {"io": [{"name": "rst_n", "dir": "input", "width": 1,
                        "role": "reset", "idle_value": 0}]}
    assert pinned_inputs(contract)["rst_n"] == 0
    assert asserted_resets(contract)["rst_n"] == 1


def test_a_reset_step_is_recognised_and_never_read_as_an_input_bundle():
    """`{"reset": true}` must not become an input named `reset`.

    The bare-dict branch of `normalise_step` would have done exactly that.
    """
    assert is_reset_step({"reset": True})
    assert is_reset_step({"reset": True, "hold": 8})
    assert not is_reset_step({"a": 1})
    assert not is_reset_step({"inputs": {"a": 1}, "hold": 2})
    inputs, hold, _, _ = normalise_step({"reset": True, "hold": 8})
    assert inputs == {}, "a reset step drives nothing"
    assert hold == 8


def test_a_reset_step_shows_the_reset_asserted_in_the_trace():
    """Without this an oracle about reset can never observe its own event."""
    rows = replay(COUNTER, CONTRACT, [
        {"inputs": {"a": 1}, "hold": 3},
        {"reset": True, "hold": 2},
        {"inputs": {"a": 1}, "hold": 2},
    ], base="step").rows
    levels = [r["inputs"]["nReset"] for r in rows]
    assert levels == [1, 1, 1, 0, 0, 1, 1], "asserted only during the reset step"


def test_a_reset_step_actually_resets_the_model_state():
    """Driving the port alone would trust a model that may ignore it."""
    rows = replay(COUNTER, CONTRACT, [
        {"inputs": {"a": 5}, "hold": 3},        # q: 5, 10, 15
        {"reset": True, "hold": 1},
        {"inputs": {"a": 5}, "hold": 1},
    ], base="step").rows
    q = [r["outputs"]["q"] for r in rows]
    assert q[:3] == [5, 10, 15]
    assert q[-1] == 5, "the count restarted, so reset() really ran"


def test_a_run_with_no_reset_step_is_unchanged():
    """The whole suite's existing behaviour must not move."""
    rows = replay(COUNTER, CONTRACT,
                  [{"inputs": {"a": 2}, "hold": 4}], base="step").rows
    assert [r["outputs"]["q"] for r in rows] == [2, 4, 6, 8]
    assert {r["inputs"]["nReset"] for r in rows} == {1}


def test_the_gate_accepts_a_reset_step_that_drives_nothing():
    """It would otherwise fail "does not drive [every input]"."""
    from specflow.testcase_agent import SuiteStimulus, gate_suite

    spec = SuiteStimulus(testpoints=[{
        "tp_uid": "TP-0000",
        "stimulus_steps": [{"a": 1}, {"reset": True}, {"a": 2}],
    }])
    issues = gate_suite(spec, testplan=[{"uid": "TP-0000"}],
                        contract=CONTRACT, max_steps=10)
    assert [i for i in issues if i.severity == "error"] == []


def test_the_gate_rejects_a_reset_step_that_also_drives_inputs():
    """Ambiguous: are they held during reset, or after it?"""
    from specflow.testcase_agent import SuiteStimulus, gate_suite

    spec = SuiteStimulus(testpoints=[{
        "tp_uid": "TP-0000",
        "stimulus_steps": [{"reset": True, "inputs": {"a": 1}}],
    }])
    issues = gate_suite(spec, testplan=[{"uid": "TP-0000"}],
                        contract=CONTRACT, max_steps=10)
    assert any("drives no inputs" in i.message for i in issues)


def test_the_model_stays_reset_for_the_whole_time_reset_is_held():
    """Reset is a level, not a pulse.

    A model that ignores the reset PORT -- which a generated one may -- would
    otherwise keep counting underneath an asserted reset, and the trace would
    show a design running during its own reset.
    """
    rows = replay(COUNTER, CONTRACT, [
        {"inputs": {"a": 5}, "hold": 2},
        {"reset": True, "hold": 4},
        {"inputs": {"a": 5}, "hold": 1},
    ], base="step").rows
    q = [r["outputs"]["q"] for r in rows]
    assert q[:2] == [5, 10]
    assert q[2:6] == [0, 0, 0, 0], "held at the reset value, not advancing"
    assert q[-1] == 5


def test_functional_inputs_are_idle_while_reset_is_held():
    """`Env.reset()` does the same, so both sides leave reset agreeing."""
    rows = replay(COUNTER, CONTRACT, [
        {"inputs": {"a": 7}, "hold": 1},
        {"reset": True, "hold": 1},
    ], base="step").rows
    assert rows[0]["inputs"]["a"] == 7
    assert rows[1]["inputs"]["a"] == 0, "not the vector the last step left"
