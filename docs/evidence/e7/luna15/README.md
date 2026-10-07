# luna15 — fresh rep 1 for fpu_exceptions and i2c_master_bit_ctrl

luna12's fpu and bit_ctrl runs were cache-seeded (luna7's / luna11's `agent_io`),
so their upstream stages were not independent samples. These two runs are the
same configuration from S1 with an empty cache: luna7's authored contracts,
GPT-6-Luna Flex at xhigh (OpenRouter), population 7, `--admit-pool --cover
--cell-budget 60`, majority shipping rule, no RTL Editor; code at 9cdce30.
Scored by golden replay of the shipped set and the hand-bound audit
(`../golden_bind/`).

`summary.json` is the table; `recorded_cost_usd` sums the cost each call's
metadata records. The cross-rep comparison is in `../REPS.md`.
