"""A check must not depend on WHEN a probe is asserted unless the text says so.

**THE SPECIFICATION WRITES AN EQUATION, NOT A SCHEDULE.** "sto_condition =
sSDA & ~dSDA & sSCL" says what the condition IS and never says whether it is a
wire or a flop. Measured on the frozen i2c set: where that formula holds, the
known-good design asserts the probe one edge later 499 of 499 times, and the
spec-derived population asserts it on the same edge 22 of 22. Five checks
convict the known-good design for it.

No binding guard reaches this -- name, width and quantity all match. The
population cannot reveal it either: every member received the same contract, so
every member computes the condition combinationally and the cell is never a
disagreement cell.
"""
from specflow.refmodel.temporal import delay_probes, phase_sensitive

PROBES = ("sto_condition",)


def _trace(pairs):
    """`(ssda, sto_condition)` per edge; `sscl` held high throughout."""
    return [{"index": i, "inputs": {},
             "outputs": {"ssda": s, "sscl": 1, "sto_condition": c}}
            for i, (s, c) in enumerate(pairs)]


#: SDA rises at index 2. A COMBINATIONAL design asserts the condition there.
COMBINATIONAL = _trace([(0, 0), (0, 0), (1, 1), (1, 0)])
#: A REGISTERED design asserts it at index 3. Same design intent, same
#: equation, one cycle later.
REGISTERED = _trace([(0, 0), (0, 0), (1, 0), (1, 1)])


def at_the_transition(trace):
    """"when SDA rises, sto_condition is asserted" -- read at the same edge."""
    for i, row in enumerate(trace):
        if i and row["outputs"]["ssda"] == 1 and trace[i - 1]["outputs"]["ssda"] == 0:
            return (row["outputs"]["sto_condition"] == 1, i, "at the rise")
    return (None, None, "no rise")


def within_one_cycle(trace):
    """The phase-tolerant reading of the same sentence."""
    for i, row in enumerate(trace):
        if i and row["outputs"]["ssda"] == 1 and trace[i - 1]["outputs"]["ssda"] == 0:
            window = trace[i:i + 2]
            return (any(r["outputs"]["sto_condition"] == 1 for r in window),
                    i, "at or just after the rise")
    return (None, None, "no rise")


def test_the_two_readings_disagree_on_the_same_design():
    """No instrument involved -- the readings themselves differ, which is the point."""
    assert at_the_transition(COMBINATIONAL)[0] is True
    assert at_the_transition(REGISTERED)[0] is False, (
        "the same equation, registered rather than wired, and the same-edge "
        "check convicts it")
    assert within_one_cycle(COMBINATIONAL)[0] is True
    assert within_one_cycle(REGISTERED)[0] is True


def test_delay_probes_shifts_only_probes():
    shifted = delay_probes(COMBINATIONAL, PROBES)
    assert [r["outputs"]["ssda"] for r in shifted] == \
           [r["outputs"]["ssda"] for r in COMBINATIONAL], "ports untouched"
    assert [r["outputs"]["sto_condition"] for r in shifted] == \
           [None, 0, 0, 1], "the probe holds its previous value"


def test_a_same_edge_read_is_flagged_and_names_the_probe():
    assert phase_sensitive(at_the_transition, COMBINATIONAL, PROBES) == \
        ["sto_condition"]


def test_a_phase_tolerant_read_is_not_flagged():
    assert phase_sensitive(within_one_cycle, COMBINATIONAL, PROBES) == []


def test_delaying_every_probe_together_finds_nothing():
    """The reason the instrument delays ONE probe at a time.

    A check of this shape reads its trigger from probes too, so shifting the
    trigger and the condition by the same amount preserves their relative
    timing and no verdict moves. Measured on the frozen set: delaying all
    probes together flagged 20 checks and NONE of the five real cases.
    """
    both = ("ssda", "sto_condition")
    together = delay_probes(COMBINATIONAL, both)
    assert at_the_transition(together)[0] == at_the_transition(COMBINATIONAL)[0], (
        "trigger and condition shifted together -- the relation is unchanged")
    assert phase_sensitive(at_the_transition, COMBINATIONAL, both) != [], (
        "delaying each of the two ALONE still finds the dependence")


def test_a_requirement_that_states_the_timing_licenses_it():
    assert phase_sensitive(
        at_the_transition, COMBINATIONAL, PROBES,
        "sto_condition shall assert on the next clock edge") == [], (
        "the same rule correspondence applies to cycle counts: a claim about "
        "timing is licensed when the sentence states one")


def test_a_check_that_raises_is_another_gates_business():
    def boom(trace):
        raise ValueError("nope")
    assert phase_sensitive(boom, COMBINATIONAL, PROBES) == []


def test_an_abstention_is_not_a_flip():
    """Saying nothing, then saying something, is not a schedule dependence.

    The instrument exists to catch a check that CONVICTS one reading of the
    equation and spares the other. A check that abstained on the real trace
    convicted nobody, so a verdict appearing on the shifted copy is an artifact
    of the shift and not evidence about the check. Without the `here is not
    None` guard this reads as a flip and the check is flagged for a claim it
    never made.
    """
    def abstains_until_shifted(trace):
        if trace[0]["outputs"]["sto_condition"] is None:
            return (True, 0, "decided, but only on the shifted copy")
        return (None, None, "nothing to say about the real trace")

    assert abstains_until_shifted(COMBINATIONAL)[0] is None
    assert abstains_until_shifted(
        delay_probes(COMBINATIONAL, PROBES))[0] is True
    assert phase_sensitive(abstains_until_shifted, COMBINATIONAL, PROBES) == []


def test_both_abstaining_is_not_a_flip():
    def abstains(trace):
        return (None, None, "nothing to say")
    assert phase_sensitive(abstains, COMBINATIONAL, PROBES) == []
