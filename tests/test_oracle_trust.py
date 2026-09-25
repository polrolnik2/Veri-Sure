"""Deciding one oracle across every testpoint it names.

This file used to hold the three screening gates. Screening moved to
`specflow/oracles_stage.py`, which runs before the reference model exists rather
than inside the loop repairing it, and mutation moved to
`refmodel/adequacy.py`, which runs after that loop converges rather than during
it. Both moved for the same measured reason: a gate that re-runs against a
design being edited gives an answer that moves with the design.

What is left here is the primitive both of them stand on, and the two ways it
was got wrong: an oracle satisfied on its first testpoint and failing on a later
one is failing, and a testpoint with no stimulus must not poison the ones that
have some.
"""

from __future__ import annotations

from specflow.refmodel import trust
from specflow.refmodel.oracles import RequirementOracle

_TWO_TP_CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]
}

_PASSTHROUGH = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
'''

#: Holds on a trace where `a` is driven high, fails where it is not.
_DEMANDS_Y_HIGH = (
    "def decide(trace):\n"
    "    if not any(r['inputs']['a'] for r in trace):\n"
    "        return (None, None, 'a never driven high')\n"
    "    for r in trace:\n"
    "        if r['inputs']['a'] and not r['outputs']['y']:\n"
    "            return (False, r['edge'], 'y low while a high')\n"
    "    return (True, None, 'y tracked a')\n"
)


def _two_tp_testplan():
    return [{"uid": "TP-0000", "covers": []}, {"uid": "TP-0001", "covers": []}]




def test_deciding_sees_every_testpoint_the_oracle_names():
    """Screening used to decide against the FIRST named testpoint alone, so an
    oracle unexercised on TP-A and failing on TP-B was judged having never been
    replayed on TP-B. Measured as explaining none of the f-i2c residue -- 26 of
    30 name exactly one testpoint -- but a real defect for the ones that name
    more, and the difference between asking the question the oracle poses and
    asking a narrower one."""
    broken = _PASSTHROUGH.replace(
        "return {'y': i['a']}",
        "return {'y': 0 if self._seen() else i['a']}\n\n"
        "    def _seen(self):\n"
        "        self._n = getattr(self, '_n', 0) + 1\n"
        "        return self._n > 2")
    oracle = RequirementOracle(req_uid="REQ-0000",
                               tp_uids=["TP-0000", "TP-0001"],
                               clause="y follows a", source=_DEMANDS_Y_HIGH)
    stimulus = {"TP-0000": [{"a": 1}],
                "TP-0001": [{"a": 1}, {"a": 1}, {"a": 1}]}
    got = trust._decide_over(oracle, broken, _TWO_TP_CONTRACT, stimulus,
                             base="step")
    assert got.failed(), (
        "satisfied on the first testpoint and failing on the second is failing")


def test_a_testpoint_with_no_stimulus_does_not_poison_the_others():
    """`decide_all` reports it as broken, correctly for its own purpose, and
    `_worst` ranks broken first -- so routing through it unchanged would let one
    stimulus-less testpoint discard an oracle its other testpoints decide
    perfectly well."""
    oracle = RequirementOracle(req_uid="REQ-0000",
                               tp_uids=["TP-0000", "TP-0999"],
                               clause="y follows a", source=_DEMANDS_Y_HIGH)
    got = trust._decide_over(oracle, _PASSTHROUGH, _TWO_TP_CONTRACT,
                             {"TP-0000": [{"a": 1}]}, base="step")
    assert not got.broken and got.ok is True


def test_no_stimulus_at_all_is_broken_rather_than_silently_passing():
    oracle = RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0999"],
                               clause="y follows a", source=_DEMANDS_Y_HIGH)
    got = trust._decide_over(oracle, _PASSTHROUGH, _TWO_TP_CONTRACT, {},
                             base="step")
    assert got.broken and "no stimulus" in got.broken


def test_projection_reduces_a_trace_to_what_one_clause_is_about():
    """Comparing whole traces would count any change as visible, so an oracle
    watching `cmd_ack` would be convicted for staying silent when a divider was
    mutated -- pushing oracles toward watching everything, which the
    over-strictness gate then punishes."""
    rows = [{"outputs": {"y": 1, "z": 0}}, {"outputs": {"y": 1, "z": 9}}]
    assert trust._project(rows, {"y"}) == trust._project(
        [{"outputs": {"y": 1, "z": 5}}, {"outputs": {"y": 1, "z": 7}}], {"y"})
    assert trust._project(rows, {"y", "z"}) != trust._project(
        [{"outputs": {"y": 1, "z": 5}}, {"outputs": {"y": 1, "z": 7}}],
        {"y", "z"})
