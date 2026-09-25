"""Step 7's must-fail leg: a check nothing can fail is not a check.

`qualify.py:3-22` states the argument -- a suite can cover every testpoint and
still be unable to fail. What is new here is where the counterexample comes
from: `mutate_model` edits the reference model's SOURCE, so it asks "does this
oracle notice an edit to this implementation". A variant is derived from the
REQUIREMENT, so it asks the question I4 is about: does this oracle notice a
design that violates the requirement.
"""

from __future__ import annotations

import json

from specflow.refmodel import variants
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
        conforming_source=CONFORMING, steps=STEPS, observable={"y"}, whole_module_ok=True)
    assert issues and "equivalent" in issues[0].path


def test_a_genuinely_different_variant_passes():
    assert V.gate_one(
        _out(BROKEN_ACTION), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"}, whole_module_ok=True) == []


def test_a_variant_that_will_not_run_is_refused():
    issues = V.gate_one(
        _out("class Model:\n    pass\n"), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"}, whole_module_ok=True)
    assert issues


def test_a_variant_reaching_outside_specflow_is_refused():
    """The same sandbox screen the reference model gets."""
    issues = V.gate_one(
        _out("import os\n" + CONFORMING), req_uid="REQ-0001", kind=V.ACTION,
        contract=CONTRACT, conforming_source=CONFORMING, steps=STEPS,
        observable={"y"}, whole_module_ok=True)
    assert issues


# --------------------------------------------------------------- the must-fail


def _variants(*sources: str) -> list[V.Variant]:
    return [V.Variant(req_uid="REQ-0001", kind=k, clause="c", source=s)
            for k, s in zip((V.TRIGGER, V.THRESHOLD, V.ACTION), sources)]


def _oracle(source: str) -> RequirementOracle:
    return RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                             clause="y follows a", source=source)


def test_an_oracle_that_catches_a_variant_is_sensitive():
    got, why, _apart = V.must_fail(
        _oracle(WATCHFUL), _variants(BROKEN_ACTION), CONTRACT,
        {"TP-0000": STEPS})
    assert got == SENSITIVE
    assert "variant" in why


def test_an_oracle_nothing_can_fail_is_convicted():
    got, why, _apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION,
                                    BROKEN_ACTION),
        CONTRACT, {"TP-0000": STEPS})
    assert got == CONVICTED
    assert "passed all 3" in why


def test_silence_over_too_few_variants_is_not_vacuity():
    """`MIN_IN_SCOPE` transfers unchanged: one observation is not evidence."""
    got, _, _apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION),
        CONTRACT, {"TP-0000": STEPS})
    assert got == CONVICTED, "two clauses is the requirement's own k, not too few"

    only_one = [V.Variant(req_uid="REQ-0001", kind=V.ACTION, clause="c",
                          source=BROKEN_ACTION)]
    got, _, _apart = V.must_fail(_oracle(VACUOUS), only_one, CONTRACT,
                         {"TP-0000": STEPS})
    assert got == CONVICTED, "one variant IS this requirement's whole k"


def test_a_requirement_with_no_variant_is_unknown_not_convicted():
    got, why, _apart = V.must_fail(_oracle(VACUOUS), [], CONTRACT, {"TP-0000": STEPS})
    assert got == UNKNOWN
    assert "no variant" in why


def test_no_stimulus_is_unknown_not_convicted():
    got, why, _apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION), CONTRACT, {})
    assert got == UNKNOWN
    assert "stimulus" in why


def test_variants_of_another_requirement_are_not_evidence():
    other = [V.Variant(req_uid="REQ-0002", kind=V.ACTION, clause="c",
                       source=BROKEN_ACTION)]
    got, _, _apart = V.must_fail(_oracle(WATCHFUL), other, CONTRACT,
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


# ------------------------------------------- an unexercised variant is not a pass

#: Decides only once `a` has gone high; otherwise the clause's scenario never
#: occurred and it returns None. That is the third state `decide` exists to
#: keep separate from False, and the state `must_fail` used to lose.
CONDITIONAL = """\
def decide(trace):
    seen = False
    for row in trace:
        if row['inputs']['a'] == 1:
            seen = True
            if row['outputs']['y'] != 1:
                return False, row['edge'], 'y did not follow a'
    if not seen:
        return None, 0, 'a was never high; the scenario never occurred'
    return True, 0, 'y followed a whenever a was high'
"""

#: `a` never goes high, so CONDITIONAL is never triggered here.
QUIET_STEPS = [{"a": 0}, {"a": 0}, {"a": 0}, {"a": 0}]


def _oracle_over(source: str, *tps: str) -> RequirementOracle:
    return RequirementOracle(req_uid="REQ-0001", tp_uids=list(tps),
                             clause="y follows a", source=source)


def test_a_variant_that_never_triggered_the_oracle_is_not_a_pass():
    """The regression. `decide(...).failed()` is False both when the oracle
    passed the variant and when the variant's trace never reached the clause's
    scenario, and only the first is vacuity -- the second is a fact about the
    stimulus. Convicting on it is the same mistake `verify_one` refuses to make
    about unexercised oracles."""
    got, why, _apart = V.must_fail(
        _oracle_over(CONDITIONAL, "TP-QUIET"),
        _variants(BROKEN_ACTION, BROKEN_ACTION, BROKEN_ACTION),
        CONTRACT, {"TP-QUIET": QUIET_STEPS})

    assert got == UNKNOWN, "never triggered is not 'passed all three'"
    assert "never reached the scenario" in why
    assert "stimulus finding" in why


def test_unexercised_replays_do_not_count_toward_the_evidence_bar():
    """Worse than a miscount: `in_scope` is what satisfies
    `min(MIN_IN_SCOPE, len(mine))`, so the never-triggered replays were the
    evidence that licensed the conviction."""
    got, why, _apart = V.must_fail(
        _oracle_over(CONDITIONAL, "TP-QUIET"),
        _variants(BROKEN_ACTION, BROKEN_ACTION, BROKEN_ACTION),
        CONTRACT, {"TP-QUIET": QUIET_STEPS})

    assert got != CONVICTED
    assert "0 real observation" in why or "leaving 0" in why


def test_every_named_testpoint_decides_not_only_the_first():
    """`must_fail` replayed against `next(tp for tp in tp_uids if stimulus)`.
    Here the first named testpoint never triggers the oracle and the second
    catches the variant outright, so first-named-only reports the exact opposite
    of the truth. `_decide_over` carries the same measurement for screening."""
    got, why, _apart = V.must_fail(
        _oracle_over(CONDITIONAL, "TP-QUIET", "TP-0000"),
        _variants(BROKEN_ACTION),
        CONTRACT, {"TP-QUIET": QUIET_STEPS, "TP-0000": STEPS})

    assert got == SENSITIVE, "the second named testpoint catches it"
    assert "variant" in why


def test_an_oracle_that_is_triggered_and_still_silent_is_still_convicted():
    """The fix must not become an escape hatch. A check that RUNS, reaches its
    scenario, and passes a design breaking its own clause is vacuous, and
    nothing here changes that."""
    got, why, _apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION,
                                    BROKEN_ACTION),
        CONTRACT, {"TP-0000": STEPS})

    assert got == CONVICTED
    assert "passed all 3" in why


def test_a_conviction_carries_what_the_variant_did_differently():
    """The author was told a COUNT and nothing else.

    `_repair_issue` sent "passed all N variant(s) ... check the specific
    behaviour the clause states", which is what the author had already tried.
    That is the same starvation `_strengthen` had -- 0 of 72 successes -- one
    notch worse, since adequacy at least quoted a line number.

    Measured on the rejected sets of s-i2c and r-i2c, rebuilt from `agent_io`:
    every vacuous oracle has a variant differing from the conforming
    implementation at ports it READS -- 11 of 11 and 13 of 13, and every variant
    of every one, 22 of 22 and 19 of 19 replays. There was always something to
    send.
    """
    got, why, apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION), CONTRACT,
        {"TP-0000": STEPS}, conforming=CONFORMING)
    assert got == V.CONVICTED, (got, why)
    assert apart, "a conviction with a conforming design must name the difference"
    assert "edge" in apart and " in one and " in apart, apart


def test_the_conviction_never_says_which_design_is_correct():
    """The conforming side is the WITNESS -- a second reading of the same
    requirements by the same author. Telling the author it is right has the
    check written against it, and that exact move measured over-strictness
    27 -> 15 with convictions 2 -> 16: oracles relaxed until they stopped
    disagreeing with an implementation nobody had shown to be correct."""
    _got, _why, apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION), CONTRACT,
        {"TP-0000": STEPS}, conforming=CONFORMING)
    assert "Do not assume either trace is correct." in apart
    for banned in ("correct one", "conforming", "expected", "should be"):
        assert banned not in apart.lower().replace(
            "do not assume either trace is correct.", ""), (banned, apart)


def test_without_a_conforming_design_the_verdict_still_stands():
    """No pair to diff is a reason for no counterexample, not for no verdict."""
    got, why, apart = V.must_fail(
        _oracle(VACUOUS), _variants(BROKEN_ACTION, BROKEN_ACTION), CONTRACT,
        {"TP-0000": STEPS})
    assert got == V.CONVICTED, why
    assert apart == ""


# --- variants emit CHANGED METHODS, spliced onto the conforming model ----
#
# Whole-module emission cost 32% of a2-i2c's output tokens -- 948k over 185
# calls -- to re-type a median 283 of 289 unchanged code lines. The tokens are
# the smaller half: naming the methods bounds the blast radius, so a variant
# that rewrites five methods has to say so.

SPLICE_BASE = (
    "class Model:\n"
    "    OUTPUT_PORTS = ('q',)\n"
    "\n"
    "    def reset(self):\n"
    "        self.q = 0\n"
    "\n"
    "    def step(self, i):\n"
    "        self.q = i['d']\n"
    "        return {'q': self.q}\n"
)


def _variant_reply(**kw):
    return json.dumps({"reasoning": "r", "clause": "c", **kw})


def test_changed_methods_are_spliced_and_the_rest_is_untouched():
    out = variants.parse_and_splice(
        _variant_reply(methods={"step": "def step(self, i):\n    self.q = 1\n"
                                "    return {'q': self.q}"}), SPLICE_BASE)
    assert not out.splice_error
    assert "self.q = 1" in out.source
    assert "def reset(self):" in out.source        # untouched, and still there
    assert "OUTPUT_PORTS = ('q',)" in out.source
    compile(out.source, "<variant>", "exec")       # and it is a real module


def test_a_variant_may_ADD_a_method_it_needs():
    """A variant needing new state has nowhere to put a helper otherwise, and
    forcing it back to whole-module emission for that one case would give up
    the bound this exists to create."""
    out = variants.parse_and_splice(
        _variant_reply(methods={"_edge": "def _edge(self, v):\n    return v"}), SPLICE_BASE)
    assert not out.splice_error
    assert "def _edge(self, v):" in out.source
    from specflow.refmodel.slicer import methods_of
    assert methods_of(out.source) == ["reset", "step", "_edge"]


def test_a_splice_that_does_not_parse_becomes_a_REPAIRABLE_issue():
    """The objection to patches was that they can fail to apply. They can --
    and a failure names the method and the syntax error, which is the most
    actionable Issue this stage produces. `run_stage` already loops on Issues,
    so it costs a round, not a counterexample."""
    out = variants.parse_and_splice(
        _variant_reply(methods={"step": "def step(self, i):\n    return ("}), SPLICE_BASE)
    assert out.splice_error and "does not parse" in out.splice_error
    issues = variants.gate_one(
        out, req_uid="REQ-0001", kind="action", contract={"io": []},
        conforming_source=SPLICE_BASE, steps=[], observable=set())
    assert issues and issues[0].severity == "error"
    assert "could not be spliced" in issues[0].message
    assert "step" in issues[0].message          # it names WHICH method


def test_a_reply_with_neither_methods_nor_source_is_rejected():
    issues = variants.gate_one(
        variants.parse_and_splice(_variant_reply(), SPLICE_BASE),
        req_uid="REQ-0001", kind="action", contract={"io": []},
        conforming_source=SPLICE_BASE, steps=[], observable=set())
    assert issues and "no design here" in issues[0].message


def test_a_whole_module_reply_is_REFUSED_the_first_time():
    """Asked for in the prompt is not enforced.

    The instruction to send only changed methods reached the live prompt and
    gpt-5-mini emitted the whole module on 5 of 5 calls anyway, taking the
    escape clause every time. Same failure as `add_stimulus` asking an agent not
    to repeat itself, and the reason I8 became a tool refusal rather than prose.
    """
    whole = SPLICE_BASE.replace("self.q = i['d']", "self.q = 0")
    out = variants.parse_and_splice(_variant_reply(source=whole), SPLICE_BASE)
    assert out.source == whole and not out.splice_error   # parsing is fine
    issues = variants.gate_one(
        out, req_uid="REQ-0001", kind="action", contract={"io": []},
        conforming_source=SPLICE_BASE, steps=[], observable=set())
    assert issues and "not the whole module" in issues[0].message


def test_and_ACCEPTED_on_the_retry_so_the_escape_stays_reachable():
    """Refused once, with the reason. A variant that genuinely has to
    restructure the model is not blocked, only asked to mean it."""
    whole = SPLICE_BASE.replace("self.q = i['d']", "self.q = 0")
    out = variants.parse_and_splice(_variant_reply(source=whole), SPLICE_BASE)
    assert variants.gate_one(
        out, req_uid="REQ-0001", kind="action", contract={"io": []},
        conforming_source=SPLICE_BASE, steps=[], observable=set(),
        whole_module_ok=True) == []


def test_the_prompt_says_the_whole_module_will_be_refused():
    """The prose and the gate must agree, or the model is told one thing and
    scored on another. Asserted on fragments that do not cross a line wrap --
    a trap that has already cost this repo once."""
    assert "Sending the whole module instead of" in variants.SYSTEM
    assert "BE REJECTED" in variants.SYSTEM
