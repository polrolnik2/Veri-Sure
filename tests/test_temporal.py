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

import pytest

from specflow.refmodel.temporal import (TO_END, WHILE_ACTIVE, after, edges,
                                        eventually, never,
                                        nexttime, nth, pulse, sequence, stable,
                                        throughout, until, worst)
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



def _while(trace, act):
    """The window the old bare `after` gave: the activation's own extent.

    These tests are about where the TRIGGER sits relative to the window, not
    about how far the window runs. Under the new default a bare `after` runs to
    the end of the trace and every operator over an unclosed window reports
    UNKNOWN -- correct, and not what these fixtures are measuring. Saying
    `until=` here is the discipline the default change exists to force.
    """
    return after(trace, act, until=lambda r: not act(r))


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
    w = after(one, lambda r: r["inputs"]["cmd"] == 8, until=TO_END)
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


def test_there_is_NO_DEFAULT_WINDOW_and_both_ends_are_named():
    """`until` is required, and that is the point.

    Every default is silently wrong for one of the two idioms, and the mistake
    is invisible where checks are screened. Scoping a bare window to its
    activation is right for "WHILE A, B holds" and wrong for "after A,
    eventually B" -- an instant's extent is one or two rows, so the consequence
    falls outside and the check CAN ONLY CONVICT. Running it to the end is right
    for the second and wrong for the first.

    MEASURED on 96 frozen checks against KNOWN-GOOD RTL, same traces: the
    activation-scoped rule convicted the correct design 15 times, the
    open-ended rule 14 -- and swapped WHICH ones, 3 fixed and 3 newly broken.
    Neither is detectable at screening, because the Python witness distinguishes
    fewer states than the RTL, so a window too narrow for the design can still
    cover the witness's latency.

    So the choice is the author's, and a missing `until` is a TypeError --
    which `well_formed`'s smoke run turns into a rejected oracle at authoring
    time, instead of a quiet wrong verdict months later.
    """
    trace = [_state(0, cmd=8), _state(1), _state(2), _state(3, ack=1)]
    act = lambda r: r["inputs"]["cmd"] == 8            # noqa: E731

    with pytest.raises(TypeError):
        after(trace, act)

    to_end = after(trace, act, until=TO_END)[0]
    assert [r["edge"] for r in to_end.rows] == [0, 1, 2, 3]
    assert eventually(to_end, lambda r: r["outputs"]["ack"] == 1)[0] is True

    while_active = after(trace, act, until=WHILE_ACTIVE)[0]
    assert [r["edge"] for r in while_active.rows] == [0, 1]
    assert eventually(while_active, lambda r: r["outputs"]["ack"] == 1)[0] is False

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
    from specflow.refmodel.temporal import eventually, throughout

    # b is true AT the activation and false afterwards.
    w = _while(_t((0, 1, 1), (2, 1, 0), (4, 0, 0)), _a)[0]
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
    from specflow.refmodel.temporal import eventually

    w = _while(_t((0, 1, 0), (2, 1, 0)), _a)[0]  # never closes
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
    w = after(rows, _a, until=lambda r: r["edge"] >= 4)[0]
    b_on, b_off = _b, (lambda r: not _b(r))
    assert sequence(w, b_off, b_on, b_off)[0] is True
    # Backwards: b is never off-then-on-then-off in THAT order twice over.
    assert sequence(w, b_on, b_off, b_on)[0] is False
    # Both orders satisfy a bare conjunction of eventuallys, which is the point.
    assert eventually(w, b_on)[0] and eventually(w, b_off)[0]


def test_never_and_until_and_nexttime():
    from specflow.refmodel.temporal import never, nexttime, until

    w = _while(_t((0, 1, 0), (2, 1, 0), (4, 1, 1), (6, 0, 1)), _a)[0]
    assert never(w, _b)[0] is False, "b does occur inside the window"
    assert never(w, lambda r: r["outputs"]["b"] == 9)[0] is True

    # `##1`: ORDERING, not a cycle count -- a row is a state, so "the next row"
    # is "the next time anything changed".
    assert nexttime(w, lambda r: not _b(r))[0] is True
    assert nexttime(w, _b)[0] is False

    # p until q, weak and strong.
    assert until(w, lambda r: not _b(r), _b)[0] is True
    closed = _while(_t((0, 1, 0), (2, 1, 0), (4, 0, 0)), _a)[0]
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

    w = _while(_t((0, 0, 1), (2, 1, 0)), _a)[0]
    assert w.edge == 2
    assert w.past("b") == 1, "the value on the row before the activation"
    assert w.value("b") == 0, "the value AT the activation"
    first = _while(_t((0, 1, 1),), _a)[0]
    assert first.past("b") is None, "no previous sample to name"


# ------------------------------------------- `|=>` on every window operator
def _t3(*rows):
    """`(edge, a, b, c)` -> rows. `a` drives the window, `b`/`c` are outputs."""
    return [{"edge": e, "inputs": {"a": a}, "outputs": {"b": b, "c": c}}
            for e, a, b, c in rows]


def _c(r):
    return r["outputs"]["c"] == 1


def test_every_window_operator_accepts_after_activation():
    """THE REGRESSION THIS EXISTS FOR, and it was a live defect.

    `after_activation` is DERIVED from the normalized schema (`effect_follows`)
    and the prompt tells the check author to pass it through. So the author
    passes it to whichever operator the requirement needs -- and six of the
    eight raised `TypeError`, because only `eventually` and `throughout`
    accepted it. Measured on the stage run over a2-i2c's 40 broken checks:
    REQ-0013, REQ-0076 and REQ-0103 were rejected as malformed with
    `never() got an unexpected keyword argument 'after_activation'` and the
    same for `pulse()`, and REQ-0076 hit it twice across three repair rounds.

    A kwarg that is correct on two operators and fatal on six is not an API,
    and no amount of prompt wording fixes it -- so this asserts the surface,
    operator by operator, rather than any one behaviour.
    """
    w = _while(_t3((0, 1, 1, 1), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    for name, call in (
            ("eventually", lambda: eventually(w, _b, after_activation=True)),
            ("throughout", lambda: throughout(w, _b, after_activation=True)),
            ("stable", lambda: stable(w, "b", after_activation=True)),
            ("pulse", lambda: pulse(w, "b", after_activation=True)),
            ("never", lambda: never(w, _b, after_activation=True)),
            ("nexttime", lambda: nexttime(w, _b, after_activation=True)),
            ("sequence", lambda: sequence(w, _b, after_activation=True)),
            ("until", lambda: until(w, _b, _c, after_activation=True)),
    ):
        ok, _, _ = call()                       # must not raise
        assert ok in (True, False, None), name


def test_never_after_activation_ignores_a_prohibition_met_at_the_trigger():
    """"Once X, never Y" says nothing about the row X arrived on."""
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    assert never(w, _b)[0] is False, "b occurs at the activation row"
    assert never(w, _b, after_activation=True)[0] is True


def test_stable_after_activation_takes_its_baseline_after_the_trigger():
    """The activation row catches the port mid-transition.

    Without this, a port that settles one row after the trigger and then holds
    is reported as unstable -- which is the over-strictness half of the same
    defect `eventually` had.
    """
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 1, 0, 0), (6, 0, 0, 0)), _a)[0]
    assert stable(w, "b")[0] is False, "b moves 1 -> 0 across the trigger"
    assert stable(w, "b", after_activation=True)[0] is True


def test_pulse_after_activation_does_not_count_a_pulse_at_the_trigger():
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    assert pulse(w, "b")[0] is True, "one one-edge pulse, at the activation"
    ok, _, detail = pulse(w, "b", after_activation=True)
    assert ok is False and "never went to 1" in detail


def test_sequence_after_activation_cannot_match_step_one_at_the_trigger():
    """Three `eventually`s pass a design that does the three things backwards;
    a `sequence` whose first step is satisfied by the activation row itself
    passes one that never starts."""
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    assert sequence(w, _b, lambda r: not _b(r))[0] is True
    ok, _, detail = sequence(w, _b, lambda r: not _b(r), after_activation=True)
    assert ok is False and "step 1 of 2" in detail


def test_until_after_activation_is_not_discharged_by_a_release_at_the_trigger():
    """The sharpest of the six: a release already true at the activation
    discharges the obligation instantly, so a real violation one row later is
    never looked at. `until` is weak, so this reads as a PASS."""
    w = _while(_t3((0, 1, 1, 1), (2, 1, 0, 0), (4, 1, 0, 1), (6, 0, 0, 0)), _a)[0]
    assert until(w, _c, _b)[0] is True, "released at the activation instant"
    ok, edge, detail = until(w, _c, _b, after_activation=True)
    assert ok is False and edge == 2 and "before any release" in detail


def test_nexttime_is_already_after_the_activation_and_says_so_when_overridden():
    """`##1` is DEFINED at the row after the trigger, so `after_activation` is
    what this operator already is. It is accepted so the derived value can be
    passed through mechanically, defaults to True, and a `False` is reported
    rather than silently turning `nexttime` into a predicate at the trigger --
    an operator that quietly becomes a different operator on a keyword is worse
    than one that ignores it."""
    w = _while(_t3((0, 1, 0, 0), (2, 1, 1, 0), (4, 0, 0, 0)), _a)[0]
    assert nexttime(w, _b)[0] is True
    assert nexttime(w, _b, after_activation=True) == nexttime(w, _b)
    ok, _, detail = nexttime(w, _b, after_activation=False)
    assert ok is True, "the verdict is unchanged"
    assert "ignored" in detail and "`##1`" in detail


# ------------------------------------------------ SVA soundness fixes (§17.2)
# Each pin below is a case that was WRONG before the fix. The comment on each
# says what it returned, because a pin whose failure mode is not written down
# gets "corrected" back to the defect by the next reader.


def test_an_empty_row_set_is_unknown_in_every_window_operator():
    """RETURNED `True` FROM `throughout` AND `never`, WHICH IS A VACUOUS PASS.

    `after_activation=True` on a one-row window leaves `w.body` empty. An
    invariant that held over zero rows did not hold; a prohibition that was not
    violated over zero rows was not tested. `stable` already guarded this and
    the other three did not, so the module written to remove vacuous passes
    contained one -- reachable, measured on c1-i2c, by 39 of 110 oracles, which
    call `throughout` or `never` with `after_activation=`.
    """
    # The activation on the LAST row of the trace: `after` seeds `rows` with
    # the trigger and never appends, so `body` is empty.
    w = _while(_t3((0, 0, 0, 0), (2, 1, 1, 0)), _a)[0]
    assert w.body == [], "the fixture must actually produce an empty body"
    for name, verdict in (
        ("throughout", throughout(w, lambda r: False, after_activation=True)),
        ("never", never(w, lambda r: True, after_activation=True)),
        ("stable", stable(w, "b", after_activation=True)),
        ("pulse", pulse(w, "b", after_activation=True)),
    ):
        assert verdict[0] is None, f"{name} decided something over zero rows"
        assert "no rows" in verdict[2], f"{name} does not say why"


def test_throughout_and_never_still_decide_when_there_are_rows():
    """The counter-case: the empty guard must not swallow a real verdict."""
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    assert throughout(w, _b)[0] is False, "b is 0 at edge 2"
    assert throughout(w, lambda r: True)[0] is True
    assert never(w, _b)[0] is False, "b IS 1 at the activation"
    assert never(w, lambda r: False)[0] is True


def test_pulse_needs_evidence_of_a_rise_not_just_an_active_value():
    """RETURNED `(True, 'pulsed once for 1 edge(s)')` FOR A PORT ALREADY HIGH.

    The window opens while `b` is already 1 and `b` never rises inside it, so
    no pulse occurred there -- but the run was counted and the check passed the
    exact design it exists to catch. `w.prev` is the evidence: it is `$past` at
    the activation, and it says the port was already active.
    """
    w = _while(_t3((0, 0, 1, 0), (2, 1, 1, 0), (4, 1, 0, 0), (6, 0, 0, 0)), _a)[0]
    assert w.prev is not None and w.prev["outputs"]["b"] == 1
    ok, _, detail = pulse(w, "b")
    assert ok is None, "no rise was witnessed, so the width is not measurable"
    assert "already 1 before the window" in detail


def test_pulse_accepts_a_rise_at_the_first_row_it_looks_at():
    """The counter-case, and the reason the guard reads `prev` rather than just
    `rows[0]`: a port that rises exactly as the window opens HAS pulsed, and
    convicting it would trade the vacuity for over-strictness."""
    w = _while(_t3((0, 0, 0, 0), (2, 1, 1, 0), (4, 1, 0, 0), (6, 0, 0, 0)), _a)[0]
    assert w.prev["outputs"]["b"] == 0, "it was at rest before the window"
    ok, edge, _ = pulse(w, "b")
    assert ok is True and edge == 2, "and the edge names where it BEGAN"


def test_pulse_at_the_very_start_of_a_trace_is_not_convicted():
    """No preceding sample is not evidence of a missing rise. A window opening
    on the trace's first row has `prev is None` -- the design has just come out
    of reset, and a port at its active value there has genuinely just
    asserted."""
    w = _while(_t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 0, 0, 0)), _a)[0]
    assert w.prev is None
    assert pulse(w, "b")[0] is True


def test_edges_skips_a_row_that_carries_no_sample():
    """RAISED `TypeError` ON rise/fall, AND REPORTED A PHANTOM EDGE ON change.

    `_val` returns `None` both for a port absent from the row and for one the
    harness could not read -- a DUT not exposing a declared output samples as
    `None`. Neither is a transition. `None > 0` killed the whole check on
    rise/fall; on change it was quieter and worse, reporting an edge where the
    sample went missing and another where it came back.
    """
    trace = [{"edge": 0, "inputs": {"a": 0}, "outputs": {}},
             {"edge": 1, "inputs": {}, "outputs": {}},
             {"edge": 2, "inputs": {"a": 1}, "outputs": {}}]
    assert edges(trace, "a", "rise") == {2}, "one rise, 0 -> 1, across the gap"
    assert edges(trace, "a", "fall") == set()
    assert edges(trace, "a", "change") == {2}, "NOT {1}, the row with no sample"


def test_worst_names_the_furthest_window_on_the_all_passing_path():
    """RETURNED THE FIRST. The failing and unknown paths name the EARLIEST
    offending window, because the first counterexample explains the rest. A
    pass has no counterexample, so the useful thing to name is how far the
    evidence reached -- naming the first told a reader the requirement held at
    the earliest place it could have, which reads as weaker evidence than was
    gathered."""
    assert worst([(True, 3, "first"), (True, 9, "last")]) == (True, 9, "last")
    assert worst([(True, 3, "p"), (False, 9, "f")])[1] == 9, "failure wins"
    assert worst([(None, 3, "u"), (True, 9, "p")])[1] == 3, "earliest unknown"


def test_the_two_untils_state_one_release_rule_between_them():
    """`after(..., until=)` DEFINES a window and skips the trigger row, so a
    release already true at the activation cannot collapse it to nothing. The
    `until()` OPERATOR asserts inside a window someone else defined, so it
    reads every row it is handed. Both are right; the pin exists because two
    operators spelled the same way, differing silently, is how a check answers
    a question nobody asked."""
    trace = _t3((0, 1, 1, 0), (2, 1, 0, 0), (4, 1, 1, 0), (6, 0, 0, 0))
    w = after(trace, _a, until=_b)[0]
    assert [r["edge"] for r in w.rows] == [0, 2, 4], "the release AT 0 is skipped"
    assert until(w, lambda r: True, _b)[1] == 0, "the operator reads row 0"
    assert until(w, lambda r: True, _b, after_activation=True)[1] == 4


# ------------------------------------------------- `disable iff`: aborts_on


def _rows(at=None, n=8):
    """`at` maps edge -> {port: value} on outputs."""
    out = []
    for i in range(n):
        o = {"al": 0, "rst": 0, "x": 0}
        o.update((at or {}).get(i, {}))
        out.append({"edge": i, "inputs": {"cmd": 1}, "outputs": o})
    return out


def _cmd(r):
    return r["inputs"]["cmd"] == 1


def test_an_aborted_window_decides_nothing():
    """SVA's `disable iff`, and the whole point of the field. A command cut
    short by reset or arbitration loss owes nothing, so every operator returns
    UNKNOWN over it -- not a pass, which would hide a real defect, and not a
    failure, which convicts a design for not doing what it was never asked."""
    rows = _rows(at={3: {"al": 1}})
    w = after(rows, _cmd, until=lambda r: False,
                aborts=lambda r: r["outputs"]["al"] == 1)[0]
    assert w.aborted and w.closed
    # EVERY operator that takes a Window. Listed exhaustively rather than
    # spot-checked: the guard is one line per operator and the failure mode of
    # forgetting one is a single check that silently keeps convicting.
    for verdict in (eventually(w, lambda r: r["outputs"]["x"] == 1, strong=True),
                    throughout(w, lambda r: r["outputs"]["x"] == 1),
                    never(w, lambda r: r["outputs"]["x"] == 0),
                    stable(w, "x"),
                    pulse(w, "x"),
                    nexttime(w, lambda r: r["outputs"]["x"] == 1),
                    sequence(w, lambda r: r["outputs"]["x"] == 1, strong=True),
                    # `nth` guards by DELEGATION -- it is sugar over `sequence`
                    # and owns no scan of its own. Exercised here anyway: the
                    # roster below is a promise about behaviour, not about
                    # which function happens to hold the `if w.aborted` line,
                    # and a later rewrite that gave `nth` its own scan would
                    # otherwise lose the guard silently.
                    nth(w, lambda r: r["outputs"]["x"] == 1, 2, strong=True),
                    until(w, lambda r: r["outputs"]["x"] == 1,
                          lambda r: False, strong=True)):
        assert verdict[0] is None, verdict
        assert "aborted" in verdict[2], verdict

    import inspect

    from specflow.refmodel import temporal as _t
    takes_a_window = {
        n for n, f in vars(_t).items()
        if not n.startswith("_") and inspect.isfunction(f)
        and list(inspect.signature(f).parameters)[:1] == ["w"]}
    assert takes_a_window == {"eventually", "throughout", "stable", "pulse",
                              "never", "nexttime", "sequence", "until",
                              "nth"}, (
        "a new Window operator needs an `if w.aborted` guard and a line "
        f"above: {takes_a_window}")


def test_the_abort_row_is_reported_not_swallowed():
    """`ok is None` covers two different facts -- "the scenario never occurred"
    and "it occurred and was cut short" -- which route to different parties.
    The edge is what tells them apart in a report."""
    rows = _rows(at={3: {"rst": 1}})
    w = after(rows, _cmd, until=lambda r: False,
                aborts=lambda r: r["outputs"]["rst"] == 1)[0]
    ok, edge, detail = eventually(w, lambda r: False, strong=True)
    assert (ok, edge) == (None, 3), (ok, edge)
    assert "edge 3" in detail


def test_an_abort_beats_a_close_on_the_same_row():
    """They describe one instant from two sides -- "it stopped" and "it
    finished" -- and reading it as a finish is what makes a cut-short attempt
    look like a missing response. The abort wins, so the ambiguity resolves
    toward saying nothing rather than toward convicting."""
    rows = _rows(at={3: {"al": 1, "x": 0}})
    same = lambda r: r["outputs"]["al"] == 1          # noqa: E731
    w = after(rows, _cmd, until=same, aborts=same)[0]
    assert w.aborted, "a row that both closes and aborts must abort"
    assert eventually(w, lambda r: r["outputs"]["x"] == 1, strong=True)[0] is None


def test_without_aborts_nothing_changes():
    """The field is inert until used. Every frozen check predates it and must
    decide exactly as before."""
    rows = _rows(at={3: {"al": 1}})
    w = after(rows, _cmd, until=lambda r: r["edge"] == 5)[0]
    assert not w.aborted
    ok, _e, _d = eventually(w, lambda r: r["outputs"]["x"] == 1, strong=True)
    assert ok is False, "a real close with no evidence is still a conviction"


def _row(edge, p, held=None):
    r = {"edge": edge, "inputs": {"p": p}, "outputs": {}}
    if held is not None:
        r["held"] = held
    return r


def test_runs_selects_by_length_in_EDGES_not_rows():
    """`runs` is `sustains`'s window opener, and `held` is the whole subtlety.

    The trace is state-compressed, so a 5-edge low is ONE row carrying
    `held: 5`. Counting rows would call it a one-edge glitch -- which is
    exactly backwards for a majority filter, where the short run is the one
    that must be suppressed and the long one the one that must get through.
    """
    from specflow.refmodel.temporal import runs

    trace = [_row(0, 1), _row(1, 1), _row(2, 0), _row(3, 1),
             _row(4, 1), _row(5, 0), _row(6, 0), _row(7, 0), _row(8, 1)]
    assert runs(trace, "p", value=0, at_most=1) == {2}
    assert runs(trace, "p", value=0, at_least=2) == {5}

    # One row, five edges: long, and emphatically not short.
    packed = [_row(0, 0, held=5), _row(1, 1)]
    assert runs(packed, "p", value=0, at_least=2) == {0}
    assert runs(packed, "p", value=0, at_most=1) == set()


def test_a_run_still_open_at_the_end_of_trace_cannot_be_called_SHORT():
    """Its length is a lower bound, not a measurement.

    Admitting it under `at_most` would let the trace running out masquerade as
    a glitch the design was supposed to suppress -- a false activation, which
    is the failure mode that produces a check convicting a correct design.
    Under `at_least` it is fine: what was already seen clears the floor.
    """
    from specflow.refmodel.temporal import runs

    trailing = [_row(0, 1), _row(1, 0)]
    assert runs(trailing, "p", value=0, at_most=1) == set()
    assert runs(trailing, "p", value=0, at_least=1) == {1}


def test_runs_refuses_to_select_everything():
    """No bound is not a wide net, it is a missing statement.

    Same rule `normalize.Sustain` enforces on the schema side: an entry with
    neither bound constrains nothing, and silently matching every run would
    hand the author an activation that fires constantly.
    """
    import pytest

    from specflow.refmodel.temporal import runs

    with pytest.raises(ValueError, match="neither at_least nor at_most"):
        runs([_row(0, 0)], "p", value=0)


def test_nth_is_goto_repetition_and_was_reachable_all_along():
    """`nth(w, p, n)` is `p[->n]`, and `sequence` already implemented it.

    `sva-divergence.md` D8 recorded `[->n]` as "simply not built" -- a claim
    made from the operator TABLE, where it does not appear, rather than from
    the semantics, where it does: sequence steps are `##[1:$]` and each
    strictly advances, so repeating one predicate n times counts occurrences.
    The gap was discoverability, not expressiveness.
    """
    from specflow.refmodel.temporal import after, nth

    trace = [{"edge": i,
              "inputs": {"go": 1 if i == 1 else 0,
                         "p": 1 if i in (2, 5, 9, 12) else 0},
              "outputs": {}} for i in range(16)]
    w = after(trace, lambda r: r["inputs"]["go"] == 1,
              until=lambda r: r["inputs"].get("done") == 1)[0]
    p = lambda r: r["inputs"]["p"] == 1  # noqa: E731

    # Four occurrences: the fourth is found, the fifth is not.
    assert nth(w, p, 4, strong=True)[0] is True
    assert nth(w, p, 5, strong=True)[0] is False


def test_nth_counts_occurrences_where_runs_measures_duration():
    """The two cycle-accurate axes, and neither substitutes for the other.

    A port that pulses four times has four OCCURRENCES and no long RUN; one
    held low for four edges has one run and one occurrence. Reading either
    through the other inverts the property -- which is the failure `runs`'
    own `held` warning is about, arriving from the other direction.
    """
    from specflow.refmodel.temporal import after, nth, runs

    pulsing = [{"edge": i, "inputs": {"go": 1 if i == 1 else 0,
                                      "p": 1 if i in (2, 4, 6, 8) else 0},
                "outputs": {}} for i in range(12)]
    w = after(pulsing, lambda r: r["inputs"]["go"] == 1,
              until=lambda r: r["inputs"].get("done") == 1)[0]
    p = lambda r: r["inputs"]["p"] == 1  # noqa: E731

    assert nth(w, p, 4, strong=True)[0] is True          # four occurrences
    assert runs(pulsing, "p", value=1, at_least=2) == set()   # no run of two
