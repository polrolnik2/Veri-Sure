# luna13 — rep 2, five modules end to end

Same configuration as luna12 (rep 1) and luna14 (rep 3), from S1 with an empty
cache: luna7's authored contracts, GPT-6-Luna at xhigh, population 7,
`--admit-pool --cover --cell-budget 60`, majority shipping rule, no RTL Editor.
Pipeline code is 9cdce30 throughout; the jobs relaunched on 150bfd0 and d9d2ef2
resumed from their cache, and those commits change only audit-side evidence
files. Scored by golden replay of the shipped set and the hand-bound audit
(`../golden_bind/`).

| module | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped (majority-excluded) | run time (last attempt) |
|---|---|---|---|---|---|---|---|
| fpu_exceptions | **90.2%** (74/82) | 34.0% (17,467/51,426) | 65.7% (46/70) | 65.7% (46/70) | 3 of 7 | 362 → 139 (74) | 11:24 |
| i2c_master_bit_ctrl | 89.8% (106/118) | 31.7% (10,999/34,644) | 21.6% (8/37) | 26.7% (24/90) | 0 of 6 | 285 → 124 (75) | 5:54 |
| i2c_master_byte_ctrl | 82.1% (92/112) | **6.4%** (3,441/53,740) | 0/3 | 23.3% (17/73) | 0 of 7 | 314 → 102 (125) | 11:48 |
| or1200_dc_fsm | **94.0%** (78/83) | 11.8% (12/102) | 0/8 | **4.4%** (3/68) | 6 of 7 | 207 → 84 (60) | 5:08 |
| or1200_sb | **93.0%** (53/57) | 92.1% (7,844/8,518) | 20.0% (1/5) | 20.0% (1/5) | 3 of 7 | 211 → 66 (48) | 5:03 |

## Read before comparing

- **bit_ctrl's population is 6, and the run produced no witness.** The
  after-oracles scoring fell back to the reference model; the hand binding was
  extended for this run's probes (150bfd0).
- **byte_ctrl took five attempts.** Two were queue restarts at 00:26Z and
  00:47Z, one exited at once when OpenRouter's credits ran out (06:51Z), and
  the last ran from 06:53Z on the SDC gateway. Its 125 SDC calls are counted
  under `uncosted_calls` in `summary.json` (3.4M prompt, 1.3M completion
  tokens); SDC reports tokens, not cost. `recorded_cost_usd` sums the
  OpenRouter calls: $10.63 for the rep.
- **byte_ctrl's reference-model call failed twice in transit** at 15:46Z. The
  session restart at about 13:43Z had moved the agent proxy to a new port, and
  the running job still named the old one. A localhost relay from the old port
  fixed it in place; the third attempt went through. The pipeline's message
  ("generates for longer than the ~300s ceiling") was a misdiagnosis: the
  attempts failed in about 29 seconds.
- **byte_ctrl's last attempt spent most of its 11:48 off the model.** One
  oracle body, REQ-0024#2, opens a window at every idle cycle with a pending
  request and scans to `cmd_ack`; on a design that never acks, every window
  runs to the end of the trace. The population tables were built three times
  in the run (oracle stage, cover, scorecard) and three more in scoring, with
  that body costing up to about four hours of one pass.
- **byte_ctrl's audit** ran on ca6b7c6. This contract declares neither
  `core_cmd` nor `bit_controller` as a probe, so the internals-recording bug
  that ca6b7c6 fixes could not touch it.

## Golden convictions against the population

How the population judges each requirement whose check convicts golden
(hand-bound traces): **shared** = every design that decides it passes (a
misreading the population shares), **minority** = one to three designs fail,
of seven (six for bit_ctrl) -- shipped under the strict-majority rule.

| module | convicting requirements | shared | minority |
|---|---|---|---|
| fpu_exceptions | 55 | 18 | 37 |
| i2c_master_bit_ctrl | 25 | 14 | 11 |
| i2c_master_byte_ctrl | 17 | 1 | 16 |
| or1200_dc_fsm | 3 | 2 | 1 |
| or1200_sb | 1 | 1 | 0 |

`corpora/` holds each run's packed corpus; `results/<module>/` the scoring JSON
and logs. The cross-rep comparison is in `../REPS.md`.
