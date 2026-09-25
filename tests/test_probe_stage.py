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


# --------------------------------------------------------------- on by default

def test_probes_are_ON_by_default_and_can_be_turned_off() -> None:
    """The switch has to exist at both levels or an A/B arm is impossible.

    `[P]` is one model call, and it is the one that decides whether a check can
    NAME the situation its requirement is about or has to guess at it from
    output combinations -- 0 of 11 to 5 of 11 on the requirements whose bodies
    use one. It is on. But a comparison arm needs to turn it off from the
    caller, not one level down.
    """
    import inspect

    from eda_agent.specflow_node import run_specflow_node
    from specflow.integration import build_artifacts

    for fn in (build_artifacts, run_specflow_node):
        param = inspect.signature(fn).parameters["enable_probes"]
        assert param.default is True, fn.__name__


def test_a_port_failure_propagates_and_is_CAUGHT_AT_THE_CALL_SITE() -> None:
    """`[P]` must be NON-FATAL, and its comment claimed that while the code did
    not implement it.

    `run_stage` calls `port.complete` bare. A `ReplayPort` raises
    `FileNotFoundError` for a stage it has no recording of, and a `FilePort`
    raises `PendingResponse`. Invisible while the stage defaulted off; on by
    default and unwrapped, that takes down every run directory recorded before
    probes existed.

    The guard is deliberately at the CALL SITE rather than in `run_probes`,
    because that is where the contract to fall back to is in scope -- returning
    a sentinel from here would make every caller re-derive it. So this pins two
    things: the failure really does propagate out of the stage, and the caller
    really does wrap it.

    The end-to-end evidence is `tests/test_specflow_reuse.py`, whose ports have
    no `probes` recording at all: those nine tests pass only because the guard
    holds.
    """
    import inspect

    import pytest

    from specflow import integration

    class _Exploding:
        def complete(self, *, stage, round_, prompt):
            raise FileNotFoundError("no recorded response for 'probes'")

    with pytest.raises(FileNotFoundError):
        probes.run_probes(requirements=REQS, contract=CONTRACT,
                          contract_json='{"io": []}', spec=SPEC,
                          port=_Exploding())

    src = inspect.getsource(integration.build_artifacts)
    guarded = src[src.index("run_probes("):]
    assert "except Exception" in guarded[:1200], (
        "the call to run_probes is not wrapped -- a missing recording or a "
        "gateway error would take down the whole build")


def test_the_stage_records_that_it_RAN_even_when_it_produced_nothing(tmp_path) -> None:
    """What makes `reuse` mean what it says.

    An empty table is a real answer -- a specification may name no state at all
    -- and a run directory whose stage produced nothing must not re-attempt it
    on every resume. The `error` field is what tells a reader it was a failure
    rather than a spec with no states in it.
    """
    import json

    path = probes.write_artifacts(tmp_path, CONTRACT, None, error="port exploded")
    held = json.loads(path.read_text())
    assert held["probes"] == []
    assert held["error"] == "port exploded"
    assert held["rounds"] == 0
