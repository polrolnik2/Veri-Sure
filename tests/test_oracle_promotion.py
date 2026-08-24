"""Step 7's must-pass leg: over-strictness caught where it can still be repaired.

Today an over-strict oracle is discovered by screening, a stage after it was
written, when the only remaining move is to discard it and hand its requirement
back as prose. Measured on g-i2c that is 27 of 77. Running the oracle against an
implementation built from the same requirement puts the failure inside
`run_stage`'s existing repair loop instead, where the author is shown the exact
edge it tripped on.
"""

from __future__ import annotations

from specflow.refmodel.oracle_gen import OracleOutput, gate_one

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]
}
TESTPLAN = [{"uid": "TP-0000", "covers": ["REQ-0000@1"]}]
STIM = {"TP-0000": [{"a": 1}, {"a": 1}, {"a": 1}]}

#: Answers on the SECOND edge -- a synchroniser, a filter, a divider tick.
CONFORMING = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        prev = getattr(self, '_p', 0)
        self._p = i['a']
        return {'y': prev}
'''

#: "y goes high at some point after a is driven" -- satisfied by any latency.
TOLERANT = (
    "def decide(trace):\n"
    "    if not any(r['inputs']['a'] for r in trace):\n"
    "        return (None, None, 'a never high')\n"
    "    if any(r['outputs']['y'] for r in trace):\n"
    "        return (True, None, 'y rose')\n"
    "    return (False, None, 'y never rose')\n"
)

#: "y is high on the SAME edge a is" -- the measured failure mode.
EDGE_EXACT = (
    "def decide(trace):\n"
    "    for r in trace:\n"
    "        if r['inputs']['a'] and not r['outputs']['y']:\n"
    "            return (False, r['edge'], 'y low on the edge a was high')\n"
    "    return (True, None, 'y tracked a exactly')\n"
)


def _gate(source, **kw):
    return gate_one(
        OracleOutput(clause="y follows a", source=source),
        req_uid="REQ-0000", tp_uids=["TP-0000"], contract=CONTRACT,
        testplan=TESTPLAN, **kw)


def test_a_tolerant_oracle_passes_the_must_pass_leg():
    assert _gate(TOLERANT, conforming_source=CONFORMING, stimulus_by_tp=STIM) == []


def test_an_edge_exact_oracle_is_caught_where_it_can_still_be_repaired():
    """The whole point: this becomes a gate issue, so `run_stage` re-prompts
    with it rather than the oracle being discarded a stage later."""
    issues = _gate(EDGE_EXACT, conforming_source=CONFORMING, stimulus_by_tp=STIM)
    assert len(issues) == 1
    assert issues[0].path.endswith(".over_strict")
    assert "FAILS your check" in issues[0].message
    assert "edge" in issues[0].message


def test_the_message_says_which_edge_and_what_tripped():
    """`gate_failures_block` hands this straight to the author. "Your oracle is
    wrong" is unactionable; "fails at edge 0 because y was low" is not."""
    msg = _gate(EDGE_EXACT, conforming_source=CONFORMING,
                stimulus_by_tp=STIM)[0].message
    assert "y low on the edge a was high" in msg
    assert "relax it to what the requirement actually says" in msg


def test_the_message_does_not_assert_the_oracle_is_wrong():
    """The conforming implementation is a second reading of the requirement, not
    a golden model, so a disagreement could be either side. An author told flatly
    that it is wrong will contort a correct check until it passes."""
    msg = _gate(EDGE_EXACT, conforming_source=CONFORMING,
                stimulus_by_tp=STIM)[0].message
    assert "it may be either" in msg
    assert "If you are confident the requirement does state it, keep the check" in msg


def test_the_leg_is_inert_without_a_conforming_implementation():
    """Designs where none could be generated must behave exactly as before,
    not fail every oracle."""
    assert _gate(EDGE_EXACT) == []
    assert _gate(EDGE_EXACT, conforming_source=CONFORMING) == []
    assert _gate(EDGE_EXACT, stimulus_by_tp=STIM) == []


def test_only_a_definite_failure_is_reported():
    """A pass, an unexercised scenario and a broken replay are all silence. Only
    a definite failure carries information; re-asking on the others would spend
    a repair round on something the author cannot act on."""
    unexercised = (
        "def decide(trace):\n"
        "    if not any(r['inputs']['a'] == 7 for r in trace):\n"
        "        return (None, None, 'the a==7 case never occurs')\n"
        "    return (True, None, 'ok')\n"
    )
    assert _gate(unexercised, conforming_source=CONFORMING,
                 stimulus_by_tp=STIM) == []


def test_well_formedness_still_runs_first():
    """Cheapest-decisive-first. An oracle that imports must not pay for a replay
    to find that out."""
    issues = _gate("import os\ndef decide(trace):\n    return True",
                   conforming_source=CONFORMING, stimulus_by_tp=STIM)
    assert issues and issues[0].path.endswith(".source")
