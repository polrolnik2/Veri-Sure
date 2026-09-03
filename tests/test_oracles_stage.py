"""[O]: the requirement oracles, as a stage.

The properties here are the ones the interleaved version could not have. Each
names the measurement that motivated it.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    # Both designs observed, neither decided. The set is not pinned exactly:
    # `verify_one` may add a note from an instrument that reads the TRACE rather
    # than the design -- `idle_match` does -- and adding one must not read as a
    # regression in the rule this test protects, which is `why == ""`.
    assert {"witness", "control"} <= set(notes)


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
    assert settings.for_stage("oracle_REQ-0001")[0] == "tiny"


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


def test_the_repair_label_does_not_change_which_model_serves_the_call():
    """`for_stage` matches on the first `_`-separated token, so a label must not
    change which model serves the call.

    The invariant is SAMENESS, not smallness. It held when oracles ran on the
    small model and it has to hold now they author at full strength, because a
    repair pass answered by a different model than the attempt it repairs makes
    the two incomparable.
    """
    from specflow.model_io import PortSettings

    # Asserted with deep_effort ON, because that is the configuration where a
    # label could change the answer -- the whole point of the invariant.
    s = PortSettings(small_model="small", small_effort="low", deep_effort="high")
    served = {s.for_stage(stage) for stage in
              ("oracle_REQ-0001", "oracle_REQ-0001_fix1",
               "oracle_REQ-0001_strengthen1")}
    assert len(served) == 1, f"a label changed the model: {served}"
    assert served == {("small", "high")}, (
        "oracles keep the small model and get deep_effort on it")

    # And with it off, they sit at small_effort -- still all the same.
    off = PortSettings(small_model="small", small_effort="low")
    assert {off.for_stage(x) for x in
            ("oracle_REQ-0001", "oracle_REQ-0001_fix1")} == {("small", "low")}


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


def test_an_inert_stimulus_is_measured_and_named(tmp_path, monkeypatch):
    """A testpoint that moves nothing makes every oracle naming it unjudgeable,
    however well written -- so a thin stimulus caps oracle quality before oracle
    quality is in question.

    `stimulus_liveness` has existed for months and nothing called it: its one
    caller went with the judge. What it says about n-i2c's stimulus, replayed on
    the KNOWN-GOOD control -- 11% of testpoints show ONE output state across
    ~256 edges, the median shows five, two of eight outputs never move -- was
    therefore never in any artifact.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    dead = {"TP-0000": [{"a": 0}, {"a": 0}, {"a": 0}]}
    O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=dead,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, repair_attempts=0, run_dir=tmp_path)

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    live = blob["stimulus_liveness"]
    assert live is not None, "measured, not omitted"
    assert live["inert_count"] == 1
    assert live["inert"] == ["TP-0000"]


def test_a_live_stimulus_reports_zero_rather_than_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_Port([_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, repair_attempts=0, run_dir=tmp_path)
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["stimulus_liveness"]["inert_count"] == 0


# ------------------------------------------------------- oracle liveness


#: Reads the declared output and decides nothing about it. Trusted by every
#: gate the stage has -- well-formed, executable, on-target, non-vacuous --
#: and unable to fail any design.
INERT = """\
def decide(trace):
    for row in trace:
        _ = row['outputs']['y']
    return True, 0, 'looked at y and concluded nothing'
"""


def test_an_oracle_that_cannot_fail_is_reported(tmp_path, monkeypatch):
    """The gap every other gate in this stage leaves open.

    Measured on the frozen 70: 20 trusted oracles could not be moved by any
    legal value of the ports they read, and 11 of them had reported CONFORMS
    against the shipped model. Nothing in the stage asked.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    got = _run(_Port([_reply(INERT)]), workdir=tmp_path, run_dir=tmp_path)

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    # `oracle_liveness` reports on the TRUSTED set, and a check that cannot fail
    # is no longer in it -- the finding moved from a report to a rejection, so
    # the artifact now says "no trusted oracle is dead" and means it.
    assert blob["oracle_liveness"] == {}
    assert got.dispositions["REQ-0001"] == "VACUOUS", (
        "reported, not gated -- this stage has twice turned a number into a "
        "refusal before knowing what it rejects")


def test_a_live_oracle_records_the_ports_it_decides_on(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)

    live = json.loads(
        (tmp_path / "specflow" / O.ARTIFACT).read_text())["oracle_liveness"]
    assert live["counts"]["dead-oracle"] == 0
    assert live["asserts_on"]["REQ-0001"] == ["y"]


def test_liveness_is_measured_against_the_witness_not_a_reference_model(
        tmp_path, monkeypatch):
    """Isolation, and it costs nothing -- see `liveness`'s own docstring.

    The same 70 oracles gave identical verdicts against a model scoring 30/168
    and the known-good control at 168/168. What is pinned here is the weaker
    structural fact: the source handed to it is the witness, and the reference
    model does not exist when this stage runs.
    """
    from specflow.refmodel import liveness as L

    seen: list[str] = []
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(
        L, "assess",
        lambda oracles, source, *a, **kw: seen.append(source) or {})
    _run(_Port([_reply(GOOD)]), workdir=tmp_path, run_dir=tmp_path)
    assert seen, "the stage must measure liveness at all"
    assert set(seen) == {WITNESS}, "every call sees the witness and nothing else"
    assert BROKEN not in seen and CRASHES not in seen


def test_an_oracle_that_cannot_fail_is_re_asked_with_the_counterexample(
        tmp_path, monkeypatch):
    """Detection with no route back is the defect this stage was built to fix.

    `ORACLE_INVALID` rose 4 -> 5 -> 8 across three turns with nothing able to
    pull it down, because the only thing that noticed could not ask again. An
    inert check now earns one attempt, the same shape gate 1 has.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(INERT), _reply(GOOD)])
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", run_dir=tmp_path,
        fanout=False, max_repairs=0, repair_attempts=1)

    asked = [p for p in port.prompts if "cannot fail" in p]
    assert asked, "the author is never told"
    assert "driven to every other legal value" in asked[0]
    # NO OFFER TO DECLINE. It is a rejection now, not an advisory, and a
    # blocking gate cannot invite the author to keep the check as it is. The one
    # escape that is not a decline survives: a requirement constraining nothing
    # observable is a finding about the specification.
    assert "you may decline" not in asked[0].lower()
    assert "finding about the specification" in asked[0].lower()

    assert got.dispositions["REQ-0001"] == O.TRUSTED
    assert "y" in got.trusted[0].source, "the working replacement was taken"
    live = json.loads(
        (tmp_path / "specflow" / O.ARTIFACT).read_text())["oracle_liveness"]
    assert live["counts"]["dead-oracle"] == 0, (
        "the artifact must report what the LAST round saw, not the first")


def test_a_still_inert_replacement_is_KEPT_because_liveness_is_not_the_only_axis(
        tmp_path, monkeypatch):
    """REVERSED, deliberately. This used to assert the opposite.

    The rule was "advice must not become a way to lose a check": a replacement
    that still cannot fail left the previous one standing. It read as the same
    asymmetry the witness advisory uses, and it is not -- because `_is_live` is
    a ONE-BIT verdict, and a repair can improve a check without moving it.

    Measured, REQ-0055 on the affected23 run:

        round 0  trigger cmd==1, `al` folded into `until`   cannot fail
        round 1  trigger WIDENED to all four commands       cannot fail -> DROPPED
        round 2  restarted from ROUND 0, fixed the abort    can fail    -> kept

    and correspondence then rejected the frozen check for narrowing "each
    command sequence" to cmd==1 -- the defect round 1 had already corrected.
    Two repair rounds spent, one correction destroyed, the requirement lost.
    Neither `_is_live` nor `_decides` can see trigger coverage, so the guard
    could not tell an improved-but-still-inert replacement from an unimproved
    one and discarded both.

    The churn the guard prevented is cheaper than the work it destroyed. The two
    remaining guards still bite, and both are measurable losses that get
    recorded: a replacement that VERIFIES worse, and one that stopped deciding.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    other_inert = INERT.replace("concluded nothing", "concluded nothing again")
    port = _Port([_reply(INERT), _reply(other_inert)])
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", run_dir=tmp_path,
        fanout=False, max_repairs=0, repair_attempts=1)

    assert got.dispositions["REQ-0001"] == "VACUOUS", (
        "a check that still cannot fail is rejected, not frozen TRUSTED")
    assert not got.trusted, "nothing inert survives into the trusted set"


def test_a_dead_check_is_re_asked_every_round_like_any_other_rejection(
        tmp_path, monkeypatch):
    """CHANGED WITH THE GATE, and the old rationale does not carry over.

    This asserted the question was asked ONCE -- "re-asking a question already
    answered is pressure by repetition, which is what turned the over-strictness
    gate into a compliance ratchet". That reasoning is about ADVISORIES, where
    declining is a real answer and repetition is coercion. A blocking gate has
    no such reading: `malformed:` and `off-target:` are re-put every round until
    fixed or the rounds run out, and "cannot fail" is now the same kind of
    finding, so it gets the same treatment. Homogeneity is the point.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(INERT)])
    O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", run_dir=tmp_path,
        fanout=False, max_repairs=0, repair_attempts=2)
    assert len([p for p in port.prompts if "cannot fail" in p]) >= 1


def test_unobservable_keeps_the_reason_its_oracle_was_rejected_for():
    """Both claims are true, and the second says whether the first is repairable.

    Generation filters on testpoint attachment, not on observability, so an
    oracle IS attempted for a requirement normalization called blind. Until this
    the rejection reason was discarded here, and seven requirements on s-i2c
    reported nothing but normalization's prose -- establishing why their oracles
    had failed meant going back to `agent_io`, where all seven turned out to
    have had between two and five rounds spent on them.
    """
    dispositions, why = O._dispositions(
        requirements=[{"uid": "REQ-0001"}],
        trusted=[],
        rejected={"REQ-0001": "vacuous: passed all 3 variant(s)"},
        had_source={"REQ-0001"},
        normalized={"REQ-0001": {"observable": [],
                                 "unobservable_reason": "counter is internal"}},
    )
    assert dispositions["REQ-0001"] == "UNOBSERVABLE", (
        "no boundary observable is the more fundamental claim and still routes "
        "to spec authoring")
    assert "counter is internal" in why["REQ-0001"]
    assert "vacuous" in why["REQ-0001"], "the rejection reason survives too"


def test_unobservable_with_no_oracle_attempt_reads_cleanly():
    """No rejection to report means no dangling 'and its oracle was rejected:'."""
    _, why = O._dispositions(
        requirements=[{"uid": "REQ-0002"}],
        trusted=[], rejected={}, had_source=set(),
        normalized={"REQ-0002": {"observable": [],
                                 "unobservable_reason": "purely internal"}},
    )
    assert why["REQ-0002"] == "purely internal"


# ------------------------------------- the tightening loop's own by-product


def test_every_replacement_is_re_verified_not_only_the_advisory_ones():
    """A reply to a REJECTION used to go into the set unchecked.

    `_strengthen` has never worked that way -- "a replacement is kept only if it
    VERIFIES" -- and the asymmetry mattered because both repair paths push the
    SAME direction: vacuity says the check passes something wrong, so tighten it.

    Measured on s-i2c, the only run whose `_fix` rounds ran, against the
    known-good control: 13 of 28 repaired-and-kept oracles are failed by it
    (46%) against 2 of 30 never repaired (6%). 13 of that run's 15 over-strict
    checks came out of the tightening loop.
    """
    import inspect

    from specflow import oracles_stage as OS

    src = inspect.getsource(OS.run_oracle_stage)
    body = src[src.index("for o in again:"):src.index("held[o.req_uid] = o")]
    assert "if o.req_uid in advisory_only:" not in body, (
        "re-verification must not be gated on the reply being advisory")
    assert body.count("verify_one(") == 1, (
        "the replacement is re-verified exactly once, on every path")


def test_over_strictness_the_repair_created_is_reported_never_acted_on():
    """The control may not select which oracles survive.

    Withholding its detail from prompts stops its behaviour leaking into oracle
    text, but kept-or-rejected is the bit that matters: it decides which oracles
    the model is repaired against, and the model is what `golden_check` then
    scores. So this is an artifact field, not a verdict.
    """
    import inspect

    from specflow import oracles_stage as OS

    src = inspect.getsource(OS.run_oracle_stage)
    where = src.index("newly_over_strict.add")
    after = src[where:where + 400]
    assert "rejected[" not in after and "continue" not in after.split("\n")[1], (
        "a control disagreement must not remove an oracle from the set")
    assert '"over_strict_after_repair"' in src, (
        "and it has to reach the artifact, or it decides nothing and reports "
        "nothing -- the pattern this repo has now caught nine times")


def test_the_repair_budget_is_attempts_not_verification_rounds():
    """`max_rounds: int = 2` bought exactly ONE repair attempt, and the name is
    why nobody noticed.

    The loop breaks at the last round BEFORE re-asking -- correctly, since an
    attempt whose reply nothing verifies is not an attempt -- so N rounds gave
    N-1 attempts. `repair_attempts` now says what it means and the loop derives
    the extra verification pass itself.
    """
    import inspect

    from specflow import oracles_stage as OS

    sig = inspect.signature(OS.run_oracle_stage).parameters
    assert "max_rounds" not in sig, "the misleading name must not survive"
    assert sig["repair_attempts"].default == 2, (
        "z-i2c rescued 8 of 16 vacuous oracles on one attempt; the second is "
        "the cheap untested lever")

    src = inspect.getsource(OS.run_oracle_stage)
    assert "verifications = max(0, int(repair_attempts)) + 1" in src
    assert "rounds == verifications" in src, (
        "the break must key on the derived count, not on the attempt budget, "
        "or the last attempt goes unverified")


def test_a_check_that_cannot_fire_does_not_refute_unobservable():
    """SURVIVING IS NOT DECIDING, and that gap sent 19 findings to the wrong party.

    `UNOBSERVABLE` means THIS REQUIREMENT'S TEXT names no declared output port
    the behaviour is directly visible on -- not that no port could observe it,
    which is why a working oracle is allowed to refute it. But nothing rejects
    an oracle for never firing: `verify_one` explicitly does not treat an
    unexercised replay as a finding, since the scenario not being staged is the
    stimulus's business. So a check that abstains on every testpoint survived
    every gate and refuted the claim on no evidence.

    Measured on z-i2c: 19 of 33 NOT_EXERCISED at turn 0 were requirements
    normalization had called unobservable, routed to "fix the stimulus" -- and a
    requirement whose own text names no observable gives the stimulus author
    nothing to aim at either.
    """
    reqs = [{"uid": "REQ-0001", "text": "x"}, {"uid": "REQ-0002", "text": "y"}]
    blind = {"REQ-0001": {"observable": []}, "REQ-0002": {"observable": []}}
    fires = RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                              clause="c", source=GOOD)
    inert = RequirementOracle(req_uid="REQ-0002", tp_uids=["TP-0000"],
                              clause="c", source=GOOD)

    disp, why = O._dispositions(
        requirements=reqs, trusted=[fires, inert], rejected={},
        had_source={"REQ-0001", "REQ-0002"}, normalized=blind,
        never_decides={"REQ-0002": "the check never triggered"})

    assert disp["REQ-0001"] == O.TRUSTED, (
        "a check that DOES decide still refutes the claim -- that rule is why "
        "normalization calling 27 of 77 unobservable was caught")
    assert disp["REQ-0002"] == "UNOBSERVABLE", (
        "a check that never fires is not evidence that something observable "
        f"was there: {disp}")


def test_the_refutation_still_works_when_liveness_was_not_measured():
    """`never_decides` defaults to empty, so a caller without a liveness report
    keeps the old behaviour rather than silently reclassifying everything."""
    reqs = [{"uid": "REQ-0001", "text": "x"}]
    o = RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                          clause="c", source=GOOD)
    disp, _ = O._dispositions(
        requirements=reqs, trusted=[o], rejected={},
        had_source={"REQ-0001"}, normalized={"REQ-0001": {"observable": []}})
    assert disp["REQ-0001"] == O.TRUSTED


# --------------------------------------------------------------- ABANDONED
#
# What DISCARD means: we failed to interpret this requirement, and stop counting
# it. Not "advisory" -- a downgraded verdict is still in the way. These pin the
# difference, and the rule that stops the softening being free.


def test_an_abandoned_requirement_leaves_the_driving_set():
    """The half that makes discard mean discard.

    Excluded from `trusted`, so the debug loop cannot decide it, `run_all`
    cannot count it and the board cannot show it.
    """
    from specflow.oracles_stage import OracleSet

    o = _oracle("def decide(t): return True", uid="REQ-0000")
    s = OracleSet(trusted=[o],
                  dispositions={"REQ-0000": "TRUSTED", "REQ-0001": "ABANDONED"},
                  abandoned={"REQ-0001": "never reached"})
    assert [x.req_uid for x in s.trusted] == ["REQ-0000"]
    assert "REQ-0001" not in {x.req_uid for x in s.trusted}


def test_an_abandoned_requirement_leaves_the_denominator_and_is_counted():
    """"46 of 70 CONFORM" with 10 abandoned is THREE numbers -- 46, 60 and 10.

    Reporting the first two without the third is the class of number this
    project has already had to retract twice.
    """
    from specflow.oracles_stage import OracleSet

    s = OracleSet(dispositions={f"REQ-000{i}": "TRUSTED" for i in range(6)}
                  | {"REQ-0006": "ABANDONED", "REQ-0007": "ABANDONED"},
                  abandoned={"REQ-0006": "never reached",
                             "REQ-0007": "no observation route found"})
    assert s.considered() == 6
    rates = s.rates()
    assert rates["considered"] == 6 and rates["abandoned"] == 2


def test_abandoning_outranks_the_claim_it_would_otherwise_report():
    """`UNOBSERVABLE` is a claim about the REQUIREMENT and can be false --
    measured: 27 of 77 called unobservable by reading the mechanism, 10 of which
    had working checks. What a bounded attempt knows is narrower and about us.
    """
    from specflow.oracles_stage import _dispositions

    reqs = [{"uid": "REQ-0000"}]
    norm = {"REQ-0000": {"observable": [], "unobservable_reason": "internal"}}
    plain, _ = _dispositions(requirements=reqs, trusted=[], rejected={},
                             had_source=set(), normalized=norm)
    assert plain["REQ-0000"] == "UNOBSERVABLE"

    out, why = _dispositions(
        requirements=reqs, trusted=[], rejected={}, had_source=set(),
        normalized=norm, abandoned={"REQ-0000": "no observation route found"})
    assert out["REQ-0000"] == "ABANDONED"
    assert why["REQ-0000"] == "no observation route found"


def test_nothing_is_abandoned_without_an_attempt():
    """THE ANTI-SHORTCUT PIN, and the load-bearing one.

    `abandoned` is populated only by a stage that ran a bounded attempt. Empty
    means nothing was tried, and nothing may be discarded on that basis --
    otherwise the gate rewards not trying, which is what z-i2c did:
    `stimulus_added: 0` on three turns with 33 oracles at NOT_EXERCISED.
    """
    from specflow.oracles_stage import _dispositions

    out, _ = _dispositions(
        requirements=[{"uid": "REQ-0000"}], trusted=[], rejected={},
        had_source=set(),
        normalized={"REQ-0000": {"observable": [], "unobservable_reason": "x"}},
        abandoned={})
    assert out["REQ-0000"] == "UNOBSERVABLE", "blocking, because nobody tried"


def test_a_requirement_the_resolution_pass_could_not_route_is_abandoned():
    """It has been ASKED, so the honest disposition is about us, not about it.

    `UNOBSERVABLE` claims no port shows the behaviour. After `resolve_indirect`
    has offered every blind requirement the indirect route and come back empty,
    what is known is narrower: we could not turn this into a check we can
    exercise.
    """
    from specflow.oracles_stage import _dispositions

    asked = {"REQ-0000": {"observable": [], "unobservable_reason": "internal",
                          "observed_via": []}}
    out, why = _dispositions(
        requirements=[{"uid": "REQ-0000"}], trusted=[], rejected={},
        had_source=set(), normalized=asked,
        abandoned={"REQ-0000": "no observation route found"})
    assert out["REQ-0000"] == "ABANDONED"
    assert why["REQ-0000"] == "no observation route found"


def test_a_normalized_form_predating_the_pass_is_not_treated_as_asked():
    """Absence of `observed_via` is absence of an attempt, not a failed one --
    abandoning on it would discard requirements nothing ever asked about."""
    from specflow.oracles_stage import _dispositions

    never_asked = {"REQ-0000": {"observable": [], "unobservable_reason": "x"}}
    out, _ = _dispositions(
        requirements=[{"uid": "REQ-0000"}], trusted=[], rejected={},
        had_source=set(), normalized=never_asked, abandoned={})
    assert out["REQ-0000"] == "UNOBSERVABLE", "blocking: the pass did not run"


# ------------------------------- the staging loop, through the whole stage
#
# `test_stimulus_loop` pins the loop in isolation. These run it where it
# actually sits -- after the repair rounds, before the freeze -- because that
# placement is what decides whether its results reach the artifact and whether
# the set it staged into is the set that gets frozen.


def _staged(tmp_path, monkeypatch, steps, oracle_source=UNEXERCISED):
    """Run the whole stage with an oracle nothing reaches, and a scripted
    generator. Returns the `OracleSet`."""
    import specflow.testcase_agent as ta

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(ta, "stimulus_for_scenario",
                        lambda **_kw: list(steps))
    port = _Port([_reply(oracle_source)])
    # COPIES: the loop appends to both by design -- the debug loop downstream
    # has to see what was staged -- so sharing the module fixtures would leak
    # minted testpoints into every later test in this file.
    return O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=[dict(e) for e in TESTPLAN],
        stimulus_by_tp={k: list(v) for k, v in STIM.items()},
        port=port, workdir=tmp_path, run_dir=tmp_path, base="step",
        fanout=False, max_repairs=0,
        want_staging=True, staging_attempts=2)


def test_the_stage_stages_what_nothing_reaches_and_records_it(tmp_path,
                                                              monkeypatch):
    """The oracle abstains until `a` reaches 7; the generator supplies it."""
    got = _staged(tmp_path, monkeypatch, [{"a": 7}, {"a": 0}])
    assert got.abandoned == {}, "it was reached, so nothing is given up on"
    added = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text()
                       )["stimulus_added"]
    assert added["REQ-0001"], "the minted testpoint is named in the artifact"
    assert got.dispositions["REQ-0001"] == O.TRUSTED


def test_a_requirement_the_stage_could_not_reach_leaves_the_frozen_set(
        tmp_path, monkeypatch):
    """"Staged N times, never reached" and "nobody tried" stop being the same
    verdict, and the first one leaves the system."""
    got = _staged(tmp_path, monkeypatch, [{"a": 1}, {"a": 0}])
    assert got.abandoned == {"REQ-0001": "never reached in 2 attempt(s)"}
    assert [o.req_uid for o in got.trusted] == [], "not in the driving set"
    assert got.dispositions["REQ-0001"] == "ABANDONED"
    assert got.considered() == 0, "it left the denominator too"

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["abandoned"] == {"REQ-0001": "never reached in 2 attempt(s)"}
    assert blob["staging"]["REQ-0001"]["reached_at_attempt"] is None
    assert len(blob["staging"]["REQ-0001"]["attempts"]) == 2, "both attempts"


def test_an_oracle_that_already_decides_is_never_staged_for(tmp_path,
                                                            monkeypatch):
    """The loop's input is `never_decides`, not "everything"."""
    got = _staged(tmp_path, monkeypatch, [{"a": 7}], oracle_source=GOOD)
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["stimulus_added"] == {} and got.abandoned == {}


# --- variants are generated ONCE, from the witness -----------------------


def test_variants_are_read_back_rather_than_regenerated(tmp_path, monkeypatch):
    """The artifact is consulted BEFORE generating, not only inherited.

    In-process inheritance (`previous.variants`) covers a scoped round and does
    not survive the process -- and [O] is long enough that it routinely does not
    finish in one. On a2-i2c a restart during the stage discarded 159 variant
    calls, about 1.3M input tokens, to rebuild a file whose own writer would
    have refused to overwrite it.
    """
    from specflow.refmodel import variants as variants_mod

    spec = tmp_path / "specflow"
    spec.mkdir()
    kept = [variants_mod.Variant(req_uid="REQ-0001", kind="trigger",
                                 source="class RefModel:\n    pass\n")]
    variants_mod.save(kept, spec / "variants.json")

    called = []
    monkeypatch.setattr(variants_mod, "run_variant_gen",
                        lambda **kw: (called.append(kw) or ([], [])))
    loaded = variants_mod.load(spec / "variants.json")
    assert [v.req_uid for v in loaded] == ["REQ-0001"]
    assert called == []          # nothing regenerated them


def test_save_refuses_to_overwrite_so_the_draw_holds_still(tmp_path):
    """A second draw would convict an oracle of vacuity about a design it was
    never shown."""
    from specflow.refmodel import variants as variants_mod

    path = tmp_path / "variants.json"
    first = [variants_mod.Variant(req_uid="REQ-0001", kind="trigger", source="a")]
    second = [variants_mod.Variant(req_uid="REQ-0002", kind="guard", source="b")]
    variants_mod.save(first, path)
    variants_mod.save(second, path)
    assert [v.req_uid for v in variants_mod.load(path)] == ["REQ-0001"]


def test_variants_are_persisted_before_the_rest_of_the_stage_can_fail():
    """Written the moment they exist, not at the end of [O].

    Oracle generation, verification, repair and the stimulus loop all come
    after, all can be interrupted, and none of them changes what a variant is.
    """
    src = Path("specflow/oracles_stage.py").read_text()
    gen = src.index("variants, _ = variants_mod.run_variant_gen(")
    gen_call = src.index("run_oracle_gen(", gen)
    assert "variants_mod.save(variants, variants_path)" in src[gen:gen_call], (
        "variants must be saved between generating them and generating oracles")


def test_a_stale_requirement_set_still_discards_the_variants():
    """Reuse is only safe because `rewrite` unlinks the artifact first."""
    src = Path("specflow/oracles_stage.py").read_text()
    rewrite = src[src.index("if rewrite and run_dir is not None:"):]
    assert '"variants.json"' in rewrite[:600]


# ------------------- a replacement that stopped deciding is not a repair


#: Decides on the one testpoint it names.
DECIDES = """\
def decide(trace):
    for row in trace:
        if row['inputs']['a'] == 1:
            return row['outputs']['y'] == 1, row['edge'], 'a was high'
    return None, None, 'a was never high'
"""
#: Same shape, activation narrowed until nothing matches -- which is what an
#: author does when told its trigger is too broad.
NARROWED = DECIDES.replace("row['inputs']['a'] == 1",
                           "row['inputs']['a'] == 7")


def test_decides_counts_the_testpoints_a_check_reaches_a_verdict_on():
    assert O._decides(_oracle(DECIDES), WITNESS, CONTRACT, STIM, base="step") == 1
    assert O._decides(_oracle(NARROWED), WITNESS, CONTRACT, STIM, base="step") == 0


def test_a_check_that_decides_nothing_is_distinguishable_from_one_that_fails():
    """The point of counting decisions rather than verdicts: `_decides` must
    not confuse "said False" with "said nothing". Both are non-True."""
    assert O._decides(_oracle(GOOD), WITNESS, CONTRACT, STIM, base="step") == 1
    assert O._decides(_oracle(GOOD), BROKEN, CONTRACT, STIM, base="step") == 1


def test_a_crashing_check_decides_nothing():
    """A `decide` that raises has not decided, whatever it was going to say."""
    boom = "def decide(trace):\n    return trace['nope']\n"
    assert O._decides(_oracle(boom), WITNESS, CONTRACT, STIM, base="step") == 0


def test_a_testpoint_with_no_stimulus_contributes_no_decision():
    o = RequirementOracle(req_uid="REQ-0001", clause="c", source=DECIDES,
                          tp_uids=["TP-0000", "TP-0404"])
    assert O._decides(o, WITNESS, CONTRACT, STIM, base="step") == 1


def test_every_path_that_discards_a_replacement_records_it():
    """A discarded repair must leave a trace in `repairs`, not only in a log.

    Three paths drop a replacement and keep the previous check: `verify_one`
    calls it worse, it stopped deciding, or it was advisory and still cannot
    fail. The third recorded nothing, and that cost real forensics. On the
    affected23 run REQ-0055's round-1 replacement widened a trigger from
    cmd==1 to all four commands; it was discarded, and NEITHER the round-2
    author NOR any reviewer ever saw it -- confirmed by grepping the rendezvous
    prompts, because the artifact held two objections and no discard. Round 2
    restarted from the round-0 check, fixed a different defect, and the frozen
    result was rejected for exactly the narrow trigger round 1 had corrected.

    The artifact is what a later reader reconstructs the loop from. A path that
    throws away an author's work and says so only to a logger makes the loop
    unauditable from its own output.
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    # Every `the previous check stands` / `previous stands` outcome pairs with a
    # `repairs.setdefault(...)` -- count the discards and the records together.
    stands = src.count("the previous check stands") + src.count("the previous stands")
    recorded = src.count('repairs.setdefault(o.req_uid, []).append')
    assert recorded >= 2, (
        f"only {recorded} discard paths record to `repairs`; a silent one is "
        f"how a lost repair becomes invisible in the artifact")
    assert stands >= recorded, "every record should describe a real stand-down"
    # AND THE THIRD GUARD IS GONE, not merely made to record itself. It
    # discarded a replacement whose check still could not fail, which threw away
    # REQ-0055's widened trigger and cost the requirement. Liveness was the only
    # axis it could see, and the repair had moved a different one.
    assert "_is_live(" not in src, (
        "the liveness discard is dropped; a helper left behind gets re-wired")


def test_every_operator_the_author_is_told_about_is_importable_and_shown():
    """The prompt must not name an operator its own import line omits.

    This is the third instance of one pattern in this stage: `observed_via`
    had a gate with no shape, `sustains` had a schema field with no prompt,
    and `runs`/`nth` were described in prose while the import statement the
    author copies listed neither. A check calling one would have raised
    NameError at decide time and been recorded as a broken oracle -- blaming
    the author for a line the prompt told it to write.

    Pins the direction that matters: everything IMPORTED must exist, and
    everything DESCRIBED must be imported.
    """
    import re

    from specflow.refmodel import temporal
    from specflow.refmodel.oracle_gen import SYSTEM

    shown = set()
    for m in re.finditer(r"from \S*temporal import \(([^)]*)\)", SYSTEM, re.S):
        shown |= {n.strip(" ,") for n in m.group(1).split()}
    assert shown, "the prompt shows no temporal import at all"

    for name in sorted(shown):
        assert hasattr(temporal, name), f"prompt imports {name}, which does not exist"

    # And the two cycle-accurate operators specifically: described in prose,
    # so they must also be reachable.
    for name in ("runs", "nth"):
        assert name in shown, f"{name} is described but not in the import line"


def test_counting_guidance_is_general_and_names_no_design():
    """The author has `runs`/`nth`; it was also told not to invent a window.

    Two things gated the requirement class the operators were built for. The
    `sustains` paragraph opened with "When it is present", and the older rule
    says "You are not inventing a window, you are copying one" -- so with
    `sustains: []` the author holds the tool and an instruction against
    reaching for it.

    Normalization is RIGHT to leave it empty in that case: it can only quote a
    phrase naming the port's own duration, and a spec often states the number
    in other units. The author reads the same sentence and can do the
    arithmetic, so the permission belongs here.

    THE FIRST VERSION OF THIS WAS OVERFITTED. It was written as an exception
    under the window rule with i2c's own filter as the worked example -- the
    port name, the sample count and the resulting bound all inlined -- which
    teaches pattern-matching on one design instead of the rule. This pins the
    general form: one section, both operators, the transcribe-or-invent test
    stated once, and no design in it.
    """
    from specflow.refmodel.oracle_gen import SYSTEM

    start = SYSTEM.find("COUNTS AND DURATIONS")
    assert start > 0, "the counting guidance must be its own section"
    block = SYSTEM[start:SYSTEM.find("COUNT IN EDGES AND LET")]

    # Both axes, named together, since confusing them inverts the property.
    assert "runs(trace, port" in block and "nth(w, holds, n)" in block
    # The test that licenses a number, and the record that proves it was applied.
    assert "whether you can quote it" in block.lower()
    assert "QUOTE THE PHRASE IN YOUR DETAIL STRING" in block
    # The arithmetic clause -- the whole reason an empty `sustains` is not a
    # statement that the requirement is countless.
    assert "ARITHMETIC ON A STATED NUMBER IS STILL TRANSCRIPTION" in block

    # NO DESIGN IN IT. This is the regression the first version was.
    for token in ("sda_i", "scl_i", "three-sample", "filter window", "cmd_ack"):
        assert token not in block, f"{token!r} overfits the prompt to one design"

    # And the rule it is an opening in must still stand, elsewhere.
    assert "not inventing a window, you are copying one" in SYSTEM



def test_an_idle_note_does_NOT_bury_the_witness_failure():
    """h3-i2c froze five checks that the witness had already failed.

    REQ-0028/0057/0099/0100/0101 each carried BOTH an `idle_match` note and a
    `witness` note. `_witness_note` returned on `idle_match` alone, so the
    author heard "you judged at idle" and never heard that a second
    implementation had failed the check. All five froze TRUSTED and all five
    convicted golden RTL -- a quarter of that run's false convictions, with the
    evidence sitting unread in `instrument_notes`.

    The specific diagnosis still leads; the witness fact now follows it.
    """
    from specflow.oracles_stage import _witness_note

    both = _witness_note("REQ-0100", {
        "idle_match": "judged at edge 8, before any of dout had moved",
        "witness": "fails it at edge 8",
    })
    kinds = [i.path.rsplit(".", 1)[-1] for i in both]
    assert kinds == ["judged_at_idle", "witness_disagrees_reported"], (
        "the precise note leads, and the witness verdict is not dropped"
    )


def test_the_witness_fact_does_not_ask_for_relaxation():
    """`_advisory` asks the author to TRY to accept the other implementation,
    and that ask measured over-strictness 27 -> 15 with convictions 2 -> 16.
    The reported fact must not carry it."""
    from specflow.oracles_stage import _witness_note

    note = _witness_note("REQ-0100", {
        "idle_match": "judged at edge 8", "witness": "fails it at edge 8",
    })[1]
    assert "not a request to weaken" in note.message
    assert "TRY" not in note.message


def test_an_idle_note_ALONE_is_unchanged():
    from specflow.oracles_stage import _witness_note

    only = _witness_note("REQ-0070", {"idle_match": "judged at edge 0"})
    assert [i.path.rsplit(".", 1)[-1] for i in only] == ["judged_at_idle"]
