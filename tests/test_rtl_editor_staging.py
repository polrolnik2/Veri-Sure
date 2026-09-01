"""Edits stage; only a commit builds and runs.

`replace_block` used to splice, write the file, simulate, and accept or roll
back on the spot -- so A COHERENT CHANGE SPANNING SEVERAL BLOCKS COULD NOT BE
EXPRESSED: every intermediate state is broken by construction and was discarded
as a regression. These pin the buffer that fixes it, and the two hazards it
introduces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from eda_agent.explain import RequirementView
from eda_agent.rtl_editor import _EditSession
from eda_agent.sim_reviewer import overdriven_signals
from eda_agent.trace_slicer import RtlBlock, parse_rtl_blocks

RTL = """\
module m(input clk, input a, output b, output c);
assign b = a;

always @(posedge clk) begin
  c <= a;
end

endmodule
"""

# The fixture above is deliberately loose -- most pins never lint it, and
# `output c` driven procedurally is a PROCASSWIRE error the staging tests do not
# care about. The two driver pins DO lint, so they get a module that compiles.
LINTABLE = """\
module m(input clk, input a, output b, output reg c);
wire w;
assign w = a;
assign b = w;

always @(posedge clk) begin
  c <= a;
end

endmodule
"""

@dataclass
class _Uncovered:
    """An OracleResult that abstained: ok is None and there is no edge."""

    ok: bool | None = None
    detail: str = "the activation never occurred"
    edge: int | None = None
    rows: list | None = None
    tp_uid: str = "TP-0009"


B_ASSIGN = "assign b = a;"
B_ALWAYS = "always @(posedge clk) begin\n  c <= a;\nend"


def _session(tmp_path, rtl: str = RTL) -> _EditSession:
    path = tmp_path / "rtl.sv"
    path.write_text(rtl)
    s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                     last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
    s.blocks_by_id = {
        "blk_assign": RtlBlock(id="blk_assign", kind="assign", start_line=2,
                               end_line=2, clocking="", code=B_ASSIGN,
                               writes=("b",), reads=("a",)),
        "blk_always": RtlBlock(id="blk_always", kind="always", start_line=4,
                               end_line=6, clocking="posedge clk",
                               code=B_ALWAYS, writes=("c",), reads=("a",)),
    }
    return s


# ------------------------------------------------- the buffer, and the file


def test_a_staged_edit_never_touches_the_accepted_file(tmp_path):
    """THE PROPERTY THAT REMOVES ROLLBACK. Rollback existed only because edits
    were applied in place, and its cost was the agent losing the work."""
    s = _session(tmp_path)
    before = s.read_rtl()
    assert s.stage_replace("blk_assign", "assign b = ~a;")["is_action_executed"]
    assert s.read_rtl() == before, "the accepted RTL must be byte-identical"
    assert "assign b = ~a;" in s.staged()


def test_discard_returns_the_buffer_to_the_accepted_rtl(tmp_path):
    s = _session(tmp_path)
    s.stage_replace("blk_assign", "assign b = ~a;")
    s.discard_staged()
    assert s.staged() == RTL
    assert s.staged_rtl is None and not s.staged_text and not s.retired_ids


def test_two_edits_to_different_blocks_both_apply(tmp_path):
    s = _session(tmp_path)
    assert s.stage_replace("blk_assign", "assign b = ~a;")["is_action_executed"]
    assert s.stage_replace("blk_always", "always @(posedge clk) c <= ~a;")[
        "is_action_executed"]
    out = s.staged()
    assert "assign b = ~a;" in out and "c <= ~a;" in out


def test_a_block_can_be_refined_after_it_was_already_staged(tmp_path):
    """The anchor follows the block, so an agent may correct its own edit.
    Anchoring on the ORIGINAL text forever would make this indistinguishable
    from editing against an anchor some other edit destroyed."""
    s = _session(tmp_path)
    s.stage_replace("blk_assign", "assign b = ~a;")
    assert s.stage_replace("blk_assign", "assign b = a & 1'b1;")[
        "is_action_executed"]
    assert "assign b = a & 1'b1;" in s.staged()
    assert "assign b = ~a;" not in s.staged()


def test_an_edit_whose_anchor_a_previous_one_destroyed_is_REFUSED(tmp_path):
    """THE LOAD-BEARING PIN. `blocks_by_id` carries LINE bounds, and one staged
    edit shifts every line after it -- so a line-number implementation would
    splice into the wrong place silently, which is the worst available outcome.
    Content anchoring makes the collision an explicit refusal."""
    s = _session(tmp_path)
    # An edit that swallows the always block along with the assign.
    s.stage_replace("blk_assign", "assign b = a;\n\nalways @(posedge clk) c <= a;")
    s.staged_rtl = s.staged().replace(B_ALWAYS, "")     # its text is now gone
    res = s.stage_replace("blk_always", "always @(posedge clk) c <= 1'b0;")
    assert not res["is_action_executed"]
    assert "not in the buffer" in res["error_msg"]
    assert "staged edit overlapped" in res["error_msg"]


def test_an_ambiguous_anchor_is_refused_rather_than_guessed(tmp_path):
    s = _session(tmp_path, RTL + "\nassign b = a;\n")
    res = s.stage_replace("blk_assign", "assign b = ~a;")
    assert not res["is_action_executed"] and "appears 2 times" in res["error_msg"]


# ------------------------------------------------------ add_block / remove_block


def test_add_block_after_a_block_and_at_module_end(tmp_path):
    s = _session(tmp_path)
    assert s.stage_add("blk_assign", "wire t = a;")["is_action_executed"]
    assert s.staged().index("wire t = a;") > s.staged().index(B_ASSIGN)
    assert s.stage_add("endmodule", "wire u = a;")["is_action_executed"]
    assert s.staged().index("wire u = a;") < s.staged().index("endmodule")


def test_an_unknown_anchor_errors_and_stages_nothing(tmp_path):
    s = _session(tmp_path)
    res = s.stage_add("blk_nope", "wire t = a;")
    assert not res["is_action_executed"] and "Unknown anchor" in res["error_msg"]
    assert s.staged_rtl is None, "a refused edit must stage nothing"


def test_remove_block_deletes_it_and_RETIRES_the_id(tmp_path):
    """A removed id is not an unknown id. Reporting "unknown block_id" would
    read as the agent's mistake rather than as its own edit."""
    s = _session(tmp_path)
    assert s.stage_remove("blk_always")["is_action_executed"]
    assert B_ALWAYS not in s.staged()
    res = s.stage_replace("blk_always", "always @(posedge clk) c <= 1'b1;")
    assert not res["is_action_executed"]
    assert "removed in this staged batch" in res["error_msg"]


def test_remove_then_add_is_one_batch(tmp_path):
    """The common "replace a block with a differently-shaped one" case."""
    s = _session(tmp_path)
    s.stage_remove("blk_always")
    s.stage_add("endmodule", "always @(posedge clk) c <= ~a;")
    out = s.staged()
    assert "c <= a;" not in out and "c <= ~a;" in out


# ------------------------------------------------------------- driver warnings


def test_removing_the_last_driver_of_a_read_signal_WARNS(tmp_path):
    """The mirror of the multi-driver guard, and it must exist because the
    failure is otherwise silent: `-Wno-fatal` means UNDRIVEN does not fail the
    build, the signal becomes X, the oracle X-guard turns that into an
    abstention, and a deleted driver surfaces only as coverage quietly falling.
    """
    rtl = RTL.replace("assign b = a;", "assign b = a;\nassign d = b;")
    s = _session(tmp_path, rtl)
    s.blocks_by_id["blk_d"] = RtlBlock(
        id="blk_d", kind="assign", start_line=3, end_line=3, clocking="",
        code="assign d = b;", writes=("d",), reads=("b",))
    res = s.stage_remove("blk_assign")
    assert res["is_action_executed"], "it must APPLY, not be refused"
    assert any("LOST their" in w and "b" in w for w in res["warnings"])


def test_a_broken_intermediate_state_WARNS_BUT_APPLIES(tmp_path):
    """THE PIN THAT KEEPS BATCHING POSSIBLE. Remove a block and its signal has
    no driver until the replacement lands two edits later; refusing there would
    break exactly the workflow the staged buffer exists for."""
    rtl = RTL.replace("assign b = a;", "assign b = a;\nassign d = b;")
    s = _session(tmp_path, rtl)
    s.blocks_by_id["blk_d"] = RtlBlock(
        id="blk_d", kind="assign", start_line=3, end_line=3, clocking="",
        code="assign d = b;", writes=("d",), reads=("b",))
    assert s.stage_remove("blk_assign")["is_action_executed"]
    res = s.stage_add("endmodule", "assign b = ~a;")     # the batch completes
    assert res["is_action_executed"]
    assert "assign b = ~a;" in s.staged()


def test_two_surviving_assigns_to_one_signal_are_flagged_cheaply(tmp_path):
    """Per-edit warnings are pure Python from the block table: the real check
    shells out to Verilator and costs ~1s, which is fine once per check_staged
    and far too much per keystroke."""
    s = _session(tmp_path)
    res = s.stage_add("endmodule", "assign b = 1'b0;")
    assert res["is_action_executed"]
    s.blocks_by_id["blk_dup"] = RtlBlock(
        id="blk_dup", kind="assign", start_line=99, end_line=99, clocking="",
        code="assign b = 1'b0;", writes=("b",), reads=())
    assert any("MORE THAN ONE" in w for w in s.driver_warnings())


@pytest.mark.parametrize("meth,args", [
    ("stage_replace", ("blk_nope", "x")),
    ("stage_remove", ("blk_nope",)),
])
def test_unknown_ids_are_rejected_uniformly(tmp_path, meth, args):
    s = _session(tmp_path)
    res = getattr(s, meth)(*args)
    assert not res["is_action_executed"] and "Unknown block_id" in res["error_msg"]


# ------------------------------------------------------------------ commit
#
# `commit` is the trial and the only one. These pin the three things that make
# that fair: it never destroys the agent's work, it never half-writes the
# accepted RTL, and it catches at claim-complete time what the per-edit warnings
# were deliberately not allowed to refuse.


class _Reviewer:
    """Stands in for `SimReviewer`, counting how often the suite actually ran.

    The batching claim is "no simulation until commit", and asserting that on
    an INVOCATION COUNT is the only way to state it -- a wall-clock assertion
    would pass on a fast machine with the simulation still happening.
    """

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def review(self):
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _committable(tmp_path, results, *, syntax=(True, ""), multi=(),
                 monkeypatch=None, rtl=None):
    """A session whose commit path is stubbed down to the decisions under test.

    `check_syntax` and `multidriven_signals` shell out to Verilator; the point
    here is the accept/keep/latch bookkeeping around them, not Verilator.
    """
    import eda_agent.rtl_editor as mod
    s = _session(tmp_path) if rtl is None else _session(tmp_path, rtl)
    s.sim_reviewer = _Reviewer(results)
    monkeypatch.setattr(mod, "check_syntax", lambda _p: syntax)
    monkeypatch.setattr(mod, "multidriven_signals",
                        lambda pth: set(multi) if str(pth).endswith("staged.sv") else set())
    monkeypatch.setattr(s, "_refresh_trace", lambda **_kw: None)
    return s


def test_staging_runs_NO_simulation_and_commit_runs_exactly_one(tmp_path, monkeypatch):
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch)
    s.stage_replace("blk_assign", "assign b = ~a;")
    s.stage_replace("blk_always", "always @(posedge clk) begin\n  c <= ~w;\nend")
    assert s.sim_reviewer.calls == 0, "staging must not simulate"
    assert s.action_calls == 0, "staging must not spend a trial"
    s.commit()
    assert s.sim_reviewer.calls == 1, "one commit, one suite run"


def test_action_calls_counts_COMMITS_not_edits(tmp_path, monkeypatch):
    """§7.3: max_trials becomes 30 compile-and-test cycles, and the edits inside
    each are free. A budget counting individual edits is an order of magnitude
    tighter than one counting rounds."""
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch)
    s.stage_replace("blk_assign", "assign b = ~a;")
    s.stage_remove("blk_always")
    s.stage_add("endmodule", "assign c = a;")
    s.check_staged()
    assert s.action_calls == 0
    s.commit()
    assert s.action_calls == 1


def test_a_commit_that_does_not_improve_KEEPS_the_batch_and_the_file(tmp_path, monkeypatch):
    """Pin 5, and the whole argument for staging. A failed attempt costs a trial
    and NOTHING ELSE: the accepted RTL is byte-identical and the agent's work
    survives, so it adjusts the batch instead of starting from the baseline."""
    s = _committable(tmp_path, [(False, 99, "{}")], monkeypatch=monkeypatch)
    s.last_mismatch_cnt = 3
    before = s.read_rtl()
    s.stage_replace("blk_assign", "assign b = ~a;")
    res = s.commit()
    assert not res["is_action_executed"]
    assert res["staged_kept"] is True
    assert s.read_rtl() == before, "the accepted RTL must be byte-identical"
    assert s.staged_rtl is not None and "assign b = ~a;" in s.staged()


def test_a_commit_that_improves_LATCHES_and_clears_the_batch(tmp_path, monkeypatch):
    s = _committable(tmp_path, [(False, 1, "{}")], monkeypatch=monkeypatch)
    s.last_mismatch_cnt = 3
    s.stage_replace("blk_assign", "assign b = ~a;")
    res = s.commit()
    assert res["is_action_executed"] and res["staged_kept"] is False
    assert "assign b = ~a;" in s.read_rtl()
    assert s.staged_rtl is None and not s.staged_text and not s.retired_ids


def test_a_commit_that_fails_to_compile_costs_a_trial_and_keeps_the_batch(tmp_path, monkeypatch):
    """Pin 19 on the price, and the staging argument on the buffer: the agent
    should fix its syntax, not lose the batch over it."""
    s = _committable(tmp_path, [(True, 0, "{}")], syntax=(False, "syntax: boom"),
                     monkeypatch=monkeypatch)
    before = s.read_rtl()
    s.stage_replace("blk_assign", "assign b = ~a")
    res = s.commit()
    assert res["is_action_executed"] is False
    assert res["is_syntax_correct"] is False and "boom" in res["syntax_output"]
    assert s.action_calls == 1, "a failed compile still costs a trial"
    assert s.sim_reviewer.calls == 0, "and never reaches the simulator"
    assert s.read_rtl() == before
    assert s.staged_rtl is not None


def test_nothing_staged_is_not_a_trial(tmp_path, monkeypatch):
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch)
    res = s.commit()
    assert not res["is_action_executed"] and s.action_calls == 0
    assert "nothing to commit" in res["error_msg"].lower()


def test_max_trials_refuses_a_COMMIT_and_staging_stays_open(tmp_path, monkeypatch):
    """Pin 18: the refusal is on the commit, and the agent can still be asked to
    explain itself afterwards."""
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch)
    s.max_trials = 1
    s.stage_replace("blk_assign", "assign b = ~a;")
    assert s.commit()["is_action_executed"]
    assert s.stage_replace("blk_always", "always @(posedge clk) c <= ~a;")["is_action_executed"]
    res = s.commit()
    assert not res["is_action_executed"] and "maximum debug trials" in res["error_msg"]
    assert s.action_calls == 1, "a refused commit does not spend the budget again"
    # Staging stays open after the refusal, so the agent can still be asked to
    # explain itself rather than being cut off mid-thought.
    assert s.stage_add("endmodule", "assign d = a;")["is_action_executed"]


def test_a_removed_last_driver_FAILS_THE_COMMIT(tmp_path, monkeypatch):
    """Pin 15, the load-bearing one. Verilator runs -Wno-fatal, so UNDRIVEN does
    not fail the build: the signal goes X, the oracle X-guard turns that into an
    abstention, and the defect would surface only as coverage quietly falling
    with nothing naming the cause."""
    # THE SOURCE MUST EXPRESS THE DEPENDENCY, not just the block table. This
    # used to monkeypatch `blk_always`'s metadata to claim it reads `b` while
    # the code said `c <= a` -- which passed only because the guard trusted the
    # table. The guard now parses the text, so the fixture says what it means.
    rtl = RTL.replace("c <= a;", "c <= b;")
    body = B_ALWAYS.replace("c <= a;", "c <= b;")
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch,
                     rtl=rtl)
    s.blocks_by_id["blk_always"] = RtlBlock(
        id="blk_always", kind="always", start_line=4, end_line=6,
        clocking="posedge clk", code=body, writes=("c",), reads=("b",))
    before = s.read_rtl()
    s.stage_remove("blk_assign")            # b loses its only driver
    res = s.commit()
    assert not res["is_action_executed"]
    assert "b" in res["error_msg"] and "LAST driver" in res["error_msg"]
    assert s.sim_reviewer.calls == 0
    assert s.read_rtl() == before
    assert s.staged_rtl is not None, "the batch survives so it can be completed"


def test_a_second_continuous_driver_FAILS_THE_COMMIT(tmp_path, monkeypatch):
    """Pin 12, at the point the batch is claimed complete rather than per edit."""
    s = _committable(tmp_path, [(True, 0, "{}")], multi=("b",), monkeypatch=monkeypatch)
    before = s.read_rtl()
    s.stage_add("endmodule", "assign b = 1'b0;")
    res = s.commit()
    assert not res["is_action_executed"]
    assert "MORE THAN ONE continuous driver" in res["error_msg"]
    assert s.sim_reviewer.calls == 0 and s.read_rtl() == before


def test_remove_then_add_commits_as_ONE_trial(tmp_path, monkeypatch):
    """Pin 16: the common 'replace a block with a differently-shaped one' case."""
    s = _committable(tmp_path, [(False, 1, "{}")], monkeypatch=monkeypatch)
    s.last_mismatch_cnt = 5
    s.stage_remove("blk_assign")
    s.stage_add("endmodule", "assign b = ~a;")
    res = s.commit()
    assert res["is_action_executed"] and s.action_calls == 1
    assert s.sim_reviewer.calls == 1
    text = s.read_rtl()
    assert "assign b = ~a;" in text and "assign b = a;" not in text


def test_commit_does_not_inflate_the_check_staged_counter(tmp_path, monkeypatch):
    """`check_calls` is reported as a finding ABOUT THE AGENT -- fifty dry runs
    against two commits. Counting commit's own pre-flight there would corrupt
    the number it exists to expose."""
    s = _committable(tmp_path, [(True, 0, "{}")], monkeypatch=monkeypatch)
    s.stage_replace("blk_assign", "assign b = ~a;")
    s.check_staged()
    s.commit()
    assert s.check_calls == 1


def test_check_staged_is_free_unbounded_and_counted(tmp_path, monkeypatch):
    """Pins 20 and 23: it reports a syntax error without writing the accepted
    file, simulating, or consuming a trial -- and is never capped silently."""
    s = _committable(tmp_path, [(True, 0, "{}")], syntax=(False, "syntax: boom"),
                     monkeypatch=monkeypatch)
    before = s.read_rtl()
    s.stage_replace("blk_assign", "assign b = ~a")
    for _ in range(50):
        res = s.check_staged()
    assert res["is_syntax_correct"] is False and "boom" in res["syntax_output"]
    assert res["check_calls"] == 50, "counted, and never silently capped"
    assert s.action_calls == 0 and s.sim_reviewer.calls == 0
    assert s.read_rtl() == before


# ------------------------------------------------- read_block sees the batch


def test_read_block_shows_the_STAGED_text_with_commit_line_numbers(tmp_path):
    """Pin 8. Showing the trace report's copy would hand the agent the text it
    edited away from, at line numbers one staged edit above it already broke."""
    s = _session(tmp_path)
    s.stage_add("blk_assign", "assign c2 = a;\nassign c3 = a;")
    out = s.read_block("blk_always")
    first = out.splitlines()[0]
    lineno = int(first.split(":")[0])
    assert s.staged().splitlines()[lineno - 1] == B_ALWAYS.splitlines()[0]


def test_read_block_on_a_removed_id_says_REMOVED_not_unknown(tmp_path):
    """Pin 14: three different facts, and reporting the agent's own deletion as
    'unknown block_id' names the wrong one."""
    s = _session(tmp_path)
    s.stage_remove("blk_assign")
    out = s.read_block("blk_assign")
    assert "removed in this staged batch" in out and "Unknown" not in out
    assert "Unknown block_id" in s.read_block("blk_nope")


def test_a_dead_anchor_names_BOTH_causes(tmp_path):
    """The message used to blame "an earlier staged edit" alone. Since a latched
    commit also invalidates the block table, that sent the agent looking for an
    overlap that did not exist."""
    s = _session(tmp_path)
    s.write_rtl(RTL.replace(B_ASSIGN, "assign b = a ^ 1'b0;"))   # as if a commit landed
    res = s.stage_replace("blk_assign", "assign b = ~a;")
    assert not res["is_action_executed"]
    assert "staged edit overlapped" in res["error_msg"]
    assert "commit has latched" in res["error_msg"]


# ------------------------------------------------------------ add_stimulus
#
# "Decides nothing" is a property of the CURRENT DESIGN, not of the stimulus:
# an oracle abstains when its activation never occurred, and whether it occurs
# depends on what the design does. #98 is the case on record -- a two-tick
# command handshake meant brief cmd pulses never left IDLE and everything
# downstream abstained. So the loop that edits the design is exactly where this
# has to be reachable.


class _Stager:
    def __init__(self, out=None, boom=False):
        self.calls = []
        self.out = out if out is not None else {"added": "TP-0400", "attached_to": ["REQ-0031"]}
        self.boom = boom

    def add_stimulus(self, req_uid, what_the_scenario_needs):
        self.calls.append((req_uid, what_the_scenario_needs))
        if self.boom:
            raise RuntimeError("generator died")
        return self.out


def test_add_stimulus_delegates_and_costs_no_trial(tmp_path):
    s = _session(tmp_path)
    s.stimulus_stager = _Stager()
    out = s.add_stimulus("REQ-0031", "issue a WRITE and hold ena until cmd_ack")
    assert out["added"] == "TP-0400"
    assert s.stimulus_stager.calls == [
        ("REQ-0031", "issue a WRITE and hold ena until cmd_ack")]
    assert s.action_calls == 0, "gathering evidence is not a design hypothesis"


def test_add_stimulus_without_a_route_says_so_instead_of_failing(tmp_path):
    """A backend that cannot mint testpoints leaves the tool REGISTERED and
    refusing. Hiding it would leave the agent with an uncovered requirement, no
    remedy, and no explanation."""
    s = _session(tmp_path)
    out = s.add_stimulus("REQ-0031", "anything")
    assert "no stimulus route" in out["error"]
    assert "testplan gap" in out["error"]


def test_a_stager_that_raises_is_reported_not_propagated(tmp_path):
    s = _session(tmp_path)
    s.stimulus_stager = _Stager(boom=True)
    out = s.add_stimulus("REQ-0031", "anything")
    assert "stimulus staging failed" in out["error"]


def test_the_stimulus_route_never_touches_the_rtl(tmp_path):
    """It APPENDS evidence. The design is not edited, which is what keeps the
    tool safe to hand an agent whose score falls with the failing count."""
    s = _session(tmp_path)
    s.stimulus_stager = _Stager()
    before = s.read_rtl()
    s.add_stimulus("REQ-0031", "drive sda_i low while the controller released SDA")
    assert s.read_rtl() == before and s.staged_rtl is None


# ----------------------------------------- the specflow backend's stimulus route


def _stager(tmp_path, monkeypatch, steps=None, checks=None):
    import eda_agent.specflow_node as node
    run = tmp_path / "run"
    (run / "specflow").mkdir(parents=True)
    (run / "specflow/testplan.json").write_text(json.dumps({"elements": [
        {"uid": "TP-0000", "tp_uid": "TP-0000", "covers": ["REQ-0001@1"]}]}))
    (run / "specflow/stimulus.json").write_text(json.dumps({"testpoints": [
        {"tp_uid": "TP-0000", "stimulus_steps": [{"inputs": {"a": 1}}]}]}))
    (run / "specflow/requirements.json").write_text(json.dumps({"requirements": [
        {"uid": "REQ-0031", "text": "the thing"}]}))
    if checks is not None:
        (run / "specflow/coverage_model.json").write_text(json.dumps({"checks": checks}))
    s = node.SpecflowStimulusStager(
        run_dir=run, contract={}, bins=[{"uid": "BIN-0001"}],
        suite_dir=tmp_path / "suite", model_port=object())
    rendered = {}
    monkeypatch.setattr(node, "SpecflowStimulusStager", node.SpecflowStimulusStager)
    import specflow.tb.render as render_mod
    import specflow.testcase_agent as tca
    monkeypatch.setattr(tca, "stimulus_for_scenario",
                        lambda **kw: (steps if steps is not None else [{"inputs": {"a": 0}}]))
    monkeypatch.setattr(render_mod, "render_suite",
                        lambda **kw: rendered.update(kw) or {})
    return s, run, rendered


def test_the_stager_refuses_a_requirement_that_is_not_uncovered(tmp_path, monkeypatch):
    """Mirrors the refmodel arm's rule: the target must already be reported
    uncovered, so it cannot be invented. A FAILING requirement is evidence about
    the design and no amount of stimulus discharges it."""
    s, _, _ = _stager(tmp_path, monkeypatch, checks=[{"uid": "CHK-0001"}])
    out = s.add_stimulus("REQ-0031", "do the thing")
    assert "not currently uncovered" in out["error"]


def test_the_stager_appends_and_rerenders(tmp_path, monkeypatch):
    s, run, rendered = _stager(tmp_path, monkeypatch, checks=[{"uid": "CHK-0001"}])
    s.uncovered = {"REQ-0031"}
    out = s.add_stimulus("REQ-0031", "hold ena until cmd_ack")
    assert out["covers"] == "REQ-0031" and out["added"].startswith("TP-")
    # APPEND-ONLY: the original testpoint is still there.
    tp = json.loads((run / "specflow/testplan.json").read_text())["elements"]
    assert [e["tp_uid"] for e in tp] == ["TP-0000", out["added"]]
    # And the suite was re-rendered, or the new testpoint would never be run.
    assert rendered["stimulus_by_tp"].keys() == {"TP-0000", out["added"]}
    assert rendered["checks"] == [{"uid": "CHK-0001"}], "checks must survive the re-render"


def test_a_missing_coverage_model_REFUSES_rather_than_dropping_every_check(
        tmp_path, monkeypatch):
    """Re-rendering with an empty check list produces a suite that passes
    because it stopped looking. That must never be the quiet outcome."""
    s, run, rendered = _stager(tmp_path, monkeypatch, checks=None)
    s.uncovered = {"REQ-0031"}
    out = s.add_stimulus("REQ-0031", "hold ena until cmd_ack")
    assert "stopped looking" in out["error"]
    assert not rendered, "nothing may be rendered when the checks are unknown"


def test_the_budget_is_finite(tmp_path, monkeypatch):
    s, _, _ = _stager(tmp_path, monkeypatch, checks=[])
    s.uncovered = {"REQ-0031"}
    s.added = ["TP-1"] * s.budget
    assert "budget spent" in s.add_stimulus("REQ-0031", "x")["error"]


def test_uncovered_requirements_needs_EVERY_covering_testpoint_idle(tmp_path):
    """Under-approximating is the safe direction: it can refuse to stage a
    requirement that would have benefited, and can never let the agent bury an
    existing verdict under new testpoints."""
    from eda_agent.specflow_node import _uncovered_requirements
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "manifest.json").write_text(json.dumps({"testpoints": [
        {"tp_uid": "TP-0", "covers": ["REQ-A@1", "REQ-B@1"]},
        {"tp_uid": "TP-1", "covers": ["REQ-B@1"]},
    ]}))
    assert _uncovered_requirements(["TP-0"], suite) == {"REQ-A"}
    assert _uncovered_requirements(["TP-0", "TP-1"], suite) == {"REQ-A", "REQ-B"}
    assert _uncovered_requirements([], suite) == set()


# --------------------------------------------------- focus / explain on the session


def test_focus_narrows_the_block_table_and_read_block_follows(tmp_path):
    from eda_agent.explain import RequirementView
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "b", "dir": "output", "width": 1},
                         {"name": "c", "dir": "output", "width": 1}]}
    s.requirements = {
        "REQ-B": RequirementView(req_uid="REQ-B", text="b follows a", ports=["b"]),
        "REQ-C": RequirementView(req_uid="REQ-C", text="c registers a", ports=["c"]),
    }
    out = s.focus("REQ-B")
    assert out["is_action_executed"] and s.focused == "REQ-B"
    ids = {b["id"] for b in out["suspect_blocks"]}
    assert ids and ids == set(s.blocks_by_id)
    # read_block still works against the narrowed table.
    one = next(iter(ids))
    assert "ERROR" not in s.read_block(one)
    assert {b["id"] for b in s.focus("REQ-C")["suspect_blocks"]} != ids


def test_focus_on_an_unknown_requirement_says_which_are_known(tmp_path):
    from eda_agent.explain import RequirementView
    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", ports=["b"])}
    out = s.focus("REQ-NOPE")
    assert not out["is_action_executed"] and "REQ-B" in out["error_msg"]


def test_explain_without_a_result_still_returns_what_the_requirement_OWES(tmp_path):
    """Knowing what the design owes is useful even with no verdict to attach it
    to -- and it is the half the loop never had at all."""
    from eda_agent.explain import RequirementView
    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(
        req_uid="REQ-B", text="b shall follow a", expectation="b is high")}
    out = s.explain("REQ-B")
    assert out["is_action_executed"]
    assert out["requirement"]["requirement"] == "b shall follow a"
    assert "no per-requirement result" in out["note"]


def test_list_failing_requirements_reports_requirements_not_check_ids(tmp_path):
    from dataclasses import dataclass as _dc

    from eda_agent.explain import RequirementView

    @_dc
    class R:
        ok: bool | None
        detail: str = ""
        tp_uid: str = ""
    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", text="b follows a",
                                               ports=["b"])}
    s.req_results = {"REQ-B": (R(False, "b fell early", "TP-0002"), {})}
    out = s.list_failing_requirements()
    assert out["failing"] == [{"req_uid": "REQ-B", "verdict": "FAILS",
                               "requirement": "b follows a",
                               "check_said": "b fell early",
                               "testpoint": "TP-0002", "ports": ["b"]}]
    assert out["uncovered"] == [] and out["passing_count"] == 0


def test_list_failing_requirements_counts_passing_and_lists_uncovered(tmp_path):
    """A pass is a number; a FAILS or an UNCOVERED is a row.

    The frozen set is around ninety requirements and most of them pass. Listing
    each would bury the handful that need work, and dropping the count entirely
    would hide the one number a repair must not spend -- an edit that fixes one
    requirement by breaking four is a regression the agent cannot otherwise see.
    """
    from dataclasses import dataclass as _dc

    from eda_agent.explain import RequirementView

    @_dc
    class R:
        ok: bool | None
        detail: str = ""
        tp_uid: str = ""
    s = _session(tmp_path)
    s.requirements = {u: RequirementView(req_uid=u, text=f"{u} text", ports=["b"])
                      for u in ("REQ-A", "REQ-B", "REQ-C", "REQ-D")}
    s.req_results = {
        "REQ-A": (R(True, "held"), {}),
        "REQ-B": (R(True, "held"), {}),
        "REQ-C": (R(False, "b fell early", "TP-1"), {}),
        "REQ-D": (R(None, "the activation never occurred"), {}),
    }
    out = s.list_failing_requirements()
    assert out["passing_count"] == 2
    assert [r["req_uid"] for r in out["failing"]] == ["REQ-C"]
    assert [r["req_uid"] for r in out["uncovered"]] == ["REQ-D"]
    # The passing ones are counted, never listed.
    listed = {r["req_uid"] for r in out["failing"] + out["uncovered"]}
    assert "REQ-A" not in listed and "REQ-B" not in listed


# --------------------------------------- the link that was missing: req_results


def test_pull_req_results_takes_the_reviewers_verdicts(tmp_path):
    """`req_results` was read by two tools and written by nothing.

    `_EditSession.req_results` has always existed, `explain` and
    `list_failing_requirements` have always read it, and no code path anywhere
    assigned to it -- so the requirement surface was registered as tools,
    described in the prompt, and permanently empty. This is the assignment.
    """
    s = _session(tmp_path)

    class _Reviewer:
        req_results = {"REQ-A": ("result", {"tp_uid": "TP-0001"})}
        vcd_path = tmp_path / "wave.vcd"

    s.sim_reviewer = _Reviewer()
    s._pull_req_results()
    assert s.req_results == {"REQ-A": ("result", {"tp_uid": "TP-0001"})}
    assert s.vcd_path == tmp_path / "wave.vcd"


def test_pull_req_results_is_a_copy_not_the_reviewers_own_dict(tmp_path):
    """Otherwise the next run mutates what `explain` is already holding."""
    s = _session(tmp_path)

    class _Reviewer:
        req_results = {"REQ-A": ("first", {})}
        vcd_path = None

    rev = _Reviewer()
    s.sim_reviewer = rev
    s._pull_req_results()
    rev.req_results["REQ-B"] = ("second", {})
    assert list(s.req_results) == ["REQ-A"]


def test_pull_req_results_degrades_on_a_backend_that_cannot_decide(tmp_path):
    """The SystemVerilog reviewer has no oracle set, and that must not raise.

    Duck-typed on purpose: a backend that decides per requirement publishes
    `req_results`, one that cannot publishes nothing, and the surface stays
    empty rather than the session failing.
    """
    s = _session(tmp_path)
    s.sim_reviewer = object()
    s._pull_req_results()
    assert s.req_results == {}
    assert s.vcd_path is None


# ------------------------- the dry run has to say "this would be rejected"


def _real_session(tmp_path):
    """A session over RTL that ACTUALLY COMPILES.

    The module-level fixture does not: `output c` driven from an `always` block
    is not legal Verilog-2005, so `check_syntax` rejects it before and after any
    edit. Every existing staging test is fine with that -- they assert on the
    buffer, not on Verilator -- but a test about the COMMIT VERDICT has to run
    against something a commit could accept, or it only measures the fixture.
    """
    from eda_agent.trace_slicer import RtlBlock
    # `w` is driven by one block and READ BY THE OTHER, which is what makes the
    # removal detectable: `undriven_signals` reports a lost driver only when a
    # surviving block still reads the signal. A module output driven by the
    # removed block and read by nothing is not a dangling read.
    rtl = ("module m(input clk, input a, output reg c);\n"
           "wire w;\n"
           "assign w = a;\n"
           "\n"
           "always @(posedge clk) begin\n"
           "  c <= w;\n"
           "end\n"
           "\n"
           "endmodule\n")
    path = tmp_path / "rtl.sv"
    path.write_text(rtl)
    s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                     last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
    s.blocks_by_id = {
        "blk_assign": RtlBlock(id="blk_assign", kind="assign", start_line=3,
                               end_line=3, clocking="", code="assign w = a;",
                               writes=("w",), reads=("a",)),
        "blk_always": RtlBlock(id="blk_always", kind="always", start_line=5,
                               end_line=7, clocking="posedge clk",
                               code="always @(posedge clk) begin\n  c <= w;\nend",
                               writes=("c",), reads=("w",)),
    }
    return s


def test_check_staged_reports_the_commit_verdict_not_only_findings(tmp_path):
    """MEASURED on the first live run, and it cost the session its only trial.

    The agent called `check_staged()`, was told "scl_oen, sda_chk, sda_oen,
    state are still read but have LOST their last driver", committed anyway,
    and the commit was rejected for exactly that. The information was there;
    the SHAPE was not -- `commit` says "Commit rejected: ...", `check_staged`
    returned the same fact as a bare string in a `warnings` list under a field
    reading `is_syntax_correct: true`.
    """
    s = _real_session(tmp_path)
    # Remove the block driving `w`, which the always block still reads.
    s.stage_remove("blk_assign")
    out = s.check_staged()
    assert out["would_commit_be_rejected"] is True
    assert "would be REJECTED" in out["verdict"]
    assert "w" in out["verdict"]
    # And the same batch IS actually rejected, so the free call and the paid one
    # cannot disagree about the same buffer.
    assert "removed their LAST driver" in (s.commit().get("error_msg") or "")


def test_check_staged_on_a_clean_batch_says_a_commit_would_proceed(tmp_path):
    """The other half of a verdict: silence is not an answer either."""
    s = _real_session(tmp_path)
    s.stage_replace("blk_always", "always @(posedge clk) begin\n  c <= ~w;\nend")
    out = s.check_staged()
    assert out["would_commit_be_rejected"] is False
    assert "would proceed to simulation" in out["verdict"]
    # Verilator's build report, and its DECLFILENAME warning about the scratch
    # file's own name, are 900 characters of noise above the finding.
    assert out["syntax_output"] == "clean"


# ------------------- what the first live run showed the agent was NOT told


def test_explain_says_when_there_is_no_waveform_at_all(tmp_path):
    """An empty internals section and a missing waveform are DIFFERENT facts.

    MEASURED on the first live editor run: all five `explain` calls came back
    with `block_internals: {}` because the suite had been run with
    `trace=False`, and nothing in the payload said so -- so the agent spent the
    session reading boundary ports and source believing it had been shown
    everything. That is the evidence state B21 records the debugger inventing a
    timing theory from.
    """
    from dataclasses import dataclass as _dc

    from eda_agent.explain import RequirementView

    @_dc
    class R:
        ok: bool | None = False
        detail: str = "b fell early"
        edge: int = 3
        rows: list = None
        tp_uid: str = "TP-0001"

    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(
        req_uid="REQ-B", text="b follows a", ports=["b"],
        source="def decide(trace):\n    return False\n")}
    s.req_results = {"REQ-B": (R(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {"a": 1}, "dut": {"b": 0}}]})}
    out = s.explain("REQ-B")
    assert out["block_internals"] == {}
    assert "NO INTERNAL SIGNALS ARE SHOWN" in out["internals_warning"]
    assert "dumped no waveform" in out["internals_warning"]


def test_explain_uses_THIS_requirements_testpoint_waveform(tmp_path):
    """One waveform per testpoint, because that is how the suite writes them.

    A single session-wide `vcd_path` cannot be right for every requirement, and
    reading the wrong testpoint's waveform is worse than reading none: it looks
    like data.
    """
    from dataclasses import dataclass as _dc

    from eda_agent.explain import RequirementView

    @_dc
    class R:
        ok: bool | None = False
        detail: str = "b fell early"
        edge: int = 0
        rows: list = None
        tp_uid: str = "TP-0007"

    s = _session(tmp_path)
    mine = tmp_path / "wave_0_test_TP0007.vcd"
    other = tmp_path / "wave_0_test_TP0000.vcd"
    for p in (mine, other):
        p.write_text("$enddefinitions $end\n")
    s.vcd_path = other
    s.vcd_by_tp = {"TP-0007": mine, "TP-0000": other}
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", text="t",
                                               ports=["b"], source="")}
    s.req_results = {"REQ-B": (R(rows=[]), {"edges": []})}

    seen = {}
    import eda_agent.explain as _ex
    real = _ex.explain_failure

    def _spy(**kw):
        seen["vcd"] = kw.get("vcd_path")
        return real(**kw)
    _ex.explain_failure = _spy
    try:
        s.explain("REQ-B")
    finally:
        _ex.explain_failure = real
    assert seen["vcd"] == mine


def test_focus_says_which_block_ids_it_just_retired(tmp_path):
    """Focusing NARROWS the slice, and that was silent.

    MEASURED on the first live editor run: the agent read block C3
    successfully, focused a different requirement four rounds later, and its
    `replace_block("C3")` nine rounds after that came back "Unknown block_id" --
    which reads as the agent having invented an id it had in fact been given.
    """
    from eda_agent.explain import RequirementView
    from eda_agent.trace_slicer import RtlBlock

    s = _session(tmp_path)
    s.blocks_by_id = {**(s.blocks_by_id or {}),
                      "blk_gone": RtlBlock(id="blk_gone", kind="assign",
                                           start_line=99, end_line=99,
                                           clocking="", code="assign z = 1'b0;",
                                           writes=("z",), reads=())}
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", text="t",
                                               ports=["b"])}
    out = s.focus("REQ-B")
    assert out["is_action_executed"]
    assert "blk_gone" in out["ids_no_longer_in_scope"]
    assert "no longer resolve" in out["scope_note"]


def test_block_internals_selects_nothing_away(tmp_path):
    """The cap was the bug, and a smarter cap would be a different bug.

    A block's `reads` include every LOCALPARAM it mentions, and
    `sorted(names)[:12]` took those first because ASCII puts CMD_START and
    ST_IDLE ahead of cnt, state and sda_chk. MEASURED on the second live editor
    run: all twelve signals shown were constants, and the state register the
    failure was about never appeared.

    Ranking that cap by transition count would only move the bias -- a `clk_en`
    toggling every cycle would win, an `sda_chk` moving ONCE at the deciding
    edge would be cut, and the second is the more informative. So nothing is
    selected away; the representation changed instead.
    """
    import sys
    import types

    from eda_agent import explain as _ex
    from eda_agent.trace_slicer import RtlBlock

    tv = {
        "CMD_START": [(0, "1000")],                    # a localparam
        "ST_IDLE": [(0, "0000")],                      # another
        "clk_en": [(0, "0"), (610000, "1"), (620000, "0")],
        "sda_chk": [(0, "0"), (630000, "1")],          # ONE change, and the point
        "state": [(0, "0001"), (610000, "0010")],
    }
    # `state` is the root; the others reach it because the block READS them.
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in tv else ""),
        "_vcd_tv": lambda vcd, full: tv[full],
        "_vcd_value_at": lambda series, t, inclusive=False: next(
            (v for tt, v in reversed(series)
             if (tt <= t if inclusive else tt < t)), None),
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$timescale 1ps $end\n")
    try:
        blocks = [RtlBlock(id="b", kind="always", start_line=1, end_line=2,
                           clocking="posedge clk", code="", writes=("state",),
                           reads=("CMD_START", "ST_IDLE", "sda_chk", "clk_en"))]
        got = _ex._block_internals(wave, blocks, [600, 610, 620, 630, 640],
                                   roots=["state"])
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]

    # Every signal that moved is present -- the one-transition one included.
    moved = {r["signal"]: r for r in got["chain"]}
    assert set(moved) == {"clk_en", "sda_chk", "state"}
    assert moved["sda_chk"]["changed"] == [{"t": 630, "v": "1"}]
    # Constants reported once each, not as N identical samples, and each says
    # what drives it (here: nothing -- they are localparams).
    held = got["__held_constant__"]
    assert set(held) == {"CMD_START", "ST_IDLE"}
    assert held["CMD_START"]["value"] == "1000"
    assert held["CMD_START"]["driven_by"] is None


def test_all_constant_internals_reads_as_a_finding_not_as_a_populated_view(tmp_path):
    """Nothing in the suspect blocks moving IS the finding for a temporal check,
    and it must not look like the internals half worked."""
    import sys
    import types

    from dataclasses import dataclass as _dc

    from eda_agent.explain import RequirementView

    @_dc
    class R:
        ok: bool | None = False
        detail: str = "d"
        edge: int = 1
        rows: list = None
        tp_uid: str = "TP-0001"

    series = {"CMD_START": ["1000", "1000"]}
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in series else ""),
        "_vcd_tv": lambda vcd, full: full,
        "_vcd_value_at": lambda tv, t, inclusive=False: series[tv][0],
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$end\n")
    try:
        s = _session(tmp_path)
        s.vcd_by_tp = {"TP-0001": wave}
        s.requirements = {"REQ-B": RequirementView(
            req_uid="REQ-B", text="t", ports=["b"],
            source="def decide(trace):\n    return False\n")}
        s.req_results = {"REQ-B": (R(rows=[]), {"edges": [
            {"edge": 0, "t": 10, "inputs": {}, "dut": {"b": 0}},
            {"edge": 1, "t": 20, "inputs": {}, "dut": {"b": 1}}]})}
        out = s.explain("REQ-B")
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]
    assert "NO INTERNAL SIGNALS ARE SHOWN" in out.get("internals_warning", "")


def test_vcd_lookups_convert_the_traces_NANOSECONDS_to_waveform_ticks(tmp_path):
    """THE TRACE AND THE WAVEFORM COUNT TIME IN DIFFERENT UNITS.

    `Env._record` stamps each row with `get_sim_time("ns")`; Verilator writes
    `$timescale 1ps`. MEASURED on the second live editor run: the trace's last
    row is t=2440 and the waveform runs to 2,440,000 -- the same instant, a
    thousand ticks apart. Every `_vcd_value_at(tv, 600)` was therefore reading
    600 PICOSECONDS into a 2.44-microsecond run, so all 53 signals in the slice
    came back holding their reset value and the internals section was not
    mis-selected but WRONG.

    Exactly the failure §5.6 predicted -- "silently collapses the window to the
    start of the run" -- surviving in the units dimension after being fixed in
    the index dimension. Nothing errors: a lookup before the first change
    legitimately returns the initial value.
    """
    from eda_agent.explain import _vcd_ticks_per_ns

    cases = {"1ps": 1000.0, "1ns": 1.0, "10ps": 100.0, "1us": 0.001,
             "1fs": 1000000.0}
    for header, want in cases.items():
        p = tmp_path / f"{header}.vcd"
        p.write_text(f"$date today $end\n$timescale {header} $end\n"
                     "$scope module top $end\n")
        assert _vcd_ticks_per_ns(p) == pytest.approx(want), header

    # An unreadable or absent header is the IDENTITY, so a caller working on a
    # waveform already in nanoseconds keeps working rather than being scaled
    # by a guess.
    bare = tmp_path / "bare.vcd"
    bare.write_text("$date today $end\n")
    assert _vcd_ticks_per_ns(bare) == 1.0
    assert _vcd_ticks_per_ns(tmp_path / "missing.vcd") == 1.0


# ------------- list_suspect_blocks and read_block must agree about what exists


def test_list_suspect_blocks_shows_the_slice_read_block_resolves_against(tmp_path):
    """They read DIFFERENT STATE, and the error message pointed at the empty one.

    `list_suspect_blocks` read `trace_report`, which only `_refresh_trace`
    writes -- and that runs only after an ACCEPTED simulation. `focus` builds
    `blocks_by_id`, and `read_block`/`replace_block` resolve against
    `blocks_by_id`. MEASURED live: an agent focused a requirement, replaced a
    block, was told the batch had removed every driver, called
    `list_suspect_blocks()` to find its way back, and got an empty list because
    no commit had ever been accepted.
    """
    from eda_agent.explain import RequirementView

    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", text="t",
                                               ports=["b"])}
    assert s.trace_report is None          # nothing has been simulated
    s.focus("REQ-B")
    out = s.list_suspect_blocks()
    ids = {r["id"] for r in out["suspect_blocks"]}
    assert ids, "focus built a slice and the listing must show it"
    # The very ids read_block resolves.
    for bid in ids:
        assert not s.read_block(bid).startswith("ERROR")
    assert out["focused"] == "REQ-B"


def test_an_empty_slice_says_why_instead_of_returning_a_bare_list(tmp_path):
    """`[]` reads as "this design has no blocks", which is never the fact."""
    s = _session(tmp_path)
    s.blocks_by_id = None
    out = s.list_suspect_blocks()
    assert out["suspect_blocks"] == []
    assert "focus(req_uid)" in out["note"]


def test_an_unknown_block_id_names_the_ids_that_do_exist(tmp_path):
    """The old message said "Use list_suspect_blocks() first" -- pointing at the
    one tool guaranteed to be empty at that moment."""
    s = _session(tmp_path)
    err = s.stage_replace("NOPE", "assign b = 1'b0;")["error_msg"]
    assert "blk_assign" in err and "blk_always" in err
    s.blocks_by_id = None
    err2 = s.stage_replace("NOPE", "assign b = 1'b0;")["error_msg"]
    assert "focus(req_uid)" in err2


def test_the_staleness_note_appears_only_when_the_slice_really_is_stale(tmp_path):
    """`focus` slices the STAGED buffer, so asserting "built from the last
    accepted RTL" for every slice was false the moment `focus` existed."""
    from eda_agent.explain import RequirementView

    s = _session(tmp_path)
    s.requirements = {"REQ-B": RequirementView(req_uid="REQ-B", text="t",
                                               ports=["b"])}
    s.stage_replace("blk_always", B_ALWAYS.replace("c <= a", "c <= ~a"))
    # Slice built from a trace report: stale relative to the staged edit.
    s.slice_from_staged = False
    assert "predate them" in s.list_suspect_blocks()["note"]
    # Rebuilt by focus from the staged buffer: not stale, so no note.
    s.focus("REQ-B")
    assert "note" not in s.list_suspect_blocks()


def test_replacing_a_block_is_not_removing_its_drivers(tmp_path):
    """THE GUARD HAD A FALSE POSITIVE ON EVERY replace_block.

    It classified by literal presence -- `b.code in text` meant driven,
    `b.code not in text` meant lost -- and a replacement necessarily removes
    the block's ORIGINAL text, so the block's writes landed in `lost` while
    nothing put the replacement into `driven`.

    MEASURED twice on live runs against the i2c FSM block: adding a
    one-character comment is reported as "scl_oen, sda_chk, sda_oen, state are
    still read but the batch removed their LAST driver". In the first session
    that false positive REJECTED the only commit the agent landed; in the third
    it cost four rounds and went away only because `focus` happened to rebuild
    the block table from the staged buffer.
    """
    rtl = ("module m(input clk, input a, output reg c, output reg d);\n"
           "wire w;\n"
           "assign w = a;\n"
           "\n"
           "always @(posedge clk) begin\n"
           "  c <= w;\n"
           "  d <= ~w;\n"
           "end\n"
           "\n"
           "endmodule\n")
    from eda_agent.trace_slicer import RtlBlock
    path = tmp_path / "rtl.sv"
    path.write_text(rtl)
    body = "always @(posedge clk) begin\n  c <= w;\n  d <= ~w;\nend"

    def _s():
        s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                         last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
        s.blocks_by_id = {
            "blk_assign": RtlBlock(id="blk_assign", kind="assign", start_line=3,
                                   end_line=3, clocking="", code="assign w = a;",
                                   writes=("w",), reads=("a",)),
            "blk_always": RtlBlock(id="blk_always", kind="always", start_line=5,
                                   end_line=8, clocking="posedge clk", code=body,
                                   writes=("c", "d"), reads=("w",)),
        }
        return s

    # A replacement that still drives both c and d is CLEAN.
    s = _s()
    s.stage_replace("blk_always", body.replace("c <= w;", "c <= w;  // touched"))
    assert s.undriven_signals(s.staged()) == []
    assert s.would_commit_be_rejected(s.staged()) == ""

    # Removing the block that drives `w`, still read, is CAUGHT.
    s2 = _s()
    s2.stage_remove("blk_assign")
    assert "w" in s2.undriven_signals(s2.staged())


def test_the_driver_guard_does_not_depend_on_which_requirement_is_focused(tmp_path):
    """It read `blocks_by_id`, so the SAME buffer could be judged differently
    depending on which requirement was in view. Parsing the text settles it."""
    rtl = ("module m(input clk, input a, output reg c);\n"
           "wire w;\n"
           "assign w = a;\n"
           "\n"
           "always @(posedge clk) begin\n"
           "  c <= w;\n"
           "end\n"
           "\n"
           "endmodule\n")
    from eda_agent.trace_slicer import RtlBlock
    path = tmp_path / "rtl.sv"
    path.write_text(rtl)
    s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                     last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
    s.blocks_by_id = {"blk_assign": RtlBlock(
        id="blk_assign", kind="assign", start_line=3, end_line=3, clocking="",
        code="assign w = a;", writes=("w",), reads=("a",))}
    s.stage_remove("blk_assign")
    caught = s.undriven_signals(s.staged())
    assert "w" in caught
    # An empty slice must not silence it: the buffer is the same buffer.
    s.blocks_by_id = {}
    assert s.undriven_signals(s.staged()) == caught


def test_the_splice_preserves_the_anchors_boundary_whitespace(tmp_path):
    """A block's `code` can SWALLOW the newline that ended it, and welding the
    replacement's last token to the next one is silent until Verilator.

    MEASURED on the i2c FSM block: the anchor ends "    end\\nend\\n", the text
    right after it is "endmodule\\n", and the agent's replacement ends "end"
    with no trailing newline -- the natural way to write a block. The splice
    produced "endendmodule", one identifier where two keywords belonged, and
    the error came back "syntax error, unexpected end of file" 145 lines from
    the edit. Every replacement of that block in the fourth live run failed
    this way: correct Verilog in, broken buffer out.
    """
    from eda_agent.trace_slicer import RtlBlock

    rtl = ("module m(input clk, input a, output reg c);\n"
           "always @(posedge clk) begin\n"
           "  c <= a;\n"
           "end\n"
           "endmodule\n")
    path = tmp_path / "rtl.sv"
    path.write_text(rtl)
    s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                     last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
    # The anchor CARRIES its trailing newline, as the real parser's does.
    anchor = "always @(posedge clk) begin\n  c <= a;\nend\n"
    assert anchor in rtl
    s.blocks_by_id = {"blk": RtlBlock(id="blk", kind="always", start_line=2,
                                      end_line=4, clocking="posedge clk",
                                      code=anchor, writes=("c",), reads=("a",))}
    # A replacement written WITHOUT a trailing newline.
    s.stage_replace("blk", "always @(posedge clk) begin\n  c <= ~a;\nend")
    staged = s.staged()
    assert "endendmodule" not in staged
    assert staged.endswith("end\nendmodule\n"), repr(staged[-24:])
    # And a replacement WITH one does not double it.
    s.discard_staged()
    s.stage_replace("blk", "always @(posedge clk) begin\n  c <= ~a;\nend\n")
    assert s.staged().endswith("end\nendmodule\n")
    assert "\n\n\nendmodule" not in s.staged()


def test_internals_report_the_waveforms_own_transition_times(tmp_path):
    """Deriving transitions from a sample grid was wrong twice over.

    IT LAGGED: values were read with `inclusive=False`, so a sample at t
    returned the value strictly BEFORE t and a change first appeared one sample
    later. MEASURED on the i2c design: `scl_oen` falls at 640ns and was reported
    at 650; `state` enters 1011 at 640 and was reported at 650. Every transition
    in every window was systematically one sample late -- exactly the error that
    makes a debugger invent a timing theory.

    AND IT WAS BLIND BETWEEN SAMPLES: a pulse shorter than the grid vanished.
    """
    import sys
    import types

    from eda_agent import explain as _ex
    from eda_agent.trace_slicer import RtlBlock

    # ticks are ps, the grid is every 10ns, and `s` pulses BETWEEN grid points.
    tv = {"s": [(0, "0"), (615000, "1"), (617000, "0")],
          "q": [(0, "0"), (640000, "1")]}
    # `q` is the root and reads `s`, so the walk reaches both.
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in tv else ""),
        "_vcd_tv": lambda vcd, full: tv[full],
        "_vcd_value_at": lambda series, t, inclusive=False: next(
            (v for tt, v in reversed(series)
             if (tt <= t if inclusive else tt < t)), None),
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$timescale 1ps $end\n")
    try:
        blocks = [RtlBlock(id="b", kind="always", start_line=1, end_line=2,
                           clocking="posedge clk", code="", writes=("q",),
                           reads=("s",))]
        got = _ex._block_internals(wave, blocks, [600, 610, 620, 630, 640, 650],
                                   roots=["q"])
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]

    rows = {r["signal"]: r for r in got["chain"]}
    # EXACT times, not the next grid point after them.
    assert [c["t"] for c in rows["q"]["changed"]] == [640]
    # And the sub-grid pulse survives, both edges of it.
    assert [c["t"] for c in rows["s"]["changed"]] == [615, 617]


def test_a_wide_vector_is_readable_as_well_as_exact(tmp_path):
    """`cnt` is 16 bits, and `0000000000000011` is hard to compare against the
    `clk_cnt=3` a requirement talks about. Narrow values stay as they are --
    `state` as `1011` is what a `case` arm is written against."""
    from eda_agent.explain import _readable
    assert _readable("0000000000000011") == "0000000000000011 (3)"
    assert _readable("1011") == "1011"
    assert _readable("0") == "0"
    assert _readable("xxxx") == "xxxx"
    assert _readable(None) is None


# ------------------------- the small repair, which had no tool


BIG = """\
module m(input clk, input a, input [1:0] sel, output reg c, output reg d);
always @(posedge clk) begin
  case (sel)
    2'd0: begin
      c <= 1'b1;
      d <= 1'b0;
    end
    2'd1: begin
      c <= 1'b1;
      d <= 1'b1;
    end
    default: begin
      c <= 1'b0;
      d <= 1'b0;
    end
  endcase
end
endmodule
"""


def _big_session(tmp_path):
    from eda_agent.trace_slicer import RtlBlock
    path = tmp_path / "rtl.sv"
    path.write_text(BIG)
    s = _EditSession(tb_path=None, rtl_path=str(path), output_dir=str(tmp_path),
                     last_mismatch_cnt=0, sim_reviewer=object(), max_trials=30)
    body = BIG[BIG.index("always"):BIG.index("endmodule")].rstrip("\n")
    s.blocks_by_id = {"blk": RtlBlock(id="blk", kind="always", start_line=2,
                                      end_line=17, clocking="posedge clk",
                                      code=body, writes=("c", "d"),
                                      reads=("sel",))}
    return s


def test_a_fragment_edit_changes_one_line_inside_a_large_block(tmp_path):
    """THE UNIT OF EDIT WAS THE BLOCK, and one block is two thirds of the design.

    Measured on both the i2c candidate and the golden design: fifteen blocks,
    and the bit-controller FSM is 4713 of 7285 characters (65%) and 7159 of
    10542 (68%). Every failing requirement's slice lands on it, so changing one
    state's `scl_oen` assignment meant retyping all 4713 characters and any slip
    anywhere in them broke the commit.
    """
    s = _big_session(tmp_path)
    whole = s.blocks_by_id["blk"].code
    res = s.stage_edit("    2'd1: begin\n      c <= 1'b1;",
                       "    2'd1: begin\n      c <= 1'b0;")
    assert res["is_action_executed"], res
    staged = s.staged()
    assert "2'd1: begin\n      c <= 1'b0;" in staged
    # The OTHER arms are untouched -- this is the property a whole-block
    # replacement cannot promise, because it retypes them all.
    assert "2'd0: begin\n      c <= 1'b1;" in staged
    assert staged.count("d <= 1'b0;") == BIG.count("d <= 1'b0;")
    assert len("    2'd1: begin\n      c <= 1'b1;") < len(whole) // 4


def test_an_ambiguous_fragment_is_refused_with_the_count(tmp_path):
    """`c <= 1'b1;` appears twice here and thirteen times in the real FSM."""
    s = _big_session(tmp_path)
    res = s.stage_edit("c <= 1'b1;", "c <= 1'b0;")
    assert not res["is_action_executed"]
    assert "appears 2 times" in res["error_msg"]
    assert "surrounding lines" in res["error_msg"]
    assert s.staged_rtl is None, "an ambiguous edit must stage NOTHING"


def test_a_fragment_that_is_not_there_is_refused(tmp_path):
    s = _big_session(tmp_path)
    res = s.stage_edit("c <= 1'bz;", "c <= 1'b0;")
    assert not res["is_action_executed"]
    assert "not in the buffer" in res["error_msg"]
    assert s.staged_rtl is None


def test_an_empty_fragment_is_refused(tmp_path):
    res = _big_session(tmp_path).stage_edit("", "anything")
    assert not res["is_action_executed"]
    assert "empty" in res["error_msg"]


def test_a_fragment_edit_moves_the_enclosing_blocks_staged_text(tmp_path):
    """Otherwise the next `replace_block` on that block anchors on bytes the
    buffer no longer holds, and is refused for an edit the agent itself made."""
    s = _big_session(tmp_path)
    s.stage_edit("    2'd1: begin\n      c <= 1'b1;",
                 "    2'd1: begin\n      c <= 1'b0;")
    assert "c <= 1'b0;" in s.staged_text["blk"]
    # And a whole-block replace still resolves afterwards.
    res = s.stage_replace("blk", s.staged_text["blk"].replace("d <= 1'b1;",
                                                              "d <= 1'b0;"))
    assert res["is_action_executed"], res


def test_a_fragment_edit_is_free_and_spends_no_trial(tmp_path):
    s = _big_session(tmp_path)
    s.stage_edit("      d <= 1'b1;", "      d <= 1'b0;")
    assert s.action_calls == 0
    assert s.check_calls == 0


def test_internals_name_the_block_that_drives_each_signal(tmp_path):
    """`suspect_blocks` was a list of bare ids and `block_internals` a list of
    signals, side by side and UNJOINED -- the agent had to call `focus`
    separately to learn that A4 is what writes `state`.

    And a signal the design does not drive at all sat in the same list as the
    ones it does. That distinction is the first thing a debugger needs: it
    separates what the design DID from what was done TO it.
    """
    import sys
    import types

    from eda_agent import explain as _ex
    from eda_agent.trace_slicer import RtlBlock

    tv = {"state": [(0, "00"), (610000, "01")],   # driven by the block
          "cmd": [(0, "0000"), (620000, "0001")],  # moved, driven by nothing
          "K": [(0, "1010")]}                      # held, driven by nothing
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in tv else ""),
        "_vcd_tv": lambda vcd, full: tv[full],
        "_vcd_value_at": lambda series, t, inclusive=False: next(
            (v for tt, v in reversed(series)
             if (tt <= t if inclusive else tt < t)), None),
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$timescale 1ps $end\n")
    try:
        blocks = [RtlBlock(id="A4", kind="always", start_line=1, end_line=2,
                           clocking="posedge clk", code="", writes=("state",),
                           reads=("cmd", "K"))]
        got = _ex._block_internals(wave, blocks, [600, 610, 620, 630],
                                   roots=["state"])
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]

    rows = {r["signal"]: r for r in got["chain"]}
    # The walk STARTS at the failing signal and reaches its inputs at depth 1,
    # each saying what it feeds -- that is the chain, not a bag.
    assert rows["state"]["driven_by"] == "A4" and rows["state"]["depth"] == 0
    assert "feeds" not in rows["state"], "the root is not fed by anything shown"
    assert rows["cmd"]["depth"] == 1 and rows["cmd"]["feeds"] == "state"
    # Moved with no driver: the stimulus did it, and it says so.
    assert rows["cmd"]["driven_by"] is None
    assert "input" in rows["cmd"]["note"]
    # Held with no driver could be a localparam OR an unmoved input, and the
    # block table cannot tell them apart -- so it must not claim either.
    k = got["__held_constant__"]["K"]
    assert k["driven_by"] is None
    assert "constant, or an input" in k["note"]
    assert "input, not the design" not in k["note"]


def test_the_chain_is_rooted_at_the_outputs_not_at_the_stimulus(tmp_path):
    """A requirement reads its ACTIVATION's inputs too, and rooting the walk at
    those would trace backwards from the stimulus -- which explains nothing
    about the design. The roots are the outputs the check convicted it on."""
    import sys
    import types

    from eda_agent import explain as _ex
    from eda_agent.trace_slicer import RtlBlock

    tv = {"out": [(0, "0"), (620000, "1")],
          "mid": [(0, "0"), (610000, "1")],
          "stim": [(0, "0"), (605000, "1")]}
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in tv else ""),
        "_vcd_tv": lambda vcd, full: tv[full],
        "_vcd_value_at": lambda series, t, inclusive=False: next(
            (v for tt, v in reversed(series)
             if (tt <= t if inclusive else tt < t)), None),
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$timescale 1ps $end\n")
    try:
        blocks = [
            RtlBlock(id="A", kind="always", start_line=1, end_line=2,
                     clocking="posedge clk", code="", writes=("out",),
                     reads=("mid",)),
            RtlBlock(id="B", kind="assign", start_line=3, end_line=3,
                     clocking="", code="", writes=("mid",), reads=("stim",)),
        ]
        got = _ex._block_internals(wave, blocks, [600, 610, 620, 630],
                                   roots=["out"])
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]

    chain = got["chain"]
    assert [(r["depth"], r["signal"]) for r in chain] == [
        (0, "out"), (1, "mid"), (2, "stim")], chain
    # Each step says what it feeds, so the chain reads as one explanation.
    assert chain[1]["feeds"] == "out" and chain[2]["feeds"] == "mid"
    assert chain[0]["driven_by"] == "A" and chain[1]["driven_by"] == "B"
    # The one nothing drives is named as the stimulus's doing.
    assert chain[2]["driven_by"] is None and "input" in chain[2]["note"]


def test_the_clock_is_not_part_of_any_explanation(tmp_path):
    """Every sequential block reads it, so it enters at depth 1 of every walk
    and brings one transition per edge -- 28 in a 140ns window on the real
    design, which is the noise that buries the signals that matter."""
    from eda_agent.explain import _clocks_and_resets
    contract = {"io": [{"name": "clk"}, {"name": "nReset"}, {"name": "rst"},
                       {"name": "scl_oen"}, {"name": "cmd"}]}
    assert _clocks_and_resets(contract) == {"clk", "nReset", "rst"}


def test_explain_on_an_uncovered_requirement_answers_a_different_question(tmp_path):
    """AN ABSTENTION HAS NO WINDOW, and `explain` was inventing one.

    With no `edge` it fell back to `max(0, edge - span_pad)` -> 0 and reported a
    span from edge 0 to edge 0 under a note reading "the interval this
    requirement governs" -- false for a check that never fired. Twenty of run
    5's 27 uncovered requirements have no edge at all.

    Here every port the activation waits on is an INPUT, so the design is not
    implicated and add_stimulus IS the route.
    """
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "rst", "direction": "input"},
                         {"name": "ena", "direction": "input"},
                         {"name": "b", "direction": "output"}]}
    s.requirements = {"REQ-B": RequirementView(
        req_uid="REQ-B", text="on reset the outputs release",
        activation={"text": "while in reset", "inputs": {"rst": 1, "ena": 1},
                    "until": [{"rst": 0}]},
        ports=["b"], source="")}
    s.req_results = {"REQ-B": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {"rst": 0, "ena": 1}, "dut": {"b": 0}},
        {"edge": 1, "t": 20, "inputs": {"rst": 0, "ena": 1}, "dut": {"b": 1}}]})}
    out = s.explain("REQ-B")

    assert out["verdict"] is None
    # NO fabricated span, and none of the failure-shaped fields.
    assert "span" not in out and "boundary_ports" not in out
    u = out["uncovered"]
    assert u["values_the_trace_carried"]["rst"] == [0]
    assert u["never_reached"] == {"rst": 1}
    assert u["discharged_by"] == "add_stimulus"
    assert "rst=1" in u["what_to_ask_for"]
    assert "add_stimulus" in u["what_to_ask_for"]


def test_an_uncovered_requirement_gated_on_an_output_is_a_DESIGN_accusation(tmp_path):
    """AN EDIT CAN DISCHARGE AN UNCOVERED CHECK when its trigger is an output.

    This function used to say, flatly, "no edit to the design can discharge an
    uncovered requirement". That is false whenever the activation waits on an
    OUTPUT: if the check opens on `cmd_ack` changing and the design never
    changes `cmd_ack`, the check is silent BECAUSE THE DESIGN IS BROKEN. No
    stimulus can move an output, so routing that to add_stimulus files a design
    bug as an evidence gap -- the #98 failure mode, which plan §6.4 already
    names one layer up ("dropping those would have locked the bug in").

    MEASURED on run 8's baseline: EIGHT of 25 uncovered requirements condition
    on an output. They were invisible because the old code read
    `activation.inputs` and the output triggers live in `opens_on`.
    """
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "ena", "direction": "input"},
                         {"name": "cmd_ack", "direction": "output"}]}
    s.requirements = {"REQ-C": RequirementView(
        req_uid="REQ-C", text="each command is acknowledged once",
        activation={"text": "the FSM advances a phase", "inputs": {"ena": 1},
                    "opens_on": [{"cmd_ack": "change"}]},
        ports=["cmd_ack"], source="")}
    s.req_results = {"REQ-C": (_Uncovered(rows=[]), {"edges": [
        # ena is driven, so the STIMULUS did its job. cmd_ack never moves.
        {"edge": 0, "t": 10, "inputs": {"ena": 1}, "dut": {"cmd_ack": 0}},
        {"edge": 1, "t": 20, "inputs": {"ena": 1}, "dut": {"cmd_ack": 0}}]})}
    u = s.explain("REQ-C")["uncovered"]

    assert u["never_reached"] == {"cmd_ack": "change"}
    assert u["discharged_by"] == "EDIT", "an output trigger accuses the DESIGN"
    said = u["what_to_ask_for"]
    assert "OUTPUT" in said and "cmd_ack never changed" in said
    assert "add_stimulus cannot help" in said
    # And the requirement summary must SHOW the output trigger, or the agent
    # cannot see why the routing went that way.
    assert s.requirements["REQ-C"].brief()["activation_opens_on"] == [
        {"cmd_ack": "change"}]


def test_values_that_appear_but_never_together_are_a_stimulus_gap(tmp_path):
    """THE CONJUNCTION IS THE QUESTION, not the ports one at a time.

    `inputs` has to hold AT ONE EDGE. Checking each port separately says
    "cmd=4 appears, ena=1 appears" about a trace where they never once held
    together -- which is exactly the scenario add_stimulus exists to request,
    reported as if nothing were missing. On run 8's baseline this distinction
    moves requirements out of "unclear" and into an actionable route.
    """
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "cmd", "direction": "input"},
                         {"name": "ena", "direction": "input"}]}
    s.requirements = {"REQ-B": RequirementView(
        req_uid="REQ-B", text="t",
        activation={"text": "cmd=4 while enabled", "inputs": {"cmd": 4, "ena": 1}},
        ports=["b"], source="")}
    s.req_results = {"REQ-B": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {"cmd": 4, "ena": 0}, "dut": {}},
        {"edge": 1, "t": 20, "inputs": {"cmd": 0, "ena": 1}, "dut": {}}]})}
    u = s.explain("REQ-B")["uncovered"]
    assert u["discharged_by"] == "add_stimulus"
    assert "TOGETHER at one edge" in u["what_to_ask_for"]
    assert "never all at the same edge" in u["what_to_ask_for"]
    # Neither value is individually absent, so nothing may be reported as unseen.
    assert "never_reached" not in u


def test_a_rise_trigger_is_a_transition_not_a_value(tmp_path):
    """`rise`/`fall`/`change` are the normalizer's edge vocabulary
    (`normalize._EDGE_WORDS`), used by 29 of the 90 requirements' opens_on
    clauses. Asking "is 'rise' among the values the trace carried" is always
    no, which made every edge-triggered activation look permanently dead and
    would have reported a working design as broken.

    `temporal.edges` is the evaluator THE ORACLES THEMSELVES run, so using it
    here is what stops this function disagreeing with the verdict it explains.
    """
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "scl_oen", "direction": "output"}]}
    view = RequirementView(
        req_uid="REQ-D", text="t",
        activation={"text": "SCL is released", "opens_on": [{"scl_oen": "rise"}]},
        ports=["scl_oen"], source="")
    s.requirements = {"REQ-D": view}

    # scl_oen DOES rise -- so the window can open and the design is not accused.
    s.req_results = {"REQ-D": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {}, "dut": {"scl_oen": 0}},
        {"edge": 1, "t": 20, "inputs": {}, "dut": {"scl_oen": 1}}]})}
    assert s.explain("REQ-D")["uncovered"]["discharged_by"].startswith("unclear")

    # It never rises -- now it IS the design, and only an edit can move it.
    s.req_results = {"REQ-D": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {}, "dut": {"scl_oen": 0}},
        {"edge": 1, "t": 20, "inputs": {}, "dut": {"scl_oen": 0}}]})}
    assert s.explain("REQ-D")["uncovered"]["discharged_by"] == "EDIT"


def test_a_clause_is_a_conjunction_and_the_list_is_the_disjunction(tmp_path):
    """`opens_on [{"scl_i": "fall", "scl_oen": 1}]` means SCL fell WHILE
    scl_oen was 1 -- one clause, both conditions, at the same edge. Returning
    "satisfied" because either held somewhere makes a dead window look alive.
    Across clauses it is any-of: one live clause opens the window."""
    s = _session(tmp_path)
    s.contract = {"io": [{"name": "scl_i", "direction": "input"},
                         {"name": "scl_oen", "direction": "output"}]}
    s.requirements = {"REQ-E": RequirementView(
        req_uid="REQ-E", text="t",
        activation={"text": "SCL falls while released",
                    "opens_on": [{"scl_i": "fall", "scl_oen": 1}]},
        ports=["scl_i"], source="")}
    # scl_i falls at edge 1, but scl_oen is 0 there and 1 only at edge 2.
    # Never both at once -> the clause never holds.
    s.req_results = {"REQ-E": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {"scl_i": 1}, "dut": {"scl_oen": 0}},
        {"edge": 1, "t": 20, "inputs": {"scl_i": 0}, "dut": {"scl_oen": 0}},
        {"edge": 2, "t": 30, "inputs": {"scl_i": 0}, "dut": {"scl_oen": 1}}]})}
    assert s.explain("REQ-E")["uncovered"]["discharged_by"] != "unclear -- read activation_text"

    # Move the fall to where scl_oen is high: the clause holds, window opens.
    s.req_results = {"REQ-E": (_Uncovered(rows=[]), {"edges": [
        {"edge": 0, "t": 10, "inputs": {"scl_i": 1}, "dut": {"scl_oen": 1}},
        {"edge": 1, "t": 20, "inputs": {"scl_i": 0}, "dut": {"scl_oen": 1}}]})}
    assert s.explain("REQ-E")["uncovered"]["discharged_by"].startswith("unclear")


def test_two_assigns_to_one_wire_are_caught_though_verilator_is_silent(tmp_path):
    """THE GUARD SEES PORTS AND GOES BLIND INSIDE THE MODULE.

    Verilator's MULTIDRIVEN -- all `multidriven_signals` is a regex over --
    fires for two combinational drivers on an OUTPUT PORT and for procedural
    drivers with DIFFERENT CLOCKING. Measured on 5.038 under `check_syntax`'s
    exact flags, it is SILENT (exit 0, no warning) for two `assign`s to an
    internal wire, and for two same-clock always blocks. That is where the
    editor works.

    It latched, too. Three live editor sessions committed an i2c design with
    `assign scl_sync` twice -- `wire scl_sync`, internal, and the candidate they
    started from has one driver. In the sixth run the two came to DISAGREE
    (`scl_oen & ~sSCL & dSCL` against `cSCL[1] & ~scl_i & scl_oen`), which
    resolves to X, and `scl_sync` feeds the clock divider's reload condition.
    The agent had spent two rounds refining the two copies separately, taking
    them for one expression, because no tool it could call would say otherwise.
    """
    src = ("module m(input a, input b, output c);\n"
           "  wire w;\n"
           "  assign w = a;\n"
           "  assign w = b;\n"
           "  assign c = w;\n"
           "endmodule\n")
    assert overdriven_signals(src) == {"w"}
    # Verilator, on that same text, says nothing -- the reason this exists.
    path = tmp_path / "m.sv"
    path.write_text(src)
    from eda_agent.sim_reviewer import multidriven_signals
    assert multidriven_signals(str(path)) == set()

    # One block writing a signal in two branches has ONE driver, not two.
    ok = ("module m(input a, input clk, output reg c);\n"
          "  always @(posedge clk) begin\n"
          "    if (a) c <= 1'b1; else c <= 1'b0;\n"
          "  end\n"
          "endmodule\n")
    assert overdriven_signals(ok) == set()


def test_a_batch_that_duplicates_a_driver_is_refused_at_commit(tmp_path):
    """And the refusal names the signal, so the fix is one search away."""
    s = _session(tmp_path, LINTABLE)
    s.stage_add("endmodule", "assign w = ~a;")
    verdict = s.would_commit_be_rejected(s.staged())
    assert "w" in verdict and "MORE THAN ONE driver" in verdict


def test_a_preexisting_duplicate_does_not_block_every_commit(tmp_path):
    """The ChipVerilog candidate these sessions start from ALREADY ships
    `scl_sync` with two drivers. An absolute check would refuse every commit for
    a defect the agent did not cause -- so the REJECTION is what the batch
    introduced, while the pre-existing one is still surfaced as its own
    sentence, because a wire resolving to X poisons everything reading it."""
    s = _session(tmp_path, LINTABLE.replace(
        "assign b = w;", "assign w = ~a;\nassign b = w;"))
    assert s.would_commit_be_rejected(s.staged()) == ""   # not this batch's doing
    warned = " ".join(s.driver_warnings())
    assert "w" in warned and "ALREADY" in warned          # but not silent either


def test_an_edit_anchor_may_differ_from_the_buffer_in_whitespace(tmp_path):
    """WHITESPACE IS NOT THE AGENT'S TO GUESS.

    `read_block` renders line-number prefixes, so no tool returns a verbatim
    substring: the agent retypes the indentation and must be right to the
    character. In the seventh live run its anchor was one space wider than the
    file (25 against 24), was refused, and it then degraded to `state <= ...`,
    `state\\t<= ...`, `state<=` -- none of which could match `state   <= `.
    That cost eleven of forty-five rounds and the run's outcome; the sixth run,
    same model and same tool, transcribed it correctly and made seven edits
    with no errors.

    A token-sequence match is not the ambiguity pin 7 guards against: a
    destroyed anchor still matches nothing, and a repeated one is still refused.
    """
    s = _session(tmp_path)
    b = max(parse_rtl_blocks(s.read_rtl()), key=lambda x: len(x.code))
    sloppy = "\n".join("  " + ln.strip() for ln in b.code.strip().splitlines())
    assert sloppy not in s.read_rtl(), "fixture must actually differ in whitespace"
    out = s.stage_edit(sloppy, "// gone")
    assert out["is_action_executed"] is True
    assert "matched_on" in out
    assert "// gone" in s.staged()


def test_whitespace_tolerance_does_not_weaken_the_two_refusals(tmp_path):
    """Pin 7 still holds: absent tokens are refused, and so is a repeat."""
    s = _session(tmp_path)
    out = s.stage_edit("no_such_identifier_anywhere <= 1;", "x")
    assert out["is_action_executed"] is False
    # The message must not send the agent back to fix indentation it already
    # got right -- that is the loop run 7 spent eleven rounds in.
    assert "whitespace was already ignored" in out["error_msg"].lower()

    (tmp_path / "b").mkdir()
    s2 = _session(tmp_path / "b")
    s2.write_rtl(s2.read_rtl().replace(
        "endmodule", "wire d1, d2;\nassign d1 = 1'b0;\nassign d2 = 1'b0;\nendmodule", 1))
    s2.staged_rtl = None
    out2 = s2.stage_edit("1'b0;", "1'b1;")
    assert out2["is_action_executed"] is False    # two matches: still refused
    assert "ambiguous" in out2["error_msg"]
    out3 = s2.stage_edit("assign  d1  =  1'b0;", "assign d1 = 1'b1;")
    assert out3["is_action_executed"] is True     # unique under normalization


class _ReqStub:
    """An OracleResult with only the field the ratchet reads."""

    def __init__(self, ok):
        self.ok = ok


def _split(session):
    return session._req_split()


def test_a_silenced_requirement_is_not_progress(tmp_path):
    """FAILING -> UNCOVERED IS EVIDENCE LOST, NOT A REQUIREMENT MET.

    A requirement has three states, so "fewer failing" is satisfied just as well
    by FAILING -> PASSING as by FAILING -> UNCOVERED. The second means the check
    stopped firing: the design did not improve, the evidence went away. Defect
    #93, and it is not hypothetical -- MEASURED on run 8 round 21, where
    `dout <= sSDA` -> `dout <= dSDA` moved the frozen 90 from 19 failing / 25
    uncovered / 46 passing to 18/26/46. Failing fell by one and PASSING DID NOT
    MOVE: REQ-0009 went dark. A failing-count ratchet would have latched it.

    PASSING is immune by construction -- silencing leaves it flat.
    """
    s = _session(tmp_path)
    before = {"REQ-A": (_ReqStub(True), {}), "REQ-B": (_ReqStub(False), {})}
    after_silenced = {"REQ-A": (_ReqStub(True), {}), "REQ-B": (_ReqStub(None), {})}
    after_repaired = {"REQ-A": (_ReqStub(True), {}), "REQ-B": (_ReqStub(True), {})}

    s.req_results = before
    ok0, bad0, dark0 = _split(s)
    assert (len(ok0), len(bad0), len(dark0)) == (1, 1, 0)

    # Silencing: failing falls 1 -> 0, and passing does NOT rise.
    s.req_results = after_silenced
    ok1, bad1, dark1 = _split(s)
    assert len(bad1) < len(bad0), "a failing-count ratchet would call this progress"
    assert len(ok1) == len(ok0), "but passing is flat, so it must not latch"

    # A real repair moves passing.
    s.req_results = after_repaired
    ok2, _b2, _d2 = _split(s)
    assert len(ok2) > len(ok0)


def test_no_requirement_data_is_not_the_same_as_nothing_passing(tmp_path):
    """`_req_split` returns None, not three empty sets.

    A backend that publishes no requirements would otherwise look like total
    failure -- passing 0, never rising -- and every commit would be refused for
    a reason that is about the harness, not the design. None routes to the
    testpoint ratchet every non-specflow caller has always used.
    """
    s = _session(tmp_path)
    s.req_results = {}
    assert s._req_split() is None
    s.req_results = {"REQ-A": (_ReqStub(None), {})}
    assert s._req_split() == (set(), set(), {"REQ-A"})


def test_a_failed_build_cannot_latch_by_leaving_no_verdicts(tmp_path):
    """If the suite fails to build, every requirement abstains -- so passing
    goes to zero and the commit cannot latch. Under the old testpoint ratchet
    an empty results dict reads as ZERO failing testpoints, which beats any
    positive previous count and would have latched RTL that does not build."""
    s = _session(tmp_path)
    s.req_results = {"REQ-A": (_ReqStub(True), {}), "REQ-B": (_ReqStub(True), {})}
    ok0, _, _ = _split(s)
    s.req_results = {"REQ-A": (_ReqStub(None), {}), "REQ-B": (_ReqStub(None), {})}
    ok1, bad1, _ = _split(s)
    assert len(bad1) == 0, "a build failure produces no FAILING testpoints"
    assert len(ok1) < len(ok0), "but passing collapses, so it cannot latch"


def test_reverting_is_a_policy_not_a_law(tmp_path):
    """A GREEDY FILTER IS EXACTLY A HILL-CLIMBER.

    A repair needing several parts to land together has to pass through a worse
    state to reach the better one. Reverting every step of it makes that repair
    unreachable however many trials remain, so `rollback_on_regression=False`
    has to let a non-improving commit STAND as the working baseline -- otherwise
    the flag exists and does nothing on the path that matters.
    """
    s = _session(tmp_path)
    assert s.rollback_on_regression is True, "greedy stays the default"
    s.rollback_on_regression = False
    assert s.rollback_on_regression is False


def test_best_is_ranked_on_the_same_quantity_the_commit_is_judged_on(tmp_path):
    """`note_best` keyed on failing TESTPOINTS while `commit` judges PASSING
    REQUIREMENTS, and with the guard off those two disagree exactly where it
    matters: `restore_best` is what makes wandering safe, so a best chosen by a
    different measure hands back a design the loop had already improved on.

    Run 8 round 21 ranks the same pair oppositely -- testpoints 104 -> 106
    (worse) against failing requirements 19 -> 18 (better, by silencing).
    """
    s = _session(tmp_path)
    # Passing rises while the testpoint count also rises: the old key would
    # refuse to record this, the new one must take it.
    assert s.note_best(104, "rtl-A", passing=46) is True
    assert s.best_passing == 46 and s.best_rtl == "rtl-A"
    assert s.note_best(106, "rtl-B", passing=48) is True, (
        "more passing IS better, whatever the testpoint count did")
    assert s.best_rtl == "rtl-B"
    # Fewer passing never wins, however good the testpoint count looks.
    assert s.note_best(1, "rtl-C", passing=47) is False
    assert s.best_rtl == "rtl-B"
    # Ties do not overwrite.
    assert s.note_best(0, "rtl-D", passing=48) is False
    assert s.best_rtl == "rtl-B"


def test_without_requirements_best_still_ranks_on_the_testpoint_count(tmp_path):
    """The fallback every non-specflow caller has always used."""
    s = _session(tmp_path)
    assert s.note_best(50, "rtl-A") is True
    assert s.note_best(40, "rtl-B") is True
    assert s.note_best(60, "rtl-C") is False
    assert s.best_rtl == "rtl-B" and s.best_mismatch_cnt == 40


def test_add_stimulus_gates_on_the_set_the_agent_is_shown(tmp_path):
    """`gate.evaluate` RETURNS ON ITS FIRST MATCHING BRANCH:

        if failing:
            return GateVerdict("REPAIR_RTL", failing=failing, ...)

    with `not_exercised` left at its default. A debug session has failing
    testpoints by definition, so that branch always wins and the set derived
    from it is always empty -- meaning `add_stimulus` refused EVERY request for
    the whole of any session it could have been useful in. It could only have
    worked once nothing failed, when there is nothing to stage.

    MEASURED on run 8, the first run whose agent ever reached the tool: four
    calls, four refusals, on uids `list_failing_requirements` had listed as
    UNCOVERED in the same session.
    """
    from specflow.gate import evaluate

    class _R:
        def __init__(self, status):
            self.status = status

    class _Rep:
        undisposed = ()

    v = evaluate(results={"TP-1": _R("FAIL"), "TP-2": _R("NOT_EXERCISED")},
                 report=_Rep(), build_ok=True)
    assert v.outcome == "REPAIR_RTL"
    assert v.not_exercised == (), (
        "this is the upstream behaviour the reviewer must not depend on: a "
        "genuinely unexercised testpoint is invisible whenever anything fails")


def test_the_manifest_fallback_survives_testpoints_listed_as_strings(tmp_path):
    """`_uncovered_requirements` did `entry.get(...)` over
    `manifest["testpoints"]`, which this suite writes as bare uid STRINGS. That
    raises AttributeError -- out of `review()`, out of `commit()` -- so on this
    shape the fallback was not merely useless but fatal."""
    import json as _json

    from eda_agent.specflow_node import _uncovered_requirements

    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "manifest.json").write_text(_json.dumps(
        {"testpoints": ["TP-0002", "TP-0003"], "modules": []}))
    assert _uncovered_requirements(["TP-0002"], suite) == set()


def test_find_signal_answers_what_read_block_cannot(tmp_path):
    """THERE WAS NO WAY TO ASK WHERE A SIGNAL COMES FROM.

    `read_block` takes a block ID and `list_suspect_blocks` shows whatever the
    last `focus` sliced, so an agent holding a signal NAME had only the id space
    to brute-force. MEASURED on run 8: seventeen consecutive rounds reading
    C1..C11 and A1..A3 one after another, plus five rounds calling
    `read_block("scl_sync")` and `read_block("assign scl_sync")` -- using the
    block reader as a search tool. Half a 45-round session, in a run whose round
    cap bound before its trial budget did.
    """
    s = _session(tmp_path)
    out = s.find_signal("b")
    assert out["signal"] == "b"
    assert out["driver_count"] == 1
    assert "assign b = a;" in out["driven_by"][0]["code"]
    assert out["driven_by"][0]["block_id"] == "blk_assign", (
        "when the block IS in the slice, name it so read_block can follow up")

    # A signal read but never driven is a module input or a lost driver, and
    # saying so is the whole point -- that is the silent-X case.
    assert s.find_signal("a")["driver_count"] == 0
    assert "nothing drives it" in s.find_signal("a")["note"]


def test_find_signal_is_not_narrowed_by_focus(tmp_path):
    """A signal's driver is frequently OUTSIDE the failing requirement's slice,
    which is exactly when the question is hard. It reads the STAGED BUFFER, so
    it sees pending edits and every block, not `blocks_by_id`."""
    s = _session(tmp_path)
    s.blocks_by_id = {}           # as if focus had narrowed to nothing
    out = s.find_signal("c")
    assert out["driver_count"] == 1, "still found, though no slice holds it"
    assert out["driven_by"][0]["block_id"] == "(not in the current slice)"

    # And a staged edit is visible before any commit.
    s.stage_edit("assign b = a;", "assign b = ~a;")
    assert "~a" in s.find_signal("b")["driven_by"][0]["code"]


def test_find_signal_names_a_duplicate_driver(tmp_path):
    """The internal-wire case Verilator will not warn about."""
    s = _session(tmp_path, LINTABLE)
    s.stage_add("endmodule", "assign w = ~a;")
    out = s.find_signal("w")
    assert out["driver_count"] == 2
    assert "2 DRIVERS" in out["note"] and "resolve to X" in out["note"]


def test_find_signal_on_an_unknown_name_lists_what_there_is(tmp_path):
    s = _session(tmp_path)
    out = s.find_signal("no_such_signal")
    assert out["driver_count"] == 0
    assert "nothing drives or reads" in out["note"]
    assert "'b'" in out["note"] and "'c'" in out["note"]


def test_restore_best_is_what_makes_keeping_regressions_safe(tmp_path):
    """WITHOUT THE RESTORE, `--keep-regressions` IS JUST A WAY TO END UP WORSE.

    The flag lets a non-improving commit stand so a multi-part repair can cross
    a valley; `restore_best` is the entire reason that is not a licence to
    finish below where you started. `RTLEditor.chat()` calls it before
    returning. The hand-rolled driver did not, while its help text and the
    agent's own prompt both promised "the session returns the BEST-scoring
    version it saw".

    MEASURED on run 9: the loop wandered to 16 passing / 70 uncovered, well
    below the 46 it began from, and with no restore that is what the run would
    have delivered.
    """
    s = _session(tmp_path)
    good = s.read_rtl()
    s.note_best(0, good, passing=46)

    # The loop wanders somewhere much worse and leaves it on disk.
    s.write_rtl(good.replace("assign b = a;", "assign b = 1'b0;"))
    assert s.read_rtl() != good
    s.note_best(0, s.read_rtl(), passing=16)          # never becomes best
    assert s.best_passing == 46

    assert s.restore_best() is True
    assert s.read_rtl() == good, "the session must end at its best point"
    assert s.restore_best() is False, "already there: nothing to do"


def test_add_stimulus_adds_ONE_testpoint_not_the_whole_stimulus_file(tmp_path):
    """`stimulus.json` and `testplan.json` are the FULL artifacts; a run may be
    built over a SUBSET of them. Re-rendering from the full set means adding one
    testpoint silently restores every testpoint the run excluded.

    MEASURED on run 10: three add_stimulus calls took the suite from 224
    testpoints to 334 -- the 331 in the stimulus file plus the 3 added. Its pass
    and coverage counts were therefore taken on a LARGER suite than its own
    baseline, than run 8, and than the golden reference, so no comparison across
    that boundary means anything. That invalidated a published comparison before
    it was caught.
    """
    import json as _json

    from eda_agent.specflow_node import SpecflowStimulusStager

    run = tmp_path / "run"
    (run / "specflow").mkdir(parents=True)
    suite = tmp_path / "suite"
    suite.mkdir()
    # The suite holds TWO testpoints; the artifacts on disk describe FIVE.
    (suite / "manifest.json").write_text(_json.dumps(
        {"testpoints": ["TP-0001", "TP-0002"], "modules": []}))
    full = [f"TP-{i:04d}" for i in range(1, 6)]
    (run / "specflow/testplan.json").write_text(_json.dumps(
        {"elements": [{"uid": u, "tp_uid": u, "covers": []} for u in full]}))
    (run / "specflow/stimulus.json").write_text(_json.dumps(
        {"testpoints": [{"tp_uid": u, "stimulus_steps": [{"drive": {"ena": 1}}]}
                        for u in full]}))
    (run / "specflow/requirements.json").write_text(_json.dumps(
        {"requirements": [{"uid": "REQ-0001", "text": "t"}]}))
    (run / "specflow/coverage_model.json").write_text(_json.dumps({"checks": []}))

    rendered = {}

    def _fake_render(**kw):
        rendered["n"] = len(kw["stimulus_by_tp"])
        rendered["uids"] = sorted(kw["stimulus_by_tp"])

    stager = SpecflowStimulusStager(
        run_dir=run, contract={"io": []}, bins=[], suite_dir=suite,
        model_port=object())
    stager.uncovered = {"REQ-0001"}
    stager._checks = []

    import eda_agent.specflow_node as sn
    import specflow.tb.render as render_mod
    import specflow.testcase_agent as tca
    orig_render, orig_stim = render_mod.render_suite, tca.stimulus_for_scenario
    render_mod.render_suite = _fake_render
    tca.stimulus_for_scenario = lambda **kw: [{"drive": {"ena": 1, "cmd": 4}}]
    try:
        out = stager.add_stimulus("REQ-0001", "drive a WRITE")
    finally:
        render_mod.render_suite, tca.stimulus_for_scenario = orig_render, orig_stim
    assert sn is not None

    assert "added" in out, out
    assert rendered["n"] == 3, (
        f"the suite had 2 testpoints and one was added, so the render must see "
        f"3 -- not {rendered['n']}, which would restore the excluded ones")
    assert rendered["uids"][:2] == ["TP-0001", "TP-0002"]


def test_normalization_accepts_the_shapes_that_lost_five_requirements():
    """PYDANTIC REJECTED THE WHOLE RECORD OVER ONE FIELD'S SHAPE.

    Five requirements -- REQ-0010, REQ-0017, REQ-0048, REQ-0078, REQ-0100 --
    reached the oracle author with NO activation and NO observation route,
    because the model returned `observed_via` or `observable` in a
    losslessly-equivalent but differently-shaped form and the stage recorded a
    Parse Error and moved on. A check was then written for each anyway.
    REQ-0010's is the naive "no output may change on any input edge", which went
    on to INVERT: it passes a design that deleted the input filter and convicts
    the golden one.
    """
    from specflow.normalize import NormalizedRequirement

    # REQ-0010 / REQ-0017: observed_via keyed BY PORT instead of a list.
    n = NormalizedRequirement.model_validate({
        "req_uid": "REQ-0010", "observable": ["busy"],
        "observed_via": {"busy": {"through_req": "REQ-0047", "when": "w",
                                  "shows": "holds: low; violated: high"}}})
    assert [r.port for r in n.observed_via] == ["busy"]
    assert n.observed_via[0].through_req == "REQ-0047"

    # REQ-0078 / REQ-0100: a single route returned unwrapped.
    n = NormalizedRequirement.model_validate({
        "req_uid": "REQ-0078", "observable": ["cmd_ack"],
        "observed_via": {"port": "cmd_ack", "through_req": "",
                         "shows": "holds: pulses; violated: silent"}})
    assert [r.port for r in n.observed_via] == ["cmd_ack"]

    # REQ-0048: `observable` given as route objects rather than port names.
    n = NormalizedRequirement.model_validate({
        "req_uid": "REQ-0048",
        "observable": [{"port": "busy", "through_req": "REQ-0049"}]})
    assert n.observable == ["busy"]


def test_an_activation_can_state_a_repetition_the_spec_gives():
    """THE FILTER REQUIREMENT NEEDED A COUNT AND NO FIELD COULD CARRY ONE.

    REQ-0046 is "majority voting over the THREE-SAMPLE histories ... so that
    short glitches are suppressed", and its `observed_via` correctly prescribed
    comparing a pulse on fewer than 2 of 3 samples against one on at least 2.
    `inputs`, `opens_on` and `until` are all per-row predicates and `until`
    documents "A CONDITION, NEVER A COUNT", so the activation came back
    `opens_on: [{scl_i: change}]` -- any edge -- and the authored check
    faithfully implemented that, convicting every design including golden.

    The ban is right about PACING and wrong about an arity the requirement
    states. `temporal.pulse(width=)` already evaluates run lengths, so the
    capability existed where the oracle RUNS and not where it is SPECIFIED.
    """
    from specflow.normalize import Activation, Sustain

    a = Activation(
        text="a short glitch on sda_i during normal operation",
        inputs={"nReset": 1, "rst": 0, "ena": 1},
        opens_on=[{"sda_i": "change"}],
        sustains=[
            Sustain(port="sda_i", value=0, at_most=1,
                    stated_by="majority function over the three-sample histories"),
            Sustain(port="sda_i", value=0, at_least=2,
                    stated_by="majority function over the three-sample histories"),
        ])
    assert [(s.at_least, s.at_most) for s in a.sustains] == [(None, 1), (2, None)]
    assert all(s.stated_by for s in a.sustains), (
        "an unattributed count is exactly the pacing guess `until` refuses")

    # It survives the JSON round trip every stage downstream reads through.
    import json as _json
    back = Activation.model_validate(_json.loads(a.model_dump_json()))
    assert [(s.port, s.at_most) for s in back.sustains][0] == ("sda_i", 1)

    # An entry constraining nothing is refused rather than silently ignored --
    # and this must be checked by REJECTION, because a field_validator on
    # `at_most` never runs when the field is left at its default.
    with pytest.raises(Exception):
        Sustain(port="sda_i", value=0)
    with pytest.raises(Exception):
        Sustain(port="sda_i", value=0, at_least=3, at_most=1)
