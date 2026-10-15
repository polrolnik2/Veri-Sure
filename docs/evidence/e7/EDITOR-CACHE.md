# RTL Editor prompt-cache hit rate

Measured on 2026-10-13 with a $6 SDC budget: the RTL Editor (generate, then
repair against the shipped set) on four rep corpora, gpt-6-luna at xhigh over
the Responses API. `e7_rtl_editor.py` writes one line per model call to
`usage.jsonl` (b42f33f); those logs are in `editor-usage/`. The two bit_ctrl
jobs ran to their ChipVerilog verdicts (both function_fail); the two fpu jobs
were stopped part-way by choice once it was clear the budget could finish only
two jobs, and their calls count here.

| job | state | calls | input | cached | hit | repair-only hit | est $ |
|---|---|---|---|---|---|---|---|
| luna12/fpu_exceptions | stopped by choice, to save budget | 58 | 6.2M | 5.4M | 87.7% | 87.9% | 0.21 |
| luna13/i2c_master_bit_ctrl | ran to verdict | 411 | 68.0M | 60.6M | 89.2% | 89.2% | 2.04 |
| luna14/i2c_master_bit_ctrl | ran to verdict | 466 | 75.2M | 67.3M | 89.5% | 89.5% | 2.17 |
| luna14/fpu_exceptions | stopped by choice, to save budget | 79 | 16.8M | 14.7M | 87.8% | 88.0% | 0.51 |
| **all** | | **1014** | 166.2M | 148.1M | **89.1%** | 89.2% | 4.93 |

generate: 5 calls, 16.9% cached; output 1.63M tokens total
per repair call: {'<50%': 7, '50-90%': 23, '>=90%': 881, '0%': 98}
edit-r0: 499 calls, 89.2% cached, avg input 183k
edit-r1: 321 calls, 89.3% cached, avg input 165k
edit-r2: 189 calls, 88.7% cached, avg input 115k

(`edit-rN` is the repair inside round N; the last review needs no call.)

- **89% of the editor's input tokens were served from the prompt cache**,
  against 91% for the pipeline stages (luna12-15, 36,132 calls). The repair loop
  resends a long, stable conversation, so nearly every call shares its prefix with
  the one before; the rate holds from round to round (88.7-89.3%).
- The misses are concentrated: 98 of 1,009 repair calls hit nothing (a call that
  starts a fresh conversation prefix), while 881 hit 90% or more.
- Generation is one call per job and cannot hit the cache (5 calls, 17%).
- The cost is input, not output: prompts grow with the conversation (115-183k
  tokens per repair call on average by round; over 300k late in a round) while
  output averages ~1.6k tokens per call. A finished bit_ctrl job is ~400-470
  calls, ~70M input tokens and ~0.7M output.
- `est $` prices the calls at twice the OpenRouter Flex rates fitted exactly on
  24,563 recorded calls ($0.0625 / $0.00625 / $0.25 per M uncached-in / cached-in /
  out); SDC reports no cost, so the true figure may be lower. On that estimate
  the ~11% of input that missed the cache is ~46% of the cost.

## Final, 2026-10-15: every logged attempt

The remaining jobs ran on an expanded budget. `editor-usage/` holds one log per
attempt: `<run>-<module>.jsonl` is the run that reached its verdict, and a
`-<timestamp>` suffix marks one that did not -- `-20261013T1053Z` the two fpu
jobs stopped by choice above, `luna14-fpu_exceptions-20261014T1226Z` the attempt
an SDC overload killed, and `luna13-i2c_master_byte_ctrl-20261015T0117Z` the
attempt a machine reboot killed. The last two were resumed (`RESUME.md` in each
job's `<run>/editor/<module>/`), so their "ran to verdict" rows are the resumes
alone. The nine jobs that finished on 2026-10-12, before b42f33f, have no log:
dc_fsm and sb in all three reps, luna13 fpu, and luna15 fpu and bit_ctrl.

| job | state | calls | input | cached | hit | repair-only hit | est $ |
|---|---|---|---|---|---|---|---|
| luna12/fpu_exceptions | ran to verdict | 223 | 63.8M | 57.9M | 90.6% | 90.7% | 1.62 |
| luna12/i2c_master_bit_ctrl | ran to verdict | 389 | 54.4M | 48.4M | 88.9% | 88.9% | 1.55 |
| luna12/i2c_master_byte_ctrl | ran to verdict | 566 | 83.9M | 74.8M | 89.2% | 89.2% | 2.34 |
| luna12/fpu_exceptions-20261013T1053Z | stopped by choice, to save budget | 58 | 6.2M | 5.4M | 87.7% | 87.9% | 0.21 |
| luna13/i2c_master_bit_ctrl | ran to verdict | 411 | 68.0M | 60.6M | 89.2% | 89.2% | 2.04 |
| luna13/i2c_master_byte_ctrl | ran to verdict (resume) | 78 | 5.9M | 5.1M | 87.1% | 87.1% | 0.25 |
| luna13/i2c_master_byte_ctrl-20261015T0117Z | killed by machine reboot, resumed | 321 | 45.6M | 38.4M | 84.2% | 84.2% | 1.64 |
| luna14/fpu_exceptions | ran to verdict (resume) | 215 | 46.8M | 41.3M | 88.3% | 88.3% | 1.41 |
| luna14/i2c_master_bit_ctrl | ran to verdict | 466 | 75.2M | 67.3M | 89.5% | 89.5% | 2.17 |
| luna14/i2c_master_byte_ctrl | ran to verdict | 577 | 83.6M | 74.9M | 89.5% | 89.5% | 2.26 |
| luna14/fpu_exceptions-20261013T1053Z | stopped by choice, to save budget | 79 | 16.8M | 14.7M | 87.8% | 88.0% | 0.51 |
| luna14/fpu_exceptions-20261014T1226Z | crashed (SDC overload), resumed | 187 | 53.0M | 47.5M | 89.6% | 89.6% | 1.40 |
| **all** | | **3570** | 603.3M | 536.4M | **88.9%** | 88.9% | 17.38 |

generate: 14 calls, 22.9% cached; output 4.64M tokens total
per repair call: {'>=90%': 3084, '50-90%': 86, '<50%': 31, '0%': 355}
edit-r0: 1884 calls, 89.2% cached, avg input 203k
edit-r1: 1075 calls, 88.3% cached, avg input 147k
edit-r2: 597 calls, 89.0% cached, avg input 105k

- **The rate held at 88.9%** over 3,570 calls and 603M input tokens, against
  89.1% on the first 1,014. Per job it is 87-91%; the one outlier is the
  rebooted byte_ctrl attempt at 84.2%.
- The misses are still concentrated: 355 of 3,556 repair calls hit nothing,
  while 3,084 hit 90% or more.
- The ~11% of input that missed the cache is $8.36 of the $17.38 estimate
  (48%). Cached input is $6.71 and output is $2.32 (1.3k tokens per call on
  average).
