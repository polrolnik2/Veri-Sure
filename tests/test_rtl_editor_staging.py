"""Edits stage; only a commit builds and runs.

`replace_block` used to splice, write the file, simulate, and accept or roll
back on the spot -- so A COHERENT CHANGE SPANNING SEVERAL BLOCKS COULD NOT BE
EXPRESSED: every intermediate state is broken by construction and was discarded
as a regression. These pin the buffer that fixes it, and the two hazards it
introduces.
"""

from __future__ import annotations

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
    assert "no longer in the staged buffer" in res["error_msg"]


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
