"""Module ports must be plain Verilog-2005, whatever the body is.

Measured on `alu`: byte-identical logic scored `function_fail` when its ports
read `input logic [15:0] a` and `pass` when they read `input [15:0] a`. The
whole difference was the keyword.

The mechanism is worth stating because it is silent. Benchmark testbenches are
Verilog-2005, so `logic` in a port list fails their compile with "Net data type
requires SystemVerilog". The scoring flow then falls back to a formal miter --
stricter, and it reports a functionally correct design as not equivalent. The
run looks like a functional failure and is a dialect mismatch, and every design
generated before this carried it, so it was a systematic loss rather than a
one-off.
"""

from __future__ import annotations

from pathlib import Path

RTL_GEN = Path(__file__).resolve().parents[1] / "eda_agent" / "rtl_generator.py"


def test_the_prompt_forbids_logic_in_the_port_list():
    text = RTL_GEN.read_text(encoding="utf-8")
    assert "PLAIN VERILOG-2005" in text
    assert "Never `input logic`" in text


def test_the_prompt_explains_the_cost_not_just_the_rule():
    """A rule with no reason gets dropped the next time the prompt is edited."""
    text = RTL_GEN.read_text(encoding="utf-8")
    assert "Net data type requires SystemVerilog" in text
    assert "formal miter" in text
    assert "function_fail" in text and "pass" in text


def test_the_body_is_still_allowed_to_be_systemverilog():
    """Over-correcting to plain Verilog everywhere would lose always_comb and
    the rest of what Verilator is happy with."""
    text = RTL_GEN.read_text(encoding="utf-8")
    assert "The body may stay SystemVerilog" in text
