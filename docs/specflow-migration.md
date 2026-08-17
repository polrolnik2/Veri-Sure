# specflow: status and migration

`specflow/` implements the spec-grounded verification pipeline described in
`docs/spec-testplan-coverage-chain.md` and motivated by
`docs/tb-hardening-research.md`.

## What it replaces, and why

The existing path generates one monolithic `tb.sv` that is simultaneously the
correctness oracle and the only channel describing failures to the repair agent.
Three structural problems follow, all verified in the code rather than inferred:

1. **The spec never reaches the verification side.** `TopAgentConfig.contract_only`
   is `True` and `_contract_only_context` (`top_agent.py:460-474`) truncates the
   contract to at most six `functional_summary` bullets. That string, not the
   spec, is what the Verifier, Coder and Debugger see.
2. **There is no post-simulation testbench feedback.**
   `TBGenerator.set_failed_trial` (`tb_generator.py:587-595`) has no callers.
   Once the testbench lints clean it is frozen; only RTL is ever repaired.
3. **The verdict is two-valued and parsed from prose.** `sim_review` returns a
   bool plus a mismatch count, so `is_pass=True, mismatch_cnt=0` means both
   "everything was checked and passed" and "nothing ran".

## Pipeline

```
prompt.txt ──S1──▶ requirements ──S2──▶ testplan ──S3──▶ bins + checks
                        │                                      │
                        └────────── reference model ───────────┤
                                          │                    │
                                          └──── cocotb suite ──┴──▶ verdict
```

Five agent calls; every gate is pure code. Gates: **G1** spec attribution,
**G2** requirement→testplan, **G3** testplan→bin+check, **G4** reference model,
**G5** rendered suite, **G6** two-sided control, **G6b** record reconciliation,
**G7** accept decision, **G8** mutation qualification.

| Module | Role |
| --- | --- |
| `schema.py`, `ids.py` | artifact types; `UID@rev` references |
| `assure.py` | one traceability engine, four defect classes |
| `stage.py` | the bounded agent-plus-gate loop, implemented once |
| `model_io.py` | `FilePort` / `ReplayPort` / `ApiPort` |
| `s1_requirements.py`, `s2_testplan.py`, `s3_coverage.py` | the three stages |
| `refmodel/` | Python reference model, G4 |
| `tb/runtime.py` | hand-written, protected: clock, scoreboard, verdict record |
| `tb/render.py` | emits the cocotb suite; owns every check and bin call |
| `run.py`, `coverage.py`, `gate.py` | execute, join, decide |
| `unreach.py` | formal discharge of unreachable bins |
| `qualify.py` | mcy mutation gate |
| `loop.py`, `testcase_agent.py` | the hard-gated loop |
| `integration.py` | bridge to `eda_agent`'s node-level run |

## Status

Milestones M0–M9 are implemented and tested; 161 tests pass with no model in the
loop, because every stage replays a recorded fixture
(`tests/fixtures/specflow/hadd`, a real VerilogEval-v2-EXT problem).

Demonstrated on real tooling rather than asserted:

- the reference model agrees with `Prob024_hadd_ref.sv` exhaustively, and a
  seeded wrong model is detected;
- the suite passes golden RTL and fails a tied-off DUT (the two-sided G6 control);
- RTL with two independent bugs reports **both**, with per-mismatch values and
  stimulus, in one run;
- a bin on a tied-low output is proved unreachable by k-induction; a live one is
  not discharged;
- a rigged bug converges in one repair; a rigged stall terminates inside budget.

## Retirement of the SystemVerilog path

`tb_backend` now defaults to `"specflow"`. `TopAgent.run` dispatches to
`_run_instance_specflow`, which builds and certifies the oracle *before* any RTL
exists, then repairs against the three-valued verdict.

Retired:

- **`TB_4_SHOT_EXAMPLES` and `GLUE_TB_EXAMPLE` are deleted** from `prompts.py`
  (31.8KB → 13.3KB). They taught the defects the harness then compensated for:
  none of the four examples emitted the `[TEST …]` markers the prompt mandated,
  and all four latched a single global `first_mismatch_time`, which is precisely
  what `utils.py:49-83` exists to detect. `FAILED_TRIAL_PROMPT` stays — it is
  shared with `rtl_generator`.
- **`top_agent` no longer imports `tb_generator` at module scope.** The import is
  local to `_run_instance`, the retired path, so `tb_generator.py` is dead code
  and deleting the file cannot break anything. A test asserts this by walking
  `top_agent`'s module-level imports.

`RTLEditor` needed no changes: it is parameterised on a reviewer object, so
`SpecflowReviewer` — same `(is_pass, mismatch_cnt, sim_output)` shape as
`SimReviewer.review()` — is the seam that swaps the oracle underneath it.

### One step needs a permission this session lacks

**`eda_agent/tb_generator.py` is still on disk.** Both `rm` and `git rm` were
refused by the environment's permission classifier. The module is unreferenced,
unreachable and unimported; removing the file is a one-line follow-up:

```bash
git rm eda_agent/tb_generator.py
```

### And two things still need an API key

Neither is possible in an environment without `OPENAI_API_KEY`:

1. **A baseline VerilogEval-v2-EXT run.** M9's comparison is meaningless without
   the before number. Note that `run_verilog_eval_v2.py:416-433` discards
   `is_sim_pass` and re-judges against the golden testbench, so replacing the
   internal oracle does not move the scoring surface — what changes is what the
   repair loop converges on, which is exactly why the baseline matters.
2. **One end-to-end node run through `top_agent`.** `cli.py:66` exits without an
   API key, so the specflow branch inside `_run_instance` has never executed in
   situ. Every part of it is tested through `integration.py`, which is a pure
   function of a run directory — but that is not the same as having run it.

Until both are done, treat the specflow path's benchmark standing as unmeasured
rather than unchanged: the machinery is tested, but no end-to-end node run has
executed in situ.

### How the node path is wired

`_run_instance_specflow` (in `top_agent.py`) builds the contract, merges any
orchestrator-supplied `contract_sva` / `child_assumes` / `child_rtl`, then calls
`specflow_node.run_specflow_node`, which:

1. calls `build_artifacts` — S1→S3, reference model, rendered suite, gate by
   gate, stopping at the first failure and naming the stage. **The oracle is
   certified before any RTL exists**, which is also what keeps the reference
   model independent: there is no `rtl.sv` to contaminate it.
2. generates RTL and syntax-checks it;
3. repairs against `SpecflowReviewer`, whose `review()` returns the three-valued
   verdict and a payload in which every mismatch names its check, both values and
   the stimulus that produced it.

`EXTEND_TB` and `STALLED` return without invoking repair: neither is an RTL
problem, and reporting them as one is what sends a repair agent after the wrong
artifact.

## Running a stage by hand

With no API key, each stage emits its prompt and stops:

```bash
python -m specflow.cli s1 --run-dir runs/<r> --model-port file   # writes the prompt, exits 3
# ...answer it at runs/<r>/agent_io/s1_r0_response.txt...
python -m specflow.cli s1 --run-dir runs/<r> --model-port file   # ingests, gates
```

Then `s2`, `s3`, `refmodel`. Once answered, `--model-port replay` reproduces the
whole chain deterministically and for free.
