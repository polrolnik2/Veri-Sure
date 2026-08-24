"""M3: G2 and G3, driven by scripted ports. No model involved.

Both stages reuse `stage.run_stage`, so the loop properties are already pinned by
the S1 tests; what is tested here is what each gate blocks on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from specflow.s2_testplan import gate as s2_gate
from specflow.s2_testplan import parse_response as s2_parse
from specflow.s2_testplan import run_s2
from specflow.s3_coverage import gate as s3_gate
from specflow.s3_coverage import parse_response as s3_parse
from specflow.s3_coverage import run_s3
from specflow.schema import has_errors

CONTRACT_OBJ = {
    "module_name": "TopModule",
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
        {"name": "cout", "dir": "output", "width": 1},
    ],
}
CONTRACT = json.dumps(CONTRACT_OBJ)

REQS = [
    {"uid": "REQ-0000", "rev": 1, "needs": ["testplan", "refmodel"]},
    {"uid": "REQ-0001", "rev": 1, "needs": ["testplan", "refmodel"]},
]
TPS = [
    {"uid": "TP-0000", "rev": 1, "covers": ["REQ-0000@1"], "needs": ["bin", "check"]},
    {"uid": "TP-0001", "rev": 1, "covers": ["REQ-0001@1"], "needs": ["bin", "check"]},
]


@dataclass
class ScriptedPort:
    replies: list[str]
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[min(round_, len(self.replies) - 1)]


def tp(uid: str, covers: list[str], dimension="D1_data_boundary", **over) -> dict:
    base = {
        "uid": uid, "rev": 1, "covers": covers, "dimension": dimension,
        "stimulus": "drive a=1,b=1", "expected_response": "sum=0, cout=1",
        "check_method": "compare against reference model",
        "needs": ["bin", "check"],
    }
    base.update(over)
    return base


def s2_response(elements: list[dict]) -> str:
    return json.dumps({"reasoning": "r", "elements": elements})


def s3_response(bins: list[dict], checks: list[dict]) -> str:
    return json.dumps({"reasoning": "r", "bins": bins, "checks": checks})


S2_GOOD = s2_response([tp("TP-0000", ["REQ-0000@1"]), tp("TP-0001", ["REQ-0001@1"])])

BIN0 = {"uid": "BIN-0000", "rev": 1, "covers": ["TP-0000@1"], "condition": "a and b are both 1"}
BIN1 = {"uid": "BIN-0001", "rev": 1, "covers": ["TP-0001@1"], "condition": "a and b are both 0"}
CHK0 = {"uid": "CHK-0000", "rev": 1, "covers": ["TP-0000@1"], "signals": ["sum"],
        "expr": "sum matches the reference model"}
CHK1 = {"uid": "CHK-0001", "rev": 1, "covers": ["TP-0001@1"], "signals": ["cout"],
        "expr": "cout matches the reference model"}
S3_GOOD = s3_response([BIN0, BIN1], [CHK0, CHK1])


# ---------------------------------------------------------------- G2


def test_s2_complete_testplan_passes():
    assert s2_gate(REQS, s2_parse(S2_GOOD)) == []


def test_s2_uncovered_requirement_blocks():
    issues = s2_gate(REQS, s2_parse(s2_response([tp("TP-0000", ["REQ-0000@1"])])))
    assert has_errors(issues)
    assert any(i.kind == "uncovered" and "REQ-0001" in i.path for i in issues)


def test_s2_bad_dimension_blocks():
    bad = s2_response([tp("TP-0000", ["REQ-0000@1"], dimension="D9_nonsense"),
                       tp("TP-0001", ["REQ-0001@1"])])
    assert any("D9_nonsense" in i.message for i in s2_gate(REQS, s2_parse(bad)))


def test_s2_empty_tuple_field_blocks():
    # An element without a stimulus is not a testpoint; it is a wish. Each field
    # maps to something the renderer must emit.
    bad = s2_response([tp("TP-0000", ["REQ-0000@1"], stimulus="  "),
                       tp("TP-0001", ["REQ-0001@1"])])
    issues = s2_gate(REQS, s2_parse(bad))
    assert any(i.path.endswith(".stimulus") for i in issues)


def test_s2_unpinned_revision_warns_but_does_not_block():
    out = s2_parse(s2_response([tp("TP-0000", ["REQ-0000"]), tp("TP-0001", ["REQ-0001@1"])]))
    issues = s2_gate(REQS, out)
    assert not has_errors(issues)
    assert any(i.kind == "outdated" for i in issues)


def test_s2_repairs_then_passes():
    port = ScriptedPort([s2_response([tp("TP-0000", ["REQ-0000@1"])]), S2_GOOD])
    res = run_s2(requirements=REQS, contract_json=CONTRACT, port=port)
    assert res.ok and res.rounds == 2
    assert "gate_failures" in port.prompts[1]


# ---------------------------------------------------------------- G3


def test_s3_complete_model_passes():
    assert s3_gate(TPS, s3_parse(S3_GOOD), CONTRACT_OBJ) == []


def test_s3_bin_without_check_blocks():
    # The purest vacuity failure: the scenario is reachable and nothing verifies
    # it. Coverable and unverifiable.
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, BIN1], [CHK0])), CONTRACT_OBJ)
    assert has_errors(issues)
    assert any(i.kind == "uncovered" and "TP-0001" in i.path for i in issues)


def test_s3_check_without_bin_blocks():
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0], [CHK0, CHK1])), CONTRACT_OBJ)
    assert any(i.kind == "uncovered" for i in issues)


def test_s3_check_on_unknown_signal_blocks():
    bad = dict(CHK1, signals=["carry_out"])
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, BIN1], [CHK0, bad])), CONTRACT_OBJ)
    assert any("carry_out" in i.message for i in issues)


def test_s3_check_on_an_input_blocks():
    # Comparing an input compares the stimulus against itself.
    bad = dict(CHK1, signals=["a"])
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, BIN1], [CHK0, bad])), CONTRACT_OBJ)
    assert any("is an input" in i.message for i in issues)


def test_s3_check_with_no_signals_blocks():
    bad = dict(CHK1, signals=[])
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, BIN1], [CHK0, bad])), CONTRACT_OBJ)
    assert any("names no signal" in i.message for i in issues)


def test_s3_prose_condition_only_warns():
    # Bin conditions are English. An unrecognised word is far more likely to be
    # a synonym than a hallucinated signal, so this must not stall a node.
    odd = dict(BIN1, condition="both operands are simultaneously deasserted")
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, odd], [CHK0, CHK1])), CONTRACT_OBJ)
    assert not has_errors(issues)


def test_s3_empty_condition_blocks():
    bad = dict(BIN1, condition="  ")
    issues = s3_gate(TPS, s3_parse(s3_response([BIN0, bad], [CHK0, CHK1])), CONTRACT_OBJ)
    assert any(i.path.endswith(".condition") and i.severity == "error" for i in issues)


def test_s3_repairs_then_passes():
    port = ScriptedPort([s3_response([BIN0], [CHK0]), S3_GOOD])
    res = run_s3(testplan=TPS, contract_json=CONTRACT, port=port)
    assert res.ok and res.rounds == 2


def test_s3_exhaustion_is_a_hard_failure():
    port = ScriptedPort([s3_response([BIN0], [CHK0])])
    res = run_s3(testplan=TPS, contract_json=CONTRACT, port=port, max_repairs=1)
    assert not res.ok and res.rounds == 2


def test_every_stage_shows_the_artifact_before_the_defects():
    """One ordering, checked across all stages rather than assumed.

    The defect list refers to the artifact, so a reader meets what is being
    repaired before what is wrong with it. This was asserted for S1 only, and
    `refmodel` was written the other way round -- caught in a live run, not by
    the suite, which is exactly the gap a cross-stage test closes.
    """
    from specflow.s1_requirements import build_prompt as s1_prompt
    from specflow.s2_testplan import build_prompt as s2_prompt
    from specflow.s3_coverage import build_prompt as s3_prompt
    from specflow.schema import Issue

    issues = [Issue("error", "some.path", "a defect")]
    prior = '{"prior": "artifact"}'
    prompts = {
        "s1": s1_prompt("spec", "{}", issues, prior),
        "s2": s2_prompt([{"uid": "REQ-0000"}], "{}", issues, prior),
        "s3": s3_prompt([{"uid": "TP-0000"}], "{}", issues, prior),
    }
    for name, p in prompts.items():
        assert "<previous_answer>" in p, name
        assert "<gate_failures>" in p, name
        assert p.index("<previous_answer>") < p.index("<gate_failures>"), name


def test_the_refmodel_stage_orders_them_the_same_way():
    """`refmodel` used to build its prompt inline inside `run_refmodel`, which
    is how it drifted out of step in the first place. It is `generate_model`
    now -- shared with the witness -- so the pin follows it there."""
    import inspect

    from specflow.refmodel import compose

    src = inspect.getsource(compose.generate_model)
    prev = src.index("previous_answer_block(previous)")
    fail = src.index("gate_failures_block(issues)")
    assert prev < fail, "refmodel appends the defect list before the artifact"
