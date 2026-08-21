"""The diagnostic that licences raising the judge's model or effort.

Escalating on a hunch is unfalsifiable: a verdict set that looks wrong is
equally consistent with a reader too small to use the evidence and with
evidence too weak for any reader. The separator is a verdict that contradicts
the trace in its own prompt.
"""

from __future__ import annotations

import json

from benchmarks.judge_capacity import analyse

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
    {"name": "cmd", "dir": "input", "width": 4},
    {"name": "cmd_ack", "dir": "output", "width": 1},
]}
REQS = {"requirements": [
    {"uid": "REQ-0000", "text": "cmd_ack pulses when the command completes.",
     "ports": ["cmd", "cmd_ack"]},
    {"uid": "REQ-0001", "text": "cmd is sampled while idle.", "ports": ["cmd"]},
]}


def _run(tmp_path, *, states: int, verdicts: dict[str, str]):
    (tmp_path / "specflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent_io").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")
    (tmp_path / "specflow" / "requirements.json").write_text(
        json.dumps(REQS), encoding="utf-8")
    (tmp_path / "specflow" / "refmodel_judge.json").write_text(json.dumps(
        {"verdicts": [{"req_uid": k, "verdict": v} for k, v in verdicts.items()]}
    ), encoding="utf-8")
    for uid in verdicts:
        (tmp_path / "agent_io" / f"judge_{uid}_r0_prompt.txt").write_text(
            f"<observed_behaviour>\n...\n\n{states} distinct output state(s) "
            f"over 64 vectors.\n</observed_behaviour>", encoding="utf-8")
    return tmp_path


def test_met_on_an_output_requirement_with_a_flat_trace_is_a_reading_failure(tmp_path):
    out = analyse(_run(tmp_path, states=1,
                       verdicts={"REQ-0000": "met", "REQ-0001": "met"}))
    assert out["reading_failure"], (
        "the judge was shown outputs that never move and still called an "
        "output requirement met; that is the reader failing, not the evidence"
    )
    assert out["verdict_contradicts_its_own_trace"] == 1
    assert out["contradictions"][0]["uid"] == "REQ-0000"


def test_a_requirement_about_no_output_cannot_be_contradicted_by_a_flat_trace(tmp_path):
    """REQ-0001 is about an input. A constant output says nothing about it."""
    out = analyse(_run(tmp_path, states=1, verdicts={"REQ-0001": "met"}))
    assert not out["reading_failure"]


def test_not_met_on_a_flat_trace_is_the_reader_working(tmp_path):
    out = analyse(_run(tmp_path, states=1, verdicts={"REQ-0000": "not_met"}))
    assert not out["reading_failure"], (
        "calling a flat trace not_met is exactly right; it must not be read as "
        "a reason to raise the model"
    )


def test_a_live_trace_is_not_a_contradiction_whatever_the_verdict(tmp_path):
    out = analyse(_run(tmp_path, states=7, verdicts={"REQ-0000": "met"}))
    assert not out["reading_failure"]
    assert out["prompts_whose_trace_was_inert"] == 0


def test_a_run_without_behavioural_evidence_says_nothing_rather_than_no(tmp_path):
    """A diagnostic that cannot see must not report an all-clear."""
    t = _run(tmp_path, states=1, verdicts={"REQ-0000": "met"})
    (t / "agent_io" / "judge_REQ-0000_r0_prompt.txt").write_text(
        "no behaviour block here", encoding="utf-8")
    out = analyse(t)
    assert out["requirements_checked"] == 0
    assert not out["reading_failure"]
