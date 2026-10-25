"""The transactional comparison: what it catches, and what it deliberately does not.

Cycle-exactness is only worth its cost if the cycle reference is correct, and
ours is a guess -- `latency_cycles` for `cmd_ack` was 3 in one run of the same
i2c spec and 1 in the next, against golden's 5 `clk_en` phases. So the suite was
paying the full price of strictness (rejecting correct RTL, which the repair loop
was watched doing) for none of the benefit.

Measured on real traces, same oracle, two DUTs, `dout` excluded: cycle-exact
separates golden from a wrong design by 15 testpoints, transactional by 40.

The danger of a looser criterion is that it stops discriminating, so most of
what is pinned here is what must STILL fail.
"""

from __future__ import annotations

import pytest

from specflow.trace_compare import (
    compress,
    cycle_exact,
    first_divergence,
    transactional,
)


def seq(*vals):
    return [(v,) for v in vals]


# ------------------------------------------------------------------ encoding

def test_compress_keeps_durations():
    """Durations are returned, never swallowed. "asserted for exactly one clk
    cycle" is a duration claim, and a two-cycle pulse has the same state
    sequence -- that class has to stay visible."""
    assert compress(seq(1, 1, 1, 0, 0)) == ([(1,), (0,)], [3, 2])


def test_compress_of_nothing_is_nothing():
    assert compress([]) == ([], [])


# ---------------------------------------------------------------- divergence

def test_first_divergence_finds_the_index():
    assert first_divergence(seq(1, 0, 1), seq(1, 1, 1)) == 1


def test_equal_sequences_do_not_diverge():
    assert first_divergence(seq(1, 0), seq(1, 0)) is None


def test_a_shorter_sequence_diverges_at_its_own_end():
    """Running out is not agreeing. A design that stopped early must not pass
    on the strength of the prefix it managed."""
    assert first_divergence(seq(1, 0), seq(1, 0, 1)) == 2


# ------------------------------------------------- what transactional ignores

def test_the_same_sequence_held_differently_passes():
    """The whole point: how long each state is held is not judged here."""
    assert transactional(seq(1, 1, 1, 0), seq(1, 0, 0, 0)).ok


def test_durations_are_reported_even_when_it_passes():
    v = transactional(seq(1, 1, 1, 0), seq(1, 0))
    assert v.ok
    assert v.dut_durations == [3, 1] and v.model_durations == [1, 1]


# --------------------------------------------------- what it must still catch

def test_a_wrong_value_fails():
    v = transactional(seq(1, 2, 0), seq(1, 3, 0))
    assert not v.ok and v.diverged_at == 1
    assert v.got == (2,) and v.expected == (3,)


def test_a_skipped_state_fails():
    """A design that goes straight to the end without passing through the
    middle produces a different sequence, not merely a faster one."""
    assert not transactional(seq(1, 0), seq(1, 2, 0)).ok


def test_a_spurious_state_fails():
    assert not transactional(seq(1, 9, 0), seq(1, 0)).ok


def test_a_design_that_stops_early_fails():
    v = transactional(seq(1), seq(1, 0, 1))
    assert not v.ok and "stopped after" in v.reason


def test_a_design_that_runs_on_fails():
    v = transactional(seq(1, 0, 1), seq(1, 0))
    assert not v.ok and "expected only" in v.reason


@pytest.mark.parametrize("dut,model", [
    (seq(0, 0, 0), seq(1, 1, 1)),          # constant, but the wrong constant
    (seq(0), seq(0, 1, 0)),                 # tied off against a pulsing model
])
def test_a_constant_design_does_not_pass_a_moving_model(dut, model):
    """The vacuity guard. A criterion that lets a tied-off DUT through is
    worthless however good its pass rate looks."""
    assert not transactional(dut, model).ok


# ------------------------------------------------ the diagnostic, not a gate

def test_cycle_exact_is_stricter_than_transactional():
    dut, model = seq(1, 1, 0), seq(1, 0, 0)
    assert transactional(dut, model).ok
    assert not cycle_exact(dut, model).ok


def test_the_divergence_index_is_monotone_and_integral():
    """`trace_summary`'s `fail_step` and the repair loop's rollback guard both
    need an integer on a later-is-better axis; the guard's only escape from a
    revert is `new_fail_time > prev_fail_time`."""
    early = transactional(seq(9, 0, 0), seq(1, 0, 0)).diverged_at
    late = transactional(seq(1, 0, 9), seq(1, 0, 0)).diverged_at
    assert isinstance(early, int) and isinstance(late, int)
    assert late > early
