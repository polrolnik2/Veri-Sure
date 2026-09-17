"""The generation-stage variety lever: cells, blindness, and the brief.

The brief's contract is the load-bearing part -- the population is a POINTER,
not an oracle -- so most of these tests are about what an author is NOT told.
"""

from __future__ import annotations

import inspect

from specflow import variety as V


def _rows(*vals: int) -> list[dict]:
    return [{"outputs": {"busy": v, "ack": 0}, "inputs": {"a": 1}, "edge": i}
            for i, v in enumerate(vals)]


POP = {
    "A": {"TP-0": _rows(0, 1), "TP-1": _rows(0, 0)},
    "B": {"TP-0": _rows(0, 0), "TP-1": _rows(0, 0)},   # differs from A on TP-0
    "C": {"TP-0": _rows(0, 1), "TP-1": _rows(0, 0)},   # a clone of A
}


def test_a_cell_is_a_port_not_a_testpoint():
    """A testpoint where two designs differ says 'somewhere in here'; a port
    says where to look, and that is the resolution an author can act on."""
    got = V.cells(POP, ["busy", "ack"])
    assert {(c.testpoint, c.port, c.pair) for c in got} == {
        ("TP-0", "busy", ("A", "B")), ("TP-0", "busy", ("B", "C"))}
    assert all(c.port != "ack" for c in got), "ack never disagrees"


def test_a_missing_replay_is_not_a_disagreement():
    """Absence is not evidence. Counting a testpoint one design never ran as a
    cell manufactures authoring targets out of a replay that did not happen --
    the conflation `must_fail` had to remove when never-triggered replays were
    counted as the evidence licensing a conviction."""
    partial = {"A": {"TP-0": _rows(0, 1)}, "B": {}}
    assert V.cells(partial, ["busy"]) == ()


def test_separation_is_polarity_corrected_and_objection_is_not():
    """A check convicting BOTH designs objects to the cell and separates
    nothing. Objecting to both sides is how a blindness score was gamed once
    before, so constriction reads `separates` -- while `objects_to_either` is
    kept because every published blindness figure here uses it."""
    cell = V.Cell(testpoint="TP-0", port="busy", left="A", right="B")

    convicts_both = {"A": False, "B": False}
    assert V.objects_to_either(cell, convicts_both)
    assert not V.separates(cell, convicts_both), (
        "convicting everything is not telling designs apart")

    discriminates = {"A": False, "B": True}
    assert V.separates(cell, discriminates)

    #: an abstention on either side is not a separation
    assert not V.separates(cell, {"A": None, "B": True})
    assert not V.separates(cell, {"A": False, "B": None})


def test_blindness_composes_so_adding_a_check_can_only_close_holes():
    """Scored over the SET, never per check. Per check, 'adding 17 checks each
    measured less blind than its parent took the blind-check count from 121 to
    136' -- a metric that worsens when you add a check is measuring the
    denominator."""
    cs = V.cells(POP, ["busy"])
    assert V.blind(cs, {}) == cs, "no checks means every cell is blind"

    closes_ab = {"A": False, "B": True, "C": False}
    after = V.blind(cs, {"c1": closes_ab})
    assert len(after) < len(cs)
    #: adding a second check cannot re-open what the first closed
    assert set(V.blind(cs, {"c1": closes_ab, "c2": {}})) <= set(after)


def test_blind_defaults_to_separation_and_the_weaker_predicate_is_opt_in():
    """The two predicates disagree exactly where it matters: a check that
    convicts BOTH designs closes the cell under the recorded definition and
    closes nothing under polarity correction. Defaulting to the weaker one
    would silently credit a blunderbuss with constriction it does not do."""
    cs = V.cells(POP, ["busy"])
    convicts_everything = {d: False for d in POP}

    assert V.blind(cs, {"c1": convicts_everything}) == cs, (
        "polarity-corrected: convicting everything separates nothing")
    assert V.blind(cs, {"c1": convicts_everything},
                   polarity_corrected=False) == (), (
        "the recorded predicate counts it as closed -- kept only so published "
        "blindness figures stay comparable")


def test_targets_are_ranked_by_port_not_enumerated_by_cell():
    """Forty briefs for one blind port buys forty near-copies of one check,
    which is the failure mode this module exists to avoid."""
    cs = [V.Cell("TP-0", "busy", "A", "B"), V.Cell("TP-1", "busy", "A", "B"),
          V.Cell("TP-0", "ack", "A", "B")]
    assert V.ranked(cs) == (("busy", 2), ("ack", 1))


# ------------------------------------------------- the brief's contract


#: distinctive names on purpose -- single letters collide with English words,
#: so a leak would hide behind "A check ..." and the test would pass on noise.
CELL = V.Cell(testpoint="TP-0", port="busy",
              left="zulufox", right="quebecvane")
BRIEF = V.brief(CELL, requirement="busy rises on START and clears on STOP",
                activation="a START is presented",
                driven={"a": 1, "cmd": 4})


def test_the_brief_names_the_location_and_the_requirement():
    for fragment in ("busy rises on START", "a START is presented",
                     "`busy`", "TP-0", "a=1", "cmd=4"):
        assert fragment in BRIEF, fragment


def test_the_brief_never_names_a_design_or_implies_one_is_correct():
    """The population is a POINTER, not an oracle. Presenting two behaviours and
    asking which the spec means makes them the answer set -- and reproduces the
    pathology the witness must-pass leg was deleted for: it "does not make the
    check more correct, it makes the check agree with the witness" (h-i2c,
    over-strictness 27 -> 15, convictions 2 -> 16)."""
    assert CELL.left not in BRIEF and CELL.right not in BRIEF, (
        "the cell carries design names; they must never be rendered")
    lowered = BRIEF.lower()
    for banned in ("correct one", "which is right", "design a", "design b",
                   "one of them", "the right behaviour", "expected value"):
        assert banned not in lowered, banned
    #: and it offers the honest exit, so a gap in the SPEC is reportable
    assert "say so in `reasoning` and write no check" in BRIEF
    assert "worse than an honest report" in BRIEF


def test_no_parameter_could_carry_a_design_or_its_values():
    """The enforcement is structural, as it is in `variants.build_prompt`: an
    instruction not to look is not a guarantee, a missing parameter is."""
    params = set(inspect.signature(V.brief).parameters)
    assert params == {"cell", "requirement", "activation", "driven"}
    for leaky in ("design", "designs", "source", "rows", "trace", "values",
                  "observed", "population", "witness", "reference"):
        assert leaky not in params, leaky


# ------------------------------------------------ the constriction report


def _verdicts(**by_check):
    return by_check


def test_a_design_is_accepted_when_nothing_convicts_it_and_rejections_union():
    """"A design is rejected when ANY of 114 members objects" -- so adding
    checks constricts monotonically and the risk is always over-constriction."""
    cs = V.cells(POP, ["busy"])
    one = V.constrict(cs, _verdicts(c1={"A": True, "B": False, "C": True}),
                      POP, ["busy"])
    assert one.accepted == ("A", "C")

    two = V.constrict(
        cs, _verdicts(c1={"A": True, "B": False, "C": True},
                      c2={"A": False, "B": True, "C": False}), POP, ["busy"])
    assert two.accepted == (), "a second objector can only shrink the set"


def test_classes_collapse_behavioural_clones_and_diameter_grades_the_gap():
    """A and C are identical traces, so accepting both is ONE class, not two --
    the cardinality and the class count are different questions. Diameter is
    the graded version: how far from equivalence, not merely how many."""
    cs = V.cells(POP, ["busy"])
    got = V.constrict(cs, _verdicts(), POP, ["busy"])
    assert got.accepted == ("A", "B", "C")
    assert got.classes == 2, "A and C are trace-identical"
    assert got.diameter > 0.0, "B differs from both"

    clones_only = {k: POP[k] for k in ("A", "C")}
    tight = V.constrict(cs, _verdicts(), clones_only, ["busy"])
    assert tight.classes == 1 and tight.diameter == 0.0


def test_one_class_is_a_success_ONLY_if_the_control_is_still_admitted():
    """The sharpest threshold in the plan. E4b reproduced the failure: dropping
    the audit constraint took classes 8 -> 1 and diameter to 0.000 while the
    first check added convicted the control, so the surviving class excluded
    the known-good design."""
    cs = V.cells(POP, ["busy"])
    #: a set that convicts B, leaving the A/C class alone
    only_ac = _verdicts(c1={"A": True, "B": False, "C": True})

    kept = V.constrict(cs, only_ac, POP, ["busy"],
                       control={"c1": True})
    assert kept.classes == 1 and kept.admits_the_control is True

    lost = V.constrict(cs, only_ac, POP, ["busy"],
                       control={"c1": False})
    assert lost.classes == 1, "the same single class"
    assert lost.admits_the_control is False, (
        "one class that excludes the correct design is over-constriction, not "
        "success -- the number alone cannot tell them apart")

    unknown = V.constrict(cs, only_ac, POP, ["busy"])
    assert unknown.admits_the_control is None, "no control, no claim"


def test_the_reusable_report_reproduces_the_e4b_driver():
    """The driver computed accepted/classes/diameter inline. If the packaged
    function disagrees with it, one of them is wrong and the recorded 56.0%
    result is not reproducible."""
    cs = V.cells(POP, ["busy"])
    empty = V.constrict(cs, _verdicts(), POP, ["busy"])
    assert empty.blind == 1.0, "no checks means every cell is blind"
    assert set(empty.accepted) == set(POP)

    closes = _verdicts(c1={"A": True, "B": False, "C": True})
    after = V.constrict(cs, closes, POP, ["busy"])
    assert after.blind < empty.blind
    assert len(after.accepted) < len(empty.accepted)
    assert after.diameter <= empty.diameter, (
        "constriction must not widen the accepted set's spread")


# ------------------------------------------------------- the authoring pass


class _Port:
    """Records what it was shown, so a test can assert on the prompt."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.stages: list[str] = []

    def complete(self, *, stage, round_, prompt):
        self.prompts.append(prompt)
        self.stages.append(stage)
        if not self.replies:
            raise AssertionError("no reply queued")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _parse(reply):
    return (reply.get("source", ""), reply.get("reasoning", ""))


TARGETS = [("REQ-0001", V.Cell("TP-0", "busy", "zulufox", "quebecvane"))]
CTX = dict(requirement_of=lambda u: "busy rises on START",
           activation_of=lambda u: "a START is presented",
           driven_of=lambda c: {"a": 1}, parse=_parse)


def test_an_authored_check_comes_back_with_its_port():
    port = _Port([{"source": "def decide(trace): return True, 0, ''"}])
    got = V.author_at(TARGETS, port=port, **CTX)
    assert len(got) == 1 and got[0].port == "busy"
    assert not got[0].declined
    assert port.stages == ["variety_busy"], "one call per PORT, not per cell"


def test_declining_is_a_result_and_not_a_failure():
    """A requirement that does not constrain the port is a finding about the
    SPECIFICATION. If declining is not cheap the gap gets filled with an
    invention -- a model asked for something impossible complies rather than
    refuses, which is why `declines_discrimination` exists at all."""
    port = _Port([{"source": "", "reasoning": "the spec says nothing about busy here"}])
    got = V.author_at(TARGETS, port=port, **CTX)
    assert got[0].declined
    assert "says nothing" in got[0].reasoning


def test_a_failed_call_is_not_recorded_as_the_spec_being_silent():
    """A gateway outage is a fact about the call. Reading it as a decline would
    turn a network error into a specification finding."""
    port = _Port([TimeoutError("gateway")])
    got = V.author_at(TARGETS, port=port, **CTX)
    assert got[0].declined and got[0].reasoning.startswith(V.PARSE_ERROR)
    assert "TimeoutError" in got[0].reasoning

    bad = _Port([{"source": None}])           # parse blows up
    got = V.author_at(TARGETS, port=bad,
                      **{**CTX, "parse": lambda r: 1 / 0})
    assert got[0].reasoning.startswith(V.PARSE_ERROR)


def test_the_author_is_never_shown_a_design_or_its_values():
    """The pass is only as honest as what reaches the prompt, so this asserts on
    what the port actually received rather than on `brief` in isolation."""
    port = _Port([{"source": "x"}])
    V.author_at(TARGETS, port=port, **CTX)
    shown = port.prompts[0]
    assert "zulufox" not in shown and "quebecvane" not in shown
    assert "busy rises on START" in shown and "`busy`" in shown


def test_the_pass_is_judged_on_cells_closed_not_checks_returned():
    """The null to beat re-authored with a witness and reached "0 cells newly
    reached -- the rewrites' objections were a strict subset of what the set
    already caught". A subset is the null however many checks came back."""
    was_blind = [V.Cell("TP-0", "busy", "A", "B"),
                 V.Cell("TP-1", "busy", "A", "B")]
    closed = V.closed_by(
        {"new1": {"A": True, "B": False},        # separates
         "new2": {"A": False, "B": False},       # convicts both: separates none
         "new3": {"A": None, "B": None}},        # abstains
        was_blind)
    assert len(closed["new1"]) == 2
    assert closed["new2"] == (), "a blunderbuss closes nothing"
    assert closed["new3"] == ()


# ------------------------------------ ranking by constriction, not by mass


CELLS_MIXED = [
    V.Cell("TP-0", "wide", "acc1", "acc2"),    # both accepted: closing MUST shrink
    V.Cell("TP-1", "half", "acc1", "rej1"),    # one accepted
    V.Cell("TP-2", "dead", "rej1", "rej2"),    # neither: cannot change a verdict
    V.Cell("TP-3", "dead", "rej1", "rej2"),
    V.Cell("TP-4", "dead", "rej1", "rej2"),
]


def test_cells_between_already_rejected_designs_cannot_move_the_set():
    """The E4 pilot closed 96 of 249 cells soundly and moved the accepted set by
    nothing, because the cells lay between designs already rejected. Closing a
    cell convicts exactly one of its pair; convicting an already-rejected design
    changes no verdict."""
    got = V.constricting(CELLS_MIXED, accepted=["acc1", "acc2"])
    assert {c.port for c in got} == {"wide", "half"}
    assert all(c.port != "dead" for c in got)


def test_mass_ranking_and_constriction_ranking_disagree_and_that_is_the_point():
    """`dead` carries the most cells and is worth nothing. Ranking by mass sent
    the pilot at exactly that kind of port."""
    by_mass = V.ranked(CELLS_MIXED)
    assert by_mass[0] == ("dead", 3), "mass puts the useless port first"

    by_constriction = V.ranked(CELLS_MIXED, accepted=["acc1", "acc2"])
    assert dict(by_constriction) == {"wide": 2, "half": 1}
    assert "dead" not in dict(by_constriction)
    assert by_constriction[0][0] == "wide", (
        "both-accepted outranks one-accepted: closing it must shrink the set "
        "whichever side the new check convicts")


def test_an_empty_accepted_set_ranks_nothing_rather_than_everything():
    """Over-constricted already: no cell can change a verdict, and the honest
    answer is that authoring has no constriction target here -- not that every
    port is equally good."""
    assert V.ranked(CELLS_MIXED, accepted=[]) == ()
    assert V.constricting(CELLS_MIXED, accepted=[]) == ()


def test_both_accepted_is_the_only_guaranteed_constricting_target():
    """Touching ONE accepted design is necessary and not sufficient. The pilot's
    checks convicted `d, r, y` and `y` -- every one already rejected -- which is
    how 96 cells closed and the accepted set did not move. A cell with both
    designs accepted has no such escape: whichever side a closing check
    convicts, the set shrinks."""
    got = V.constricting(CELLS_MIXED, accepted=["acc1", "acc2"], both=True)
    assert [c.port for c in got] == ["wide"]
    assert len(V.constricting(CELLS_MIXED, accepted=["acc1", "acc2"])) == 2, (
        "the weaker predicate still admits the one-accepted cell")


def test_the_accepted_weighting_is_documented_as_a_diagnostic_not_a_target():
    """`accepted` reads the SUITE'S verdicts about UNVERIFIED designs, so using
    it to choose authoring targets filters evidence about the suite by the
    suite's own opinion -- the circularity this module exists to avoid, reached
    through arithmetic rather than prose.

    It is also fragile and non-monotone: measured, ONE check carries five of
    eight rejections, and dropping it returns three designs to the accepted set
    -- so removing a bad check re-values cells the weighting had zeroed.
    """
    for fn in (V.constricting, V.ranked):
        doc = fn.__doc__ or ""
        assert "NOT" in doc or "not" in doc
    assert "DO NOT TARGET WITH IT" in (V.constricting.__doc__ or "")
    assert "NOT AN AUTHORING TARGET" in (V.ranked.__doc__ or "").upper(), (
        "`ranked(accepted=...)` must say it is a diagnostic; the mass ranking "
        "is what reads only the designs and is safe to target with")
