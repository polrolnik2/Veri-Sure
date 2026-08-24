"""The loop with no judge in it: verdicts are the outcome of running something.

Every blocking verdict here comes from EXECUTING an oracle written before any
verdict existed. The judge's verdict was an opinion its oracle was then asked to
justify -- a rationalisation of a conclusion already reached, by something that
had read the model. Running an oracle written from the requirement alone is not
a justification; it is the verdict.
"""

from __future__ import annotations

from specflow.refmodel import verdict as V
from specflow.refmodel.oracles import (
    RequirementOracle,
    decide_all,
    transactional_view,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]
}

#: Answers one edge late -- a synchroniser, a filter, a divider tick.
LATE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        prev = getattr(self, '_p', 0)
        self._p = i['a']
        return {'y': prev}
'''

STIM = {"TP-0000": [{"a": 0}, {"a": 1}, {"a": 1}, {"a": 1}]}


def _raw():
    from specflow.refmodel.oracles import replay
    return replay(LATE, CONTRACT, STIM["TP-0000"], base="step").rows


# ------------------------------------------------------------- transactional


def test_the_view_collapses_repetition_and_keeps_the_duration():
    """`trace_compare.transactional` is the accept criterion: the ordered
    sequence of distinct states, durations reported rather than enforced. An
    oracle deciding over raw edges is not held to it."""
    rows = transactional_view(_raw())
    assert [r["held"] for r in rows] == [1, 1, 2]
    assert [r["index"] for r in rows] == [0, 1, 2]
    assert sum(r["held"] for r in rows) == len(_raw())


def test_the_view_preserves_input_transitions():
    """Compression is over the WHOLE row. An i2c oracle detects START as an
    INPUT event -- SDA falling while SCL is high -- so compressing outputs alone
    would swallow the events these clauses are about."""
    rows = transactional_view([
        {"edge": 0, "inputs": {"a": 0}, "outputs": {"y": 0}},
        {"edge": 1, "inputs": {"a": 1}, "outputs": {"y": 0}},
    ])
    assert len(rows) == 2, "an input change must start a new state"


def test_the_first_edge_survives_so_a_failure_still_localises():
    rows = transactional_view(_raw())
    assert rows[-1]["edge"] == rows[-1]["first_edge"]
    assert rows[-1]["first_edge"] == 2


def test_next_row_means_next_state_not_next_clock():
    """The property that makes a large class of edge-exact reasoning correct for
    free: "then" becomes latency-insensitive."""
    rows = transactional_view(_raw())
    rising = next(r for r in rows if r["inputs"]["a"] == 1)
    following = rows[rising["index"] + 1]
    assert following["outputs"]["y"] == 1, (
        "the state after the input event is the one that answers it, whatever "
        "the latency"
    )


def test_decide_all_can_run_over_the_transactional_view():
    """Screening and the session must agree on this, or a gate passes an oracle
    the loop then fails for a reason the gate never saw."""
    counts_the_edges = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="y rises",
        source=("def decide(trace):\n"
                "    return (True, None, str(len(trace)) + ' rows')\n"))
    raw = decide_all([counts_the_edges], LATE, CONTRACT, STIM, base="step")
    txn = decide_all([counts_the_edges], LATE, CONTRACT, STIM, base="step",
                     transactional=True)
    assert raw[0].detail == "4 rows"
    assert txn[0].detail == "3 rows"


# ------------------------------------------------------- verdicts from running


def test_a_blocking_verdict_is_the_outcome_of_running_something():
    """No opinion anywhere in this chain: replay, decide, classify, issue."""
    fails = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="y tracks a exactly",
        source=("def decide(trace):\n"
                "    for r in trace:\n"
                "        if r['inputs']['a'] and not r['outputs']['y']:\n"
                "            return (False, r['edge'], 'y low while a high')\n"
                "    return (True, None, 'ok')\n"))
    results = decide_all([fails], LATE, CONTRACT, STIM, base="step",
                         transactional=True)
    by = {r.req_uid: r for r in results}
    mech = V.classify(
        discarded={}, passing=set(),
        failing={u for u, r in by.items() if r.failed()},
        had_oracle={"REQ-0000"}, requirements=[{"uid": "REQ-0000"}])
    assert mech["REQ-0000"] == "VIOLATES"
    issues = V.issues(mech, {u: r.detail for u, r in by.items()})
    assert issues and "fix the implementation" in issues[0].message
    assert "y low while a high" in issues[0].message


def test_an_unexercised_oracle_routes_to_the_stimulus_not_the_model():
    """The measured failure of the old schema: 31 of 33 blocking findings went
    to the reference-model agent when the fix lay elsewhere."""
    unex = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="the a==7 case",
        source=("def decide(trace):\n"
                "    if not any(r['inputs']['a'] == 7 for r in trace):\n"
                "        return (None, None, 'a==7 never driven')\n"
                "    return (True, None, 'ok')\n"))
    results = decide_all([unex], LATE, CONTRACT, STIM, base="step",
                         transactional=True)
    assert results[0].unexercised()
    mech = V.classify(discarded={"REQ-0001": "unexercised: a==7 never driven"},
                      passing=set(), failing=set(), had_oracle={"REQ-0001"},
                      requirements=[{"uid": "REQ-0001"}])
    assert mech["REQ-0001"] == "NOT_EXERCISED"
    assert V.ROUTE[mech["REQ-0001"]] == "fix the stimulus"


# ------------------------------------------------------------------- freezing

#: Demands `y` this edge, which `LATE` never manages. A real failing oracle,
#: not a stub: `well_formed` discards one that names no declared port.
STRICT = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] != row['inputs']['a']:
            return False, row['edge'], 'y did not follow a'
    return True, 0, 'y followed a throughout'
"""

#: The same clause, rewritten to agree with whatever it is shown.
LENIENT = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] not in (0, 1):
            return False, row['edge'], 'y is not a bit'
    return True, 0, 'ok'
"""


def test_the_loop_refuses_to_run_against_a_set_that_moved(monkeypatch, tmp_path):
    """Step 6's whole point, asserted where it matters rather than in the hash.

    The judge-driven loop was measured re-randomising its own metric: 100% of
    the requirements that changed verdict between turns had a rewritten oracle,
    and CONFORMS walked 30, 33, 30. Freezing is what makes "N failing going to
    zero" a claim about the model.
    """
    import pytest

    from specflow.refmodel import compose

    oracle = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="y follows a",
        source=STRICT)

    class _Debugger:
        def debug(self, session):
            # A debug turn must not be able to rewrite the measure. This one
            # does, which is the defect the guard exists to catch -- and it
            # edits the model too, so the loop genuinely reaches another turn
            # rather than stopping for want of progress.
            session.oracles[0].source = LENIENT
            return LATE + "\n# edited\n", 1, ""

    with pytest.raises(RuntimeError, match="changed under the loop"):
        compose._oracle_driven_turns(
            source=LATE, contract=CONTRACT, contract_json="{}",
            requirements=[{"uid": "REQ-0001", "text": "y follows a"}],
            covers={"step": ["REQ-0001"]}, oracles=[oracle], base="step",
            testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
            stimulus_by_tp=dict(STIM), run_dir=None, debugger=_Debugger(),
            max_turns=2, control_source=None, normalized=None, judge_port=None,
        )


def test_the_turn_artifact_names_the_frozen_set_and_what_was_appended(tmp_path):
    """A reader must be able to tell "NOT_EXERCISED fell" from "NOT_EXERCISED
    fell BECAUSE stimulus was added". Those are different claims."""
    import json

    from specflow.refmodel import compose

    oracle = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="y follows a",
        source=STRICT)

    class _Quiet:
        def debug(self, session):
            return session.source, 0, "nothing to do"

    compose._oracle_driven_turns(
        source=LATE, contract=CONTRACT, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y follows a"}],
        covers={"step": ["REQ-0001"]}, oracles=[oracle], base="step",
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp=dict(STIM), run_dir=tmp_path, debugger=_Quiet(),
        max_turns=1, control_source=None, normalized=None, judge_port=None,
    )
    blob = json.loads(
        (tmp_path / "specflow" / "judge" / "r0" / "trust.json").read_text())
    assert blob["driver"] == "requirement-oracles"
    assert blob["oracle_set"]["count"] == 1
    assert blob["oracle_set"]["frozen"]["REQ-0001"]
    assert blob["oracle_set"]["evidence_changed"] == []
    assert blob["stimulus_added"] == []
