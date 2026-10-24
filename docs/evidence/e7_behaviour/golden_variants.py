"""Corrected references for scoring, where golden itself carries a quirk the spec does not ask for.

i2c_master_bit_ctrl (docs/evidence/e7/qualitative/i2c_master_bit_ctrl.md, BIT-CTRL-GOLDEN.md):
  gB  golden never resets `dout`, and the harness runs testpoints back to back, so its `dout` at
      the start of a testpoint is whatever the previous one left. gB resets it to 0 on nReset/rst.
  gC  gB, with the raw capture registers cSCL/cSDA reset to 11 instead of 00 (the spec: "filtered
      SCL/SDA are initialized high"); golden's 00 makes a filter glitch after each reset at
      clk_cnt < 4.
"""
import re


def _patch(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def bit_ctrl_corrected(ref: str) -> tuple[str, str]:
    """(gB, gC) from the reference bit controller's source."""
    gB = _patch(ref, "    always @(posedge clk)\n      if (sSCL & ~dSCL) dout <= #1 sSDA;",
                "    always @(posedge clk or negedge nReset)\n      if (!nReset) dout <= #1 1'b0;\n"
                "      else if (rst) dout <= #1 1'b0;\n      else if (sSCL & ~dSCL) dout <= #1 sSDA;")
    gC = re.sub(r"(cS(?:CL|DA)\s*<=\s*(?:#1\s*)?)2'b00", r"\g<1>2'b11", gB)
    assert gC.count("2'b11") - gB.count("2'b11") == 4, "cSCL/cSDA are reset in two places each"
    return gB, gC
