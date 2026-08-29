"""[O] stages the scenarios nothing reaches, and knows whether it worked.

z-i2c ended with 33 unexercised oracles and `stimulus_added: 0` on all three
debug turns, because the only route to stage one was a tool inside a turn that
never called it. Detection and repair both belong here: `build_artifacts` orders
stimulus before [O], `stimulus_for_scenario` is standalone, and liveness is
already measured against the witness with no reference model in existence.
"""

from __future__ import annotations

from specflow import oracles_stage as O
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {
    "module_name": "m",
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "rst_n", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 8},
        {"name": "q", "dir": "output", "width": 8},
    ],
}

WITNESS = '''from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]

    def reset(self):
        self.n = 0

    def step(self, i):
        if not hasattr(self, "n"):
            self.reset()
        self.n = self.mask(self.n + i.get("a", 0), 8)
        return {"q": self.n}
'''

#: Abstains unless `a` was driven to 7 -- the scenario the loop must stage.
ORACLE = '''def decide(trace):
    for row in trace:
        if row["inputs"].get("a") == 7:
            return (row["outputs"]["q"] != 0, row["edge"], "q moved")
    return (None, None, "a was never driven to 7")
'''

REQ = {"uid": "REQ-0000", "text": "when a is 7, q moves",
       "needs": ["testplan", "refmodel"]}
NORM = {"REQ-0000": {"activation": {"text": "a is 7", "inputs": {"a": 7}},
                     "observable": ["q"], "expectation": "q is non-zero"}}


def _oracle(source=ORACLE):
    return RequirementOracle(req_uid="REQ-0000", tp_uids=[],
                             clause="q moves", source=source)


class _Gen:
    """Stands in for `stimulus_for_scenario`. Records every hint it was given."""

    def __init__(self, *scripted):
        self.scripted, self.hints = list(scripted), []

    def __call__(self, *, requirement, contract, port, what_the_scenario_needs):
        self.hints.append(what_the_scenario_needs)
        return self.scripted.pop(0) if self.scripted else []


def _run(gen, **kw):
    import specflow.testcase_agent as ta

    original = ta.stimulus_for_scenario
    ta.stimulus_for_scenario = gen
    try:
        return O.stage_unexercised(
            held={"REQ-0000": kw.pop("oracle", _oracle())},
            unexercised={"REQ-0000": "never triggered"},
            requirements=[REQ], normalized=NORM, contract=CONTRACT,
            testplan=kw.pop("testplan", []),
            stimulus_by_tp=kw.pop("stimulus_by_tp", {}),
            witness=kw.pop("witness", WITNESS), port=object(), **kw)
    finally:
        ta.stimulus_for_scenario = original


MISS = [{"inputs": {"a": 1}, "hold": 4}]
HIT = [{"inputs": {"a": 7}, "hold": 4}]


def test_the_loop_stops_when_the_check_stops_abstaining():
    """THE MECHANICAL TEST. An oracle abstains exactly when its activation never
    occurred, so a non-None result IS the proof the scenario is now staged --
    computed from the run, not claimed by the generator."""
    gen = _Gen(HIT)
    abandoned, record = _run(gen)
    assert abandoned == {}
    assert record["REQ-0000"]["reached_at_attempt"] == 1


def test_the_loop_stops_on_a_FAILING_check_exactly_as_on_a_passing_one():
    """THE ANTI-VACUITY PIN.

    Gating on `ok is True` would be the vacuity failure moved down a level:
    stimulus tuned until the implementation passes is stimulus selected to
    avoid finding bugs, silently and under a green artifact. The loop asks "is
    this scenario staged", which is settled the moment the check stops
    abstaining -- whichever way it then decides.
    """
    fails = ORACLE.replace('row["outputs"]["q"] != 0', 'False')
    gen = _Gen(HIT)
    abandoned, record = _run(gen, oracle=_oracle(fails))
    assert abandoned == {}, "a failing check is still a STAGED scenario"
    assert record["REQ-0000"]["reached_at_attempt"] == 1
    assert "False" in record["REQ-0000"]["attempts"][0]["outcome"]


def test_a_requirement_never_reached_is_abandoned_with_its_attempt_count():
    """"staged N times, never reached" and "nobody tried" stop being the same
    verdict. That distinction is what the discard is gated on."""
    gen = _Gen(MISS, MISS, MISS)
    abandoned, record = _run(gen)
    assert abandoned == {"REQ-0000": "never reached in 3 attempt(s)"}
    assert record["REQ-0000"]["reached_at_attempt"] is None
    assert len([t for t in record["REQ-0000"]["attempts"] if t.get("staged")]) == 3


def test_each_retry_carries_what_the_last_attempt_actually_did():
    """A retry that only rephrases is a retry that learns nothing.

    The current `add_stimulus` docstring ASKS the agent to "describe it more
    concretely rather than repeating", which is a request, not a mechanism.
    """
    gen = _Gen(MISS, MISS, HIT)
    _run(gen)
    assert len(gen.hints) == 3
    assert gen.hints[0] != gen.hints[1]
    assert "Attempt 1 did not stage it" in gen.hints[1]
    assert "a=7" in gen.hints[1], "the required value is named"


def test_an_undriven_activation_value_is_diagnosed_mechanically():
    """`check_static` decides an input-only activation FROM THE STEPS ALONE --
    no model, no replay, no doubt -- and names the miss precisely."""
    gen = _Gen(MISS, MISS, MISS)
    _, record = _run(gen)
    first = record["REQ-0000"]["attempts"][0]
    assert first["diagnosis"] == "a required input value was never driven"
    assert "a=7" in first["evidence"]["activation"]


def test_the_budget_is_spent_once_across_requirements():
    gen = _Gen(MISS, MISS, MISS)
    _, record = _run(gen, budget=1)
    staged = [t for t in record["REQ-0000"]["attempts"] if t.get("staged")]
    assert len(staged) == 1
    assert record["REQ-0000"]["attempts"][-1]["outcome"] == "budget spent"


def test_staged_testpoints_are_appended_never_substituted():
    """Appending cannot make a scenario stop occurring; editing could, which
    would turn a VIOLATES into a NOT_EXERCISED -- the `add_testcase` rule."""
    stim = {"TP-0000": [{"inputs": {"a": 1}, "hold": 1}]}
    gen = _Gen(HIT)
    _run(gen, stimulus_by_tp=stim)
    assert stim["TP-0000"] == [{"inputs": {"a": 1}, "hold": 1}]
    assert len(stim) == 2


def test_a_generator_that_produces_nothing_is_recorded_not_crashed():
    gen = _Gen()
    abandoned, record = _run(gen)
    assert abandoned == {"REQ-0000": "never reached in 3 attempt(s)"}
    assert all("nothing gate-clean" in t["outcome"]
               for t in record["REQ-0000"]["attempts"])


def test_nothing_runs_without_a_witness():
    """The witness is the only implementation in existence at [O]. Without one
    there is nothing to replay against, and inventing a verdict would be worse
    than reporting none."""
    assert _run(_Gen(HIT), witness="") == ({}, {})


# --- staging runs after the FIRST verify pass, and what it changes is
# --- re-verified -----------------------------------------------------------


def test_staging_is_inside_the_verify_loop_not_after_it():
    """Section 7.1: "After [O]'s FIRST verify pass".

    `verify_one`'s evidence-dependent legs have nothing to decide on for an
    oracle whose scenario nothing reaches, so it cannot be convicted -- and
    equally cannot be improved, because the repair round hands the author a
    check with no counterexample. Staging after the whole loop spent every
    round blind on roughly a third of the set (n-i2c 24 of 70, z-i2c 33).
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    loop_at = src.index("for rounds in range(1, verifications + 1):")
    stage_at = src.index("gone, staging = stage_unexercised(")
    gate_at = src.index("why, may_quote, notes = verify_one(")
    repair_at = src.index("again, _ = run_oracle_gen(")
    assert loop_at < stage_at < gate_at < repair_at, (
        "the round must run generate/repair -> STAGE -> GATE. Staging after the "
        "gate is what made the routes one-way on d1-i2c.")
    assert "if rounds == 1 and want_staging" not in src, (
        "staging must run EVERY round: a check rewritten at round 2 has a "
        "different trigger, and the old scenario verdict is about a check that "
        "no longer exists")
    assert "survivors = {u: o for u, o in held.items() if u not in rejected}" not in src, (
        "eligibility is `this check decides nothing`, full stop -- a rejected "
        "check must not be excluded from staging")


def test_the_gate_always_decides_against_the_stimulus_staging_just_added():
    """The reason the extra re-verify pass could be deleted.

    Staging used to run AFTER the gate, so a newly reachable oracle needed a
    whole extra round to be judged against evidence that now decided it, and
    `if not ask: break` carried an exception to allow it. Staging now runs
    BEFORE the gate in the same round, so the exception is not merely
    unnecessary -- it must be ABSENT, or a round that stages and rejects nothing
    spins without regenerating anything.
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    assert src.index("gone, staging = stage_unexercised(") < src.index(
        "why, may_quote, notes = verify_one(")
    assert "staged_now" not in src, "the extra-pass flag has no meaning now"
    tail = src[src.index("if rounds == verifications:"):]
    assert "continue" not in tail.split("again, _ = run_oracle_gen(")[0], (
        "a round that staged must fall through to the gate, not take another")


def test_abandonment_from_the_resolution_pass_survives_staging():
    """`stage_unexercised` returns a FRESH dict and the call site rebound it.

    Every "no observation route found" recorded alongside it was discarded, so
    a requirement the resolution pass could not route stayed in `trusted` and
    was frozen -- the exact opposite of abandoning it.
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    assert "abandoned.update(gone)" in src
    assert "abandoned, staging = stage_unexercised(" not in src


def test_staging_is_actually_CALLED_during_round_one(tmp_path, monkeypatch):
    """Executed, not read.

    The three tests above assert the SOURCE looks right, which proves nothing
    about whether the branch runs -- and the live run reached round 2 with no
    stimulus minted, which is exactly the observation a source-text test cannot
    explain. This one drives `run_oracle_stage` and records the call.
    """
    import json as _json

    from specflow import oracles_stage as _O
    from tests.test_oracles_stage import (CONTRACT, GOOD, REQS, STIM, TESTPLAN,
                                          WITNESS, _Port, _reply)

    seen = {}

    def _spy(**kw):
        seen["round"] = True
        seen["held"] = sorted(kw["held"])
        seen["unexercised"] = dict(kw["unexercised"])
        return {}, {}

    monkeypatch.setattr(_O, "_witness", lambda **_kw: (WITNESS, _O.WITNESS))
    monkeypatch.setattr(_O, "stage_unexercised", _spy)
    _O.run_oracle_stage(
        requirements=REQS, contract_json=_json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, want_staging=True)
    assert seen.get("round"), "stage_unexercised was never called"
    assert "REQ-0001" in seen["held"]


def test_staging_is_skipped_when_the_switch_is_off(tmp_path, monkeypatch):
    import json as _json

    from specflow import oracles_stage as _O
    from tests.test_oracles_stage import (CONTRACT, GOOD, REQS, STIM, TESTPLAN,
                                          WITNESS, _Port, _reply)

    called = []
    monkeypatch.setattr(_O, "_witness", lambda **_kw: (WITNESS, _O.WITNESS))
    monkeypatch.setattr(_O, "stage_unexercised",
                        lambda **kw: (called.append(1), ({}, {}))[1])
    _O.run_oracle_stage(
        requirements=REQS, contract_json=_json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, want_staging=False)
    assert called == []


# --- abandonment must be EARNED, and the budget must fit the work ----------


def test_a_requirement_the_budget_never_reached_is_NOT_abandoned():
    """The anti-shortcut pin, and it fired live.

    a2-i2c's flat `STAGING_BUDGET = 12` minted 12 testpoints, covered 4
    requirements, and recorded the other THIRTY-SIX as `"never reached"` -- a
    claim about the design and the stimulus -- when no stimulus had ever been
    generated for them. Section 8.0: "a requirement may only be abandoned if
    the attempt actually ran... without that pairing the gate rewards not
    trying." Budget exhaustion IS "the loop did not run".
    """
    from specflow.oracles_stage import BUDGET_SPENT, stage_unexercised

    gen = _Gen()
    abandoned, record = _run(gen, budget=0)          # nothing may be minted
    assert abandoned == {}, "nothing was attempted, so nothing may be abandoned"
    outcomes = [t["outcome"] for t in record["REQ-0000"]["attempts"]]
    assert outcomes == [BUDGET_SPENT]
    assert record["REQ-0000"]["attempted"] == 0
    assert stage_unexercised is not None


def test_a_generator_that_RAN_and_produced_nothing_still_counts_as_an_attempt():
    """The distinction is whether the generator was INVOKED, not whether it
    returned something usable. A generator that ran and came back empty is a
    finding about the scenario; a budget that ran out is a finding about us."""
    gen = _Gen()
    abandoned, record = _run(gen)
    assert abandoned == {"REQ-0000": "never reached in 3 attempt(s)"}
    assert record["REQ-0000"]["attempted"] == 3
    assert record["REQ-0000"]["staged"] == 0


def test_the_budget_is_sized_from_the_number_of_unexercised_oracles():
    """A flat constant borrowed from [D]'s per-turn budget is what broke: 41
    oracles wanting 3 attempts each against a budget of 12."""
    from specflow import oracles_stage as O

    assert O.STAGING_BUDGET_PER_ORACLE >= 1
    assert not hasattr(O, "STAGING_BUDGET"), "the flat constant must be gone"
    import inspect
    src = inspect.getsource(O.stage_unexercised)
    assert "len(unexercised)) * STAGING_BUDGET_PER_ORACLE" in src


def test_a_route_is_refuted_only_when_NONE_of_its_ports_moved():
    """`route_never_moved` was the LIST of silent ports, so it was truthy when
    any port was quiet -- and the message said all of them were.

    Live on a2-i2c: REQ-0006 is observable at six ports, three of which moved
    on every attempt, and all three retries were told "the ports this
    requirement is observed on never moved, so the observation route is what is
    wrong, not the stimulus". That is worse than an unhelpful hint -- it aims
    the retry away from the stimulus and at a route that was working.
    """
    from specflow.oracles_stage import _diagnose

    partial = {"first_change": {"a": 3, "b": None}, "route_never_moved": False}
    assert "never moved" not in _diagnose(partial)
    allsilent = {"first_change": {"a": None, "b": None},
                 "route_never_moved": True}
    assert "never moved" in _diagnose(allsilent)


# --- the two classified failures: reset scenarios and unconditional checks --


def test_a_reset_scenario_is_told_to_use_a_RESET_STEP():
    """Reset is not a drivable input and the hint never said so.

    a2-i2c's three genuinely-attempted reset requirements -- REQ-0006, 0007,
    0009 -- spent every attempt driving inputs. Their ports moved each time, so
    the design was running; the reset scenario was simply never staged.
    """
    from specflow.oracles_stage import _hint

    shape = {"activation": {"text": "rst is asserted high at a rising edge of clk"}}
    h = _hint({"uid": "REQ-0007", "text": "reset clears internal state"},
              shape, None, 0)
    assert '{"reset": true}' in h
    assert "not a drivable input" in h


def test_a_two_RESET_design_is_told_to_NAME_the_port():
    """`{"reset": true}` asserts both at the same edge, which is precisely the
    state a requirement about ONE reset can never be observed in.

    Measured on a2-i2c: 204 replayed edges, one row with rst==1 and nReset==0 on
    that same row, and zero rows with rst==1 and nReset==1 -- so REQ-0006 and
    REQ-0007 abstained by construction. The step schema takes a port list now;
    this hint is the only thing that can tell the generator which port to name,
    and until it did it pointed at the one form that cannot express the
    scenario.
    """
    from specflow.oracles_stage import _hint

    shape = {"activation": {"text": "rst is asserted high at a rising edge of clk"}}
    two = {"rst": 1, "nReset": 0}
    h = _hint({"uid": "REQ-0007", "text": "reset clears internal state"},
              shape, None, 0, reset_ports=two)
    assert '{"reset": ["rst"], "hold": N}' in h
    assert "nReset" in h.split("port-list form", 1)[1]

    # Naming neither leaves the choice to the generator rather than guessing it.
    vague = _hint({"uid": "REQ-0009", "text": "reset clears the sample history"},
                  {"activation": {"text": "the reset is asserted"}}, None, 0,
                  reset_ports=two)
    assert '{"reset": ["<port>"], "hold": N}' in vague


def test_a_single_RESET_design_is_not_told_to_name_it():
    """One reset port makes `true` and the list form identical, and the extra
    paragraph is then noise in a prompt that already has the right advice."""
    from specflow.oracles_stage import _hint

    h = _hint({"uid": "REQ-0007", "text": "reset clears internal state"},
              {"activation": {"text": "rst is asserted high"}}, None, 0,
              reset_ports={"rst": 1})
    assert '{"reset": true}' in h
    assert "MORE THAN ONE RESET PORT" not in h


def test_an_ordinary_scenario_is_not_told_about_reset():
    """The detector must stay narrow -- "start with reset released" describes
    the harness default and matching it would fire on nearly every testpoint."""
    from specflow.oracles_stage import _hint

    for text in ("a glitch on sda_i while scl_i is high",
                 "start with reset released and cmd = WRITE"):
        h = _hint({"uid": "REQ-0031", "text": "t"}, {"activation": {"text": text}},
                  None, 0)
        assert "reset step" not in h and '{"reset": true}' not in h


def test_the_reset_detector_learned_the_abbreviation():
    """It spelled out `reset` and normalisation writes `rst`."""
    from specflow.testcase_agent import _WANTS_RESET_ASSERTED as R

    for yes in ("on a rising clk edge while rst is asserted high",
                "rst is asserted high and a rising edge of clk occurs",
                "assert the reset", "rst=1"):
        assert R.search(yes), yes
    for no in ("rst is released", "reset is deasserted", "rst is not asserted",
               "start with reset released", "rst=0", "nReset=1", "always"):
        assert not R.search(no), no


def test_an_UNCONDITIONAL_activation_that_abstains_is_the_CHECK_s_defect():
    """It cannot be waiting for a scenario that is always true.

    a2-i2c's REQ-0003: activation "always", both observable ports moving on all
    three attempts, the check abstaining every time -- and it was recorded
    "never reached", blaming the stimulus author for a check that was broken.
    """
    import inspect

    from specflow import oracles_stage as O

    src = inspect.getsource(O.run_oracle_stage)
    block = src[src.index("if want_staging and witness:"):]
    assert ".unconditional" in block
    assert 'why = ("malformed:' in block, "must route to ORACLE_INVALID"
    assert "quotable[uid] = why" in block, "the AUTHOR is re-asked, not the stimulus"
    assert "unexer.pop(uid)" in block, "and it must not be staged"
    from specflow.refmodel.verdict import of_discard
    assert of_discard("malformed: the activation holds at all times") == "ORACLE_INVALID"


def test_an_arbitration_requirement_is_told_how_to_emulate_a_second_master():
    """`al` looks unstageable and is not.

    Arbitration-lost needs a competing master and there is none to ask -- but
    sda_i is drivable (only clk and the resets are excluded), so the contention
    is emulated by driving the line low while the controller has released it,
    with `until` waiting for the release rather than guessing when it happens.

    Three of a2-i2c's five route-refused abandonments hinge on `al` -- REQ-0010,
    REQ-0020, REQ-0021 -- all refused with "the ports this requirement is
    observed on never moved". The schema could always say this; nothing ever
    suggested it, which is the same shape as the reset case.
    """
    from specflow.oracles_stage import _hint

    h = _hint({"uid": "REQ-0021", "text": "al is asserted when SDA is released"},
              {"activation": {"text": "during the WRITE arbitration-check phase"},
               "observable": ["al", "sda_oen"]}, None, 0)
    assert "ARBITRATION LOST" in h
    assert "sda_i=0" in h and "sda_oen" in h


def test_the_arbitration_hint_is_withheld_from_everything_else():
    """A hint offered to every requirement is noise, and this one describes a
    contention no ordinary scenario should stage."""
    from specflow.oracles_stage import _hint

    h = _hint({"uid": "REQ-0031", "text": "the filter suppresses a glitch"},
              {"activation": {"text": "a glitch on sda_i while scl_i is high"},
               "observable": ["busy"]}, None, 0)
    assert "ARBITRATION LOST" not in h


def test_reset_and_arbitration_hints_do_not_exclude_each_other():
    from specflow.oracles_stage import _hint

    h = _hint({"uid": "REQ-0010", "text": "al after reset"},
              {"activation": {"text": "rst is asserted high at a rising edge"},
               "observable": ["al"]}, None, 0)
    assert "ARBITRATION LOST" in h and "reset step" in h


# ------------------------------------- the minted element passes S2's own gate


def _gate_errors(elements: list[dict], requirements: list[dict]) -> list:
    """The REAL S2 gate over a testplan, which is what `--reuse` re-runs."""
    from specflow.s2_testplan import gate
    from specflow.schema import TestplanOutput

    out = TestplanOutput.model_validate({"elements": elements})
    return [i for i in gate(requirements, out) if i.severity == "error"]


def test_a_staged_testpoint_passes_the_gate_that_planned_the_others():
    """THE LOAD-BEARING PIN, and the defect it fixes is an ORDERING one.

    The staging loop appends to `testplan` after S2's gate has already run and
    nothing re-gates it, so `--reuse` on the NEXT run was the first thing ever
    to look at these elements -- and it rejected them, which forced S2 and S3 to
    regenerate on every resumed run. Measured on d1-i2c: its own testplan failed
    its own gate with 106 errors over the 53 elements the loop had minted.
    """
    gen = _Gen(HIT)
    testplan: list[dict] = []
    _run(gen, testplan=testplan)
    assert len(testplan) == 1, "the loop staged nothing, so this pins nothing"
    assert _gate_errors(testplan, [REQ]) == []


def test_the_staged_element_quotes_the_normalized_expectation():
    """Not invented prose. Filling a field to satisfy a gate would make the gate
    measure nothing -- a vacuous check, one artifact up."""
    el = O._staged_element("TP-0009", "REQ-0000", REQ, NORM["REQ-0000"],
                           stimulus="drive a=7")
    assert el["expected_response"] == "q is non-zero"
    assert "REQ-0000" in el["check_method"] and "q" in el["check_method"]
    assert el["covers"] == ["REQ-0000@1"] and el["stimulus"] == "drive a=7"


def test_a_requirement_with_no_normalized_expectation_still_gates_clean():
    """The weaker answer is the requirement's own text, and it is still TRUE.
    An element that cannot say what is expected is what the gate exists to
    reject, so falling through to an empty string is not an option."""
    el = O._staged_element("TP-0009", "REQ-0000", REQ, {"observable": ["q"]},
                           stimulus="drive a=7")
    assert el["expected_response"] == REQ["text"]
    assert _gate_errors([el], [REQ]) == []


# --------------------- staging runs every round, and may now gate (#130)


def test_attempts_are_per_requirement_not_per_round():
    """Three rounds of three attempts is nine, and "staged N times, never
    reached" would stop being true of anything. `prior` carries the count."""
    gen = _Gen(MISS, MISS, MISS)
    tp1: list[dict] = []
    _, first = _run(gen, testplan=tp1, attempts=2)
    assert first["REQ-0000"]["attempted"] == 2

    # Round 2, same requirement, budget already spent: no further generator call
    gen2 = _Gen(HIT)
    _, second = _run(gen2, testplan=tp1, attempts=2, prior=first)
    assert gen2.hints == [], "an exhausted requirement must not be re-asked"
    assert second["REQ-0000"]["attempted"] == 2, "the count carries, not restarts"


def test_abandonment_waits_for_the_last_round():
    """Between rounds the AUTHOR REWRITES THE CHECK, so its activation is a
    different scenario. "Never reached" taken early is a verdict about a trigger
    that no longer exists."""
    gone, rec = _run(_Gen(MISS, MISS), attempts=2, final=False)
    assert gone == {}, "not the last round -- record the attempts, judge nothing"
    assert rec["REQ-0000"]["attempted"] == 2

    gone2, _ = _run(_Gen(), attempts=2, prior=rec, final=True)
    assert gone2 == {"REQ-0000": "never reached in 2 attempt(s)"}, (
        "a requirement whose attempts an earlier round spent must still reach "
        "its disposition on the last round")


# ------------------------------------------- the `unreached` gate and its guards


def _record(**kw):
    base = {"attempted": 2, "reached_at_attempt": None, "staged": 2,
            "attempts": [{"attempt": 1, "staged": "TP-0001",
                          "evidence": {"inert": True}}]}
    base.update(kw)
    return base


def test_an_unattempted_check_is_never_convicted_of_being_unreached():
    """THE ANTI-SHORTCUT PIN. A discard must be EARNED by an attempt that ran,
    or the gate rewards not trying -- section 8.0's rule, and the one that keeps
    this narrower than "unexercised is a finding", which the module refuses."""
    o = _oracle()
    o.tp_uids = ["TP-0000"]
    for record in (None, {}, _record(attempted=0), _record(reached_at_attempt=2)):
        assert O._unreached(o, record, WITNESS, CONTRACT, {"TP-0000": MISS},
                            base="step", transactional=True) == ""


def test_a_check_that_decides_somewhere_is_not_unreached():
    """Zero, not partial. Deciding on one testpoint and not another is ordinary."""
    o = _oracle()
    o.tp_uids = ["TP-0000", "TP-0001"]
    stim = {"TP-0000": HIT, "TP-0001": MISS}       # HIT makes the check decide
    assert O._unreached(o, _record(), WITNESS, CONTRACT, stim,
                        base="step", transactional=True) == ""


def test_a_refuted_observation_route_is_not_the_check_s_fault():
    """`route_never_moved` is a finding against normalisation. Re-asking the
    check author for it sends the finding to the party who cannot act on it."""
    o = _oracle()
    o.tp_uids = ["TP-0000"]
    rec = _record(attempts=[{"attempt": 1, "staged": "TP-0001",
                             "evidence": {"route_never_moved": True}}])
    assert O._unreached(o, rec, WITNESS, CONTRACT, {"TP-0000": MISS},
                        base="step", transactional=True) == ""


def test_an_exhausted_staging_attempt_convicts_and_says_what_was_tried():
    """The check decides nothing AND an independent author could not reach it.
    That pairing is what the ordering earns -- before staging ran first, an
    abstention could not be attributed and the module refused to try."""
    o = _oracle()
    o.tp_uids = ["TP-0000"]
    why = O._unreached(o, _record(), WITNESS, CONTRACT, {"TP-0000": MISS},
                       base="step", transactional=True)
    assert why.startswith("unreached: ")
    assert "2 attempt(s)" in why
    assert "nothing in the design moved" in why, "the diagnosis must travel"
    from specflow.refmodel.verdict import of_discard
    assert of_discard(why) == "ORACLE_INVALID"
