

def test_a_cross_constraint_declares_the_needs_that_make_it_ordinary():
    """**`needs` IS WHAT MAKES "AN ORDINARY REQUIREMENT" TRUE.**

    `cross_constraint_requirements` promises they "go through normalize, the
    check author and every existing gate exactly as any requirement does". S2
    covers a requirement only when it declares `needs=testplan`, and every
    requirement S1 mints declares `("testplan", "refmodel")`. These arrived
    with none -- the only requirements in the system minted outside S1, and so
    the only ones that could.

    It killed four of five full-pipeline runs. The model answered correctly and
    said so: "REQ-0151 does not declare needs=['testplan'], so it must not be
    covered by any testplan element" -- zero elements, and the gate failed it
    for producing nothing. Five repair rounds could not converge because the
    requirement was malformed, not the answer.
    """
    from specflow.probes import (CrossConstraint, ProbeOutput,
                                 cross_constraint_requirements)

    out = ProbeOutput(probes=[], cross_constraints=[
        CrossConstraint(text="while slave_wait is active the counter pauses",
                        probe="slave_wait", ports=[], span="")])
    got = cross_constraint_requirements(out, [{"uid": "REQ-0000"}])
    assert len(got) == 1
    #: THE SAME VALUE S1 MINTS, not merely non-empty: a cross-constraint that
    #: asked for a testplan and not a refmodel would be planned and then never
    #: checked.
    assert got[0]["needs"] == ["testplan", "refmodel"]
    assert got[0]["uid"] == "REQ-0001"


def test_every_field_an_s1_requirement_carries_is_carried_here_too():
    """The fan-out gates read requirement dicts by key. A field S1 always sets
    and this never does is a divergence that only shows up as a stage failing
    on an item it cannot explain -- which is how `needs` was found.
    """
    from specflow.probes import (CrossConstraint, ProbeOutput,
                                 cross_constraint_requirements)

    got = cross_constraint_requirements(
        ProbeOutput(probes=[], cross_constraints=[
            CrossConstraint(text="t", probe="p", ports=[], span="")]),
        [{"uid": "REQ-0000"}])[0]
    for field in ("uid", "text", "unit_kind", "needs", "spec_spans"):
        assert field in got, f"{field!r} is on every S1 requirement and not here"
