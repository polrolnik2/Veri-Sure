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

#: Live but weak: it pins y at the FIRST edge only, so a near perturbation
#: there moves the verdict -- `liveness` calls it live -- while every mutant
#: that only changes later edges walks past it. Neither of the other fixtures
#: can test the two-vocabulary split: SHARP is adequate, and BLUNT is a DEAD
#: oracle, which is relayed from liveness rather than convicted by a mutant. A
#: band check is no good either -- only a FAR perturbation moves it, so liveness
#: calls it dead-stimulus and adequacy abstains.
WEAK = """\
def decide(trace):
    row = trace[0]
    if row['outputs']['y'] != row['inputs']['a']:
        return False, row['edge'], 'the first sum is not a'
    return True, 0, 'the first sum is a'
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
    level, detail, _ = _assess(SHARP)
    assert level == adequacy.ADEQUATE, detail


def test_an_oracle_no_mutant_can_fail_is_inadequate():
    level, detail, _ = _assess(BLUNT)
    assert level == adequacy.INADEQUATE
    assert "survived" in detail, "the counterexample has to be nameable"


def test_too_few_in_scope_mutants_is_unknown_not_inadequate():
    """One observation is not evidence. `MIN_IN_SCOPE` transfers unchanged."""
    unreachable = _oracle(BLUNT).model_copy(update={"tp_uids": ["TP-NONE"]})
    level, detail, _ = adequacy.adequacy_of(unreachable, FINAL, CONTRACT, STIM,
                                            base="step")
    assert level == adequacy.UNKNOWN
    assert "stimulus" in detail


def test_an_oracle_reading_no_declared_port_is_unknown():
    level = _assess("def decide(trace):\n    return True, 0, 'ok'\n").verdict
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


def test_one_strengthening_round_runs_by_default():
    """One retry: debug, mutate the shipped model, strengthen what caught
    nothing, debug once more -- TWO reference models in total.

    It shipped at 0 while adequacy could only be trusted to measure. n-i2c
    reported 46 CONFORMS of which 6 could be shown to discriminate, and nothing
    was done about the other 40, which is measuring a set and acting on none
    of it.

    The default is only safe alongside `_unbuildable`: 19 of n-i2c's 20
    inadequacy findings cited one mutant putting the literal 2 on a one-bit
    port, and strengthening against those would have returned 20 oracles
    over-strict. The two are pinned together here so the default cannot outlive
    the filter that justifies it.
    """
    import inspect

    from specflow.refmodel import adequacy, compose

    sig = inspect.signature(compose.run_refmodel)
    assert sig.parameters["adequacy_rounds"].default == 1
    assert hasattr(adequacy, "_unbuildable"), (
        "a strengthening round must not run without the illegal-mutant filter")


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
    wide = adequacy.adequacy_of(oracle, FINAL, CONTRACT, STIM, **few).verdict
    narrow, detail, _ = adequacy.adequacy_of(
        oracle, FINAL, CONTRACT, STIM, scope={"hit"}, **few)
    assert wide == adequacy.ADEQUATE
    assert narrow == adequacy.UNKNOWN, (
        f"a scope the oracle does not decide on starves the evidence: {detail}")

    paired, why, _ = adequacy.adequacy_of(
        oracle, FINAL, CONTRACT, STIM, base="step", scope={"hit"},
        propose=adequacy.PROPOSAL_LIMIT)
    assert paired != adequacy.UNKNOWN, (
        "the same narrow scope decides once the candidate budget travels with "
        f"it -- that is the pairing, and without it the scope starves: {why}")


def test_an_empty_scope_is_reported_as_asserting_on_nothing():
    """Distinct from "reads no declared port" -- a different finding, and the
    routing depends on telling them apart."""
    level, detail, _ = adequacy.adequacy_of(
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
    starved, why, _ = adequacy.adequacy_of(
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
    assert derived["REQ-0001"][0] == adequacy.ADEQUATE, (
        "and the derived scope must still be able to say ADEQUATE. An instrument "
        "that only ever convicts is the same defect as one that never does -- "
        "measured on n-i2c's 70, the paired configuration returns 0 adequate, "
        "and that reading is only worth anything if a sharp oracle can reach it")


def test_an_oracle_asserting_on_nothing_is_left_to_liveness():
    """Adequacy must not re-report a finding liveness owns.

    On w-i2c's 58, 11 of the 15 the paired instrument leaves undecided assert on
    no declared port, and 9 of those liveness has already convicted as
    dead-oracle or dead-stimulus -- a harder verdict, reached without mutants.
    Abstaining is the correct behaviour, not a gap.
    """
    inert = _oracle("def decide(trace):\n    return True, 0, 'ok'\n")
    report = adequacy.assess([inert], FINAL, CONTRACT, STIM, base="step")
    level, detail = report[inert.req_uid][:2]
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
    level, detail = report["REQ-0001"][:2]
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


def test_the_reason_counts_the_survivors_it_does_not_name_the_first():
    """A broad failure and a single shared blind spot used to report identically.

    `survivor = survivor or mutant.description` kept the FIRST survivor in
    deterministic SITE order, and site order starts at the top of the file where
    the reset and initialisation block lives. Measured on w-i2c's 43 decidable
    oracles: naming only the first, 25 of them read "survived line 21: True
    becomes False" and the population looks concentrated on one mutant. Counting
    every survivor, 253 of 330 in-scope mutants got past, 24 distinct mutants
    survived somewhere, and 14 oracles missed all 8 shown to them.

    The rework plan read the first form as evidence -- "every one cites survived
    line 27" -- and built a filter on it that fired on 0 of 70.
    """
    level, detail, _ = _assess(BLUNT)
    assert level == adequacy.INADEQUATE
    assert detail.startswith("survived "), detail
    n, m = map(int, __import__("re").match(r"survived (\d+) of (\d+) ", detail).groups())
    assert 0 < n <= m, detail
    assert n > 1, (
        "the fixture's blunt oracle misses more than one mutant, and the report "
        f"has to say so rather than naming the earliest: {detail}")


def test_the_reason_does_not_grow_without_bound():
    """The detail is embedded verbatim in the strengthening prompt, so a list of
    every survivor is a worse instruction than a count and a sample."""
    named = adequacy._survived([f"line {i}: a becomes b" for i in range(9)], 9)
    assert named.count(";") <= adequacy.SURVIVORS_NAMED
    assert "and 6 more" in named, named
    assert named.startswith("survived 9 of 9 "), named


def test_the_artifact_carries_how_much_the_set_demands(tmp_path):
    """"48 inadequate" says nothing about how much got past. An oracle that
    missed one of eight and one that missed eight of eight are the same row."""
    report = {"REQ-0001": (adequacy.INADEQUATE, adequacy._survived(["a", "b"], 8)),
              "REQ-0002": (adequacy.ADEQUATE, "caught every one of 4 mutants it could observe"),
              "REQ-0003": (adequacy.UNKNOWN, "only 1 mutant(s) changed anything")}
    assert adequacy.strength(report) == {
        "mutants_shown": 12, "mutants_missed": 2, "missed_pct": 16}
    written = json.loads(adequacy.write(tmp_path, report, 0).read_text())
    assert written["strength"]["mutants_missed"] == 2


def test_a_trace_that_never_finishes_is_the_counterexample():
    """Length is a difference, and on i2c it is the commonest one.

    Measured on w-i2c REQ-0000: the surviving mutant ran 204 edges where the
    design it was compared against ran 30, because it never leaves reset, so the
    transaction never completes and the replay runs to its edge budget.
    `_project` counts that -- tuples of different length are unequal, which is
    why the mutant was in scope at all -- but zipping the rows positionally
    finds no disagreeing port in the first 30 and reported nothing, so the
    author was handed the empty fallback for the single clearest defect there is.
    """
    diffs = adequacy._difference(
        [{"edge": i, "outputs": {"y": 0}} for i in range(3)],
        [{"edge": i, "outputs": {"y": 0}} for i in range(9)],
        {"y"})
    assert diffs, "a run that never finishes has to reach the author"
    assert "3 edges and the other 9" in diffs[0], diffs
    assert "never finishes" in diffs[0]


def test_a_port_present_on_one_side_only_is_a_difference():
    """The second way `_difference` returned nothing: requiring the port in BOTH
    rows skips exactly the case `_project` counts via `.get` returning None."""
    diffs = adequacy._difference(
        [{"edge": 0, "outputs": {"y": 1}}], [{"edge": 0, "outputs": {}}], {"y"})
    assert diffs and "y is 1 in one and None in the other" in diffs[0], diffs


def test_the_counterexample_never_says_which_trace_is_correct():
    """Naming it hands the author the reference model's behaviour to write
    against, and the reference model is the artifact this oracle exists to
    judge. The plan already records the weaker form: a control may reject an
    oracle but never repair one, because quoting a known-good trace tunes the
    oracle to it and the model is then tuned to the oracle, so `golden_check`
    stops being held out. This is that with the loop closed tighter.
    """
    diffs = adequacy._difference(
        [{"edge": 2, "outputs": {"y": 5}}], [{"edge": 2, "outputs": {"y": 6}}],
        {"y"})
    text = adequacy._instruct(diffs, 1, 4)
    assert "in one and 6 in the other" in text
    for banned in ("correct", "conforming", "expected", "should be", "base"):
        assert banned not in text.lower(), (banned, text)


def test_the_author_gets_the_counterexample_and_the_artifact_gets_the_mutation():
    """Two vocabularies for one event, because their readers may see different
    things. `inadequate()` feeds the strengthening prompt and must carry traces;
    the artifact keeps the mutation, which is what a person debugging this
    pipeline needs and what the author must never be sent."""
    import re as _re
    report = adequacy.assess([_oracle(WEAK)], FINAL, CONTRACT, STIM,
                             base="step")
    rec = report["REQ-0001"]
    assert rec.verdict == adequacy.INADEQUATE, rec
    assert _re.search(r"line \d+", rec.detail), rec.detail
    author = adequacy.inadequate(report)["REQ-0001"]
    assert not _re.search(r"line \d+", author), author


# ------------------------------------------------- mutants nothing can BE
#
# The sibling of the equivalent-mutant filter. `_project` drops a mutant nothing
# can SEE; this drops one nothing can BE.


def test_a_mutant_putting_an_illegal_value_on_a_port_is_discarded():
    """Measured on n-i2c: 20 inadequate verdicts, 19 citing the SAME illegal
    mutant -- `survived line 27: 1 becomes 2` on a one-bit port. Acting on them
    would have sent 20 oracles to be rewritten until they caught a value no
    hardware can produce, and they would have come back over-strict."""
    from specflow.refmodel.adequacy import _unbuildable

    widths = {"q": 1, "wide": 8}
    assert _unbuildable([{"outputs": {"q": 2}}], widths) == "q=2 on a 1-bit port"
    assert _unbuildable([{"outputs": {"q": 1}}], widths) == ""
    assert _unbuildable([{"outputs": {"wide": 255}}], widths) == ""
    assert _unbuildable([{"outputs": {"wide": 256}}], widths)
    assert _unbuildable([{"outputs": {"q": -1}}], widths)


def test_an_undeclared_port_is_not_screened():
    """Over-approximating here would drop real evidence, and the declared set
    is the only thing this can be checked against."""
    from specflow.refmodel.adequacy import _unbuildable

    assert _unbuildable([{"outputs": {"internal": 999}}], {"q": 1}) == ""


def test_the_widths_come_from_the_contract():
    from specflow.refmodel.adequacy import _declared_widths

    assert _declared_widths({"io": [
        {"name": "q", "dir": "output", "width": 4},
        {"name": "f", "dir": "output"},
    ]}) == {"q": 4, "f": 1}


def test_a_survivor_is_described_by_its_EFFECT_not_its_source_edit():
    """The report defect that sent an earlier analysis after a phantom filter.

    `mutant.description` names the source edit -- "line 48: 1 becomes 2" -- and
    read alone that looks like a design no hardware can be. The observable
    truth for that same mutant was `scl_oen 1->0`: SCL driven low instead of
    released after reset, an ordinary and serious defect the oracle missed.
    """
    from specflow.refmodel.adequacy import _effect

    base = [{"edge": 0, "inputs": {}, "outputs": {"scl_oen": 1, "busy": 0}},
            {"edge": 1, "inputs": {}, "outputs": {"scl_oen": 1, "busy": 0}}]
    mutant = [{"edge": 0, "inputs": {}, "outputs": {"scl_oen": 0, "busy": 0}},
              {"edge": 1, "inputs": {}, "outputs": {"scl_oen": 0, "busy": 0}}]
    got = _effect(base, mutant, {"scl_oen", "busy"})
    assert got == "scl_oen 1->0", got
    # A port the oracle does not read is not reported, and neither is a
    # repetition of the same transition on later rows.
    assert "busy" not in got


def test_effect_says_so_when_nothing_at_the_ports_moved():
    """Silence would read as "no evidence gathered" rather than "none found"."""
    from specflow.refmodel.adequacy import _effect

    rows = [{"edge": 0, "inputs": {}, "outputs": {"scl_oen": 1}}]
    assert _effect(rows, rows, {"scl_oen"}) == "no port difference"
