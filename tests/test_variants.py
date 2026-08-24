"""Step 7's must-fail leg: a check nothing can fail is not a check.

`qualify.py:3-22` states the argument -- a suite can cover every testpoint and
still be unable to fail. What is new here is where the counterexample comes
from: `mutate_model` edits the reference model's SOURCE, so it asks "does this
oracle notice an edit to this implementation". A variant is derived from the
REQUIREMENT, so it asks the question I4 is about: does this oracle notice a
design that violates the requirement.
"""

from __future__ import annotations

from specflow.refmodel import variants as V
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.trust import CONVICTED, SENSITIVE, UNKNOWN

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]
}

CONFORMING = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
"""

#: Breaks the action clause: y is the inverse of a.
BROKEN_ACTION = CONFORMING.replace("'y': i['a']", "'y': 1 - i['a']")

#: Changes internal state only. Nothing at a port can tell it from CONFORMING.
EQUIVALENT = CONFORMING.replace(
    "    def step(self, i):",
    "    def step(self, i):\n        self._unused = i['a'] + 1")

STEPS = [{"a": 0}, {"a": 1}, {"a": 0}, {"a": 1}]

#: Watches y follow a. Catches BROKEN_ACTION.
WATCHFUL = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] != row['inputs']['a']:
            return False, row['edge'], 'y did not follow a'
    return True, 0, 'y followed a throughout'
"""

#: Names y and reads it, so it is well formed -- and cannot fail.
VACUOUS = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] not in (0, 1):
            return False, row['edge'], 'y is not a bit'
    return True, 0, 'y stayed a bit'
"""


def _out(source: str, clause: str = "y follows a") -> V.VariantOutput:
    return V.VariantOutput(reasoning="broke it", clause=clause, source=source)


# ------------------------------------------------------------------ choosing k


def test_k_is_the_requirement_s_own_clause_count():
    """Open question 2: k is determined by the requirement, never picked."""
    bare = V.kinds_for({"text": "the output follows the input"}, None)
    assert bare == [V.TRIGGER, V.ACTION]


def test_a_stated_bound_earns_a_threshold_variant():
    bounded = V.kinds_for({"text": "cmd_ack pulses high for one clock"}, None)
    assert bounded[:3] == [V.TRIGGER, V.THRESHOLD, V.ACTION]
    assert V.DURATION in bounded, (
        "'pulses high for one clock' states a length as plainly as it states "
        "a bound")


def test_stated_ordering_and_duration_earn_their_own_variants():
    """The two kinds the first three did not cover, and the gap was measured.

    A model scoring 30/168 against golden RTL differs from a known-good control
    on 134 of 167 testpoints in the view the oracles decide over, and 36 of 56
    trusted oracles assert on a diverging port in a testpoint they name. Two
    notice. Per (testpoint, port) that divergence is 636 duration, 186 value,
    171 order -- `ACTION` covers the value column and nothing covered the rest.
    """
    ordered = V.kinds_for(
        {"text": "the controller drives SDA low, then releases SCL"}, None)
    assert V.ORDER in ordered and V.DURATION not in ordered

    held = V.kinds_for({"text": "al remains set once asserted"}, None)
    assert V.DURATION in held


def test_a_requirement_stating_neither_gets_neither():
    """A variant for a property the requirement does not state is one an oracle
    is RIGHT to ignore, and convicting it for that is the over-strictness this
    stage exists not to cause."""
    plain = V.kinds_for({"text": "scl_o is tied low"}, None)
    assert plain == [V.TRIGGER, V.ACTION]


def test_the_normalized_form_is_read_too():
    """A bound stated in the expectation counts, not only in the raw text."""
    kinds = V.kinds_for(
        {"text": "the counter reports"},
        {"activation": {"text": "always"}, "expectation": "after 16 cycles"})
    assert V.THRESHOLD in kinds


# ------------------------------------------------------------------- isolation


def test_the_prompt_cannot_carry_an_oracle():
    """I4's structural half, asserted on the constructed artifact.

    Same enforcement as `oracle_gen`: a later edit wanting to pass the check
    would have to add a PARAMETER, which is a visible change to a signature.
    """
    prompt = V.build_prompt(
        requirement={"uid": "REQ-0001", "text": "y follows a"},
        kind=V.ACTION, contract_json="{}", contract=CONTRACT,
        conforming_source=CONFORMING)
    for forbidden in ("def decide(", "OracleResult", "tp_uids"):
        assert forbidden not in prompt, forbidden
    assert "conforming_implementation" in prompt
    assert V.WHAT_EACH_KIND_MEANS[V.ACTION] in prompt


# ------------------------------------------------------------------ the gate


def test_a_variant_that_changes_nothing_observable_is_refused():
    """Equivalence, decided by projection rather than by asking a model."""
    issues = V.gate_one(
        _out(EQUIVALENT), req_uid="REQ-0001", kind=V.ACTION, contract=CONTRACT,
        conforming_source=CONFORMING, steps=STEPS, observable={"y"})
    assert issues and "equivalent" in issues[0].path


def test_a_genuinely_different_variant_passes():
    assert V.gate_one(
        _out(BROKEN_ACTION), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"}) == []


def test_a_variant_that_will_not_run_is_refused():
    issues = V.gate_one(
        _out("class Model:\n    pass\n"), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"})
    assert issues


def test_a_variant_reaching_outside_specflow_is_refused():
    """The same sandbox screen the reference model gets."""
    issues = V.gate_one(
        _out("import os\n" + CONFORMING), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"})
    assert issues


# --------------------------------------------------------------- the must-fail


def _variants(*sources: str) -> list[V.Variant]:
    return [V.Variant(req_uid="REQ-0001", kind=k, clause="c", source=s)
            for k, s in zip((V.TRIGGER, V.THRESHOLD, V.ACTION), sources)]


def _oracle(source: str) -> RequirementOracle:
    return RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                             clause="y follows a", source=source)


def test_an_oracle_that_catches_a_variant_is_sensitive():
    got, why = V.must_fail(
        _oracle(WATCHFUL), _variants(BROKEN_ACTION), CONTRACT,
        {"TP-0000": STEPS})
    assert got == SENSITIVE
    assert "variant" in why


def test_an_oracle_nothing_can_fail_is_convicted():
    got, why = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION,
                                    BROKEN_ACTION),
        CONTRACT, {"TP-0000": STEPS})
    assert got == CONVICTED
    assert "passed all 3" in why


def test_silence_over_too_few_variants_is_not_vacuity():
    """`MIN_IN_SCOPE` transfers unchanged: one observation is not evidence."""
    got, _ = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION),
        CONTRACT, {"TP-0000": STEPS})
    assert got == CONVICTED, "two clauses is the requirement's own k, not too few"

    only_one = [V.Variant(req_uid="REQ-0001", kind=V.ACTION, clause="c",
                          source=BROKEN_ACTION)]
    got, _ = V.must_fail(_oracle(VACUOUS), only_one, CONTRACT,
                         {"TP-0000": STEPS})
    assert got == CONVICTED, "one variant IS this requirement's whole k"


def test_a_requirement_with_no_variant_is_unknown_not_convicted():
    got, why = V.must_fail(_oracle(VACUOUS), [], CONTRACT, {"TP-0000": STEPS})
    assert got == UNKNOWN
    assert "no variant" in why


def test_no_stimulus_is_unknown_not_convicted():
    got, why = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION), CONTRACT, {})
    assert got == UNKNOWN
    assert "stimulus" in why


def test_variants_of_another_requirement_are_not_evidence():
    other = [V.Variant(req_uid="REQ-0002", kind=V.ACTION, clause="c",
                       source=BROKEN_ACTION)]
    got, _ = V.must_fail(_oracle(WATCHFUL), other, CONTRACT,
                         {"TP-0000": STEPS})
    assert got == UNKNOWN


# --------------------------------------------- where the conviction now lives


def test_the_loop_no_longer_convicts_anything():
    """Vacuity is decided once, by the oracle stage, against variants that do
    not move. Deciding it per turn is what made VACUOUS wander 16, 18, 16 under
    an oracle set that was already frozen: gate 2 re-derives its mutants from
    the CURRENT model, so the conviction set moves as the agent edits."""
    import inspect

    from specflow.refmodel import compose

    src = inspect.getsource(compose._debug_turns)
    assert "must_fail" not in src
    assert "vacuous" not in src


def test_the_stage_is_what_convicts():
    from specflow import oracles_stage

    assert "must_fail" in inspect_source(oracles_stage.verify_one)


def inspect_source(fn) -> str:
    import inspect

    return inspect.getsource(fn)
