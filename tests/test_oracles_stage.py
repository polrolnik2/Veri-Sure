"""[O]: the requirement oracles, as a stage.

The properties here are the ones the interleaved version could not have. Each
names the measurement that motivated it.
"""

from __future__ import annotations

import json

from specflow import oracles_stage as O
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.variants import Variant

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "y", "dir": "output", "width": 1},
]}

WITNESS = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
"""
BROKEN = WITNESS.replace("i['a']", "1 - i['a']")
CRASHES = WITNESS.replace("i['a']", "self.MISSING")

STIM = {"TP-0000": [{"a": 0}, {"a": 1}, {"a": 0}]}
TESTPLAN = [{"uid": "TP-0000", "covers": ["REQ-0001@1"]}]
REQS = [{"uid": "REQ-0001", "text": "y follows a"}]

GOOD = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] != row['inputs']['a']:
            return False, row['edge'], 'y did not follow a'
    return True, 0, 'y followed a'
"""
#: Demands something the witness cannot do.
OVER_STRICT = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] != 1:
            return False, row['edge'], 'y was not already high'
    return True, 0, 'ok'
"""
#: Reads a declared port and cannot fail.
VACUOUS = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] not in (0, 1):
            return False, row['edge'], 'y is not a bit'
    return True, 0, 'y stayed a bit'
"""
#: Its scenario never occurs in this stimulus. NOT a defect.
UNEXERCISED = """\
def decide(trace):
    if not any(r['inputs']['a'] == 7 for r in trace):
        return None, None, 'a never reached 7'
    return True, 0, 'ok'
"""


def _oracle(source: str, uid: str = "REQ-0001") -> RequirementOracle:
    return RequirementOracle(req_uid=uid, tp_uids=["TP-0000"],
                             clause="y follows a", source=source)


def _verify(source, **kw):
    return O.verify_one(
        _oracle(source), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp=STIM, witness=kw.pop("witness", WITNESS),
        variants=kw.pop("variants", []), base="step", **kw)


# ------------------------------------------------------------- verification


def test_a_sound_oracle_passes():
    assert _verify(GOOD) == ("", True)


def test_an_over_strict_oracle_is_rejected_and_quotable():
    why, quotable = _verify(OVER_STRICT)
    assert why.startswith("over-strict:") and quotable
    assert "edge" in why, "the author needs to know where it tripped"


def test_a_vacuous_oracle_is_rejected():
    variants = [Variant(req_uid="REQ-0001", kind=k, clause="c", source=BROKEN)
                for k in ("trigger", "action")]
    why, quotable = _verify(VACUOUS, variants=variants)
    assert why.startswith("vacuous:") and quotable


def test_an_unexercised_oracle_is_NOT_rejected():
    """`NOT_EXERCISED` is a joint property of stimulus and model and belongs to
    the debug loop. Rejecting it here deletes the findings the stimulus tool
    exists to act on."""
    assert _verify(UNEXERCISED) == ("", True)


def test_a_witness_that_crashes_does_not_convict_the_oracle():
    """Blaming the check for the reference's crash is the confusion this whole
    design exists to prevent, one level over."""
    assert _verify(GOOD, witness=CRASHES) == ("", True)


def test_a_malformed_oracle_is_rejected_before_anything_is_replayed():
    why, _ = _verify("def decide(trace):\n    return True, 0, 'ok'\n")
    assert why.startswith("malformed:"), why


# ----------------------------------------------- the control rejects, never repairs


def test_a_control_rejection_is_not_quotable():
    """Feeding a known-good design's trace back to the oracle author tunes the
    oracle against it -- and the model is then tuned against the oracle, so the
    model ends up tuned against the grade. `golden_check` stops being held out.
    """
    # Passes the witness, fails the control.
    control = WITNESS.replace("i['a']", "0")
    why, quotable = O.verify_one(
        _oracle(GOOD), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp=STIM, witness=WITNESS, control=control,
        variants=[], base="step")
    assert why.startswith("over-strict:")
    assert not quotable
    assert "withheld" in why


def test_the_control_runs_last():
    """It is the only check whose finding cannot be acted on, so spending it
    before the ones that can would waste the strongest instrument."""
    control = WITNESS.replace("i['a']", "0")
    why, quotable = O.verify_one(
        _oracle(OVER_STRICT), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp=STIM, witness=WITNESS, control=control,
        variants=[], base="step")
    assert quotable, "the witness caught it first, so the author can be told"


# --------------------------------------------------------------- the stage


class _Port:
    """Replies with a fixed oracle body, and records what it was asked."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.prompts: list[str] = []

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


def _reply(source: str) -> str:
    return json.dumps({"reasoning": "r", "clause": "y follows a",
                       "source": source})


def _run(port, **kw):
    return O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=kw.pop("workdir"), base="step",
        control_source=kw.pop("control_source", None),
        fanout=False, max_repairs=0, **kw)


def test_every_requirement_gets_a_disposition(tmp_path, monkeypatch):
    """5 of 77 oracles vanished at generation on h-i2c and surfaced as an
    UNDECIDED that also means 'decided nothing'. A stage records them."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    two = REQS + [{"uid": "REQ-0002", "text": "no testpoint covers this"}]
    got = O.run_oracle_stage(
        requirements=two, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0)
    assert set(got.dispositions) == {"REQ-0001", "REQ-0002"}
    assert got.dispositions["REQ-0001"] == O.TRUSTED
    assert got.dispositions["REQ-0002"] == "UNDECIDED"
    assert "no oracle was produced" in got.reasons["REQ-0002"]


def test_a_rejected_oracle_is_re_asked_with_the_reason(tmp_path, monkeypatch):
    """ORACLE_INVALID rose 4 -> 5 -> 8 monotonically because nothing ever
    re-asked. This is the loop every other stage already has."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(OVER_STRICT), _reply(GOOD)])
    got = _run(port, workdir=tmp_path)
    assert len(port.prompts) == 2, "the rejection must cost a second call"
    assert "over_strict" in port.prompts[1] or "over-strict" in port.prompts[1]
    assert got.dispositions["REQ-0001"] == O.TRUSTED
    assert got.rounds == 2


def test_an_unrepairable_oracle_lands_on_a_verdict_not_a_hole(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    got = _run(_Port([_reply(OVER_STRICT)]), workdir=tmp_path)
    assert got.dispositions["REQ-0001"] == "ORACLE_INVALID"
    assert got.reasons["REQ-0001"].startswith("over-strict:")
    assert got.trusted == []


def test_a_control_only_rejection_does_not_cost_a_repair_call(tmp_path, monkeypatch):
    """Its reason cannot reach a prompt, so re-asking would spend a call on a
    prompt carrying no information."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    got = _run(port, workdir=tmp_path,
               control_source=WITNESS.replace("i['a']", "0"))
    assert len(port.prompts) == 1
    assert got.dispositions["REQ-0001"] == "ORACLE_INVALID"


def test_the_artifact_carries_the_trusted_set_and_the_reasons(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    got = _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert [o["req_uid"] for o in blob["oracles"]] == ["REQ-0001"]
    assert blob["dispositions"]["REQ-0001"] == O.TRUSTED
    assert blob["witness"] == O.WITNESS
    assert got.trusted[0].hash, "frozen oracles carry their content hash"


def test_no_witness_is_reported_rather_than_assumed(tmp_path, monkeypatch):
    """Over-strictness UNBOUNDED is a real weakening and must be visible."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: ("", O.NO_BOUND))
    got = _run(_Port([_reply(OVER_STRICT)]), workdir=tmp_path)
    assert got.witness_kind == O.NO_BOUND
    assert got.dispositions["REQ-0001"] == O.TRUSTED, (
        "with nothing to bound it, an over-strict oracle cannot be caught -- "
        "which is why the absence is reported")
