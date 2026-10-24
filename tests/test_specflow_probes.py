

def test_cross_constraints_are_not_minted_as_requirements():
    """**S1 HAS ALREADY MINTED EVERY ONE OF THEM.**

    The argument they were added on is that they tie a probe to real ports
    "where the spec STATES the relation" -- and if the spec states it, S1 mints
    a requirement from that sentence, because S1 divides the whole document.

    Measured on i2c_master_bit_ctrl: S1's obligations cover 15,523 of 15,713
    spec bytes (98.8%), and 14 of 14 cross-constraint spans fall inside an S1
    obligation whose quote is the same sentence. The cross-constraint text is a
    paraphrase of a requirement that already exists, handed a second uid.

    The duplication was not free. It inflated the span denominator,
    double-counted a failing relation across two uids, and -- because these
    were the only requirements minted outside S1, and so the only ones without
    `needs` -- killed four of five full-pipeline runs at S2.

    The anti-circularity argument survives without them: a probe carries
    `licensed_by`, those requirements name real ports, and a design that lies
    about the probe fails THEIR checks on the same boundary signals.
    """
    import re
    from pathlib import Path

    from specflow import integration as I

    src = Path(I.__file__).read_text()
    #: Over the WHOLE module: `if _probes_enabled:` appears twice, and
    #: anchoring on the first put the window before the code under test.
    assert "reqs = list(reqs) + cross" not in src, (
        "cross-constraints are being minted as requirements again")
    #: Recorded, not silently dropped -- a stage that stops doing something has
    #: to say so, or the next reader finds an empty list and no reason.
    assert re.search(r"cross-constraint\(s\) recorded and NOT minted", src)
    #: And the function that built them is still reachable, because the
    #: measurement that retired it should be reproducible.
    from specflow.probes import cross_constraint_requirements
    assert callable(cross_constraint_requirements)


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
