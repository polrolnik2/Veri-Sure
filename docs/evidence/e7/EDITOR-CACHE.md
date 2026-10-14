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

## Update, 2026-10-14 (interim)

The remaining jobs ran on an expanded budget, and `editor-usage/` now holds one log
per attempt: `<run>-<module>.jsonl` is the run that reached (or is reaching) its
verdict, and a `-<timestamp>` suffix marks an attempt that did not --
`-20261013T1053Z` the two fpu jobs stopped by choice above (the table's rows), and
`luna14-fpu_exceptions-20261014T1226Z` the attempt an SDC overload killed, which was
then resumed from its round-1 RTL (`luna14/editor/fpu_exceptions/RESUME.md`). The
three byte_ctrl logs are snapshots of jobs still running; the table is regenerated
over every attempt when they finish. At the last snapshot, 2,922 calls over all
attempts were 89.3% cached.
