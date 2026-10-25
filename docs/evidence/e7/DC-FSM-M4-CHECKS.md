# dc_fsm's M4: why no check catches it, in any corpus

M4 is `biu_read` gated by load. Golden raises `biu_read` in a store's miss-evaluation cycle:
`biu_read = hitmiss_eval & tagcomp_miss | ~hitmiss_eval & load`. The designs do not
(`DC-FSM-FINAL-MODES.md`: 33% of the luna14 final's remaining disagreement with golden). Figures
come from `e7_behaviour/dc_fsm_m4_checks.py`, written to `DC-FSM-M4-CHECKS.json`.

## The spec invites it

Four behavioural sentences mention `biu_read`. Only the formula implies a read request during a
store's miss evaluation.
- Two sentences frame it as a load-miss signal: "For a non-cache-inhibited load miss, biu_read
  is asserted", and "If the access is a cacheable load miss, biu_read is asserted…".
- One contrasts it with stores: "…while biu_write is asserted during write-through store
  processing".
- "The combined output biu_read is asserted when the FSM is evaluating a miss and tagcomp_miss=1,
  or when hit/miss evaluation is complete and a refill load sequence is active." This is golden.

## How the checks are made

- **The author never sees the reference model's code or behaviour.** It writes one check per
  requirement from:
  - the requirement and its normalised form;
  - the port contract;
  - the spec;
  - the requirements it names;
  - in a repair round, its own previous check.
  A must-pass gate against a "witness" implementation was removed earlier. It had been measured
  making checks agree with the witness (`specflow/refmodel/oracle_gen.py`).
- **Shipping is decided by a population.** That is 7 designs written independently by the same
  generator from the requirements (`specflow/population/`). A check that a majority of them fails
  is dropped as presumed wrong: "no body a majority of the population convicts".
- **The reference model is then repaired against the shipped checks.**

## Per corpus, the check that restates the formula

| corpus | check | written as | population convicted | fate |
|---|---|---|---|---|
| luna12 | REQ-0033 | golden's formula, with a timing-window bug | 7 of 7, all on the window bug | dropped |
| luna13 | REQ-0031 | first body: formula with the window bug; the shipped body narrows "evaluating a miss" to `load == 1` | 7 of 7 (first body) | first dropped; the narrowed one shipped |
| luna14 | REQ-0032 | **golden's formula, correct** | **6 of 7, at a store's miss evaluation** | **dropped by the majority rule** |

How common M4 is: luna14's correct check, replayed on every corpus's designs.

| corpus | reference model | population designs with M4 |
|---|---|---|
| luna12 | correct | 6 of 7 |
| luna13 | M4 | 7 of 7 |
| luna14 | M4 | 6 of 7 |

12 of the 15 RTL designs fitted in `qualitative/or1200_dc_fsm.md` carry it too.

## What this shows

- **M4 is the generator's near-universal reading.** It appears in 19 of 21 population designs,
  2 of 3 reference models and 12 of 15 RTL designs. The spec's prose invites it.
- **Every corpus ends with no shipped check that catches it, by three routes:**
  - in luna14 the check was written correctly, and dropped because most of the population shares
    the misreading;
  - in luna12 and luna13 the formula check carried a window bug that convicts every design;
  - in luna13 the shipped variant writes the misreading into its code.
- **Majority vote over same-model readings drops the correct minority reading.** This is the
  same failure as the consensus latch on a defect the peers share. The population exists to catch
  over-strict checks, which it does: it drops the window-bugged checks. It cannot tell an
  over-strict check from a correct one that most readers get wrong.
- **A check that convicts nearly the whole population on one clause is the case worth
  arbitrating, not dropping.** luna14's REQ-0032 would have been decided by the same narrow judge
  that keeps dc_fsm luna14's cache-inhibit fix.
