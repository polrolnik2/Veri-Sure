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
