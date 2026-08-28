"""I1/I2: the oracle is written before any verdict, from the requirement alone.

The enforcement here is deliberately structural rather than a prompt rule. The
ISSTA-2026 misguidance result is that the implementation's PRESENCE IN CONTEXT
causes a mirrored oracle -- not the model's intent -- so "we asked it not to
look" is not a control. `validate._static_checks` (`validate.py:40-70`) already
applies the same reasoning to RTL contamination of the reference model: the
check reads the artifact.

Measured cost of not having this, on `a-i2c`: the generated model passed 35 of
54 trusted oracles while a known-good control passed 25, and 22 of 54 were
failed by that control outright.
"""

from __future__ import annotations

import inspect

from specflow.refmodel import oracle_gen
from specflow.refmodel.oracle_gen import build_prompt, gate_one, parse_response, OracleOutput

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "cmd_ack", "dir": "output", "width": 1},
    ]
}
REQ = {"uid": "REQ-0000", "text": "cmd_ack is high for exactly one clock",
       "spec_spans": [{"start": 0, "end": 10, "quote": "asserts cmd_ack"}]}
TESTPLAN = [{"uid": "TP-0000", "covers": ["REQ-0000@1"]}]

MODEL_SOURCE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['cmd_ack']

    def step(self, i):
        self._n = getattr(self, '_n', 0) + 1
        return {'cmd_ack': 1 if self._n == 3 else 0}
'''


def test_the_prompt_cannot_carry_an_implementation():
    """The strong form: there is no PARAMETER a design could arrive through.

    A dict-shaped context would let a later edit slip the model source in as one
    more key; a named signature makes that a visible change to a function.
    """
    params = set(inspect.signature(build_prompt).parameters)
    assert params == {"requirement", "contract_json", "contract",
                      "normalized", "issues", "previous"}
    assert not (params & {"source", "model", "trace", "behaviour",
                          "stimulus_by_tp", "testpoints", "verdict"})


def test_the_built_prompt_contains_no_implementation_and_no_trace():
    """Read the artifact back, which is what makes this a control rather than a
    restatement of the prompt's own instruction."""
    prompt = build_prompt(requirement=REQ, contract_json="{}", contract=CONTRACT)
    for forbidden in ("class Model", "RefModel", "def step", "OUTPUT_PORTS",
                      "observed_behaviour", "model_run_on_this_testpoint_stimulus"):
        assert forbidden not in prompt, f"{forbidden!r} reached the oracle prompt"
    # ... nor any fragment of an actual model.
    assert "self._n" not in prompt
    for line in MODEL_SOURCE.splitlines():
        if line.strip() and len(line.strip()) > 12:
            assert line.strip() not in prompt


def test_the_prompt_carries_the_requirement_and_its_ports():
    """Isolation must not be achieved by starving the stage."""
    prompt = build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT,
        normalized={"activation": {"text": "a command completes"},
                    "observable": ["cmd_ack"], "expectation": "high one clock"},
    )
    assert "cmd_ack is high for exactly one clock" in prompt
    assert "asserts cmd_ack" in prompt          # the spec span rides along
    assert '"observable"' in prompt             # the normalized form
    assert "cmd" in prompt and "clk" in prompt  # the declared ports


def test_the_generator_is_told_not_to_choose_testpoints():
    """`tp_uids` is the harness's, from S2's `covers`. On d-i2c, 17 of 23
    malformed oracles were malformed for this field alone -- 11 omitted it and 6
    invented names no testplan contains."""
    prompt = build_prompt(requirement=REQ, contract_json="{}", contract=CONTRACT)
    assert "Do NOT name testpoints" in prompt
    assert "tp_uids" not in oracle_gen.OracleOutput.model_fields


def test_the_prompt_states_the_clk_rule():
    """Every row IS an edge, so an oracle hunting a clock transition finds a
    flat line and reports it cannot see its scenario -- which reads as a thin
    testplan when nothing is wrong with the testplan."""
    prompt = " ".join(build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT).split())
    assert "NEVER look for a clock transition" in prompt
    assert "Every row IS one rising clock edge" in prompt


def test_the_prompt_says_ok_none_is_not_counted_against_the_design():
    """The tri-state has to be worth using. An oracle that returns False for an
    absent scenario sends someone to fix correct code -- 13 of 22 over-strict
    oracles on a-i2c did exactly that."""
    # Asserted on fragments that do not span a line break: the source wraps
    # inside a `#` comment block, so a phrase crossing two lines picks up a
    # stray marker even after whitespace normalisation. This exact trap has
    # cost this repo a false test failure once already.
    prompt = " ".join(build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT).split())
    assert "Return ok=None when THE ACTIVATION NEVER OCCURS" in prompt
    assert "Do NOT return False for that" in prompt
    assert "an oracle that passes" in prompt and "is vacuous" in prompt


def test_the_gate_reuses_well_formed_rather_than_re_deriving_a_screen():
    """An oracle is the same trust class as the reference model. A source that
    imports, or that names no declared port, is rejected here rather than
    discovered by screening a stage later."""
    ok = OracleOutput(clause="c", source=(
        "def decide(trace):\n"
        "    return (True, None, str(trace[0]['outputs']['cmd_ack']))"))
    assert gate_one(ok, req_uid="REQ-0000", tp_uids=["TP-0000"],
                    contract=CONTRACT, testplan=TESTPLAN) == []

    imports = OracleOutput(clause="c", source="import os\ndef decide(trace):\n    return True")
    assert gate_one(imports, req_uid="REQ-0000", tp_uids=["TP-0000"],
                    contract=CONTRACT, testplan=TESTPLAN)

    no_port = OracleOutput(clause="c", source="def decide(trace):\n    return (True, None, '')")
    issues = gate_one(no_port, req_uid="REQ-0000", tp_uids=["TP-0000"],
                      contract=CONTRACT, testplan=TESTPLAN)
    assert issues and "decides nothing observable" in issues[0].message


def test_a_missing_clause_is_rejected():
    """The clause is what lets a reader tell an over-strict oracle from a real
    defect. Without it a discarded oracle is unauditable."""
    out = OracleOutput(clause="", source="def decide(trace):\n    return True")
    issues = gate_one(out, req_uid="REQ-0000", tp_uids=["TP-0000"],
                      contract=CONTRACT, testplan=TESTPLAN)
    assert issues and issues[0].path.endswith(".clause")


def test_a_parse_failure_is_reported_as_one():
    out = parse_response("not json at all")
    assert out.reasoning.startswith("Parse Error: ")
    issues = gate_one(out, req_uid="REQ-0000", tp_uids=["TP-0000"],
                      contract=CONTRACT, testplan=TESTPLAN)
    assert issues and issues[0].path.endswith(".response")


def test_the_prompt_forbids_demanding_a_response_at_a_fixed_edge():
    """The largest measured cause of over-strict oracles, and it was a defect in
    this prompt rather than in the specification.

    `agent.py:104-109` tells the reference MODEL that the testbench compares the
    ordered sequence of distinct output states and ignores how long each is
    held, so it need not be cycle-accurate -- and `trace_compare.transactional`
    implements that. The oracle prompt never carried the rule over, so oracles
    held designs to a stricter standard than the comparison they feed.

    Measured on g-i2c: 27 of 77 isolated oracles are failed by an implementation
    scoring 181/181 against golden, and the dominant pattern is demanding the
    response too early -- "busy low when START detected at edge 13", when the
    design sees the START through a synchroniser and a majority filter.
    """
    prompt = " ".join(build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT).split())
    assert "DO NOT DEMAND A RESPONSE AT A PARTICULAR EDGE" in prompt
    assert "ORDERED SEQUENCE of distinct output states" in prompt
    assert "do not index a fixed edge" in prompt


def test_the_prompt_still_permits_a_duration_the_spec_actually_fixes():
    """The rule must not become "never check timing". `cmd_ack is high for
    exactly one clock` IS a duration the specification states, and an oracle
    that declines to check it demands nothing -- which the mutation gate then
    convicts. The two gates pull in opposite directions and the prompt has to
    name the line between them."""
    prompt = " ".join(build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT).split())
    assert "Demand an exact count only when the requirement itself states one" in prompt
    assert "exactly one clock" in prompt


def test_the_prompt_describes_the_transactional_trace_it_actually_receives():
    """The oracle is handed `transactional_view` output, not raw edges. A prompt
    describing the wrong shape is worse than no description: the author writes
    against `edge` arithmetic that no longer means what it says."""
    prompt = " ".join(build_prompt(
        requirement=REQ, contract_json="{}", contract=CONTRACT).split())
    assert "trace is a list of STATES, not of clock edges" in prompt
    assert "THE NEXT DISTINCT STATE, not the next clock" in prompt
    # `held` is how a duration claim is checked once repetition is collapsed.
    assert '"held": int' in prompt or "held\": int" in prompt or "held" in prompt
    assert "Do not compute with `edge`" in prompt


def test_the_worked_example_uses_the_shape_the_prompt_describes():
    """An example contradicting its own instructions is the instruction that
    wins. The cmd_ack example must check `held`, not count consecutive rows."""
    prompt = build_prompt(requirement=REQ, contract_json="{}", contract=CONTRACT)
    assert "r['held'] != 1" in prompt
    assert "for row in trace:\\n        if row['outputs']['cmd_ack']:" not in prompt


def test_no_design_can_reach_the_oracle_author_at_all():
    """The must-pass leg that used to run a witness here is gone, so this is now
    the stronger property: `gate_one` has no parameter a design's BEHAVIOUR
    could come back through, and `build_prompt` has none a design could enter
    through.

    Oracle generation moved before the reference model precisely so that an
    oracle cannot encode a design's choices. A repair round quoting a witness's
    trace reintroduced exactly that, one round later and harder to see -- and
    fitted to a generated guess rather than a real design.
    """
    import inspect

    from specflow.refmodel.oracle_gen import build_prompt, gate_one

    body = inspect.getsource(gate_one)
    for ran in ("_decide_over", "replay(", "trust."):
        assert ran not in body, f"generation runs a design: {ran}"

    taken = set(inspect.signature(build_prompt).parameters)
    assert not (taken & {"source", "model", "conforming_source", "witness",
                         "control", "observed_behaviour"}), taken



def test_the_author_is_told_to_check_transitions_not_levels():
    """The generation-side half of the idle-match finding.

    On an open-drain line the resting value and the "released" value are the
    same number, so `outputs[p] == released` matches index 0 before anything has
    happened. Measured: a check demanding SDA low before SCL release failed a
    design that did exactly that -- `sda_oen` 0 at edge 4, `scl_oen` 1 at edge 5
    -- because it took the first `scl_oen == 1`, which was idle. A sibling
    requirement stated the same ordering, so it was not a protocol disagreement.

    The detector (`liveness.judged_before_the_scenario`) catches this after the
    fact and only 3 of the 5 cases. This is the half that stops them being
    written, and it costs nothing per call.
    """
    import re

    from specflow.refmodel.oracle_gen import SYSTEM

    # Strip the comment markers before collapsing: the rule lives inside a
    # `#` block in the prompt, so a phrase that wraps a line comes back as
    # "TRANSITION, # NOT THE LEVEL". Asserting on the raw text has cost this
    # repo three times today alone.
    flat = re.sub(r"\s+", " ", SYSTEM.replace("#", " "))
    assert "LOOK FOR THE TRANSITION, NOT THE LEVEL" in flat
    # It must say WHY, not just what: the rule is unmemorable without the
    # open-drain fact that makes a level check match idle.
    assert "RESTING value" in flat and "SAME NUMBER" in flat
    # And point at where the polarity actually is, rather than assuming it.
    assert "notes" in flat


# ------------------------------------ the two halves of the level/action rule


def _author_prompt() -> str:
    from specflow.refmodel import oracle_gen

    return oracle_gen.build_prompt(
        requirement={"uid": "REQ-0001", "text": "t"},
        contract_json="{}", contract={"ports": []})


def test_the_transition_rule_carries_its_converse():
    """MEASURED, and this pin is the fix for it. The prompt said "WHEN THE
    REQUIREMENT DESCRIBES AN ACTION, LOOK FOR THE TRANSITION, NOT THE LEVEL"
    with a real case behind it -- on an open-drain line the resting value and
    the released value are the same number, so a level scan matches index 0 --
    and never said what following it costs on a requirement that states a
    STATE. 8 of one run's 43 control-refuted checks demanded a transition where
    the requirement stated a level, and a correct design that already holds the
    value and never changes it was convicted for being right.

    Both halves or neither: the rule is a choice between two readings, and a
    prompt carrying only one of them is what produced the class.
    """
    body = _author_prompt()
    # Fragments only, none crossing a line wrap: the prompt is a wrapped comment
    # block and an assertion spanning a break has cost this repo once already.
    assert "LOOK FOR THE TRANSITION" in body
    assert "AND THE CONVERSE" in body
    for phrase in ("requirement can describe a STATE rather than an ACTION",
                   "There a correct design may ALREADY hold the value",
                   "require the TRANSITION when the requirement names an ACTION",
                   "require the LEVEL when it names a STATE"):
        assert phrase in body, phrase


def test_strong_true_is_offered_with_the_boundary_it_lacked():
    """`strong=True` converts "the trace ended" into "the design failed". True
    for an OBLIGATION, false for a STATE, where it convicts on a short
    testpoint. The instruction existed with a measured count behind it (5 of 14
    abstentions) and no boundary at all."""
    body = _author_prompt()
    assert "strong=True" in body
    assert "OBLIGATION" in body
    assert "false for a STATE" in body


def test_absence_inside_an_opened_window_is_distinguished_from_no_window():
    """The ok=None rule was stated twice and both statements cover NO WINDOW.
    Every one of the 7 measured defects in this class is a window that OPENED
    and did not contain the evidence -- uncovered by the rule, and covered by
    `strong=True` pointing the other way."""
    body = _author_prompt()
    assert 'THAT RULE COVERS "NO WINDOW"' in body
    assert "the activation DID occur, the window opened" in body
    for phrase in ("absence IS the violation, and False is right",
                   "that is missing evidence and ok=None is"):
        assert phrase in body, phrase


def test_the_temporal_flags_state_the_cost_of_setting_them():
    """Both flags remove vacuity by converting an abstention into a conviction,
    so both have the same boundary and it runs the other way. Every occurrence
    of "already" in these two modules used to sit on the vacuity side."""
    from specflow.refmodel.temporal import eventually

    doc = eventually.__doc__ or ""
    assert "BOTH FLAGS HAVE THE SAME BOUNDARY" in doc
    assert "may hold the value from before the activation" in doc
    assert "trades vacuity for over-strictness" in doc
