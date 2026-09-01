# Convergence: reached on coverage, blocked on the oracle set

Iterating the RTL editor with Sonnet subagents, against the goal
*"failing only where golden fails, and covering all reachable assertions"*.

## The like-for-like measurement

Earlier comparisons in this file were taken on **different suites** and were
withdrawn. `add_stimulus` re-rendered from the full `stimulus.json`, so three
scenario requests took run 10's suite from 224 testpoints to 334 while baseline,
run 8 and golden stayed at 224. Fixed (one call adds one testpoint), and golden
re-run on run 10's own 334-testpoint suite. Everything below is one suite.

| on 334 testpoints | passing | failing | covered |
|---|---|---|---|
| **GOLDEN** | 51 | **12** | 63/90 |
| **run 10** | **61** | 5 | 66/90 |

## 1. The candidate beats the reference, which is the defect

run 10 **passes 11 checks the golden design fails**: REQ-0010, 0027, 0030, 0054,
0059, 0060, 0068, 0095, 0105, 0115, 0126. It agrees with golden on 71/90.

A check the known-good design fails is a wrong check. Passing it is not
correctness — it is the design deformed until an error is satisfied. `passing`
goes **up** while agreement goes down, so no threshold on the pass rate can
detect this; `satisfiable.py` now prints agreement beside it and warns whenever a
candidate outscores the reference.

## 2. The oracle set's error rate GROWS with stimulus

| golden on | fails | covers |
|---|---|---|
| 224 testpoints | 3 | 63/90 |
| 334 testpoints | **12** | 63/90 |

The same 90 checks convict the same correct design **four times as often** once
110 more testpoints run. This is the finding that settles the goal: it is not
"two requirements are wrong", it is that **13% of the frozen set is provably
wrong and the fraction rises as you exercise it harder**. Every one of those 12
is an edit the loop is *rewarded* for making, and run 10 took 11 of them.

## 3. Coverage is reached, and the residue is unreachable

Golden covers **63/90 on both suites** — 110 extra testpoints bought exactly
**one** newly covered requirement. So the 26 requirements golden never covers on
either suite are not a stimulus gap; nothing the stimulus generator produces
reaches them.

run 10 covers **66/90**: all of golden's 63 except REQ-0085, plus four golden
never covers (REQ-0048, REQ-0097, REQ-0108, REQ-0125). Against "cover all
assertions **if they are reachable**", that clause is effectively met — the
candidate covers more than the reference does.

`add_stimulus` itself remains ineffective, and this is why it cannot close the
rest: three calls added three testpoints that ran (PASS, PASS, FAIL) and covered
**none** of their targets — REQ-0017, REQ-0019, REQ-0024 are still uncovered.
The tool is reachable now and not yet useful.

## Verdict against the goal

| clause | status |
|---|---|
| fail only where golden fails | **not met** — 4 extra: REQ-0042, REQ-0048, REQ-0099, REQ-0119 |
| cover all reachable assertions | **met** — 66/90 vs golden's 63/90 |
| requirements proven written incorrectly | **12** — golden fails them |

**Stopping.** The stop clause fires, and it fires *because* of the first clause
rather than beside it: with 13% of the oracle set provably wrong and the loop
scored on satisfying it, the four residual failures cannot be attributed to the
design. Pushing the candidate to fail "only where golden fails" would mean
pushing it further into the eleven inversions it has already taken.

The remaining work is upstream — repairing the requirements — and needs the
requirement author, not the RTL debugger.

## Loop defects fixed on the way, each caught by a live run

| defect | evidence |
|---|---|
| `stage_edit` demanded byte-exact whitespace | run 7 lost 11 of 45 rounds to a one-space mismatch; run 8 landed the same edit first try |
| uncovered UIDs shed to a bare count | run 7 made 0 `add_stimulus` calls with the tool wired |
| `add_stimulus` gated on an always-empty set | `gate.evaluate` returns on `if failing:` without `not_exercised`; 4 calls, 4 refusals in run 8 |
| `add_stimulus` re-rendered the whole stimulus file | run 10's suite grew 224 → 334, invalidating every cross-run comparison |
| commit judged on failing testpoints | run 8 r21: silencing REQ-0009 lowered failing without raising passing |
| rollback forced on any regression | hill-climber could not cross a valley; now `--keep-regressions` + `restore_best` |
| multi-driver guard blind to internal wires | 3 runs latched `assign scl_sync` twice, disagreeing in run 6 → X |
| no signal search | run 8 swept 13 block ids and called `read_block("scl_sync")` |
| `restore_best` never called by the driver | run 9 wandered to 16 passing with nothing to return it |

---

# Equivalence check: the oracle score and the design have come apart

Everything above is measured through the frozen 90 checks, and 12 of those
provably convict golden — so the numbers describe the checks as much as the
design. Differential co-simulation asks a question the checks cannot corrupt:
driven by the **same stimulus**, do the two designs produce the **same outputs**?
No reference model, no activation, no window, nothing to abstain.

`docs/evidence/equiv10.py`, 4000 shared-stimulus clock edges:

| design | mismatching edges | % | first divergence |
|---|---|---|---|
| **golden vs golden (control)** | **0** | **0.0%** | none — equivalent |
| baseline (loop input) | 3241 | 81.0% | edge 0 |
| **run 8** | 3065 | **76.6%** | edge 0 |
| **run 10** (loop output) | 3165 | **79.1%** | edge 0 |

The control is exact, so the harness is sound.

## Two things this settles

**1. The loop's objective is anti-correlated with correctness here.** Run 10
scores *higher* on the oracle set than run 8 (61 vs 58 passing) and is *further
from golden* (79.1% vs 76.6% mismatching). This measurement is independent of
suite size, of which testpoints were rendered, and of the oracle set entirely —
so unlike the earlier comparison it cannot be an artifact of the 224/334 split.
It is the same ordering the agreement metric gave, arrived at by a route that
shares none of its assumptions.

**2. "Convergence" was never behavioural.** The loop moved the design 81.0% →
79.1% mismatching: **1.9 points** over five trials, while the oracle score went
46 → 61 of 90. Run 8 did better on both counts with one trial (4.4 points).
Per port, run 10 made `dout` almost twice as wrong (315 → 607 mismatching edges)
and `busy` worse (1068 → 1257), buying that with `sda_oen` (1873 → 1343).

## What this does not say

Cycle-exact co-simulation punishes a *timing* difference as hard as a logic
error, and this design has a clock divider — a candidate that interpreted the
prescaler differently would mismatch heavily while being defensible. So 79%
is **not** "79% wrong"; it is "not cycle-equivalent, and far from it".

The comparison *between* runs is unaffected by that caveat, because all three
candidates are measured against the same reference on the same stimulus. That
comparison is the finding: **more oracle-set optimisation, no closer to the
design.**
