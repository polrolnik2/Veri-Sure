"""`deliverable`: the shipped module has the reference interface and the
verified behaviour, probes unconnected."""
import shutil
import subprocess

import pytest

from eda_agent.strip_probes import deliverable

RTL = """
module ctr (input wire clk, input wire rst, output reg [3:0] q, output wire at_top);
    assign at_top = (q == 4'hf);
    always @(posedge clk) if (rst) q <= 0; else q <= q + 1;
endmodule
"""
CONTRACT = {"module_name": "ctr", "parameters": [], "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "rst", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 4},
    {"name": "at_top", "dir": "probe", "width": 1}]}


def test_the_wrapper_carries_the_reference_interface_only():
    out = deliverable(RTL, CONTRACT)
    assert "module ctr__probed" in out and out.count("module ctr (") == 1
    wrapper = out[out.index("module ctr ("):]
    assert "at_top" not in wrapper and "output wire [3:0] q" in wrapper


def test_parameters_or_an_ambiguous_header_ship_nothing():
    assert deliverable(RTL, {**CONTRACT, "parameters": [{"name": "W"}]}) is None
    assert deliverable(RTL + RTL, CONTRACT) is None


@pytest.mark.skipif(not shutil.which("iverilog"), reason="needs iverilog")
def test_the_wrapped_design_elaborates_and_counts(tmp_path):
    (tmp_path / "d.v").write_text(deliverable(RTL, CONTRACT))
    (tmp_path / "tb.v").write_text("""
module tb; reg clk=0, rst=1; wire [3:0] q; ctr dut(.clk(clk), .rst(rst), .q(q));
always #1 clk = ~clk;
initial begin #4 rst = 0; #20 $display("q=%0d", q); $finish; end endmodule
""")
    subprocess.run(["iverilog", "-o", str(tmp_path / "a"), str(tmp_path / "d.v"),
                    str(tmp_path / "tb.v")], check=True)
    out = subprocess.run(["vvp", str(tmp_path / "a")], capture_output=True, text=True).stdout
    assert "q=" in out and "q=0" not in out
