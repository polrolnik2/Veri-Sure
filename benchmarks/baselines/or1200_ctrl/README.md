# ChipVerilog baseline: `or1200_ctrl`

Two arms of Veri-Sure on the same task, same model, same reasoning effort.

| | arm A | arm B |
| --- | --- | --- |
| what | pre-hardening SystemVerilog testbench path | specflow spec-grounded chain |
| verdict | equivalence_error (flow=equivalence, proof=bounded_seq) | not scored |
| produced RTL | True | False |

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

## What this round actually measured

Not oracle quality. The two arms failed in incomparable ways: arm A got far
enough to be wrong in measurable ways -- a candidate, a verdict, a mismatch
trajectory of 9, 16, 5, 6, 5, 7, 6, 5 -- while arm B never produced an artifact
to be wrong about. This measures that specflow's first stage did not survive a
14.3KB specification.

Arm A's verdict is `equivalence_error`, not `function_fail`: Yosys could not
import a `$mem_v2` cell into its SAT database, so `formal_status` is `unknown`.
By ChipVerilog's own convention a solver that proves nothing does not convict
the candidate. Arm A cleared every gate that could decide -- compile gate,
interface compatibility, reference precheck -- and the one that would have
decided correctness could not run.

## Why arm B failed, and what came of it

S1 hard-failed after four rounds. Two defects in the gate, both since fixed:

1. **Offsets, not quotes.** G1 required the model's exact character offsets.
   0 of 31 were right; 30 of 31 quotes were verbatim and locatable by search.
   Round 0 produced 55 requirements citing real clauses (median 130 characters)
   and received 58 errors, every one about arithmetic. Rounds 1 and 2 cited
   1- and 6-character fragments and received 2 -- the feedback made attributing
   nothing cheaper than attributing correctly. Fixed in `fde9e71`; re-scoring
   round 0 under that gate gives 8 errors instead of 58, all `uncovered`.

2. **The repair round could not see what it was repairing.** The prompt said
   "fix exactly these defects" while the model had no access to its own previous
   answer, so it regenerated everything each round: requirement counts churned
   55 -> 61 -> 51 -> 31, and an issue list keyed by UID was being applied to an
   artifact that no longer existed. Fixed in `353fd60`.

This baseline is therefore the "before" for both fixes, which is the use it is
committed for.

## Known gap

Arm A's token accounting is empty. The runner was patched to record it, but arm
A executes from a worktree copy staged before that patch, so this round's
numbers are lost. `make_arm_a.sh` copies the runner fresh, so a reconstructed
arm A records them.
