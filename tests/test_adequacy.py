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


def test_narrowing_the_scope_cannot_resolve_an_unknown():
    """Narrowing alone can only starve. Half of why the pairing is needed.

    Measured on the frozen 70 at 8 candidates: `ports_read` gave adequate 6 /
    inadequate 20 / unknown 44, assertion ports gave 6 / 18 / 46 -- two verdicts
    moved and both went inadequate -> unknown. The mechanism forces that
    direction, so it is pinned rather than re-measured: a narrower projection
    admits a SUBSET of the mutants, so `in_scope` can only fall, and falling is
    what pushes an oracle under `MIN_IN_SCOPE`.

    This is still true and is no longer an argument against the narrow scope.
    It says the scope cannot travel without the candidate budget, which is what
    `PROPOSAL_LIMIT` supplies -- see the paired test below.
    """
    oracle = _oracle(SHARP)
    few = dict(base="step", propose=adequacy.MUTANT_LIMIT)
    wide, _ = adequacy.adequacy_of(oracle, FINAL, CONTRACT, STIM, **few)
    narrow, detail = adequacy.adequacy_of(
        oracle, FINAL, CONTRACT, STIM, scope={"hit"}, **few)
    assert wide == adequacy.ADEQUATE
    assert narrow == adequacy.UNKNOWN, (
        f"a scope the oracle does not decide on starves the evidence: {detail}")

    paired, why = adequacy.adequacy_of(
        oracle, FINAL, CONTRACT, STIM, base="step", scope={"hit"},
        propose=adequacy.PROPOSAL_LIMIT)
    assert paired != adequacy.UNKNOWN, (
        "the same narrow scope decides once the candidate budget travels with "
        f"it -- that is the pairing, and without it the scope starves: {why}")


def test_an_empty_scope_is_reported_as_asserting_on_nothing():
    """Distinct from "reads no declared port" -- a different finding, and the
    routing depends on telling them apart."""
    level, detail = adequacy.adequacy_of(
        _oracle(SHARP), FINAL, CONTRACT, STIM, base="step", scope=set())
    assert level == adequacy.UNKNOWN
    assert "asserts on no declared port" in detail


def test_the_candidate_budget_is_not_the_in_scope_budget():
    """The bound that starved the instrument, and it starved it silently.

    `mutants()` proposes in deterministic SITE order and the visibility filter
    runs after, so one budget spent before the filter is spent on candidates
    that may all be invisible to this oracle. The oracle then reads UNKNOWN --
    "nothing to say" rather than "not allowed to look".
    """
    oracle = _oracle(BLUNT).model_copy(update={"clause": "y stays in range"})
    starved, why = adequacy.adequacy_of(
        oracle, FINAL, CONTRACT, STIM, base="step", scope={"hit"}, propose=2)
    assert starved == adequacy.UNKNOWN, why
    assert "0 mutant(s)" in why, why
    assert adequacy.PROPOSAL_LIMIT > adequacy.MUTANT_LIMIT, (
        "candidates must outnumber the in-scope evidence they are spent to find")


def test_the_in_scope_budget_still_stops_the_search():
    """Raising the candidates must not turn a bounded sweep into an unbounded one.

    `MUTANT_LIMIT` keeps its meaning -- the evidence saturates -- so the loop
    has to stop at eight VISIBLE mutants however many candidates remain.
    """
    seen = []
    real = adequacy.replay

    def counting(source, contract, steps, *, base):
        seen.append(source)
        return real(source, contract, steps, base=base)

    adequacy.replay = counting
    try:
        adequacy.adequacy_of(_oracle(SHARP), FINAL, CONTRACT, STIM,
                             base="step", limit=2, propose=60)
    finally:
        adequacy.replay = real
    assert len(seen) <= 1 + 60, "the candidate budget still bounds the sweep"
    wide = list(seen)
    seen.clear()
    adequacy.replay = counting
    try:
        adequacy.adequacy_of(_oracle(SHARP), FINAL, CONTRACT, STIM,
                             base="step", limit=8, propose=60)
    finally:
        adequacy.replay = real
    assert len(wide) < len(seen), (
        "a smaller in-scope budget has to stop the search sooner")


def test_the_default_scope_is_derived_from_liveness_not_from_reads():
    """`ports_read` is a string scan and counts ports the oracle only TRIGGERS
    on -- 59% of them on w-i2c. A mutant visible only in one of those is a
    conviction the oracle could not have earned, and `adequacy_rounds` would
    send it to be strengthened against a defect it does not cover.
    """
    from specflow.refmodel import liveness

    oracles = [_oracle(SHARP)]
    derived = adequacy.assess(oracles, FINAL, CONTRACT, STIM, base="step")
    explicit = adequacy.assess(
        oracles, FINAL, CONTRACT, STIM, base="step",
        scope=liveness.assertion_ports(
            liveness.assess(oracles, FINAL, CONTRACT, STIM, base="step")))
    assert derived == explicit, "the default must be the derived map, not ports_read"


def test_an_oracle_asserting_on_nothing_is_left_to_liveness():
    """Adequacy must not re-report a finding liveness owns.

    On w-i2c's 58, 11 of the 15 the paired instrument leaves undecided assert on
    no declared port, and 9 of those liveness has already convicted as
    dead-oracle or dead-stimulus -- a harder verdict, reached without mutants.
    Abstaining is the correct behaviour, not a gap.
    """
    inert = _oracle("def decide(trace):\n    return True, 0, 'ok'\n")
    report = adequacy.assess([inert], FINAL, CONTRACT, STIM, base="step")
    level, detail = report[inert.req_uid]
    assert level == adequacy.UNKNOWN
    assert "asserts on no declared port" in detail, detail


def test_a_dead_oracle_still_reaches_the_strengthening_edge():
    """The routing the derived scope would otherwise have dropped.

    An oracle that asserts on nothing projects onto nothing, so the mutant sweep
    has no evidence and `adequacy_of` answers UNKNOWN -- correctly, as a
    primitive told to look at no ports. But `inadequate()` is what feeds the
    strengthening edge, so at the SET level that silence would stop a check that
    cannot fail from ever being repaired. `assess` relays `liveness.dead`
    instead, which is the harder verdict and was reached without mutants.
    """
    report = adequacy.assess([_oracle(BLUNT)], FINAL, CONTRACT, STIM,
                             base="step")
    level, detail = report["REQ-0001"]
    assert level == adequacy.INADEQUATE, (level, detail)
    assert "REQ-0001" in adequacy.inadequate(report), (
        "a check that cannot fail is the clearest case for strengthening")
    assert "survived" not in detail, (
        "the reason has to be liveness's, not a mutant that was never run")


def test_a_dead_stimulus_is_not_sent_to_the_oracle_author():
    """`liveness.dead` excludes DEAD_STIMULUS deliberately and the relay keeps
    that exclusion: the check demonstrably CAN fail, so it is a finding about
    the testplan, and strengthening it would tighten what was never wrong."""
    from specflow.refmodel import liveness

    assert liveness.DEAD_STIMULUS not in {
        v for v in (liveness.DEAD_ORACLE,)}, "distinct verdicts"
    report = {"REQ-0001": {"verdict": liveness.DEAD_STIMULUS, "detail": "d"},
              "REQ-0002": {"verdict": liveness.DEAD_ORACLE, "detail": "o"}}
    assert liveness.dead(report) == {"REQ-0002": "o"}
