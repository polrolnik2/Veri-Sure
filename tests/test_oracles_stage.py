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


# ------------------------------------------------------------- the ordering


def test_the_oracle_stage_runs_before_the_reference_model_exists():
    """Isolation as a fact about time rather than a prompt discipline.

    `oracle_gen.build_prompt` has no parameter a design could arrive through and
    a test reads the prompt back -- but the model source used to be in the same
    process, one frame up the call stack, because oracle generation ran INSIDE
    `run_refmodel`. Nothing leaks from an artifact that has not been produced.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("specflow/integration.py").read_text())
    build = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "build_artifacts")

    def first_line(name: str) -> int:
        return min(n.lineno for n in ast.walk(build)
                   if isinstance(n, ast.Call)
                   and getattr(n.func, "id", "") == name)

    assert first_line("run_oracle_stage") < first_line("run_refmodel")


def test_the_model_stage_generates_no_oracles_at_all():
    """Not "prefers the supplied set" -- cannot produce one. An oracle written
    after the model exists is written by something that could have read it, and
    the only way to be sure is for the code that writes oracles not to be
    reachable from the code that writes models."""
    import ast
    import inspect

    from specflow.refmodel import compose

    tree = ast.parse(inspect.getsource(compose))
    called = {
        node.func.id if isinstance(node.func, ast.Name)
        else getattr(node.func, "attr", "")
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert "run_oracle_gen" not in called
    assert "oracle_set" in inspect.signature(compose.run_refmodel).parameters



def test_an_oracle_with_no_stimulus_to_run_on_is_not_malformed():
    """It cannot be replayed, so no leg can rule on it -- and that is a fact
    about the STIMULUS. Rejecting it would call a check malformed for a reason
    it has no way to fix, which is the same mistake as rejecting an unexercised
    one."""
    why, quotable = O.verify_one(
        _oracle(GOOD), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp={}, witness=WITNESS, variants=[], base="step")
    assert (why, quotable) == ("", True)


def test_an_oracle_with_no_stimulus_is_still_screened_structurally():
    """The checks that need nothing to replay against still run."""
    why, _ = O.verify_one(
        _oracle("def decide(trace):\n    return True, 0, 'ok'\n"),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp={},
        witness=WITNESS, variants=[], base="step")
    assert why.startswith("malformed:")


def test_the_witness_is_recorded_apart_from_the_reference_model():
    """`model_io` keys every prompt/response pair by `{stage}_r{round}`. Two
    callers produce a model from the same prompt -- the reference model and the
    witness -- so one name for both has the witness overwrite the model's
    record, and a cache or a replay then serves one where the other was asked
    for. Silent, and it corrupts the run's own evidence."""
    import inspect

    from specflow.refmodel import compose, conform

    assert conform.WITNESS_STAGE != compose.STAGE
    assert "stage=WITNESS_STAGE" in inspect.getsource(
        conform.conforming_implementation)
    assert "stage" in inspect.signature(compose.generate_model).parameters


def test_the_witness_is_written_once_and_read_forever(tmp_path):
    """A strengthening round re-enters the stage, and a freshly generated
    witness would be a DIFFERENT reading of the same requirements -- so an
    oracle could be accepted this round and rejected the next for no reason
    anyone could name. Same disease as an unfrozen oracle set, one level over.
    """
    calls: list[int] = []

    def _gen(*, requirements, contract_json, port, workdir, max_repairs=2):
        calls.append(1)
        return WITNESS, []

    import specflow.refmodel.conform as conform
    real = conform.conforming_implementation
    conform.conforming_implementation = _gen
    try:
        first, kind = O._witness(
            requirements=REQS, contract_json="{}", port=None,
            workdir=tmp_path, run_dir=tmp_path)
        again, _ = O._witness(
            requirements=REQS, contract_json="{}", port=None,
            workdir=tmp_path, run_dir=tmp_path)
    finally:
        conform.conforming_implementation = real

    assert kind == O.WITNESS
    assert first == again == WITNESS
    assert len(calls) == 1, "the second round must read, not regenerate"
    assert (tmp_path / "specflow" / "witness.py").is_file()


def test_a_stale_upstream_rebuilds_the_frozen_set(tmp_path, monkeypatch):
    """Written once means once per REQUIREMENT SET, not once per directory.

    Without this the stage spends its whole fan-out generating oracles for the
    new requirements and then silently keeps the old file, so the loop measures
    the new model against checks written for requirements that no longer exist.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    before = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())

    other = GOOD.replace("y did not follow a", "y diverged from a")
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(other)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, run_dir=tmp_path, rewrite=True)
    after = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())

    assert before["oracles"][0]["source"] != after["oracles"][0]["source"]
    assert got.trusted[0].hash != before["oracles"][0]["hash"]


def test_without_rewrite_the_frozen_set_still_wins(tmp_path, monkeypatch):
    """The default is unchanged: a re-entry that is NOT a regeneration must not
    be able to move the measure."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    other = GOOD.replace("y did not follow a", "y diverged from a")
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(other)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, run_dir=tmp_path)
    assert "y did not follow a" in got.trusted[0].source


def test_a_model_with_no_oracles_is_reported_as_unchecked():
    """A model that was never decided and one that passed look identical from
    the outside, and that ambiguity is the one this pipeline exists to remove."""
    import inspect

    from specflow.refmodel import compose

    src = inspect.getsource(compose.run_refmodel)
    assert "refmodel.unchecked" in src
    assert "unrepaired, not" in src


def test_the_witness_is_never_downgraded_to_the_small_model():
    """It is a whole implementation, the same artifact class as the reference
    model, and it answers "can a design built from this requirement satisfy
    this check?". A weaker one answers no too often -- and a witness failure is
    read as over-strictness, so every false no RELAXES an oracle. Downgrading it
    trades over-strict oracles for vacuous ones, which is the trade this
    pipeline has already measured going the wrong way."""
    from specflow.model_io import ApiPort, PortSettings
    from specflow.refmodel.conform import WITNESS_STAGE

    assert WITNESS_STAGE in PortSettings.full_strength_stages
    assert WITNESS_STAGE in ApiPort.__dataclass_fields__[
        "full_strength_stages"].default

    settings = PortSettings(small_model="tiny", small_effort="low")
    assert settings.for_stage(WITNESS_STAGE) == (None, None)
    assert settings.for_stage("oracle_REQ-0001") == ("tiny", "low")


def test_vacuous_is_none_not_zero_when_no_variant_check_ran():
    """`VACUOUS: 0` and `VACUOUS: None` are different claims and only one is
    ever true. This exact ambiguity misread a whole run: `over_strict: 0` was
    taken as "no oracle is over-strict" when it meant "no control was supplied",
    and 22 of 54 trusted oracles turned out to be failed by a known-good model.
    """
    unchecked = O.OracleSet(trusted=[_oracle(GOOD)],
                            dispositions={"REQ-0001": O.TRUSTED}, variants=[])
    assert unchecked.rates()["VACUOUS"] is None

    checked = O.OracleSet(
        trusted=[_oracle(GOOD)], dispositions={"REQ-0001": O.TRUSTED},
        variants=[Variant(req_uid="REQ-0001", kind="action", clause="c",
                          source=BROKEN)])
    assert checked.rates().get("VACUOUS", 0) == 0


def test_the_artifact_says_which_checks_actually_ran(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["vacuity_checked"] is False
    assert blob["over_strictness_bounded_by"] == O.WITNESS
