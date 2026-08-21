"""The judge emitting a mini-oracle alongside each verdict.

Two things here are easy to break silently. The oracle must survive parsing --
the three prose slots have a validator that flattens lists, and routing
structure through one of them would destroy it without erroring. And each
round's artifacts must not clobber the last, which is the defect
`benchmarks/judge_capacity.py` already works around in `refmodel_judge.json`.
"""

from __future__ import annotations

import json

from specflow.refmodel.judge import (
    SYSTEM,
    JudgeResult,
    RequirementVerdict,
    oracles_of,
    parse_response,
    verdict_map,
    write_round,
)
from specflow.refmodel.oracles import RequirementOracle

ORACLE_SRC = "def decide(trace):\n    return (False, 3, 'cmd_ack never rose')\n"


def _verdict(uid="REQ-0000", verdict="not_met", with_oracle=True):
    oracle = RequirementOracle(
        req_uid=uid, tp_uids=["TP-0007"], clause="cmd_ack pulses once",
        source=ORACLE_SRC,
    ) if with_oracle else None
    return RequirementVerdict(req_uid=uid, verdict=verdict, reason="r", oracle=oracle)


def test_an_oracle_survives_parsing_as_structure():
    """The prose slots join lists with '; '; a new field is why this works."""
    raw = json.dumps({
        "verdict": "not_met",
        "reason": ["one", "two"],          # this SHOULD be flattened
        "oracle": {"tp_uids": ["TP-0007"], "clause": "c", "source": ORACLE_SRC},
    })
    v = parse_response(raw)
    assert v.reason == "one; two", "the prose validator still applies"
    assert v.oracle is not None
    assert v.oracle.tp_uids == ["TP-0007"], "structure must NOT be flattened"
    assert v.oracle.source == ORACLE_SRC


def test_a_verdict_without_an_oracle_is_still_valid():
    """The judge may decline, and the loop falls back to prose for it."""
    assert parse_response(json.dumps({"verdict": "met"})).oracle is None


def test_an_unparseable_answer_yields_no_oracle_rather_than_a_broken_one():
    v = parse_response("not json at all")
    assert v.verdict == "ambiguous" and v.oracle is None


def test_write_round_keeps_rounds_apart():
    """`write_report` writes one fixed path and is overwritten every round.

    A repair loop works on the round in front of it, so the artifacts for that
    round have to survive the next one.
    """
    import tempfile
    from pathlib import Path

    run = Path(tempfile.mkdtemp())
    write_round(run, 0, JudgeResult(verdicts=[_verdict()]))
    write_round(run, 2, JudgeResult(verdicts=[_verdict(verdict="met")]))

    r0 = json.loads((run / "specflow" / "judge" / "r0" / "verdicts.json").read_text())
    r2 = json.loads((run / "specflow" / "judge" / "r2" / "verdicts.json").read_text())
    assert r0["round"] == 0 and r2["round"] == 2
    assert r0["verdicts"][0]["verdict"] == "not_met"
    assert r2["verdicts"][0]["verdict"] == "met", "round 0 must not have been clobbered"


def test_an_oracle_is_written_as_a_runnable_file():
    """Not a JSON string: the agent reads it with the tool it reads models with."""
    import tempfile
    from pathlib import Path

    run = Path(tempfile.mkdtemp())
    out = write_round(run, 1, JudgeResult(verdicts=[_verdict()]))
    path = out / "oracles" / "REQ-0000.py"
    assert path.exists()

    namespace: dict = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)  # noqa: S102
    assert callable(namespace["decide"])
    assert namespace["decide"]([]) == (False, 3, "cmd_ack never rose")
    # The header carries enough to read it without the verdict file open.
    assert "cmd_ack pulses once" in path.read_text()
    assert "TP-0007" in path.read_text()


def test_a_verdict_with_no_oracle_writes_no_file():
    import tempfile
    from pathlib import Path

    run = Path(tempfile.mkdtemp())
    out = write_round(run, 0, JudgeResult(verdicts=[_verdict(with_oracle=False)]))
    assert not list((out / "oracles").glob("*.py"))


def test_oracles_of_and_verdict_map_are_the_screening_inputs():
    result = JudgeResult(verdicts=[_verdict(), _verdict("REQ-0001", "met", False)])
    assert [o.req_uid for o in oracles_of(result)] == ["REQ-0000"]
    assert verdict_map(result) == {"REQ-0000": "not_met", "REQ-0001": "met"}


def test_the_prompt_no_longer_claims_the_scenario_is_absent():
    """It said the trace was a GENERIC sweep and the scenario would not appear.

    That stopped being true when per-testpoint replays landed, and left the
    prompt discouraging use of evidence that is now present.
    """
    assert "not the testpoint's scenario" not in SYSTEM
    assert "model_run_on_this_testpoint_stimulus" in SYSTEM


def test_the_prompt_states_the_rules_an_oracle_is_screened_against():
    """A judge not told the rules cannot be blamed for failing them."""
    for phrase in ("def decide(trace)", "DECLARED PORTS", "mutation-tested",
                   "tp_uids", "edge"):
        assert phrase in SYSTEM, phrase


# ------------------------------------------------------------- reconciliation


def test_the_reconcile_prompt_carries_the_contradiction_and_both_sides():
    """The judge cannot settle what it cannot see."""
    from specflow.refmodel.judge import RECONCILE_SYSTEM, build_reconcile_prompt

    v = _verdict(verdict="met")
    prompt = build_reconcile_prompt(
        source="class Model: pass", contract_json="{}",
        requirement={"uid": "REQ-0000", "text": "cmd_ack pulses"},
        verdict=v,
        conflict="You judged this 'met'. Your oracle FAILS the same model at "
                 "edge 3: cmd_ack never rose",
    )
    assert "cmd_ack pulses" in prompt          # the requirement
    assert "your_verdict" in prompt            # what it said
    assert v.oracle.source.strip() in prompt   # what it wrote
    assert "FAILS the same model at edge 3" in prompt   # the contradiction
    assert RECONCILE_SYSTEM.split("\n")[0] in prompt


def test_reconciliation_offers_both_resolutions():
    """Changing the VERDICT is the outcome worth having, not a fallback.

    It means writing the check made the claim concrete enough to fail, which
    reading the code did not.
    """
    from specflow.refmodel.judge import RECONCILE_SYSTEM

    assert "Fix the oracle." in RECONCILE_SYSTEM
    assert "Change the verdict." in RECONCILE_SYSTEM
    assert "trivially" in RECONCILE_SYSTEM, (
        "it must forbid ending the argument by making the oracle vacuous"
    )


def test_reconcile_stamps_the_req_uid_on_the_repaired_oracle():
    """The harness owns the identifier, on a repair as on a first answer."""
    from specflow.refmodel.judge import reconcile

    class _Port:
        def complete(self, *, stage, round_, prompt):
            return json.dumps({
                "verdict": "not_met", "reason": "fixed",
                "oracle": {"tp_uids": ["TP-0007"], "clause": "c",
                           "source": ORACLE_SRC},
            })

    out = reconcile(
        conflicts={"REQ-0031": "they disagree"},
        verdicts={"REQ-0031": _verdict(uid="REQ-0031")},
        requirements=[{"uid": "REQ-0031", "text": "t"}],
        source="class Model: pass", contract_json="{}", contract=None,
        port=_Port(), fanout=False,
    )
    assert out["REQ-0031"].req_uid == "REQ-0031"
    assert out["REQ-0031"].oracle.req_uid == "REQ-0031"
    assert out["REQ-0031"].verdict == "not_met"
