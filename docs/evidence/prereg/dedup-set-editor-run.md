# PRE-REGISTERED: the de-duplicated set, run through the editor

Fixed before the loop was dispatched.

## What is being tested, and why it is not another draw of the same thing

§9z measured that the 169-check set holds **77 distinct verdict vectors over the
nine designs -- 72 checks (48%) are exact duplicates and one vector is carried by
21 checks.** It reported that as a SPAN correction and stopped.

**It bites somewhere §9z never looked: the editor counts objections.** An opinion
carried by 19 checks casts 19 votes and an opinion carried by one casts one, so
the criterion the loop descends on is weighted by AUTHORING REDUNDANCY rather than
by content. That has been true of all five graded draws and of every earlier run
on this plan, and nothing has ever tested it.

**De-duplication removes nothing by construction.** Two checks with the same
verdict vector agree on every (design, testpoint) either decides: they cannot
separate a pair the other cannot, they close no cell the other does not, and an
editor satisfying one satisfies the other. Dropping one changes the WEIGHT of an
opinion and not the set's content.

## The set

Vectors taken over all **29** designs, not the nine -- a finer partition, so this
errs toward keeping checks. Plus the one sound opinion §9ab found.

| | |
|---|---|
| the shipped set | 169 |
| reads no real declared output -- cannot close a blind cell | 20 |
| live | 149 |
| **distinct opinions** | **86** |
| + §9ab's sound opinion | **87** |
| largest identical group collapsed | **19 checks -> 1** |
| ***audit: convict the reference*** | ***0*** |
| decide NOTHING on the reference | **0** |

The audit is zero and **every one of the 87 decides**, where the 169 carried 20
that read no real output. So this is a strictly denser criterion at the same
false-reject rate, built golden-free by a partition over the population's own
traces, with the audit computed afterwards and selecting nothing.

**Baseline on the start design, the same arbitrary unchecked LLM design (`gen/L.v`,
md5 34a7fd66) every graded draw started from:**

| set | objections | of | rate |
|---|---|---|---|
| HOLE | 24 | 169 | 14.2% |
| **DEDUP** | **22** | **87** | **25.3%** |

## THE BAR, AND IT IS A DISTRIBUTION AND NOT A POINT

§9t established that **one graded run is not a measurement**. Five draws of the
169-set from this same start design, same 21-trial budget, differing only in the
session, graded at:

    146, 192, 192, 207, 220 of 348 testpoints differing   (median 192, sd 28)

A single DEDUP draw is read against that spread and nothing else:

| outcome | reading |
|---|---|
| **`NO-DIFF-40`** | equivalence. The goal's finish condition, and it would settle it |
| **< 146** | outside the control range on the favourable side. **Still one draw** -- it would license a replicate, never a claim |
| **146-220** | INSIDE the control spread. **De-duplication is not shown to do anything**, and that is the outcome to expect |
| **> 220** | worse than every control draw -- redundancy was load-bearing, which would itself be worth knowing |

**A fall in OBJECTIONS is not a result.** The DEDUP set has a different
denominator, so its objection count is not comparable to the 169-set's by
construction. Only the miter and the testpoint count are comparable, and both are
computed last.

## INTEGRITY PINS

* **Graded in its OWN clean directory** from the accepted `dut.v`, never `best.v`
  (selected by a cell count this arm's latch does not use) and never `loopDEDUP/run1`
  (whatever was last simulated, which for a rejected commit is the candidate).
* **Three pins in the same process** or no verdict is quotable: reference vs
  itself `EQUIVALENT`, reference+probes `NO-DIFF-40`, a live mutant `DIFFERS`.
* **The editor is told not to look for a reference implementation**, and is
  additionally forbidden the other loop directories and every `*.md` but its own.
* **The audit is computed last** and selects nothing.
* Same stimulus (`stimJUDGE`), same start design, same 21-trial budget as the five
  controls -- only the set differs.
