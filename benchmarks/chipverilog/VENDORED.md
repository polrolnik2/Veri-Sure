# ChipVerilog — vendored copy

This directory is a verbatim vendored copy of the upstream ChipVerilog benchmark.
It is **not** Veri-Sure code. Do not edit files here to fix Veri-Sure bugs; changes
would be lost on the next upstream sync and would silently invalidate comparisons
against published numbers.

## Provenance

| | |
| --- | --- |
| Upstream | <https://github.com/HKUSTGZ-MICS-LYU/ChipVerilog> |
| Commit | `3eea482f20c048966d54ed04c418b85e5fd4d498` (2026-08-15) |
| Paper | [arXiv:2607.13079](https://arxiv.org/abs/2607.13079) — Tan, Du, Meng, Lyu |
| Artifact | Zenodo DOI [10.5281/zenodo.21583114](https://doi.org/10.5281/zenodo.21583114) |
| Vendored | 2026-08-17, excluding `.git/` and `__pycache__/` |

To re-sync, clone upstream at a new commit and replace this tree wholesale,
then update the commit hash above.

## Licensing — read before redistributing

The harness (`tools/`, `artifact_evaluation/`) is MIT, but the RTL under `Src/`
and `Des/` is third-party OpenCores material under its own terms — **LGPL** for
OR1200, MIPS-16 and the double-precision FPU, BSD for I2C, and unspecified for
the CORDIC core. See `THIRD_PARTY_LICENSES.md`. The repository-level MIT
`LICENSE` does not override these. Upstream notices in source headers must be
retained.

Veri-Sure itself is MIT; this directory is the one part of the tree that is not.

## Layout

| Path | Size | Purpose |
| --- | --- | --- |
| `Src/` | 6.1M | Original source trees, docs, benches, per-task `description.txt` prompts |
| `Des/` | 2.9M | Flattened per-module reference designs used by the verification flow |
| `Result/` | 65M | Published candidate verdicts for `claude`, `codex`, `deepseek` (baselines) |
| `tools/` | 228K | `formal_equivalence.py`, `generate_deepseek_results.py` |
| `artifact_evaluation/` | 36K | `reproduce_metrics.py`, `smoke_test.sh`, metric definition |

## What the benchmark is

64 tasks across 5 families: `or1200_hp` (38), `mips_16` (11), `double_fpu` (9),
`i2c` (3), `verilog_cordic_core` (3). Several targets exceed 1000 lines. Each task
pairs specification documents with reference RTL.

Evaluation is **level-aware**: an `iverilog` compile gate (the top module must carry
the reference name), then either a self-checking simulation testbench or a Yosys
equivalence flow.

## Reproducing the published numbers

Requires only the Python standard library — the cached verdicts under `Result/`
are sufficient, no EDA tools needed:

```bash
python3 benchmarks/chipverilog/artifact_evaluation/reproduce_metrics.py
```

Verified 2026-08-17 (64 tasks × 5 samples × 3 models = 960 verdicts):

| model | syntax@1 | syntax@5 | function@1 | function@5 |
| --- | ---: | ---: | ---: | ---: |
| Claude Opus 4.5 | 78.75 | 96.88 | 17.50 | 35.94 |
| GPT-5.4 | 83.13 | 93.75 | 23.13 | 37.50 |
| DeepSeek V4 Pro | 45.94 | 78.13 | 13.44 | 23.44 |

Running the verification flow itself additionally needs `iverilog`, `vvp` and `yosys`.

## Why this benchmark is interesting for TB hardening

Measured over those 960 cached verdicts, the oracle that actually decided the
verdict was:

| flow | share |
| --- | ---: |
| Yosys equivalence | 56.9% |
| compile gate | 30.7% |
| simulation testbench | 12.4% |

Only 16 of the 64 task directories ship a testbench at all; of those, 12 are
self-checking and 4 are print-only (`IF_stage`, `mips_16_core_top`,
`register_file`, `or1200_top`). The remaining 48 tasks have no testbench, which
is why formal equivalence carries the suite.

Two mechanisms in `tools/formal_equivalence.py` are directly relevant to hardening
Veri-Sure's own testbenches:

1. **`tb_is_self_checking()`** — a static gate. A testbench counts as self-checking
   iff some string literal can express a fail verdict (`/fail|error|mismatch|wrong|
   incorrect/i` over string literals of the comment-stripped text). The upstream
   docstring puts it plainly: *"a print-only bench cannot produce a trustworthy
   pass."* Print-only benches are excluded from concluding, and fall through to formal.

2. **Reference precheck** — the golden design is elaborated through the flow first.
   If the reference fails, the verdict is `reference_fail`, not `function_fail`:
   blame lands on the harness rather than the candidate. Solver timeouts are
   likewise excluded from `function_fail`, because a timeout proves nothing about
   the candidate.

Note the asymmetry when using this to measure Veri-Sure: ChipVerilog's flow assumes
a reference design exists, whereas a Veri-Sure run generates its own testbench and
has no golden RTL to precheck against.
