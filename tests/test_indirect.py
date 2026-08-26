"""Every unobservable requirement is asked whether it is observed INDIRECTLY.

`UNOBSERVABLE` claims no port shows the behaviour, and this pipeline measured
that claim wrong at scale: normalisation called 27 of 77 requirements
unobservable by reading each one's MECHANISM rather than its effect, and 10 of
the 27 already had working checks against real output ports.

Two independent indirections. `observed_via` makes a requirement CHECKABLE --
it is observed at a port its own text does not name. `activated_via` makes it
STAGEABLE -- the state its activation needs has to be reached. They fail
differently: no route to observe is a specification finding, no route to reach
is a testplan one, and a requirement can be perfectly observable and unreachable.
"""

from __future__ import annotations

from specflow.normalize import (
    Activation,
    NormalizedRequirement,
    NormalizeOutput,
    REACH_DEPTH,
    Reach,
    Route,
    gate_indirect,
    reaching,
    resolve_indirect,
)

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "sda_i", "dir": "input", "width": 1},
    {"name": "busy", "dir": "output", "width": 1},
    {"name": "al", "dir": "output", "width": 1},
]}

DISCRIMINATING = ("busy stays low for a glitch narrower than the filter depth "
                  "and does not rise")


def _blind(uid="REQ-0031"):
    return NormalizedRequirement(
        req_uid=uid, activation=Activation(text="a glitch on sda_i"),
        observable=[], unobservable_reason="the filter is internal",
        expectation="no START is detected")


def _seer(uid="REQ-0007"):
    return NormalizedRequirement(
        req_uid=uid, activation=Activation(text="a START is detected"),
        observable=["busy"], expectation="busy rises")


def _out(**kw):
    return NormalizeOutput(normalized=[NormalizedRequirement(**kw)])


# ------------------------------------------------------------- the gate


def test_a_route_naming_one_case_is_rejected():
    """THE VACUITY FAILURE, ONE STAGE EARLY, and harder to see because the route
    looks like progress. A check over "the port shows X" passes any design that
    ever shows X -- including one with none of this behaviour."""
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0007", when="after a glitch",
        shows="busy is low")])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0007", "REQ-0031"})
    assert issues and "HOLDS" in issues[0].message


def test_a_route_naming_both_cases_passes():
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0007", when="after a glitch",
        shows=DISCRIMINATING)])
    assert gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                         known={"REQ-0007", "REQ-0031"}) == []


def test_a_route_through_an_undeclared_port_is_rejected():
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="filter_cnt", through_req="REQ-0007", when="x",
        shows=DISCRIMINATING)])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0007", "REQ-0031"})
    assert any("not a declared output port" in i.message for i in issues)


def test_a_requirement_cannot_be_observed_through_itself():
    """That is the direct case, and the first pass already said there is none."""
    out = _out(req_uid="REQ-0031", observed_via=[Route(
        port="busy", through_req="REQ-0031", when="x", shows=DISCRIMINATING)])
    issues = gate_indirect(out, uid="REQ-0031", contract=CONTRACT,
                           known={"REQ-0031"})
    assert any("through itself" in i.message for i in issues)


def test_an_empty_answer_is_accepted_as_an_honest_no_route():
    """"Nothing observes this" is worth more than a route that does not
    discriminate."""
    assert gate_indirect(_out(req_uid="REQ-0031"), uid="REQ-0031",
                         contract=CONTRACT, known={"REQ-0031"}) == []


# ------------------------------------------------- the closure over hops


def _reachable(uid, via=()):
    return NormalizedRequirement(
        req_uid=uid, observable=["busy"],
        activated_via=[Reach(through_req=t,
                             activation=Activation(text=f"via {t}"))
                       for t in via])


def test_local_hops_are_followed_into_a_full_chain_deepest_first():
    """Normalisation emits ONE hop each; the walk is mechanical. Asking a model
    for the whole chain asks it to hold the state machine in its head, and one
    wrong link invalidates everything after it."""
    by = {r.req_uid: r for r in
          [_reachable("A", ["B"]), _reachable("B", ["C"]), _reachable("C")]}
    chain, why = reaching("A", by)
    assert [h.through_req for h in chain] == ["C", "B"], "drive order"
    assert why == ""


def test_a_cycle_is_a_specification_finding_not_a_hang():
    by = {r.req_uid: r for r in [_reachable("X", ["Y"]), _reachable("Y", ["X"])]}
    chain, why = reaching("X", by)
    assert chain == []
    assert "closes on itself" in why and "Y" in why and "X" in why


def test_a_chain_deeper_than_the_bound_is_reported_rather_than_followed():
    uids = [f"R{i}" for i in range(REACH_DEPTH + 3)]
    by = {u: _reachable(u, [n]) for u, n in zip(uids, uids[1:])}
    by[uids[-1]] = _reachable(uids[-1])
    chain, why = reaching(uids[0], by)
    assert chain == [] and "more likely a misreading" in why


def test_an_input_only_activation_needs_no_chain():
    by = {"A": _reachable("A")}
    assert reaching("A", by) == ([], "")


# ------------------------------------------------------------- the pass


class _Port:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def complete(self, prompt, **kw):
        self.prompts.append(prompt)
        return self.reply


def _resolve(reply, shapes):
    port = _Port(reply)
    merged, results = resolve_indirect(
        normalized=shapes,
        requirements=[{"uid": s.req_uid, "text": "t"} for s in shapes],
        contract_json="{}", contract=CONTRACT, port=port, fanout=False)
    return merged, results, port


ROUTED = ('{"normalized": [{"req_uid": "REQ-0031", "observed_via": [{"port": '
          '"busy", "through_req": "REQ-0007", "when": "after a glitch", '
          f'"shows": "{DISCRIMINATING}"}}]}}]}}')


def test_a_resolved_requirement_becomes_observable_at_the_route_s_port():
    """`observable` holds the ports it is decidable at BY ANY ROUTE, so every
    downstream stage keeps reading one field."""
    merged, _, _ = _resolve(ROUTED, [_blind(), _seer()])
    got = {n.req_uid: n for n in merged}["REQ-0031"]
    assert got.observable == ["busy"]
    assert got.unobservable_reason == "", "no longer true, so it goes"
    assert got.indirect and got.observed_via[0].through_req == "REQ-0007"


def test_the_other_requirements_are_the_evidence():
    _, _, port = _resolve(ROUTED, [_blind(), _seer()])
    assert "REQ-0007" in port.prompts[0]
    assert "busy" in port.prompts[0]


def test_a_directly_observable_requirement_is_never_asked():
    _, results, port = _resolve(ROUTED, [_seer()])
    assert port.prompts == [] and results == []


def test_an_honest_no_route_leaves_the_requirement_as_it_was():
    """It stays UNOBSERVABLE here; the oracle stage is what turns having been
    ASKED into ABANDONED."""
    merged, _, _ = _resolve('{"normalized": [{"req_uid": "REQ-0031"}]}',
                            [_blind(), _seer()])
    got = {n.req_uid: n for n in merged}["REQ-0031"]
    assert got.unobservable and got.unobservable_reason
    assert got.observed_via == []


# --------------------------------------------- the route reaches every stage
#
# A route computed at normalisation and read by nothing is a field, not a fix.
# These pin that it arrives everywhere a requirement is planned, covered,
# checked or staged.


ROUTE = {"port": "busy", "through_req": "REQ-0007",
         "when": "after a glitch narrower than the filter depth",
         "shows": DISCRIMINATING}
SHAPE = {"activation": {"text": "a glitch on sda_i", "inputs": {"sda_i": 0}},
         "observable": ["busy"], "expectation": "no START is detected",
         "observed_via": [ROUTE], "activated_via": []}


def test_s2_is_told_to_plan_both_sides_of_the_difference():
    """The observation is a DIFFERENCE at a port this requirement does not own,
    so one scenario there is satisfied by the port's ordinary behaviour -- an
    element covering only the holding case is discharged by a design with none
    of this requirement's behaviour."""
    from specflow.s2_testplan import build_prompt_one

    prompt = build_prompt_one({"uid": "REQ-0031"}, "{}", normalized=SHAPE)
    assert "PLAN BOTH CASES" in prompt
    assert "REQ-0007" in prompt and DISCRIMINATING in prompt


def test_s2_says_nothing_about_indirection_for_a_direct_requirement():
    from specflow.s2_testplan import build_prompt_one

    direct = {"activation": {"text": "x"}, "observable": ["busy"]}
    assert "PLAN BOTH CASES" not in build_prompt_one(
        {"uid": "REQ-0007"}, "{}", normalized=direct)


def test_s3_is_given_the_route_its_bin_condition_needs():
    """A requirement whose own text names no port can otherwise only produce a
    bin over something internal -- coverable and unverifiable."""
    from specflow.s3_coverage import build_prompt_one

    prompt = build_prompt_one({"uid": "TP-0001", "covers": ["REQ-0031@1"]},
                              "{}", normalized=SHAPE)
    assert "OBSERVED AT ANOTHER REQUIREMENT'S PORT" in prompt
    assert "qualified by this" in prompt


def test_s3_rejects_a_check_that_is_the_other_requirement_s_check():
    """It passes and fails with `through_req`, so this element is covered on
    paper and verified by nothing."""
    from specflow.s3_coverage import CoverageOutput, indirect_issues

    out = CoverageOutput(checks=[{"uid": "CHK-0000", "covers": ["TP-0001@1"],
                                  "signals": ["busy"],
                                  "expr": "busy matches the reference model"}])
    issues = indirect_issues({"uid": "TP-0001"}, out, SHAPE)
    assert issues and "verified by nothing" in issues[0].message


def test_s3_accepts_a_check_qualified_by_this_requirement_s_activation():
    from specflow.s3_coverage import CoverageOutput, indirect_issues

    out = CoverageOutput(checks=[{
        "uid": "CHK-0000", "covers": ["TP-0001@1"], "signals": ["busy"],
        "expr": "after a glitch on sda_i, busy matches the reference model"}])
    assert indirect_issues({"uid": "TP-0001"}, out, SHAPE) == []


def test_s3_says_nothing_about_a_direct_element():
    from specflow.s3_coverage import CoverageOutput, indirect_issues

    out = CoverageOutput(checks=[{"uid": "CHK-0000", "covers": ["TP-0001@1"],
                                  "signals": ["busy"], "expr": "busy rises"}])
    assert indirect_issues({"uid": "TP-0001"}, out, {"observable": ["busy"]}) == []


def test_the_oracle_author_is_told_the_port_belongs_to_another_requirement():
    from specflow.refmodel.oracle_gen import build_prompt

    prompt = build_prompt(requirement={"uid": "REQ-0031"}, contract_json="{}",
                          contract={}, normalized=SHAPE)
    assert "THE PORT BELONGS TO ANOTHER REQUIREMENT" in prompt
    assert "Checking only one side of `shows`" in prompt


def test_the_stimulus_hint_carries_the_reaching_sequence_not_the_state_name():
    """"Get the FSM into START_B" is not a step list; "issue START as REQ-0012
    prescribes, then hold" is."""
    from specflow.oracles_stage import _hint

    stateful = dict(SHAPE, activation={"text": "while in START_B"},
                    activated_via=[{"through_req": "REQ-0012",
                                    "activation": {"text": "a START is issued",
                                                   "inputs": {"cmd": 1}}}])
    hint = _hint({"uid": "REQ-0031", "text": "t"}, stateful, None, 0)
    assert "STATE, not a set of values" in hint
    assert "REQ-0012" in hint and "cmd=1" in hint


def test_the_stimulus_hint_names_the_port_the_scenario_must_move():
    from specflow.oracles_stage import _hint

    hint = _hint({"uid": "REQ-0031", "text": "t"}, SHAPE, None, 0)
    assert "another requirement's port" in hint and "busy" in hint


def test_staging_runs_by_default():
    """z-i2c ended with 33 unexercised oracles and `stimulus_added: 0`: a third
    of the set decided nothing, and off-by-default meant the pipeline's answer
    to "nothing reaches this requirement" was to report it."""
    import inspect

    from specflow.oracles_stage import run_oracle_stage

    assert inspect.signature(run_oracle_stage).parameters[
        "want_staging"].default is True


def test_the_first_pass_is_given_a_third_answer_it_can_actually_give():
    """It sees ONE requirement, so it cannot name a route -- it does not know
    which requirement owns which port. What it CAN do is distinguish "I cannot
    name a port for this" from "nothing at the interface distinguishes this at
    all", and the second pass reads that difference.

    Without the third answer the first pass has only two moves, and one of them
    is reaching for the nearest port -- the mistake the discipline exists to
    stop.
    """
    from specflow.normalize import SYSTEM

    assert "THERE IS A THIRD ANSWER" in SYSTEM
    assert "you cannot see the other requirements" in SYSTEM.lower()
    assert "Do NOT reach for a port on the" in SYSTEM


def test_the_second_pass_is_shown_what_the_first_one_claimed():
    from specflow.normalize import NormalizedRequirement, build_indirect_prompt

    shape = NormalizedRequirement(
        req_uid="REQ-0031", observable=[],
        unobservable_reason="not visible on any port this requirement names")
    prompt = build_indirect_prompt({"uid": "REQ-0031"}, shape, [shape],
                                   "{}", CONTRACT)
    assert "not visible on any port this requirement names" in prompt


def test_the_indirect_prompt_shows_the_shape_it_will_be_parsed_for():
    """CAUGHT LIVE, AFTER 63 WASTED CALLS.

    The prompt described the two fields well enough that the model answered
    correctly -- it named a port, a `through_req`, a `when` and both sides of
    `shows` -- IN PROSE. `parse_response` wants JSON, so every one of those
    answers parsed to nothing, the gate said "no answer returned", and the
    repair loop spent its whole budget re-asking a question that was already
    being answered: 18 requirements, 63 calls, r0=18 r1=18 r2=17 r3=14.

    The first-pass `SYSTEM` ends with "Reply with ONE JSON object and nothing
    else" and an example. This one did not, because it was written as a
    description of a new question rather than as a sibling of the prompt it
    shares a parser with.

    Both halves are pinned: the shape, and the SHAPE OF "NO" -- an empty answer
    is the honest outcome here and a model shown only the populated example
    tends to populate it.
    """
    from specflow.normalize import INDIRECT_SYSTEM

    assert "Reply with ONE JSON object" in INDIRECT_SYSTEM
    assert '"observed_via"' in INDIRECT_SYSTEM
    assert '"activated_via"' in INDIRECT_SYSTEM
    assert '"observed_via": []' in INDIRECT_SYSTEM, "the empty answer too"


def test_every_prompt_parsed_as_json_says_so():
    """The general form of the same defect, across the stages that share the
    discipline. A system prompt is the only place the output contract is
    stated, and a parser is silent about what it wanted."""
    from specflow import normalize, s2_testplan, s3_coverage
    from specflow.refmodel import oracle_gen

    for name, text in (
        ("normalize.SYSTEM", normalize.SYSTEM),
        ("normalize.INDIRECT_SYSTEM", normalize.INDIRECT_SYSTEM),
        ("s2.SYSTEM", s2_testplan.SYSTEM),
        ("s3.SYSTEM", s3_coverage.SYSTEM),
        ("oracle_gen.SYSTEM", oracle_gen.SYSTEM),
    ):
        assert "JSON" in text, f"{name} never asks for JSON"
        assert "{" in text and "}" in text, f"{name} never shows the shape"
