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


def test_a_continuation_keeps_its_requirement_and_widens_the_span():
    """The fold used to DELETE the continuation's obligations.

    Measured on c1-i2c, that discarded 42 of the 169 obligations the classifier
    authored -- 25% -- including the one sentence that stated the filter's
    sampling interval as `clk_cnt >> 2`, which is why the filter cluster had no
    threshold to quote. The span survived, so `assure` saw nothing missing and
    the loss was silent. See docs/evidence/continuations.md.
    """
    spec = "The FSM accepts:\n\n  - a START condition\n"
    units = divide(spec)
    results = [
        type("R", (), {"output": UnitClassification(
            kind="behavioural",
            obligations=[Obligation(start=0, end=units[0].length,
                                    text="The FSM accepts commands.", ports=[])])})(),
        type("R", (), {"output": UnitClassification(
            kind="behavioural", continues_previous=True,
            obligations=[Obligation(start=0, end=units[1].length,
                                    text="The FSM accepts a START.", ports=[])])})(),
    ]
    from specflow.s1_requirements import normalize_spec
    text = normalize_spec(spec)
    reqs = to_requirements(spec, units, results)

    assert [r["text"] for r in reqs] == [
        "The FSM accepts commands.", "The FSM accepts a START."]
    stem, item = (r["spec_spans"][0] for r in reqs)
    # The stem is untouched; the item reaches back to it.
    assert (stem["start"], stem["end"]) == (units[0].start, units[0].end)
    assert (item["start"], item["end"]) == (units[0].start, units[1].end)
    for sp in (stem, item):
        assert sp["quote"] == text[sp["start"]:sp["end"]]


def test_a_chain_of_continuations_anchors_on_the_unit_that_stands_alone():
    """Three in a row all reach back to the stem, not each to the one before.

    Anchoring one unit back would leave the third continuation's span starting
    inside the chain, where its subject is not named -- which is the fragment
    problem the widening exists to prevent.
    """
    spec = "The FSM accepts:\n\n  - START\n  - STOP\n  - a WRITE of one bit\n"
    units = divide(spec)
    assert len(units) == 4
    results = [
        type("R", (), {"output": UnitClassification(
            kind="scaffolding")})(),          # the stem states nothing itself
        *(type("R", (), {"output": UnitClassification(
            kind="behavioural", continues_previous=True,
            obligations=[Obligation(start=0, end=u.length,
                                    text=f"The FSM accepts {i}.", ports=[])])})()
          for i, u in enumerate(units[1:])),
    ]
    reqs = to_requirements(spec, units, results)
    assert len(reqs) == 3
    for r, u in zip(reqs, units[1:]):
        span = r["spec_spans"][0]
        assert (span["start"], span["end"]) == (units[0].start, u.end)


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
    # The stage name is keyed by offset, not index: a re-division cannot collide
    # with a fixture recorded against a different partition.
    assert seen == [f"classify_{u.start}" for u in units]
