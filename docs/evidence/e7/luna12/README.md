# luna12 — five modules end to end, rep 1

Total model spend for the rep: $7.82 (OpenRouter, GPT-6-Luna Flex).

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
| i2c_master_byte_ctrl | 75.5% (83/110) | 13.3% (7,603/57,110) | 0/7 | 36.5% (27/74)¹ | 304 → 88 (122) | 8:41 (last attempt) |

¹ Re-audited after 5fe1601 + ca6b7c6; it was 32.7% (17/52). The golden replay's
recording of the reference's internals went through the probe-width refusal,
and this contract declares a one-bit probe `core_cmd` beside the design's
`reg [3:0] core_cmd`: the register was blanked, and with it the six probes
the hand binding derives from it, so 22 checks abstained. Every earlier
verdict is unchanged; the 22 newly judged checks add 10 convictions
(REQ-0003, 0038, 0051, 0053, 0058, 0060, 0076, 0085, 0108, 0115).

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
- **byte_ctrl** needed five attempts at its oracle stage: after a session
  restart the network path cut long requests (six transport failures, the
  build gave up on resumable state); two provider outages ("Flex processing
  is temporarily unavailable", a bare `finish_reason='error'`) each aborted
  the stage and the autorun re-entered it; and three container reboots
  killed the process. Every attempt resumed from the cache, so no call was
  paid twice; e465fd8 now waits out a fast-failing outage per call instead
  of re-entering the stage. Its span is the lowest of the five: the majority
  rule removed 122 of 304 bodies, and 27 behavioural requirements were left
  with none.
- The probe stage minted probes no design can implement for byte_ctrl
  (`contentreference`, from citation tokens left in the spec text, and two
  "is instantiated" structural probes) and one for sb (`or1200_sb_fifo`);
  the hand bindings were extended for them (ec33357).

## Would the latency instrument fix fpu? (offline, after the rep)

`refmodel.latency.fragile` delays the observables of a passing trace by one
and two clocks on the run's own witness and flags a check that then fails --
golden-free. Made decisive at shipping on fpu's 352-body pool:

| rule | span | blind | audit (raw = hand-bound) |
|---|---|---|---|
| pipeline (majority) | 90.7% | 6.7% | 49/74 = 66.2% |
| majority + drop latency-fragile | 87.2% | 34.9% | 44/70 = 62.9% |
| drop latency-fragile only | 91.9% | 0.7% | 50/75 = 66.7% |

It flags 69 of the 172 bodies that convict golden and 19 of the 180 that do
not. Golden is not the witness delayed by a register stage: the difference also
runs through the 60 internal probes and the enable-gated registers, which the
lag does not move. Not a fix; not adopted.

Rep-1 hand-bound conviction rows by module: fpu 59, bit_ctrl 30 (2 on the
power-on first row), byte_ctrl 17 (27 after the re-audit, ¹ above), dc_fsm 2, sb 0.

**After a30e279** (a preponed trace is not judged on its power-on row),
re-scored offline: bit_ctrl hand-bound audit 27/87 -> 26/85 = 30.6%; the other
modules had no conviction on that row.
