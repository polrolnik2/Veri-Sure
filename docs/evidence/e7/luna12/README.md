# luna12 — five modules end to end, rep 1

Pipeline from S1 through the reference model on dbc3676 (contracts: luna7's
authored `input_contract.json`; GPT-6-Luna Flex, effort xhigh; population 7;
`--admit-pool --cover --cell-budget 60`; shipping rule: no body a **majority**
of the population convicts). **No RTL Editor** (dropped by the user for this
rep). After each run: golden replay + triple of the shipped set, and the
hand-bound audit (`e7_bind_golden.py`). Golden is only RUN, except the
audit-only bindings in `../golden_bind/`.

| module | span | blindness | audit raw | audit hand-bound | pool → shipped (majority-excluded) | run time |
|---|---|---|---|---|---|---|
| fpu_exceptions | **90.7%** (78/86) | **6.7%** (2,200/32,770) | 66.2% (49/74) | 66.2% (49/74) | 352 → 143 (67) | 6:15 |
| i2c_master_bit_ctrl | 82.1% (96/117) | 65.0% (36,329/55,857) | 27.3% (9/33) | 31.0% (27/87) | 346 → 104 (130) | 4:31 |
| or1200_dc_fsm | 87.7% (71/81) | 94.0% (438/466) | 12.5% (1/8) | **3.4%** (2/59) | 232 → 80 (61) | 4:32 |
| or1200_sb | **94.3%** (50/53) | 99.4% (8,654/8,708) | **0/3** | **0/3** | 212 → 68 (50) | 6:30 |
| i2c_master_byte_ctrl | pending | | | | | |

`corpora/` holds each run's packed corpus (`e6_pack_corpus.py`: contract,
requirements, normalized forms, testplan, stimulus, coverage, probes, the
oracle set with its corpus, the shipped set, the population, the reference
model, the scorecard, sha256 of every file). `results/<module>/` holds the
scoring JSON and logs; `summary.json` is the table above.

## Read before comparing

- **bit_ctrl and fpu are cache-seeded.** Their run directories started with
  luna11's (bit_ctrl) and luna7's (fpu) `agent_io`, and `--resume-verified`
  replays every byte-identical prompt. Their upstream stages are therefore
  luna7's samples, not independent ones. Fresh rep-1 runs for both are
  prepared in `luna15/`; byte_ctrl, dc_fsm and sb are fresh.
- **fpu's audit is one latency reading.** The spec lists a chain of
  registered intermediate stages (`NaN_output_0`, `out_0`/`out_1`/`out_2`,
  then `out`); golden answers two cycles after its inputs, while all seven
  spec-derived designs and the checks answer after one, and the contract
  states no latency (`timing: {}`). The population agrees with itself (low
  blindness) and disagrees with golden (high audit).
- **sb's audit says little.** The golden build compiles the store buffer
  out (`OR1200_SB_IMPLEMENTED` is commented out in `or1200_defines.v`), so the
  reference is a pass-through and every probe is UNBOUND; 3 checks are
  judgeable on it.
- **dc_fsm's blindness is over 466 cells.** The population nearly agrees
  everywhere; few disagreements exist and almost none is separated.
- **bit_ctrl's blindness** is the pool's: after the majority rule removed 130
  of 346 bodies, the remainder separates 19,528 of 55,857 cells.
- **byte_ctrl** lost its oracle stage twice: after a session restart long
  requests were cut by the network path (six transport failures, the build
  gave up at 10:27 on resumable state), and a container reboot killed the
  resumed run. It is resuming from the cache.
- The probe stage minted probes no design can implement for byte_ctrl
  (`contentreference`, from citation tokens left in the spec text, and two
  "is instantiated" structural probes) and one for sb (`or1200_sb_fifo`);
  the hand bindings were extended for them (ec33357).
