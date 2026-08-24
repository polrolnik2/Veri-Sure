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
