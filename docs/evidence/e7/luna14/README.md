# luna14 — rep 3, five modules end to end

Same configuration as luna12 (rep 1) and luna13 (rep 2), from S1 with an empty
cache: luna7's authored contracts, GPT-6-Luna at xhigh, population 7,
`--admit-pool --cover --cell-budget 60`, majority shipping rule, no RTL Editor.
Pipeline code is 9cdce30 throughout; the jobs relaunched on 150bfd0 and d9d2ef2
resumed from their cache, and those commits change only audit-side evidence
files. Scored by golden replay of the shipped set and the hand-bound audit
(`../golden_bind/`).

| module | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped (majority-excluded) | run time (last attempt) |
|---|---|---|---|---|---|---|---|
| fpu_exceptions | 85.9% (73/85) | 10.8% (74/687) | 60.6% (43/71) | 60.6% (43/71) | 1 of 7 | 329 → 138 (75) | 3:51 |
| i2c_master_bit_ctrl | 89.9% (107/119) | 73.7% (36,123/48,987) | 19.4% (7/36) | 16.5% (16/97) | 0 of 7 | 345 → 111 (109) | 5:57 |
| i2c_master_byte_ctrl | 87.3% (96/110) | **7.7%** (3,773/48,918) | 0/8 | 32.6% (28/86)¹ | 0 of 7 | 303 → 99 (107) | 5:25 |
| or1200_dc_fsm | 89.0% (73/82) | 93.2% (3,411/3,661) | 0/8 | **4.3%** (3/69) | 4 of 7 | 244 → 79 (47) | 5:49 |
| or1200_sb | **96.3%** (52/54) | 39.3% (3,264/8,306) | **0/5** | **0/5** | 2 of 7 | 214 → 66 (46) | 1:12 |

¹ Audited after 5fe1601 + ca6b7c6. The first audit read 23/61 = 37.7%: the
golden replay's recording of the reference's `reg [3:0] core_cmd` went through
the probe-width refusal (the contract also declares a one-bit probe
`core_cmd`), which blanked the six probes the hand binding derives from it.
No earlier verdict changed; the 25 newly judged checks add 5 convictions
(REQ-0020, 0047, 0058, 0060, 0110).

## Read before comparing

- **Two providers.** OpenRouter's credits ran out at about 06:40Z on
  2026-10-07; every model call after that went to the SDC gateway (`gpt-6-luna`,
  xhigh, streamed; a direct probe of the gateway answered as
  `gpt-6-luna-2026-09-22`, while the streamed calls' metadata records only the
  requested name).
  That covers the remaining stages of fpu, byte_ctrl and sb. Calls already in
  the cache replay regardless of provider. `recorded_cost_usd` in
  `summary.json` sums only the OpenRouter calls ($9.15 for the rep); SDC
  reports tokens, not cost, so its 866 calls are counted under
  `uncosted_calls` (21.3M prompt, 6.6M completion tokens).
- **bit_ctrl's population** was 6 before the 00:26Z restart and 7 after; the
  table is the 7.
- **byte_ctrl** was relaunched in error for about two minutes at 13:38Z after
  the disk filled (its audit had failed). It was stopped during preflight;
  the rewritten `contract.json` is byte-identical, and `shipped.json` is read
  from the scored copy in `after_oracles/` (the packed corpus has it too).

## Golden convictions against the population

How the population judges each check that convicts golden (hand-bound
traces): **shared** = every design that decides it passes (a misreading the
population shares), **minority** = one to three of seven fail (shipped under the
strict-majority rule).

| module | conviction rows | shared | minority |
|---|---|---|---|
| fpu_exceptions | 52 | 49 | 3 |
| i2c_master_bit_ctrl | 17 | 13 | 4 |
| i2c_master_byte_ctrl | 28 | 11 | 17 |
| or1200_dc_fsm | 3 | 3 | 0 |
| or1200_sb | 0 | — | — |

`corpora/` holds each run's packed corpus; `results/<module>/` the scoring JSON
and logs. The cross-rep comparison is in `../REPS.md`.
