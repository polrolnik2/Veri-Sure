"""[P] -- the stage that turns the specification's nouns into declared signals.

What is pinned here is everything that does NOT need a model: the gate, the
artifact shape, and the orphan report. The four questions that need one -- does
it collapse three phrasings into one probe, does it quote rather than
paraphrase, does it recognise an alias, does it hypothesise only where the spec
says so -- are the live tests, run against a real author.
"""
from __future__ import annotations

from pathlib import Path

from specflow import probes

SPEC = (Path(__file__).parent / "fixtures" / "probes" / "synthetic_spec.txt").read_text()

CONTRACT = {"module_name": "dcfsm", "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "req", "dir": "input", "width": 1},
    {"name": "burst", "dir": "output", "width": 1},
    {"name": "saved_addr", "dir": "output", "width": 32},
]}

REQS = [{"uid": f"REQ-{u}", "text": t, "unit_kind": "behavioural"} for u, t in [
    ("0001", "On a request with a tag miss, the controller enters LREFILL3."),
    ("0002", "While in the line-refill state, no second request is accepted."),
]]


def _out(**kw) -> probes.ProbeOutput:
    return probes.ProbeOutput.model_validate({"reasoning": "ok", **kw})


def _probe(**kw) -> dict:
    base = {"name": "in_lrefill3", "notes": "the FSM is in LREFILL3",
            "licensed_by": ["REQ-0001"],
            "spans": ["the controller enters the LREFILL3 state"]}
    base.update(kw)
    return base


def _gate(out: probes.ProbeOutput):
    return probes.gate(out, contract=CONTRACT, spec=SPEC, requirements=REQS)


def test_a_well_formed_table_passes() -> None:
    assert _gate(_out(probes=[_probe()])) == []


def test_the_linters_rules_are_CALLED_not_reimplemented() -> None:
    """Width, licensing and span presence belong to one owner.

    The linter lints a contract however produced, so a second copy of those
    rules in this stage would be a second place for them to drift out of step.
    """
    for bad, expect in [
        ({"spans": ["a sentence that is not in the specification"]}, "span"),
        ({"licensed_by": []}, "licensed_by"),
    ]:
        issues = _gate(_out(probes=[_probe(**bad)]))
        assert issues, f"{bad} should have been refused"
        assert any(expect in i.path or expect in i.message for i in issues), issues


def test_a_probe_may_not_shadow_a_declared_port() -> None:
    """The alias case. `saved_addr_r` is `saved_addr` under another name.

    Declaring it hands the check author two names for one wire and inflates
    every count downstream.
    """
    issues = _gate(_out(probes=[_probe(name="saved_addr")]))
    assert any("already a declared port" in i.message for i in issues), issues


def test_a_probe_must_be_nameable_in_verilog() -> None:
    """It becomes a port of the generated module, so this is not cosmetic."""
    for name in ("in lrefill3", "In_LREFILL3", "3refill"):
        issues = _gate(_out(probes=[_probe(name=name)]))
        assert any("identifier" in i.message for i in issues), (name, issues)


def test_a_probe_may_not_cite_a_requirement_that_does_not_exist() -> None:
    issues = _gate(_out(probes=[_probe(licensed_by=["REQ-9999"])]))
    assert any("not requirements" in i.message for i in issues), issues


def test_a_cross_constraint_must_name_real_ports() -> None:
    """The whole point of one is that it ties a probe to what a design cannot
    lie about -- signals golden and the boolean miter can both see."""
    out = _out(probes=[_probe()], cross_constraints=[{
        "text": "While in LREFILL3, burst is asserted.", "probe": "in_lrefill3",
        "ports": ["not_a_port"], "span": "asserts burst"}])
    issues = _gate(out)
    assert any("not declared ports" in i.message for i in issues), issues


def test_the_contract_gains_probes_without_being_mutated() -> None:
    out = _out(probes=[_probe()], aliases=[
        {"term": "saved_addr_r", "port": "saved_addr", "why": "assigned from it"}])
    doc = probes.augmented(CONTRACT, out)
    assert len(CONTRACT["io"]) == 4, "the input contract was mutated"
    entry = next(p for p in doc["io"] if p["dir"] == "probe")
    assert entry["name"] == "in_lrefill3"
    # Width is not the model's to choose. A wider signal would need an encoding
    # the specification does not state, and inventing one is how ten checks were
    # previously made unfalsifiable.
    assert entry["width"] == 1
    assert doc["probes"] == ["in_lrefill3"]
    assert doc["probe_aliases"][0]["port"] == "saved_addr"


def test_cross_constraints_become_ORDINARY_requirements() -> None:
    """No new machinery: they go through normalize and every existing gate."""
    out = _out(probes=[_probe()], cross_constraints=[{
        "text": "While in LREFILL3, burst is asserted.", "probe": "in_lrefill3",
        "ports": ["burst"], "span": "asserts burst"}])
    reqs = probes.cross_constraint_requirements(out, REQS)
    assert len(reqs) == 1
    assert reqs[0]["unit_kind"] == "behavioural"
    assert reqs[0]["spec_spans"] == ["asserts burst"]
    assert reqs[0]["derived_from_probe"] == "in_lrefill3"
    # NOT a collision with an existing requirement. `mint(prefix, len(reqs))`
    # gives REQ-0002 here, which already exists -- the cross-constraint would
    # have silently replaced a real requirement.
    assert reqs[0]["uid"] not in {r["uid"] for r in REQS}
    assert reqs[0]["uid"] == "REQ-0003"


def test_cross_constraint_uids_do_not_collide_across_a_GAP() -> None:
    """Derived from the uids that exist, not from the count."""
    sparse = [{"uid": "REQ-0001"}, {"uid": "REQ-0007"}]
    out = _out(cross_constraints=[
        {"text": "one", "probe": "p", "ports": [], "span": "s"},
        {"text": "two", "probe": "p", "ports": [], "span": "s"}])
    reqs = probes.cross_constraint_requirements(out, sparse)
    assert [r["uid"] for r in reqs] == ["REQ-0008", "REQ-0009"]


def test_an_orphan_is_a_probe_no_activation_or_effect_names() -> None:
    """Reported, never enforced, and it has two opposite readings.

    If a licensing requirement's TEXT names the state but its activation does
    not, normalize failed to use a declared probe. If no requirement's
    activation depends on the state, [P] over-nominated.
    """
    doc = probes.augmented(CONTRACT, _out(probes=[
        _probe(), _probe(name="in_nowhere",
                         spans=["the controller idles until a request arrives"])]))
    normalized = [{"req_uid": "REQ-0001",
                   "activation": {"opens_on": [{"in_lrefill3": 1}], "until": [],
                                  "aborts_on": [], "sustains": []},
                   "observable": ["burst"]}]
    assert probes.orphans(doc, normalized) == ["in_nowhere"]


def test_a_probe_named_only_as_an_EFFECT_is_not_an_orphan() -> None:
    """The override case: a transition obligation asserts ON the state."""
    doc = probes.augmented(CONTRACT, _out(probes=[_probe()]))
    normalized = [{"req_uid": "REQ-0001",
                   "activation": {"opens_on": [], "until": [], "aborts_on": [],
                                  "sustains": []},
                   "observable": ["in_lrefill3"]}]
    assert probes.orphans(doc, normalized) == []


def test_a_parse_failure_is_an_issue_not_an_empty_table() -> None:
    """An unparseable answer must not read as 'this design has no states'."""
    out = probes.parse_response("not json at all")
    assert out.reasoning.startswith("Parse Error: ")
    assert _gate(out)


def test_the_prompt_carries_the_spec_the_requirements_and_the_contract() -> None:
    prompt = probes.build_prompt(requirements=REQS,
                                 contract_json='{"io": []}', spec=SPEC)
    assert "REQ-0001" in prompt
    assert "OR1200_DC_STORE_REFILL" in prompt, "the spec did not reach the author"
    assert "<contract_json>" in prompt
    # The three rules a gate cannot recover from if the author never hears them.
    assert "ONE SITUATION GETS ONE PROBE" in prompt
    assert "VERBATIM" in prompt
    assert "ONE BIT" in prompt
