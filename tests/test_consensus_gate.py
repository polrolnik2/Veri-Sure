"""The consensus latch: agreement with independently generated designs decides whether a commit is kept."""
import shutil
from pathlib import Path

import pytest

from eda_agent.consensus_gate import ConsensusGate
from eda_agent.rtl_editor import (EXTRA_ORDER_PROMPT, EXTRA_ORDER_PROMPT_CHECKS, RTLEditor, _EditSession,
                                  workflow_prompt)

needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")

CONTRACT = {"module_name": "cnt", "clocking": {"clock": {"name": "clk"}},
            "io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "rst", "dir": "input", "width": 1},
                   {"name": "en", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 2}]}


def counter(step: int, name: str = "cnt") -> str:
    return f"""module {name}(input clk, input rst, input en, output reg [1:0] q);
  always @(posedge clk) if (rst) q <= 2'd0; else if (en) q <= q + 2'd{step};
endmodule
"""


#: rows carry every contract input in declaration order: clk, rst, en
ROWS = {"TP-0000": [[0, 0, 1]] * 6 + [[0, 0, 0]] * 2, "TP-0001": [[0, 0, 1], [0, 0, 0], [0, 0, 1]] * 3}


@pytest.fixture
def gate(tmp_path):
    return ConsensusGate(contract=CONTRACT, rows_by_tp=ROWS, peers=[counter(1), counter(1)], workdir=tmp_path)


@needs_iverilog
def test_a_design_that_behaves_like_the_peers_agrees_fully(gate):
    assert len(gate.peers) == 2
    assert gate.agreement(counter(1)) == pytest.approx(1.0)
    assert gate.agreement(counter(2)) < 1.0


@needs_iverilog
def test_judge_reports_direction_and_the_outputs_that_moved_away(gate):
    up = gate.judge(counter(2), counter(1))
    assert up["rises"] and up["after"] > up["before"] and up["peers"] == 2
    down = gate.judge(counter(1), counter(2))
    assert not down["rises"] and down["outputs_moved_away"] == ["q"]
    same = gate.judge(counter(1), counter(1))
    assert not same["rises"], "a tie does not latch"


@needs_iverilog
def test_a_design_that_does_not_compile_never_latches(gate):
    assert gate.agreement("module cnt(input clk; endmodule") is None
    assert not gate.judge(counter(1), "module cnt(input clk; endmodule")["rises"]


@needs_iverilog
def test_an_already_wrapped_deliverable_is_simulated_as_is(gate):
    wrapped = counter(1, "cnt__probed") + """module cnt(input clk, input rst, input en, output [1:0] q);
  cnt__probed u(.clk(clk), .rst(rst), .en(en), .q(q));
endmodule
"""
    assert gate.agreement(wrapped) == pytest.approx(1.0)


class _Gate:
    def __init__(self, before, after):
        self.v = {"old": before, "new": after}

    def judge(self, before, after):
        a0, a1 = self.v.get(before), self.v.get(after)
        return {"peers": 3, "before": a0, "after": a1, "rises": a1 > a0, "outputs_moved_away": ["q"]}


def _session(tmp_path, rtl="new"):
    p = tmp_path / "rtl.sv"
    p.write_text(rtl)
    s = _EditSession(tb_path=None, rtl_path=str(p), output_dir=str(tmp_path), last_mismatch_cnt=5,
                     sim_reviewer=None, max_trials=3)
    s.latch_rule = "consensus"
    return s


def test_a_commit_that_raises_agreement_latches(tmp_path):
    s = _session(tmp_path)
    c = _Gate(0.5, 0.6).judge("old", "new")
    r = s._consensus_decision({}, c, None, None, "old", 0, None, "{}", is_sim_pass=True)
    assert r["is_action_executed"] and r["accept_reason"].startswith("LATCHED ON AGREEMENT")
    assert s.accepted_agreement == pytest.approx(0.6)
    assert Path(s.rtl_path).read_text() == "new"


def test_a_commit_that_lowers_agreement_is_reverted_whatever_the_checks_say(tmp_path):
    s = _session(tmp_path)
    c = _Gate(0.6, 0.5).judge("old", "new")
    both = ({"REQ-1"}, {"REQ-2"}, set()), ({"REQ-1", "REQ-2"}, set(), set())  # the checks: 1 -> 2 passing
    r = s._consensus_decision({}, c, both[0], both[1], "old", 2, None, "{}")
    assert not r.get("is_action_executed")
    assert "did NOT latch" in r["error_msg"] and "passing requirements 1 -> 2" in r["error_msg"]
    assert "moved AWAY" in r["error_msg"] and "q" in r["error_msg"]
    assert Path(s.rtl_path).read_text() == "old"


def test_best_is_ranked_on_agreement_under_the_consensus_latch(tmp_path):
    s = _session(tmp_path)
    assert s.note_best(5, "a", passing=10, agreement=0.5)
    assert not s.note_best(1, "b", passing=20, agreement=0.4), "more checks passing, less agreement"
    assert not s.note_best(1, "c", passing=20, agreement=0.5), "a tie keeps the earliest"
    assert s.best_rtl == "a" and s.best_agreement == pytest.approx(0.5)


def test_workflow_prompt_says_what_the_run_does():
    assert workflow_prompt(True) == EXTRA_ORDER_PROMPT_CHECKS
    assert workflow_prompt(False) == EXTRA_ORDER_PROMPT
    full = workflow_prompt(True, full_view=True)
    assert "_tool_read_design()" in full and "MUST only modify code inside suspect blocks" not in full
    assert "Only modify code inside suspect blocks." not in full
    cons = workflow_prompt(True, latch_rule="consensus")
    assert "INDEPENDENTLY" in cons and "If it improves, the batch is latched." not in cons


def test_the_consensus_latch_needs_a_gate():
    with pytest.raises(ValueError):
        RTLEditor(None, sim_reviewer=None, latch_rule="consensus")
    with pytest.raises(ValueError):
        RTLEditor(None, sim_reviewer=None, latch_rule="majority")
