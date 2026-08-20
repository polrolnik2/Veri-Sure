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


#: A prescaled sequential contract: the shape where a scenario needs many edges.
PRESCALED = {
    "top": "d",
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset", "active_low": True},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "clk_cnt", "dir": "input", "width": 16},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "ack", "dir": "output", "width": 1},
    ],
}


def test_the_generic_sweep_cannot_contain_a_multi_cycle_scenario():
    """Why "absence of the scenario" is explicitly NOT a finding.

    "ambiguous" is BLOCKING. If the judge treated a scenario missing from the
    trace as grounds for it, nearly every requirement of a sequential design
    would block and no generation round could ever pass.

    And the scenarios really are missing, by construction rather than by luck:
    `default_stimulus` is a corner-first sweep that varies inputs at EVERY step,
    so it never holds a command stable across the many edges a prescaled FSM
    needs to advance. Measured on the real `i2c_master_bit_ctrl` contract: the
    longest run of consecutive steps that could advance its FSM is 0, where one
    START on golden needs ~26 edges at clk_cnt=4. The known-correct control
    model reaches busy=1 on 0 of 64 steps.

    The trace is still worth sending -- that same control model shows 12
    distinct output states where the inert model shows 1 -- but its authority is
    over liveness and contradiction, never over coverage.
    """
    from specflow.ports import pinned_inputs
    from specflow.tb.render import default_stimulus

    pinned = dict(pinned_inputs(PRESCALED))
    walk = [{**pinned, **v} for v in default_stimulus(PRESCALED)]
    assert len(walk) > 8

    held = max(
        (sum(1 for a, b in zip(walk, walk[1:]) if a.get(port) == b.get(port))
         for port in ("cmd", "ena")),
        default=0,
    )
    assert held < len(walk) - 1, (
        "if the sweep DID hold inputs stable it could reach scenarios, and the "
        "instruction telling the judge to ignore their absence would be wrong"
    )


def _edges(rows: list[str]) -> int:
    """Edges represented by an RLE'd trace: "  3-8  ..." is six of them.

    The traces are run-length encoded, losslessly, because a prescaled design
    spends most of a scenario holding one state. These tests are about how many
    EDGES were replayed, which is a property of the replay; how they are
    rendered is not.
    """
    n = 0
    for row in rows:
        head = row.strip().split()[0]
        if "-" in head:
            lo, hi = head.split("-", 1)
            n += int(hi) - int(lo) + 1
        elif head.isdigit():
            n += 1
    return n


COUNTER = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["ack"]
    LATENCY_CYCLES = 0

    def __init__(self):
        self.n = 0

    def step(self, i):
        self.n = self.n + 1 if i.get("ena") else 0
        return {"ack": 1 if self.n >= 5 else 0}
'''


def test_a_held_step_is_replayed_for_every_edge_it_declares():
    """`hold` is what lets a scenario span the edges a prescaled design needs."""
    from specflow.refmodel.judge import scenario_trace

    rows = scenario_trace(COUNTER, PRESCALED,
                          [{"inputs": {"ena": 1, "cmd": 0, "clk_cnt": 1}, "hold": 6}],
                          base="step")
    assert _edges(rows) == 6, f"expected 6 edges, got {_edges(rows)}"


def test_a_bare_step_is_one_edge():
    from specflow.refmodel.judge import scenario_trace

    rows = scenario_trace(COUNTER, PRESCALED,
                          [{"ena": 1, "cmd": 0, "clk_cnt": 1}] * 3, base="step")
    assert _edges(rows) == 3


def test_until_stops_the_replay_when_the_model_reaches_the_condition():
    """The point of `until`: wait for the design rather than guess a duration.

    With no DUT at this stage the condition resolves against the MODEL, which is
    the right reading -- this trace is the model's own run.
    """
    from specflow.refmodel.judge import scenario_trace

    rows = scenario_trace(
        COUNTER, PRESCALED,
        [{"inputs": {"ena": 1, "cmd": 0, "clk_cnt": 1},
          "until": {"port": "ack", "value": 1}, "timeout": 200}],
        base="step")
    assert _edges(rows) == 5, f"should stop the edge ack rises, got {_edges(rows)}"
    assert "ack=1" in rows[-1]
    assert sum("ack=1" in r for r in rows) == 1


def test_a_replay_that_never_satisfies_until_is_capped_and_says_so():
    """An `until` may wait 200 edges; 77 requirements of those is megabytes."""
    from specflow.refmodel.judge import _SCENARIO_EDGES, scenario_trace

    rows = scenario_trace(
        COUNTER, PRESCALED,
        [{"inputs": {"ena": 0, "cmd": 0, "clk_cnt": 1},   # ena=0 -> ack never rises
          "until": {"port": "ack", "value": 1}, "timeout": 200}],
        base="step")
    assert _edges(rows) == _SCENARIO_EDGES
    assert "never reached" in rows[-1], (
        "an `until` that never fires is a finding about the model -- the "
        "testbench will wait for that condition too -- not a silent stop"
    )


def test_the_concrete_trace_replaces_the_prose_it_supersedes():
    from specflow.refmodel.judge import _for_judge

    tp = {"uid": "TP-0000", "covers": ["REQ-0001@1"],
          "stimulus": "drive ena high for a while",
          "expected_response": "ack rises"}
    steps = {"TP-0000": [{"inputs": {"ena": 1, "cmd": 0, "clk_cnt": 1}, "hold": 6}]}

    out = _for_judge([tp], source=COUNTER, contract=PRESCALED,
                     stimulus_by_tp=steps, base="step")[0]
    assert "model_run_on_this_testpoint_stimulus" in out
    assert "stimulus" not in out, "the vectors ARE the stimulus; prose is redundant"
    assert out["expected_response"] == "ack rises", (
        "the specification's claim must stay -- it is what the trace is judged against"
    )

    # ...and with no concrete stimulus, the prose is all there is, so it stays.
    bare = _for_judge([tp], source=COUNTER, contract=PRESCALED,
                      stimulus_by_tp={}, base="step")[0]
    assert bare["stimulus"] == "drive ena high for a while"
    assert "model_run_on_this_testpoint_stimulus" not in bare


def test_a_long_held_replay_is_capped_and_says_so():
    """The other truncation path: many edges of `hold`, no `until` involved."""
    from specflow.refmodel.judge import _SCENARIO_EDGES, scenario_trace

    rows = scenario_trace(
        COUNTER, PRESCALED,
        [{"inputs": {"ena": 1, "cmd": 0, "clk_cnt": 1}, "hold": 60}], base="step")
    assert _edges(rows) == _SCENARIO_EDGES
    assert "truncated" in rows[-1], "truncation must be announced, not silent"


def test_the_encoding_is_lossless_and_records_how_long_a_state_held():
    """A duration claim needs the hold length, so collapsing must keep it."""
    from specflow.refmodel.judge import scenario_trace

    rows = scenario_trace(COUNTER, PRESCALED,
                          [{"inputs": {"ena": 0, "cmd": 0, "clk_cnt": 1}, "hold": 9}],
                          base="step")
    assert _edges(rows) == 9
    assert len(rows) == 1, "nine identical edges should collapse to one row"
    assert "held 9 edges" in rows[0], "the duration must survive the collapse"


def test_distinct_states_are_never_merged():
    """Lossless means the model's state sequence is still fully visible."""
    from specflow.refmodel.judge import scenario_trace

    rows = scenario_trace(COUNTER, PRESCALED,
                          [{"inputs": {"ena": 1, "cmd": 0, "clk_cnt": 1}, "hold": 8}],
                          base="step")
    assert _edges(rows) == 8
    # ack rises at the 5th edge, so the run splits: ack=0 for 4, then ack=1.
    assert sum("ack=0" in r for r in rows) == 1
    assert sum("ack=1" in r for r in rows) == 1
    assert "held 4 edges" in rows[0]


def test_the_prefix_puts_invariant_sections_before_changing_ones():
    """Prefix caching keeps a prefix only up to its first differing byte.

    The model source changes every repair round. Anything emitted after it is
    therefore cold every round, however fixed it is in itself. `contract_json`
    is fixed for the whole node and was being emitted after the source, which
    stranded 10.2 kB behind a 7.9 kB block on all ~77 calls of every round
    after the first.
    """
    prefix = shared_prefix(ACTIVE, json.dumps(CONTRACT), "trace")

    def at(tag: str) -> int:
        # The delimited block, not the bare word: SYSTEM's own prose names
        # <observed_behaviour>, and matching that would compare the wrong thing.
        return prefix.index(f"\n<{tag}>\n")

    assert at("contract_json") < at("reference_model"), (
        "the contract is invariant across rounds and must precede the model "
        "source, which is not"
    )
    assert prefix.index("<system>") < at("contract_json")
    # The trace derives from the source, so it belongs after it.
    assert at("reference_model") < at("observed_behaviour")
