# The loop converges — on the oracle set, away from the design

Result of iterating the RTL editor with Sonnet subagents until convergence, and
the reason to stop.

## The numbers

Same 90-oracle suite, same 224-testpoint stimulus at `hold=60`, same starting
candidate (`ChipVerilog/Result/codex/.../i2c_master_bit_ctrl_t1.v`), decided
against the benchmark's golden `i2c_master_bit_ctrl.v`.

| | passing | INVERTED | real | **agrees with golden** | broke | trials |
|---|---|---|---|---|---|---|
| baseline | 46 | 1 | 45 | 70/90 | 15 | — |
| **run 8** | 58 | 1 | 57 | **84/90** | 3 | 1/4 |
| **run 10** | **61** | 3 | 58 | **77/90** | 5 | 5/8 |
| GOLDEN | 60 | 0 | 60 | 90/90 | 0 | — |

**Run 10 scores above the reference design and is further from it.** It beats
run 8 on the loop's objective (61 vs 58 passing) while agreeing with golden on
*seven fewer* requirements (77 vs 84) and breaking two more that golden passes.
It spent five trials to run 8's one, and spent the extra four moving away.

## Why

`passing` and `correct` are different quantities, and the gap is the oracle
set's own errors. A check the **known-good design fails** is a wrong check, so a
candidate that *passes* it has been shaped to satisfy an error.

Run 10 passes three such checks. Two of them —

- **REQ-0030** "The arbitration-lost output `al` is asserted when a STOP condition…"
- **REQ-0095** "The module shall enable arbitration checking during the stable high phase…"

— are the pair that **convict golden**, i.e. proven written incorrectly. Run 8
failed them, correctly. Run 10 *satisfies* them, which is strictly worse: the
loop found edits that make a wrong specification true of the design.

That is the failure mode plan §12 predicted in the abstract ("the loop will be
asked to 'repair' a correct design toward 43 wrong demands"). This is it,
measured, with the direction of travel visible across two runs.

## What this means for the metric

`passing` alone cannot detect it — it goes **up** while the design gets worse.
`satisfiable.py` now prints both columns and refuses to let the pass rate stand
alone, warning explicitly when a candidate scores above the reference:

```
passing (the objective)           61       60
agrees with golden             77/90    90/90
passes what golden FAILS           3        0   [REQ-0006, REQ-0030, REQ-0095]
broke what golden passes           5        0   [REQ-0042, REQ-0048, ...]
```

## Stop

The goal was: iterate until the loop autonomously converges; stop if
requirements are proven written incorrectly and unsatisfiable.

Both conditions are met, and the second is met more strongly than "two checks
are wrong":

1. **The loop converges.** From 46 passing to 58 in a single trial (run 8),
   against a golden ceiling of 60, with no reference visible to the agent.
2. **REQ-0030 and REQ-0095 are proven written incorrectly** — they convict the
   known-good design, so no edit to any candidate can satisfy them *correctly*.
3. **Further iteration is actively harmful, not merely capped.** The loop does
   not stop at those checks; it deforms the design until they pass. More trials
   made the artifact worse by the only measure that is not the loop's own
   objective.

Continuing to iterate the *editor* cannot fix this. The defect is upstream, in
the oracle set — and repairing it needs the requirement author, not the RTL
debugger.

## Loop mechanics settled on the way here

Fixed, each measured on a live run rather than inferred:

| defect | evidence |
|---|---|
| `stage_edit` demanded exact whitespace | run 7 burned 11 of 45 rounds on a one-space mismatch; run 8 landed the same edit first try, `matched_on: token sequence` |
| uncovered UIDs shed to a bare count | run 7 made 0 `add_stimulus` calls with the tool wired |
| `add_stimulus` gated on an always-empty set | `gate.evaluate` returns on `if failing:` without `not_exercised`; 4 calls, 4 refusals in run 8 |
| commit judged on failing testpoints | run 8 r21: silencing REQ-0009 lowered failing without raising passing |
| multi-driver guard blind to internal wires | 3 runs latched `assign scl_sync` twice, disagreeing in run 6 → X |
| no way to find a signal's driver | run 8 swept 13 block ids and called `read_block("scl_sync")` |
| `restore_best` never called by the driver | run 9 wandered to 16 passing / 70 uncovered with nothing to return it |
