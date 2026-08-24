"""[O]: the requirement oracles, as a stage.

The properties here are the ones the interleaved version could not have. Each
names the measurement that motivated it.
"""

from __future__ import annotations

import json

from specflow import oracles_stage as O
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel import variants as variants_mod
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
    assert _verify(GOOD) == ("", True, {})


def test_no_implementation_gates_an_oracle():
    """The rule the whole stage now turns on.

    An oracle that fails BOTH designs is still usable. Only two things reject,
    and neither is an implementation: structure, and vacuity from variants,
    which come from the requirement text.
    """
    control = WITNESS.replace("i['a']", "0")
    why, quotable, notes = O.verify_one(
        _oracle(OVER_STRICT), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp=STIM, witness=WITNESS, control=control,
        variants=[], base="step")
    assert why == "", f"a design rejected an oracle: {why}"
    assert quotable
    assert set(notes) == {"witness", "control"}


def test_the_witness_records_a_disagreement_rather_than_a_verdict():
    """It is a second reading of the same requirements by the same author, so
    an oracle failing it means two same-author readings disagree and either
    could be wrong. Measured: rejecting on it moved over-strictness 27 -> 15 and
    convictions 2 -> 16 -- oracles relaxed until they stopped disagreeing."""
    why, _quotable, notes = _verify(OVER_STRICT)
    assert why == ""
    assert "edge" in notes["witness"], "the observation still says where"


def test_the_control_records_without_saying_where():
    """It is known-good because it scores 168/168 against the golden RTL, so it
    is a proxy for the held-out grade. Its detail must not reach a prompt, and
    its keep/reject bit must not shape the run either."""
    control = WITNESS.replace("i['a']", "0")
    _why, _q, notes = O.verify_one(
        _oracle(GOOD), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp=STIM, witness=WITNESS, control=control,
        variants=[], base="step")
    assert "control" in notes
    assert "withheld" in notes["control"]
    assert "-- " not in notes["control"], "no trace detail may appear"


def test_a_vacuous_oracle_is_rejected():
    """Variants come from the requirement text, so this gate involves no
    design and keeps its authority."""
    variants = [Variant(req_uid="REQ-0001", kind=k, clause="c", source=BROKEN)
                for k in ("trigger", "action")]
    why, quotable, _notes = _verify(VACUOUS, variants=variants)
    assert why.startswith("vacuous:") and quotable


def test_an_unexercised_oracle_is_NOT_rejected():
    """`NOT_EXERCISED` is a joint property of stimulus and model and belongs to
    the debug loop. Rejecting it here deletes the findings the stimulus tool
    exists to act on."""
    assert _verify(UNEXERCISED) == ("", True, {})


def test_a_witness_that_crashes_does_not_convict_the_oracle():
    """Blaming the check for the reference's crash is the confusion this whole
    design exists to prevent, one level over."""
    assert _verify(GOOD, witness=CRASHES) == ("", True, {})


def test_an_oracle_that_breaks_on_replay_is_still_malformed():
    """The ORACLE breaking is structural and rejects; the DESIGN breaking does
    not. The distinction is the one the module exists to keep."""
    why, _q, _n = _verify("def decide(trace):\n"
                          "    return trace['y'], 0, 'wrong shape'\n")
    assert why.startswith("malformed:"), why


def test_a_malformed_oracle_is_rejected_before_anything_is_replayed():
    why, _q, _n = _verify("def decide(trace):\n    return True, 0, 'ok'\n")
    assert why.startswith("malformed:"), why


# --------------------------------------------------------------- the stage


class _Port:
    """Replies with a fixed oracle body, and records what it was asked."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.prompts: list[str] = []
        self.stages: list[str] = []

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.prompts.append(prompt)
        self.stages.append(stage)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


def _reply(source: str) -> str:
    return json.dumps({"reasoning": "r", "clause": "y follows a",
                       "source": source})


#: Variants for a requirement, so the vacuity gate -- the only quotable
#: rejection left, and the only one derived from the requirement rather than
#: from a design -- can fire in the repair-loop tests.
def _variants():
    return [Variant(req_uid="REQ-0001", kind=k, clause="c", source=BROKEN)
            for k in ("trigger", "action")]


def _with_variants(monkeypatch):
    """Make the stage's variant fan-out return a fixed pair.

    Vacuity is the only quotable rejection left -- the only gate derived from
    the requirement rather than from a design -- so it is what drives the repair
    loop now.
    """
    monkeypatch.setattr(variants_mod, "run_variant_gen",
                        lambda **_kw: (_variants(), []))


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
    _with_variants(monkeypatch)
    port = _Port([_reply(VACUOUS), _reply(GOOD)])
    got = _run(port, workdir=tmp_path, want_variants=True)
    assert len(port.prompts) == 2, "the rejection must cost a second call"
    assert "vacuous" in port.prompts[1]
    assert got.dispositions["REQ-0001"] == O.TRUSTED
    assert got.rounds == 2


def test_an_unrepairable_oracle_lands_on_a_verdict_not_a_hole(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _with_variants(monkeypatch)
    got = _run(_Port([_reply(VACUOUS)]), workdir=tmp_path, want_variants=True)
    assert got.dispositions["REQ-0001"] == "VACUOUS"
    assert got.reasons["REQ-0001"].startswith("vacuous:")
    assert got.trusted == []


def test_a_control_disagreement_costs_no_call_and_no_verdict(tmp_path,
                                                             monkeypatch):
    """The control is a proxy for the held-out grade, so it may neither spend a
    repair call nor decide a disposition. It is recorded and nothing else."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    got = _run(port, workdir=tmp_path, run_dir=tmp_path,
               control_source=WITNESS.replace("i['a']", "0"))
    assert len(port.prompts) == 1
    assert got.dispositions["REQ-0001"] == O.TRUSTED
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["unsatisfiable_by_the_control"] == ["REQ-0001"]


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
    why, quotable, _differs = O.verify_one(
        _oracle(GOOD), contract=CONTRACT, testplan=TESTPLAN,
        stimulus_by_tp={}, witness=WITNESS, variants=[], base="step")
    assert (why, quotable) == ("", True)


def test_an_oracle_with_no_stimulus_is_still_screened_structurally():
    """The checks that need nothing to replay against still run."""
    why, _q, _differs = O.verify_one(
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


def test_a_repair_pass_is_recorded_beside_the_attempt_it_repairs(tmp_path,
                                                                 monkeypatch):
    """`model_io` keys every prompt/response pair by `{stage}_r{round}`, and
    each `run_stage` call starts its rounds at zero -- so a repair pass over the
    same requirement silently REWRITES the record of the attempt it is
    repairing. Both the rejected oracle and the prompt showing why it was
    rejected vanish, and that is the evidence every measurement in this project
    is reconstructed from.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _with_variants(monkeypatch)
    port = _Port([_reply(VACUOUS), _reply(GOOD)])
    _run(port, workdir=tmp_path, want_variants=True)

    stages = [p for p in port.stages]
    assert stages[0] == "oracle_REQ-0001", stages
    assert stages[1] != stages[0], (
        f"the repair pass reused the first pass's record key: {stages}")
    assert stages[1].startswith("oracle_REQ-0001_fix"), stages


def test_the_repair_label_does_not_escape_the_small_model():
    """`for_stage` matches on the first `_`-separated token, so a label must not
    change which model serves the call."""
    from specflow.model_io import PortSettings

    s = PortSettings(small_model="small", small_effort="low")
    for stage in ("oracle_REQ-0001", "oracle_REQ-0001_fix1",
                  "oracle_REQ-0001_strengthen1"):
        assert s.for_stage(stage) == ("small", "low"), stage


def test_a_repaired_oracle_keeps_a_record_of_what_was_caught(tmp_path,
                                                            monkeypatch):
    """A repaired oracle ends TRUSTED with an empty `reasons` entry, so without
    this the only trace of what the gate caught is in `agent_io` -- and a repair
    pass is exactly what overwrites that. "What does the must-pass leg actually
    catch" is a question this project has already had to answer once by
    reconstructing it from a transcript directory."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _with_variants(monkeypatch)
    got = _run(_Port([_reply(VACUOUS), _reply(GOOD)]), workdir=tmp_path,
               run_dir=tmp_path, want_variants=True)

    assert got.dispositions["REQ-0001"] == O.TRUSTED
    assert got.repairs["REQ-0001"], "the complaint that was acted on is gone"
    assert got.repairs["REQ-0001"][0].startswith("vacuous:")

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["repairs"]["REQ-0001"] == got.repairs["REQ-0001"]


def test_testpoints_no_oracle_names_are_counted_not_ignored(tmp_path,
                                                            monkeypatch):
    """Stimulus that runs and proves nothing is the inert-testbench failure
    this project exists to prevent, one level up. Measured on n-i2c: 17 of 167
    testpoints were named by no oracle -- each one renders, starts a simulator
    process, and decides nothing."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    plan = list(TESTPLAN) + [{"uid": "TP-0900", "covers": ["REQ-0404@1"]}]
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=plan, stimulus_by_tp=STIM,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, run_dir=tmp_path)

    assert got.testpoints_no_oracle_names == ["TP-0900"]
    assert got.decides_nothing() == 1
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["testpoints_no_oracle_names"] == ["TP-0900"]


def test_a_fully_covered_plan_reports_an_empty_list_not_a_missing_key(tmp_path,
                                                                      monkeypatch):
    """An empty list and an unmeasured one read the same in a report and mean
    opposite things."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["testpoints_no_oracle_names"] == []
