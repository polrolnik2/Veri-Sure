"""Requirement oracles: replay, decide, and what must never be confused.

The distinction this file exists to pin is between a FAILING MODEL and a BROKEN
ORACLE. Both look like "not ok" from a distance, and treating the second as the
first sends a repair loop after code that may be perfectly correct -- which is
the failure this whole design exists to stop, one level up from the inert
reference model that started it.
"""

from __future__ import annotations

from specflow.refmodel.oracles import (
    RequirementOracle,
    decide,
    decide_all,
    ports_read,
    replay,
    well_formed,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
        {"name": "ack", "dir": "output", "width": 1},
    ]
}
PLAN = [{"uid": "TP-0000"}, {"uid": "TP-0001"}]
STIM = {"TP-0000": [{"inputs": {"a": 3}, "hold": 4}]}

#: Accumulates, and pulses `ack` once on the third edge.
LIVE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q", "ack"]

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, "n"):
            self.reset()
        self.n = self.mask(self.n + i.get("a", 0), 8)
        self.k += 1
        return {"q": self.n, "ack": 1 if self.k == 3 else 0}
'''

#: The inert failure mode that started all of this: outputs never move.
INERT = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q", "ack"]

    def step(self, i):
        return {"q": 0, "ack": 0}
'''


def _oracle(source: str, *, tps=("TP-0000",), uid="REQ-0000") -> RequirementOracle:
    return RequirementOracle(
        req_uid=uid, tp_uids=list(tps), clause="q must move", source=source
    )


Q_MOVES = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["q"] != 0:
            return (True, row["edge"], "q moved")
    return (False, None, "q never left 0")
'''


# ----------------------------------------------------------------- replay


def test_replay_returns_one_structured_row_per_edge():
    rep = replay(LIVE, CONTRACT, STIM["TP-0000"], base="step")
    assert not rep.error
    assert [r["edge"] for r in rep.rows] == [0, 1, 2, 3]
    assert rep.rows[0]["outputs"] == {"q": 3, "ack": 0}
    # Inputs the stimulus did not name are still present, from `pinned_inputs`.
    assert rep.rows[0]["inputs"]["rst_n"] == 1


def test_replay_reports_a_model_that_raises_rather_than_propagating():
    rep = replay("class Model:\n    def step(self, i):\n        raise ValueError('x')\n",
                 CONTRACT, STIM["TP-0000"], base="step")
    assert "raised at edge 0" in rep.error
    assert rep.rows == []


def test_until_runs_to_the_testpoints_own_timeout():
    """Capping it at a render budget made scenarios read as never completing."""
    steps = [{"inputs": {"a": 1}, "until": {"port": "ack", "value": 1}, "timeout": 50}]
    rep = replay(LIVE, CONTRACT, steps, base="step")
    assert len(rep.rows) == 3, "should stop the edge ack rises, not before or after"
    assert rep.rows[-1]["outputs"]["ack"] == 1
    assert not rep.notes


def test_an_until_that_never_fires_is_stated_but_not_blamed():
    """On the known-good control, 23 of 60 scenarios never fire their `until`.

    The stimulus paired clk_cnt=200 with timeout=500 when one command at that
    divider needs upwards of 1000 edges. Phrasing that as a model defect would
    make a correct model look broken.
    """
    steps = [{"inputs": {"a": 0}, "until": {"port": "ack", "value": 9}, "timeout": 6}]
    rep = replay(LIVE, CONTRACT, steps, base="step")
    assert rep.notes and "did not reach" in rep.notes[0]
    assert not rep.error, "an unfired `until` is not an error"


# ----------------------------------------------------------------- decide


def test_a_failing_model_is_reported_as_failing_not_broken():
    trace = replay(INERT, CONTRACT, STIM["TP-0000"], base="step").rows
    result = decide(_oracle(Q_MOVES), trace)
    assert result.ok is False
    assert not result.broken, "the model is wrong; the oracle worked perfectly"
    assert "never left 0" in result.detail


def test_a_passing_model_carries_the_edge_the_oracle_decided_on():
    trace = replay(LIVE, CONTRACT, STIM["TP-0000"], base="step").rows
    result = decide(_oracle(Q_MOVES), trace)
    assert result.ok is True
    assert result.edge == 0, "a failure that cannot localise itself is prose again"


def test_an_oracle_that_raises_is_broken_not_a_failing_model():
    trace = replay(LIVE, CONTRACT, STIM["TP-0000"], base="step").rows
    result = decide(_oracle("def decide(trace):\n    return trace['nope']\n"), trace)
    assert result.broken, (
        "an oracle that throws must never be reported as a model defect -- that "
        "sends the repair loop after correct code"
    )


def test_an_oracle_returning_the_wrong_shape_is_broken():
    trace = replay(LIVE, CONTRACT, STIM["TP-0000"], base="step").rows
    result = decide(_oracle("def decide(trace):\n    return 'yes'\n"), trace)
    assert result.broken and "expected (ok, edge, detail)" in result.broken


def test_a_bare_bool_is_accepted_for_the_trivial_case():
    trace = replay(LIVE, CONTRACT, STIM["TP-0000"], base="step").rows
    result = decide(_oracle("def decide(trace):\n    return True\n"), trace)
    assert result.ok is True and not result.broken


# ----------------------------------------------------------------- decide_all


def test_a_missing_stimulus_is_broken_rather_than_a_silent_pass():
    results = decide_all([_oracle(Q_MOVES, tps=("TP-0001",))],
                         LIVE, CONTRACT, STIM, base="step")
    assert results[0].broken and "no stimulus recorded" in results[0].broken


def test_an_oracle_holds_only_if_it_holds_on_every_testpoint_it_names():
    stim = {"TP-0000": [{"inputs": {"a": 3}, "hold": 4}],
            "TP-0001": [{"inputs": {"a": 0}, "hold": 4}]}   # q stays 0 here
    results = decide_all([_oracle(Q_MOVES, tps=("TP-0000", "TP-0001"))],
                         LIVE, CONTRACT, stim, base="step")
    assert results[0].ok is False, "the first failing scenario is the answer"


def test_a_broken_model_is_attributed_to_the_model_not_the_oracle():
    results = decide_all(
        [_oracle(Q_MOVES)],
        "class Model:\n    def step(self, i):\n        raise ValueError('x')\n",
        CONTRACT, STIM, base="step")
    assert results[0].broken.startswith("the MODEL "), (
        "the reader must be able to tell whose defect this is"
    )


# ----------------------------------------------------------------- screening


def test_well_formed_accepts_a_sound_oracle():
    assert well_formed(_oracle(Q_MOVES), CONTRACT, PLAN) is None


def test_an_unknown_testpoint_is_rejected_before_the_loop_sees_it():
    bad = _oracle(Q_MOVES, tps=("TP-9999",))
    assert "not in the testplan" in (well_formed(bad, CONTRACT, PLAN) or "")


def test_the_model_sandbox_is_reused_rather_than_re_derived():
    """An oracle is the same trust class as the reference model."""
    bad = _oracle("import os\n\n\ndef decide(trace):\n    return True\n")
    assert well_formed(bad, CONTRACT, PLAN) is not None


def test_wrong_arity_is_rejected():
    bad = _oracle("def decide(trace, extra):\n    return True\n")
    assert "expected exactly 1" in (well_formed(bad, CONTRACT, PLAN) or "")


def test_an_oracle_naming_no_declared_port_decides_nothing_observable():
    """It would also be unscopeable by the mutation gate, which projects on ports."""
    bad = _oracle("def decide(trace):\n    return (True, None, 'sure')\n")
    assert "names no declared port" in (well_formed(bad, CONTRACT, PLAN) or "")


def test_ports_read_finds_only_declared_ports():
    o = _oracle('def decide(trace):\n    x = "not_a_port"\n'
                '    return (trace[0]["outputs"]["ack"] == 1, 0, x)\n')
    assert ports_read(o, CONTRACT) == {"ack"}


def test_decide_may_answer_with_the_verdict_vocabulary_it_also_writes():
    """The judge writes a verdict and an oracle in one reply and mixes them.

    On d-i2c r0 five oracles returned ('met', ...), ('ambiguous', ...) or
    ('not_met', ...). The mapping is exact and the rest of the tuple is fine,
    so discarding them handed five requirements back as unverifiable prose.
    """
    from specflow.refmodel.oracles import RequirementOracle, decide

    def _o(body):
        return RequirementOracle(req_uid="R", tp_uids=["TP-0000"], clause="c",
                                 source=f"def decide(trace):\n    return {body}\n")
    row = [{"edge": 0, "inputs": {}, "outputs": {"q": 1}}]
    assert decide(_o("('met', 3, 'ok')"), row).ok is True
    assert decide(_o("('not_met', 3, 'no')"), row).failed()
    assert decide(_o("('ambiguous', None, 'unseen')"), row).unexercised()
    assert decide(_o("('banana', 1, 'x')"), row).broken, "only exact words map"


def test_a_two_tuple_is_read_as_ok_and_detail():
    """The edge is optional; dropping the whole verdict over it is not a trade."""
    from specflow.refmodel.oracles import RequirementOracle, decide

    o = RequirementOracle(req_uid="R", tp_uids=["TP-0000"], clause="c",
                          source="def decide(trace):\n    return (False, 'no ack')\n")
    out = decide(o, [{"edge": 0, "inputs": {}, "outputs": {"q": 1}}])
    assert out.failed() and out.detail == "no ack" and out.edge is None


def test_a_timed_out_wait_does_not_abandon_the_rest_of_the_testpoint():
    """The defect that made a good testplan look thin.

    `until` waits for the design to say something. When it never does, that is
    a complete observation -- "waited, it did not happen" -- and the steps after
    it are a different part of the scenario, not a continuation of the wait.

    Breaking on the timeout note truncated 61 of 167 testpoints on d-i2c,
    discarding 259 stimulus steps and 17 reset steps that never executed. The
    oracles then correctly reported they could not see their scenario, and the
    loss read as a testplan gap when the testplan had asked for the right thing.
    """
    from specflow.refmodel.oracles import replay

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
        {"name": "done", "dir": "output", "width": 1},
    ]}
    model = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "done"]\n\n'
             '    def reset(self):\n        self.n = 0\n\n'
             '    def step(self, i):\n'
             '        if not hasattr(self, "n"):\n            self.reset()\n'
             '        self.n = self.mask(self.n + i.get("a", 0), 8)\n'
             '        return {"q": self.n, "done": 0}\n')   # `done` never rises

    rep = replay(model, contract, [
        {"inputs": {"a": 1}, "until": {"port": "done", "value": 1}, "timeout": 5},
        {"inputs": {"a": 2}, "hold": 3},
    ], base="step")
    assert rep.notes, "the wait really did time out, and must say so"
    assert len(rep.rows) == 8, "5 waiting + 3 after -- the tail still ran"
    assert rep.rows[-1]["inputs"]["a"] == 2, "the step after the wait was applied"


def test_a_reset_step_after_a_timed_out_wait_still_fires():
    """17 reset steps were skipped this way, so reset requirements read as
    unexercised while the stimulus had asked for exactly the right thing."""
    from specflow.refmodel.oracles import replay

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
        {"name": "done", "dir": "output", "width": 1},
    ]}
    model = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "done"]\n\n'
             '    def reset(self):\n        self.n = 0\n\n'
             '    def step(self, i):\n'
             '        if not hasattr(self, "n"):\n            self.reset()\n'
             '        self.n = self.mask(self.n + i.get("a", 0), 8)\n'
             '        return {"q": self.n, "done": 0}\n')
    rep = replay(model, contract, [
        {"inputs": {"a": 1}, "until": {"port": "done", "value": 1}, "timeout": 4},
        {"reset": True, "hold": 2},
    ], base="step")
    assert any(r["inputs"]["rst_n"] == 0 for r in rep.rows), "reset was asserted"


def test_the_edge_budget_still_stops_a_replay():
    """It is a resource limit, not an observation, and must remain terminal."""
    from specflow.refmodel.oracles import replay

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
    ]}
    model = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q"]\n\n'
             '    def step(self, i):\n        return {"q": i.get("a", 0)}\n')
    rep = replay(model, contract,
                 [{"inputs": {"a": 1}, "hold": 50}] * 4, base="step",
                 edge_budget=30)
    assert len(rep.rows) == 30
    assert any("stopped after 30 edges" in n for n in rep.notes)


def test_well_formed_SMOKE_RUNS_the_body_so_a_bad_call_cannot_be_frozen():
    """A wrong keyword compiles perfectly and raises only when the check RUNS.

    Every other screen in `well_formed` is static -- the source parses, `decide`
    exists with arity 1, a declared port is named -- and a call like
    `after(..., aborts_on=...)` passes all of them. Measured on h2-i2c: 25 of 96
    frozen oracles raised on every trace, 22 with exactly that keyword, and all
    25 passed this function. Because `decide` returns ok=False for a broken
    oracle, they were indistinguishable from convictions of the design.
    """
    bad = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="q settles",
        source="def decide(trace):\n"
               "    return sorted(trace, nosuchkeyword=True) and (True, 0, 'q')\n")
    why = well_formed(bad, CONTRACT, PLAN)
    assert why, "an oracle that raises on any trace must not be well-formed"
    assert "nosuchkeyword" in why, why


def test_the_smoke_run_does_NOT_reject_an_oracle_that_merely_abstains():
    """Abstaining on a blank trace is CORRECT, and must not read as broken.

    The smoke rows are every declared port at zero, so a real activation almost
    never occurs in them. An oracle returning ok=None there has behaved exactly
    as `decide`'s contract asks, and rejecting it would discard the honest ones
    while keeping the vacuous checks that answer True regardless.
    """
    shy = RequirementOracle(
        req_uid="REQ-0002", tp_uids=["TP-0000"], clause="ack pulses",
        source="def decide(trace):\n"
               "    for row in trace:\n"
               "        if row['outputs']['ack'] == 1:\n"
               "            return (True, row['edge'], 'ack pulsed')\n"
               "    return (None, None, 'ack never pulsed in this trace')\n")
    assert well_formed(shy, CONTRACT, PLAN) is None
