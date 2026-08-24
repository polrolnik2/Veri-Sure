"""[M] Satisfying every oracle means nothing if none of them could have failed.

`qualify.py:3-22` states it for the suite: a suite can cover every testpoint and
still be unable to fail. This is the same claim one level down, asked of the
model that is about to become the reference for a whole verification suite.
"""

from __future__ import annotations

import json

from specflow.refmodel import adequacy
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 4},
    {"name": "y", "dir": "output", "width": 8},
    {"name": "hit", "dir": "output", "width": 1},
]}

#: Deliberately has several mutable sites on the observable path -- a counter,
#: a threshold, a comparison and two constants. `MIN_IN_SCOPE` is 3, so a model
#: too simple to yield three visible mutants answers UNKNOWN however good the
#: oracle is, which would test the fixture rather than the gate.
FINAL = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y', 'hit']
    LATENCY_CYCLES = 0

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, 'n'):
            self.reset()
        self.k = self.k + 1
        self.n = self.mask(self.n + i['a'], 8)
        if self.n > 12:
            self.n = self.mask(self.n - 4, 8)
        return {'y': self.n, 'hit': 1 if self.k == 3 else 0}
"""

STIM = {"TP-0000": [{"a": 3}, {"a": 5}, {"a": 7}, {"a": 1}, {"a": 2}, {"a": 6}]}

#: Reproduces the design's rule exactly, so any edit to it is visible.
SHARP = """\
def decide(trace):
    total = 0
    for row in trace:
        total = (total + row['inputs']['a']) % 256
        if total > 12:
            total = (total - 4) % 256
        if row['outputs']['y'] != total:
            return False, row['edge'], 'y does not follow the rule'
    return True, 0, 'y followed the rule'
"""

#: Reads y and cannot be made to fail by any edit that keeps it in range.
BLUNT = """\
def decide(trace):
    for row in trace:
        if not (0 <= row['outputs']['y'] <= 255):
            return False, row['edge'], 'y left its width'
    return True, 0, 'y stayed in range'
"""


def _oracle(source: str, uid: str = "REQ-0001") -> RequirementOracle:
    return RequirementOracle(req_uid=uid, tp_uids=["TP-0000"],
                             clause="y accumulates a", source=source)


def _assess(source: str):
    return adequacy.adequacy_of(_oracle(source), FINAL, CONTRACT, STIM,
                                base="step")


def test_a_sharp_oracle_is_adequate():
    level, detail = _assess(SHARP)
    assert level == adequacy.ADEQUATE, detail


def test_an_oracle_no_mutant_can_fail_is_inadequate():
    level, detail = _assess(BLUNT)
    assert level == adequacy.INADEQUATE
    assert "survived" in detail, "the counterexample has to be nameable"


def test_too_few_in_scope_mutants_is_unknown_not_inadequate():
    """One observation is not evidence. `MIN_IN_SCOPE` transfers unchanged."""
    unreachable = _oracle(BLUNT).model_copy(update={"tp_uids": ["TP-NONE"]})
    level, detail = adequacy.adequacy_of(unreachable, FINAL, CONTRACT, STIM,
                                         base="step")
    assert level == adequacy.UNKNOWN
    assert "stimulus" in detail


def test_an_oracle_reading_no_declared_port_is_unknown():
    level, _ = _assess("def decide(trace):\n    return True, 0, 'ok'\n")
    assert level == adequacy.UNKNOWN


def test_inadequate_names_what_a_strengthening_round_should_target():
    report = {"REQ-0001": (adequacy.INADEQUATE, "survived line 12: + -> -"),
              "REQ-0002": (adequacy.ADEQUATE, "caught every one"),
              "REQ-0003": (adequacy.UNKNOWN, "only 1 mutant")}
    assert adequacy.inadequate(report) == {
        "REQ-0001": "survived line 12: + -> -"}


def test_the_report_is_written_and_not_gated(tmp_path):
    """Its rate has to be measured before it decides anything."""
    report = {"REQ-0001": (adequacy.ADEQUATE, "caught 4"),
              "REQ-0002": (adequacy.INADEQUATE, "survived x")}
    path = adequacy.write(tmp_path, report, 0)
    blob = json.loads(path.read_text())
    assert blob["counts"] == {adequacy.ADEQUATE: 1, adequacy.INADEQUATE: 1}
    assert blob["by_requirement"]["REQ-0002"]["verdict"] == adequacy.INADEQUATE


def test_it_runs_after_the_debug_loop_not_inside_it():
    """`trust.sensitivity` guards itself with "only oracles that currently
    pass", which inside the loop biases the sample to whatever the broken model
    happens to satisfy -- and it re-derives mutants from the CURRENT source, so
    the answer moves as the agent edits. After the loop no guard is needed."""
    import inspect

    from specflow.refmodel import compose

    src = inspect.getsource(compose._closed_loop)
    converged = src.index("_debug_turns(")
    measured = src.index("assess(")
    assert converged < measured


def test_a_strengthening_round_is_off_by_default():
    import inspect

    from specflow.refmodel import compose

    sig = inspect.signature(compose.run_refmodel)
    assert sig.parameters["adequacy_rounds"].default == 0


# ------------------------------------------------------- the loop end to end


def _oracle_set(oracles):
    from specflow.oracles_stage import TRUSTED, OracleSet

    return OracleSet(trusted=list(oracles),
                     dispositions={o.req_uid: TRUSTED for o in oracles},
                     reasons={}, variants=[], witness_kind="witness", rounds=1)


def test_the_closed_loop_measures_adequacy_after_it_converges(tmp_path):
    """Nothing ran `_closed_loop` before this: the ordering was asserted by
    reading its source, which cannot catch a wiring defect."""
    import json

    from specflow.refmodel import compose

    oracle = _oracle(SHARP)

    class _Quiet:
        def debug(self, session):
            return session.source, 0, "nothing to do"

    source, issues = compose._closed_loop(
        source=FINAL, contract=CONTRACT, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y accumulates a"}],
        covers={"step": ["REQ-0001"]}, oracles=[oracle], base="step",
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp=dict(STIM), run_dir=tmp_path, debugger=_Quiet(),
        max_turns=1, control_source=None, normalized=None, item_port=None,
        variants=[], carried={}, oracle_rates={},
        oracle_set=_oracle_set([oracle]), adequacy_rounds=0,
    )
    assert source == FINAL
    blob = json.loads((tmp_path / "specflow" / "adequacy_r0.json").read_text())
    assert blob["by_requirement"]["REQ-0001"]["verdict"] == adequacy.ADEQUATE


def test_an_inadequate_oracle_sends_the_loop_back_to_the_stage(tmp_path,
                                                               monkeypatch):
    """The feedback edge, exercised rather than described. A mutant the oracle
    could not catch must reach the stage that owns oracle generation, scoped to
    that requirement, with the counterexample in hand."""
    from specflow import oracles_stage
    from specflow.refmodel import compose

    asked: dict = {}

    def _stage(**kw):
        asked.update(kw)
        return _oracle_set([_oracle(SHARP)])

    monkeypatch.setattr(oracles_stage, "run_oracle_stage", _stage)

    class _Quiet:
        def debug(self, session):
            return session.source, 0, "nothing to do"

    compose._closed_loop(
        source=FINAL, contract=CONTRACT, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y accumulates a"}],
        covers={"step": ["REQ-0001"]}, oracles=[_oracle(BLUNT)], base="step",
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp=dict(STIM), run_dir=tmp_path, debugger=_Quiet(),
        max_turns=1, control_source=None, normalized=None, item_port=None,
        variants=[], carried={}, oracle_rates={},
        oracle_set=_oracle_set([_oracle(BLUNT)]), adequacy_rounds=1,
    )
    assert "REQ-0001" in (asked.get("strengthen") or {}), asked.keys()
    assert "survived" in asked["strengthen"]["REQ-0001"]
    assert asked.get("previous") is not None, "the round must build on the set"


def test_no_strengthening_round_is_spent_when_every_oracle_is_adequate(
        tmp_path, monkeypatch):
    from specflow import oracles_stage
    from specflow.refmodel import compose

    called: list[int] = []
    monkeypatch.setattr(oracles_stage, "run_oracle_stage",
                        lambda **_kw: called.append(1))

    class _Quiet:
        def debug(self, session):
            return session.source, 0, "nothing to do"

    compose._closed_loop(
        source=FINAL, contract=CONTRACT, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y accumulates a"}],
        covers={"step": ["REQ-0001"]}, oracles=[_oracle(SHARP)], base="step",
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp=dict(STIM), run_dir=tmp_path, debugger=_Quiet(),
        max_turns=1, control_source=None, normalized=None, item_port=None,
        variants=[], carried={}, oracle_rates={},
        oracle_set=_oracle_set([_oracle(SHARP)]), adequacy_rounds=1,
    )
    assert called == []
