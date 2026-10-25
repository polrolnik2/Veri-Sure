"""A pre-made child is a library for every lint, not something to redraft.

The generator's lint gate, and the editor's, linted the design alone. A design
that instantiates its child exactly as the specification says then fails
"Cannot find file containing module", and the generator's retry prompt pushes
the model to write a stand-in child of its own -- i2c_master_byte_ctrl, 14 of
14 designs, about 72% of that module's disagreement with golden. These pin that
the children reach every lint.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
CHILD = ("module kid(input clk, input a, output reg y);\n"
         "  always @(posedge clk) y <= a;\n"
         "endmodule\n")
PARENT = ("module top(input clk, input a, output y);\n"
          "  kid u_kid(.clk(clk), .a(a), .y(y));\n"
          "endmodule\n")


@pytest.fixture
def lib(tmp_path):
    import shutil
    if shutil.which("verilator") is None:
        pytest.skip("verilator not installed")
    (tmp_path / "kid.v").write_text(CHILD, encoding="utf-8")
    (tmp_path / "top.sv").write_text(PARENT, encoding="utf-8")
    return tmp_path


def test_a_design_that_instantiates_its_child_lints_only_with_the_child(lib):
    """The failure that made the generator write a stand-in child."""
    from eda_agent.sim_reviewer import check_syntax
    ok, out = check_syntax(str(lib / "top.sv"))
    assert not ok and "kid" in out
    assert check_syntax(str(lib / "top.sv"), [str(lib / "kid.v")])[0]


def test_the_generator_lint_gate_is_given_the_children(lib, monkeypatch):
    import asyncio

    import eda_agent.rtl_generator as gen
    seen = []

    def fake_lint(path, extra=(), incs=()):
        seen.append((list(extra), list(incs)))
        return True, ""

    g = gen.RTLGenerator.__new__(gen.RTLGenerator)
    g.max_trials, g.failed_trial = 2, []
    monkeypatch.setattr(gen, "check_syntax", fake_lint)
    monkeypatch.setattr(gen, "looks_like_placeholder", lambda *_a: None)
    monkeypatch.setattr(g, "reset", lambda: None, raising=False)
    monkeypatch.setattr(g, "get_init_prompt_messages",
                        lambda *_a, **_k: [SimpleNamespace(content="init")], raising=False)
    monkeypatch.setattr(g, "get_order_prompt_messages",
                        lambda *_a, **_k: [SimpleNamespace(content="order")], raising=False)

    async def reply(_agent, _prompt):
        return "x"
    monkeypatch.setattr(g, "_call_agent", reply, raising=False)
    monkeypatch.setattr(g, "parse_output",
                        lambda _t: SimpleNamespace(reasoning="ok", module=PARENT), raising=False)
    g._agent = None
    ok, _code = asyncio.run(g.chat(
        input_spec="", testbench="", interface="", rtl_path=str(lib / "out.sv"),
        contract_json="{}", extra_sources=[str(lib / "kid.v")], include_dirs=[str(lib)]))
    assert ok
    assert seen == [([str(lib / "kid.v")], [str(lib)])]


def test_the_editor_lints_with_the_reviewers_children(lib):
    """A staged edit that keeps the child instance must not read as a syntax error."""
    from eda_agent.rtl_editor import _EditSession
    s = _EditSession(tb_path=None, rtl_path=str(lib / "top.sv"), output_dir=str(lib),
                     last_mismatch_cnt=0, sim_reviewer=None, max_trials=1)
    assert not s._static_findings(PARENT)[0]
    s.extra_sources = (str(lib / "kid.v"),)
    assert s._static_findings(PARENT)[0]


def test_the_reviewer_publishes_what_it_builds_with(tmp_path):
    from eda_agent.specflow_node import SpecflowReviewer
    rev = SpecflowReviewer(built=None, hdl_toplevel="top", output_dir=tmp_path,
                           extra_sources=[tmp_path / "kid.v"], include_dirs=[tmp_path])
    assert rev.extra_sources == (str(tmp_path / "kid.v"),)
    assert rev.include_dirs == (str(tmp_path),)
