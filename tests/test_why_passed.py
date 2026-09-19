"""WHY an oracle passed a design built to break it, not just that it did.

a2-i2c ended with 14 VACUOUS, every one reading "passed all N variant(s)".
That stops at the symptom, and the three causes want different owners:
REQ-0092 checks `sda_oen` against `din` during the `cmd==8` command-issue
window while the FSM drives SDA tens of edges later -- repairable by widening
the window. REQ-0063 is "the two-stage capture reduces metastability risk",
which no functional replay observes at any port, ever -- not an oracle defect
at all. The artifact could not tell them apart.

Comparing where the variant DIFFERS on the ports the oracle reads against the
rows the oracle actually READ separates them, using replays that already
happen and no model calls.
"""

from __future__ import annotations

from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.variants import Variant, _examined, _span, why_passed

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "d", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 1},
    {"name": "r", "dir": "output", "width": 1},
]}
GOOD = ("class Model:\n"
        "    OUTPUT_PORTS = ('q', 'r')\n"
        "    def step(self, i):\n"
        "        self.q = i.get('d', 0)\n"
        "        self.r = 0\n"
        "        return {'q': self.q, 'r': self.r}\n")
#: differs on `q` at every edge
BROKEN = GOOD.replace("self.q = i.get('d', 0)", "self.q = 0")
#: differs on `q` only from the third edge -- the window-missed shape
LATE = GOOD.replace(
    "self.q = i.get('d', 0)",
    "self.n = getattr(self, 'n', 0) + 1\n"
    "        self.q = i.get('d', 0) if self.n < 3 else 0")
STIM = {"TP-0": [{"d": 1}, {"d": 1}, {"d": 1}]}

READS_EVERY_ROW = ("def decide(trace):\n"
                   "    for st in trace:\n"
                   "        st.get('outputs')\n"
                   "    return (True, 0, 'ok')\n")
READS_ROW_ZERO = ("def decide(trace):\n"
                  "    trace[0].get('outputs')\n"
                  "    return (True, 0, 'ok')\n")


def _oracle(src: str) -> RequirementOracle:
    return RequirementOracle(req_uid="R", tp_uids=["TP-0"], source=src)


def _variant(src: str) -> Variant:
    return Variant(req_uid="R", kind="action", source=src)


def test_a_check_that_read_the_divergence_and_passed_is_vacuous():
    label, why = why_passed(_oracle(READS_EVERY_ROW), _variant(BROKEN), GOOD,
                            CONTRACT, STIM, {"q"})
    assert label == "vacuous"
    assert "read" in why and "passed both anyway" in why


def test_a_check_that_LOOKED_ELSEWHERE_is_window_missed_and_repairable():
    """REQ-0092's shape: right trace, wrong time.

    The author is told both ranges, which is what it needs and could not
    previously see -- "passed all 5 variants" gave it nowhere to look.
    """
    label, why = why_passed(_oracle(READS_ROW_ZERO), _variant(LATE), GOOD,
                            CONTRACT, STIM, {"q"})
    assert label == "window-missed"
    assert "differ at edge(s) 2-" in why
    assert "only read edge(s) 0-0" in why
    # And it must point at a CONDITION, never a cycle count: Phases 3-6 stopped
    # `latency_cycles` gating because the spec does not pin cycle counts.
    assert "CONDITION rather than a count" in why


def test_a_port_nothing_differs_on_is_a_SPECIFICATION_finding():
    """REQ-0063's shape -- metastability, unobservable at any port.

    Not vacuity: no check over these ports could have told the designs apart,
    so convicting this one blames the author for the requirement.
    """
    label, why = why_passed(_oracle(READS_EVERY_ROW), _variant(BROKEN), GOOD,
                            CONTRACT, STIM, {"r"})
    assert label == "no-discrimination"
    assert "specification finding" in why


def test_the_reads_are_recorded_from_the_oracle_s_own_access():
    """`decide` returns ONE edge and it is None on an abstention, so nothing in
    the artifact said which rows a check looked at."""
    rows = [{"edge": i, "inputs": {}, "outputs": {"q": 0}} for i in range(5)]
    assert _examined(_oracle(READS_ROW_ZERO), rows) == {0}
    assert _examined(_oracle(READS_EVERY_ROW), rows) == {0, 1, 2, 3, 4}


def test_an_oracle_that_raises_still_yields_what_it_read():
    boom = "def decide(trace):\n    trace[1].get('outputs')\n    raise ValueError('x')\n"
    assert 1 in _examined(_oracle(boom), [{"outputs": {}} for _ in range(3)])


def test_no_conforming_source_means_no_diagnosis_rather_than_a_wrong_one():
    assert why_passed(_oracle(READS_EVERY_ROW), _variant(BROKEN), "",
                      CONTRACT, STIM, {"q"}) == ("", "")


def test_span_reads_empty_as_none():
    assert _span([]) == "none" and _span([3, 4, 9]) == "3-9"
