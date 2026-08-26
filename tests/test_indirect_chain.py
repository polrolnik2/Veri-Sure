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

SEER = json.dumps({"normalized": [{
    "req_uid": "REQ-0001",
    "activation": {"text": "a START is detected", "inputs": {"sda_i": 0}},
    "observable": ["busy"], "expectation": "busy rises"}]})

ROUTED = json.dumps({"normalized": [{
    "req_uid": "REQ-0002",
    "observed_via": [{
        "port": "busy", "through_req": "REQ-0001",
        "when": "after a glitch narrower than the filter depth",
        "shows": "busy stays low for a narrow glitch and rises for a wide one"}],
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
