"""[O]: the requirement oracles, as a stage.

The properties here are the ones the interleaved version could not have. Each
names the measurement that motivated it.
"""

from __future__ import annotations

import json
from pathlib import Path

from specflow import oracles_stage as O
from specflow.refmodel import liveness as _L
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
# An abstainer that is otherwise a REAL check: it reads the declared output.
# The earlier body read only `a`, so it decided nothing about the design at all,
# and `well_formed` now refuses that -- which would have made these tests about
# the wrong thing. Abstention is what they are for; naming no output was never
# the point.
UNEXERCISED = """\
def decide(trace):
    hits = [r for r in trace if r['inputs']['a'] == 7]
    if not hits:
        return None, None, 'a never reached 7'
    for row in hits:
        if row['outputs']['y'] != row['inputs']['a']:
            return False, row['edge'], 'y did not follow a while a was 7'
    return True, 0, 'y followed a whenever a was 7'
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

    #: FILTERED ON THE REJECTION, NOT ON A PHRASE. "cannot fail" also appears
    #: in SYSTEM -- "weakening what you assert produces a check that cannot
    #: fail, which is discarded as vacuous" -- so the loose filter matched the
    #: first GENERATION prompt and asserted against it.
    asked = [p for p in port.prompts if "vacuous: this check cannot fail" in p]
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
    #: THE REASON NOW NAMES THE FAILURE. "never reached" alone charged every
    #: loss to the stimulus loop; measured on a full run, only 5 of 30 were
    #: failures that loop could act on.
    assert list(got.abandoned) == ["REQ-0001"]
    assert got.abandoned["REQ-0001"].startswith(
        "never reached in 2 attempt(s)")
    assert [o.req_uid for o in got.trusted] == [], "not in the driving set"
    assert got.dispositions["REQ-0001"] == "ABANDONED"
    assert got.considered() == 0, "it left the denominator too"

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert list(blob["abandoned"]) == ["REQ-0001"]
    assert blob["abandoned"]["REQ-0001"].startswith(
        "never reached in 2 attempt(s)")
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


# --------------------------------------------------------------------------
# A1/A2: THE CORPUS. A run authors three to six bodies per requirement and
# keeps ONE; every other body is discarded at the moment it is superseded,
# which is exactly the population a selection rule needs.
# --------------------------------------------------------------------------

def _body(n: int) -> str:
    return (f"def decide(trace):\n"
            f"    return (trace[0]['outputs']['y'] == {n}, 0, 'v{n}')\n")


def _corpus_oracle(uid: str, n: int) -> RequirementOracle:
    return RequirementOracle(req_uid=uid, clause="", source=_body(n),
                             tp_uids=["TP-0000"])


def test_a_superseded_body_is_retained_with_the_objection_it_answered():
    corpus: dict[str, list[O.CorpusBody]] = {}
    O._retain(corpus, _corpus_oracle("REQ-0001", 0), arm="repair", round_=0)
    O._retain(corpus, _corpus_oracle("REQ-0001", 1), arm="repair", round_=1,
              answered="narrowed 'each command' to cmd==1")
    members = corpus["REQ-0001"]
    assert len(members) == 2
    assert [m.round_ for m in members] == [0, 1]
    assert members[1].answered.startswith("narrowed")
    #: and the predecessor's TEXT survives, which is the whole point
    assert members[0].source != members[1].source


def test_retention_de_duplicates_by_CONTENT_not_by_round():
    """The recording key is `{stage}_r{round}` and the resume port returns the
    FIRST response for a matching key, so N draws under one stage name are one
    response replayed N times. k1's volume round retained 8 byte-identical
    pairs exactly that way -- retaining by round would record a corpus of N
    where the authoring produced 1.
    """
    corpus: dict[str, list[O.CorpusBody]] = {}
    for r in range(4):
        O._retain(corpus, _corpus_oracle("REQ-0001", 0), arm="draw", round_=r)
    assert len(corpus["REQ-0001"]) == 1


def test_the_corpus_survives_a_freeze_and_reload():
    """THE LOSSY-LOAD TRAP. `load` already dropped `repairs`, `abandoned` and
    `tools`; a corpus field added without extending it would vanish on every
    `--reuse`, and surviving the run that built it is the corpus's entire job.
    """
    import tempfile

    from specflow.refmodel import freeze as freeze_mod

    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "specflow").mkdir(parents=True)
        oracle = _corpus_oracle("REQ-0001", 0)
        freeze_mod.freeze(
            [oracle], run / "specflow" / O.ARTIFACT,
            extra={
                "dispositions": {"REQ-0001": "TRUSTED"},
                "repairs": {"REQ-0001": ["round 0 objected"]},
                "abandoned": {"REQ-0002": "no observation route found"},
                "tools": {"correspondence": False, "max_repairs": 3},
                "corpus": {"REQ-0001": [
                    {"source": _body(0), "arm": "repair", "round": 0,
                     "answered": "", "frozen": True},
                    {"source": _body(1), "arm": "repair", "round": 1,
                     "answered": "narrowed the trigger", "frozen": False},
                ]},
            })
        back = O.load(run)

    assert back is not None
    members = back.corpus["REQ-0001"]
    assert [m.round_ for m in members] == [0, 1]
    assert [m.frozen for m in members] == [True, False]
    assert members[1].answered == "narrowed the trigger"
    #: and the three fields that were ALREADY being lost
    assert back.repairs == {"REQ-0001": ["round 0 objected"]}
    assert back.abandoned == {"REQ-0002": "no observation route found"}
    assert back.tools["max_repairs"] == 3


def test_an_unretained_run_reads_as_not_retained_and_not_as_one_body():
    """Empty is the honest value. A corpus defaulting to the trusted set would
    make every historical run look like it authored exactly one body per
    requirement, which is the claim the retention exists to stop being true."""
    assert O.OracleSet(trusted=[_corpus_oracle("REQ-0001", 0)]).corpus == {}


def test_the_stage_hands_out_a_corpus_of_what_it_actually_authored(
        tmp_path, monkeypatch):
    """**A2 AT THE CALL SITE, not at the helper.** The retention test above
    calls `_retain` directly and therefore cannot see whether the repair loop
    calls it -- a mutation disabling the wiring survived that test. This one
    drives the stage and reads the corpus off the set it returns.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    _with_variants(monkeypatch)
    #: VACUOUS is rejected by the vacuity gate, GOOD replaces it -- the same
    #: fixture the repair-loop tests above use, chosen because the first
    #: version of this test used a body that was never rejected, so no repair
    #: ran and the mutation disabling the repair-path retention survived.
    got = _run(_Port([_reply(VACUOUS), _reply(GOOD)]), workdir=tmp_path,
               want_variants=True)
    assert got.repairs["REQ-0001"], "no repair ran; the wiring is untested"

    members = got.corpus["REQ-0001"]
    #: **BOTH bodies are present**, not just the survivor
    assert len(members) == 2, [m.arm for m in members]
    assert {m.arm for m in members} == {"generate", "repair"}
    assert [m.round_ for m in members] == [0, 1]
    #: the superseded body's TEXT survives, which is the whole point
    assert members[0].source != members[1].source
    #: the objection it answered travels with the replacement
    assert members[1].answered.startswith("vacuous:")
    #: exactly one survivor, and its text is the one in `trusted`
    assert [m.frozen for m in members] == [False, True]
    assert members[1].source == got.trusted[0].source


# --------------------------------------------------------------------------
# THE APPLIED CORRESPONDENCE RATE. The gate is published at one draw per
# oracle and this stage spends up to `repair_attempts + 1` of them over the
# whole surviving set. `repairs` carries the reasons but not the round, so the
# population that tells the two apart was not recoverable from a finished run.
# --------------------------------------------------------------------------


def _review(*, obligation: bool = True, tests: bool = True,
            missing: str = "", reasoning: str = ""):
    from specflow.refmodel.correspondence import Review

    return Review(states_an_obligation=obligation, tests_the_requirement=tests,
                  what_is_missing=missing, reasoning=reasoning)


def test_the_round_record_splits_the_two_legs_and_counts_what_was_ASKED():
    """`not-assertable` accuses the specification, `off-target` accuses the
    check, and they route to different owners -- so one count over both would
    be the routing error `rejects` exists to prevent. And `reviewed` counts
    oracles PUT to the gate, not answers received: a parse error is not a
    rejection, so it belongs in neither list and still in the denominator.
    """
    from specflow.refmodel.correspondence import PARSE_ERROR

    record = O._correspondence_round(2, {
        "REQ-0001": _review(),
        "REQ-0002": _review(tests=False, missing="decides the prescaler"),
        "REQ-0003": _review(obligation=False, missing="forbids nothing"),
        #: both legs false -- the prior question wins, exactly as `rejects` says
        "REQ-0004": _review(obligation=False, tests=False, missing="no effect"),
        #: an unreachable model. Asked, unanswered, convicted of nothing.
        "REQ-0005": _review(reasoning=f"{PARSE_ERROR}TimeoutError()"),
    })

    assert record["round"] == 2
    assert record["reviewed"] == 5, "a parse error is still an oracle asked"
    assert record["off_target"] == ["REQ-0002"]
    assert record["not_assertable"] == ["REQ-0003", "REQ-0004"]


def test_the_applied_rate_is_recoverable_per_round_after_a_freeze_and_reload():
    """THE LOSSY-LOAD TRAP, and the reason this field exists at all.

    Without the round index a run cannot be asked the one question that
    separates a gate finding something new from a gate re-rolling the same
    dice: what does the triple look like over the checks rejected on a round
    > 1 only? This pins that the index survives to the artifact and back.

    It records a QUESTION being answerable. A round-2 rejection is not evidence
    the check was bad and the count is not a span loss -- see the call site.
    """
    import tempfile

    from specflow.refmodel import freeze as freeze_mod

    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "specflow").mkdir(parents=True)
        freeze_mod.freeze(
            [_corpus_oracle("REQ-0001", 0)], run / "specflow" / O.ARTIFACT,
            extra={
                "dispositions": {"REQ-0001": "TRUSTED"},
                "correspondence_rounds": [
                    {"round": 1, "reviewed": 40, "off_target": ["REQ-0009"],
                     "not_assertable": []},
                    {"round": 2, "reviewed": 39, "off_target": ["REQ-0021"],
                     "not_assertable": ["REQ-0033"]},
                ],
            })
        back = O.load(run)

    assert back is not None
    rounds = back.correspondence_rounds
    assert [r["round"] for r in rounds] == [1, 2]
    assert [r["reviewed"] for r in rounds] == [40, 39]
    #: THE POPULATION THE PRE-REGISTRATION NAMES: rejected on a round > 1.
    later = [u for r in rounds if r["round"] > 1 for u in r["off_target"]]
    assert later == ["REQ-0021"]
    #: and the legs stay apart across the round trip
    assert rounds[1]["not_assertable"] == ["REQ-0033"]


def test_a_set_frozen_before_this_measurement_reloads_EMPTY_not_wrong():
    """Missing is "not measured", never "the gate rejected nobody" -- the same
    distinction `load` already keeps for `oracle_liveness`. A zero here would
    read as a clean run and put a 0% applied rate into a comparison.
    """
    import tempfile

    from specflow.refmodel import freeze as freeze_mod

    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "specflow").mkdir(parents=True)
        freeze_mod.freeze([_corpus_oracle("REQ-0001", 0)],
                          run / "specflow" / O.ARTIFACT,
                          extra={"dispositions": {"REQ-0001": "TRUSTED"}})
        back = O.load(run)

    assert back is not None
    assert back.correspondence_rounds == []


# --------------------------------------------------------------------------
# SURVIVING IS NOT DECIDING. `trusted` means "passed every gate"; on the two
# runs where both were counted it overstated what executed by 17% and 30%.
# --------------------------------------------------------------------------


def _set_with(liveness: dict[str, str], uids=("REQ-0001", "REQ-0002")):
    return O.OracleSet(
        trusted=[_corpus_oracle(u, 0) for u in uids],
        dispositions={u: "TRUSTED" for u in uids},
        liveness=liveness)


def test_an_inert_check_that_SHIPPED_is_counted_apart_from_a_live_one():
    """The round loop rejects `dead-oracle` and deliberately does not reject
    `dead-stimulus` -- an unstaged scenario is the testplan's business, not the
    author's -- and `unknown` covers a check with no replayable testpoint. All
    three ship TRUSTED and none of them decided anything on this run.
    """
    rates = _set_with(
        {"REQ-0001": _L.LIVE, "REQ-0002": _L.DEAD_STIMULUS},
    ).rates()

    assert rates["trusted"] == 2, "the headline is unchanged"
    assert rates["trusted_live"] == 1
    assert rates["trusted_inert"] == 1
    assert rates["trusted_liveness_unknown"] == 0


def test_a_trusted_check_liveness_never_reached_is_UNKNOWN_not_live():
    """Absent from the map is not a verdict. Defaulting it to live is how
    "nobody looked" turns into a count of working checks."""
    rates = _set_with({"REQ-0001": _L.LIVE}).rates()

    assert rates["trusted_live"] == 1
    assert rates["trusted_liveness_unknown"] == 1, (
        "REQ-0002 has no verdict and must not be credited with one")


def test_a_dead_oracle_restored_by_reuse_is_not_folded_into_unknown():
    """It should be empty -- the round loop rejects `dead-oracle`. But a set
    frozen before that gate existed can carry one through `--reuse`, and
    folding it into "unknown" would hide precisely the checks the gate was
    added to catch."""
    rates = _set_with({"REQ-0001": _L.DEAD_ORACLE,
                       "REQ-0002": _L.DEAD_STIMULUS}).rates()

    assert rates["trusted_inert"] == 2
    assert rates["trusted_liveness_unknown"] == 0


def test_liveness_that_never_ran_reports_None_and_never_zero():
    """The rule this class already keeps for VACUOUS and NOT_ASSERTABLE. A
    zero would read as "nothing inert shipped", which is what "nobody looked"
    looks like in a report."""
    rates = _set_with({}).rates()

    assert rates["trusted"] == 2
    assert rates["trusted_live"] is None
    assert rates["trusted_inert"] is None
    assert rates["trusted_liveness_unknown"] is None


# --------------------------------------------------------------------------
# E1: A REQUIREMENT THAT LEAVES THROUGH A SILENT GUARD IS INVISIBLE IN EVERY
# RATE. `_unreached` has five of them; 18 of k1-dcfsm's 25 ABANDONED were
# silenced there and which guard did it was unrecoverable from the artifact.
# --------------------------------------------------------------------------


def test_each_unreached_guard_names_itself_into_the_record():
    """Five `return ""`s are indistinguishable in the artifact, and the five
    route to five different owners: a testplan defect, a normalisation defect
    and an author defect are not the same finding. This pins that each guard
    that fires says which one it was."""
    silenced: dict[str, str] = {}
    oracle = _oracle(GOOD)

    #: nothing was attempted -- a discard must be EARNED by an attempt that ran
    assert O._unreached(oracle, None, WITNESS, CONTRACT, STIM, base="step",
                        transactional=True, silenced=silenced) == ""
    assert "nothing was attempted" in silenced["REQ-0001"]

    #: attempted == 0 is a different guard and must not read as the first
    silenced.clear()
    assert O._unreached(oracle, {"attempted": 0}, WITNESS, CONTRACT, STIM,
                        base="step", transactional=True,
                        silenced=silenced) == ""
    assert "attempted == 0" in silenced["REQ-0001"]

    #: the scenario WAS reached -- not a silence at all
    silenced.clear()
    assert O._unreached(oracle, {"attempted": 2, "reached_at_attempt": 1},
                        WITNESS, CONTRACT, STIM, base="step",
                        transactional=True, silenced=silenced) == ""
    assert "WAS reached" in silenced["REQ-0001"]

    #: no stimulus on any testpoint it names -- the TESTPLAN's, not the author's
    silenced.clear()
    assert O._unreached(oracle, {"attempted": 2}, WITNESS, CONTRACT, {},
                        base="step", transactional=True,
                        silenced=silenced) == ""
    assert "no stimulus" in silenced["REQ-0001"]

    #: and the collector is optional -- a caller that passes none still works
    assert O._unreached(oracle, None, WITNESS, CONTRACT, STIM, base="step",
                        transactional=True) == ""


def test_a_real_unreached_rejection_is_not_recorded_as_silenced():
    """The record is of requirements that left WITHOUT a disposition. One that
    gets a real `unreached:` objection is visible already and must not be
    double-counted as invisible."""
    silenced: dict[str, str] = {}
    why = O._unreached(
        _oracle(UNEXERCISED), {"attempted": 3, "attempts": []}, WITNESS,
        CONTRACT, STIM, base="step", transactional=True, silenced=silenced)
    assert why.startswith("unreached:"), why
    assert silenced == {}, silenced


def test_the_two_dropped_fields_survive_a_freeze_and_reload():
    """`testpoints_no_oracle_names` was being dropped by `load`, so
    `decides_nothing()` read 0 on every `--reuse` -- which its own docstring
    says must never happen: "an empty list and an unmeasured one read the same
    in a report and mean opposite things"."""
    import tempfile

    from specflow.refmodel import freeze as freeze_mod

    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "specflow").mkdir(parents=True)
        freeze_mod.freeze(
            [_corpus_oracle("REQ-0001", 0)], run / "specflow" / O.ARTIFACT,
            extra={
                "dispositions": {"REQ-0001": "TRUSTED"},
                "testpoints_no_oracle_names": ["TP-0007", "TP-0009"],
                "unreached_silenced": {"REQ-0002": "attempted == 0"},
            })
        back = O.load(run)

    assert back is not None
    assert back.testpoints_no_oracle_names == ["TP-0007", "TP-0009"]
    assert back.decides_nothing() == 2, "it read 0 on every --reuse before this"
    assert back.unreached_silenced == {"REQ-0002": "attempted == 0"}


def test_the_unreached_call_site_passes_the_collector():
    """Third time on this branch that a call site inside `run_oracle_stage`
    survived every behavioural test when deleted. The function is correct and
    unreachable from any unit test, so the wiring is pinned at the source."""
    import re
    from pathlib import Path

    import specflow.oracles_stage as oracles_stage

    src = Path(oracles_stage.__file__).read_text(encoding="utf-8")

    assert re.search(r"_unreached\(.{0,300}?silenced=unreached_silenced",
                     src, re.DOTALL), (
        "run_oracle_stage must pass its collector to _unreached, or the guard "
        "attribution is computed and thrown away")
    #: and it has to reach the artifact and come back
    assert '"unreached_silenced": unreached_silenced' in src
    assert 'blob.get("unreached_silenced")' in src
    assert 'blob.get("testpoints_no_oracle_names")' in src


def test_abandonment_is_scoped_to_the_requirements_the_stage_was_given():
    """`normalized` can hold more than `requirements` -- an `only`-scoped round,
    or a caller passing a map built over a larger set. Without the scope guard
    the loop abandons uids that get no disposition at all, while
    `considered()` still subtracts them: measured at 20 requirements with 41
    normalized forms, `abandoned` held 17 of which 10 had no disposition and
    `considered()` read 3 where it should read 13.
    """
    import re
    from pathlib import Path

    import specflow.oracles_stage as oracles_stage

    src = Path(oracles_stage.__file__).read_text(encoding="utf-8")
    loop = src[src.index("for uid, shape in (normalized or {}).items():"):]
    guard = loop[:loop.index('if "observed_via" not in shape:')]
    assert re.search(r"if uid not in by_uid:\s*\n\s*continue", guard), (
        "the abandonment loop must skip uids the stage was not given, or it "
        "abandons requirements that have no disposition and silently shrinks "
        "the denominator `considered()` divides by")


def test_considered_never_exceeds_what_the_dispositions_describe():
    """The invariant the scope bug broke: everything `abandoned` names must be
    something `dispositions` also names, or the denominator is subtracting
    requirements that were never in the numerator."""
    s = O.OracleSet(
        trusted=[], dispositions={"REQ-0001": "ABANDONED", "REQ-0002": "TRUSTED"},
        abandoned={"REQ-0001": "no observation route found"})
    assert s.considered() == 1

    stray = O.OracleSet(
        trusted=[], dispositions={"REQ-0001": "ABANDONED", "REQ-0002": "TRUSTED"},
        abandoned={"REQ-0001": "x", "REQ-9999": "not in this stage at all"})
    assert stray.considered() == 0, (
        "this is the defect's signature: a stray abandonment drives the "
        "denominator below the number of requirements actually dispositioned")


def test_the_repair_slope_is_recorded_and_survives_a_reload():
    """The stage blocks a repair that stops deciding ENTIRELY (`was and not
    now`). It does not see one that goes from ten testpoints to one, and that
    is the gradual road into the sound-and-blind population -- among k1's 68
    sound checks the chance of discriminating is 26% against a 75% base rate.

    Recorded so the distribution can be read BEFORE a threshold is picked; the
    cliff is measured at nine checks and the slope at none.
    """
    import tempfile

    from specflow.refmodel import freeze as freeze_mod

    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp)
        (run / "specflow").mkdir(parents=True)
        freeze_mod.freeze(
            [_corpus_oracle("REQ-0001", 0)], run / "specflow" / O.ARTIFACT,
            extra={"dispositions": {"REQ-0001": "TRUSTED"},
                   "repair_narrowing": {
                       "REQ-0001": [{"round": 1, "was": 10, "now": 1}],
                       "REQ-0002": [{"round": 1, "was": 2, "now": 5}]}})
        back = O.load(run)

    assert back is not None
    assert back.narrowing["REQ-0001"] == [{"round": 1, "was": 10, "now": 1}]
    #: a repair that WIDENS is recorded too -- the field is the slope, not a
    #: one-sided complaint, and a widening is the outcome a repair wants
    assert back.narrowing["REQ-0002"][0]["now"] == 5


def test_the_slope_is_recorded_on_any_change_not_only_a_total_loss():
    """`if was and not now` is the CLIFF. Recording only that would leave the
    slope exactly as unmeasured as it was, which is the thing this is for."""
    import re
    from pathlib import Path

    import specflow.oracles_stage as oracles_stage

    src = Path(oracles_stage.__file__).read_text(encoding="utf-8")
    assert re.search(r"if was != now:\s*\n\s*narrowing\.setdefault", src), (
        "the slope must be recorded whenever the count CHANGES; recording it "
        "only when the check stops deciding measures the cliff twice and the "
        "slope never")


def test_the_control_bar_is_priced_beside_the_rates_and_never_gated_on():
    """The bar stays -- the control may not select which oracles survive,
    because gating on it tunes the model toward the held-out grade. But the
    COST of keeping it was only ever recoverable by reconstruction: "61 checks
    the golden falsifies, known at authoring time, shipped TRUSTED"."""
    s = O.OracleSet(
        trusted=[_corpus_oracle("REQ-0001", 0), _corpus_oracle("REQ-0002", 1)],
        dispositions={"REQ-0001": "TRUSTED", "REQ-0002": "TRUSTED"},
        witness_kind="witness+control",
        control_notes={"REQ-0001": "fails it at edge 12"})
    assert s.rates()["trusted_the_control_fails"] == 1
    #: and it changes no disposition -- the check is still TRUSTED
    assert s.dispositions["REQ-0001"] == "TRUSTED"
    assert "REQ-0001" in [o.req_uid for o in s.trusted]


def test_no_control_reports_None_and_never_zero():
    """0 would read as "no oracle is over-strict". That exact ambiguity misread
    a whole run: `over_strict: 0` meant "no control was supplied", and 22 of 54
    trusted oracles turned out to be failed by a known-good model."""
    s = O.OracleSet(trusted=[], dispositions={"REQ-0001": "TRUSTED"},
                    witness_kind=O.NO_BOUND)
    assert s.rates()["trusted_the_control_fails"] is None


def test_a_check_the_whole_population_convicts_is_rejected():
    """The dual of `_cannot_fail`, exercised through the helper that decides
    it. `_population_verdicts` feeds `variety.refuted_by_the_population`, and
    the stage rejects what comes back.
    """
    from specflow import oracles_stage as O
    from specflow import variety

    #: Convicts every design -- the specification admits several behaviours
    #: here and this rejects all of them, so it rejects the correct one.
    everywhere = {"0": False, "1": False, "2": False}
    #: Spares one. That is a separation, which is what the suite is for.
    discriminates = {"0": False, "1": False, "2": True}
    refuted = variety.refuted_by_the_population(
        {"blunderbuss": everywhere, "useful": discriminates})
    assert refuted == ("blunderbuss",)
    why = O._refuted_everywhere(3)
    #: `over-strict:` because `_repair_issue` already routes that prefix to the
    #: relax-it instruction, which is the right ask for this defect.
    assert why.startswith("over-strict:")
    assert O._repair_issue("REQ-1", why).path.endswith(".over_strict")


def _rescue_env(monkeypatch, *, live, refuted):
    """Stub the two replay passes `_rescue_from_corpus` makes.

    `live` is the set of candidate keys that decide on the witness; `refuted`
    the set the population contradicts. Stubbed because both are whole-suite
    replays and this test is about the ADMISSION RULE, not about replay.
    """
    from specflow import oracles_stage as O

    def tables(flat, pop, *a, **k):
        if len(pop) > 1:
            return ({key: {"0": False} if key in refuted else {"0": True}
                     for key in flat}, {}, {})
        return ({key: {"0": True if key in live else None} for key in flat},
                {}, {})

    monkeypatch.setattr(O, "_population_tables", tables)
    monkeypatch.setattr(O.variety, "refuted_by_the_population",
                        lambda v, **k: tuple(u for u, per in v.items()
                                             if all(x is False for x in per.values())))


def test_a_discarded_requirement_is_rescued_by_its_OWN_corpus(monkeypatch):
    """A requirement was discarded whenever its LAST body failed, even when an
    earlier one passes every blocking rule -- so the stage threw away span it
    had already paid for. `_retain` has kept every superseded body since it
    landed, expressly so selection "has something to choose from".

    Measured on the probe run, offline, against its own witness and its own
    three designs: of 39 requirements lost while carrying an observable
    obligation, 11 have a body in their own corpus that decides and is not
    refuted. Span 71.1% -> 79.3% for zero model calls.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel.oracle_gen import RequirementOracle

    #: The standing body is filtered out before the candidates are keyed, so
    #: the surviving draft is #0 -- which is the point of the filter.
    _rescue_env(monkeypatch, live={"REQ-1#0"}, refuted=set())
    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="older",
                                     arm="generate", round_=0),
                        O.CorpusBody(req_uid="REQ-1", source="newest",
                                     arm="repair", round_=1)]}
    held = {"REQ-1": RequirementOracle(req_uid="REQ-1", tp_uids=["TP-1"],
                                       clause="c", source="newest")}
    got = O._rescue_from_corpus(
        corpus=corpus, held=held, blocked={"REQ-1"},
        reasons_for={"REQ-1": "over-strict: convicts every design"},
        witness="w", population=(), contract={}, stimulus_by_tp={},
        base="", transactional=False)
    assert set(got) == {"REQ-1"}, got
    assert got["REQ-1"].source == "older"
    #: It is keyed by the REQUIREMENT on the way out, never by the candidate id
    #: the two replay passes used.
    assert got["REQ-1"].req_uid == "REQ-1"


def test_the_rescue_replaces_a_BODY_and_never_overturns_a_VERDICT(monkeypatch):
    """The first draft of this re-admitted the standing body of every
    discarded requirement, which silently repealed the correspondence gate, the
    hollow-requirement route and the control-only rejection at once. Nine tests
    said so.

    Two restrictions make it true, and both are load-bearing.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel.oracle_gen import RequirementOracle

    _rescue_env(monkeypatch, live={"REQ-1#0", "REQ-1#1"}, refuted=set())
    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="only",
                                     arm="generate", round_=0)]}
    held = {"REQ-1": RequirementOracle(req_uid="REQ-1", tp_uids=["TP-1"],
                                       clause="c", source="only")}

    def rescue(why):
        return O._rescue_from_corpus(
            corpus=corpus, held=held, blocked={"REQ-1"},
            reasons_for={"REQ-1": why}, witness="w", population=(),
            contract={}, stimulus_by_tp={}, base="", transactional=False)

    #: 1. THE SAME BODY IS NOT A RESCUE. Re-admitting the very body that was
    #:    rejected is ignoring the verdict: these tests are a SUBSET of the
    #:    rules that produced it, so it would pass by construction.
    assert rescue("over-strict: convicts every design") == {}

    #: 2. ONLY A GROUND THESE TESTS ARE THE INSTRUMENT FOR. A faithfulness
    #:    label accuses the REQUIREMENT, and demoting it is
    #:    `demote_faithfulness`'s decision, not this function's.
    corpus["REQ-1"].insert(0, O.CorpusBody(req_uid="REQ-1", source="older",
                                           arm="generate", round_=0))
    assert set(rescue("over-strict: convicts every design")) == {"REQ-1"}
    for terminal in ("off-target: does not test the requirement",
                     "not-assertable: the requirement states no obligation",
                     "vacuous: this check cannot fail",
                     "malformed: no normalized form"):
        assert rescue(terminal) == {}, terminal


def test_the_population_is_a_PREFERENCE_in_the_rescue_and_not_a_VETO(monkeypatch):
    """No spec-derived design is guaranteed correct, so none of them may cost a
    requirement its check -- and seven cannot either.

    Choosing BETWEEN bodies on their say-so is a different act from discarding
    one: nothing is lost, so a golden-free preference is free. A refuted body
    is therefore taken when it is the only one that decides, and passed over
    when another candidate decides too.

    Deciding nothing is still disqualifying, and that is not the population's
    judgement -- a check that returns no verdict anywhere is vacuous whatever
    any design does.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel.oracle_gen import RequirementOracle

    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="older",
                                     arm="generate", round_=0),
                        O.CorpusBody(req_uid="REQ-1", source="newest",
                                     arm="repair", round_=1)]}
    held = {"REQ-1": RequirementOracle(req_uid="REQ-1", tp_uids=["TP-1"],
                                       clause="c", source="newest")}

    def rescue():
        return O._rescue_from_corpus(
            corpus=corpus, held=held, blocked={"REQ-1"},
            reasons_for={"REQ-1": "over-strict: convicts every design"},
            witness="w", population=("a", "b"), contract={},
            stimulus_by_tp={}, base="", transactional=False)

    #: THE ONLY CANDIDATE THAT DECIDES, AND THE POPULATION REFUTES IT. Taken:
    #: losing the requirement on seven same-author readings is the authority
    #: the witness gate was deleted for, at a larger N.
    _rescue_env(monkeypatch, live={"REQ-1#0"}, refuted={"REQ-1#0"})
    got = rescue()
    assert set(got) == {"REQ-1"}, got
    assert got["REQ-1"].source == "older"

    #: A candidate that decides nothing is still not a rescue, and that is not
    #: the population's judgement about it.
    _rescue_env(monkeypatch, live=set(), refuted=set())
    assert rescue() == {}, "a candidate that decides nothing is not a rescue"


def test_the_author_is_told_its_check_runs_on_every_testpoint():
    """Nothing in the prompt said so, and the author reasonably assumed
    otherwise: it is handed a requirement and its testpoints and writes a check
    for that scenario. The harness then calls `decide` on every testpoint the
    stimulus drives.

    Measured, replaying each frozen check against all of them: 47 of 96 convict
    EVERY ONE of three independently written spec-derived designs, against 14
    when each was replayed only on the two testpoints its requirement named.
    The checks did not change; the places they were asked about did.

    A prompt-content pin, because the prompt is the only place this can be
    said and a deletion here is invisible in every behavioural test.
    """
    from specflow.refmodel.oracle_gen import SYSTEM

    assert "EVERY TESTPOINT IN THE SUITE" in SYSTEM
    #: The ask has to be about the WINDOW, not about the assertion. Weakening
    #: what a check asserts to stop it firing produces a check that cannot
    #: fail, which is discarded as vacuous -- over-strictness and vacuity as
    #: one defect with two signs.
    assert 'IT IS "FIRES IN THE WRONG' in SYSTEM
    assert "discarded as vacuous" in SYSTEM
    #: And it has to name the fields that carry the answer, or it is advice
    #: with nothing to act on.
    for field in ("aborts_on", "until", "sustains"):
        assert field in SYSTEM, field

    #: **AND THE OTHER SIGN, OR THE PARAGRAPH ABOVE IS AN INSTRUCTION TO GO
    #: INERT.** The run written to the scope paragraph alone came back with
    #: 86.1% of its (check, testpoint) decisions passing all seven designs and
    #: 76 of 104 checks never telling any two apart anywhere.
    assert "86.1%" in SYSTEM
    assert "the same answer whatever the design did" in SYSTEM
    assert "would this check\nreturn False?" in SYSTEM


def test_the_set_level_repair_budget_reaches_the_stage_from_the_pipeline():
    """`run_oracle_stage` has taken `repair_attempts` since it was written and
    `build_artifacts` never passed it, so every run used the default 2 -- the
    same class of defect as `demote_faithfulness` being built and not
    connected, and as `cell_budget` arriving at a leg nothing could see.

    A source-level pin: a call site inside `build_artifacts` has twice been
    deleted on this branch without failing a single behavioural test.
    """
    import inspect
    import re

    from specflow import integration

    assert "oracle_repair_attempts" in inspect.signature(
        integration.build_artifacts).parameters
    src = inspect.getsource(integration.build_artifacts)
    call = re.search(r"oracle_set = run_oracle_stage\((.*?)\n        \)", src,
                     re.S)
    assert call, "cannot find the run_oracle_stage call"
    assert "repair_attempts=oracle_repair_attempts" in call.group(1), call.group(1)


def test_the_over_strict_message_names_WHERE_it_fired_and_no_design():
    """The first version gave no location at all.

    An author told only "you convict all of them" has to guess which clause is
    wrong and which scenario made it wrong. The check runs on every testpoint
    the suite drives, so the commonest cause is a window that opened where the
    requirement does not govern rather than a detail pinned too tightly inside
    it -- and only the location distinguishes those two.

    What travels is a testpoint id and the scenario S2 wrote for it: this
    pipeline's own inputs, already in the author's prompt for its own
    testpoints. The population may only REFUTE; the witness is the one that may
    repair. No design's source, no design's values, no claim that any of them
    is correct -- the same discipline `CellBrief` enforces by its constructor.
    """
    from specflow import oracles_stage as O

    testplan = [{"uid": "TP-1", "stimulus": "Assert reset mid-WRITE."},
                {"uid": "TP-4", "stimulus": "Lose arbitration."}]
    #: THE INTERSECTION, not the union: a testpoint where only some readings
    #: were convicted is an ordinary disagreement.
    where = O._where_it_fired(
        {"0": frozenset({"TP-1", "TP-9"}), "1": frozenset({"TP-1", "TP-4"})},
        testplan)
    assert where == [("TP-1", "Assert reset mid-WRITE.")], where

    why = O._refuted_everywhere(7, where)
    assert why.startswith("over-strict:")
    assert "TP-1" in why and "Assert reset mid-WRITE." in why
    assert "not any design's behaviour" in why
    #: It has to say which of the two repairs to make, or the location is a
    #: fact with no instruction attached.
    assert "make the activation FALSE there" in why
    assert "aborts_on" in why

    #: And with no location it is the message it always was, not a stub.
    assert "IT FIRED" not in O._refuted_everywhere(7)
    assert O._refuted_everywhere(7, []).startswith("over-strict:")


def test_an_extra_draft_goes_to_the_CORPUS_and_never_to_held(tmp_path,
                                                             monkeypatch):
    """Fill the pool, then select.

    A second draft must not disturb the first one's standing -- it is there so
    `_rescue_from_corpus` has something to choose from when the first is
    refuted or never reached. Holding it instead would silently replace a check
    that passed with one nothing has verified.

    It is a COVERAGE lever and is not reported as a variety one: resampling one
    prompt returns 69% identical bodies among pairs where both are sound, and
    `effective_size` is what says whether a set gained anything.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    ALT = GOOD.replace("y did not follow a", "y differs from a")
    port = _Port([_reply(GOOD), _reply(ALT)])
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", run_dir=tmp_path,
        fanout=False, max_repairs=0, repair_attempts=0, extra_drafts=1)

    bodies = got.corpus.get("REQ-0001") or []
    arms = sorted(b.arm for b in bodies)
    assert "resample" in arms, arms
    #: THE FIRST DRAFT STILL HOLDS. The alternate is a candidate, not a
    #: replacement.
    assert len(got.trusted) == 1
    assert got.trusted[0].source == GOOD, (
        "the alternate draft displaced the verified body")
    #: Each draft gets its own stage name, or `run_stage` keys its record by
    #: stage and the second silently overwrites the first one's evidence.
    labels = [s for s in port.stages if "alt" in s]
    assert labels, port.stages


def test_a_cell_check_is_taken_when_it_SEPARATES_MORE(monkeypatch):
    """The old rule took one only when the standing body decided NOTHING --
    a rule about liveness in a leg whose entire subject is separation.

    Measured on the first run where the leg fired: 12 targets, 12 bodies
    authored, **6 adopted**, and the six were the requirements with no deciding
    body, so the leg could not touch the blindness it was aimed at. That run
    also says why it matters: every testpoint carrying a cell had a median of
    39 checks deciding on it and NOT ONE blind cell sat where no check decided.
    The set spoke everywhere and agreed everywhere.
    """
    from specflow import oracles_stage as O
    from specflow import variety as V
    from specflow.refmodel.oracle_gen import RequirementOracle

    cells = (V.Cell(testpoint="TP-1", port="p", left="0", right="1"),
             V.Cell(testpoint="TP-2", port="p", left="0", right="1"))

    #: The standing body decides on both testpoints and separates neither;
    #: the cell body separates TP-2.
    tables = {
        "REQ-1": {"TP-1": {"0": True, "1": True},
                  "TP-2": {"0": True, "1": True}},
        "REQ-1#cell": {"TP-2": {"0": True, "1": False}},
        "REQ-2": {"TP-1": {"0": True, "1": False}},
        "REQ-2#cell": {"TP-1": {"0": True, "1": True}},
    }

    def fake(flat, *a, **k):
        by_tp = {key: tables.get(key, {}) for key in flat}
        folded = {key: {d: (False if any(
            c.get(d) is False for c in t.values()) else True)
            for d in ("0", "1")} for key, t in by_tp.items()}
        return folded, by_tp, {}

    monkeypatch.setattr(O, "_population_tables", fake)

    def body(uid):
        return RequirementOracle(req_uid=uid, tp_uids=[], clause="c",
                                 source=f"# {uid}")

    held = {"REQ-1": body("REQ-1"), "REQ-2": body("REQ-2")}
    taken = O._adopt_cell_bodies(
        [body("REQ-1"), body("REQ-2")], held=held, population=("a", "b"),
        contract={}, stimulus_by_tp={}, cells=cells, base="",
        transactional=False)
    #: REQ-1's standing check separates nothing and the cell check separates
    #: one, so it is taken. REQ-2's separates one already and the cell check
    #: separates none, so it is not.
    assert taken == ["REQ-1"], taken
    assert held["REQ-1"].source == "# REQ-1"
    #: Span is untouched: one check before, one after, for both requirements.
    assert set(held) == {"REQ-1", "REQ-2"}


def test_a_refuted_cell_check_is_never_taken(monkeypatch):
    """Otherwise this leg becomes a way to buy blindness with over-strictness,
    which is how a blindness score was gamed here once before: a check
    convicting BOTH sides separates neither, and one convicting every reading
    has rejected the correct one too."""
    from specflow import oracles_stage as O
    from specflow import variety as V
    from specflow.refmodel.oracle_gen import RequirementOracle

    cells = (V.Cell(testpoint="TP-1", port="p", left="0", right="1"),)
    #: It separates TP-1 -- and convicts every design somewhere, so it is
    #: refuted and must not be taken however much it separates.
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": False, "1": False} for k2 in flat},
        {k2: {"TP-1": {"0": True, "1": False}} for k2 in flat}, {}))

    held = {}
    taken = O._adopt_cell_bodies(
        [RequirementOracle(req_uid="REQ-1", tp_uids=[], clause="c", source="x")],
        held=held, population=("a", "b"), contract={}, stimulus_by_tp={},
        cells=cells, base="", transactional=False)
    assert taken == [], taken
    assert held == {}


def test_a_check_that_tells_no_two_readings_apart_is_ADVISED(monkeypatch):
    """The dual of the refutation leg, and the sign this stage had no
    instrument for.

    Measured on the run that motivated it: of 13,019 (check, testpoint)
    decisions, **86.1% decided all seven designs and convicted none**, only
    3.1% were mixed, and **76 of 104 checks never told any two readings apart
    anywhere** -- with blindness at 55.1% and not one blind cell at a testpoint
    no check reached. The set spoke everywhere and agreed everywhere.
    """
    from specflow import oracles_stage as O
    from specflow import variety as V
    from specflow.refmodel.oracle_gen import RequirementOracle

    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: (
        V.Cell(testpoint="TP-1", port="p", left="0", right="1"),
        V.Cell(testpoint="TP-1", port="q", left="0", right="1"),
    ))
    held = {u: RequirementOracle(req_uid=u, tp_uids=[], clause="c", source="x")
            for u in ("REQ-1", "REQ-2", "REQ-3", "REQ-4")}
    by_tp = {
        #: decided both, same verdict, on a port it observes -> INERT
        "REQ-1": {"TP-1": {"0": True, "1": True}},
        #: decided both and SEPARATED them -> not inert
        "REQ-2": {"TP-1": {"0": True, "1": False}},
        #: abstained on one -> says nothing about the design
        "REQ-3": {"TP-1": {"0": True}},
        #: same verdict, but on a port its requirement does not observe
        "REQ-4": {"TP-1": {"0": True, "1": True}},
    }
    normalized = {"REQ-1": {"observable": ["p"]}, "REQ-2": {"observable": ["p"]},
                  "REQ-3": {"observable": ["p"]}, "REQ-4": {"observable": ["z"]}}
    got = O._inert_where_it_should_decide(
        held, by_tp, {"io": [{"name": "p", "dir": "output"}]}, {}, normalized,
        population=("a", "b"), base="", transactional=False)
    assert set(got) == {"REQ-1"}, got
    assert "TP-1 on `p`" in got["REQ-1"]
    assert "same verdict for both" in got["REQ-1"]


def test_the_inert_note_asks_for_a_STRONGER_assertion_not_a_wider_window():
    """The two signs pull in opposite directions and the message has to say
    which one it wants. `_advisory` asks the author to ACCEPT a second
    implementation -- pressure toward relaxation, measured at over-strictness
    27 -> 15 with convictions 2 -> 16 -- so it is not sent alongside this."""
    from specflow import oracles_stage as O

    issues = O._witness_note("REQ-1", {"inert": "at TP-1 on `p` ...",
                                       "witness": "failed at edge 3"})
    assert len(issues) == 1, [i.path for i in issues]
    text = issues[0].message
    assert issues[0].path.endswith(".decides_nothing_apart")
    assert "at full strength" in text
    assert "Do not widen the window" in text
    #: And it offers the one answer that is not a weakening: the specification
    #: may simply not constrain that port there.
    assert "finding about the specification" in text
    assert issues[0].severity == "warning", "advisory, never blocking"


def test_choosing_a_BODY_costs_no_span_where_dropping_a_CHECK_does(monkeypatch):
    """`select` drops CHECKS, and a requirement whose only check it drops loses
    its span -- `placement` at its recorded threshold takes span to 69.0%.

    `_retain` keeps every superseded body, so the same golden-free scores can
    choose BETWEEN a requirement's bodies instead. No spec-derived design is
    guaranteed correct, so none of them may cost a requirement its check -- but
    they may say which of several checks to prefer.

    Measured on one run's 510 bodies over 130 requirements, choosing on span
    and blindness alone: the frozen set 86.9% span / 21.4% blind, best
    placement per requirement 97.7% / 11.4%, this rule 97.7% / **4.9%**.
    """
    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    cells = (V.Cell(testpoint="TP-1", port="p", left="0", right="1"),
             V.Cell(testpoint="TP-2", port="p", left="0", right="1"))
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: cells)
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())

    #: #0 separates nothing; #1 separates TP-1 and sits inside the guard.
    tables = {"REQ-1#0": {"TP-1": {"0": True, "1": True}},
              "REQ-1#1": {"TP-1": {"0": True, "1": False}}}
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": True} for k2 in flat},
        {k2: tables.get(k2, {}) for k2 in flat}, {k2: {} for k2 in flat}))
    monkeypatch.setattr(P, "tells", lambda *a, **k: type(
        "T", (), {"dissent_weighted": 0.0, "placement": 0.0})())

    held = {"REQ-1": O.RequirementOracle(req_uid="REQ-1", tp_uids=["TP-1"],
                                         clause="c", source="zero")}
    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="zero",
                                     arm="generate", round_=0),
                        O.CorpusBody(req_uid="REQ-1", source="one",
                                     arm="resample", round_=0)]}
    got = O._choose_bodies(
        corpus=corpus, held=held, population=("a", "b"), contract={
            "io": [{"name": "p", "dir": "output"}]},
        stimulus_by_tp={}, base="", transactional=False)
    assert set(got) == {"REQ-1"}, got
    assert got["REQ-1"].source == "one", "the separating body was not chosen"
    #: It is the REQUIREMENT's uid on the way out, never the candidate key the
    #: scoring pass used.
    assert got["REQ-1"].req_uid == "REQ-1"


def test_the_dissent_guard_is_a_PREFERENCE_and_never_loses_a_requirement(
        monkeypatch):
    """A requirement whose bodies are ALL outside the guard still freezes one.
    Convicting the population's centre is a reason to prefer another body, not
    a reason to have none -- seven same-author readings may not contain the
    correct design, and on one run they demonstrably did not."""
    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: (
        V.Cell(testpoint="TP-1", port="p", left="0", right="1"),))
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": True} for k2 in flat},
        {k2: {"TP-1": {"0": True, "1": False}} for k2 in flat},
        {k2: {} for k2 in flat}))
    #: EVERY body is far outside the guard.
    monkeypatch.setattr(P, "tells", lambda *a, **k: type(
        "T", (), {"dissent_weighted": 99.0, "placement": 0.0})())

    held = {"REQ-1": O.RequirementOracle(req_uid="REQ-1", tp_uids=[],
                                         clause="c", source="old")}
    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="new",
                                     arm="generate", round_=0)]}
    got = O._choose_bodies(
        corpus=corpus, held=held, population=("a", "b"),
        contract={"io": [{"name": "p", "dir": "output"}]},
        stimulus_by_tp={}, base="", transactional=False,
        max_dissent_weighted=2.0)
    assert set(got) == {"REQ-1"}, "the requirement lost its check to the guard"
    assert got["REQ-1"].source == "new"


def test_a_tie_between_two_bodies_breaks_the_SAME_WAY_EVERY_RUN(monkeypatch):
    """Ties are broken by whichever body is seen first, and iterating a SET
    breaks them on string hash order -- which Python randomises per process.

    Measured before this: the same configuration on the same artifact gave
    14.7% blindness with audit 0 of 22 on one run and 13.8% with audit 1 of 21
    on the next. Nothing had changed but the process. A selection rule that
    does not hold still cannot be reported, which is the same property the
    witness and the population are held on disk for.
    """
    import inspect

    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: (
        V.Cell(testpoint="TP-1", port="p", left="0", right="1"),))
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())
    #: INDISTINGUISHABLE bodies: same verdicts, same separation, same tells.
    #: Exactly the case that decided REQ-0098 on a real run, where one of two
    #: identical-scoring bodies convicted the known-good control and the other
    #: did not.
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": True} for k2 in flat},
        {k2: {"TP-1": {"0": True, "1": True}} for k2 in flat},
        {k2: {} for k2 in flat}))
    monkeypatch.setattr(P, "tells", lambda *a, **k: type(
        "T", (), {"dissent_weighted": 0.0, "placement": 0.0})())

    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source=f"body{i}",
                                     arm="generate", round_=0)
                        for i in range(4)]}
    picks = {O._choose_bodies(
        corpus=corpus, held={}, population=("a", "b"),
        contract={"io": [{"name": "p", "dir": "output"}]},
        stimulus_by_tp={}, base="", transactional=False)["REQ-1"].source
        for _ in range(8)}
    assert picks == {"body0"}, picks

    #: And the source says so, because a single process cannot show the
    #: failure this pins -- hash randomisation differs BETWEEN processes.
    src = inspect.getsource(O._choose_bodies)
    assert "alive = sorted(" in src
    assert "for uid in sorted(corpus)" in src
    assert "order = sorted(" in src


def test_refutation_is_a_GUARD_over_how_much_and_not_over_whether(monkeypatch):
    """**SEPARATION FIRST, THEN THE GUARDS, THEN MORE SEPARATION** -- the same
    ordering, and the same place, the dissent guard was moved to.

    It was a TIER (`tier = spared or per_req[uid]`), so a refuted body lost to
    ANY body the population spares, whatever either separated -- blindness
    24.41% on the corpus where that bound hardest, against 9.23% here.

    And BELOW marginal separation is too far, which was tried: REQ-0001 then
    froze a body convicting all seven designs AND the control over a sibling
    the population spares. Four of its six corpus bodies convict all seven,
    separating 18242 / 15626 / 10711 / 5525 cells against the spared sibling's
    2601 -- the more over-strict the body, the more it "separates", because a
    refuted check closes cells BY convicting. A rule reading separation before
    refutation reads over-strictness as reach.

    Blindness decided the placement and audit is reported beside it, fixed in
    writing first -- `docs/evidence/e6/PREREGISTERED.md`.
    """
    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    cells = (V.Cell(testpoint="TP-1", port="p", left="0", right="1"),
             V.Cell(testpoint="TP-2", port="p", left="0", right="1"))
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: cells)
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())
    monkeypatch.setattr(P, "tells", lambda *a, **k: type(
        "T", (), {"dissent_weighted": 0.0, "placement": 0.0})())

    #: #0 convicts BOTH designs -- refuted -- and separates both cells.
    #: #1 spares them and separates one.
    folded = {"REQ-1#0": {"0": False, "1": False},
              "REQ-1#1": {"0": True, "1": False}}
    two = {"REQ-1#0": {"TP-1": {"0": True, "1": False},
                       "TP-2": {"0": False, "1": True}},
           "REQ-1#1": {"TP-1": {"0": True, "1": False}}}

    def _pick(tables):
        monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
            {k2: folded.get(k2, {}) for k2 in flat},
            {k2: tables.get(k2, {}) for k2 in flat}, {k2: {} for k2 in flat}))
        corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="refuted",
                                         arm="generate", round_=0),
                            O.CorpusBody(req_uid="REQ-1", source="spared",
                                         arm="repair", round_=1)]}
        return O._choose_bodies(
            corpus=corpus, held={}, population=("a", "b"),
            contract={"io": [{"name": "p", "dir": "output"}]},
            stimulus_by_tp={}, base="", transactional=False)["REQ-1"].source

    #: Both separate something, so the guard decides and the spared body wins
    #: even though the refuted one closes twice as many cells.
    assert _pick(two) == "spared", (
        "separating MORE beat the population convicting it outright")

    #: But the guard may not prefer a check that decides NOTHING. A spared body
    #: separating no cell loses to a refuted one that separates -- position one
    #: is `bool(closes - covered)` and no guard sits above it. A guard against
    #: over-strictness buying its safety with vacuity is the same defect
    #: wearing its other sign.
    inert = {"REQ-1#0": two["REQ-1#0"], "REQ-1#1": {}}
    assert _pick(inert) == "refuted", (
        "the guard preferred a body that tells no two readings apart")


def test_a_requirement_whose_bodies_are_ALL_refuted_still_freezes_one(
        monkeypatch):
    """A preference and never a rejection, for the reason the refutation leg
    itself is advisory: no spec-derived design is guaranteed correct, so seven
    of them may not cost a requirement its only check."""
    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: (
        V.Cell(testpoint="TP-1", port="p", left="0", right="1"),))
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())
    monkeypatch.setattr(P, "tells", lambda *a, **k: type(
        "T", (), {"dissent_weighted": 0.0, "placement": 0.0})())
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": False, "1": False} for k2 in flat},
        {k2: {"TP-1": {"0": True, "1": False}} for k2 in flat},
        {k2: {} for k2 in flat}))

    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="only",
                                     arm="generate", round_=0)]}
    got = O._choose_bodies(
        corpus=corpus, held={}, population=("a", "b"),
        contract={"io": [{"name": "p", "dir": "output"}]},
        stimulus_by_tp={}, base="", transactional=False)
    assert got["REQ-1"].source == "only", "the requirement lost its only check"


def test_the_population_leg_is_off_below_two_designs():
    """One design convicting a check is an ordinary disagreement, not the
    population contradicting it. The guard is in the stage, so this pins the
    source: a behavioural test cannot reach the round loop without a run.
    """
    import re
    from pathlib import Path

    from specflow import oracles_stage as O

    src = Path(O.__file__).read_text()
    assert re.search(r"if len\(population\) >= 2:", src), (
        "the population leg lost its minimum-size guard")
    body = src[src.index("if len(population) >= 2:"):][:4000]
    assert "variety.refuted_by_the_population" in body
    #: **AND IT DOES NOT REJECT.** No spec-derived design is guaranteed
    #: correct, so none of them may discard a check and seven cannot either --
    #: the pathology the witness gate was deleted for, at a larger N. It earns
    #: a repair round; `rejected` is for what this stage can establish
    #: mechanically without believing any implementation.
    assert "quotable[uid] = why" in body, "the refutation tells nobody"
    assert "rejected[uid] = quotable[uid] = why" not in body, (
        "the population discards a check again")


def test_the_population_reaches_the_stage_from_the_pipeline():
    """`build_artifacts` must forward it, or the filter is another lever built
    and not connected -- which is what happened to `demote_faithfulness`.
    """
    import inspect
    import re
    from pathlib import Path

    from specflow import integration as I

    assert "population_sources" in inspect.signature(I.build_artifacts).parameters
    src = Path(I.__file__).read_text()
    call = re.search(r"run_oracle_stage\((.{0,2000}?)\n        \)", src, re.DOTALL)
    assert call and "population=population_sources" in call.group(1), (
        "build_artifacts accepts a population and does not forward it")


def test_the_control_is_not_the_population():
    """`control_source` is a separate parameter and must stay separate: the
    filter's whole claim is that it reads no reference and no grade.
    """
    import inspect

    from specflow import oracles_stage as O

    sig = inspect.signature(O.run_oracle_stage)
    assert "control_source" in sig.parameters and "population" in sig.parameters
    assert sig.parameters["population"].default == ()


def test_the_stage_can_build_its_own_population(tmp_path, monkeypatch):
    """`population_size` asks the witness generator for k readings instead of
    one, and below two it is not a population.

    **THE GENERATOR HAS TO SUCCEED FOR THE GUARDS TO MEAN ANYTHING.** A first
    version of this test passed `port=None`, so every generation failed and
    the function returned `()` for the wrong reason -- both size guards
    survived mutation. The stub is what makes the assertions load-bearing.
    """
    import inspect

    from specflow import oracles_stage as O
    from specflow.refmodel import conform

    calls = []

    def _gen(*, requirements, contract_json, port, workdir):
        calls.append(workdir)
        return f"# design {len(calls)}\n", []

    monkeypatch.setattr(conform, "conforming_implementation", _gen)
    monkeypatch.setattr(O, "_ports_agree", lambda *_a, **_k: True)

    sig = inspect.signature(O.run_oracle_stage)
    assert sig.parameters["population_size"].default == 0

    kw = dict(requirements=[{"uid": "REQ-1", "text": "x"}],
              contract_json="{}", port=object(), run_dir=None)
    #: ONE READING IS NOT A POPULATION even when it is produced successfully --
    #: a single design contradicting a check is an ordinary disagreement.
    assert O._population(size=1, workdir=tmp_path / "a", **kw) == ()
    assert O._population(size=0, workdir=tmp_path / "b", **kw) == ()
    #: AND IT COSTS NOTHING TO SAY SO. The late "fewer than two produced" guard
    #: returns `()` for these sizes anyway, so the only thing the early guard
    #: buys is not paying for a generation whose result is discarded -- which
    #: is invisible unless the call count is what gets asserted.
    assert calls == [], "a sub-population size still bought model calls"
    #: Two is the minimum that means anything, and each member gets its own
    #: workdir so the cache returns independent readings.
    got = O._population(size=3, workdir=tmp_path / "c", **kw)
    assert len(got) == 3 and len(set(got)) == 3
    assert len({str(w) for w in calls[-3:]}) == 3


def test_a_partly_built_population_is_not_used(tmp_path, monkeypatch):
    """Three asked for, one produced: the leg goes off rather than refuting on
    a population of one.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel import conform

    n = {"i": 0}

    def _flaky(*, requirements, contract_json, port, workdir):
        n["i"] += 1
        return ("# only the first\n", []) if n["i"] == 1 else ("", [])

    monkeypatch.setattr(conform, "conforming_implementation", _flaky)
    monkeypatch.setattr(O, "_ports_agree", lambda *_a, **_k: True)
    assert O._population(
        size=3, requirements=[{"uid": "REQ-1", "text": "x"}],
        contract_json="{}", port=object(), workdir=tmp_path,
        run_dir=None) == ()


def test_a_population_that_cannot_be_built_leaves_the_leg_off():
    """Never raises. A missing population weakens the stage exactly as a
    missing witness does -- it does not fail the run.
    """
    from specflow import oracles_stage as O

    #: `port=None` makes every generation attempt fail; two are requested and
    #: none arrives, so the leg reports off rather than propagating.
    assert O._population(
        size=3, requirements=[{"uid": "REQ-1", "text": "x"}],
        contract_json="{}", port=None, workdir=Path("/tmp"),
        run_dir=None) == ()


def test_the_population_size_reaches_the_stage_from_the_pipeline():
    import inspect
    import re
    from pathlib import Path as P

    from specflow import integration as I

    assert "population_size" in inspect.signature(I.build_artifacts).parameters
    src = P(I.__file__).read_text()
    call = re.search(r"run_oracle_stage\((.{0,2200}?)\n        \)", src, re.DOTALL)
    assert call and "population_size=population_size" in call.group(1)


def test_a_cell_brief_cannot_carry_a_design():
    """The structural guarantee, not an instruction not to look.

    `build_prompt` refuses the design under test by SIGNATURE. A `str` gap
    parameter would have given that back, so the gap is typed and can only be
    built from a `variety.Cell` through `variety.brief` -- whose parameters are
    a cell, a requirement, an activation and the driven inputs.
    """
    import pytest

    from specflow.refmodel.oracle_gen import CellBrief
    from specflow.variety import Cell

    cell = Cell(testpoint="TP-1", port="busy", left="zulufox", right="quebecvane")
    b = CellBrief.at(cell, requirement="busy falls on completion",
                     activation="a WRITE completes", driven={"ena": 1})
    assert "busy" in b.text and "TP-1" in b.text
    #: THE DESIGN NAMES ARE NEVER RENDERED, so the author cannot even tell
    #: which readings came apart, let alone what either of them did.
    assert "zulufox" not in b.text and "quebecvane" not in b.text
    #: And nothing else may pose as a gap.
    with pytest.raises(ValueError, match="disagreement CELL"):
        CellBrief(text="the reference returns 0 here", origin="golden")


def test_the_gap_reaches_the_authoring_prompt():
    """A brief that is built and not rendered is the whole lever doing
    nothing, which is exactly how `demote_faithfulness` sat unused.
    """
    from specflow.refmodel.oracle_gen import CellBrief, build_prompt
    from specflow.variety import Cell

    cell = Cell(testpoint="TP-9", port="scl_oen", left="a", right="b")
    gap = CellBrief.at(cell, requirement="hold scl low",
                       activation="during a transfer", driven={})
    req = {"uid": "REQ-1", "text": "hold scl low"}
    with_gap = build_prompt(requirement=req, contract_json="{}", contract={},
                            gap=gap)
    without = build_prompt(requirement=req, contract_json="{}", contract={})
    assert "scl_oen" in with_gap and "TP-9" in with_gap
    #: DISCRIMINATE ON THE TESTPOINT, not the port: the system prompt carries
    #: `scl_oen` in a worked example of its own, so a port name proves nothing
    #: about whether the gap was rendered.
    assert "TP-9" not in without
    assert gap.text in with_gap


def test_cell_authoring_is_off_without_a_population(monkeypatch):
    """A cell is a place two spec-derived designs come apart. One design, or
    none, has no cells -- and the leg must not do the REPLAY WORK finding that
    out, which is the only thing the early guard buys.

    Downstream guards return `[]` for these inputs anyway, so asserting on the
    return value alone leaves the early one untested -- the same trap the
    population size guard had.
    """
    import inspect

    from specflow import oracles_stage as O

    assert inspect.signature(
        O.run_oracle_stage).parameters["cell_budget"].default == 0

    replays = []
    monkeypatch.setattr(O, "_population_rows",
                        lambda *a, **k: replays.append(1) or {})
    kw = dict(held={}, stimulus_by_tp={}, testplan=[], by_uid={},
              normalized=None, budget=5, base="", transactional=True)
    #: **THE REAL CONTRACT SHAPE.** Ports live under `io` with a `dir`. The
    #: first version of this test invented `{"outputs": [...]}`, which no
    #: contract has -- so it agreed with the bug it was meant to catch and the
    #: lever returned [] on a full pipeline run without a word.
    real = {"io": [{"name": "p", "dir": "output", "width": 1},
                   {"name": "clk", "dir": "input", "width": 1}]}
    #: One design is not a population.
    assert O._cell_targets(population=("only one",), contract=real, **kw)[0] == []
    #: No declared OUTPUT means no port a cell could sit on -- inputs do not
    #: count, which is the half `dir` filtering carries.
    assert O._cell_targets(
        population=("a", "b"),
        contract={"io": [{"name": "clk", "dir": "input"}]}, **kw)[0] == []
    assert replays == [], "the leg replayed the population before checking it"


def test_cell_targets_reads_the_contract_the_pipeline_actually_writes():
    """Pinned against a REAL contract from a run, not one this test invented.

    The lever spent a full pipeline run doing nothing because it read
    `contract["outputs"]`; every other reader in the tree filters `io` on
    `dir == "output"`. A shape-invented test cannot catch that, so this one
    loads an artifact.
    """
    import json
    from pathlib import Path as P

    from specflow import oracles_stage as O

    contract = json.loads(
        P("docs/evidence/e3_contract.json").read_text(encoding="utf-8"))
    assert "outputs" not in contract, (
        "if a contract ever grows an `outputs` key, revisit the accessor")
    ports = [str(p.get("name")) for p in contract["io"]
             if p.get("dir") == "output" and p.get("name")]
    assert len(ports) >= 4, ports
    #: With real ports and a real population the leg gets as far as replaying,
    #: which is the step the empty-outputs bug skipped entirely.
    reached = []
    import unittest.mock as mock
    with mock.patch.object(O, "_population_rows",
                           side_effect=lambda *a, **k: reached.append(1) or {}):
        O._cell_targets(population=("a", "b"), held={}, contract=contract,
                        stimulus_by_tp={}, testplan=[], by_uid={},
                        normalized=None, budget=5, base="", transactional=True)
    assert reached == [1], "the leg gave up before replaying a real contract"


def test_the_cell_budget_reaches_the_stage_from_the_pipeline():
    import inspect
    import re
    from pathlib import Path as P

    from specflow import integration as I

    assert "cell_budget" in inspect.signature(I.build_artifacts).parameters
    src = P(I.__file__).read_text()
    call = re.search(r"run_oracle_stage\((.{0,2400}?)\n        \)", src, re.DOTALL)
    assert call and "cell_budget=cell_budget" in call.group(1)


def _cellrows(port_vals):
    """Two designs disagreeing on the named ports at the named testpoints."""
    a, b = {}, {}
    for tp, ports in port_vals.items():
        a[tp] = [{"inputs": {}, "outputs": {p: 0 for p in ports}}]
        b[tp] = [{"inputs": {}, "outputs": {p: 1 for p in ports}}]
    return {"alpha": a, "bravo": b}


def test_one_cell_target_per_requirement(monkeypatch):
    """A `RequirementOracle` is keyed by `req_uid`, so two checks authored for
    one requirement cannot both be held -- the second overwrites the first.

    Measured before this held: twelve targets landed on three requirements,
    nine of them on one, and at most one of those nine could survive. Twelve
    calls for a yield that was near zero by construction.
    """
    from specflow import oracles_stage as O

    rows = _cellrows({"TP-1": ["p", "q"], "TP-2": ["p", "q"]})
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: rows)
    monkeypatch.setattr(O, "_population_verdicts_by_tp",
                        lambda *a, **k: {})
    contract = {"io": [{"name": "p", "dir": "output"},
                       {"name": "q", "dir": "output"}]}
    #: BOTH testpoints cover the SAME requirement.
    testplan = [{"uid": "TP-1", "covers": ["REQ-1@1"]},
                {"uid": "TP-2", "covers": ["REQ-1@1"]}]
    got, _cells = O._cell_targets(
        population=("a", "b"), held={}, contract=contract,
        stimulus_by_tp={"TP-1": [{}], "TP-2": [{}]}, testplan=testplan,
        by_uid={"REQ-1": {"uid": "REQ-1", "text": "t"}}, normalized=None,
        budget=8, base="", transactional=True)
    assert len(got) == 1, [t["cell"] for t in got]
    assert got[0]["requirement"]["uid"] == "REQ-1"


def test_the_cell_budget_spreads_across_ports(monkeypatch):
    """`ranked` collapses cells to `(port, count)`, so ranking by that weight
    alone poured a whole budget into one port -- `sda_oen`, twelve of twelve --
    which is the opposite of a variety lever.
    """
    from specflow import oracles_stage as O

    #: `p` disagrees at three testpoints, `q` at one. Weight says p first.
    rows = _cellrows({"TP-1": ["p"], "TP-2": ["p"], "TP-3": ["p"],
                      "TP-4": ["q"]})
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: rows)
    monkeypatch.setattr(O, "_population_verdicts_by_tp",
                        lambda *a, **k: {})
    contract = {"io": [{"name": "p", "dir": "output"},
                       {"name": "q", "dir": "output"}]}
    testplan = [{"uid": f"TP-{i}", "covers": [f"REQ-{i}@1"]} for i in range(1, 5)]
    by_uid = {f"REQ-{i}": {"uid": f"REQ-{i}", "text": "t"} for i in range(1, 5)}
    got, _cells = O._cell_targets(
        population=("a", "b"), held={}, contract=contract,
        stimulus_by_tp={f"TP-{i}": [{}] for i in range(1, 5)},
        testplan=testplan, by_uid=by_uid, normalized=None,
        budget=2, base="", transactional=True)
    ports = [t["cell"].port for t in got]
    assert len(got) == 2
    #: THE LIGHTER PORT IS REACHED BEFORE THE HEAVIER ONE IS EXHAUSTED. A
    #: budget of two with `p` carrying three cells must not be two `p`s.
    assert set(ports) == {"p", "q"}, ports


def test_a_cell_is_blind_until_a_check_separates_it_AT_THAT_TESTPOINT(monkeypatch):
    """One separation anywhere used to close every cell of the pair.

    `_cell_targets` fed `variety.blind` the table `_population_verdicts`
    returns, which is one bool per `(check, design)` with the testpoints folded
    away. `separates` then read `cell.left`/`cell.right` and nothing else, so a
    check that told two designs apart at ONE testpoint scored as adjudicating
    that pair's cells at EVERY testpoint.

    Measured on the first probe-bearing run: 151 checks, three designs, 3,530
    cells, 14 separations in total -- and blindness read **0.0%**. The cell leg
    ran with a budget of 12, found nothing to author at, and authored nothing.
    At `(testpoint, pair)` resolution the same set and the same replays read
    **97.0%**.
    """
    from specflow import oracles_stage as O

    rows = _cellrows({"TP-1": ["p"], "TP-2": ["p"]})
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: rows)
    #: ONE check, separating the pair at TP-1 and abstaining at TP-2.
    monkeypatch.setattr(
        O, "_population_verdicts_by_tp",
        lambda *a, **k: {"REQ-1": {"TP-1": {"alpha": True, "bravo": False}}})
    contract = {"io": [{"name": "p", "dir": "output"}]}
    testplan = [{"uid": "TP-1", "covers": ["REQ-1@1"]},
                {"uid": "TP-2", "covers": ["REQ-2@1"]}]
    got, _cells = O._cell_targets(
        population=("a", "b"), held={}, contract=contract,
        stimulus_by_tp={"TP-1": [{}], "TP-2": [{}]}, testplan=testplan,
        by_uid={"REQ-1": {"uid": "REQ-1", "text": "t"},
                "REQ-2": {"uid": "REQ-2", "text": "t"}},
        normalized=None, budget=8, base="", transactional=True)
    at = [t["cell"].testpoint for t in got]
    #: TP-2 IS STILL BLIND. Collapsing to the pair returns no target at all.
    assert at == ["TP-2"], at


def test_the_per_testpoint_table_keeps_one_column_per_replay():
    """`_population_verdicts_by_tp` is the same replays, not collapsed.

    A testpoint with no stimulus, and a verdict that is broken or `None`, leave
    the entry OUT rather than recording a false one -- an absent entry
    separates nothing, which is the rule `separates` already applies to an
    abstention.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel.oracle_gen import RequirementOracle

    seen = []

    class _R:
        def __init__(self, ok):
            self.ok, self.broken = ok, False

    def fake_decide(oracle, rows, **_kw):
        seen.append(rows)
        #: design "0" says True, design "1" abstains.
        return _R(True if rows == ["0"] else None)

    monkeypatch_rows = {"0": ["0"], "1": ["1"]}
    O_replay = O.replay
    try:
        O.replay = lambda src, contract, steps, base="": type(
            "Rep", (), {"rows": monkeypatch_rows[src], "unavailable": ()})()
        O_decide = O.decide
        O.decide = fake_decide
        held = {"REQ-1": RequirementOracle(
            req_uid="REQ-1", tp_uids=["TP-1", "TP-NOSTIM"], clause="c",
            source="def decide(trace):\n    return (None, None, '')")}
        got = O._population_verdicts_by_tp(
            held, ("0", "1"), {}, {"TP-1": [{}]}, base="", transactional=False)
    finally:
        O.replay = O_replay
        O.decide = O_decide
    #: The testpoint with no stimulus is absent, not present-and-empty.
    assert got == {"REQ-1": {"TP-1": {"0": True}}}, got


def test_a_check_is_replayed_where_the_STIMULUS_goes_not_where_the_testplan_points(
        monkeypatch):
    """`oracle.tp_uids` had a median of **2 of 499** on the probe run.

    A cell at TP-0400 can only be separated by a check replayed at TP-0400, so
    a suite whose checks are each pinned to two testpoints is blind almost
    everywhere by construction. The check already says for itself where it
    applies -- `decide` returns None when the clause's scenario never occurred
    -- so `tp_uids` was a second, cruder gate on top of that one.

    Measured on the run's own three designs and 3,530 cells, at
    `(testpoint, pair)` resolution: TRUSTED 96 goes 96.9% -> 22.3% blind, and
    all 151 first drafts 97.0% -> 12.8%.
    """
    from specflow import oracles_stage as O
    from specflow.refmodel.oracle_gen import RequirementOracle

    rows = {"0": {"TP-1": ["a"], "TP-2": ["b"]},
            "1": {"TP-1": ["a"], "TP-2": ["b"]}}
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: rows)
    monkeypatch.setattr(O, "_population_unavailable", lambda *a, **k: {})

    class _V:
        def __init__(self, ok):
            self.ok, self.broken = ok, False

    #: True at TP-1 on both designs; separates them at TP-2.
    monkeypatch.setattr(O, "decide", lambda o, r, **k: _V(
        True if r == ["a"] else (r == ["b"] and o.req_uid == "REQ-1")))

    held = {"REQ-1": RequirementOracle(
        req_uid="REQ-1", tp_uids=["TP-1"], clause="c", source="s")}
    _v, by_tp, obj = O._population_tables(
        held, ("x", "y"), {}, {"TP-1": [{}], "TP-2": [{}]},
        base="", transactional=False)
    #: TP-2 IS IN THE TABLE, and the check never named it.
    assert sorted(by_tp["REQ-1"]) == ["TP-1", "TP-2"], by_tp
    #: `placement` needs WHERE it objected, and TP-2 is where.
    assert obj["REQ-1"]["0"] == frozenset(), obj
    #: A testpoint with no stimulus is not in scope at all.
    assert O._population_scope({"TP-1": [{}], "TP-3": []}, None) == ["TP-1"]


def test_one_set_of_replays_feeds_all_three_population_instruments(monkeypatch):
    """Refutation, cell blindness and `placement` want three shapes of the same
    evidence. Replaying the population once per instrument was 3 x 499 replays
    each; with the scope widened that is the difference between a stage that
    finishes a round and one that does not."""
    from specflow import oracles_stage as O

    calls = []
    monkeypatch.setattr(O, "_population_rows",
                        lambda *a, **k: calls.append(1) or {})
    monkeypatch.setattr(O, "_population_unavailable", lambda *a, **k: {})
    O._population_tables({}, (), {}, {}, base="", transactional=False)
    assert calls == [1], f"{len(calls)} replay passes for one table build"

    #: And each public shape is ONE build, not one per value it returns.
    for fn in (O._population_verdicts, O._population_verdicts_by_tp,
               O._population_objections):
        calls.clear()
        fn({}, (), {}, {}, base="", transactional=False)
        assert calls == [1], f"{fn.__name__}: {len(calls)} replay passes"


def test_the_selected_set_is_what_gets_frozen():
    """`population` was imported by `scoring` and by no pipeline module, so
    every selection figure on this branch was post-hoc. A run must be able to
    freeze the SELECTED set.
    """
    import inspect
    import re
    from pathlib import Path as Pth

    from specflow import integration as I
    from specflow import oracles_stage as O

    assert "selection" in inspect.signature(O.run_oracle_stage).parameters
    assert "selection" in inspect.signature(I.build_artifacts).parameters
    src = Pth(I.__file__).read_text()
    call = re.search(r"run_oracle_stage\((.{0,2600}?)\n        \)", src, re.DOTALL)
    assert call and "selection=selection" in call.group(1)
    #: SOURCE-LEVEL, because the apply site sits in the round loop's tail and a
    #: behavioural test cannot reach it without a full run -- the same reason
    #: the demotion forward needed one.
    stage = Pth(O.__file__).read_text()
    body = stage[stage.index("selection_dropped: dict[str, str] = {}"):][:1400]
    assert "_select_frozen(" in body
    assert "trusted = [o for o in trusted if o.req_uid in kept]" in body, (
        "the selected set is computed and not frozen")


def test_selection_scores_per_testpoint_not_on_a_concatenated_trace():
    """The correction that makes wiring `select` honest.

    `select` drives a check over a population member's rows. Flattening a
    design's testpoints into one trace changes verdicts wholesale -- measured,
    per-testpoint and concatenated scoring agreed on ONE check of 16 and 27 at
    t=0. So each member is passed as a MARKER row and the closure returns the
    verdict already computed on the testpoints the check names.
    """
    import re
    from pathlib import Path as Pth

    from specflow import oracles_stage as O

    src = Pth(O.__file__).read_text()
    body = src[src.index("def _select_frozen("):]
    body = body[:body.index("def _refuted_everywhere")]
    assert '{"__design__": d}' in body, "members are no longer markers"
    assert re.search(r"verdicts\.get\(uid, \{\}\)\.get\(d\)", body), (
        "the closure re-decides instead of using the per-testpoint verdict")


def test_a_selection_refusal_is_recorded_not_silently_skipped():
    """`Ruleset.min_population` is 5, so a three-design run is refused BY
    DESIGN. That has to read as "the rule declined", never as "the rule found
    nothing to drop" -- the `VACUOUS: 0` against `VACUOUS: None` problem one
    level over.
    """
    from pathlib import Path as Pth

    from specflow import oracles_stage as O

    assert "selection_ran" in O.OracleSet.__dataclass_fields__
    assert O.OracleSet.__dataclass_fields__["selection_ran"].default is False
    src = Pth(O.__file__).read_text()
    body = src[src.index("def _select_frozen("):]
    body = body[:body.index("def _refuted_everywhere")]
    assert "except ValueError as exc" in body and "REFUSED" in body


def test_the_selection_record_survives_a_reuse():
    """THE LOSSY-LOAD TRAP, which has cost this stage two fields already.

    A key written at freeze and not read in `load` is absent from every
    `--reuse`, so a reused run would report a set that HAD been selected as one
    that never was.
    """
    import re
    from pathlib import Path as Pth

    from specflow import oracles_stage as O

    src = Pth(O.__file__).read_text()
    loader = src[src.index("def load(run_dir: Path)"):]
    for key in ("selection_dropped", "selection_ran"):
        assert re.search(rf'blob\.get\("{key}"\)', loader), (
            f"`{key}` is frozen but never read back")


def test_an_abandonment_says_which_staging_failure_it_was():
    """"never reached in N attempts" charged every loss to the stimulus loop.

    `_diagnose` already separates four failures and the stage was discarding
    that at the one place a reader counts losses by stage. Measured on a full
    run: of 30 requirements abandoned here, 17 had their activation DRIVEN and
    the check still saw nothing, 8 were `route_never_moved` -- which
    `_diagnose` itself calls a finding against normalisation -- and only 5 were
    the pacing failure this loop can act on.
    """
    from pathlib import Path as Pth

    from specflow import oracles_stage as O

    #: The four diagnoses are distinct strings, so an abandonment carrying one
    #: is attributable without re-reading the evidence.
    assert O._diagnose({"activation": "not_fired"}) != O._diagnose({"inert": True})
    #: The RETURNED text, not the docstring: "normalisation" is the
    #: docstring's word for it and the string a reader sees says
    #: "the observation route is what is wrong, not the stimulus".
    assert "not the stimulus" in O._diagnose({"route_never_moved": True})

    src = Pth(O.__file__).read_text()
    site = src[src.index('abandoned[uid] = (f"never reached'):][:300]
    assert "_diagnose" in src[src.index("ATTEMPTED AND EXHAUSTED"):
                              src.index("ATTEMPTED AND EXHAUSTED") + 2000], (
        "the abandonment no longer names the failure")
    assert "said" in site


def test_the_staging_budget_is_not_cut_short_by_a_normalisation_diagnosis():
    """The tempting fix, refuted by the same run that motivated it.

    `_diagnose` says `route_never_moved` is "NOT a reason to spend another
    attempt on the stimulus". Measured: of 27 requirements that hit it at some
    attempt, **3 were reached at a later one**. Exiting early would have saved
    44 attempts and lost those 3, so the budget is deliberately unchanged and
    only the attribution moved.
    """
    from pathlib import Path as Pth

    from specflow import oracles_stage as O

    src = Pth(O.__file__).read_text()
    loop = src[src.index("def stage_unexercised("):]
    loop = loop[:loop.index("\ndef ", 10)]
    #: No early exit keyed on the diagnosis inside the attempt loop.
    for bail in ("if evidence.get(\"route_never_moved\"): break",
                 "if _diagnose(evidence)", "route_never_moved:\n                break"):
        assert bail not in loop, f"an early exit crept in: {bail!r}"


def test_an_undecidable_activation_is_not_reported_as_a_driven_one():
    """**"COULD NOT BE DECIDED" IS NOT "WAS DRIVEN".**

    `_evidence` writes `activation` only when `check_static` returns a verdict,
    and `check_static` "Returns None when the obligation is not input-only, so
    a caller can tell 'this stimulus does not stage it' from 'this cannot be
    answered here'." `_diagnose` fell through on the absent key and asserted
    the first.

    Measured on a full run: all 17 requirements abandoned under that
    fallthrough had NO activation evidence, so every one was reported as "the
    activation was driven" on the strength of a key never written.
    """
    from specflow import oracles_stage as O

    #: Absent key -- state-dependent, nothing decided it.
    undecidable = O._diagnose({"edges": 12, "inert": False})
    assert "state-dependent" in undecidable
    assert "driven" not in undecidable, (
        "an undecided activation is being reported as a driven one")
    assert "probe" in undecidable

    #: Present and fired -- the check is the one at fault, and that is the
    #: case that belongs with its author rather than with the stimulus.
    driven = O._diagnose({"activation": "fired: a=7 at edge 3", "edges": 12})
    assert driven == "the activation was driven and the check still saw nothing"
    assert undecidable != driven

    #: The mechanically certain miss still outranks both.
    assert O._diagnose({"activation": "not_fired: a never reached 7"}) == (
        "a required input value was never driven")


def test_the_dissent_guard_never_prefers_a_check_that_SEPARATES_NOTHING(
        monkeypatch):
    """The guard was a TIER -- `inside or tier` -- so any body inside it beat
    any body outside it whatever either one decided. A body convicting NOBODY
    is as far inside as a body can get, so the guard against over-strictness
    selected for the other sign of the same defect.

    Measured on the end-to-end run: four requirements froze a body separating
    nothing over a sibling separating thousands of cells -- REQ-0001 at 0
    against 7863, REQ-0021 at 0 against 4749, REQ-0121 at 0 against 3612 -- and
    the run reported 14.6% blindness against a target of 10%. Re-choosing that
    same corpus with separation ahead of the guard: **9.2%**, with the
    threshold left exactly where it shipped.
    """
    from specflow import oracles_stage as O
    from specflow import population as P
    from specflow import variety as V

    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: {"0": {}, "1": {}})
    monkeypatch.setattr(V, "cells", lambda *a, **k: (
        V.Cell(testpoint="TP-1", port="p", left="0", right="1"),))
    monkeypatch.setattr(P, "characterise", lambda *a, **k: object())
    #: `inert` convicts nobody and separates nothing; `sharp` convicts three of
    #: seven, which is outside the guard, and separates the cell.
    tables = {"REQ-1#0": {"TP-1": {"0": True, "1": True}},
              "REQ-1#1": {"TP-1": {"0": True, "1": False}}}
    monkeypatch.setattr(O, "_population_tables", lambda flat, *a, **k: (
        {k2: {"0": True} for k2 in flat},
        {k2: tables.get(k2, {}) for k2 in flat}, {k2: {} for k2 in flat}))
    monkeypatch.setattr(P, "tells", lambda obj, *a, **k: type(
        "T", (), {"dissent_weighted": 0.0 if not obj else 3.4,
                  "placement": 0.0})())

    #: `tells` is handed the objections of the body being scored, so the inert
    #: one arrives with an empty map and the sharp one with a conviction.
    def tables2(flat, *a, **k):
        return ({k2: {"0": True} for k2 in flat},
                {k2: tables.get(k2, {}) for k2 in flat},
                {k2: ({} if k2.endswith("#0") else {"d1": ("TP-1",)})
                 for k2 in flat})
    monkeypatch.setattr(O, "_population_tables", tables2)

    held = {"REQ-1": O.RequirementOracle(req_uid="REQ-1", tp_uids=["TP-1"],
                                         clause="c", source="inert")}
    corpus = {"REQ-1": [O.CorpusBody(req_uid="REQ-1", source="inert",
                                     arm="generate", round_=0),
                        O.CorpusBody(req_uid="REQ-1", source="sharp",
                                     arm="resample", round_=0)]}
    got = O._choose_bodies(
        corpus=corpus, held=held, population=("a", "b"),
        contract={"io": [{"name": "p", "dir": "output"}]},
        stimulus_by_tp={}, base="", transactional=False,
        max_dissent_weighted=2.0)
    assert got.get("REQ-1") is not None, (
        "the inert body was kept: the guard still outranks separation")
    assert got["REQ-1"].source == "sharp", got["REQ-1"].source


def test_a_requirement_with_NO_OBSERVABLE_is_never_staged(monkeypatch):
    """A testpoint exists to put a check in the situation it watches for. A
    requirement `normalize` says states no boundary effect has no such
    situation and no check to put there, so staging one buys stimulus for a
    heading.

    Measured on the end-to-end run, which staged 111 testpoints: **60 of them,
    54% of the whole staging budget, went to 20 requirements with no
    observable** -- 51 classified scaffolding, 9 interface, and NOT ONE of the
    20 carried a trusted check. Their own `unobservable_reason` says why:
    "Nothing in this requirement constrains behavior at the interface; it only
    identifies the module's architectural role."

    Those testpoints then had no coverage bin either, which is what made a
    finished run fail its OWN `gate_s3` on re-gate -- 111 errors, a contiguous
    tail TP-0371..TP-0481 -- so `--reuse` re-bought S3 and everything below it.
    """
    from specflow import oracles_stage as O

    from specflow import testcase_agent as TA

    calls = []
    #: Imported inside `stage_unexercised`, so the patch goes on the module it
    #: is imported FROM.
    monkeypatch.setattr(TA, "stimulus_for_scenario",
                        lambda **kw: calls.append(kw) or [])

    held = {"REQ-1": O.RequirementOracle(req_uid="REQ-1", tp_uids=[],
                                         clause="c", source=GOOD),
            "REQ-2": O.RequirementOracle(req_uid="REQ-2", tp_uids=[],
                                         clause="c", source=GOOD)}
    reqs = [{"uid": "REQ-1", "text": "the module is the bit controller"},
            {"uid": "REQ-2", "text": "y follows a"}]
    normalized = {
        #: No observable, with normalize's own reason.
        "REQ-1": {"activation": {"text": "always"}, "observable": [],
                  "unobservable_reason": "identifies the module's role only"},
        "REQ-2": {"activation": {"text": "when a rises"},
                  "observable": ["y"], "expectation": "y follows a"},
    }
    testplan: list[dict] = []
    O.stage_unexercised(
        held=held, unexercised={"REQ-1": "never fired", "REQ-2": "never fired"},
        requirements=reqs, normalized=normalized,
        contract={"io": [{"name": "a", "dir": "input", "width": 1},
                         {"name": "y", "dir": "output", "width": 1}]},
        testplan=testplan, stimulus_by_tp={}, witness=WITNESS, port=None,
        attempts=1, budget=8)

    asked = {k["requirement"]["uid"] for k in calls if k.get("requirement")}
    assert "REQ-1" not in asked, (
        "stimulus was generated for a requirement with no observable")
    assert "REQ-2" in asked, "the observable requirement was not staged"

    #: **AND AN EMPTY `observable` ALONE IS NOT ENOUGH.** That is absence of
    #: evidence -- normalize may never have run for the uid at all -- and
    #: skipping on it drops a requirement nobody has examined. The skip is on
    #: `unobservable_reason`, which is normalize SAYING SO. Dropping the reason
    #: from REQ-1 must bring it back.
    calls.clear()
    silent = {**normalized, "REQ-1": {"activation": {"text": "always"},
                                      "observable": []}}
    O.stage_unexercised(
        held=held, unexercised={"REQ-1": "never fired"},
        requirements=reqs, normalized=silent,
        contract={"io": [{"name": "a", "dir": "input", "width": 1},
                         {"name": "y", "dir": "output", "width": 1}]},
        testplan=[], stimulus_by_tp={}, witness=WITNESS, port=None,
        attempts=1, budget=8)
    assert {k["requirement"]["uid"] for k in calls if k.get("requirement")} \
        == {"REQ-1"}, "an unexamined requirement was skipped as unobservable"


def test_a_staged_testpoint_gets_a_BIN_and_a_CHECK_that_pass_S3s_gate(
        monkeypatch):
    """Three artifacts describe one testpoint, and staging wrote back two.

    `_staged_element` already fixed this one artifact up, for S2, and says so:
    "The staging loop appends to `testplan` AFTER S2's gate has run, and
    nothing re-gates the artifact afterwards." S3 never got the same treatment.

    Measured on the end-to-end run: its own `coverage_model.json` failed its own
    `gate_s3` with **111 errors over a contiguous tail TP-0371..TP-0481** --
    exactly the 111 testpoints the stage had staged -- so every `--reuse`
    re-bought S3 and everything below it, and a smoke test of the RTL editor
    loop burned 922 model calls regenerating a coverage model that was already
    on disk.
    """
    from specflow import oracles_stage as O
    from specflow import testcase_agent as TA
    from specflow.s3_coverage import CoverageOutput, gate

    monkeypatch.setattr(TA, "stimulus_for_scenario", lambda **kw: list(STIM["TP-0000"]))

    contract = {"module_name": "m", "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1}]}
    held = {"REQ-0001": O.RequirementOracle(req_uid="REQ-0001", tp_uids=[],
                                            clause="c", source=GOOD)}
    testplan: list[dict] = []
    bins: list[dict] = []
    checks: list[dict] = []
    O.stage_unexercised(
        held=held, unexercised={"REQ-0001": "never fired"},
        requirements=[{"uid": "REQ-0001", "text": "y follows a"}],
        normalized={"REQ-0001": {"activation": {"text": "when a rises"},
                                 "observable": ["y"],
                                 "expectation": "y follows a"}},
        contract=contract, testplan=testplan, stimulus_by_tp={},
        witness=WITNESS, port=None, bins=bins, checks=checks,
        attempts=1, budget=4)

    assert testplan, "nothing was staged, so this test proves nothing"
    staged = {e["uid"] for e in testplan}
    assert {b["covers"][0].split("@")[0] for b in bins} == staged
    assert {c["covers"][0].split("@")[0] for c in checks} == staged

    #: THE POINT: the artifact it produced passes the gate that refused the
    #: real run's.
    issues = gate(testplan, CoverageOutput.model_validate(
        {"reasoning": "", "bins": bins, "checks": checks}), contract)
    assert [i for i in issues if i.severity == "error"] == []


def test_a_check_may_compare_a_PROBE(monkeypatch):
    """`gate_s3` split the contract into outputs and everything-else, so a
    `dir: "probe"` entry fell to "an input; a check must compare an output".

    That predates probes being part of the interface. The runtime samples every
    probe on BOTH the DUT and the reference model and compares them, and 106 of
    one run's 122 frozen checks read one. Comparing a probe is comparing
    something the design drives; comparing an input is comparing the stimulus
    with itself, and only the second is the error this gate is for.
    """
    from specflow.s3_coverage import CoverageOutput, gate

    contract = {"io": [{"name": "a", "dir": "input", "width": 1},
                       {"name": "y", "dir": "output", "width": 1},
                       {"name": "idle", "dir": "probe", "width": 1}]}
    tp = [{"uid": "TP-0000", "covers": ["REQ-0001@1"],
           "needs": ["bin", "check"]}]
    cov = {"reasoning": "",
           "bins": [{"uid": "BIN-0000", "covers": ["TP-0000@1"],
                     "condition": "a rises"}],
           "checks": [{"uid": "CHK-0000", "covers": ["TP-0000@1"],
                       "expr": "the FSM leaves idle", "signals": ["idle"]}]}
    issues = gate(tp, CoverageOutput.model_validate(cov), contract)
    assert [i for i in issues if i.severity == "error"] == []

    #: An INPUT is still refused -- that check compares the stimulus with
    #: itself, which is the error this gate exists for.
    cov["checks"][0]["signals"] = ["a"]
    bad = gate(tp, CoverageOutput.model_validate(cov), contract)
    assert any("must compare an output" in i.message
               for i in bad if i.severity == "error")


def test_the_population_is_not_built_through_a_RESUME_port(tmp_path):
    """**ONE RECORDED WITNESS REPLAYED SEVEN TIMES IS NOT A POPULATION.**
    `ResumePort` replays a recorded response keyed by `(stage, round_)`, and
    every member asks under the same key -- `conforming_implementation` passes
    `stage=WITNESS_STAGE` for all of them. A resumed run therefore wrote seven
    byte-identical designs.

    Measured on the run that found it: all 7 files 8748 bytes, ONE distinct
    md5, `cells` 0, and the scorecard reporting `BLINDNESS 0/0 = n/a` beside
    `population 7`. A degenerate population cannot disagree with itself, so the
    instrument blindness is measured with had quietly become a constant, and
    the run reported a span and an audit over it as though nothing were wrong.

    The premise of resume -- same key, same answer -- is exactly false for a
    population, whose whole value is that independent readings of one
    specification differ. Nothing is lost by refusing it: the loop already
    resumes from `{i}.py` on disk, per member.
    """
    from specflow import oracles_stage as O

    seen = []

    class _Inner:
        def complete(self, *, stage, round_, prompt):
            seen.append("inner")
            return ""

    class _Resume:
        """Stands in for `ResumePort`: replays, and exposes `.inner`."""

        def __init__(self, inner):
            self.inner = inner

        def complete(self, *, stage, round_, prompt):
            seen.append("REPLAYED")
            return "recorded"

    inner = _Inner()
    O._population(size=3, requirements=[{"uid": "REQ-1", "text": "t"}],
                  contract_json='{"module_name": "m", "io": []}',
                  port=_Resume(inner), workdir=tmp_path, run_dir=None)
    assert "REPLAYED" not in seen, (
        "the population was generated through the resume port, so every "
        "member would replay one recorded witness")
