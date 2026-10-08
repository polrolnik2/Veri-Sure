# Three reps of the five-module E2E run

Each module was run end to end three times from S1 with an empty cache, under
one configuration: luna7's authored contracts, GPT-6-Luna at xhigh, population
7, `--admit-pool --cover --cell-budget 60`, majority shipping rule, no RTL
Editor. Pipeline code is 9cdce30 for reps 2 and 3 and for luna15; rep 1
(luna12) ran on dbc3676, and the only pipeline change between the two that
moves a score is a30e279, applied below to luna12's bit_ctrl as its offline
re-score (27/87 -> 26/85).

| module | rep 1 | rep 2 | rep 3 |
|---|---|---|---|
| fpu_exceptions, i2c_master_bit_ctrl | luna15 | luna13 | luna14 |
| i2c_master_byte_ctrl, or1200_dc_fsm, or1200_sb | luna12 | luna13 | luna14 |

luna12's fpu and bit_ctrl were cache-seeded (luna7's and luna11's
`agent_io`), so they are not independent samples; they are listed under each
table as `seeded` and left out of the means. Every byte_ctrl hand-bound audit
here is the one taken after 5fe1601 + ca6b7c6.

Span is over behavioural requirements; blindness over the population's
disagreement cells; the audit is the share of judgeable shipped checks that
convict the known-good design (raw: golden as it is; hand-bound: golden with
its internals bound to the contract's probes, `golden_bind/`); accepts is
how many population designs pass the whole shipped set.

### fpu_exceptions

| rep | run | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped |
|---|---|---|---|---|---|---|---|
| 1 | luna15 | 90.7% (78/86) | 16.7% (18/108) | 59.5% (44/74) | 59.5% (44/74) | 6 of 7 | 285 → 143 |
| 2 | luna13 | 90.2% (74/82) | 34.0% (17,467/51,426) | 65.7% (46/70) | 65.7% (46/70) | 3 of 7 | 362 → 139 |
| 3 | luna14 | 85.9% (73/85) | 10.8% (74/687) | 60.6% (43/71) | 60.6% (43/71) | 1 of 7 | 329 → 138 |
| mean (range) | | **88.9%** (85.9–90.7) | **20.5%** (10.8–34.0) | **61.9%** (59.5–65.7) | **61.9%** (59.5–65.7) | | |
| seeded | luna12 | 90.7% (78/86) | 6.7% (2,200/32,770) | 66.2% (49/74) | 66.2% (49/74) | 4 of 7 | 352 → 143 |

### i2c_master_bit_ctrl

| rep | run | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped |
|---|---|---|---|---|---|---|---|
| 1 | luna15 | 84.0% (100/119) | 73.9% (31,087/42,065) | 13.5% (5/37) | 12.9% (12/93) | 1 of 7 | 338 → 108 |
| 2 | luna13 | 89.8% (106/118) | 31.7% (10,999/34,644) | 21.6% (8/37) | 26.7% (24/90) | 0 of 6 | 285 → 124 |
| 3 | luna14 | 89.9% (107/119) | 73.7% (36,123/48,987) | 19.4% (7/36) | 16.5% (16/97) | 0 of 7 | 345 → 111 |
| mean (range) | | **87.9%** (84.0–89.9) | **59.8%** (31.7–73.9) | **18.2%** (13.5–21.6) | **18.7%** (12.9–26.7) | | |
| seeded | luna12 | 82.1% (96/117) | 65.0% (36,329/55,857) | 27.3% (9/33) | 30.6% (26/85) | 0 of 7 | 346 → 104 |

### i2c_master_byte_ctrl

| rep | run | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped |
|---|---|---|---|---|---|---|---|
| 1 | luna12 | 75.5% (83/110) | 13.3% (7,603/57,110) | 0.0% (0/7) | 36.5% (27/74) | 0 of 7 | 304 → 88 |
| 2 | luna13 | 82.1% (92/112) | 6.4% (3,441/53,740) | 0.0% (0/3) | 23.3% (17/73) | 0 of 7 | 314 → 102 |
| 3 | luna14 | 87.3% (96/110) | 7.7% (3,773/48,918) | 0.0% (0/8) | 32.6% (28/86) | 0 of 7 | 303 → 99 |
| mean (range) | | **81.6%** (75.5–87.3) | **9.1%** (6.4–13.3) | **0.0%** (0.0–0.0) | **30.8%** (23.3–36.5) | | |

### or1200_dc_fsm

| rep | run | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped |
|---|---|---|---|---|---|---|---|
| 1 | luna12 | 87.7% (71/81) | 94.0% (438/466) | 12.5% (1/8) | 3.4% (2/59) | 4 of 7 | 232 → 80 |
| 2 | luna13 | 94.0% (78/83) | 11.8% (12/102) | 0.0% (0/8) | 4.4% (3/68) | 6 of 7 | 207 → 84 |
| 3 | luna14 | 89.0% (73/82) | 93.2% (3,411/3,661) | 0.0% (0/8) | 4.3% (3/69) | 4 of 7 | 244 → 79 |
| mean (range) | | **90.2%** (87.7–94.0) | **66.3%** (11.8–94.0) | **4.2%** (0.0–12.5) | **4.0%** (3.4–4.4) | | |

### or1200_sb

| rep | run | span | blindness | audit raw | audit hand-bound | accepts | pool → shipped |
|---|---|---|---|---|---|---|---|
| 1 | luna12 | 94.3% (50/53) | 99.4% (8,654/8,708) | 0.0% (0/3) | 0.0% (0/3) | 5 of 7 | 212 → 68 |
| 2 | luna13 | 93.0% (53/57) | 92.1% (7,844/8,518) | 20.0% (1/5) | 20.0% (1/5) | 3 of 7 | 211 → 66 |
| 3 | luna14 | 96.3% (52/54) | 39.3% (3,264/8,306) | 0.0% (0/5) | 0.0% (0/5) | 2 of 7 | 214 → 66 |
| mean (range) | | **94.5%** (93.0–96.3) | **76.9%** (39.3–99.4) | **6.7%** (0.0–20.0) | **6.7%** (0.0–20.0) | | |

## What holds across reps

- **Span is stable, and meets the 0.90 target on sb in every rep, fpu in two
  and dc_fsm in one -- never on bit_ctrl or byte_ctrl.** Per-module means: sb 94.5%, dc_fsm 90.2%, fpu 88.9%,
  bit_ctrl 87.9%, byte_ctrl 81.6%; no module's range is wider than 12 points.
- **The hand-bound audit is stable per module, and it is not near zero where
  it matters.** fpu 61.9% (59.5–65.7), byte_ctrl 30.8% (23.3–36.5),
  bit_ctrl 18.7% (12.9–26.7), dc_fsm 4.0% (3.4–4.4), sb 0–1 of 5. fpu is
  the highest in every rep; byte_ctrl and bit_ctrl trade second place.
- **Blindness is not a stable per-module number.** Its denominator, the
  cells on which the population disagrees, moves by up to 36x between reps
  (dc_fsm: 102, 466 and 3,661 cells; sb 39.3% to 99.4%). It measures the
  population as much as the checks, so it is reported with its denominator
  and not averaged into a quality claim.
- **No population design passes byte_ctrl's whole shipped set in any rep,**
  and at most one passes bit_ctrl's; fpu accepts 1 to 6, dc_fsm and sb 2 to 6.

## Where golden's convictions come from

For each requirement whose shipped check convicts golden (hand-bound), how the
population judges it: **shared** = every deciding design passes it, a
misreading the population shares and no population-based rule can see;
**minority** = one to three designs fail it too, and the strict-majority rule
shipped it.

| module | rep 1 | rep 2 | rep 3 | shared : minority, all reps |
|---|---|---|---|---|
| fpu_exceptions | 52 (50 : 2) | 55 (18 : 37) | 52 (49 : 3) | 117 : 42 |
| i2c_master_bit_ctrl | 14 (11 : 3) | 25 (14 : 11) | 17 (13 : 4) | 38 : 18 |
| i2c_master_byte_ctrl | 27 (3 : 24) | 17 (1 : 16) | 28 (11 : 17) | 15 : 57 |
| or1200_dc_fsm | 2 (1 : 1) | 3 (2 : 1) | 3 (3 : 0) | 6 : 2 |
| or1200_sb | 0 | 1 (1 : 0) | 0 | 1 : 0 |

fpu and bit_ctrl convict golden mostly on readings the whole population
shares (luna13's fpu is the exception, 37 of 55 minority). byte_ctrl is the
reverse: 57 of 72 convictions are checks that some designs also fail. A
stricter shipping rule would remove those, at a cost in span and blindness
that the saved pools can measure offline, as the selection-rule triple did
for luna7's bit_ctrl; that has not been run.

## Cost and time

OpenRouter (recorded per call): luna12 $7.82, luna13 $10.63, luna14 $9.15,
luna15 $5.11. OpenRouter's credits ran out at about 06:40Z on 2026-10-07 and
the remaining stages went to the SDC gateway, which reports tokens, not cost:
125 calls on luna13 (3.4M prompt, 1.3M completion tokens) and 866 on luna14
(21.3M, 6.6M). Last-attempt wall times run from 1:12 (luna14 sb) to 11:48
(luna13 byte_ctrl).

## Found while running them

- **Population tables were rebuilt seven times for luna13's byte_ctrl** --
  three in the pipeline (oracle stage, cover, scorecard) and four in scoring
  (the pipeline set's score, the after-oracles cover and score, the hand-bound
  score) -- and nothing bounds the time one body may take. One body, luna13's REQ-0024#2,
  scans from every idle-with-request cycle to `cmd_ack`; on a design that
  never acks every window runs to the end of the trace, and it cost three to
  four hours of one pass. Two hardening items: compute the tables once per run
  and share them, and give a body a time budget per trace.
- **The golden replay's recording of a reference's internals went through
  the probe-width refusal**, which blanked byte_ctrl's `reg [3:0] core_cmd`
  wherever a contract also declared a one-bit probe of that name, and with it
  six bound probes (5fe1601); the follow-up stops a name that resolves to an
  instance from failing every testpoint (ca6b7c6). luna12 and luna14 byte_ctrl
  were re-audited; no earlier verdict changed.
- **The transport-failure message misdiagnoses a refused connection as a
  gateway timeout.** After the session restart moved the agent proxy's port,
  luna13 byte_ctrl's still-running job named the old one; its calls failed in
  about 29 seconds while the message blamed a ~300-second generation ceiling.
