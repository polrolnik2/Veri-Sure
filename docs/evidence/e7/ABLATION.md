# The RTL Editor without its repair loop

**The question:** what does the repair loop add over generation alone, with the
same model and the same inputs?

**What ran.** Three generation-only designs on each of the 17 corpora, 51 in all
(`e7_module.py --editor-only --rounds 0 --tag genN`, d3bad0f). RTLGenerator wrote
`rtl.sv` from the specification and the run's contract. The run's shipped set
reviewed it once, and no repair ran. The ChipVerilog verdict then graded it on the
deliverable, as for the editor jobs. The model was gpt-6-luna at xhigh on the SDC
gateway, as in the editor jobs.

The generator's own retry loop stayed in, as it was in the editor jobs: up to 5
calls, re-prompting only on a parse error, a placeholder stub or a failed compile.
41 designs took one call, 9 took two and 1 took three. That came to 62 calls,
about $0.47 by the `EDITOR-CACHE.md` pricing, and 11.2 hours of job time.

**Beside them:** the verdict on each editor job's own generated design, i.e. its
round 0 before any repair (`<run>/editor/<module>/chipverilog_generated.json`,
CPU only). That gives the same design before and after repair. For the two
resumed jobs, round 0 is the killed attempt's (`RESUME.md`).

Records: `<run>/ablation/<module>/<genN>/`, one row per design in `ABLATION.json`.

Each cell is **passing requirements / failing testpoints · verdict** (fail =
function_fail, error = equivalence_error).

| corpus | N | gen1 | gen2 | gen3 | editor round 0 (generated) | editor final (repaired) | final vs best sample |
|---|---|---|---|---|---|---|---|
| luna12 fpu_exceptions | 143 | 88 / 58 · fail | 126 / 31 · fail | 136 / 3 · fail | 99 / 283 · fail | 136 / 0 · fail | equal |
| luna13 fpu_exceptions | 138 | 126 / 8 · fail | 92 / 255 · fail | 126 / 8 · fail | 127 / 6 · fail | 132 / 0 · fail | above |
| luna14 fpu_exceptions | 136 | 102 / 90 · fail | 131 / 72 · fail | 87 / 4 · fail | 103 / 309 · fail | 131 / 72 · fail | equal |
| luna15 fpu_exceptions | 143 | 95 / 264 · fail | 103 / 266 · fail | 130 / 73 · fail | 128 / 76 · fail | 128 / 76 · fail | below |
| luna12 i2c_master_bit_ctrl | 103 | 80 / 275 · fail | 76 / 273 · fail | 75 / 285 · fail | 77 / 272 · fail | 77 / 49 · fail | below |
| luna13 i2c_master_bit_ctrl | 123 | 64 / 263 · fail | 77 / 266 · fail | 77 / 259 · fail | 71 / 254 · fail | 78 / 206 · fail | above |
| luna14 i2c_master_bit_ctrl | 111 | 88 / 296 · fail | 93 / 282 · fail | 99 / 303 · fail | 98 / 292 · fail | 96 / 107 · fail | below |
| luna15 i2c_master_bit_ctrl | 106 | 91 / 308 · fail | 92 / 290 · fail | 95 / 294 · fail | 91 / 296 · fail | 98 / 299 · fail | above |
| luna12 i2c_master_byte_ctrl | 88 | 69 / 338 · fail | 67 / 346 · fail | 71 / 83 · fail | 62 / 321 · fail | 72 / 270 · fail | above |
| luna13 i2c_master_byte_ctrl | 97 | 73 / 272 · fail | 74 / 223 · fail | 73 / 219 · fail | 73 / 90 · fail | 71 / 119 · fail | below |
| luna14 i2c_master_byte_ctrl | 98 | 73 / 360 · fail | 76 / 125 · fail | 83 / 302 · fail | 73 / 260 · fail | 59 / 210 · fail | below |
| luna12 or1200_dc_fsm | 80 | 66 / 35 · fail | 65 / 26 · fail | 70 / 24 · fail | 66 / 35 · fail | 69 / 0 · fail | below |
| luna13 or1200_dc_fsm | 84 | 84 / 0 · fail | 67 / 21 · fail | 72 / 20 · fail | 76 / 20 · fail | 84 / 0 · fail | equal |
| luna14 or1200_dc_fsm | 79 | 68 / 8 · fail | 71 / 5 · fail | 70 / 6 · fail | 65 / 12 · fail | 74 / 4 · fail | above |
| luna12 or1200_sb | 68 | 63 / 12 · fail | 60 / 45 · fail | 62 / 27 · error | 61 / 43 · error | 64 / 12 · error | above |
| luna13 or1200_sb | 66 | 28 / 156 · pass | 28 / 154 · pass | 28 / 156 · pass | 28 / 154 · pass | 65 / 2 · error | above |
| luna14 or1200_sb | 66 | 27 / 138 · fail | 28 / 133 · pass | 28 / 135 · pass | 28 / 135 · pass | 31 / 128 · pass | above |

**Verdicts:**

| arm | pass | function_fail | equivalence_error |
|---|---|---|---|
| generation only, 51 designs | 5 | 45 | 1 |
| editor round 0, 17 designs | 2 | 14 | 1 |
| editor final, 17 designs | 1 | 14 | 2 |

## What it shows

- **Repair raises the shipped-set score.** The mean pass rate is 84.0% for the
  editor's finals, against 76.1% for the generation-only designs and 75.5% for
  the editor's own round 0, another generated design. Against its own round 0,
  the final is higher on 12 corpora, equal on 2 and lower on 3. All three lower
  ones are jobs the `restore_best` defect hit (`EDITOR-RESULTS.md`).
- **Repair does not change correctness.** No design on any module other than sb
  is equivalent to golden in either arm: 45 of 45 generated, 14 of 14 repaired.
  Every pass in either arm is or1200_sb through the configuration route: the
  design keeps the specification's `ifdef OR1200_SB_IMPLEMENTED` with a
  pass-through fallback, and the benchmark leaves the macro undefined.
  luna14 sb's gen1 took that route but registers the acknowledge in its
  fallback, a cycle late, so it fails.
- **On the one job where repair changed a verdict, it moved away from golden.**
  luna13 sb's generated design is proven equivalent (induction, k=16), as all
  three ablation samples are. The repair made it satisfy the shipped checks
  (28 -> 65 passing, 154 -> 2 failing testpoints). Those checks were written
  against this run's buffering reference model, so the repaired design buffers,
  which golden does not. Its verdict is equivalence_error, because the checker
  cannot import its FIFO memory; it would not be equivalent either way. The
  repair loop optimizes toward the checks, and where the checks are wrong, it
  repairs a correct design into an incorrect one.
- **Generation alone can satisfy a whole shipped set and still be wrong.**
  luna13 dc_fsm gen1 passes all 84 requirements with no failing testpoint and
  is function_fail, exactly like the editor's final on that corpus.
- **Samples vary widely, and most of the editor's gain is one good draw.** On
  fpu, three samples of one corpus spread by up to 48 requirements (luna12: 88,
  126, 136). Picking the best of three by the same shipped set gives a mean pass
  rate of 81.7%, against 84.0% for the editor's finals. The editor's final beats
  that best sample on 8 corpora, ties 3 and is below 6. Generation costs about
  $0.01 a design; a full logged repair job is estimated at $1.55-2.34
  (`EDITOR-CACHE.md`).

Equivalence is the grade here, and only the luna13 sb case moved it. The rest
of the difference between the arms is how well the designs satisfy the run's
own checks.
