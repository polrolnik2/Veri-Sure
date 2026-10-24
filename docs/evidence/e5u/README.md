# A frozen upstream, so `[O]` can be measured against identical inputs

Everything a run produces before the oracle stage: S1's requirements, `[P]`'s
probe table, S2's testplan, S3's coverage model, the stimulus, the normalized
forms, and the witness.

`docs/evidence/e5_oracle_stage.py` re-enters `run_oracle_stage` against these,
so a change to how checks are authored, refuted or repaired is measured in about
an hour instead of three -- and measured against IDENTICAL inputs rather than a
fresh draw that moves every number at once and leaves no way to attribute the
difference.

**The witness is here for the same reason the stage holds it on disk.** A
freshly drawn witness is a second reading of the same requirements, so a check
could be accepted in one run and rejected in the next for no reason anyone could
name -- "the thing doing the measuring has to hold still". The design population
is NOT here: it is per-run and each member costs one call, and holding it fixed
across experiments would tie every blindness figure to one draw of seven.

**The contract that was in force is not the file on disk.** `[P]` appends the
probes in `probes.json` to `contract["io"]` before the oracle stage sees it, and
`benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json` declares none.
Replaying against the file makes every probe-reading check abstain -- 82 of 96
on the previous run. Both drivers here rebuild it from `probes.json`.

Produced by `docs/evidence/e5_full_pipeline.py`, whose oracle stage was stopped
once these were written.

    148 requirements   17 probes   366 testpoints   147 normalized forms
