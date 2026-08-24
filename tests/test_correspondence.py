"""Does this oracle test the requirement it claims to test?

Every other check asks whether an oracle is a good CHECK -- well-formed,
satisfiable, able to fail something. None asks whether it is a check of THIS
requirement, so an oracle could name a declared port, run cleanly, catch a
variant, and be about something the requirement never mentions.
"""

from __future__ import annotations

import json

from specflow import oracles_stage as O
from specflow.refmodel import correspondence as C
from specflow.refmodel.oracles import RequirementOracle

REQ = {"uid": "REQ-0001", "text": "cmd_ack pulses high for one clock on WRITE"}
ORACLE = RequirementOracle(
    req_uid="REQ-0001", tp_uids=["TP-0000"], clause="cmd_ack pulses high",
    source="def decide(trace):\n"
           "    for row in trace:\n"
           "        if row['outputs']['cmd_ack']:\n"
           "            return True, row['edge'], 'pulsed'\n"
           "    return None, None, 'never pulsed'\n")


def _reply(ok: bool, missing: str = "") -> str:
    return json.dumps({"reasoning": "r", "tests_the_requirement": ok,
                       "what_is_missing": missing})


class _Port:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.stages: list[str] = []

    def complete(self, *, stage, round_, prompt):
        self.prompts.append(prompt)
        self.stages.append(stage)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


# ------------------------------------------------------------------ the prompt


def test_the_prompt_carries_two_texts_and_no_design():
    """Authority here follows independence, not strength. It may block only
    because it is never shown an implementation."""
    prompt = C.build_prompt(requirement=REQ, oracle=ORACLE)
    assert REQ["text"] in prompt
    assert "def decide" in prompt
    for forbidden in ("class Model", "RefModel", "OUTPUT_PORTS", "edge 0",
                      "observed_behaviour", "outputs':"):
        assert forbidden not in prompt, forbidden


def test_there_is_no_parameter_a_design_could_arrive_through():
    """An exact set, so admitting a new channel is a deliberate edit here.

    `spec` was added and this test is what made it visible. It is admitted
    because it is strictly UPSTREAM of everything -- it is the document S1
    read, so it cannot carry back any artifact the pipeline produced. The
    others on this list are the requirement, its normalized form and the oracle
    under review; none is an implementation, and adding one that is should fail
    this assertion rather than pass quietly.
    """
    import inspect

    taken = set(inspect.signature(C.build_prompt).parameters)
    assert taken == {"requirement", "oracle", "normalized", "spec"}


def test_wider_spec_context_did_not_help_and_is_off_by_default():
    """Measured, both arms, same 70 frozen oracles scored against `liveness`.

    Arm A (no spec) rejected 3 of 70, lift +0.06. Arm B (the whole 15.7 KB
    spec, ahead of the requirement so the prefix stays cacheable) rejected 3 of
    70, lift -0.00. Wider context changed nothing, which is the result: the
    reviewer's handicap is that it never sees an execution, and deadness is a
    property of execution that no amount of prose settles.

    So it defaults off -- an empty `spec` produces the arm-A prompt exactly --
    and the parameter stays because the measurement should be repeatable on a
    design whose spec is organised differently.
    """
    import inspect

    assert inspect.signature(C.build_prompt).parameters["spec"].default == ""
    assert C.build_prompt(requirement=REQ, oracle=ORACLE) == C.build_prompt(
        requirement=REQ, oracle=ORACLE, spec="")
    assert "specification" in C.build_prompt(
        requirement=REQ, oracle=ORACLE, spec="the spec text")


def test_the_reviewer_is_not_offered_a_third_answer():
    """A reviewer given "ambiguous" takes it. That is how the retired judge
    produced 50 AMBIGUOUS verdicts out of 77 on one run."""
    assert "There is no third answer" in C.SYSTEM
    assert "ambiguous" not in C.Review.model_fields


def test_the_reviewer_is_told_not_to_judge_strictness_or_designs():
    for phrase in ("You are not judging any design",
                   "how thorough, how strict"):
        assert phrase in C.SYSTEM, phrase


def test_partial_and_loose_checks_are_on_target():
    """Measured: asking this reviewer about strength made it reject 56 of 70
    real oracles, and only 3 of those were genuinely about the wrong subject.
    26 said "it should also check X" and 15 wanted tighter timing -- both
    answers to a question a different gate asks. As a blocking gate that pushes
    every check toward demanding MORE, while gate 1 pushes them toward
    demanding less."""
    assert "decides only PART of the requirement is ON TARGET" in C.SYSTEM
    assert '"It should also check X" is a YES' in C.SYSTEM


# ----------------------------------------------------------------- the verdict


def test_a_no_rejects_and_carries_what_is_missing():
    out = C.review_one(ORACLE, REQ, port=_Port([_reply(False, "must check the pulse is ONE clock")]))
    why = C.rejects(out)
    assert why.startswith("off-target:")
    assert "ONE clock" in why


def test_a_yes_does_not_reject():
    assert C.rejects(C.review_one(ORACLE, REQ, port=_Port([_reply(True)]))) == ""


def test_an_unparseable_reply_is_not_a_rejection():
    """A blocking gate must not be made out of a bad reply."""
    assert C.rejects(C.review_one(ORACLE, REQ, port=_Port(["not json"]))) == ""


def test_an_unreachable_reviewer_is_not_a_rejection():
    """...nor out of a network error."""
    class _Dead:
        def complete(self, **_kw):
            raise RuntimeError("connection refused")

    assert C.rejects(C.review_one(ORACLE, REQ, port=_Dead())) == ""


def test_each_oracle_is_recorded_under_its_own_key():
    port = _Port([_reply(True)])
    C.review([ORACLE], {"REQ-0001": REQ}, port=port, fanout=False)
    assert port.stages == ["correspond_REQ-0001"]


# ------------------------------------------------------------- inside the stage


def test_the_stage_blocks_on_an_off_target_oracle(tmp_path, monkeypatch):
    """The only blocking gate that is not mechanical -- and the only check of
    any kind that connects an oracle to ITS requirement."""
    from tests.test_oracles_stage import (
        CONTRACT, GOOD, REQS, STIM, TESTPLAN, WITNESS, _Port as _GenPort,
        _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(C, "review", lambda *a, **k: {
        "REQ-0001": C.Review(tests_the_requirement=False,
                             what_is_missing="it never reads y")})

    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_GenPort([_gen_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, max_rounds=1, want_correspondence=True)

    assert got.dispositions["REQ-0001"] == "ORACLE_INVALID"
    assert "never reads y" in got.reasons["REQ-0001"]


def test_the_witness_note_is_taken_before_anything_blocks(tmp_path, monkeypatch):
    """Gate 1 first and non-mandatory: a rejection is read beside what the
    witness thought rather than instead of it."""
    from tests.test_oracles_stage import (
        CONTRACT, OVER_STRICT, REQS, STIM, TESTPLAN, WITNESS,
        _Port as _GenPort, _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(C, "review", lambda *a, **k: {
        "REQ-0001": C.Review(tests_the_requirement=False,
                             what_is_missing="off target")})

    O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_GenPort([_gen_reply(OVER_STRICT)]), workdir=tmp_path,
        base="step", fanout=False, max_repairs=0, max_rounds=1,
        run_dir=tmp_path, want_correspondence=True)

    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert blob["correspondence_checked"] is True
    assert "witness" in blob["instrument_notes"]["REQ-0001"], (
        "the witness observation must survive a downstream rejection")


# ------------------------------------------------- gate 1 advises, never gates


def test_gate_1_earns_one_attempt_and_only_one(tmp_path, monkeypatch):
    """Non-mandatory means TRY, not ignore. The author is asked once to make the
    check accept a second implementation -- and asked once only, because a
    disagreement that recurs every round spends a call per round on an author
    who has already answered, which is pressure by repetition."""
    from tests.test_oracles_stage import (
        CONTRACT, OVER_STRICT, REQS, STIM, TESTPLAN, WITNESS,
        _Port as _GenPort, _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _GenPort([_gen_reply(OVER_STRICT)])
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", fanout=False,
        max_repairs=0, max_rounds=3, run_dir=tmp_path)

    assert len(port.prompts) == 2, (
        f"gate 1 must earn exactly one attempt, got {len(port.prompts)}")
    assert "witness_disagrees" in port.prompts[1]
    # And declining costs nothing: the reply is the same over-strict oracle.
    assert got.dispositions["REQ-0001"] == O.TRUSTED
    blob = json.loads((tmp_path / "specflow" / O.ARTIFACT).read_text())
    assert "witness" in blob["instrument_notes"]["REQ-0001"]


def test_the_advice_rides_along_when_a_round_happens_anyway(tmp_path,
                                                            monkeypatch):
    """Gate 1 comes first: when an oracle is re-asked for a blocking reason,
    the witness observation is in the prompt ahead of it -- free, because the
    call was already being spent."""
    from tests.test_oracles_stage import (
        CONTRACT, GOOD, OVER_STRICT, REQS, STIM, TESTPLAN, WITNESS,
        _Port as _GenPort, _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    # Off-target blocks; the witness also disagrees with OVER_STRICT.
    seen = {"n": 0}

    def _review(*_a, **_k):
        seen["n"] += 1
        return {"REQ-0001": C.Review(tests_the_requirement=seen["n"] == 1 and False
                                     or seen["n"] > 1,
                                     what_is_missing="it never reads y")}

    monkeypatch.setattr(C, "review", _review)
    port = _GenPort([_gen_reply(OVER_STRICT), _gen_reply(GOOD)])
    O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", fanout=False,
        max_repairs=0, want_correspondence=True)

    assert len(port.prompts) == 2, "the blocking reason must cost a round"
    repair = port.prompts[1]
    assert "witness_disagrees" in repair, "gate 1's advice is not in the prompt"
    assert "off_target" in repair or "off-target" in repair
    assert repair.index("witness_disagrees") < repair.index("off"), (
        "gate 1 comes first")


def test_the_advice_says_it_may_be_ignored():
    """An author told "an independent implementation fails your check" contorts
    a correct check. The wording has to carry non-mandatory or it is just a
    rejection with softer punctuation."""
    issue = O._advisory("REQ-0001", "fails it at edge 3")
    assert issue.severity == "warning"
    for phrase in ("TRY to make", "NOT A DEFECT AND YOU MAY DECLINE",
                   "no better authority", "KEEP YOUR", "rejected for declining"):
        assert phrase in issue.message, phrase
