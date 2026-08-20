"""The judge decides from what the model DID, not only from what it claims.

The per-requirement judge read source against requirement text and never ran
anything. Measured on `i2c_master_bit_ctrl`: the repair loop turned an active
model (4 distinct output states over a 64-vector corner sweep) into an inert one
(exactly 1) at the FIRST repair round, and the judge returned "met" on 77 of 77
requirements for that round and every round after. Scored against golden RTL the
shipped model went 34/181 to 18/181 and its separation from a known-WRONG design
inverted to -9 -- it matched the wrong design better than the right one.

Reading code cannot catch that. Code can be structurally perfect and sit behind
a condition that is never true.
"""

from __future__ import annotations

import json

from specflow.refmodel.judge import build_prompt, observed_behaviour, shared_prefix

CONTRACT = {
    "top": "d",
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset", "active_low": True},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 4},
    ],
}

ACTIVE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 0

    def step(self, i):
        return {"q": self.mask(i.get("a", 0), 4)}
'''

#: Structurally complete and permanently unreachable -- the shape that shipped.
INERT = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 0

    def __init__(self):
        self.enabled = False

    def step(self, i):
        if self.enabled:            # never true; the body below is dead
            return {"q": self.mask(i.get("a", 0), 4)}
        return {"q": 0}
'''


def test_an_inert_model_is_reported_as_inert():
    trace = observed_behaviour(INERT, CONTRACT, base="step")
    assert trace is not None
    assert "1 distinct output state(s)" in trace
    assert "NEVER CHANGE" in trace, (
        "the judge should not have to derive inertness by counting trace rows"
    )


def test_an_active_model_is_not():
    trace = observed_behaviour(ACTIVE, CONTRACT, base="step")
    assert trace is not None
    assert "NEVER CHANGE" not in trace
    assert "1 distinct output state(s)" not in trace


def test_the_trace_is_the_whole_run_not_a_summary():
    """A requirement is about a moment, so an aggregate over moments won't do."""
    trace = observed_behaviour(ACTIVE, CONTRACT, base="step")
    rows = [ln for ln in trace.splitlines() if "->" in ln and "=" in ln]
    assert len(rows) >= 16, f"only {len(rows)} steps rendered"
    assert all("a=" in r and "q=" in r for r in rows), "each step needs inputs AND outputs"


def test_a_model_that_cannot_be_driven_yields_no_trace_rather_than_raising():
    """Instrumentation must never be what fails a generation round.

    `_behavioural_checks` already blocks on a model that will not run, and the
    judge does not run on a model carrying mechanical errors.
    """
    assert observed_behaviour("class NotAModel: pass", CONTRACT, base="step") is None
    assert observed_behaviour("syntax ~~ error", CONTRACT, base="step") is None
    assert observed_behaviour(ACTIVE, CONTRACT, base="no_such_method") is None


def test_the_trace_rides_in_the_shared_prefix_so_it_is_sent_once_per_round():
    """Cost, and the reason it is affordable at ~70 requirements per round.

    The prefix is byte-identical across every requirement of a round, so the
    trace is cached after the first two calls. Putting it in the per-requirement
    item instead would re-send it ~70 times.
    """
    trace = observed_behaviour(ACTIVE, CONTRACT, base="step")
    prefix = shared_prefix(ACTIVE, json.dumps(CONTRACT), trace)
    assert "</observed_behaviour>" in prefix
    assert shared_prefix(ACTIVE, json.dumps(CONTRACT), trace) == prefix


def test_each_requirement_is_shown_only_its_own_testpoints():
    """testpoint.covers is "REQ-0001@1"; the revision is not part of the key."""
    req = {"uid": "REQ-0001", "text": "q follows a"}
    mine = [{"uid": "TP-0000", "covers": ["REQ-0001@1"], "stimulus": "drive a"}]
    prompt = build_prompt(
        source=ACTIVE, contract_json=json.dumps(CONTRACT), requirement=req,
        methods=["step"], testpoints=mine,
    )
    assert "TP-0000" in prompt
    assert "testpoints_covering_this_requirement" in prompt

    bare = build_prompt(
        source=ACTIVE, contract_json=json.dumps(CONTRACT), requirement=req,
        methods=["step"],
    )
    assert "testpoints_covering_this_requirement" not in bare


def test_only_judgeable_testpoint_fields_are_sent():
    """The uncacheable half of this, so it is the half worth trimming.

    The trace rides in the shared prefix and is sent once per round; the
    testpoints are per-requirement and cannot be cached. Measured on
    `i2c_master_bit_ctrl`, 77 requirements: unprojected and uncapped they cost
    260 kB (~65k tokens) per round, projected 146 kB (~36k).
    """
    from specflow.refmodel.judge import _for_judge

    tps = [{"uid": f"TP-{i:04d}", "rev": 1, "covers": ["REQ-0001@1"],
            "dimension": "D2_control_flow", "needs": ["bin", "check"],
            "stimulus": "drive a", "expected_response": "q follows",
            "check_method": "compare against the reference model"}
           for i in range(6)]
    out = _for_judge(tps)
    assert len(out) == 3, "the 1-to-6 tail is capped"
    assert set(out[0]) == {"uid", "stimulus", "expected_response"}
    assert "check_method" not in out[0], (
        "check_method tells the TESTBENCH how to check, not the judge how to judge"
    )


def test_a_requirement_with_no_testpoints_is_handled():
    assert _for_judge_empty() == []


def _for_judge_empty():
    from specflow.refmodel.judge import _for_judge

    return _for_judge([])


def test_run_judge_actually_delivers_the_trace_to_every_call():
    """The wiring, not the pieces.

    `observed_behaviour` and `build_prompt` are tested above in isolation; this
    pins that `run_judge` computes the trace and puts it in front of the judge,
    which is the step that was missing and the reason 77 of 77 came back "met".
    """
    from specflow.refmodel.judge import run_judge

    seen: list[str] = []

    class Port:
        def complete(self, *, stage, round_, prompt):
            seen.append(prompt)
            return json.dumps({"verdict": "not_met", "reason": "outputs never move",
                               "evidence": "observed_behaviour", "remedy": "make it live"})

    reqs = [{"uid": "REQ-0001", "text": "q must follow a"},
            {"uid": "REQ-0002", "text": "q must reset to 0"}]
    tps = [{"uid": "TP-0000", "covers": ["REQ-0001@1"], "stimulus": "sweep a",
            "expected_response": "q tracks a"}]

    run_judge(
        source=INERT, contract_json=json.dumps(CONTRACT), requirements=reqs,
        covers={"REQ-0001": ["step"], "REQ-0002": ["step"]},
        port=Port(), contract=CONTRACT, base="step", testplan=tps,
    )

    assert len(seen) == 2
    assert all("</observed_behaviour>" in p for p in seen), "the trace reached every call"
    assert all("NEVER CHANGE" in p for p in seen), "and it carried the inertness fact"
    # ...and only the requirement that owns TP-0000 is shown it.
    owns = [p for p in seen if "TP-0000" in p]
    assert len(owns) == 1, "a testpoint must not leak into an unrelated requirement"


def test_run_judge_without_a_contract_still_works():
    """The trace is additive. A caller that cannot supply a contract still judges."""
    from specflow.refmodel.judge import run_judge

    seen: list[str] = []

    class Port:
        def complete(self, *, stage, round_, prompt):
            seen.append(prompt)
            return json.dumps({"verdict": "met", "reason": "r", "evidence": "e"})

    run_judge(source=ACTIVE, contract_json=json.dumps(CONTRACT),
              requirements=[{"uid": "REQ-0001", "text": "t"}],
              covers={"REQ-0001": ["step"]}, port=Port())
    # the closing tag, not the bare word: SYSTEM itself names the block.
    assert seen and "</observed_behaviour>" not in seen[0]
