# Control oracles

A hand transliteration of a known-correct design into a specflow reference model.
Its job is to answer one question the pipeline cannot answer about itself:

> If the oracle were *right*, would the harness pass a design that is right?

Without a control, a failing testpoint has two explanations — the design is
wrong, or the harness is — and no way to choose. A control fixes the oracle so
only the harness is variable.

**These are debug instruments. They are not part of the pipeline**, no gate reads
them, and no agent sees them. Production has no golden RTL; that is the point.

## `i2c_master_bit_ctrl`

A line-by-line transliteration of
`benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/i2c_master_bit_ctrl.v`.

Reproduce the control measurement (needs a completed run's testplan and coverage
model — any i2c run under a scratchpad will do):

```
python -m benchmarks.golden_check \
  --run <run-dir> --model benchmarks/controls/i2c_master_bit_ctrl/ref_model.py \
  --dut golden=benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/i2c_master_bit_ctrl.v \
  --dut candidate=<run-dir>/rtl.sv \
  --top i2c_master_bit_ctrl --include benchmarks/chipverilog/Des/i2c \
  --idle-high scl_i --idle-high sda_i --hold 60
```

Expected: **golden 168/168, a wrong candidate 28/168.**

### Two bugs this file had, and what they cost

Both are the same mistake — reading a value from the **wrong clock generation** —
and between them they accounted for **every one of the 55 testpoints a correct
design was failing**. Neither was a harness defect. Worth recording because a
generated reference model can make exactly the same error, and because they are
the reason the control was mistrusted for as long as it was.

1. **`sta_condition` / `sto_condition` computed combinationally.** Golden
   registers them (`sta_condition <= #1 ~sSDA & dSDA & sSCL;`) and `busy`/`al`
   read the registered value. Collapsing that stage made `al` fire one edge
   early, which aborted the command the DUT was completing — so the model fell a
   whole command period behind and then missed a command window at the next
   stimulus vector boundary. **46 of 55 failures**, spread across `al`, `busy`,
   `scl_oen` and every "one side ran out of states" report.

2. **The FSM gated on `clk_en` after the divider had overwritten it.** Golden's
   `if (clk_en) case (c_state)` sits in an `always @(posedge clk)` block, so it
   reads the value latched on the *previous* edge. Reading the freshly computed
   one advances the machine one edge early. Invisible while `ena=0` — `clk_en` is
   then 1 every cycle, so old and new agree — and it appeared the instant the
   prescaler started toggling. **The remaining 9 failures.**
