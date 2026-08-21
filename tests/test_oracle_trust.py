"""The three gates an oracle passes before it may drive a repair loop.

The gates that convict are easy to write and easy to get wrong in the same
direction: too eager, and a sound oracle is discarded for reasons that are
about the stimulus rather than about the oracle. Most of this file is about the
two ways that happens.
"""

from __future__ import annotations

from specflow.refmodel import trust
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
        {"name": "ack", "dir": "output", "width": 1},
    ]
}
PLAN = [{"uid": "TP-0000"}]
STIM = {"TP-0000": [{"inputs": {"a": 3}, "hold": 8}]}

#: `q` accumulates through arithmetic with several mutable constants; `ack`
#: pulses on the third edge. Two independent signals, so a mutant can move one
#: and not the other -- and enough q-arithmetic that a q-oracle sees at least
#: `MIN_IN_SCOPE` mutants, which is what makes a conviction test possible at all.
GOOD = '''from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q", "ack"]

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, "n"):
            self.reset()
        self.n = self.mask(self.n * 2 + i.get("a", 0) + 1, 8)
        self.k = self.k + 1
        return {"q": self.n, "ack": 1 if self.k == 3 else 0}
'''

ACK_PULSES = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["ack"] == 1:
            return (True, row["edge"], "ack pulsed")
    return (False, None, "ack never pulsed")
'''


def _oracle(source: str = ACK_PULSES, uid: str = "REQ-0000") -> RequirementOracle:
    return RequirementOracle(
        req_uid=uid, tp_uids=["TP-0000"], clause="ack pulses once", source=source
    )


def _screen(oracles, verdicts, source=GOOD, control=None):
    return trust.screen(oracles, verdicts, source, CONTRACT, STIM, PLAN,
                        base="step", control_source=control)


# ------------------------------------------------------- gate 1: agreement


def test_an_oracle_agreeing_with_its_author_survives():
    out = _screen([_oracle()], {"REQ-0000": "met"})
    assert [o.req_uid for o in out.trusted] == ["REQ-0000"]


def test_an_oracle_contradicting_its_author_is_discarded():
    """The judge said not_met; its own oracle passes the same model."""
    out = _screen([_oracle()], {"REQ-0000": "not_met"})
    assert "disagreed" in out.discarded["REQ-0000"]
    assert not out.trusted


def test_an_oracle_that_fails_the_model_matches_a_not_met_verdict():
    never = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["ack"] == 9:
            return (True, row["edge"], "found")
    return (False, None, "ack never reached 9")
'''
    out = _screen([_oracle(never)], {"REQ-0000": "not_met"})
    assert out.trusted, "a failing oracle is exactly what not_met should produce"


# ----------------------------------------------------- gate 2: sensitivity


def test_an_oracle_no_mutant_can_move_is_unknown_not_vacuous():
    """The escape the plan is most concerned about.

    A clause whose stimulus exercises it barely at all may admit no usable
    mutant. Calling that vacuity would discard a sound oracle for a defect in
    the testplan.
    """
    level, detail = trust.sensitivity(
        _oracle(), GOOD, CONTRACT, {"TP-0000": [{"inputs": {"a": 0}, "hold": 1}]},
        base="step")
    assert level != trust.CONVICTED, detail
    assert level == trust.UNKNOWN and "before silence means vacuity" in detail


def test_a_line_the_stimulus_never_executes_yields_no_mutant():
    """The first of the two exclusions, pinned at the mechanism.

    An oracle is driven by ONE requirement's stimulus, so a mutant on a path
    that stimulus never takes is invisible to it for reasons having nothing to
    do with the oracle's quality. Proposing one at all manufactures evidence of
    vacuity.
    """
    from specflow.refmodel import mutate_model

    with_dead_branch = GOOD.replace(
        "        self.k = self.k + 1\n",
        "        if i.get(\"a\", 0) == 7:\n"
        "            self.k = self.k + 100\n"
        "        self.k = self.k + 1\n",
    )
    dead = next(i + 1 for i, line in enumerate(with_dead_branch.splitlines())
                if "100" in line)
    executed = mutate_model.executed_lines(
        with_dead_branch, CONTRACT, STIM["TP-0000"], base="step")
    assert dead not in executed, "a=3, so the `== 7` body never runs"

    sites = mutate_model.mutants(with_dead_branch, lines=executed, limit=99)
    assert not [m for m in sites if m.line == dead], (
        "no mutant may be proposed on a line this stimulus cannot reach"
    )
    # And unrestricted, the same line DOES offer one -- so the filter is what
    # excluded it, not an absence of anything to mutate.
    assert [m for m in mutate_model.mutants(with_dead_branch, limit=99)
            if m.line == dead]


def test_a_change_outside_the_clause_is_not_an_in_scope_mutant():
    """The rule the out-of-scope exclusion rests on.

    An `ack` oracle must not be convicted for ignoring a `q`-only change.
    Convicting it would push oracles toward watching everything, which gate 3
    then punishes as over-strict -- the two gates would pull opposite ways and
    no oracle could satisfy both.
    """
    before = [{"edge": 0, "inputs": {}, "outputs": {"q": 1, "ack": 0}}]
    after = [{"edge": 0, "inputs": {}, "outputs": {"q": 99, "ack": 0}}]
    assert trust._project(before, {"ack"}) == trust._project(after, {"ack"}), (
        "a q-only change must be invisible to an ack oracle"
    )
    assert trust._project(before, {"q"}) != trust._project(after, {"q"})


def test_an_oracle_nothing_can_falsify_is_convicted():
    always = '''
def decide(trace):
    _ = [r["outputs"]["q"] for r in trace]
    return (True, 0, "asserts nothing about what it read")
'''
    o = RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                          clause="always", source=always)
    level, detail = trust.sensitivity(o, GOOD, CONTRACT, STIM, base="step")
    assert level == trust.CONVICTED, detail
    out = _screen([o], {"REQ-0000": "met"})
    assert "vacuous" in out.discarded["REQ-0000"]


def test_an_oracle_that_already_fails_is_not_mutation_tested():
    """It has demonstrated it fires; building mutants to prove it is waste."""
    never = '''
def decide(trace):
    _ = trace[0]["outputs"]["ack"]
    return (False, None, "no")
'''
    out = _screen([_oracle(never)], {"REQ-0000": "not_met"})
    assert out.sensitivity["REQ-0000"] == trust.SENSITIVE


# ---------------------------------------------------- gate 3: over-strict


def test_an_oracle_the_control_fails_is_discarded_as_over_strict():
    control = GOOD.replace('1 if self.k == 3 else 0', '0')   # never pulses ack
    out = _screen([_oracle()], {"REQ-0000": "met"}, control=control)
    assert "over-strict" in out.discarded["REQ-0000"]


def test_the_control_gate_is_skipped_when_no_control_exists():
    """Gates 1 and 2 must still apply on a design with nothing known-good."""
    out = _screen([_oracle()], {"REQ-0000": "met"}, control=None)
    assert out.trusted


# ------------------------------------------------------------- reporting


def test_the_rates_separate_unknown_from_convicted():
    """Collapsing them would read a thin stimulus as a bad judge."""
    always = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="always",
        source="def decide(trace):\n    return (True, 0, str(trace[0]['outputs']['q']))\n")
    out = _screen([_oracle(), always], {"REQ-0000": "met", "REQ-0001": "met"})
    rates = out.rates()
    assert set(rates) == {"trusted", "malformed", "disagreed", "convicted",
                          "over_strict", "unknown", "unexercised",
                          "control_unexercised"}
    assert rates["trusted"] + rates["convicted"] == 2


def test_a_malformed_oracle_is_rejected_before_any_mutation_sweep():
    bad = RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-9999"],
                            clause="x", source=ACK_PULSES)
    out = _screen([bad], {"REQ-0000": "met"})
    assert out.discarded["REQ-0000"].startswith("malformed:")
    assert "REQ-0000" not in out.sensitivity, "gate 2 must not have run"


# ------------------------------------- a scenario that never occurred (tri-state)


def test_an_oracle_whose_scenario_never_occurs_is_not_a_failing_model():
    """The defect this tri-state exists for, in one assertion.

    Measured on a-i2c: 13 of the 22 oracles a known-good control "failed" were
    failing with details like "no STOP condition observed in trace" and "nReset
    was never asserted low". They were handed to a debug agent as model defects.
    It could not fix them because there was nothing wrong to fix.
    """
    from specflow.refmodel.oracles import decide

    absent = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="on STOP, release SDA",
        source=("def decide(trace):\n"
                "    for row in trace:\n"
                "        if row['inputs'].get('stop'):\n"
                "            return (True, row['edge'], 'saw it')\n"
                "    return (None, None, 'no STOP condition observed in trace')\n"))
    out = decide(absent, [{"edge": 0, "inputs": {"a": 1}, "outputs": {"q": 0}}])
    assert out.unexercised(), "None must not be read as a broken oracle"
    assert not out.failed(), "and must not be read as a failing model"
    assert out.broken == ""
    assert "no STOP condition" in out.detail


def test_a_malformed_return_is_still_a_broken_oracle():
    """The tri-state must not turn every shape error into a free pass."""
    from specflow.refmodel.oracles import decide

    junk = RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"], clause="x",
                             source="def decide(trace):\n    return 'banana'\n")
    out = decide(junk, [])
    assert out.broken and not out.unexercised()


def test_the_control_failing_to_reach_a_scenario_is_not_over_strictness():
    """Gate 3 must not convict an oracle for a scenario the control never reaches.

    The clause is conditional on an event -- "after ack pulses, q must move" --
    so on a control that never pulses ack the oracle has nothing to judge. That
    is the control's coverage gap, not the oracle demanding too much, and the
    two must not land in the same bucket.

    Note the difference from a misuse of None: absent `ack` is unexercised HERE
    because ack is this clause's TRIGGER. For a clause that says "ack pulses",
    absent ack would be the failure itself, and returning None would be the
    oracle excusing a real defect.
    """
    after_ack = '''
def decide(trace):
    for n, row in enumerate(trace):
        if row["outputs"]["ack"] == 1 and n + 1 < len(trace):
            nxt = trace[n + 1]
            want = (row["outputs"]["q"] * 2 + 4) % 256
            got = nxt["outputs"]["q"]
            return (got == want, nxt["edge"], f"q={got} want={want}")
    return (None, None, "ack never pulses, so this clause never applies")
'''
    never_acks = GOOD.replace("1 if self.k == 3 else 0", "0")
    out = _screen([_oracle(source=after_ack)], {"REQ-0000": "met"},
                  control=never_acks)
    assert "REQ-0000" not in out.discarded, "not a discard"
    assert out.rates()["over_strict"] == 0, "and not counted as over-strict"
    assert "REQ-0000" in out.unexercised, "but it must be REPORTED"
    assert out.rates()["control_unexercised"] == 1


def test_an_unexercised_oracle_is_a_gate_1_conflict_worth_reconciling():
    """A judge that ruled on a clause its own check cannot see did not use it.

    Usually the tp_uids are wrong, which is exactly the kind of thing the
    reconcile call can fix -- so this leaves a conflict, not a bare discard.
    """
    blind = _oracle(source=(
        "def decide(trace):\n"
        "    for row in trace:\n"
        "        if row['inputs'].get('rst_n') == 0 and row['outputs']['ack']:\n"
        "            return (True, row['edge'], 'saw it')\n"
        "    return (None, None, 'never occurs: reset is never asserted')\n"))
    out = _screen([blind], {"REQ-0000": "met"})
    assert out.trusted == []
    assert "unexercised" in out.discarded["REQ-0000"]
    assert "REQ-0000" in out.conflicts
    assert "never occurs" in out.conflicts["REQ-0000"]
    assert out.rates()["unexercised"] == 1


# ------------------------------------------------------- the stimulus itself


def test_liveness_names_the_testpoints_that_move_nothing():
    """An inert testpoint makes every oracle naming it unjudgeable.

    Measured on a-i2c: 35 of 167 testpoints moved neither the generated model
    nor the known-good control, and the dominant cause was a prescaler starved
    of time -- 60 of 167 hold a `clk_cnt` so large the run ends before one
    divider tick completes.
    """
    from specflow.refmodel.oracles import stimulus_liveness

    live = stimulus_liveness(
        GOOD, CONTRACT,
        {"TP-0000": [{"inputs": {"a": 3}, "hold": 8}],       # q climbs
         "TP-DEAD": [{"inputs": {"a": 0}, "hold": 0}]},      # no edges at all
        base="step")
    assert "TP-0000" not in live.inert
    assert "TP-DEAD" in live.inert
    assert live.summary()["inert"] == 1
    assert live.summary()["inert_fraction"] == 0.5


def test_liveness_reports_a_model_that_will_not_replay_apart_from_an_inert_one():
    """Both leave a testpoint undecidable, for opposite reasons.

    Folding them together would report a broken model as a thin testplan.
    """
    from specflow.refmodel.oracles import stimulus_liveness

    live = stimulus_liveness("class NotAModel:\n    pass\n", CONTRACT, STIM, base="step")
    assert live.errors and not live.inert
    assert live.summary()["failed_to_replay"] == 1


def test_every_gate_leaves_a_conflict_the_judge_can_settle():
    """A discarded oracle with no conflict blames the MODEL for the judge's error.

    The requirement keeps its blocking verdict, the executable evidence is
    thrown away, and the reference model gets a prose failure it cannot fix.
    """
    vacuous = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="c",
        source="def decide(trace):\n    return (bool(trace[0]['outputs']['q'] >= 0), 0, 'always')\n")
    out = _screen([vacuous], {"REQ-0000": "met"})
    assert out.rates()["convicted"] == 1
    assert "REQ-0000" in out.conflicts, "convicted must be reconcilable"
    assert "VACUOUS" in out.conflicts["REQ-0000"]

    # Gate 1 must be SATISFIED before gate 3 can be reached, so the oracle has
    # to pass the judged model and fail the control -- the same model in both
    # roles would be caught as a disagreement first.
    never_acks = GOOD.replace("1 if self.k == 3 else 0", "0")
    never = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="c",
        source=("\ndef decide(trace):\n"
                "    for row in trace:\n"
                "        if row['outputs']['ack'] == 1:\n"
                "            return (False, row['edge'], 'ack pulsed')\n"
                "    return (True, None, 'ack stayed low')\n"))
    out2 = _screen([never], {"REQ-0000": "met"}, source=never_acks, control=GOOD)
    assert out2.rates()["over_strict"] == 1
    assert "REQ-0000" in out2.conflicts, "over-strict must be reconcilable"
    assert "KNOWN-GOOD" in out2.conflicts["REQ-0000"]
