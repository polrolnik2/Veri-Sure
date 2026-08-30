"""Edits stage; only a commit builds and runs.

`replace_block` used to splice, write the file, simulate, and accept or roll
back on the spot -- so A COHERENT CHANGE SPANNING SEVERAL BLOCKS COULD NOT BE
EXPRESSED: every intermediate state is broken by construction and was discarded
as a regression. These pin the buffer that fixes it, and the two hazards it
introduces.
"""

from __future__ import annotations

import json

import pytest

from eda_agent.rtl_editor import _EditSession
from eda_agent.trace_slicer import RtlBlock

RTL = """\
module m(input clk, input a, output b, output c);
assign b = a;

always @(posedge clk) begin
  c <= a;
end

endmodule
"""

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


def test_block_internals_selects_nothing_away_and_reports_transitions(tmp_path):
    """The cap was the bug, and a smarter cap would be a different bug.

    A block's `reads` include every LOCALPARAM it mentions, and those are
    constants. Taking `sorted(names)[:12]` took them FIRST, because ASCII puts
    CMD_START and ST_IDLE ahead of cnt, state and sda_chk. MEASURED on the
    second live editor run: all twelve signals `explain` showed were constants,
    twelve parameter definitions at fifteen identical samples each, and the
    state register the failure was about never appeared.

    Ranking the cap by transition count would only move the bias: a `clk_en`
    toggling every cycle would win and an `sda_chk` moving ONCE at exactly the
    deciding edge would be cut -- and the second is the more informative for a
    temporal check. So nothing is selected away; the REPRESENTATION changes
    from a dense grid to transitions, which is what makes that affordable.
    """
    import sys
    import types

    from eda_agent import explain as _ex
    from eda_agent.trace_slicer import RtlBlock

    times = [10, 20, 30]
    series = {
        "CMD_START": ["1000", "1000", "1000"],   # a localparam
        "ST_IDLE": ["0000", "0000", "0000"],     # another
        "clk_en": ["0", "1", "0"],               # noisy: 2 transitions
        "sda_chk": ["0", "0", "1"],              # ONE transition, and the point
        "state": ["0001", "0010", "0011"],
    }
    fake = types.ModuleType("eda_agent.trace_report")
    fake.__dict__.update({
        "VCDVCD": lambda *a, **k: object(),
        "_vcd_find_signal": lambda vcd, leaf, prefer_substrings=None: (
            leaf if leaf in series else ""),
        "_vcd_tv": lambda vcd, full: full,
        "_vcd_value_at": lambda tv, t, inclusive=False: series[tv][times.index(t)],
    })
    real = sys.modules.get("eda_agent.trace_report")
    sys.modules["eda_agent.trace_report"] = fake
    wave = tmp_path / "w.vcd"
    wave.write_text("$enddefinitions $end\n")   # must EXIST; the reader is faked
    try:
        blocks = [RtlBlock(id="b", kind="always", start_line=1, end_line=2,
                           clocking="posedge clk", code="",
                           writes=("state", "sda_chk", "clk_en"),
                           reads=("CMD_START", "ST_IDLE"))]
        got = _ex._block_internals(wave, blocks, times)
    finally:
        if real is not None:
            sys.modules["eda_agent.trace_report"] = real
        else:
            del sys.modules["eda_agent.trace_report"]

    # EVERY signal that moved is present -- the one-transition one included.
    assert set(got) - {"__held_constant__"} == {"clk_en", "sda_chk", "state"}
    assert got["sda_chk"] == {"at_window_start": "0",
                              "changed": [{"t": 30, "v": "1"}]}
    # Constants are reported once each, not as N identical samples.
    assert got["__held_constant__"] == {"CMD_START": "1000", "ST_IDLE": "0000"}


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
