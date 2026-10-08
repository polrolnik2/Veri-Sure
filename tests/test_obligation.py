"""The cover-point obligation: what it can decide, and what it refuses to."""

from __future__ import annotations

from specflow.normalize import Activation, NormalizedRequirement
from specflow.obligation import (
    FIRED,
    NOT_FIRED,
    UNKNOWN,
    Obligation,
    by_requirement,
    check_replay,
    check_static,
    obligations,
    report,
    worst,
)


def _rows(*states):
    return [{"edge": i, "inputs": {}, "outputs": dict(s)}
            for i, s in enumerate(states)]


def test_an_input_only_obligation_is_decided_from_the_steps_with_no_model():
    """The half that needs nothing to run. `cmd=8` either appears in the step
    list or it does not."""
    ob = Obligation("REQ-0000", "a WRITE is issued", {"cmd": 8, "ena": 1})
    hit = check_static(ob, [{"cmd": 0, "ena": 1}, {"cmd": 8, "ena": 1}])
    assert hit.status == FIRED

    miss = check_static(ob, [{"cmd": 0, "ena": 1}, {"cmd": 4, "ena": 1}])
    assert miss.status == NOT_FIRED
    # The detail names what was driven instead -- this is the 6-case
    # wrong-command bucket on f-i2c, which `gate_suite` passes as legal.
    assert "cmd=8" in miss.detail and "4" in miss.detail


def test_a_state_dependent_obligation_cannot_be_decided_statically():
    """Returns None rather than guessing, so a caller can tell "not staged"
    from "not answerable here"."""
    ob = Obligation("REQ-0001", "while the FSM is idle", {}, ("busy",))
    assert check_static(ob, [{"cmd": 0}]) is None


def test_a_reset_precondition_is_satisfied_by_a_reset_step_not_a_driven_value():
    """Reset is not drivable -- the runtime sequences it on both sides at once
    (`testcase_agent.py:440-449`) -- so a driven-values scan would report
    "never" for a testpoint that does assert reset."""
    ob = Obligation("REQ-0002", "during reset", {"nReset": 0})
    resets = frozenset({"nReset"})
    with_step = check_static(ob, [{"reset": True}, {"cmd": 0}], reset_ports=resets)
    assert with_step.status == FIRED
    without = check_static(ob, [{"cmd": 0}], reset_ports=resets)
    assert without.status == NOT_FIRED and "no reset step" in without.detail


def test_the_replay_leg_refutes_but_never_confirms():
    """Movement on the observable ports is NECESSARY for the scenario, not
    sufficient. Reporting it as sufficient would let a testpoint that merely
    wiggles an output count as having staged a specific case."""
    ob = Obligation("REQ-0003", "after arbitration is lost", {}, ("al",))

    inert = check_replay(ob, _rows({"al": 0}, {"al": 0}, {"al": 0}))
    assert inert.status == NOT_FIRED
    assert "never occurs" in inert.detail

    moving = check_replay(ob, _rows({"al": 0}, {"al": 1}))
    assert moving.status == UNKNOWN
    assert "cannot be confirmed" in moving.detail


def test_movement_on_a_port_the_requirement_is_not_about_does_not_count():
    """The projection rule `trust._project` already applies one level down: a
    requirement about `al` is not exercised because `busy` moved."""
    ob = Obligation("REQ-0004", "arbitration lost", {}, ("al",))
    rows = _rows({"al": 0, "busy": 0}, {"al": 0, "busy": 1})
    assert check_replay(ob, rows).status == NOT_FIRED


def test_worst_lets_one_firing_testpoint_settle_it():
    """A requirement staged by one of its testpoints is staged, whatever the
    others could not do -- and UNKNOWN beats NOT_FIRED, because a testpoint that
    might have staged it is not evidence that nothing did."""
    assert worst([]) == UNKNOWN
    assert worst([_c(NOT_FIRED), _c(FIRED)]) == FIRED
    assert worst([_c(NOT_FIRED), _c(UNKNOWN)]) == UNKNOWN
    assert worst([_c(NOT_FIRED), _c(NOT_FIRED)]) == NOT_FIRED


def _c(status):
    from specflow.obligation import Check
    return Check("REQ-0000", "TP-0000", status)


def test_an_unobservable_requirement_gets_no_obligation():
    """There is nothing to stage. Asking whether the stimulus staged an internal
    counter would report a stimulus defect for a specification one."""
    norm = [
        NormalizedRequirement(req_uid="REQ-0000", observable=["busy"],
                              activation=Activation(text="x"), expectation="y"),
        NormalizedRequirement(req_uid="REQ-0001", observable=[],
                              unobservable_reason="div_cnt is internal",
                              activation=Activation(text="x"), expectation="y"),
    ]
    assert [o.req_uid for o in obligations(norm, contract=_ENC)] == ["REQ-0000"]


def test_attachment_comes_from_the_testplan_not_from_an_oracle():
    """`covers` was written by S2 before any oracle existed, which is what makes
    a disagreement between this check and the oracle informative rather than
    tautological."""
    tp = [{"uid": "TP-0000", "covers": ["REQ-0000@1"]},
          {"uid": "TP-0001", "covers": ["REQ-0000@2", "REQ-0001@1"]}]
    assert by_requirement(tp) == {"REQ-0000": ["TP-0000", "TP-0001"],
                                  "REQ-0001": ["TP-0001"]}


def test_report_without_replays_decides_only_the_input_only_obligations():
    """The correct answer for a caller with no model in hand -- not a soft
    NOT_FIRED for everything it could not check."""
    obs = [Obligation("REQ-0000", "a WRITE", {"cmd": 8}),
           Obligation("REQ-0001", "while idle", {}, ("busy",))]
    tp = [{"uid": "TP-0000", "covers": ["REQ-0000@1"]},
          {"uid": "TP-0001", "covers": ["REQ-0001@1"]}]
    out = report(obligations_=obs, testplan=tp,
                 stimulus_by_tp={"TP-0000": [{"cmd": 8}], "TP-0001": [{"cmd": 0}]})
    assert out["by_requirement"] == {"REQ-0000": FIRED, "REQ-0001": UNKNOWN}
    assert out["decidable"] == 1 and out["total"] == 2


def test_report_counts_bound_what_the_gate_can_ever_say():
    """A run where most activations are prose is a run where most of the answer
    is UNKNOWN -- a finding about normalization, not about the stimulus."""
    obs = [Obligation(f"REQ-{i:04d}", "prose", {}, ("busy",)) for i in range(3)]
    out = report(obligations_=obs, testplan=[], stimulus_by_tp={})
    assert out["decidable"] == 0
    assert out["counts"][UNKNOWN] == 3


# --- a reset port at its IDLE value needs no reset step --------------------


def test_a_reset_at_its_idle_value_needs_no_step():
    """"While not in reset" is every trace's default, not something to stage.

    `check_static` demanded a reset step for ANY value on a reset port, so a
    requirement whose activation says "while not in reset" was reported as
    "the stimulus never drives nReset=1 (no reset step)". On a2-i2c that sent
    five requirements -- REQ-0021, 0043, 0079, 0086, 0087 -- chasing a step
    none of them wanted, and in every one of the five the complaint was only
    ever the two reset ports at their inactive levels; cmd, ena, din, sda_i and
    scl_i were never the miss. Two eventually added the step, satisfied this
    check, and STILL abstained -- so the diagnosis had been aiming the retry
    away from the cause the whole time.
    """
    from specflow.ports import asserted_resets

    contract = {"io": [
        {"name": "rst", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
    ]}
    active = asserted_resets(contract)          # {'rst': 1, 'nReset': 0}
    idle = Obligation(req_uid="R", text="while not in reset, cmd is WRITE",
                      inputs={"nReset": 1, "rst": 0, "cmd": 8}, observable=["q"])
    got = check_static(idle, [{"cmd": 8}], reset_ports=active)
    assert got.status == FIRED, got.detail


def test_a_reset_at_its_ACTIVE_value_still_needs_one():
    from specflow.ports import asserted_resets

    contract = {"io": [{"name": "rst", "dir": "input", "width": 1},
                       {"name": "cmd", "dir": "input", "width": 4}]}
    active = asserted_resets(contract)
    ob = Obligation(req_uid="R", text="while rst is asserted",
                    inputs={"rst": 1}, observable=["q"])
    assert check_static(ob, [{"cmd": 8}], reset_ports=active).status == NOT_FIRED
    with_step = check_static(ob, [{"reset": True}, {"cmd": 8}], reset_ports=active)
    assert with_step.status == FIRED


def test_the_plain_set_form_keeps_its_old_behaviour():
    """Only the mapping can tell asserted from idle, so a caller that supplies
    a bare set is no worse off than before -- and no better."""
    ob = Obligation(req_uid="R", text="while not in reset",
                    inputs={"nReset": 1}, observable=["q"])
    got = check_static(ob, [{"cmd": 8}], reset_ports=frozenset({"nReset"}))
    assert got.status == NOT_FIRED


# ------------------------------- a value-set fires on ANY of its alternatives


_ENC = {"io": [
    {"name": "cmd", "dir": "input", "width": 4,
     "encoding": {"I2C_CMD_NOP": 0, "I2C_CMD_START": 1, "I2C_CMD_STOP": 2,
                  "I2C_CMD_WRITE": 4, "I2C_CMD_READ": 8},
     "encoding_complete": True},
    {"name": "ena", "dir": "input", "width": 1},
]}


def _steps(*cmds):
    return [{"inputs": {"cmd": c, "ena": 1}, "hold": 1} for c in cmds]


def test_a_value_set_FIRES_on_any_one_of_its_alternatives():
    """"a START, STOP, READ or WRITE command is accepted" is staged by a
    stimulus that drives ANY one of them. Demanding all four would report
    NOT_FIRED on a step list that stages the requirement perfectly."""
    from specflow.obligation import FIRED, Obligation, check_static
    ob = Obligation.of("REQ-0057", "a supported command is accepted",
                       {"cmd": ["I2C_CMD_START", "I2C_CMD_STOP",
                                "I2C_CMD_READ", "I2C_CMD_WRITE"], "ena": 1},
                       ("cmd_ack",), _ENC)
    assert check_static(ob, _steps(1)).status == FIRED


def test_a_value_set_does_NOT_fire_when_none_of_its_alternatives_is_driven():
    """The set widens what counts, it does not make the check unfalsifiable."""
    from specflow.obligation import NOT_FIRED, Obligation, check_static
    ob = Obligation.of("REQ-0057", "a supported command is accepted",
                       {"cmd": ["I2C_CMD_START", "I2C_CMD_STOP"], "ena": 1},
                       ("cmd_ack",), _ENC)
    got = check_static(ob, _steps(0, 8))
    assert got.status == NOT_FIRED
    assert "cmd=1|2" in got.detail


def test_a_SYMBOL_is_resolved_before_it_reaches_the_static_check():
    """THE BUG THIS FOUND. `Obligation.inputs` used to hold whatever the
    normalization wrote -- `dict(n.activation.inputs)`, symbols included -- and
    `check_static` compared those against the integers the stimulus drives. A
    string never equals an int, so every symbolic activation reported NOT_FIRED
    with a message naming a value the stimulus does drive.

    Latent while normalizations wrote numbers. h2-i2c writes symbols for 28 of
    28 `cmd` activations, which would have made the entire static leg answer
    "the stimulus never drives cmd=I2C_CMD_START".
    """
    from specflow.obligation import FIRED, Obligation, check_static
    ob = Obligation.of("REQ-0001", "a START is issued",
                       {"cmd": "I2C_CMD_START"}, ("cmd_ack",), _ENC)
    assert ob.inputs == {"cmd": (1,)}
    assert check_static(ob, _steps(1)).status == FIRED
