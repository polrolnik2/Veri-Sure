"""S1b normalization: the gate that separates a typo from a spec defect."""

from __future__ import annotations

from specflow.normalize import (
    Activation,
    NormalizedRequirement,
    NormalizeOutput,
    gate_one,
    parse_response,
    shared_prefix,
    unobservable,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "cmd_ack", "dir": "output", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
    ]
}
REQ = {"uid": "REQ-0000", "text": "on START, cmd_ack pulses for one clock"}


def _out(**kw) -> NormalizeOutput:
    kw.setdefault("activation", Activation(text="a START is issued"))
    kw.setdefault("expectation", "cmd_ack pulses high for exactly one clock")
    return NormalizeOutput(normalized=[NormalizedRequirement(**kw)])


def test_a_well_formed_normalization_passes():
    assert gate_one(REQ, _out(observable=["cmd_ack", "busy"]), CONTRACT) == []


def test_naming_a_non_port_is_an_error_not_an_unobservable_finding():
    """The distinction the whole stage rests on. A wrong name buys a repair
    round; a spec defect does not, and conflating them means either every typo
    is reported as a spec defect or every spec defect is retried until the
    budget runs out."""
    issues = gate_one(REQ, _out(observable=["div_cnt"]), CONTRACT)
    assert [i.severity for i in issues] == ["error"]
    assert "not a declared output port" in issues[0].message


def test_an_input_port_is_not_an_observable():
    """An input is what a test drives, never what it observes."""
    issues = gate_one(REQ, _out(observable=["ena"]), CONTRACT)
    assert issues and "not a declared output port" in issues[0].message


def test_no_observable_with_a_reason_is_accepted():
    """UNOBSERVABLE is a conclusion, not a failure. Rejecting it would force
    the model to name a port it knows is wrong, which produces an oracle that
    fails correct designs."""
    out = _out(observable=[], unobservable_reason="div_cnt is an internal counter")
    assert gate_one(REQ, out, CONTRACT) == []
    norm = out.normalized[0].model_copy(update={"req_uid": "REQ-0000"})
    assert norm.unobservable
    assert unobservable([norm]) == {"REQ-0000": "div_cnt is an internal counter"}


def test_no_observable_and_no_reason_is_an_error():
    """Declining to commit is not the same as claiming there is none."""
    issues = gate_one(REQ, _out(observable=[]), CONTRACT)
    assert issues and "unobservable_reason" in issues[0].message


def test_claiming_both_an_observable_and_a_reason_is_a_contradiction():
    out = _out(observable=["busy"], unobservable_reason="also internal, somehow")
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and "contradict" in issues[0].message


def test_activation_inputs_are_checked_against_the_contract():
    ok = _out(observable=["busy"], activation=Activation(text="x", inputs={"cmd": 1}))
    assert gate_one(REQ, ok, CONTRACT) == []

    unknown = _out(observable=["busy"],
                   activation=Activation(text="x", inputs={"nope": 1}))
    assert any("not a declared input" in i.message
               for i in gate_one(REQ, unknown, CONTRACT))

    too_wide = _out(observable=["busy"],
                    activation=Activation(text="x", inputs={"ena": 2}))
    assert any("does not fit" in i.message
               for i in gate_one(REQ, too_wide, CONTRACT))


def test_reset_may_appear_in_an_activation_even_though_it_is_not_drivable():
    """"While reset is asserted" is a real precondition, and the runtime has a
    reset step that reaches it. `_drivable` excludes reset from STIMULUS; that
    is a statement about who owns the pin, not about what a requirement may be
    conditioned on."""
    out = _out(observable=["busy"],
               activation=Activation(text="during reset", inputs={"nReset": 0}))
    assert gate_one(REQ, out, CONTRACT) == []


def test_an_input_only_activation_is_distinguishable_from_a_stateful_one():
    """Not a quality judgement -- it decides WHERE the condition can be checked.
    An input-only activation is readable off a stimulus step list with no model
    at all; a stateful one needs something to run."""
    assert Activation(text="cmd is START", inputs={"cmd": 1}).input_only
    assert not Activation(text="while the FSM is idle").input_only


def test_two_normalizations_for_one_requirement_is_rejected():
    out = NormalizeOutput(normalized=[
        NormalizedRequirement(activation=Activation(text="a"), observable=["busy"],
                              expectation="x"),
        NormalizedRequirement(activation=Activation(text="b"), observable=["busy"],
                              expectation="y"),
    ])
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and "two requirements" in issues[0].message


def test_a_parse_failure_is_reported_as_one_not_as_an_empty_answer():
    out = parse_response("this is not json")
    assert out.reasoning.startswith("Parse Error: ")
    issues = gate_one(REQ, out, CONTRACT)
    assert issues and issues[0].path.endswith(".response")


def test_the_prompt_shows_the_port_lists_the_gate_validates_against():
    """`suite_shared_prefix` learned this the hard way: a gate validating against
    a list the model was never shown cost 12 repair rounds in 41 testpoints."""
    prefix = shared_prefix("{}", CONTRACT)
    assert "cmd_ack" in prefix and "busy" in prefix
    assert "ONLY names `observable` may contain" in prefix
    # Inputs listed too, because `activation.inputs` is gated the same way.
    assert "activation.inputs" in prefix


def test_the_prompt_separates_the_mechanism_from_the_effect():
    """The measured failure mode, and the more expensive of the two mistakes.

    Most requirements describe internal machinery on the way to a result: "the
    filter suppresses a glitch so no START is detected", "the FSM leaves idle
    and runs the command". Reading the MECHANISM and calling the requirement
    unobservable writes off behaviour that is perfectly checkable.

    Measured on f-i2c: 27 of 77 requirements came back UNOBSERVABLE, and 10 of
    those had oracles that had already passed screening -- well-formedness alone
    requires naming a declared port, so something observable was plainly there.
    After this rule, 7 of those 10 flip to observable while 4 of 4 genuinely
    internal controls (div_cnt, clk_en, scl_sync, cnt) stay unobservable.
    """
    prefix = " ".join(shared_prefix("{}", CONTRACT).split())
    assert "ASK ABOUT THE EFFECT, NOT THE MECHANISM" in prefix
    # The completable-sentence test is what makes the rule applicable rather
    # than a sentiment.
    assert "no boundary effect AT ALL" in prefix
    # Both mistakes must stay named. Dropping either half is how this swings
    # back the other way into reaching for the nearest output port.
    assert "produces a check that fails correct designs" in prefix
    assert "writes off behaviour that is perfectly checkable" in prefix


# ------------------------------------------- activation inputs are NECESSARY


def test_the_prompt_asks_for_necessary_not_sufficient_inputs():
    """The bar `check_static` actually needs, pinned against reverting.

    The clause this replaces told the model to leave `inputs` empty whenever the
    precondition read as internal state. The model followed it, and 57 of 77
    requirements came back with no input activation -- 32 of them naming a
    command or reset in their own activation text, several with the literal
    encoding (`"A START (cmd = 0001) ... is issued"` normalized to `{}`).

    That capped `_attach` at 26% of the suite, which is why a run that added 48
    testpoints moved `NOT_EXERCISED` by zero.

    Necessary is the right bar because `inputs` gates ATTACHMENT, not truth: the
    oracle still runs afterwards and reports the scenario unexercised if it did
    not occur. Measured on the requirements that already had inputs, a static
    match predicts the oracle really fires with precision 0.81, against 0.40 for
    attaching everything -- and 0.40 is the regime the f-i2c result (one true
    finding for 27 false) came out of.
    """
    from specflow.normalize import SYSTEM

    assert "NECESSARY condition, not a sufficient one" in SYSTEM
    assert "must these values be driven" in SYSTEM
    # The state-phrased cases now get inputs rather than being excluded.
    assert "during the READ data-bit phase" in SYSTEM
    # And the genuine exclusion survives: nothing a test drives reaches it.
    assert "after arbitration has been lost" in SYSTEM

    stale = ('"while the state machine is idle" and "after arbitration has '
             'been lost"\ncannot')
    assert stale not in SYSTEM, (
        "the sufficiency reading is back; it empties `inputs` for any "
        "precondition phrased as internal state")


def test_reset_stays_a_legitimate_activation_input():
    """Unchanged by the rewrite, and easy to lose in it.

    Matched across collapsed whitespace: the rewrite reflowed the paragraph and
    put a newline inside "Reset ports", so the obvious assertion failed on text
    that was present and correct. That trap has cost this repo before.
    """
    import re

    from specflow.normalize import SYSTEM

    flat = re.sub(r"\s+", " ", SYSTEM)
    assert "Reset ports may appear in `inputs`" in flat
