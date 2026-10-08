# ChipVerilog baseline: `i2c_master_bit_ctrl`

Two arms of Veri-Sure on the same task, same model, same reasoning effort.

| | arm A | arm B |
| --- | --- | --- |
| what | pre-hardening SystemVerilog testbench path | specflow spec-grounded chain |
| verdict | function_fail (flow=equivalence, proof=bounded_seq) | function_fail (flow=equivalence, proof=bounded_seq) |
| produced RTL | True | True |

## How to read these numbers

**Which oracle decided.** ChipVerilog is level-aware: an iverilog compile gate,
then a self-checking simulation testbench where the task ships one, otherwise a
Yosys equivalence proof. Only 6 task directories ship a testbench and only 11
tasks were ever decided by one, so for most tasks -- including this one unless
`flow` says `simulation_tb` -- the verdict is an equivalence result and **not** a
testbench pass rate.

**This environment is not the published one.** Re-verifying the five published
`claude` candidates for `i2c_master_top` reproduces 3 of 5. Both disagreements
move `compile_fail` to `function_fail`, because this iverilog accepts candidates
the published environment rejected. The pass count reproduces exactly (0 of 5
both ways), so pass/fail is comparable with published numbers while the failure
*category* is environment-local. Both arms are scored by one invocation, so they
remain comparable with each other regardless.

**What arm A is.** The merge-base tree with the agent hardening absent --
`specflow/` gone, `tb_generator.py`, `_run_instance` and `TB_4_SHOT_EXAMPLES`
present -- plus two things that are not hardening: transport (that tree cannot
reach this model at all) and hierarchy plumbing (inert on a leaf task).
`make_arm_a.sh` reconstructs it and re-checks those properties.

**Neither arm receives golden RTL.** The two are comparable to each other; they
are not directly comparable to ChipVerilog's published table, whose flow
prechecks a reference design.

## Contents

Veri-Sure's own outputs only. The vendored task under
`benchmarks/chipverilog/Des/` is referenced, not copied: that tree carries
third-party licensing (LGPL for OR1200/MIPS/FPU, BSD for I2C) and `VENDORED.md`
warns that copies drift from the notice governing them. Derived artifacts here
-- `requirements.json` above all -- quote spec fragments verbatim by design.

## The comparison

Both arms produced a compiling, interface-compatible candidate and both scored
`function_fail` -- a real design that is functionally wrong, not one that failed
to build. That already beats 6 of the 15 published attempts on this task, which
died at the compile gate. Neither is correct.

| | arm A | arm B |
| --- | --- | --- |
| RTL | 8,842 B | 10,595 B |
| own verdict | `is_sim_pass: False` | `EXTEND_TB` |
| input tokens | ~895k | 95k |
| debug loop | 807,786 input tokens, 8 rounds | did not run |

## What each failure was worth

Arm A stalled: 22 mismatches, eight identical rounds, no diagnosis of why it
could not move. Its debug loop spent 807,786 input tokens producing 30,032
tokens of edits -- the accumulated `failed_trial` history re-splatted into every
prompt, which is the pathology specflow's stage design cites from LLM4DV, here
measured rather than argued.

Arm B's suite never ran. `Env.expect` re-derived the `evaluate` vs `step` choice
from `LATENCY_CYCLES > 1` while `compose.choose_base` makes it from the contract,
so a sequential model with latency 0 or 1 was routed to an entry point it does
not define. All 23 testpoints raised `NotImplementedError` before writing a
record. specflow's sequential path had never once run, and the test suite stayed
green throughout because the only fixture is a combinational half adder.

The verdict is the part worth keeping. No test reported a mismatch, because no
test got far enough to check anything -- a two-valued oracle would have returned
`is_pass=True, mismatch_cnt=0`. The three-valued verdict returned `EXTEND_TB`,
and G6b's reconciliation caught 23 XML failures against 0 JSON records. That is
the exact confusion the redesign exists to prevent, caught on the first real
sequential design.

Fixed in `f6da2eb`: `expect` now dispatches on what the model implements, with a
test that fails against the old logic.

## What this does and does not establish

Not oracle quality. Arm B's oracle -- 31 requirements, 23 testpoints at 64
stimulus vectors each, a 370-line sequential reference model -- was built and
certified but never exercised, so nothing here measures whether it is a good
one. Re-running arm B on this task with the dispatch fix is the measurement that
would.

What it does establish: the four specflow stages complete on a real ChipVerilog
task (S1, S2, S3 in one round each; refmodel in four), which no previous run had
shown, and the three-valued verdict distinguished "nothing ran" from "everything
passed" in a case where a two-valued one could not.
