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

## Timing or logic? Per output, and the answer differs

Cycle-exact co-simulation punishes a phase shift as hard as a wrong function, so
the raw 79% needs decomposing. If a difference is pure timing, shifting run 10's
stream by k cycles drives the mismatch rate to ~0. Sweeping k over [-40, +40]:

| output | at k=0 | best | at k | verdict |
|---|---|---|---|---|
| `dout` | 15.1% | **0.5%** | −4 | **TIMING** — recoverable |
| `scl_oen` | 44.5% | **38.8%** | −5 | **LOGIC** — irreducible |
| `cmd_ack` | 4.6% | 4.0% | −5 | mostly agrees |

So the edge-4 `dout` divergence that started this — the one the first-divergence
number pointed at — **is a timing artifact**. Run 10's `dout` leads golden's by
four cycles and is then 99.5% identical. `scl_oen`, which contributes the largest
share of the 79%, is not: no shift in an 81-cycle window rescues it.

### The cause is one edit, and it is a functional regression

Both designs sample identically — `if (sSCL & ~dSCL) dout <= sSDA;`, textually
the same. The difference is what feeds `sSCL`/`sSDA`:

```verilog
// GOLDEN, and the BASELINE run 10 started from
assign sSCL = majority3(fSCL);      // 3-deep filter, filter_cnt-paced
assign sSDA = majority3(fSDA);

// RUN 10
assign sSCL = cSCL[1];              // raw 2-stage synchroniser
assign sSDA = cSDA[1];
```

**Run 10 bypassed the glitch filter.** `fSCL`/`fSDA` are still shifted every
cycle and `majority3` is still declared — the filter is computed and thrown
away.

That explains both columns. Dropping the filter removes ~4 cycles of latency,
which is exactly `dout`'s recoverable offset; and it removes spike rejection,
which is a functional requirement of I²C, not a timing preference. Golden's own
comment says what it is for: *"filter SCL and SDA signals; (attempt to) remove
glitches"*.

So the answer to "is it only cycle-accuracy" is **no**. Even where the observable
symptom is a clean 4-cycle shift, the edit that produced it deleted a required
function. And it is the kind of edit the loop is rewarded for: less latency means
responses land sooner and more windows close in time, which is how a design that
deleted a filter scored 61 against golden's 51.

## Why nothing caught the filter deletion

Three requirements govern the filter run 10 bypassed. Each failed to catch it in
a *different* way, and none of them was merely uncovered.

| requirement | in the 90? | verdict | why it missed |
|---|---|---|---|
| **REQ-0046** "Majority voting over the three-sample histories must produce sSCL and sSDA so that short glitches … are suppressed" | **NO — dropped** | — | the check that literally forbids this edit is not in the set |
| **REQ-0010** "reduces short glitches by … a majority function over the three-sample histories" | yes | **INVERTED**: run 10 **PASSES**, golden **FAILS** | the surviving check *rewards* the deletion |
| **REQ-0045** "a filter counter … must trigger periodic sample-shift events that move the synchronized samples into fSCL/fSDA" | yes | both PASS | run 10 still shifts `fSCL`/`fSDA` every cycle — it only stopped *reading* them. The check watches the machinery run and cannot see the output discarded |

### REQ-0046's provenance, which is the uncomfortable part

It was in the frozen 110 with disposition **TRUSTED**. It was then classified
**over-strict**, sent for re-authoring, and the re-author returned
**ORACLE_INVALID** — so `base_suite()`'s rule that a rejected check contributes
nothing (rather than silently keeping the stale one) dropped it from the 90.

That rule is right in general: keeping a check the author has rejected would
score a lost check as if it survived. But the consequence here is that the
one requirement whose violation *is* this defect was removed from the set by the
over-strictness repair — and the pipeline has no way to notice that what it
discarded was the only guard on a real property.

### The shape of the trap

Run 10 left the filter *computed* and stopped *consuming* it. That is precisely
the edit that satisfies REQ-0045 (machinery still ticks), satisfies REQ-0010
(which is inverted anyway), and violates only REQ-0046 (not in the set). The
dead code is what makes it invisible: a checker that asks "does the filter run"
sees yes, and only a checker asking "does anything use the filter's output"
would see no.

### Why REQ-0010 inverted, and why REQ-0046 was dropped — the same flaw, opposite outcomes

**REQ-0046 was rejected for a sound reason.** Its check verified the filter
*indirectly*, by demanding a minimum latency between an `scl_i`/`sda_i` toggle
and a `busy` transition. The re-author's recorded reason:

> a legitimate busy transition, correctly delayed by roughly the true filter
> latency from its actual causal excitation, lands within `period` edges of a
> DIFFERENT, unrelated scl_i/sda_i toggle … and the check cannot tell that apart
> from "busy reacted too fast to this toggle".

That is a real unsoundness — the check convicts correct designs — and
ORACLE_INVALID was the right call *on the check as written*. The deeper problem
is that the filter's actual property (`sSCL` is the majority of the last three
samples) is **internal**, and this oracle framework observes only boundary
ports, so every boundary proxy for it is attribution-ambiguous.

**REQ-0010 has the identical flaw and survived.** Its check scans for a
single-sample `A,B,A` glitch on `sda_i`/`scl_i` and then demands that *no output
at all* change across those three rows. Run against both designs:

```
GOLDEN (has the filter)    FAIL
   sda_i single-sample glitch at rows 0,1,2 caused output 'dout' change 0 -> 1

RUN 10 (filter bypassed)   PASS
   1 single-sample input glitch(es) observed during activation
   with no immediate output reaction
```

Golden fails because `dout` makes a **legitimate data capture** in a window that
happens to contain an injected glitch, and the check attributes the capture to
the glitch — precisely the coincidence-attribution error REQ-0046 was rejected
for. Run 10 passes because its `dout` does not move in that window, which is a
consequence of its *different, wrong* `dout` behaviour, not of any filtering.

So the inversion has nothing to do with filtering. **The check convicts golden
for doing its job and acquits run 10 for not doing it**, and the property it was
supposed to guard is untested either way.

The net: the over-strictness repair removed the check with this flaw that was
*also* the only guard on the filter, and kept the check with the same flaw that
guards nothing. Both decisions were made on soundness, neither on coverage —
nothing in the pipeline asks what a rejected check was the last guard for.

## RETRACTED: "the framework cannot express this property"

*The section that stood here argued the filter property was inexpressible — that
observing it needed either internal signal visibility or a two-trace
counterfactual, and that `decide(trace)` could do neither. That is wrong, and the
artifact that disproves it is one I had not read: the normalized record.*

## The normalization was right. The oracle authoring was not.

`normalized.json` for REQ-0046 does not mark it unobservable. It says:

```
observable   : ['al', 'busy', 'dout']
observed_via : 3 recipes, e.g. through busy (via REQ-0047) --
   when : "apply an SDA or SCL input pulse that is SHORTER than the
           majority-filter window (appears on fewer than 2 of 3 filter samples)
           AND COMPARE WITH a sustained input change that occupies at least
           2 of 3 samples"
   shows: "filter holds -> busy unchanged; filter violated -> busy changes
           per the filtered event"
```

That is a **differential test**, and it is expressible in a single trace: one
trace containing both a sub-threshold pulse and a supra-threshold change, with
the check requiring the outputs to move for the second and not the first. No
internal visibility needed, no counterfactual needed. My claim that neither was
avoidable was wrong — a differential comparison sidesteps the attribution
problem, which is exactly why the normalizer specified one.

**The authored check did NOT ignore that recipe — it implemented the ACTIVATION, and the activation is where the recipe was lost.** (See the section below; this sentence originally read "the authored check ignored that recipe", which the activation schema shows to be unfair.) REQ-0046's frozen oracle opens a
window on *any* `scl_i`/`sda_i` change and demands `busy`, `dout` and `al` do not
change:

```python
windows = after(trace, lambda r: inputs_active(r) and opens(r))   # ANY input edge
# ... require busy, dout, al unchanged at the activation
```

Grepping it for the distinction the recipe is built on — *sustained*, *majority*,
*2 of 3* — finds nothing. So it asserts that no output may ever change on any
input edge, which convicts every correct design, golden included. The re-author's
later ORACLE_INVALID diagnosis described the symptom (coincidence-attribution)
accurately without noticing the check had simply not implemented the specified
experiment.

**REQ-0010 had no recipe to ignore.** It has an oracle in the frozen 90 and *no
normalized record at all*. It is one of five: REQ-0010, REQ-0017, REQ-0048,
REQ-0078, REQ-0100.

122 requirements were normalized and 109 carry an `observed_via` recipe, 75 of
them inside the frozen 90 — so the indirect-observation machinery is populated
and largely unused. REQ-0010's naive check is what authoring without it looks
like, and REQ-0048 and REQ-0100 are in the same class, both among run 10's
failures.

Also: **`unobservable` is empty — zero requirements were ever marked so.** The
mechanism exists and has never fired on this run.

### So, to the question directly

The activations are not the problem. REQ-0046's activation is reasonable and its
observation strategy is sound and implementable. The defects sit one layer either
side of it:

1. **Five oracles were authored for requirements normalization never processed**,
   so their authors had no activation and no observation recipe.
2. **Where a recipe existed, the author did not implement it** — and no gate
   compares an authored check against the `observed_via` it was given.

The second is load-bearing: the pipeline generates a precise, sound experimental
design and then never checks that the oracle performs it.


## The activation could not say what the requirement means

The check faithfully implements the activation it was given:

```
activation.opens_on : [{'scl_i': 'change'}, {'sda_i': 'change'}]
the check opens on  : (r['edge'] in scl_changes) or (r['edge'] in sda_changes)
```

So the author did not ignore anything. **The activation flattened "a short
GLITCH on scl_i or sda_i" into "ANY CHANGE on scl_i or sda_i"** — and the
glitch's defining property, its duration of fewer than 2 of 3 filter samples, is
simply not in it.

That is not an authoring slip. `Activation` cannot carry it. Its three fields are
all per-row predicates — `inputs` a conjunction over one row, `opens_on` a
disjunction over one row, `until` a closing condition — and the schema documents
the exclusion in terms:

> **"A CONDITION, NEVER A COUNT.** `until cmd_ack` is expressible; `for 12 edges`
> is a guess at pacing this specification does not state, and Phases 3-6 severed
> pacing from latency for exactly that reason."

The policy is right in general and wrong here. For a majority-of-three filter the
count **is** the specification — "fewer than 2 of 3 samples" is stated by the
design's own structure, not guessed at from prose — so the one rule protecting
the pipeline from invented pacing is what stops it expressing a real,
spec-given repetition.

**The check language does not share the limitation.** `temporal.pulse` already
takes a width:

```python
def pulse(w, port, *, active=1, width=1, after_activation=False):
    """`port` must go active for exactly `width` consecutive rows, once."""
```

So repetition is expressible where the oracle runs, and inexpressible where the
oracle is specified. The `observed_via` prose describes the differential
experiment correctly and has no structured counterpart, so an author working
from the structure — which is what the structure is for — cannot arrive at it.

### Corrected chain of custody for REQ-0046

| stage | what happened | fault? |
|---|---|---|
| requirement | "Majority voting … so that short glitches are suppressed" | sound |
| normalize → `observed_via` | three correct differential recipes, in prose | sound |
| normalize → `activation` | glitch duration dropped; `opens_on` = any edge | **schema cannot express a count** |
| oracle author | implements the activation faithfully | sound, given its input |
| resulting check | "no output may change on any input edge" | convicts every design |
| re-author | ORACLE_INVALID, diagnosing attribution ambiguity | correct on the symptom |
| `base_suite()` | rejected check contributes nothing → dropped | correct rule |
| run 10 | deletes the filter; nothing left to notice | — |

Every stage behaved correctly under its own contract. The property was lost at
the one point where a duration had to survive into a structured form and could
not.
