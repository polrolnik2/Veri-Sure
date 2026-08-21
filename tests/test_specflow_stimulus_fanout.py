"""Stimulus is generated per testpoint, not in one call for the whole suite.

Monolithic generation was measured degrading at scale on `i2c_master_bit_ctrl`:
167 testpoints in one request, three repair rounds returning stimulus for TEN
of them, and a fourth returning all 167 with exactly one step each -- every
`hold` equal to 1, 59 distinct sequences, one testpoint driving `clk_cnt=1000`
for a single edge. `gate_suite` passed it because one step is non-empty.
"""

from __future__ import annotations

import json

from specflow.testcase_agent import (
    build_suite_prompt,
    build_suite_prompt_one,
    run_suite_stimulus_fanout,
)

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
    ]
}
PLAN = [
    {"uid": f"TP-{i:04d}", "dimension": "D2_control_flow",
     "stimulus": f"scenario {i}", "expected_response": f"response {i}"}
    for i in range(5)
]


class RecordingPort:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, *, stage, round_, prompt):
        self.prompts.append(prompt)
        uid = stage.rsplit("_", 1)[-1]
        return json.dumps({
            "reasoning": "r",
            "testpoints": [{
                "tp_uid": uid,
                "stimulus_steps": [{"inputs": {"ena": 1, "cmd": 1}, "hold": 8}],
            }],
        })


def test_each_testpoint_gets_its_own_call():
    port = RecordingPort()
    merged, per_item = run_suite_stimulus_fanout(
        testplan=PLAN, contract=CONTRACT, port=port, fanout=False
    )
    assert len(per_item) == len(PLAN)
    assert len(port.prompts) == len(PLAN), (
        "the whole point is one request per testpoint; a single call carrying "
        "all of them is what degraded to one step each"
    )
    assert {tp.tp_uid for tp in merged.testpoints} == {e["uid"] for e in PLAN}


def test_a_call_carries_its_own_testpoint_and_not_the_others():
    """Otherwise the split is nominal and each call still costs the whole plan."""
    port = RecordingPort()
    run_suite_stimulus_fanout(
        testplan=PLAN, contract=CONTRACT, port=port, fanout=False
    )
    from specflow.fanout import PREFIX_SENTINEL

    for i, prompt in enumerate(port.prompts):
        # Only the ITEM region. The shared prefix carries an output example
        # naming TP-0000, which is prose in the cached head, not a leak of one
        # testpoint into another's call.
        item = prompt.split(PREFIX_SENTINEL, 1)[1]
        assert f"TP-{i:04d}" in item
        others = [f"TP-{j:04d}" for j in range(len(PLAN)) if j != i]
        assert not [o for o in others if o in item], (
            f"call {i} names other testpoints; the prompt was not actually split"
        )


def test_the_per_item_prompt_is_far_smaller_than_the_monolithic_one():
    """The size gap is the mechanism, not a nicety.

    One request carrying 167 testpoints x up to 24 steps x 6 ports is what the
    model answered by shrinking every sequence to a single step.
    """
    big = build_suite_prompt(testplan=PLAN, contract=CONTRACT, max_steps=24)
    one = build_suite_prompt_one(PLAN[0], CONTRACT, 24)
    assert len(one) < len(big)


def test_the_shared_prefix_precedes_the_item_so_it_can_cache():
    from specflow.fanout import PREFIX_SENTINEL

    prompt = build_suite_prompt_one(PLAN[3], CONTRACT, 24)
    assert PREFIX_SENTINEL in prompt
    assert prompt.index(PREFIX_SENTINEL) < prompt.index("TP-0003")
