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

import json
from pathlib import Path

from specflow.normalize import (
    Activation,
    antecedent_port,
    discriminates_on,
    indirect_review,
    write_artifacts,
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


def _settled(uid="REQ-0012"):
    """A known sibling that needs nothing: observable, and drivable."""
    return NormalizedRequirement(
        req_uid=uid, activation=Activation(text="cmd is START", inputs={"cmd": 1}),
        observable=["cmd_ack"], expectation="cmd_ack pulses")


def test_a_requirement_that_needs_NEITHER_is_never_asked():
    """Observable at its own port AND drivable -- nothing to resolve."""
    settled = _seer().model_copy(update={
        "activation": Activation(text="cmd is WRITE", inputs={"cmd": 1})})
    _, results, port = _resolve(ROUTED, [settled])
    assert port.prompts == [] and results == []


def test_an_UNCONDITIONAL_activation_is_not_asked_how_to_reach_it():
    """`input_only` was carrying this and getting it wrong.

    It is `bool(inputs)`, so "at all times" with no inputs read as
    state-dependent. On a2-i2c that mislabelled 8 of 11 requirements -- and
    every one of them would have cost a model call asking how to reach
    "always".
    """
    always = _seer().model_copy(update={"activation": Activation(text="at all times")})
    _, results, port = _resolve(ROUTED, [always])
    assert port.prompts == [] and results == []


def test_an_OBSERVABLE_but_UNREACHABLE_requirement_is_asked_the_other_question():
    """The cell the pass could never fill: entry was gated on observability.

    Live proof it was structural rather than a property of the design -- on
    a2-i2c, `activated_via` WITHOUT `observed_via` came back zero of 105.
    """
    stateful = _seer().model_copy(update={
        "activation": Activation(text="the FSM is in START_B")})
    reply = ('{"normalized": [{"req_uid": "REQ-0007", "activated_via": '
             '[{"through_req": "REQ-0012", "activation": {"text": "issue START",'
             ' "inputs": {"cmd": 1}}}]}]}')
    merged, results, port = _resolve(reply, [stateful, _settled()])
    assert len(port.prompts) == 1
    assert "ACTIVATION ONLY" in port.prompts[0]
    got = next(n for n in merged if n.req_uid == "REQ-0007")
    assert [h.through_req for h in got.activated_via] == ["REQ-0012"]
    # And its own observable is untouched -- it never needed a route.
    assert got.observable == ["busy"] and got.observed_via == []


def test_a_route_returned_for_a_requirement_that_did_NOT_ask_is_ignored():
    """`observable` is what every downstream stage reads.

    A requirement asked only the activation question is already decidable at a
    port of its own. Overwriting that with a route it was told not to look for
    is strictly worse than ignoring the route.
    """
    stateful = _seer().model_copy(update={
        "activation": Activation(text="the FSM is in START_B")})
    reply = ('{"normalized": [{"req_uid": "REQ-0007", "observed_via": [{"port": '
             '"cmd_ack", "through_req": "REQ-0009", "when": "later", '
             f'"shows": "{DISCRIMINATING}"}}]}}]}}')
    merged, _, _ = _resolve(reply, [stateful])
    got = next(n for n in merged if n.req_uid == "REQ-0007")
    assert got.observable == ["busy"] and got.observed_via == []


def test_a_reaching_chain_survives_an_answer_with_no_observation_route():
    """`if not answer.observed_via: continue` threw the whole answer away.

    A blind requirement whose route was not found but whose reaching chain WAS
    lost the chain too -- the one artefact the stimulus author needs, discarded
    with a question it had not been asked.
    """
    reply = ('{"normalized": [{"req_uid": "REQ-0031", "observed_via": [], '
             '"activated_via": [{"through_req": "REQ-0012", "activation": '
             '{"text": "issue START"}}]}]}')
    merged, _, _ = _resolve(reply, [_blind(), _settled()])
    got = next(n for n in merged if n.req_uid == "REQ-0031")
    assert [h.through_req for h in got.activated_via] == ["REQ-0012"]
    assert got.unobservable          # still blind: no route was found
    assert got.unobservable_reason   # and its reason is left standing


def test_the_ask_note_is_in_the_ITEM_block_not_the_cached_prefix():
    """Forking the system text per question would split a 64 KB head three ways.

    Measured: that head is 97.3% of the prompt, so the note has to ride in the
    item block or the stage pays for the sentence three times over.
    """
    from specflow.normalize import indirect_prefix
    for note in ("OBSERVATION ONLY", "ACTIVATION ONLY", "THE QUESTION FOR THIS"):
        assert note not in indirect_prefix("{}", CONTRACT, [_seer()])


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


def test_the_whole_requirement_set_is_in_the_CACHED_prefix():
    """MEASURED AT 7x. The set is the largest thing this stage sends and it is
    the same for every call, so it is the largest cacheable thing it has. It sat
    in the item block because each call filtered out its own entry -- making a
    ~48 KB block differ per call for the sake of one row.

    Live on a2-i2c before the fix: `normalize_indirect` ran 31 calls, 549 KB of
    input, 11.9% cached, common prefix 16,262 of 64,423 characters. `normalize`
    beside it ran 84.7%.
    """
    from specflow.fanout import PREFIX_SENTINEL
    from specflow.normalize import build_indirect_prompt

    others = [_seer("REQ-0007"), _blind("REQ-0031"), _blind("REQ-0044")]
    a = build_indirect_prompt({"uid": "REQ-0031"}, _blind("REQ-0031"), others,
                              "{}", CONTRACT)
    b = build_indirect_prompt({"uid": "REQ-0044"}, _blind("REQ-0044"), others,
                              "{}", CONTRACT)
    head_a = a[: a.index(PREFIX_SENTINEL)]
    assert head_a == b[: b.index(PREFIX_SENTINEL)], "the head must be identical"
    assert "REQ-0007" in head_a, "the set is in the cached head, not the item"
    # The gap between the two is what a provider can cache. Before the fix it
    # was 25% of the prompt; the whole set being shared is what moves it.
    common = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    assert common > len(a) * 0.5, f"only {common / len(a):.0%} shared"


def test_a_requirement_sees_its_own_entry_and_is_told_to_ignore_it():
    """A row a model is told to skip costs a few tokens once; a prefix that
    differs per call costs the whole prefix every time."""
    from specflow.normalize import build_indirect_prompt

    mine = _blind("REQ-0031")
    prompt = build_indirect_prompt({"uid": "REQ-0031"}, mine, [mine, _seer()],
                                   "{}", CONTRACT)
    assert prompt.count("REQ-0031") >= 2, "its own entry stays in the set"
    assert "Ignore that entry" in prompt


# --- 9.4: what we computed ABOUT the routes ------------------------------
#
# Reported, never gated. a2-i2c resolved 28 of 105 requirements and left zero
# unobservable, and a 100% resolution rate is the shape of a model reaching for
# an answer -- so the routes were read rather than counted, and these are the
# three numbers that reading produced.


def _norm(uid: str, *, act: str) -> NormalizedRequirement:
    return NormalizedRequirement(req_uid=uid, activation=Activation(text=act))


def test_a_route_discriminating_by_cycle_count_is_marked_timing():
    assert discriminates_on(
        Route(shows="cmd_ack pulses one clock cycle after completion")
    ) == "timing"
    assert discriminates_on(
        Route(shows="busy stays low for a narrow glitch and rises for a wide one")
    ) == "value"


def test_a_route_whose_port_its_own_activation_pins_is_flagged():
    """REQ-0005's shape: the route observes the ANTECEDENT, so it cannot fail."""
    req = _norm("REQ-0005", act="an output-enable is released high (scl_oen = 1)")
    circular = Route(port="scl_oen", through_req="REQ-0009",
                     shows="when this holds scl_oen == 1; when it does not, 0")
    assert antecedent_port(req, circular)


def test_a_port_named_only_by_a_SIBLING_is_not_flagged():
    req = _norm("REQ-0031", act="a glitch on sda_i while scl_i is high")
    assert not antecedent_port(req, Route(port="busy", through_req="REQ-0007",
                                          shows="busy stays low, then rises"))


def test_the_flag_is_a_SHAPE_and_the_review_does_not_convict_on_it():
    """REQ-0035 names the port in a PRECONDITION and discriminates on DYNAMICS.

    A gate here would reject that to catch REQ-0005, which is the trade this
    codebase refuses elsewhere. So the route stays, flagged, and vacuity is left
    to convict the one that cannot fail.
    """
    req = _norm("REQ-0035", act="the controller releases SCL (scl_oen is released)")
    dynamics = Route(port="scl_oen", through_req="REQ-0036",
                     shows="scl_oen remains held steady while slave_wait is "
                           "active; otherwise it follows normal FSM timing")
    review = indirect_review([req.model_copy(update={"observed_via": [dynamics],
                                                     "observable": ["scl_oen"]})])
    assert review["antecedent_port_routes"] == [
        {"req_uid": "REQ-0035", "port": "scl_oen"}]
    assert review["resolved"] == 1          # flagged, and still resolved


def test_concentration_is_reported_because_those_requirements_fail_TOGETHER():
    """Eleven requirements through one port is one finding, not eleven."""
    reqs = [
        _norm(f"REQ-000{i}", act="something").model_copy(update={
            "observable": ["cmd_ack"],
            "observed_via": [Route(port="cmd_ack", through_req="REQ-0036",
                                   shows="cmd_ack pulses one cycle later")],
        })
        for i in range(3)
    ]
    review = indirect_review(reqs)
    assert review["port_concentration"] == {"cmd_ack": 3}
    assert review["through_req_concentration"] == {"REQ-0036": 3}
    assert review["requirements_resting_wholly_on_timing"] == 3


def test_a_requirement_whose_EVERY_alternative_is_an_antecedent_has_none_left():
    """One bad alternative among three is survivable; all of them is not."""
    req = _norm("REQ-0005", act="an output-enable (scl_oen or sda_oen) is released")
    both = req.model_copy(update={
        "observable": ["scl_oen", "sda_oen"],
        "observed_via": [
            Route(port="scl_oen", through_req="REQ-0009", shows="scl_oen == 1"),
            Route(port="sda_oen", through_req="REQ-0009", shows="sda_oen == 1"),
        ],
    })
    survivor = _norm("REQ-0102", act="either output-enable is released").model_copy(
        update={"observable": ["cmd_ack", "sda_oen"], "observed_via": [
            Route(port="sda_oen", through_req="REQ-0009", shows="sda_oen == 1"),
            Route(port="cmd_ack", through_req="REQ-0036",
                  shows="cmd_ack pulses one cycle after completion"),
        ]})
    review = indirect_review([both, survivor])
    assert review["requirements_with_no_non_antecedent_route"] == ["REQ-0005"]


def test_the_review_is_absent_rather_than_empty_when_nothing_resolved():
    assert indirect_review([_norm("REQ-0001", act="x")]) == {}


def test_the_review_is_on_the_face_of_the_artifact(tmp_path):
    req = _norm("REQ-0031", act="a glitch on sda_i").model_copy(update={
        "observable": ["busy"],
        "observed_via": [Route(port="busy", through_req="REQ-0007",
                               shows="busy stays low then rises one cycle later")],
    })
    path = write_artifacts(tmp_path, [req], [])
    written = json.loads(path.read_text())
    assert written["indirect_review"]["resolved"] == 1
    assert written["indirect_review"]["discriminates_on"] == {"timing": 1, "value": 0}
    # And it says it is our reading, not the resolution pass's claim.
    assert "no gate" in written["indirect_review"]["note"]


def test_no_gate_reads_the_review():
    """Reported, not gated -- the whole point of it."""
    src = Path("specflow/normalize.py").read_text()
    gate = src[src.index("def gate_indirect("):src.index("def _reach_edges(")
               if "def _reach_edges(" in src else src.index("REACH_DEPTH")]
    for name in ("indirect_review", "discriminates_on", "antecedent_port"):
        assert name not in gate
