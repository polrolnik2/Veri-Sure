"""S1 below the divider: the boundary pass, the freeze, and the glue.

THE UNIT IS THE REQUIREMENT. `divide` cuts, the boundary pass enlarges by
merging with the unit before, `mint_requirements` freezes one requirement per
unit, and classify fills supportive fields on requirements that already exist.
That is what makes the 100%-of-spec catch-all structurally impossible rather
than merely penalised, and it is why G1' is small: tiling, span-containment and
"two obligations in one restatement" all policed freedoms the classifier no
longer has.
"""

from __future__ import annotations

import json
import os

from specflow.divide import divide
from specflow.s1_classify import (
    PREFIX_SENTINEL,
    UnitClassification,
    build_prompt,
    divide_and_classify,
    gate_unit,
    parse_response,
    shared_prefix,
    attach_classification,
    mint_requirements,
)
from specflow.schema import has_errors

CONTRACT = json.dumps({
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
        {"name": "cout", "dir": "output", "width": 1},
    ]
})
SPEC = "The sum output is a xor b.\n\nThe cout output is a and b.\n"


def _unit(spec=SPEC, i=0):
    return divide(spec)[i]


def _ok(text="The sum output is a xor b.", ports=("sum",), **kw):
    return UnitClassification(unit_kind="behavioural", text=text,
                              ports=list(ports), **kw)


def _reqs(spec, units, *classifications):
    """Mint first, classify after -- the order the pipeline uses."""
    reqs = mint_requirements(spec, units)
    results = [type("R", (), {"output": c})() for c in classifications]
    return attach_classification(spec, units, reqs, results)



# ------------------------------------------------------------------ the gate


def test_a_unit_that_states_its_requirement_passes():
    assert gate_unit(_ok(), unit=_unit(), spec=SPEC,
                     contract=json.loads(CONTRACT)) == []


def test_the_classifier_cannot_split_a_unit_because_the_shape_forbids_it():
    """The rule is enforced by the ANSWER'S SHAPE, not by a gate.

    `UnitClassification` carries one restatement, not a list, so "return nine
    requirements for this sentence" is not a move the model can make and then
    have rejected -- it is unrepresentable. On n3-i2c, under the list, one
    feature-list sentence became nine requirements sharing one span and one
    reset sentence became seven.
    """
    assert not hasattr(UnitClassification(), "obligations")
    assert isinstance(UnitClassification().text, str)


def test_a_restatement_opening_with_a_back_reference_is_an_error():
    """The 15-28% failure mode, checked on the restatement the model authors."""
    for opener in ("It is asserted for one cycle.",
                   "This also clears the flag.",
                   "Otherwise the output holds."):
        out = _ok(opener)
        issues = gate_unit(out, unit=_unit(), spec=SPEC,
                           contract=json.loads(CONTRACT))
        assert has_errors(issues), opener


def test_a_self_contained_restatement_passes():
    out = _ok("The sum output is driven to the xor of a and b.")
    assert gate_unit(out, unit=_unit(), spec=SPEC,
                     contract=json.loads(CONTRACT)) == []


def test_a_restatement_carrying_two_obligations_is_NOT_rejected():
    """The check that used to reject this is gone, and removing it was forced.

    It defended against a model claiming a wide span with a crammed sentence.
    The model cannot choose a span any more, so the only thing the check could
    still do is reject the correct answer: a merged block, or a sentence that
    states two things in one breath, MUST be restated as both.
    """
    out = _ok("The module shall drive sum to a xor b and shall assert cout "
              "when both inputs are high.", ports=("sum", "cout"))
    assert gate_unit(out, unit=_unit(), spec=SPEC,
                     contract=json.loads(CONTRACT)) == []


def test_a_port_the_contract_does_not_declare_is_an_error():
    out = _ok(ports=("sum", "carry_out_typo"))
    issues = gate_unit(out, unit=_unit(), spec=SPEC,
                       contract=json.loads(CONTRACT))
    assert has_errors(issues)


def test_unit_kind_never_blocks_anything():
    """It records how the unit reads and decides nothing.

    A `scaffolding` unit that states a requirement is not a contradiction the
    gate should resolve -- the classification is advisory, and whether the
    obligation can be checked is settled by trying, at the oracle stage.
    """
    out = UnitClassification(unit_kind="scaffolding",
                             text="The sum output is driven to a xor b.",
                             ports=["sum"])
    assert gate_unit(out, unit=_unit(), spec=SPEC,
                     contract=json.loads(CONTRACT)) == []


def test_a_supporting_unit_that_is_not_a_unit_is_an_error():
    """The vocabulary is the frozen partition, which is what stops this being a
    way to claim arbitrary text."""
    units = divide(SPEC)
    starts = frozenset(u.start for u in units)
    out = _ok(supporting_units=[99999])
    issues = gate_unit(out, unit=units[0], spec=SPEC,
                       contract=json.loads(CONTRACT), unit_starts=starts)
    assert has_errors(issues)
    assert gate_unit(_ok(supporting_units=[units[1].start]), unit=units[0],
                     spec=SPEC, contract=json.loads(CONTRACT),
                     unit_starts=starts) == []


def test_a_behavioural_unit_stating_nothing_is_an_error():
    out = UnitClassification(unit_kind="behavioural", text="   ")
    issues = gate_unit(out, unit=_unit(), spec=SPEC,
                       contract=json.loads(CONTRACT))
    assert has_errors(issues)
    assert any(i.kind == "uncovered" for i in issues)


def test_a_short_unit_is_never_rejected_for_being_short():
    """No minimum length, deliberately. A 24-character floor rejected the half
    adder's legitimate `' - output cout'`, and a threshold standing in for a
    property is the mistake this module has reverted twice."""
    spec = " - output cout\n"
    u = divide(spec)[0]
    out = _ok("The cout output is declared as an output port.", ports=("cout",))
    assert gate_unit(out, unit=u, spec=spec, contract=json.loads(CONTRACT)) == []


def test_a_parse_error_short_circuits_every_other_check():
    out = UnitClassification(reasoning="Parse Error: boom")
    issues = gate_unit(out, unit=_unit(), spec=SPEC,
                       contract=json.loads(CONTRACT))
    assert len(issues) == 1 and "Parse Error" in issues[0].message


# --------------------------------------------------------------- the prompt


def test_the_shared_prefix_is_byte_identical_across_units():
    """C1, applied to the real stage rather than a stand-in.

    Every unit of a spec must produce a prompt opening with the same block, or
    the fan-out costs ~30x what it should and nothing anywhere reports it.
    """
    spec = "\n\n".join(f"Paragraph {i} states that the sum output is driven." for i in range(30))
    units = divide(spec)
    prompts = [
        build_prompt(spec=spec, contract_json=CONTRACT, unit=u, index=i, units=units)
        for i, u in enumerate(units)
    ]
    common = os.path.commonprefix(prompts)
    assert PREFIX_SENTINEL in common, "the shared block is not actually shared"
    assert common.startswith(shared_prefix(spec, CONTRACT))


def test_a_repair_round_appends_after_the_unit():
    """C2 on the real stage: issues and the previous answer must not prepend."""
    from specflow.schema import Issue

    units = divide(SPEC)
    r0 = build_prompt(spec=SPEC, contract_json=CONTRACT, unit=units[0], index=0, units=units)
    r1 = build_prompt(spec=SPEC, contract_json=CONTRACT, unit=units[0], index=0, units=units,
                      issues=[Issue("error", "x", "y")], previous="{}")
    assert r1.startswith(shared_prefix(SPEC, CONTRACT))
    assert len(r1) > len(r0)
    assert r1.index("<unit ") < r1.index("gate_failures")


def test_the_prompt_carries_the_neighbouring_units():
    """What makes splitting below a paragraph safe: the referent is in view."""
    units = divide(SPEC)
    p = build_prompt(spec=SPEC, contract_json=CONTRACT, unit=units[1], index=1, units=units)
    assert "<previous_unit start=" in p and "The sum output is a xor b." in p
    assert "<next_unit>" not in p, "there is no unit after the last one"


def test_the_prompt_never_asks_for_spec_text_back():
    p = shared_prefix(SPEC, CONTRACT)
    # The unit IS the requirement, minted before this call, so there is no span
    # for the model to quote, compute, or get wrong.
    assert "cannot create a requirement" in p
    assert "0-based" not in p


def test_a_response_that_lost_its_opening_is_a_parse_error_not_scaffolding():
    """The silent one: 6 of 168 responses on n3-i2c arrived with no head.

    The first output-text delta went missing, so the text began at
    `"reasoning": "...` with no `{`. `extract_json_object` scraped the last
    OBLIGATION out of the remainder -- `{start, end, text, ports}` -- every
    field fell to its default, and `kind` defaulted to "scaffolding". A
    scaffolding unit with no obligations passes `gate_unit` without a word, so
    six behavioural units produced nothing while the gate read ok=True with
    zero issues. One stated that `busy` is set on START and cleared on STOP.
    """
    # What the six real ones looked like: the opening `{` and part of the
    # first key gone, so `extract_json_object` scrapes whatever inner object it
    # can find. `kind` decides everything and the prompt always asks for it, so
    # its absence is a truncated response and never a verdict.
    headless = (
        '"reasoning": "The unit states two observable actions.",\n'
        '  "detail": {"note": "The FSM stalls.", "ports": []}\n}'
    )
    out = parse_response(headless)
    assert out.reasoning.startswith("Parse Error: "), out
    assert "opening was lost in transport" in out.reasoning
    # ...and the gate must then BLOCK, so a repair round happens.
    u = divide(SPEC)[0]
    issues = gate_unit(out, unit=u, spec=SPEC, contract=None)
    assert any(i.severity == "error" for i in issues), issues


def test_a_genuine_scaffolding_verdict_still_parses():
    """The guard keys on `kind`, which the prompt always asks for, so an honest
    'this unit constrains nothing' answer is untouched."""
    out = parse_response('{"reasoning": "A heading.", "unit_kind": "scaffolding",'
                         ' "text": "Section 3 introduces the bit-level FSM."}')
    assert out.unit_kind == "scaffolding"
    assert not out.reasoning.startswith("Parse Error")
    assert gate_unit(out, unit=divide(SPEC)[0], spec=SPEC, contract=None) == []


# -------------------------------------------------------------- assembly


def _res(*classifications):
    return [type("R", (), {"output": c})() for c in classifications]


def test_every_unit_becomes_one_requirement_spanning_exactly_that_unit():
    units = divide(SPEC)
    reqs = _reqs(SPEC, units,
                 _ok("The sum output is a xor b.", ("sum",)),
                 _ok("The cout output is a and b.", ("cout",)))
    assert [r["uid"] for r in reqs] == ["REQ-0000", "REQ-0001"]
    for r, u in zip(reqs, units):
        core = r["spec_spans"][0]
        assert core["role"] == "core"
        assert (core["start"], core["end"]) == (u.start, u.end)
        assert core["quote"] == u.text(SPEC)


def test_a_unit_that_requires_nothing_STILL_becomes_a_requirement():
    """Whether an obligation can be asserted is not knowable here.

    It is knowable once something has tried, which is the oracle stage and its
    dispositions. Deciding it at S1 is how 49 of n3-i2c's 168 units produced
    nothing at all -- silently, because the divide arm runs no
    unattributed-text check that would have noticed.
    """
    units = divide(SPEC)
    reqs = _reqs(SPEC, units,
                 UnitClassification(unit_kind="scaffolding",
                                    text="This heading introduces the adder."),
                 _ok("The cout output is a and b.", ("cout",)))
    assert len(reqs) == 2
    assert reqs[0]["unit_kind"] == "scaffolding"
    assert reqs[0]["text"] == "This heading introduces the adder."


def test_classify_cannot_move_or_replace_the_core_span():
    """It may APPEND a supporting span; the core is never rewritten."""
    units = divide(SPEC)
    reqs = _reqs(SPEC, units,
                 _ok(supporting_units=[units[1].start]),
                 _ok("The cout output is a and b.", ("cout",)))
    spans = reqs[0]["spec_spans"]
    assert [s0["role"] for s0 in spans] == ["core", "supporting"]
    assert (spans[0]["start"], spans[0]["end"]) == (units[0].start, units[0].end)
    assert (spans[1]["start"], spans[1]["end"]) == (units[1].start, units[1].end)


def test_a_supporting_unit_is_linked_as_an_obligation_never_asserted_on():
    """Every unit is a requirement, so a supporting span is also a supporting
    OBLIGATION -- recorded as a link, and never a second thing to check."""
    units = divide(SPEC)
    reqs = _reqs(SPEC, units,
                 _ok(supporting_units=[units[1].start]),
                 _ok("The cout output is a and b.", ("cout",)))
    assert reqs[0]["supports"] == ["REQ-0001"]
    cores = [s0 for s0 in reqs[0]["spec_spans"] if s0["role"] == "core"]
    assert len(cores) == 1, "exactly one span is what a check must satisfy"


def test_a_requirement_marks_which_of_its_fields_are_supportive():
    units = divide(SPEC)
    reqs = _reqs(SPEC, units, _ok(), _ok("The cout output is a and b.", ("cout",)))
    assert set(reqs[0]["supportive"]) == {"text", "ports", "unit_kind", "supports"}
    assert "spec_spans" not in reqs[0]["supportive"], "the core is not supportive"


def test_a_unit_cannot_support_itself():
    units = divide(SPEC)
    reqs = _reqs(SPEC, units,
                 _ok(supporting_units=[units[0].start]),
                 _ok("The cout output is a and b.", ("cout",)))
    assert [s0["role"] for s0 in reqs[0]["spec_spans"]] == ["core"]
    assert reqs[0]["supports"] == []


def test_divide_and_classify_runs_every_unit(monkeypatch):
    """The stage wiring: one call per unit per stage, serial when replaying."""
    seen: list[str] = []
    units, results, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=_s1_port(set(), seen),
        fanout=False)
    assert len(units) == 2
    assert all(r.ok for r in results), [r.issues for r in results]
    assert len(reqs) == 2
    # The stage name is keyed by BOTH offsets, not by index: a re-division
    # cannot collide with a fixture recorded against a different partition, and
    # naming by the start alone was one-sided -- a divider change that moves
    # only a unit's END would have replayed the longer unit's response.
    assert seen == (
        [f"boundary_{u.start}_{u.end}" for u in units]
        + [f"classify_{u.start}_{u.end}" for u in units]
    )


# ------------------------------------------------------- merging units


def _s1_port(continuing, seen):
    """A stub answering BOTH S1 stages.

    `continuing` names the boundary stages that answer yes. The classify half
    returns ONE restatement, because that is the only shape the schema admits.
    """

    class _P:
        def complete(self, *, stage, round_, prompt):
            seen.append(stage)
            if stage.startswith("boundary_"):
                return json.dumps({"reasoning": "-",
                                   "continues_previous": stage in continuing})
            return json.dumps({"kind": "behavioural",
                               "text": "The sum output is driven.",
                               "ports": ["sum"]})
    return _P()


def test_the_boundary_pass_runs_before_classification():
    """The order is the design: no unit is classified at a granularity that a
    later step is about to revise."""
    units = divide(SPEC)
    assert len(units) == 2
    seen: list[str] = []
    divide_and_classify(spec=SPEC, contract_json=CONTRACT,
                        port=_s1_port(set(), seen), fanout=False)
    assert [x.split("_")[0] for x in seen] == [
        "boundary", "boundary", "classify", "classify"], seen


def test_a_continuation_merges_the_units_and_classify_sees_the_whole_block():
    """The point is not a wider span: it is that ONE call authors the
    requirement from ALL the text it rests on.

    Under the fold the surviving requirement was written by a call that saw only
    the anchor unit, and the continuation's text was appended to its span
    afterwards -- c1-i2c's REQ-0083 carried 1,369 characters and stated one
    sentence's worth of it.
    """
    units = divide(SPEC)
    seen: list[str] = []
    port = _s1_port({f"boundary_{units[1].start}_{units[1].end}"}, seen)

    merged, results, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=port, fanout=False)

    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (units[0].start, units[1].end)
    # Both boundary calls, then ONE classify call over the merged block.
    assert seen == [
        f"boundary_{units[0].start}_{units[0].end}",
        f"boundary_{units[1].start}_{units[1].end}",
        f"classify_{merged[0].start}_{merged[0].end}",
    ]
    assert len(reqs) == 1
    span = reqs[0]["spec_spans"][0]
    assert (span["start"], span["end"]) == (units[0].start, units[1].end)


def test_nothing_chaining_leaves_the_scaffold_and_classifies_it_once():
    seen: list[str] = []
    units, _, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=_s1_port(set(), seen),
        fanout=False)
    assert len(units) == 2 and len(reqs) == 2
    assert sum(x.startswith("classify_") for x in seen) == 2


def test_a_run_of_continuations_becomes_ONE_merged_unit():
    """Three consecutive flags make one block of four, not three pairwise
    merges. Continuation is transitive: each flag is relative to its immediate
    predecessor, so the chain is what keeps a merged unit contiguous."""
    from specflow.s1_classify import _chains

    assert _chains([False, True, True, False, True]) == [[0, 1, 2], [3, 4]]
    # A flag on index 0 has nothing to join; `gate_boundary` also rejects it.
    assert _chains([True, False]) == [[0], [1]]


def test_merge_false_skips_the_boundary_pass_entirely():
    seen: list[str] = []
    units, _, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, fanout=False, merge=False,
        port=_s1_port({f"boundary_{u.start}_{u.end}" for u in divide(SPEC)}, seen))
    assert len(units) == 2 and len(reqs) == 2
    assert not any(x.startswith("boundary_") for x in seen), seen


def test_the_first_unit_cannot_continue_anything():
    from specflow.s1_classify import BoundaryDecision, gate_boundary

    yes = BoundaryDecision(continues_previous=True)
    assert gate_boundary(yes, index=0), "index 0 has nothing before it"
    assert gate_boundary(yes, index=1) == []


def test_a_headless_boundary_response_is_a_parse_error_not_a_no():
    """`False` is a real answer, so a truncated response must not default to it.

    Measured at 1.5% of classify calls on c1-i2c and 3.6% on n3-i2c -- not rare
    enough to leave defaulting.
    """
    from specflow.s1_classify import parse_boundary

    out = parse_boundary('"reasoning": "It completes the sentence before it.",\n'
                         '  "some_inner": {"a": 1}}')
    assert out.reasoning.startswith("Parse Error: ")
    assert gate_boundary_error(out)


def gate_boundary_error(out):
    from specflow.s1_classify import gate_boundary
    return any(i.severity == "error" for i in gate_boundary(out, index=3))
