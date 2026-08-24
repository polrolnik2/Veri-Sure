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


def test_generation_runs_no_design_against_the_oracle():
    """A must-pass leg used to live here: the oracle was replayed against the
    witness and a failure re-prompted the author with the edge its check
    tripped on.

    It is measurably the wrong trade. The witness is a second reading of the
    same requirement by the same author, so it cannot say the oracle is wrong --
    and telling an author "an independent implementation fails your check" does
    not make the check correct, it makes the check agree with the witness.
    Measured on h-i2c: over-strictness 27 -> 15 bought with convictions 2 -> 16,
    oracles relaxed until they stopped disagreeing.
    """
    # A witness this oracle definitely fails, plus stimulus to run it on.
    issues = _gate(EDGE_EXACT, conforming_source=CONFORMING,
                   stimulus_by_tp=STIM, base="step")
    assert issues == [], (
        "a design rejected an oracle at generation: "
        + "; ".join(i.message for i in issues))


def test_generation_still_screens_structure():
    """Removing the design leg must not remove the checks that involve no
    design at all -- those are the ones that keep their authority."""
    assert _gate("def decide(trace):\n    return True, 0, 'ok'\n",
                 conforming_source=CONFORMING, stimulus_by_tp=STIM,
                 base="step"), "an oracle naming no declared port must be caught"
    assert gate_one(
        OracleOutput(clause="", source=EDGE_EXACT), req_uid="REQ-0000",
        tp_uids=["TP-0000"], contract=CONTRACT, testplan=TESTPLAN), (
        "an oracle that does not say which clause it decides must be caught")
