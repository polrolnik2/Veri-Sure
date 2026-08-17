"""M2: S1's gate and repair loop, driven by a scripted port.

No model is involved. The port returns canned responses, so every branch of the
loop -- clean first try, repair-then-pass, exhaustion, unparseable output -- is
exercised deterministically. That is the point of splitting the model behind a
port: the loop's control flow is testable without the thing that makes it slow
and non-deterministic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from specflow.model_io import FilePort, PendingResponse, ReplayPort
from specflow.s1_requirements import (
    build_prompt,
    gate,
    normalize_spec,
    parse_response,
    renumber,
    run_s1,
)
from specflow.schema import RequirementsOutput, has_errors

SPEC = "The module adds a and b.\nOn overflow the output saturates.\n"
CONTRACT = json.dumps(
    {"module_name": "TopModule", "io": [{"name": n} for n in ("a", "b", "sum")]}
)


def span(fragment: str) -> dict:
    start = SPEC.index(fragment)
    return {"start": start, "end": start + len(fragment), "quote": fragment}


def req(uid: str, fragment: str, ports=("a", "b", "sum")) -> dict:
    return {
        "uid": uid,
        "text": f"requirement from {fragment[:20]}",
        "rev": 1,
        "spec_spans": [span(fragment)],
        "ports": list(ports),
        "needs": ["testplan", "refmodel"],
    }


LINE1, LINE2 = SPEC.split("\n")[0], SPEC.split("\n")[1]


def response(reqs: list[dict], underdetermined=()) -> str:
    return json.dumps(
        {"reasoning": "r", "requirements": reqs, "underdetermined": list(underdetermined)}
    )


COMPLETE = response([req("REQ-0000", LINE1), req("REQ-0001", LINE2)])
MISSING_SATURATION = response([req("REQ-0000", LINE1)])


@dataclass
class ScriptedPort:
    """Returns a canned reply per round, and records the prompts it was given."""

    replies: list[str]
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[min(round_, len(self.replies) - 1)]


# ---------------------------------------------------------------- the gate


def test_complete_decomposition_passes():
    out = parse_response(COMPLETE)
    assert gate(SPEC, out, json.loads(CONTRACT)) == []


def test_dropped_spec_sentence_is_caught():
    # The saturation clause is exactly the failure the pipeline exists to catch:
    # nothing downstream can notice a behaviour that never became a requirement.
    issues = gate(SPEC, parse_response(MISSING_SATURATION), json.loads(CONTRACT))
    assert has_errors(issues)
    assert any("saturates" in i.message for i in issues)


def test_port_not_in_contract_is_caught():
    bad = response([req("REQ-0000", LINE1, ports=("a", "carry_out")),
                    req("REQ-0001", LINE2)])
    issues = gate(SPEC, parse_response(bad), json.loads(CONTRACT))
    assert any("carry_out" in i.message for i in issues)


def test_unparseable_response_is_an_error_not_a_crash():
    out = parse_response("I'm afraid I can't do that")
    assert out.reasoning.startswith("Parse Error: ")
    assert has_errors(gate(SPEC, out, {}))


def test_empty_requirements_is_an_error():
    assert has_errors(gate(SPEC, parse_response(response([])), {}))


def test_duplicate_uid_is_an_error():
    dup = response([req("REQ-0000", LINE1), req("REQ-0000", LINE2)])
    issues = gate(SPEC, parse_response(dup), {})
    assert any("duplicate uid" in i.message for i in issues)


# ---------------------------------------------------------------- the loop


def test_clean_first_round_stops_immediately():
    port = ScriptedPort([COMPLETE])
    res = run_s1(spec=SPEC, contract_json=CONTRACT, port=port)
    assert res.ok and res.rounds == 1
    assert len(res.output.requirements) == 2


def test_repair_round_receives_the_defects_and_can_pass():
    port = ScriptedPort([MISSING_SATURATION, COMPLETE])
    res = run_s1(spec=SPEC, contract_json=CONTRACT, port=port)
    assert res.ok and res.rounds == 2
    # The second prompt must carry the gate's complaint, and only the current
    # one -- not an accumulated history of every prior attempt.
    assert "gate_failures" in port.prompts[1]
    assert "saturates" in port.prompts[1]
    assert "gate_failures" not in port.prompts[0]


def test_exhaustion_is_a_hard_failure_not_a_pass():
    port = ScriptedPort([MISSING_SATURATION])
    res = run_s1(spec=SPEC, contract_json=CONTRACT, port=port, max_repairs=2)
    assert not res.ok
    assert res.rounds == 3
    assert has_errors(res.issues)


def test_gate_does_not_soften_with_attempts():
    # Same defect every round; the verdict must be identical on the last round
    # as on the first. A gate that relaxes under pressure is not a gate.
    port = ScriptedPort([MISSING_SATURATION])
    a = run_s1(spec=SPEC, contract_json=CONTRACT, port=port, max_repairs=0)
    b = run_s1(spec=SPEC, contract_json=CONTRACT, port=ScriptedPort([MISSING_SATURATION]),
               max_repairs=3)
    assert [i.message for i in a.issues] == [i.message for i in b.issues]


# ---------------------------------------------------------------- renumber


def test_renumber_canonicalises_and_keeps_underdetermined_pointing_right():
    out = RequirementsOutput.model_validate(
        json.loads(response([req("REQ-0007", LINE1), req("REQ-0009", LINE2)],
                            [{"req_uid": "REQ-0009", "question": "what on overflow?"}]))
    )
    renumber(out)
    assert [r.uid for r in out.requirements] == ["REQ-0000", "REQ-0001"]
    assert out.underdetermined[0].req_uid == "REQ-0001"


# ---------------------------------------------------------------- ports


def test_file_port_emits_then_ingests(tmp_path):
    port = FilePort(root=tmp_path)
    try:
        port.complete(stage="s1", round_=0, prompt="PROMPT")
        raise AssertionError("should have raised PendingResponse")
    except PendingResponse as p:
        assert p.prompt_path.read_text() == "PROMPT"
        p.response_path.write_text(COMPLETE)

    assert port.complete(stage="s1", round_=0, prompt="PROMPT") == COMPLETE


def test_replay_port_is_deterministic_and_never_writes(tmp_path):
    (tmp_path / "s1_r0_response.txt").write_text(COMPLETE)
    port = ReplayPort(root=tmp_path)
    assert port.complete(stage="s1", round_=0, prompt="ignored") == COMPLETE
    # A prompt file must NOT appear: replay consults nothing and records nothing.
    assert not (tmp_path / "s1_r0_prompt.txt").exists()


def test_replay_port_is_explicit_when_a_fixture_is_missing(tmp_path):
    try:
        ReplayPort(root=tmp_path).complete(stage="s1", round_=0, prompt="x")
        raise AssertionError("should have raised")
    except FileNotFoundError as exc:
        assert "--model-port file" in str(exc)


def test_prompt_states_the_offset_convention():
    # G1 verifies character offsets, so the convention cannot be left implicit.
    prompt = build_prompt(SPEC, CONTRACT)
    assert str(len(normalize_spec(SPEC))) in prompt
    assert "0-based" in prompt


# --- the offset-agreement invariant ----------------------------------------
#
# Regression for a real M2 failure: build_prompt embedded `spec.rstrip()` while
# gate() checked offsets against the raw `spec`, and the prompt stated
# `len(spec)`. Every VerilogEval prompt begins with a blank line, so every span
# a model produced was rejected for a reason unrelated to its decomposition --
# the gate was measuring against text the model never saw.

LEADING_WS_SPEC = "\n" + SPEC + "\n\n"


def test_prompt_body_is_exactly_what_the_gate_measures():
    prompt = build_prompt(LEADING_WS_SPEC, CONTRACT)
    body = prompt.split("<specification>\n", 1)[1].split("\n</specification>", 1)[0]
    assert body == normalize_spec(LEADING_WS_SPEC)


def test_stated_length_matches_the_embedded_text():
    prompt = build_prompt(LEADING_WS_SPEC, CONTRACT)
    body = prompt.split("<specification>\n", 1)[1].split("\n</specification>", 1)[0]
    assert f"exactly {len(body)} characters" in prompt


def test_spans_computed_against_the_prompt_body_verify():
    # Offsets taken from the text the model is shown must satisfy the gate even
    # when the raw spec carries leading and trailing whitespace.
    body = normalize_spec(LEADING_WS_SPEC)
    frag = "On overflow the output saturates."
    start = body.index(frag)
    reqs = [
        {"uid": "REQ-0000", "text": "adds", "rev": 1, "ports": ["a", "b", "sum"],
         "needs": ["testplan"],
         "spec_spans": [{"start": 0, "end": start, "quote": body[:start]}]},
        {"uid": "REQ-0001", "text": "saturates", "rev": 1, "ports": ["sum"],
         "needs": ["testplan"],
         "spec_spans": [{"start": start, "end": len(body), "quote": body[start:]}]},
    ]
    out = parse_response(response(reqs))
    assert gate(LEADING_WS_SPEC, out, json.loads(CONTRACT)) == []
