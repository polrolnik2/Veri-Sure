"""An invariant over a window that runs to end of trace convicts by construction.

**`until=TO_END` OPENS A WINDOW THAT NEVER CLOSES.** With the default
`overlap=False` the scan resumes past the window's end, so the whole trace
after the FIRST activation is one window -- later activations open nothing,
they are simply inside it. An invariant asserted there is asserted from the
first trigger to the end of the run, across every gap the requirement
permits, which is strictly more than "after E, P holds while S" ever said.

The proof needs no design, no population and no reference -- it is below, in
`test_the_shape_convicts_a_trace_the_requirement_permits`.

Measured on the frozen i2c set: REQ-0034 (busy after a filtered START/STOP) and
REQ-0128 (idle-and-released after arbitration loss) carry the shape, and both
convict the known-good design. REQ-0046 carries it without convicting.
"""
from specflow.refmodel.oracles import RequirementOracle, well_formed
from specflow.refmodel.temporal import TO_END, after, throughout, unbounded_invariant

CONTRACT = {"io": [{"name": "busy", "dir": "output", "width": 1}]}
PLAN = [{"uid": "TP-0000"}]

BAD = """def decide(trace):
    from specflow.refmodel.temporal import TO_END, after, throughout, worst

    def started(row):
        return row['outputs'].get('sta') == 1

    windows = after(trace, started, until=TO_END)
    return worst([throughout(w, lambda r: r['outputs'].get('busy') == 1)
                  for w in windows])
"""

GOOD = """def decide(trace):
    from specflow.refmodel.temporal import after, throughout, worst

    def started(row):
        return row['outputs'].get('sta') == 1

    windows = after(trace, started,
                    until=lambda row: row['outputs'].get('sto') == 1)
    return worst([throughout(w, lambda r: r['outputs'].get('busy') == 1)
                  for w in windows])
"""


def _rows(pairs):
    return [{"index": i, "inputs": {}, "outputs": {"sta": s, "busy": b}}
            for i, (s, b) in enumerate(pairs)]


def test_the_shape_convicts_a_trace_the_requirement_permits():
    """No design, no population, no reference -- the trace alone convicts.

    The requirement is "after a START, busy is high until the transaction
    ends". This trace starts, is busy, ends (index 3), starts again and is busy
    again -- exactly what the requirement describes. The unbounded window still
    reports a violation, because it opened at index 0 and never closed, so the
    legitimate idle gap at index 3 falls inside it.
    """
    trace = _rows([(1, 1), (0, 1), (0, 1), (0, 0), (1, 1), (0, 1)])
    windows = after(trace, lambda r: r["outputs"]["sta"] == 1, until=TO_END)
    assert len(windows) == 1, (
        "with the default overlap=False the scan resumes past the window's "
        "end, so TO_END yields ONE window covering the rest of the trace -- "
        "the later activation opens nothing, it is already inside")
    assert len(windows[0].rows) == len(trace), "and it runs to the end"
    verdict = throughout(windows[0], lambda r: r["outputs"]["busy"] == 1)
    assert verdict[0] is False, (
        "a trace the requirement PERMITS is convicted, because the window "
        "never closed at the end of the situation")


def test_the_detector_names_the_operator():
    assert unbounded_invariant(BAD) == ["throughout"]


def test_a_window_that_closes_is_not_flagged():
    assert unbounded_invariant(GOOD) == []


def test_an_existential_over_to_end_is_not_flagged():
    """`eventually` over a long window has MORE chances to find its witness."""
    src = BAD.replace("throughout", "eventually").replace(
        "== 1)", "== 1, strong=False)")
    assert unbounded_invariant(src) == []


def test_well_formed_refuses_it_and_says_what_to_do():
    why = well_formed(RequirementOracle(
        req_uid="REQ-0001", clause="", source=BAD, tp_uids=["TP-0000"]),
        CONTRACT, PLAN)
    assert why is not None, "the shape must be refused, not left to convict"
    assert "throughout" in why and "TO_END" in why
    assert "really does oblige this for the rest of the run" in why, (
        "the objection has to offer the legitimate reading -- a requirement "
        "that genuinely obliges something for the rest of the run keeps "
        "TO_END and states it -- or it reads as a ban on saying 'forever'")


def test_well_formed_admits_the_bounded_form():
    assert well_formed(RequirementOracle(
        req_uid="REQ-0001", clause="", source=GOOD, tp_uids=["TP-0000"]),
        CONTRACT, PLAN) is None


def test_a_non_compiling_body_is_left_to_the_other_gate():
    assert unbounded_invariant("def decide(trace)\n    return True") == []
