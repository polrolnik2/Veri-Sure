"""Temporal operators, and the two things hand-rolled scanning gets wrong.

Six of a2-i2c's fourteen vacuous oracles evaluate the expectation on the SAME
trace row as the activation. REQ-0092's activation is `cmd == 8` -- the
command-issue window -- and it reads `sda_oen` there, while an i2c bit
controller drives SDA tens of edges later. The check is not weak, it is empty.

Nothing in those oracles is badly written; an AST screen over all fourteen
found no early return and no any-match standing in for all-match. The fault is
the joint assumption that activation and effect hold at one instant, which is
the shape index arithmetic makes easiest.
"""

from __future__ import annotations

from specflow.refmodel.temporal import (after, eventually, pulse, stable,
                                        throughout, worst)
from specflow.refmodel.verdict import truncated


def _state(edge, cmd=0, ack=0, oen=1, held=1):
    return {"edge": edge, "held": held, "index": edge,
            "inputs": {"cmd": cmd, "din": 1}, "outputs": {"ack": ack, "oen": oen}}


ISSUE_THEN_ACK = [_state(0, cmd=8), _state(1, cmd=8), _state(2),
                  _state(3, oen=0), _state(4, ack=1), _state(5)]


def _windows(trace=None):
    return after(trace or ISSUE_THEN_ACK,
                 lambda r: r["inputs"]["cmd"] == 8,
                 until=lambda r: r["outputs"]["ack"] == 1)


def test_a_window_spans_the_activation_to_its_consequence():
    """The point of the whole module: the effect is not at the activation."""
    w = _windows()
    assert len(w) == 1 and w[0].edge == 0
    assert w[0].closed and len(w[0].rows) == 5      # edges 0..4, closing on ack


def test_a_condition_true_for_many_rows_is_ONE_window():
    """Otherwise a two-state command issue produces two windows and every
    verdict is counted twice."""
    assert len(_windows()) == 1


def test_eventually_finds_an_effect_the_activation_row_cannot_show():
    ok, edge, _ = eventually(_windows()[0], lambda r: r["outputs"]["ack"] == 1)
    assert (ok, edge) == (True, 4)


def test_a_window_that_RUNS_OFF_THE_END_is_unknown_not_false():
    """Nothing was seen to be wrong -- we stopped looking.

    `verdict.truncated()` reconstructs this from the oracle's prose today, by
    matching seven phrases; an author who words it differently is scored as
    having found a real bug. Here it is structural, and the wording it produces
    is one `truncated()` already recognises, so both paths agree.
    """
    trace = [_state(0, cmd=8), _state(1, cmd=8), _state(2)]
    w = after(trace, lambda r: r["inputs"]["cmd"] == 8,
              until=lambda r: r["outputs"]["ack"] == 1)
    ok, _edge, why = eventually(w[0], lambda r: r["outputs"]["ack"] == 1)
    assert ok is None
    assert truncated(why), why


def test_throughout_fails_on_the_first_row_that_breaks_it():
    ok, edge, _ = throughout(_windows()[0], lambda r: r["outputs"]["oen"] == 1)
    assert (ok, edge) == (False, 3)


def test_stable_holds_whatever_value_it_found():
    """The slave_wait shape -- "held steady" names no value, so `throughout`
    cannot express it."""
    quiet = [_state(0, cmd=8), _state(1, cmd=8, oen=1), _state(2, ack=1)]
    w = after(quiet, lambda r: r["inputs"]["cmd"] == 8,
              until=lambda r: r["outputs"]["ack"] == 1)
    assert stable(w[0], "oen")[0] is True
    assert stable(_windows()[0], "oen")[0] is False


def test_pulse_counts_EDGES_not_rows():
    """The trace is state-compressed: consecutive edges with identical inputs
    and outputs are ONE row carrying `held`. Counting rows would call a 40-edge
    assertion a single-cycle pulse."""
    one = [_state(0, cmd=8), _state(1, ack=1, held=1), _state(2, ack=1)]
    w = after(one, lambda r: r["inputs"]["cmd"] == 8)
    assert pulse(_windows()[0], "ack")[0] is True
    wide = [_state(0, cmd=8), _state(1, cmd=8), _state(2, ack=1, held=4),
            _state(3, ack=1)]
    ww = after(wide, lambda r: r["inputs"]["cmd"] == 8,
               until=lambda r: r["outputs"]["ack"] == 1)
    ok, _e, why = pulse(ww[0], "ack")
    assert ok is False and "4 edge(s), not 1" in why
    assert w and one


def test_pulse_refuses_two_pulses_in_one_window():
    twice = [_state(0, cmd=8), _state(1, ack=1), _state(2), _state(3, ack=1),
             _state(4, ack=1), _state(5, oen=0)]
    w = after(twice, lambda r: r["inputs"]["cmd"] == 8,
              until=lambda r: r["outputs"]["oen"] == 0)
    ok, _e, why = pulse(w[0], "ack")
    assert ok is False and "pulsed 2 times" in why


def test_a_window_with_no_until_ends_WITH_THE_ACTIVATION():
    """And that narrowness is deliberate, because of which way it fails.

    Without `until` the window is the activation's own extent plus the row that
    ended it, so a check looking for a later effect returns False or UNKNOWN --
    loudly, against the witness, where gate 1 makes the author add the `until`.
    An open-ended default would fail the other way: `eventually` would find the
    event somewhere in the remaining trace and pass, which is the vacuity this
    module exists to remove.
    """
    trace = [_state(0, cmd=8), _state(1), _state(2), _state(3, ack=1)]
    narrow = after(trace, lambda r: r["inputs"]["cmd"] == 8)[0]
    assert [r["edge"] for r in narrow.rows] == [0, 1]
    assert eventually(narrow, lambda r: r["outputs"]["ack"] == 1)[0] is False
    wide = after(trace, lambda r: r["inputs"]["cmd"] == 8,
                 until=lambda r: r["outputs"]["ack"] == 1)[0]
    assert eventually(wide, lambda r: r["outputs"]["ack"] == 1)[0] is True


def test_worst_puts_failure_first_and_unknown_above_a_pass():
    """A requirement holding on nine windows and breaking on the tenth is
    broken; a grown evidence set only moves a verdict toward worse."""
    assert worst([(True, 1, "a"), (None, 2, "b"), (False, 3, "c")])[0] is False
    assert worst([(True, 1, "a"), (None, 2, "b")])[0] is None
    assert worst([])[0] is None


def test_the_activation_value_is_readable_after_the_fact():
    """Expectations are usually written against what the inputs WERE when the
    requirement applied, and re-reading them later is a common way to get it
    wrong."""
    assert _windows()[0].value("din") == 1


def test_the_oracle_prompt_offers_them_and_forbids_a_cycle_count():
    from specflow.refmodel.oracle_gen import SYSTEM

    assert "after(trace" in SYSTEM and "eventually(w" in SYSTEM
    assert "NEVER A COUNT" in SYSTEM
