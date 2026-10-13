# RTL Editor prompt-cache hit rate

Measured on 2026-10-13 with a $6 SDC budget: the RTL Editor (generate, then
repair against the shipped set) on four rep corpora, gpt-6-luna at xhigh over
the Responses API. `e7_rtl_editor.py` now writes one line per model call to
`usage.jsonl` (b42f33f); those logs are in `editor-usage/`. The two fpu jobs
were stopped part-way by choice once it was clear the budget could finish only
two jobs; their calls count here.

| job | state | calls | input | cached | hit | repair-only hit | est $ |
|---|---|---|---|---|---|---|---|
| luna12/fpu_exceptions | stopped by choice, to save budget | 58 | 6.2M | 5.4M | 87.7% | 87.9% | 0.21 |
| luna13/i2c_master_bit_ctrl | running | 298 | 53.5M | 48.1M | 89.8% | 89.8% | 1.52 |
| luna14/i2c_master_bit_ctrl | running | 357 | 60.2M | 54.0M | 89.7% | 89.7% | 1.70 |
| luna14/fpu_exceptions | stopped by choice, to save budget | 79 | 16.8M | 14.7M | 87.8% | 88.0% | 0.51 |
| **all** | | **792** | 136.7M | 122.2M | **89.4%** | 89.4% | 3.94 |

generate: 5 calls, 16.9% cached; output 1.20M tokens total
per repair call: {'<50%': 5, '50-90%': 17, '>=90%': 690, '0%': 75}
edit-r0: 499 calls, 89.2% cached, avg input 183k
edit-r1: 288 calls, 90.0% cached, avg input 157k

- **89% of the editor's input tokens were served from the prompt cache**,
  against 91% for the pipeline stages (luna12-15, 36,132 calls). The repair loop
  resends a long, stable conversation, so nearly every call shares its prefix with
  the one before.
- The misses are concentrated: 75 repair calls hit nothing (a call that starts a
  fresh conversation prefix), while 690 hit 90% or more.
- Generation is one call per job and cannot hit the cache (5 calls, 17%).
- The cost is input, not output: prompts grow with the conversation (157-183k
  tokens per repair call on average; over 300k late in a round) while output
  averages ~1.5k tokens per call.
- `est $` prices the calls at twice the OpenRouter Flex rates fitted exactly on
  24,563 recorded calls ($0.0625 / $0.00625 / $0.25 per M uncached-in / cached-in /
  out); SDC reports no cost, so the true figure may be lower.

Interim: the two bit_ctrl jobs are still running; this file is updated when they
finish.
