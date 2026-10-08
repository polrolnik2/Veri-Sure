"""A stimulus step can state its own duration, and the gate accepts it.

How long a vector was applied used to come from `LATENCY_CYCLES + 1` -- the max
of the contract's guessed per-output latencies. That tied the pace of every
stimulus in the suite to a number an LLM produced, and it was not even stable:
the same i2c spec yielded 3 in one run and 1 in the next, silently rescaling the
whole suite between them.

It also left no way to say a command needs cycles except to repeat an identical
dict. `gate_suite` rejected any key that was not a port, so `hold` was a hard
error. On i2c that showed up as every testpoint having three vectors -- 12 edges
against the 26 golden needs for one START -- and 61 of 168 testpoints unable to
complete a single command.
"""

from __future__ import annotations

import pytest

from specflow.tb.runtime import normalise_step
from specflow.testcase_agent import MAX_HOLD, MAX_TIMEOUT, SuiteStimulus, gate_suite

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "rst_n", "dir": "input", "width": 1},
        {"name": "go", "dir": "input", "width": 1},
        {"name": "done", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": True},
}
PLAN = [{"uid": "TP-0000"}]


def _gate(steps):
    spec = SuiteStimulus.model_validate(
        {"testpoints": [{"tp_uid": "TP-0000", "stimulus_steps": steps}]}
    )
    return gate_suite(spec, testplan=PLAN, contract=CONTRACT, max_steps=24)


def _errors(steps):
    return [i for i in _gate(steps) if i.severity == "error"]


# ------------------------------------------------------------- normalisation

def test_a_bare_dict_is_one_edge():
    """Not `LATENCY_CYCLES + 1`. Duration is the test's business, and a hidden
    multiplier meant nobody could tell how long a vector was actually applied."""
    assert normalise_step({"go": 1}) == ({"go": 1}, 1, None, 0)


@pytest.mark.parametrize("bad", [0, -5, "x", None])
def test_a_nonsense_hold_clamps_to_one_edge(bad):
    _, hold, _, _ = normalise_step({"inputs": {"go": 1}, "hold": bad})
    assert hold == 1


def test_until_survives_normalisation():
    inputs, hold, until, timeout = normalise_step(
        {"inputs": {"go": 1}, "until": {"port": "done", "value": 1}, "timeout": 50}
    )
    assert (inputs, until, timeout) == ({"go": 1}, {"port": "done", "value": 1}, 50)


# --------------------------------------------------------------------- gate

def test_hold_and_until_are_accepted():
    """They were a hard error: `gate_suite` rejected every key that was not a
    drivable input, so there was no way to express duration at all."""
    assert not _errors([
        {"inputs": {"go": 1}, "hold": 4},
        {"inputs": {"go": 0}, "until": {"port": "done", "value": 1}, "timeout": 100},
    ])


def test_a_bare_dict_still_works():
    """The old shape must keep working -- every recorded fixture uses it."""
    assert not _errors([{"go": 1}])


def test_until_must_wait_on_an_output():
    """A step waits on what the DESIGN reports. Waiting on an input the test
    drives is a tautology: it is already true the moment it is written."""
    errs = _errors([{"inputs": {"go": 1}, "until": {"port": "go", "value": 1}}])
    assert errs and "not a declared output" in errs[0].message


def test_an_absurd_hold_is_rejected_in_favour_of_until():
    errs = _errors([{"inputs": {"go": 1}, "hold": MAX_HOLD + 1}])
    assert errs and "use `until`" in errs[0].message


def test_an_absurd_timeout_is_rejected():
    errs = _errors([{"inputs": {"go": 1},
                     "until": {"port": "done", "value": 1},
                     "timeout": MAX_TIMEOUT + 1}])
    assert errs and "exceeds" in errs[0].message


def test_the_inputs_of_a_wrapped_step_are_still_checked():
    """Wrapping inputs in `{"inputs": ...}` must not smuggle them past the
    width and drivability checks that a bare dict gets."""
    errs = _errors([{"inputs": {"go": 99}}])
    assert errs, "an out-of-range value inside `inputs` was not caught"


def test_a_wrapped_step_still_has_to_drive_everything():
    errs = _errors([{"inputs": {}, "hold": 2}])
    assert any("does not drive" in i.message for i in errs)
