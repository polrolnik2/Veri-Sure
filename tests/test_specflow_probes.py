

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


def test_a_cross_constraint_must_quote_the_specification_verbatim():
    """**A CROSS-CONSTRAINT IS A REQUIREMENT, WHICH IS MORE POWER THAN A
    PROBE, NOT LESS -- and it had no licensing check at all.**

    `contract_linter.probe_issues` verifies every PROBE's spans verbatim
    against the specification, "what stops the stage that proposes probes from
    inventing one". The cross-constraint gate checked only that the probe named
    exists and the ports are declared.

    A probe adds a NAME. A cross-constraint adds an OBLIGATION that checks are
    written against and designs are convicted by, and it is the only
    requirement in the system minted outside S1. An invented one convicts
    correct designs -- audit, paid at the far end where it looks like an
    over-strict check.
    """
    from specflow.probes import (CrossConstraint, ProbeEntry, ProbeOutput,
                                 gate)

    SPEC = "While `slave_wait` is active, the timing counter is paused."
    contract = {"io": [{"name": "q", "dir": "output", "width": 1}]}

    def run(span: str):
        out = ProbeOutput(
            probes=[ProbeEntry(name="slave_wait", licensed_by=["REQ-0000"],
                               spans=[SPEC])],
            cross_constraints=[CrossConstraint(
                text="the counter pauses", probe="slave_wait",
                ports=["q"], span=span)])
        return [i for i in gate(out, contract=contract, spec=SPEC,
                                requirements=[{"uid": "REQ-0000"}])
                if "cross_constraints" in i.path]

    assert run(SPEC) == [], "a verbatim quotation is licensed"
    #: Line wrapping is not drift -- the linter's own rule.
    assert run("While `slave_wait` is active,\n  the timing counter is paused.") == []
    #: A PARAPHRASE LICENSES NOTHING. This is the case that matters: it is what
    #: an invented obligation looks like, and it reads plausibly.
    bad = run("the counter stops while the slave is holding the line")
    assert bad and "verbatim" in bad[0].message
    #: And no span at all.
    none = run("")
    assert none and "quotes no specification text" in none[0].message
