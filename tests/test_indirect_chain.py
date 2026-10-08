"""The route survives every hand-off, in the order a run makes them.

Each stage's use of `observed_via` is pinned on its own elsewhere. This drives
them IN SEQUENCE, from one blind requirement through to a frozen oracle set,
because every one of those hand-offs is a place a field can be computed and then
dropped -- which is what `covers`, `unobservable()` and `stimulus_liveness` each
did before something looked.
"""

from __future__ import annotations

import json

from specflow.normalize import resolve_indirect, run_normalize_fanout
from specflow.normalize import write_artifacts as write_normalized

CONTRACT = {
    "module_name": "filt",
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "sda_i", "dir": "input", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
    ],
}
CONTRACT_JSON = json.dumps(CONTRACT)

REQS = [
    {"uid": "REQ-0001", "text": "when a START is detected, busy rises"},
    {"uid": "REQ-0002", "text": "the input filter suppresses a short glitch, "
                                "so no START is detected"},
]

#: The blind one, as the FIRST pass sees it -- no port of its own, and the third
#: answer: it suspects a boundary effect it cannot name a port for.
BLIND = json.dumps({"normalized": [{
    "req_uid": "REQ-0002",
    "activation": {"text": "a glitch on sda_i", "inputs": {"sda_i": 0}},
    "observable": [],
    "unobservable_reason": ("not visible on any port this requirement names; "
                            "the effect is that no START is detected"),
    "expectation": "no START is detected"}]})

#: The DIRECTLY observable one. It carries an `observed_via` naming its own
#: port with an empty `through_req`, because that is what `gate_one` requires of
#: a first-pass answer -- the route is the base case, not an indirect-only
#: field. This fixture asserted `observable: ["busy"]` with no route until the
#: merge started honouring `StageResult.ok`, at which point it stopped shipping
#: and five tests here failed. It was always gate-failing; nothing had ever
#: read the verdict.
SEER = json.dumps({"normalized": [{
    "req_uid": "REQ-0001",
    "activation": {"text": "a START is detected", "inputs": {"sda_i": 0}},
    "observable": ["busy"],
    "observed_via": [{
        "port": "busy", "through_req": "",
        "when": "after a START-shaped edge on sda_i while scl_i is high",
        "shows": "busy is high once a START has been detected",
        "otherwise": "busy stays low when none has"}],
    "expectation": "busy rises"}]})

ROUTED = json.dumps({"normalized": [{
    "req_uid": "REQ-0002",
    "observed_via": [{
        "port": "busy", "through_req": "REQ-0001",
        "when": "after a glitch narrower than the filter depth",
        "shows": "busy rises for a wide one",
        "otherwise": "busy stays low for a narrow one"}],
    "activated_via": []}]})


class _Port:
    """Answers by stage name, and records every prompt it was given."""

    def __init__(self, by_stage: dict):
        self.by_stage, self.seen = dict(by_stage), []

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.seen.append((stage, prompt))
        for key, reply in self.by_stage.items():
            if key in stage:
                return reply
        raise AssertionError(f"no scripted reply for stage {stage!r}")

    def prompt_for(self, fragment: str) -> str:
        for stage, prompt in self.seen:
            if fragment in stage:
                return prompt
        raise AssertionError(f"no stage matched {fragment!r}: "
                             f"{[s for s, _ in self.seen]}")


def _normalized():
    port = _Port({"normalize_indirect_REQ-0002": ROUTED,
                  "normalize_REQ-0001": SEER, "normalize_REQ-0002": BLIND})
    shapes, _ = run_normalize_fanout(
        requirements=REQS, contract_json=CONTRACT_JSON, contract=CONTRACT,
        port=port, fanout=False)
    merged, _ = resolve_indirect(
        normalized=shapes, requirements=REQS, contract_json=CONTRACT_JSON,
        contract=CONTRACT, port=port, fanout=False)
    return merged, port


def test_the_first_pass_leaves_it_blind_and_the_second_routes_it():
    merged, port = _normalized()
    by_uid = {n.req_uid: n for n in merged}
    assert by_uid["REQ-0001"].observable == ["busy"], "the direct one is untouched"
    blind = by_uid["REQ-0002"]
    assert blind.observable == ["busy"], "decidable at the route's port"
    assert blind.indirect and blind.observed_via[0].through_req == "REQ-0001"
    assert blind.unobservable_reason == ""


def test_only_the_blind_requirement_is_asked_the_second_question():
    _, port = _normalized()
    asked = [s for s, _ in port.seen if "indirect" in s]
    assert asked == ["normalize_indirect_REQ-0002"]


def test_the_second_pass_sees_the_other_requirement_s_port():
    """It cannot name a route without them, which is why this pass exists at
    all and why it runs after the merge rather than inside the fan-out."""
    _, port = _normalized()
    prompt = port.prompt_for("indirect")
    assert "REQ-0001" in prompt and '"busy"' in prompt
    assert "the effect is that no START is detected" in prompt, (
        "the first pass's suspicion reaches the second")


def test_the_route_survives_the_artifact_round_trip(tmp_path):
    """Written and read back as dicts -- the shape every downstream stage
    actually receives, which is not the pydantic model."""
    merged, _ = _normalized()
    write_normalized(tmp_path, merged, [])
    blob = json.loads((tmp_path / "specflow" / "normalized.json").read_text())
    shapes = {n["req_uid"]: n for n in blob["normalized"]}
    route = shapes["REQ-0002"]["observed_via"][0]
    assert route["port"] == "busy" and route["through_req"] == "REQ-0001"
    assert "rises for a wide one" in route["shows"]
    assert "REQ-0002" not in blob["unobservable"], "no longer a spec defect"


def test_the_route_reaches_s2_s3_and_the_oracle_author(tmp_path):
    """The three hand-offs after normalisation, in the order a run makes them."""
    from specflow.refmodel.oracle_gen import build_prompt as oracle_prompt
    from specflow.s2_testplan import build_prompt_one as s2_prompt
    from specflow.s3_coverage import build_prompt_one as s3_prompt

    merged, _ = _normalized()
    write_normalized(tmp_path, merged, [])
    blob = json.loads((tmp_path / "specflow" / "normalized.json").read_text())
    by_uid = {n["req_uid"]: n for n in blob["normalized"]}
    shape = by_uid["REQ-0002"]

    s2 = s2_prompt(REQS[1], CONTRACT_JSON, normalized=shape)
    assert "PLAN BOTH CASES" in s2 and "REQ-0001" in s2

    s3 = s3_prompt({"uid": "TP-0007", "covers": ["REQ-0002@1"]},
                   CONTRACT_JSON, normalized=shape)
    assert "OBSERVED AT ANOTHER REQUIREMENT'S PORT" in s3

    author = oracle_prompt(requirement=REQS[1], contract_json=CONTRACT_JSON,
                           contract=CONTRACT, normalized=shape)
    assert "THE PORT BELONGS TO ANOTHER REQUIREMENT" in author
    assert "rises for a wide one" in author, "the discrimination reaches it"

    # And the direct requirement is told none of it.
    direct = s2_prompt(REQS[0], CONTRACT_JSON, normalized=by_uid["REQ-0001"])
    assert "PLAN BOTH CASES" not in direct


def test_a_requirement_with_no_route_stays_blind_and_carries_its_reason():
    """The honest "no route" answer. The oracle stage is what turns having been
    ASKED into ABANDONED -- see `test_oracles_stage`."""
    port = _Port({"normalize_indirect_REQ-0002":
                  json.dumps({"normalized": [{"req_uid": "REQ-0002"}]}),
                  "normalize_REQ-0001": SEER, "normalize_REQ-0002": BLIND})
    shapes, _ = run_normalize_fanout(
        requirements=REQS, contract_json=CONTRACT_JSON, contract=CONTRACT,
        port=port, fanout=False)
    merged, _ = resolve_indirect(
        normalized=shapes, requirements=REQS, contract_json=CONTRACT_JSON,
        contract=CONTRACT, port=port, fanout=False)
    blind = {n.req_uid: n for n in merged}["REQ-0002"]
    assert blind.unobservable and blind.observed_via == []
    assert "no START is detected" in blind.unobservable_reason


# ------------------------------- a form that failed its gate does not ship


def test_a_form_that_never_passed_its_gate_is_absent_from_merged():
    """MEASURED: 15 of c1-i2c's 122 shipped this way, every one carrying
    "observable at [...] but no route given" -- which hands the check author a
    port it may assert anything about. REQ-0094 did exactly that.

    Not a quality claim: 39% of checks from flagged requirements are refuted by
    the known-good control against 39% from clean ones. The pipeline stops
    acting on a claim its own gate rejected, which is a different argument and
    the one that holds.
    """
    bad = json.dumps({"normalized": [{
        "req_uid": "REQ-0001",
        "activation": {"text": "a START is detected", "inputs": {"sda_i": 0}},
        "observable": ["busy"],          # ... and no `observed_via`
        "expectation": "busy rises"}]})
    port = _Port({"normalize_REQ-0001": bad, "normalize_REQ-0002": BLIND,
                  "normalize_indirect_REQ-0002": ROUTED})
    merged, results = run_normalize_fanout(
        requirements=REQS, contract_json=CONTRACT_JSON, contract=CONTRACT,
        port=port, max_repairs=0, fanout=False)
    assert "REQ-0001" not in {n.req_uid for n in merged}
    assert not results[0].ok


def test_what_did_not_ship_is_named_and_reasoned_rather_than_dropped_quietly():
    """Dropped from the loop, never dropped from the report. A build that
    passes with N requirements carrying no check has to say N."""
    from specflow.normalize import malformed

    bad = json.dumps({"normalized": [{
        "req_uid": "REQ-0001", "observable": ["busy"],
        "activation": {"text": "t", "inputs": {"sda_i": 0}},
        "expectation": "e"}]})
    port = _Port({"normalize_REQ-0001": bad, "normalize_REQ-0002": BLIND,
                  "normalize_indirect_REQ-0002": ROUTED})
    _, results = run_normalize_fanout(
        requirements=REQS, contract_json=CONTRACT_JSON, contract=CONTRACT,
        port=port, max_repairs=0, fanout=False)
    report = malformed(REQS, results)
    assert "REQ-0001" in report
    assert any("no route given" in why for why in report["REQ-0001"])
    assert "REQ-0002" not in report, "one that passed is not reported"


def test_malformed_is_not_abandoned():
    """ABANDONED means "attempted and exhausted" and routes to the spec author.
    This is the NORMALIZER returning a structure its own gate rejects, and it
    routes to whoever owns that prompt. Filing one as the other hides a prompt
    defect inside a spec-quality count."""
    from specflow import normalize as N
    from specflow.refmodel import verdict as V

    assert "ABANDONED" not in (N.malformed.__doc__ or "").split("DELIBERATELY")[0]
    assert "ABANDONED" in V.ROUTE
    assert "MALFORMED" not in V.ROUTE, "different stage, different reader"


# --------------------------- `observed_via` is not the indirect flag


def test_a_direct_route_does_not_make_a_requirement_indirect():
    """MEASURED, and this is what the blocking merge exposed. The first-pass
    gate REQUIRES a route on every observable requirement, so a directly
    observable one carries one naming its own port with an empty `through_req`.
    Branching on the presence of `observed_via` therefore fires on almost
    everything: 109 of c1-i2c's 122 carry it and only 33 name a `through_req`,
    so 76 requirements were told the port belonged to someone else.
    """
    from specflow.s2_testplan import borrowed

    direct = {"observed_via": [{"port": "busy", "through_req": "",
                                "when": "w", "shows": "s", "otherwise": "o"}]}
    indirect = {"observed_via": [{"port": "busy", "through_req": "REQ-0001",
                                  "when": "w", "shows": "s", "otherwise": "o"}]}
    assert borrowed(direct) == []
    assert len(borrowed(indirect)) == 1
    assert borrowed({}) == [] and borrowed(None) == []
    mixed = {"observed_via": direct["observed_via"] + indirect["observed_via"]}
    assert len(borrowed(mixed)) == 1, "only the borrowed one counts"


def test_the_indirect_note_reaches_only_the_borrowed_requirement():
    from specflow import s2_testplan, s3_coverage

    direct = {"observable": ["busy"],
              "observed_via": [{"port": "busy", "through_req": "",
                                "when": "w", "shows": "s", "otherwise": "o"}]}
    req = {"uid": "REQ-0001", "text": "t"}
    s2 = s2_testplan.build_prompt_one(req, CONTRACT_JSON, normalized=direct)
    assert "PLAN BOTH CASES" not in s2
    s3 = s3_coverage.build_prompt_one(
        {"tp_uid": "TP-0001", "covers": ["REQ-0001"]}, CONTRACT_JSON,
        normalized=direct)
    assert "OBSERVED AT ANOTHER REQUIREMENT'S PORT" not in s3
