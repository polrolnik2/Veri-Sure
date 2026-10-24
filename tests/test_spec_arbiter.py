"""Targeted arbitration: commits the consensus latch cannot decide go to a judgment against the spec."""
import shutil
from pathlib import Path

import pytest

from eda_agent.consensus_gate import ConsensusGate
from eda_agent.rtl_editor import RTLEditor, _EditSession
from eda_agent.spec_arbiter import SpecArbiter, configuration

needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")

CONTRACT = {"module_name": "cnt", "clocking": {"clock": {"name": "clk"}},
            "io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "rst", "dir": "input", "width": 1},
                   {"name": "en", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 2}]}


def counter(step: int) -> str:
    return f"""module cnt(input clk, input rst, input en, output reg [1:0] q);
  always @(posedge clk) if (rst) q <= 2'd0; else if (en) q <= q + 2'd{step};
endmodule
"""


ROWS = {"TP-0000": [[0, 0, 1]] * 6 + [[0, 0, 0]] * 2, "TP-0001": [[0, 0, 0]] * 60 + [[0, 0, 1]] * 4}


class _Judge(SpecArbiter):
    """Answers as a judge that knows the counter must step by 1: picks the candidate whose q does."""

    def ask(self, user):
        rows = [r.split(" | ") for r in user.split("## Excerpt")[1].splitlines()[2:] if " | " in r]
        head = user.split("## Excerpt")[1].splitlines()[2].split(" | ")
        xi, yi = head.index("X.q"), head.index("Y.q")
        good = {"X": 0, "Y": 0}
        prev = None
        for r in rows:
            if prev is not None and r[-1] == "<<":
                for lab, i in (("X", xi), ("Y", yi)):
                    good[lab] += int(r[i], 16) == (int(prev[i], 16) + 1) % 4
            prev = r
        self.prompts.append(user)
        return {"verdict": "X" if good["X"] > good["Y"] else "Y" if good["Y"] > good["X"] else "undetermined",
                "output_tokens": 10}


@pytest.fixture
def judge(tmp_path):
    gate = ConsensusGate(contract=CONTRACT, rows_by_tp=ROWS, peers=[counter(1)], workdir=tmp_path)
    a = _Judge(gate=gate, spec="q counts enabled cycles.", workdir=tmp_path)
    a.prompts = []
    return a


@needs_iverilog
def test_the_judge_is_asked_twice_per_divergence_and_scores_the_edit(judge):
    better = judge.decide(counter(2), counter(1))
    assert better["score"] == pytest.approx(1.0) and better["asked"] == 2
    assert len(judge.prompts) == 4, "each testpoint in both label orders"
    assert judge.decide(counter(1), counter(2))["score"] == pytest.approx(-1.0)


@needs_iverilog
def test_the_prompt_shows_the_divergence_not_the_edit(judge):
    judge.decide(counter(2), counter(1))
    p = judge.prompts[0]
    assert "X.q" in p and "Y.q" in p and "<<" in p
    assert "rst=1" in p, "the bench's own reset is described"
    assert "after" not in p.split("## Excerpt")[1] and "before" not in p.split("## Excerpt")[1]


@needs_iverilog
def test_a_long_quiet_history_is_collapsed(judge):
    judge.decide(counter(2), counter(1))
    long_ = next(p for p in judge.prompts if "60 rows" not in p and "0-" in p.split("## Excerpt")[1])
    assert "stands for rows a through b" in long_
    assert len(long_.split("## Excerpt")[1].splitlines()) < 30


def test_configuration_reports_the_macros_the_spec_names(tmp_path):
    (tmp_path / "x_defines.v").write_text("`define X_USE_FIFO\n//`define X_FAST_PATH\n`define X_CMD 4'b0100\n")
    text = configuration("Uses X_USE_FIFO, X_FAST_PATH and X_CMD; not X_OTHER.", [str(tmp_path)])
    assert "X_USE_FIFO is defined" in text and "X_FAST_PATH is NOT defined" in text
    assert "X_CMD is defined as 4'b0100" in text and "X_OTHER" not in text


class _Fixed:
    band = 0.02

    def __init__(self, score):
        self.score, self.calls = score, 0

    def decide(self, before, after):
        self.calls += 1
        return {"score": self.score, "asked": 2, "answers": {}, "tokens": 0,
                "episodes": [{"tp": "TP-0001", "answers": ["before", "before"]}] if self.score < 0 else []}


def _session(tmp_path, arbiter):
    p = tmp_path / "rtl.sv"
    p.write_text("new")
    s = _EditSession(tb_path=None, rtl_path=str(p), output_dir=str(tmp_path), last_mismatch_cnt=5,
                     sim_reviewer=None, max_trials=3)
    s.latch_rule, s.latch_arbiter = "consensus", arbiter
    return s


def _judged(before, after):
    return {"peers": 3, "before": before, "after": after, "rises": after >= before + 0.001,
            "outputs_moved_away": ["q"], "behaviour_changed": True, "min_gain": 0.001, "tolerance": 0.005}


UP = ({"REQ-1"}, {"REQ-2"}, set()), ({"REQ-1", "REQ-2"}, set(), set())


def test_the_judge_keeps_a_fix_the_tolerance_would_refuse(tmp_path):
    """dc_fsm luna14: a real fix cost 0.85 points of agreement with peers that share the defect."""
    s = _session(tmp_path, _Fixed(+0.6))
    r = s._consensus_decision({}, _judged(0.9981, 0.9896), *UP, "old", 0, None, "{}", is_sim_pass=True)
    assert r["is_action_executed"] and r["accept_reason"].startswith("LATCHED ON THE SPECIFICATION")
    assert s.best_rtl == "new"


def test_the_judge_refuses_a_regression_the_tolerance_would_keep(tmp_path):
    s = _session(tmp_path, _Fixed(-1.0))
    r = s._consensus_decision({}, _judged(0.8604, 0.8600), *UP, "old", 2, None, "{}")
    assert not r.get("is_action_executed") and Path(s.rtl_path).read_text() == "old"
    assert "THE PREVIOUS BEHAVIOUR" in r["error_msg"] and "TP-0001" in r["error_msg"]


def test_when_every_answer_abstains_the_tolerance_decides(tmp_path):
    s = _session(tmp_path, _Fixed(0.0))
    r = s._consensus_decision({}, _judged(0.9981, 0.9978), *UP, "old", 0, None, "{}", is_sim_pass=True)
    assert r["is_action_executed"] and "WITHIN TOLERANCE" in r["accept_reason"]
    assert "could not decide" in r["accept_reason"]


def test_the_judge_is_not_asked_when_agreement_decides(tmp_path):
    rise, fall = _Fixed(-1.0), _Fixed(+1.0)
    r = _session(tmp_path, rise)._consensus_decision({}, _judged(0.5, 0.6), *UP, "old", 0, None, "{}",
                                                      is_sim_pass=True)
    assert r["is_action_executed"] and rise.calls == 0
    r = _session(tmp_path, fall)._consensus_decision({}, _judged(0.9916, 0.3807), *UP, "old", 2, None, "{}")
    assert not r.get("is_action_executed") and fall.calls == 0, "a 61-point fall is refused unasked"


def test_the_arbiter_needs_the_consensus_latch():
    with pytest.raises(ValueError):
        RTLEditor(None, sim_reviewer=None, latch_arbiter=_Fixed(1.0))
