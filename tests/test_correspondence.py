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

    `contract` was added second, and this test failed on it before it was
    admitted here -- which is the mechanism working. It is admitted on the same
    ground as `spec`: an INTERFACE is not a design. The contract fixes port
    names, directions and widths before the reference model, the witness or any
    trace exists, so nothing about a design's BEHAVIOUR can travel through it.
    `oracle_gen.build_prompt` has taken it all along, so the author knew every
    port's direction while its reviewer did not, and that asymmetry had no
    defence.

    The line that would fail: a `model`, `witness`, `trace`, `replay` or
    `verdict` parameter. Any of those carries what a design DID, which is what
    I1 exists to keep out of a reviewer that is meant to compare two texts.

    `siblings` was added third and failed here too. It carries OTHER
    REQUIREMENTS -- their sentences and normalized forms -- which is the same
    class of text as `requirement` itself and upstream of every design, so it
    admits on the same ground. It is needed because `through_req` was a bare
    uid: on REQ-0085's prompt "REQ-0007" appeared exactly once, in the route,
    with that requirement's text absent, so the route pointed at nothing the
    reviewer could read. Only the requirements a route NAMES are carried, and a
    separate test pins that.
    """
    import inspect

    taken = set(inspect.signature(C.build_prompt).parameters)
    assert taken == {"requirement", "oracle", "normalized", "spec", "contract",
                     "siblings"}
    assert not (taken & {"model", "witness", "trace", "replay", "verdict",
                         "design", "rows"})


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
    for phrase in ("no design", "HOW MUCH IT DEMANDS"):
        assert phrase in C.SYSTEM, phrase


def test_the_gate_refuses_STRENGTH_and_CODE_STYLE_but_not_LOGIC():
    """The line this gate must not cross, stated as three separate refusals.

    Strength is another gate's question and asking it here rejected 56 of 70.
    Code style is nobody's -- a reviewer asked how the check is WRITTEN will
    find something. Logical direction is neither: a check that asserts its own
    antecedent is not a weak check of the requirement, it is not a check of it,
    which is this gate's own question.
    """
    for phrase in ("HOW MUCH IT DEMANDS", "HOW IT IS WRITTEN",
                   "WHERE IT READS A VALUE FROM",
                   "DOES THE CODE DECIDE WHAT THE"):
        assert phrase in C.SYSTEM, phrase


def test_direction_is_asked_as_part_of_the_same_question():
    """MEASURED BEFORE IT WAS ADDED: 0 rejections in 82 checks, 37 of which a
    known-good implementation refutes. The topic question alone contributes
    nothing to that residue."""
    for phrase in ("ASSERTS THE TRIGGER INSTEAD OF THE EFFECT",
                   "TRIGGERS ON THE WRONG SITUATION",
                   "CONVICTS OUTSIDE THE CLAIM",
                   "THERE MUST BE A SENTENCE"):
        assert phrase in C.SYSTEM, phrase
    # The CHECK's verdict must still be ONE field, not several to hide behind:
    # a reviewer that can pass the main question while flagging direction
    # separately will do exactly that, and the rejection stops binding.
    #
    # `states_an_obligation` is admitted beside it, and the reason is the whole
    # test of whether a field is allowed here: it is not a grade of the check at
    # all. It accuses the SPECIFICATION and routes to spec authoring, so it
    # cannot be folded into `tests_the_requirement` without sending a repair
    # round to the author -- the one party that cannot act on it.
    assert set(C.Review.model_fields) == {
        "reasoning", "states_an_obligation", "tests_the_requirement",
        "what_is_missing"}


def test_asserting_the_premise_is_not_a_WEAK_check():
    """The collision the direction leg would otherwise have with the old rule,
    and the reason the escape hatch is WEAKNESS rather than PARTIALNESS.

    MEASURED on c1-i2c: 99 of 104 requirements have exactly ONE distinct
    clause -- 95% atomic. So "decides only PART of the requirement" was
    accommodating a case that barely exists while muddying the common one, and
    it would have readmitted a check asserting only the condition as a "part".
    A requirement states one claim; the licence is to decide it weakly, never
    to decide half of it."""
    assert "says NOTHING about any other row" in C.SYSTEM
    assert "ASSERTS THE TRIGGER INSTEAD OF THE EFFECT" in C.SYSTEM
    assert "no design can fail it" in C.SYSTEM


def test_partial_and_loose_checks_are_on_target():
    """Measured: asking this reviewer about strength made it reject 56 of 70
    real oracles, and only 3 of those were genuinely about the wrong subject.
    26 said "it should also check X" and 15 wanted tighter timing -- both
    answers to a question a different gate asks. As a blocking gate that pushes
    every check toward demanding MORE, while gate 1 pushes them toward
    demanding less."""
    # Fragments that do not cross a line wrap -- an assertion spanning a break
    # has now cost this file four times.
    assert "NOT YOUR QUESTION" in C.SYSTEM
    assert "weaker than you would have written" in C.SYSTEM
    assert "pushes every check toward demanding more" in C.SYSTEM
    # the licence is the IMPLEMENTATION axis, never a licence to be vague about
    # logic -- "loosely" invited exactly that reading and is gone.
    assert "loosely" not in C.SYSTEM and "more tightly" not in C.SYSTEM


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
        fanout=False, max_repairs=0, repair_attempts=0, want_correspondence=True)

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
        base="step", fanout=False, max_repairs=0, repair_attempts=0,
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
        max_repairs=0, repair_attempts=2, run_dir=tmp_path)

    assert len(port.prompts) == 2, (
        f"gate 1 must earn exactly one attempt, got {len(port.prompts)}")
    # Either spelling of gate 1's advice: the generic ask, or the specific
    # `judged_at_idle` note that replaces it when the trace shows the check
    # answered before anything it reads had moved.
    assert ("witness_disagrees" in port.prompts[1]
            or "judged_at_idle" in port.prompts[1])
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
    # Gate 1's advice has TWO spellings. The generic ask -- "a second
    # implementation fails your check, TRY to accept it" -- and the specific
    # `judged_at_idle` note that REPLACES it when the trace shows the check
    # answered before anything it reads had moved. Either is gate 1 speaking;
    # pinning only the first would fail the moment the sharper note applies.
    gate1 = next((m for m in ("witness_disagrees", "judged_at_idle")
                  if m in repair), None)
    assert gate1, "gate 1's advice is not in the prompt under either spelling"
    off = next((m for m in ("off_target", "off-target") if m in repair), None)
    assert off, "the off-target rejection is not in the prompt"
    # Index on the FULL marker, never the bare "off": the prompt's temporal
    # block says "a window that runs off the end of the trace", which precedes
    # the gate_failures section and made this assertion compare gate 1 against
    # a word in the system text rather than against the rejection.
    assert repair.index(gate1) < repair.index(off), "gate 1 comes first"


def test_the_advice_says_it_may_be_ignored():
    """An author told "an independent implementation fails your check" contorts
    a correct check. The wording has to carry non-mandatory or it is just a
    rejection with softer punctuation."""
    issue = O._advisory("REQ-0001", "fails it at edge 3")
    assert issue.severity == "warning"
    for phrase in ("TRY to make", "NOT A DEFECT AND YOU MAY DECLINE",
                   "no better authority", "KEEP YOUR", "rejected for declining"):
        assert phrase in issue.message, phrase


def test_the_interface_reaches_the_reviewer_with_directions_and_notes():
    """Port direction is what makes three of the reviewer's cases decidable.

    Without it, "reads ports the requirement is not about" has nothing to
    resolve a name against, and a check convicting on the value of an INPUT --
    something the DUT does not drive -- is indistinguishable from one
    convicting on an output. REQ-0028 is the recorded case.
    """
    # THE REAL ARTIFACT SHAPE: `io`, and the direction key is `dir`. The first
    # version of this test invented `{"ports": [...]}` with a `direction` key,
    # so it passed against a projection that read neither and emitted an empty
    # block -- the change was inert and the test said it worked. A fixture that
    # invents its input tests nothing.
    contract = {"io": [
        {"name": "scl_oen", "dir": "output", "width": 1,
         "notes": "0 drives SCL low; 1 releases it to the pull-up"},
        {"name": "sda_i", "dir": "input", "width": 1, "idle_value": 1},
    ]}
    oracle = C.RequirementOracle(
        req_uid="REQ-0001", clause="c", source="def decide(trace): ...")
    body = C.build_prompt(requirement={"uid": "REQ-0001"}, oracle=oracle,
                          contract=contract)
    assert "scl_oen" in body and "output" in body
    assert "sda_i" in body and "input" in body
    assert "releases it to the pull-up" in body
    assert "idle_value" in body, "a port resting at its asserted value is the case"


def test_pacing_fields_are_not_offered_to_the_reviewer():
    """Phases 3-6 severed cycle counts from gating, and the surplus question
    exists to catch invented timing. Handing the reviewer a `latency_cycles`
    would invite exactly the demand the other gate is trying to remove.
    """
    contract = {"io": [{"name": "busy", "dir": "output", "width": 1}],
                "latency_cycles": 3, "clocking": {"clock": "clk"}}
    oracle = C.RequirementOracle(req_uid="R", clause="c", source="s")
    body = C.build_prompt(requirement={"uid": "R"}, oracle=oracle,
                          contract=contract)
    assert "latency_cycles" not in body


def test_an_absent_contract_leaves_the_prompt_exactly_as_it_was():
    """The parameter defaults off, so the measured arm-A prompt is reproducible."""
    oracle = C.RequirementOracle(req_uid="R", clause="c", source="s")
    req = {"uid": "R", "text": "t"}
    assert (C.build_prompt(requirement=req, oracle=oracle)
            == C.build_prompt(requirement=req, oracle=oracle, contract=None)
            == C.build_prompt(requirement=req, oracle=oracle, contract={}))


def test_the_projection_is_pinned_to_the_shape_a_real_contract_has():
    """The regression that a hand-written fixture could not catch.

    `contract.json` carries `io`, and each entry's direction key is `dir`. A
    projection reading `ports`/`direction` returns an empty list against every
    real artifact in this repo, which is silent: the prompt still renders, just
    with nothing in it. So this asserts against a contract loaded the way the
    pipeline loads one, not one written to suit the code.
    """
    import json
    import pathlib

    found = [p for p in pathlib.Path("benchmarks").rglob("contract*.json")]
    real = None
    for path in found:
        try:
            obj = json.loads(path.read_text())
        except Exception:  # noqa: BLE001, PERF203
            continue
        if isinstance(obj, dict) and obj.get("io"):
            real = obj
            break
    if real is None:  # no fixture on disk: assert the key names directly
        real = {"io": [{"name": "p", "dir": "output", "width": 1}]}
    got = C._ports(real)["ports"]
    assert got, "an empty projection means the interface block carries nothing"
    assert all("name" in r for r in got)
    assert any(r.get("direction") in ("input", "output") for r in got), \
        "the direction key is `dir` in the artifact and `direction` in the projection"
    assert C._ports({"ports": [{"name": "x", "direction": "output"}]})["ports"] == [], \
        "the OLD shape must project to nothing, so this test fails if it is restored"


def test_the_per_design_constants_sit_in_the_CACHED_prefix():
    """`shared_block` is the cached head, and its rule is that nothing in it
    varies between the items of one stage. The specification and the interface
    satisfy that; the requirement and the oracle do not.

    Placing them merely EARLY in the item half puts them after the sentinel, so
    they are re-sent and re-priced on every call -- which is what `fanout.py`'s
    floor comment records this stage doing once already: SYSTEM alone is ~471
    tokens, under the 1024-token floor below which NOTHING caches, measured at
    12% against 65-83% for every other fan-out.
    """
    from specflow.fanout import PREFIX_SENTINEL

    contract = {"io": [{"name": "zzbusyzz", "dir": "output", "width": 1}]}
    body = C.build_prompt(requirement=REQ, oracle=ORACLE,
                          spec="THE-SPEC-TEXT-MARKER", contract=contract)
    head, tail = body.split(PREFIX_SENTINEL, 1)
    assert "THE-SPEC-TEXT-MARKER" in head and "zzbusyzz" in head
    assert REQ["text"] not in head, "the requirement varies per item"
    # A marker unique to the FIXTURE: the briefing itself contains `def decide`
    # in its worked examples, so that string cannot distinguish the two halves.
    assert "'pulsed'" not in head, "so does the oracle"
    assert REQ["text"] in tail and "pulsed" in tail


def test_demanding_an_INTERNAL_signal_is_not_a_valid_rejection():
    """MEASURED, and this is the fix for it. Given the interface, the reviewer
    began rejecting checks for not observing signals that are not ports at all
    -- "would need to observe the internal sto_condition signal", "instead of
    checking slave_wait", "does not detect when the internal counter expires".
    Four of arm C's five false positives had exactly that shape, and the arm
    scored 29% precision against a 45% base rate: worse than rejecting at
    random.

    It is the same error made once already at normalization, reading each
    requirement's MECHANISM instead of its EFFECT, which called 27 of 77
    requirements unobservable when 10 of them already had working checks.
    """
    for phrase in ("THAT IT DOES NOT WATCH AN INTERNAL SIGNAL",
                   "NEVER a valid rejection",
                   "MECHANISM instead of its"):
        assert phrase in C.SYSTEM, phrase


def test_the_reviewer_is_pointed_AT_the_observation_route():
    """It always HAD `observed_via` -- `build_prompt` passes `normalized`
    whole -- and that is what makes arm C's false positives a misreading rather
    than a gap. REQ-0085's prompt carried a route naming `scl_oen` with a
    `shows` spelling out both cases, and the reviewer rejected the check for
    "checking scl_oen held released instead of checking slave_wait": it named
    the internal mechanism over the route printed beside it.

    So the fix is not to supply the route -- it is to say the route is the
    STANDARD the check is judged against.
    """
    for phrase in ("OBSERVATION ROUTE", "THAT IS THE STANDARD",
                   "even when the requirement's"):
        assert phrase in C.SYSTEM, phrase


def test_the_route_actually_reaches_the_prompt():
    """The pin under the paragraph above: a rule about `observed_via` is worth
    nothing if the block never carries one."""
    normalized = {"observable": ["busy"], "observed_via": [
        {"port": "busy", "through_req": "REQ-0007", "when": "w",
         "shows": "busy stays low for a narrow glitch and rises for a wide one"}]}
    body = C.build_prompt(requirement=REQ, oracle=ORACLE, normalized=normalized)
    assert "observed_via" in body
    assert "rises for a wide one" in body, "the discrimination, not just the port"


def test_a_route_s_through_req_is_not_a_dangling_pointer():
    """MEASURED: on REQ-0085's prompt the string "REQ-0007" appeared exactly
    ONCE -- inside the route -- while that requirement's text and its normalized
    form were both absent. A reviewer told a behaviour is visible through
    REQ-0007, and given no way to read REQ-0007, cannot judge the route at all
    and falls back to this requirement's own sentence, which names the internal
    mechanism the route exists to get past. That is arm C's failure mode.
    """
    normalized = {"observable": ["busy"], "observed_via": [
        {"port": "busy", "through_req": "REQ-0007", "when": "w", "shows": "s"}]}
    siblings = {"REQ-0007": {"uid": "REQ-0007",
                             "text": "busy is set when a START is detected",
                             "observable": ["busy"],
                             "expectation": "busy rises on START"}}
    body = C.build_prompt(requirement=REQ, oracle=ORACLE, normalized=normalized,
                          siblings=siblings)
    assert "<route_requirements>" in body, "the BLOCK, not the word: SYSTEM names it too"
    assert "busy is set when a START is detected" in body
    assert "busy rises on START" in body


def test_only_the_requirements_a_route_NAMES_are_carried():
    """Not the whole set: the reviewer judges one requirement and the prompt
    stays a pair of texts plus what its own routes point at."""
    normalized = {"observed_via": [
        {"port": "busy", "through_req": "REQ-0007", "when": "w", "shows": "s"}]}
    siblings = {"REQ-0007": {"text": "the one that is named"},
                "REQ-0099": {"text": "the one that is NOT named"}}
    body = C.build_prompt(requirement=REQ, oracle=ORACLE, normalized=normalized,
                          siblings=siblings)
    assert "the one that is named" in body
    assert "the one that is NOT named" not in body


def test_a_direct_route_carries_no_sibling_block():
    """`through_req` empty is this requirement's own port -- there is nothing to
    point at, and an empty block would be noise on the 76 of 122 that are
    direct."""
    normalized = {"observed_via": [
        {"port": "busy", "through_req": "", "when": "w", "shows": "s"}]}
    body = C.build_prompt(requirement=REQ, oracle=ORACLE, normalized=normalized,
                          siblings={"REQ-0007": {"text": "x"}})
    assert "<route_requirements>" not in body


def test_the_gate_is_told_it_can_convict_a_check_that_became_the_siblings():
    """The one rejection only this gate can make, and it was not expressible
    while `through_req` was a bare uid."""
    assert "has the check silently become THAT" in C.SYSTEM
    assert "testing the neighbour under a different uid" in C.SYSTEM


# --------------------------------------- the prior question: is there anything
#                                         to assert at all?


def test_a_requirement_that_forbids_nothing_is_not_the_checks_fault():
    """`not-assertable` and `off-target` accuse different parties.

    The author cannot decline: handed a definition it produces the most
    plausible check in the neighbourhood, and that check is well-formed. So the
    finding must land on the SPECIFICATION, or a repair round goes to the one
    party with no move.
    """
    from specflow.refmodel import verdict as V

    out = C.rejects(C.Review(states_an_obligation=False,
                             what_is_missing="defines cmd; states no effect"))
    assert out.startswith("not-assertable:")
    assert V.of_discard(out) == "NOT_ASSERTABLE"
    assert V.ROUTE["NOT_ASSERTABLE"] == "return to spec authoring"
    assert "NOT_ASSERTABLE" in V.BLOCKING, "a hollow requirement must not pass"


def test_the_prior_question_wins_when_the_reply_says_both():
    """A reply may reject on both counts. The requirement's defect is the one
    that decides, because it is the one that ends the requirement rather than
    buying it a repair round."""
    out = C.rejects(C.Review(states_an_obligation=False,
                             tests_the_requirement=False,
                             what_is_missing="a scope statement"))
    assert out.startswith("not-assertable:"), out


def test_an_old_reply_without_the_field_is_not_a_rejection():
    """The field defaults TRUE on purpose. A model that never saw section 3b
    must not have its silence read as "this requirement is hollow" -- the
    expensive error is rejecting a real requirement."""
    assert C.rejects(C.Review(tests_the_requirement=True)) == ""
    assert C.rejects(C.Review(tests_the_requirement=False,
                              what_is_missing="x")).startswith("off-target:")


def test_naming_an_internal_mechanism_is_not_grounds_on_its_own():
    """The boundary that keeps section 3b from becoming the rejection section 7
    forbids. Both examples must be IN the prompt, because the contrast is the
    only thing separating "invisible mechanism" from "no obligation"."""
    assert "3b. THE PRIOR QUESTION" in C.SYSTEM
    assert "reloads the internal\n       counter cnt" in C.SYSTEM, (
        "the OBLIGATION-despite-an-internal-mechanism example must survive")
    assert "slave_wait condition indicates" in C.SYSTEM, (
        "the NO-OBLIGATION counterpart must survive beside it")
    assert "never \"can this be observed\"" in C.SYSTEM


def test_the_stage_routes_a_hollow_requirement_to_spec_authoring(
        tmp_path, monkeypatch):
    """End to end: the disposition is NOT_ASSERTABLE, not ORACLE_INVALID."""
    from tests.test_oracles_stage import (
        CONTRACT, GOOD, REQS, STIM, TESTPLAN, WITNESS, _Port as _GenPort,
        _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(C, "review", lambda *a, **k: {
        "REQ-0001": C.Review(states_an_obligation=False,
                             what_is_missing="names a capability, no effect")})

    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=_GenPort([_gen_reply(GOOD)]), workdir=tmp_path, base="step",
        fanout=False, max_repairs=0, repair_attempts=0, want_correspondence=True)

    assert got.dispositions["REQ-0001"] == "NOT_ASSERTABLE"
    assert "no effect" in got.reasons["REQ-0001"]


def test_a_hollow_requirement_never_costs_a_repair_round(tmp_path, monkeypatch):
    """The saving that makes this cheaper than the gate it replaces: nothing the
    author writes can add an obligation, so it is never re-asked."""
    from tests.test_oracles_stage import (
        CONTRACT, GOOD, REQS, STIM, TESTPLAN, WITNESS, _Port as _GenPort,
        _reply as _gen_reply,
    )

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(C, "review", lambda *a, **k: {
        "REQ-0001": C.Review(states_an_obligation=False,
                             what_is_missing="a definition")})

    port = _GenPort([_gen_reply(GOOD)] * 6)
    got = O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", fanout=False,
        max_repairs=0, repair_attempts=2, want_correspondence=True)

    assert got.dispositions["REQ-0001"] == "NOT_ASSERTABLE"
    assert not [s for s in port.stages if "fix" in s], (
        f"a hollow requirement was re-asked: {port.stages}")


def test_zero_hollow_requirements_is_not_reported_when_nobody_asked():
    """The summary's own rule, applied to the new gate. Correspondence is the
    only leg that can emit NOT_ASSERTABLE, so with it off a 0 would read as
    "every requirement asserts something" when it means "not looked at" -- the
    exact ambiguity that once had `over_strict: 0` read as a clean bill."""
    off = O.OracleSet(dispositions={"REQ-0001": "TRUSTED"},
                      tools={"correspondence": False})
    assert off.rates()["NOT_ASSERTABLE"] is None

    on = O.OracleSet(dispositions={"REQ-0001": "TRUSTED"},
                     tools={"correspondence": True})
    assert "NOT_ASSERTABLE" not in on.rates(), (
        "with the gate on and nothing found, absence is a real zero")

    found = O.OracleSet(dispositions={"REQ-0001": "NOT_ASSERTABLE"},
                        tools={"correspondence": True})
    assert found.rates()["NOT_ASSERTABLE"] == 1
