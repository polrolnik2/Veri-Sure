"""R2/R3: the per-requirement judge, and the asymmetry that makes it safe.

The founding rule of every gate here is that an LLM never certifies its own
side's completeness. A judge is an LLM assessing an LLM, so it is allowed in only
under an asymmetry: it can **block** and it cannot **accept**. The first test
below is that guarantee, and it is the one that matters most -- if `met` could
discharge an obligation, the judge would become the acceptance authority and the
whole gate design would be decorative.
"""

from __future__ import annotations

import json
import os

import pytest

from specflow.fanout import PREFIX_SENTINEL
from specflow.refmodel.judge import (
    BLOCKING,
    JudgeResult,
    RequirementVerdict,
    build_prompt,
    parse_response,
    run_judge,
    shared_prefix,
    to_issue,
)
from specflow.schema import has_errors

CONTRACT = json.dumps({
    "module_name": "TopModule",
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
        {"name": "cout", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": False},
    "timing": {"sum": {"latency_cycles": 0}, "cout": {"latency_cycles": 0}},
})
SOURCE = (
    "def _half_add(self, a, b):\n"
    "    return (a ^ b) & 1, (a & b) & 1\n"
    "\n"
    "def evaluate(self, i):\n"
    "    o = {p: None for p in self.OUTPUT_PORTS}\n"
    "    o['sum'], o['cout'] = self._half_add(i['a'], i['b'])\n"
    "    return o\n"
)
REQS = [
    {"uid": "REQ-0000", "rev": 1, "text": "sum is a xor b.", "needs": ["refmodel"]},
    {"uid": "REQ-0001", "rev": 1, "text": "cout is a and b.", "needs": ["refmodel"]},
]
COVERS = {"REQ-0000": ["_half_add"], "REQ-0001": ["_half_add"]}


class Scripted:
    def __init__(self, reply):
        self.reply = reply
        self.prompts: dict[str, str] = {}

    def complete(self, *, stage, round_, prompt):
        self.prompts[stage] = prompt
        return self.reply(stage)


# ------------------------------------------------------- R3: it cannot accept


def test_met_certifies_nothing():
    """**The guarantee the judge is admitted under.**

    A `met` verdict produces no issue, and therefore cannot cancel one. If it
    could, an LLM would be the acceptance authority -- which is exactly what
    every gate in this pipeline is built to avoid.
    """
    met = RequirementVerdict(req_uid="REQ-0000", verdict="met", reason="fine")
    assert to_issue(met) is None
    assert not met.blocks

    result = JudgeResult(verdicts=[met])
    assert result.issues == []

    # A failing script check stands beside a `met`, untouched.
    from specflow.schema import Issue

    script_issues = [Issue("error", "ref_model.py.evaluate", "leaves ['cout'] unwritten")]
    combined = script_issues + result.issues
    assert has_errors(combined), "a met verdict cancelled a mechanical failure"


def test_both_failing_verdicts_block():
    assert BLOCKING == {"not_met", "ambiguous"}
    for verdict in ("not_met", "ambiguous"):
        v = RequirementVerdict(req_uid="REQ-0000", verdict=verdict, reason="r")
        assert v.blocks
        assert to_issue(v) is not None
    assert has_errors(JudgeResult(verdicts=[
        RequirementVerdict(req_uid="REQ-0000", verdict="not_met", reason="r")
    ]).issues)


def test_an_unreadable_verdict_defaults_to_blocking():
    """A malformed response is not silence and must not read as one."""
    v = parse_response("this is not json")
    assert v.verdict == "ambiguous" and v.blocks
    assert "Parse Error" in v.reason


# --------------------------------------- both blocking verdicts carry feedback


def test_not_met_carries_reason_evidence_and_remedy():
    """The feedback channel is the product, not the verdict.

    A judge returning pass/fail would be an expensive boolean; the mechanical
    gates already produce better booleans for free. What this adds is a
    per-requirement statement of what is wrong and what to do -- strictly more
    than G4 can say, since `leaves ['cout'] unwritten` reports a free port, not
    which requirement went unserved.
    """
    issue = to_issue(RequirementVerdict(
        req_uid="REQ-0031", verdict="not_met",
        reason="cmd_ack must pulse for one cycle; _fsm never clears it",
        evidence="_fsm lines 12-18",
        remedy="clear cmd_ack at the start of each step",
    ))
    assert issue is not None
    assert "REQ-0031" in issue.path and "not_met" in issue.path
    for fragment in ("cmd_ack must pulse", "evidence: _fsm lines 12-18",
                     "remedy: clear cmd_ack"):
        assert fragment in issue.message


def test_ambiguous_carries_feedback_too():
    issue = to_issue(RequirementVerdict(
        req_uid="REQ-0031", verdict="ambiguous",
        reason="could not determine whether the filter interval is applied",
        evidence="_filter lines 4-9",
        remedy="say which line applies the interval",
    ))
    assert issue is not None
    assert "could not determine" in issue.message
    assert "remedy: say which line" in issue.message


def test_the_default_ambiguous_remedy_offers_both_branches():
    """It must NOT presuppose the requirement is met.

    `ambiguous` means the judge could not tell -- which covers a requirement
    implemented illegibly *and* a requirement not implemented at all. Phrasing
    the remedy as "explain why it is met" would steer the generator into writing
    a justifying comment over absent behaviour, which is the persuade-the-judge
    failure the R3 asymmetry exists to contain. Not worth inviting even though
    it is contained.
    """
    issue = to_issue(RequirementVerdict(
        req_uid="REQ-0031", verdict="ambiguous", reason="cannot tell", remedy=""
    ))
    assert issue is not None
    msg = " ".join(issue.message.lower().split())
    assert "if the requirement is not implemented, implement it" in msg
    assert "make that legible" in msg and "inline comment" in msg
    assert "why it is met" not in msg, "the remedy presupposes the code is correct"
    assert "explaining why the requirement is met" not in msg


def test_the_prompt_tells_the_judge_ambiguous_is_not_probably_met():
    # Whitespace-normalised: the prompt is wrapped prose, and asserting on a
    # phrase that happens to survive a line break is a test that breaks on
    # rewrapping rather than on meaning.
    text = " ".join(shared_prefix(SOURCE, CONTRACT).lower().split())
    assert 'does not mean "probably met but unclear"' in text
    assert "do not guess which" in text
    # And it tells the judge its met cannot accept, so generosity buys nothing.
    assert "cannot accept anything" in text


# ------------------------------------------------------------------ the stage


def test_one_call_per_requirement_and_the_harness_owns_the_uid():
    """A judge answering about the wrong requirement would otherwise silently
    retarget its own verdict onto a requirement it never read."""
    def reply(stage):
        return json.dumps({"req_uid": "REQ-9999", "verdict": "met", "reason": "r"})

    port = Scripted(reply)
    result = run_judge(source=SOURCE, contract_json=CONTRACT, requirements=REQS,
                       covers=COVERS, port=port, fanout=False)

    assert set(port.prompts) == {"judge_REQ-0000", "judge_REQ-0001"}
    assert [v.req_uid for v in result.verdicts] == ["REQ-0000", "REQ-0001"]


def test_the_prompt_carries_the_model_and_the_claimed_methods():
    p = build_prompt(source=SOURCE, contract_json=CONTRACT,
                     requirement=REQS[0], methods=["_half_add"])
    assert "_half_add" in p
    assert "<claimed_methods>" in p
    assert p.index("<reference_model>") < p.index("<claimed_methods>")


def test_a_requirement_with_no_claimed_methods_still_gets_judged():
    """The coverage-map check catches an *absent* entry. An entry that is present
    and empty is the judge's to convict, and it must not crash on the way."""
    p = build_prompt(source=SOURCE, contract_json=CONTRACT,
                     requirement=REQS[0], methods=[])
    assert "(none declared)" in p


def test_c1_the_judge_stage_shares_a_byte_identical_prefix():
    reqs = [{"uid": f"REQ-{i:04d}", "text": f"requirement {i}"} for i in range(40)]
    prompts = [
        build_prompt(source=SOURCE, contract_json=CONTRACT, requirement=r, methods=["_x"])
        for r in reqs
    ]
    common = os.path.commonprefix(prompts)
    assert PREFIX_SENTINEL in common
    assert all(p.startswith(shared_prefix(SOURCE, CONTRACT)) for p in prompts)


def test_c2_a_repair_round_keeps_the_prefix():
    from specflow.schema import Issue

    shared = shared_prefix(SOURCE, CONTRACT)
    r1 = build_prompt(source=SOURCE, contract_json=CONTRACT, requirement=REQS[0],
                      methods=["_half_add"], issues=[Issue("error", "p", "m")],
                      previous="{}")
    assert r1.startswith(shared)
    assert r1.index("<requirement>") < r1.index("gate_failures")


def test_counts_and_report_shape(tmp_path):
    from specflow.refmodel.judge import write_report

    result = JudgeResult(verdicts=[
        RequirementVerdict(req_uid="REQ-0000", verdict="met", reason="r"),
        RequirementVerdict(req_uid="REQ-0001", verdict="not_met", reason="r"),
        RequirementVerdict(req_uid="REQ-0002", verdict="ambiguous", reason="r"),
    ])
    assert result.counts() == {"met": 1, "not_met": 1, "ambiguous": 1}
    write_report(tmp_path, result)
    d = json.loads((tmp_path / "specflow" / "refmodel_judge.json").read_text())
    assert d["counts"]["met"] == 1
    assert d["blocking"] == ["REQ-0001", "REQ-0002"]
    # Passing verdicts are kept: `met` certifies nothing mechanically, but it is
    # the record of what was examined and why it was thought fine.
    assert len(d["verdicts"]) == 3


# ------------------------------------------------- wired into the refmodel gate


def test_the_judge_blocks_the_refmodel_gate(tmp_path):
    from specflow.refmodel.compose import run_refmodel

    model_reply = json.dumps({
        "base": "evaluate", "source": SOURCE,
        "covers": {"REQ-0000": ["_half_add"], "REQ-0001": ["_half_add"]},
    })

    class Port:
        def complete(self, *, stage, round_, prompt):
            if stage.startswith("judge_"):
                return json.dumps({
                    "verdict": "not_met",
                    "reason": "the carry is ORed, not ANDed",
                    "evidence": "_half_add line 2",
                    "remedy": "use & rather than |",
                })
            return model_reply

    res, source = run_refmodel(
        requirements=REQS, contract_json=CONTRACT, port=Port(),
        workdir=tmp_path, max_repairs=0, judge_port=Port(), run_dir=tmp_path,
    )
    assert not res.ok, "a not_met verdict did not block the gate"
    assert any("the carry is ORed" in i.message for i in res.issues)
    assert (tmp_path / "specflow" / "refmodel_judge.json").exists()


def test_the_judge_does_not_run_on_a_model_that_fails_the_script_checks(tmp_path):
    """Spending ~70 questions on a model that does not import rediscovers what a
    script already said, about code that is going to be regenerated anyway."""
    from specflow.refmodel.compose import run_refmodel

    asked: list[str] = []

    class Port:
        def complete(self, *, stage, round_, prompt):
            asked.append(stage)
            if stage.startswith("judge_"):
                return json.dumps({"verdict": "met", "reason": "r"})
            # Leaves `cout` undetermined: a mechanical failure.
            return json.dumps({
                "base": "evaluate",
                "source": "def evaluate(self, i):\n"
                          "    o = {p: None for p in self.OUTPUT_PORTS}\n"
                          "    o['sum'] = 1\n"
                          "    return o\n",
                "covers": {"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]},
            })

    res, _ = run_refmodel(
        requirements=REQS, contract_json=CONTRACT, port=Port(),
        workdir=tmp_path, max_repairs=0, judge_port=Port(), run_dir=tmp_path,
    )
    assert not res.ok
    assert not any(s.startswith("judge_") for s in asked), (
        f"the judge ran on a model that had already failed mechanically: {asked}"
    )


@pytest.mark.parametrize("verdict", ["met", "not_met", "ambiguous"])
def test_every_verdict_round_trips_through_the_parser(verdict):
    raw = json.dumps({"verdict": verdict, "reason": "r", "evidence": "e", "remedy": "m"})
    assert parse_response(raw).verdict == verdict
