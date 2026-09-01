"""D2 + G1': per-unit classification and the atomicity gate.

G1' is load-bearing on its own. Fanning S2 out one-to-one makes G2's
"uncovered requirement" check vacuous, so the completeness argument moves here:
a unit's obligations must tile it, and an obligation may never reach outside its
own unit. Those two together are what make the 100%-of-spec catch-all
structurally impossible rather than merely penalised.
"""

from __future__ import annotations

import json
import os

from specflow.divide import divide
from specflow.s1_classify import (
    PREFIX_SENTINEL,
    Obligation,
    UnitClassification,
    build_prompt,
    divide_and_classify,
    gate_unit,
    parse_response,
    shared_prefix,
    to_requirements,
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


def _ok(body_len, *obligations):
    return UnitClassification(kind="behavioural", obligations=list(obligations))


# ------------------------------------------------------------------ the gate


def test_a_tiling_partition_passes():
    u = _unit()
    out = _ok(u.length, Obligation(start=0, end=u.length, text="The sum output is a xor b.", ports=["sum"]))
    assert gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT)) == []


def test_an_uncovered_stretch_of_the_unit_is_an_error():
    """This replaces "unattributed spec text", scoped to a unit.

    Scoping is the point: unattributed-text-over-the-whole-spec is answerable
    with one enormous span, and was, twice. Unattributed-text-within-one-unit is
    not, because a span cannot reach outside its unit.
    """
    u = _unit()
    out = _ok(u.length, Obligation(start=0, end=8, text="The sum output is driven.", ports=["sum"]))
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert has_errors(issues)
    assert any(i.kind == "uncovered" for i in issues)


def test_overlapping_obligations_are_an_error():
    u = _unit()
    out = _ok(
        u.length,
        Obligation(start=0, end=15, text="The sum output is driven.", ports=["sum"]),
        Obligation(start=10, end=u.length, text="The sum output equals a xor b.", ports=["sum"]),
    )
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert any("overlap" in i.message for i in issues)


def test_a_span_reaching_outside_its_unit_is_an_error():
    """The check that makes the catch-all unavailable rather than discouraged."""
    u = _unit()
    out = _ok(u.length, Obligation(start=0, end=u.length + 500, text="Everything.", ports=["sum"]))
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert any("not inside the unit" in i.message for i in issues)


def test_a_restatement_opening_with_a_back_reference_is_an_error():
    """The 15-28% failure mode, checked on the restatement rather than the spec.

    The model authors the restatement, so this is checkable without touching
    spec text -- which it must not.
    """
    u = _unit()
    for opener in ("It is a xor b.", "This is a xor b.", "Also, sum is a xor b.",
                   "Otherwise sum is a xor b."):
        out = _ok(u.length, Obligation(start=0, end=u.length, text=opener, ports=["sum"]))
        issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
        assert any("unresolved reference" in i.message for i in issues), opener


def test_a_self_contained_restatement_passes():
    u = _unit()
    out = _ok(u.length, Obligation(start=0, end=u.length,
                                   text="The sum output is a xor b.", ports=["sum"]))
    assert not has_errors(gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT)))


def test_two_obligations_in_one_restatement_are_an_error():
    u = _unit()
    out = _ok(u.length, Obligation(
        start=0, end=u.length,
        text="The sum shall be a xor b and the carry shall be a and b.", ports=["sum"]))
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert any("more than one obligation" in i.message for i in issues)


def test_one_obligation_over_two_ports_is_not_split():
    """`drives SCL and SDA low` is one obligation. The check looks for a second
    subject-verb obligation, not for the word "and"."""
    u = _unit()
    out = _ok(u.length, Obligation(
        start=0, end=u.length,
        text="The design shall drive both scl_o and sda_o low.", ports=["sum"]))
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert not any("more than one obligation" in i.message for i in issues)


def test_a_short_span_is_never_rejected_for_being_short():
    """The reverted MIN_SPAN_CHARS regression, pinned.

    The half adder's `' - output cout'` is 13 characters and legitimate. No
    threshold stands in for atomicity here; over-splitting is punished
    downstream by G2 and G4 instead.
    """
    spec = " - output cout\n"
    u = divide(spec)[0]
    out = _ok(u.length, Obligation(start=0, end=u.length,
                                   text="The cout output is declared.", ports=["cout"]))
    assert gate_unit(out, unit=u, spec=spec, contract=json.loads(CONTRACT)) == []


def test_a_port_the_contract_does_not_declare_is_an_error():
    u = _unit()
    out = _ok(u.length, Obligation(start=0, end=u.length,
                                   text="The carry output is a and b.", ports=["carry"]))
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert any("not a port in the contract" in i.message for i in issues)


def test_a_non_behavioural_unit_returning_obligations_is_an_error():
    u = _unit()
    out = UnitClassification(kind="scaffolding", obligations=[
        Obligation(start=0, end=u.length, text="Something.", ports=[])])
    assert has_errors(gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT)))


def test_a_behavioural_unit_with_no_obligations_is_an_error():
    u = _unit()
    out = UnitClassification(kind="behavioural", obligations=[])
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
    assert any(i.kind == "uncovered" for i in issues)


def test_a_parse_error_short_circuits_every_other_check():
    u = _unit()
    out = UnitClassification(reasoning="Parse Error: bad json")
    issues = gate_unit(out, unit=u, spec=SPEC, contract=json.loads(CONTRACT))
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
    assert "<previous_unit>" in p and "The sum output is a xor b." in p
    assert "<next_unit>" not in p, "there is no unit after the last one"


def test_the_prompt_never_asks_for_spec_text_back():
    p = shared_prefix(SPEC, CONTRACT)
    assert "OFFSETS" in p and "NEVER quote" in p


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
    headless = (
        '"reasoning": "The unit states two observable actions.",\n'
        '  "kind_was_here_before_truncation": 1,\n'
        '  "obligations_list": [\n'
        '    {"start": 0, "end": 12, "text": "The FSM stalls.", "ports": []}\n'
        "  ]\n}"
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
    out = parse_response('{"reasoning": "A heading.", "kind": "scaffolding"}')
    assert out.kind == "scaffolding"
    assert not out.reasoning.startswith("Parse Error")
    assert gate_unit(out, unit=divide(SPEC)[0], spec=SPEC, contract=None) == []


# -------------------------------------------------------------- assembly


def test_requirements_carry_absolute_offsets_and_sequential_uids():
    units = divide(SPEC)
    results = [
        type("R", (), {"output": _ok(u.length, Obligation(
            start=0, end=u.length, text=f"Unit {i} is satisfied.", ports=[]))})()
        for i, u in enumerate(units)
    ]
    reqs = to_requirements(SPEC, units, results)
    assert [r["uid"] for r in reqs] == ["REQ-0000", "REQ-0001"]
    from specflow.s1_requirements import normalize_spec
    text = normalize_spec(SPEC)
    for r in reqs:
        span = r["spec_spans"][0]
        assert text[span["start"]:span["end"]] == span["quote"]


def test_a_requirements_span_is_the_whole_unit_not_the_obligation():
    """Obligations account for the unit; they never narrow what it is attributed to.

    REQ-0010 shipped with the span `" and glitch filtering."` -- a noun phrase
    from a feature list -- and the pipeline authored a check about a
    three-sample filter window from it. Offsets are the tiling gate's input and
    nothing else; the span recorded is the unit.
    """
    spec = "The counter counts up and it saturates on overflow.\n"
    units = divide(spec)
    assert len(units) == 1
    unit = units[0]
    results = [type("R", (), {"output": _ok(
        unit.length,
        Obligation(start=0, end=21, text="The counter counts up.", ports=[]),
        Obligation(start=21, end=unit.length,
                   text="The counter saturates on overflow.", ports=[]),
    )})()]
    reqs = to_requirements(spec, units, results)
    assert len(reqs) == 2
    for r in reqs:
        span = r["spec_spans"][0]
        assert (span["start"], span["end"]) == (unit.start, unit.end)
        assert span["quote"] == unit.text(spec)


def test_to_requirements_neither_folds_nor_widens_nor_drops():
    """Merging is resolved upstream, so this function is now purely mechanical.

    Three designs have passed through here. The original FOLDED a continuation
    into the previous requirement and deleted its obligations -- 42 of 169 on
    c1-i2c, 25%, silently, because the span survived and `assure` checks spans.
    The second kept the obligations and WIDENED their spans backwards, which
    stopped the loss but left two independent classifications standing, one per
    half of a thought, with no call having seen the whole. The third merges the
    UNITS and re-reads them, which happens in `divide_and_classify` before this
    is called.

    So a `continues_previous` still set on a result reaching here changes
    nothing: every unit is already as wide as it should be.
    """
    spec = "The FSM accepts a START.\n\nIt then drives SCL low.\n"
    units = divide(spec)
    assert len(units) == 2
    results = [
        type("R", (), {"output": _ok(units[0].length, Obligation(
            start=0, end=units[0].length,
            text="The FSM accepts a START condition.", ports=[]))})(),
        type("R", (), {"output": UnitClassification(
            kind="behavioural", continues_previous=True,
            obligations=[Obligation(start=0, end=units[1].length,
                                    text="The FSM drives SCL low.", ports=[])])})(),
    ]
    reqs = to_requirements(spec, units, results)
    assert len(reqs) == 2, "no requirement may be dropped"
    for r, u in zip(reqs, units):
        span = r["spec_spans"][0]
        assert (span["start"], span["end"]) == (u.start, u.end), "no widening"
        assert span["quote"] == u.text(spec)



def test_scaffolding_units_produce_no_requirements():
    units = divide(SPEC)
    results = [type("R", (), {"output": UnitClassification(kind="scaffolding")})()
               for _ in units]
    assert to_requirements(SPEC, units, results) == []


def test_divide_and_classify_runs_every_unit(monkeypatch):
    """The stage wiring: one call per unit, serial when replaying."""
    seen: list[str] = []

    class _Port:
        def complete(self, *, stage, round_, prompt):
            seen.append(stage)
            # The prompt declares the unit's length, so a caller never has to
            # re-derive it by slicing -- which this stub got wrong by one on its
            # first attempt, and the gate caught, which is the point of the gate.
            import re as _re
            length = int(_re.search(r'<unit kind="[^"]*" length="(\d+)"', prompt).group(1))
            return json.dumps({
                "kind": "behavioural",
                "obligations": [{"start": 0, "end": length,
                                 "text": "The sum output is driven.", "ports": ["sum"]}],
            })

    units, results, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=_Port(), fanout=False)
    assert len(seen) == len(units) == 2
    assert all(r.ok for r in results), [r.issues for r in results]
    assert len(reqs) == 2
    # The stage name is keyed by BOTH offsets, not by index: a re-division
    # cannot collide with a fixture recorded against a different partition, and
    # naming by the start alone was one-sided -- a divider change that moves
    # only a unit's END would have replayed the longer unit's response.
    assert seen == [f"classify_{u.start}_{u.end}" for u in units]


# ------------------------------------------------------- merging units


def _merging_port(flags, recorded):
    """A port that declares `continues_previous` for the units named in `flags`
    and records every stage it is asked for."""
    import re as _re

    class _P:
        def complete(self, *, stage, round_, prompt):
            recorded.append(stage)
            length = int(_re.search(r'<unit kind="[^"]*" length="(\d+)"', prompt).group(1))
            return json.dumps({
                "kind": "behavioural",
                "continues_previous": stage in flags,
                "obligations": [{"start": 0, "end": length,
                                 "text": "The sum output is driven.",
                                 "ports": ["sum"]}],
            })
    return _P()


def test_a_continuation_merges_the_two_units_and_is_re_read_as_one():
    """The scaffold is a first guess; `continues_previous` corrects it.

    The point is not a wider span. Widening leaves TWO classifications
    standing, one per half of a thought, with no call having seen the whole.
    Merging joins the units and asks again over the joined text, so a
    requirement straddling the boundary is authored once, from all of it.
    """
    units = divide(SPEC)
    assert len(units) == 2
    seen: list[str] = []
    # The SECOND unit says it continues the first.
    port = _merging_port({f"classify_{units[1].start}_{units[1].end}"}, seen)

    merged, results, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=port, fanout=False)

    assert len(merged) == 1, [u for u in merged]
    assert (merged[0].start, merged[0].end) == (units[0].start, units[1].end)
    # Pass one asked both units; pass two asked the merged block ONCE more.
    assert seen == [
        f"classify_{units[0].start}_{units[0].end}",
        f"classify_{units[1].start}_{units[1].end}",
        f"classify_{merged[0].start}_{merged[0].end}",
    ]
    assert len(reqs) == 1
    span = reqs[0]["spec_spans"][0]
    assert (span["start"], span["end"]) == (units[0].start, units[1].end)


def test_nothing_chaining_costs_no_second_pass():
    """The merge is not a tax on the common case: with no continuation the
    partition is unchanged, so re-asking would repeat the identical question."""
    seen: list[str] = []
    units, results, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, port=_merging_port(set(), seen),
        fanout=False)
    assert len(units) == 2
    assert len(seen) == 2, seen
    assert len(reqs) == 2


def test_a_run_of_continuations_becomes_ONE_merged_unit():
    """Three consecutive continuations make one block of four, not three pairs.

    The chain is what keeps a merged unit contiguous, and it closes at the first
    unit that stands on its own -- so a merge can never reach across the
    document, which is the property the catch-all ban rests on.
    """
    from specflow.s1_classify import UnitClassification, _chains

    def r(flag):
        return type("R", (), {"output": UnitClassification(
            kind="behavioural", continues_previous=flag)})()

    assert _chains([r(False), r(True), r(True), r(False), r(True)]) == [
        [0, 1, 2], [3, 4]]
    # Index 0 can never continue: there is nothing before it.
    assert _chains([r(True), r(False)]) == [[0], [1]]


def test_merge_false_returns_the_scaffold_untouched():
    seen: list[str] = []
    units, _, reqs = divide_and_classify(
        spec=SPEC, contract_json=CONTRACT, fanout=False, merge=False,
        port=_merging_port({f"classify_{u.start}_{u.end}" for u in divide(SPEC)}, seen))
    assert len(units) == 2 and len(seen) == 2 and len(reqs) == 2
