"""The compile gate must reject what the SCORER rejects, not what iverilog can parse.

The gate ran at `-g2012` and so passed designs ChipVerilog could not admit. The
scorer compiles the task's shipped testbench against the candidate at `-g2012`
first and, on failure, retries with no language flag -- iverilog 12's default,
`-g2005`. For `alu` the shipped testbench fails the `-g2012` attempt, so the
plain retry is what decides, and a candidate using SystemVerilog port syntax
never reaches simulation: it is diverted to formal equivalence and scored
`function_fail` however correct it is.

A gate more permissive than the scorer is worse than no gate. It reports `pass`
on the one fact it exists to establish -- that the design can be built -- for a
design the scorer will refuse to build.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmarks.run_chipverilog import compile_gate

needs_iverilog = pytest.mark.skipif(
    not shutil.which("iverilog"), reason="iverilog not installed"
)

DES = Path("benchmarks/chipverilog/Des")

#: A task that ships a testbench, so the scorer simulates it and the dialect
#: decides. `alu` was scored `function_fail` purely for SystemVerilog ports.
TASK_WITH_TB = DES / "mips_16" / "alu"

#: A task that ships none, so the scorer proves equivalence with yosys and
#: never invokes iverilog. `or1200_gmultp2_32x32` was scored `pass` (temporal
#: induction, k=16) with `input logic` ports -- the same declarations that cost
#: `alu` its verdict.
TASK_WITHOUT_TB = DES / "or1200" / "or1200_gmultp2_32x32"

needs_corpus = pytest.mark.skipif(
    not TASK_WITH_TB.exists() or not TASK_WITHOUT_TB.exists(),
    reason="ChipVerilog corpus not present",
)


#: Verilog-2005 port declarations; a SystemVerilog body. What the RTL prompt asks for.
PORTABLE_PORTS = """
module alu (input [15:0] a, input [15:0] b, input [2:0] cmd, output reg [15:0] r);
  logic [31:0] wide;
  always @(*) begin wide = {16'b0, a}; r = cmd[0] ? wide[15:0] : b; end
endmodule
"""

#: Byte-identical apart from the port list. This is the shape that scored
#: `function_fail` on a design our own testbench had passed 40/40.
SV_PORTS = """
module alu (input logic [15:0] a, input logic [15:0] b, input logic [2:0] cmd,
            output logic [15:0] r);
  logic [31:0] wide;
  always @(*) begin wide = {16'b0, a}; r = cmd[0] ? wide[15:0] : b; end
endmodule
"""


@needs_corpus
@needs_iverilog
def test_the_gate_rejects_systemverilog_port_declarations(tmp_path):
    rtl = tmp_path / "rtl.sv"
    rtl.write_text(SV_PORTS, encoding="utf-8")
    result = compile_gate(rtl, "alu", [], TASK_WITH_TB)
    assert result["status"] == "fail", (
        "a design the scorer diverts to formal must not pass the compile gate"
    )
    assert "SystemVerilog" in result["stderr"], result["stderr"]


@needs_corpus
@needs_iverilog
def test_the_gate_still_allows_systemverilog_inside_the_body(tmp_path):
    """The constraint is the port list alone, or it would reject correct work.

    `-g2005` accepts `logic` as a variable inside the module and rejects it only
    as a port net type. Pinning both halves keeps a future tightening to
    `-g2005` strictness elsewhere -- or a loosening back to `-g2012` -- from
    passing silently.
    """
    rtl = tmp_path / "rtl.sv"
    rtl.write_text(PORTABLE_PORTS, encoding="utf-8")
    result = compile_gate(rtl, "alu", [], TASK_WITH_TB)
    assert result["status"] == "pass", result["stderr"]


@needs_iverilog
def test_the_two_differ_only_in_the_port_list(tmp_path):
    """Guards the claim the whole finding rests on: the bodies are identical.

    Without this the pair could drift into differing in substance, and the two
    gate assertions above would then be pinning nothing in particular.
    """
    def body(src: str) -> str:
        return src.split(");", 1)[1].strip()

    assert body(PORTABLE_PORTS) == body(SV_PORTS)
    assert "logic [31:0] wide;" in body(SV_PORTS), (
        "the shared body must actually contain SystemVerilog, or the "
        "body-is-still-allowed test proves nothing"
    )


@needs_corpus
def test_the_dialect_is_only_enforced_where_the_scorer_enforces_it():
    """A uniform -g2005 gate rejects correct work, which is the mirror defect.

    Tightening every task to Verilog-2005 fails `or1200_gmultp2_32x32` -- a
    design the benchmark scores `pass`. A gate that wrongly rejects is not the
    safe direction: it sends the repair loop after a design that was already
    correct.
    """
    from benchmarks.run_chipverilog import scorer_language_flag

    assert scorer_language_flag(TASK_WITH_TB) == "-g2005"
    assert scorer_language_flag(TASK_WITHOUT_TB) == "-g2012"


@needs_corpus
@needs_iverilog
def test_systemverilog_ports_pass_where_no_testbench_will_ever_see_them(tmp_path):
    rtl = tmp_path / "rtl.sv"
    rtl.write_text(SV_PORTS.replace("module alu", "module or1200_gmultp2_32x32"),
                   encoding="utf-8")
    result = compile_gate(rtl, "or1200_gmultp2_32x32", [], TASK_WITHOUT_TB)
    assert result["status"] == "pass", (
        "this task is scored by yosys equivalence, which accepts SystemVerilog"
    )


def test_the_flag_falls_back_to_permissive_when_routing_is_unknown(tmp_path):
    """Unknown routing must not become a rejection.

    The gate mirrors an authority it may fail to consult -- a vendored tool
    that is absent or restructured. Failing open keeps an unrecognised task
    scoring as it did before; failing closed would reject every such task on a
    guess.
    """
    from benchmarks.run_chipverilog import scorer_language_flag

    assert scorer_language_flag(None) == "-g2012"
    assert scorer_language_flag(tmp_path) == "-g2012"
