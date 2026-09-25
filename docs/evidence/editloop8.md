# Run 8: the loop converges, and the ceiling is now known

First run measured on **passing requirements** rather than failing testpoints,
and the first to reach a score comparable to the golden design.

## Result

| | failing | uncovered | **passing** |
|---|---|---|---|
| baseline (ChipVerilog codex/t1) | 19 | 25 | **46** |
| **run 8, after 1 trial** | 5 | 27 | **58** |
| GOLDEN `i2c_master_bit_ctrl.v` | 3 | 27 | **60** |

Twelve requirements repaired in a **single commit**, from a 45-round session
that spent **1 of its 4 trials**.

## What the one commit was

Rounds 3–6, four `edit` calls, then one `check_staged` and one `commit`:

```
CMD_START  4'b1000 -> 4'b0001
CMD_STOP   4'b0100 -> 4'b0010
CMD_READ   4'b0010 -> 4'b1000
CMD_WRITE  4'b0001 -> 4'b0100
```

That is the encoding in the benchmark's own `i2c_master_defines.v`
(`START=1, STOP=2, WRITE=4, READ=8`), which the candidate had reversed. Runs 5
and 6 found the same defect and each spent four trials on it; run 8 spent one.

**The whitespace-tolerant anchor was load-bearing here.** Rounds 4 and 5 report
`matched_on: "the token sequence, not the exact characters"` — the agent's
anchors did not match the buffer byte-for-byte and were applied anyway. Run 7,
same model and same tool without that tolerance, burned eleven of forty-five
rounds failing the identical edit and never landed it.

## The ceiling, and the stop condition

`satisfiable.py` decides the same 90 oracles over the same stimulus against the
**golden** design, and splits the survivors:

| class | n | requirements |
|---|---|---|
| DISCRIMINATING — golden passes, candidate fails | 3 | REQ-0009, REQ-0042, REQ-0066 |
| **CONVICTS-GOLDEN — proven unsatisfiable** | **2** | **REQ-0030, REQ-0095** |
| INVERTED — candidate passes, golden fails | 1 | REQ-0006 |

REQ-0030 ("al is asserted when a STOP condition…") and REQ-0095 ("enable
arbitration checking during the stable high phase") **fail the known-good design
too**. No edit to the candidate can satisfy a check the reference does not
satisfy: they are written wrong or inexpressible in the harness, and chasing
them can only burn trials.

Golden abstaining is deliberately NOT counted here. A check that never fired
against the reference says nothing about whether it is satisfiable — that is a
gap in the golden run's stimulus, not a verdict — so it is reported as its own
UNKNOWN class. Zero of them in this snapshot.

So convergence for this suite is **60–61 passing with 2 requirements
permanently unsatisfiable**, and run 8 sits at 58.

## Two defects this run exposed

**1. `add_stimulus` refused every request, and always would have.** The agent
called it four times — REQ-0076 twice, REQ-0078, REQ-0004 — all uids
`list_failing_requirements` had just listed as UNCOVERED. All four came back
*"not currently uncovered"*.

The set it gates on came from `_uncovered_requirements(verdict.not_exercised)`,
and `gate.evaluate` returns on its first matching branch:

```python
if failing:
    return GateVerdict("REPAIR_RTL", failing=failing, reason=...)
```

with `not_exercised` left at its default. A debug session has failing testpoints
by definition, so that branch always wins and the set is always empty. **The
tool was dead for the entire duration of every session it exists to serve** — it
could only have worked once nothing failed, when there is nothing to stage. It
now gates on `req_results`, which is what the agent is shown. Uncovered went
25 → 27 across this run with the tool inert, which is the cost.

**2. The round cap binds, not the trial budget.** 45 rounds, 1 trial, 3 unspent
— the same shape as run 7 (45 rounds, 2 trials). Seventeen rounds (12–28) went
to `read_block` sweeping nearly every block in the design, and rounds 30–33 and
42 are the agent trying `read_block("scl_sync")` and
`read_block("assign scl_sync")` — using a block-id reader as a **signal search**.
There is no tool that answers "where is this signal driven", so the agent
brute-forces the id space. Run 9 raises the cap to 130 rounds and 8 trials to
find out whether the loop keeps converging when it is not round-starved; the
missing search tool is not yet built.

## Honest notes

Run 8 differs from runs 5–7 in five ways at once — whitespace-tolerant anchors,
uncovered UIDs surviving the budget, the internal-wire driver guard, the
passing-requirement criterion, and `--keep-regressions`. It is not a clean
attribution of any single change. What it establishes is that the loop as a
whole now converges to within 2 of the golden score, and that 2 of the 5
remaining failures are provably not the design's fault.
