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


def test_the_prompt_states_the_RETURN_contract_and_the_SVA_mapping():
    """The operators were described by meaning and never by signature.

    An author was told what `eventually` MEANS and never what it RETURNS, so the
    one fact that makes `return worst([...])` the whole function -- that a
    Verdict is the same `(ok, edge, detail)` triple `decide` returns -- appeared
    only implicitly, inside an example. Uptake was 1 of 182.

    And they ARE the SVA operators. A model writing hardware checks has priors
    for `throughout`, `$stable` and `s_eventually`; naming the correspondence
    costs four lines and buys the semantics. It has to name where the analogy
    BREAKS too, and the third break is the one that bites: a row is not a clock
    tick, because the trace is state-compressed.
    """
    from specflow.refmodel.oracle_gen import SYSTEM

    assert "`(ok, edge, detail)`" in SYSTEM or "(ok, edge, detail)" in SYSTEM
    assert "worst([])" in SYSTEM, "the abstention path must be spelled out"
    # ASSERT ON A FRAGMENT THAT DOES NOT CROSS A LINE WRAP. The prompt reads
    # "the scenario was never\nstaged", so "never staged" is not a substring of
    # it -- and the assertion failed for the formatting rather than for the
    # meaning. This repo has paid for that mistake before.
    assert "blames the design for a testpoint that does not exist" in SYSTEM, (
        "an empty window list is a stimulus fact; turning it into False blames "
        "the design for a testpoint that does not exist")
    assert "SVA OPERATORS" in SYSTEM
    for sva in ("s_eventually", "throughout", "$stable", "$rose"):
        assert sva in SYSTEM, sva
    assert "A ROW IS NOT A CLOCK TICK" in SYSTEM
    assert "at most 64" in SYSTEM, "a silent cap is against the house rule"


def test_worst_of_nothing_abstains_exactly_as_the_prompt_promises():
    """Pinned because the prompt now instructs the author to return it."""
    ok, edge, detail = worst([])
    assert ok is None and edge is None
    assert detail == "the activation never occurred"


# ---------------------------------------------------------------- SVA toolbox
def _t(*rows):
    """`(edge, a, b)` triples -> trace rows. `a` is an input, `b` an output."""
    return [{"edge": e, "inputs": {"a": a}, "outputs": {"b": b}}
            for e, a, b in rows]


def _a(r):
    return r["inputs"]["a"] == 1


def _b(r):
    return r["outputs"]["b"] == 1


def test_the_activation_row_is_excluded_by_after_activation():
    """`|=>` against `|->`, and this is the gap that mattered most.

    The window OPENS at the activation row, so a consequent already true there
    satisfies `eventually` -- which is the exact vacuity this module was
    written to remove. Six of a2-i2c's fourteen vacuous checks evaluated the
    expectation on the SAME row as the activation, and the operators as first
    built still permitted it.
    """
    from specflow.refmodel.temporal import after, eventually, throughout

    # b is true AT the activation and false afterwards.
    w = after(_t((0, 1, 1), (2, 1, 0), (4, 0, 0)), _a)[0]
    assert eventually(w, _b)[0] is True, "|-> is satisfied at the activation"
    assert eventually(w, _b, after_activation=True)[0] is False, (
        "|=> must not be satisfied by the activation instant itself")
    assert throughout(w, _b)[0] is False
    assert throughout(w, lambda r: not _b(r), after_activation=True)[0] is True


def test_strong_eventually_convicts_where_weak_abstains():
    """A requirement that says the response MUST come is a strong liveness
    claim, and under weak semantics it can never be violated -- only left
    undecided. 11 of 105 requirements are phrased that way, and 5 of 14
    abstaining checks abstained for exactly this reason."""
    from specflow.refmodel.temporal import after, eventually

    w = after(_t((0, 1, 0), (2, 1, 0)), _a)[0]  # never closes
    assert not w.closed
    assert eventually(w, _b)[0] is None, "weak: we stopped looking"
    assert eventually(w, _b, strong=True)[0] is False, (
        "strong: the obligation was never discharged")


def test_sequence_is_ordering_and_three_eventuallys_are_not():
    """What `sequence` adds over a conjunction of `eventually` calls is exactly
    the ordering -- and three `eventually`s pass a design that does the three
    things backwards."""
    from specflow.refmodel.temporal import after, eventually, sequence

    rows = _t((0, 1, 0), (2, 1, 1), (4, 1, 0), (6, 0, 0))
    w = after(rows, _a)[0]
    b_on, b_off = _b, (lambda r: not _b(r))
    assert sequence(w, b_off, b_on, b_off)[0] is True
    # Backwards: b is never off-then-on-then-off in THAT order twice over.
    assert sequence(w, b_on, b_off, b_on)[0] is False
    # Both orders satisfy a bare conjunction of eventuallys, which is the point.
    assert eventually(w, b_on)[0] and eventually(w, b_off)[0]


def test_never_and_until_and_nexttime():
    from specflow.refmodel.temporal import after, never, nexttime, until

    w = after(_t((0, 1, 0), (2, 1, 0), (4, 1, 1), (6, 0, 1)), _a)[0]
    assert never(w, _b)[0] is False, "b does occur inside the window"
    assert never(w, lambda r: r["outputs"]["b"] == 9)[0] is True

    # `##1`: ORDERING, not a cycle count -- a row is a state, so "the next row"
    # is "the next time anything changed".
    assert nexttime(w, lambda r: not _b(r))[0] is True
    assert nexttime(w, _b)[0] is False

    # p until q, weak and strong.
    assert until(w, lambda r: not _b(r), _b)[0] is True
    closed = after(_t((0, 1, 0), (2, 1, 0), (4, 0, 0)), _a)[0]
    assert closed.closed
    assert until(closed, lambda r: not _b(r), _b)[0] is True, "weak: no release needed"
    assert until(closed, lambda r: not _b(r), _b, strong=True)[0] is False


def test_first_match_and_overlapping_attempts():
    """SVA starts an attempt at EVERY tick the antecedent holds, so attempts
    run concurrently; the default here scans past a window first. Right for a
    serialized protocol, wrong for a pipelined one."""
    from specflow.refmodel.temporal import after, first_match

    # `a` rises three times; each window runs to the next `b`.
    rows = _t((0, 1, 0), (1, 0, 0), (2, 1, 0), (3, 0, 0), (4, 1, 0), (5, 0, 1))
    serial = after(rows, _a, until=_b)
    assert len(serial) == 1, "the first window swallows the later rises"
    concurrent = after(rows, _a, until=_b, overlap=True)
    assert [w.edge for w in concurrent] == [0, 2, 4]
    assert [w.edge for w in first_match(concurrent)] == [0]
    assert first_match([]) == []


def test_past_is_one_row_not_a_cycle_count():
    """`$past(sig)` -- what it was before this happened -- is not a count.
    `$past(sig, 3)` is, and Phases 3-6 severed those."""
    from specflow.refmodel.temporal import after

    w = after(_t((0, 0, 1), (2, 1, 0)), _a)[0]
    assert w.edge == 2
    assert w.past("b") == 1, "the value on the row before the activation"
    assert w.value("b") == 0, "the value AT the activation"
    first = after(_t((0, 1, 1),), _a)[0]
    assert first.past("b") is None, "no previous sample to name"
