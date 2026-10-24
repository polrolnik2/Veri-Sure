"""Stimulus is a reusable artifact, like every other stage's output.

It was the one major artifact never written to `specflow/`, so `--reuse` could
not cover it and every rerun paid for it again -- 167 model calls on
i2c_master_bit_ctrl, the most expensive stage in the pipeline now that it fans
out, repeated even when nothing upstream had changed.
"""

from __future__ import annotations

import json

from specflow.testcase_agent import (
    STIMULUS_MAX_STEPS,
    SuiteStimulus,
    gate_suite,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "q", "dir": "output", "width": 8},
    ]
}
PLAN = [{"uid": "TP-0000", "dimension": "D2", "stimulus": "s", "expected_response": "r"}]


def _spec(steps):
    return SuiteStimulus(
        reasoning="r", testpoints=[{"tp_uid": "TP-0000", "stimulus_steps": steps}]
    )


def test_a_recorded_stimulus_round_trips_through_its_own_model():
    """Reuse validates the file against SuiteStimulus before gating it."""
    spec = _spec([{"inputs": {"ena": 1}, "hold": 8}])
    restored = SuiteStimulus.model_validate(json.loads(json.dumps(spec.model_dump())))
    assert restored.testpoints[0].tp_uid == "TP-0000"
    assert restored.testpoints[0].stimulus_steps == spec.testpoints[0].stimulus_steps


def test_the_reuse_gate_is_the_same_bound_the_generator_was_held_to():
    """A reuse path gated more loosely accepts what a fresh run would reject.

    `STIMULUS_MAX_STEPS` is named for exactly this: the bound applied when a
    recorded artifact is reused must be the one applied when it was generated.
    """
    over = _spec([{"inputs": {"ena": 1}} for _ in range(STIMULUS_MAX_STEPS + 1)])
    issues = gate_suite(over, testplan=PLAN, contract=CONTRACT,
                        max_steps=STIMULUS_MAX_STEPS)
    assert [i for i in issues if i.severity == "error"], (
        "an over-long recorded stimulus must be regenerated, not reused"
    )


def test_a_stimulus_missing_a_testpoint_is_not_reusable():
    """The testplan may have grown since the file was written."""
    spec = _spec([{"inputs": {"ena": 1}, "hold": 4}])
    grown = [*PLAN, {"uid": "TP-0001", "dimension": "D2",
                     "stimulus": "s", "expected_response": "r"}]
    issues = gate_suite(spec, testplan=grown, contract=CONTRACT,
                        max_steps=STIMULUS_MAX_STEPS)
    assert any(i.severity == "error" and "TP-0001" in i.path for i in issues), (
        "reusing stimulus that predates a testplan change would leave the new "
        "testpoint silently on default_stimulus"
    )
