# RTL Editor on the rep corpora -- results

One job per corpus: luna12, luna13 and luna14 on all five modules, and luna15 on
fpu_exceptions and i2c_master_bit_ctrl -- 17 jobs. Each job ran
`e7_module.py --editor-only` (`e7_rtl_editor.py`). RTLGenerator writes `rtl.sv` from the
specification and the run's contract. RTLEditor then repairs it against the
run's SHIPPED check set for up to 3 rounds and 20 trials, and a ChipVerilog
verdict (`tools/formal_equivalence.py`) grades the final deliverable against
golden. Neither model sees the golden design. All calls went to gpt-6-luna at
xhigh on the SDC gateway (Responses API, streamed). Each job's record is in
`<run>/editor/<module>/`; `EDITOR.json` has one row per job, and
`EDITOR-CACHE.md` has the token use.

| run | module | reviews: pass / failing testpoints | final pass · fail · abstain of N | trials | hours | verdict |
|---|---|---|---|---|---|---|
| luna12 | fpu_exceptions | 99/283 → 136/1 → 136/0 | 136 · 1 · 6 of 143 | 11 | 4.2 | function_fail |
| luna12 | i2c_master_bit_ctrl | 77/272 → 77/251 → 78/108 → 77/49 ¹ | 77 · 11 · 15 of 103 | 16 | 3.7 | function_fail |
| luna12 | i2c_master_byte_ctrl | 62/321 → 69/273 → 72/270 → 72/270 | 72 · 4 · 12 of 88 | 8 | 6.9 | function_fail |
| luna12 | or1200_dc_fsm | 66/35 → 66/29 → 69/0 | 69 · 8 · 3 of 80 | 10 | 1.7 | function_fail |
| luna12 | or1200_sb | 61/43 → 64/12 | 64 · 0 · 4 of 68 | 7 | 1.5 | equivalence_error ² |
| luna13 | fpu_exceptions | 127/6 → 132/0 | 132 · 1 · 5 of 138 | 1 | 0.6 | function_fail |
| luna13 | i2c_master_bit_ctrl | 71/254 → 78/261 → 78/206 → 78/206 | 78 · 13 · 32 of 123 | 16 | 6.4 | function_fail |
| luna13 | i2c_master_byte_ctrl ³ | 73/90 → 71/119 ¹ | 71 · 6 · 20 of 97 | 1 (+14) | 2.2 | function_fail |
| luna13 | or1200_dc_fsm | 76/20 → 84/0 | 84 · 0 · 0 of 84 | 2 | 0.5 | function_fail |
| luna13 | or1200_sb | 28/154 → 28/154 → 26/154 → 65/2 ¹ | 65 · 0 · 1 of 66 | 10 | 2.2 | equivalence_error ² |
| luna14 | fpu_exceptions ³ | 131/72 → 131/73 → 131/72 | 131 · 3 · 2 of 136 | 12 (+8) | 3.9 | function_fail |
| luna14 | i2c_master_bit_ctrl | 98/292 → 98/283 → 100/190 → 96/107 ¹ | 96 · 4 · 11 of 111 | 18 | 6.2 | function_fail |
| luna14 | i2c_master_byte_ctrl | 73/260 → 76/227 → 65/227 → 59/210 ¹ | 59 · 24 · 15 of 98 | 10 | 6.7 | function_fail |
| luna14 | or1200_dc_fsm | 65/12 → 74/4 | 74 · 0 · 5 of 79 | 14 | 2.0 | function_fail |
| luna14 | or1200_sb | 28/135 → 31/128 → 31/128 → 31/128 | 31 · 10 · 25 of 66 | 8 | 2.2 | pass (induction) ⁴ |
| luna15 | fpu_exceptions | 128/76 → 128/76 → 128/76 → 128/76 | 128 · 6 · 9 of 143 | 4 | 2.9 | function_fail |
| luna15 | i2c_master_bit_ctrl | 91/296 → 96/297 → 96/296 → 98/299 | 98 · 0 · 8 of 106 | 20 | 4.7 | function_fail |

A review is one run of the shipped suite; the first scores the generated RTL. A
job stops early when a review has no failing requirement or no failing
testpoint. Every function_fail is a bounded sequential counterexample (`bounded_seq`).

¹ Passing fell between two reviews: the defect described below.
² The checker could not import the RTL's FIFO memory (`fifo_mem`, a `$mem_v2`
cell) into its SAT database. This is an instrument failure, not a verdict.
³ Resumed; the trials in brackets are the killed attempt's. See `RESUME.md` in
the job's directory. luna13 byte_ctrl's resume started from the wrong RTL.
⁴ The generated RTL kept the specification's `ifdef OR1200_SB_IMPLEMENTED`
and wrote a pass-through `else` branch. The benchmark leaves that macro
undefined, so golden is a pass-through too, and the two are equivalent. This
run's checks were written against a buffering reference model and fail it on
10 requirements. The pass comes from the configuration, not from the repair loop.

## What it shows

- **No repair reached golden** except luna14 sb, by the route in ⁴.
- **Passing the shipped set does not imply equivalence.** Four jobs end with
  zero failing testpoints and still fail equivalence: luna12 and luna13 fpu,
  and luna12 and luna13 dc_fsm. luna13 dc_fsm passes all 84 of its
  requirements. A design that satisfies every shipped check yet differs from
  golden is a direct instance of blindness. This one is found by the editor
  rather than by the population.
- **The editor can hand back a design its own ratchet rejected.** A commit
  latches only when passing requirements rise. `RTLEditor.chat` then ends with
  `restore_best()`, and `note_best` records every judged commit BEFORE the
  latch decision (`eda_agent/rtl_editor.py:1995`). The design the round started
  from is never recorded. A round whose candidates were all rejected therefore
  returns the best of them, even when it is worse than the input. Passing falls
  between reviews in 5 of 17 jobs (6 times; ¹). It also explains the two
  rounds of luna13 byte_ctrl's first attempt that latched nothing yet changed
  the RTL: each returned a rejected candidate that tied at 73. **Fixed on this
  branch after these jobs ran:** the judge now records the starting design
  before the first commit, and since ties do not overwrite, a round that latches
  nothing returns its input. All 17 jobs above ran without the fix.

## Attempts that did not reach a verdict

- **2026-10-12T21:35Z, SDC `BUDGET_EXCEEDED`:** this stopped luna12 fpu,
  luna14 fpu and luna13 bit_ctrl mid-run. All three were set aside and run
  again from scratch, and their post-crash `interface_fail` verdicts are
  artifacts.
- **2026-10-13T10:53Z, stopped by choice** to fit the $6 budget: the two fpu
  jobs (`EDITOR-CACHE.md`). Both ran again on the expanded budget.
- **2026-10-14T12:26Z, SDC overload:** killed luna14 fpu in round 1; resumed.
- **2026-10-15T01:15Z, machine reboot:** killed luna13 byte_ctrl in round 2;
  resumed.

The 17 records took 58.7 hours of job time. Most of it went to simulating the
suite and deciding on the recording, not to model calls.
