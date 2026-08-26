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

REQ = {"uid": "REQ-0000", "text": "when a is 7, q moves"}
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
    assert abandoned == {"REQ-0000": "never reached"}
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
    assert abandoned == {"REQ-0000": "never reached"}
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
    stage_at = src.index("gone, staging = stage_unexercised(")
    loop_at = src.index("for rounds in range(1, verifications + 1):")
    assert loop_at < stage_at, "staging must sit inside the verify loop"
    assert "if rounds == 1 and want_staging and witness:" in src


def test_a_round_that_staged_takes_another_pass_even_with_nothing_rejected():
    """Staging changes the evidence, so the set must be re-verified.

    Before this, `if not ask: break` ended the loop the moment nothing was
    rejected -- so a newly reachable oracle went straight to `_dispositions`
    and `freeze` without one run that decides it.
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    tail = src[src.index("if rounds == verifications:"):]
    assert "if not staged_now:" in tail and "break" in tail
    assert "continue" in tail, "a staged round must re-verify, not stop"


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
