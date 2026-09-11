# Pre-registration — BTL: the blindness-targeted strengthening ladder

Fixed before any model call. Committed before the round was dispatched.

## The gap this addresses, and why the two prior attempts do not

The stimulus loop is finished — decide coverage **348 of 348**, SILENT **0 of
146** — so the residue is entirely **blindness**: the set decides where the
design is wrong and passes, 126 of 146. Two rounds have attacked it and both
failed in a way that is now understood rather than merely recorded:

* **The STRENGTH round** asked 34 sound-and-blind checks to assert every
  obligation in their own sentence. Strength rose 24x (1.8% → 44.1%), the audit
  went 0 → 23 of 34 = 68% unsound, and the both-cell landed at **0 of 34 — the
  MINIMUM the marginals allow.** Every check that gained discrimination lost
  soundness. But that round gave each author **one rewrite** and **an aggregate
  objection**: *"you decided N times and objected zero times."*
* **The LADDER round** (narrowing direction) showed why one rewrite is not a
  test: the landscape is **non-monotone**. Its single landing rung sat at depth 3
  with depths 1, 2, 4 and 5 all failing; one check ROSE from 5 to 7 convictions
  under narrowing. **A one-shot round samples one point of a bumpy landscape, so
  0 of N is what it should be expected to return even where a target exists.**

So the strengthening direction has never been tried with the two things the
narrowing direction had: **a ladder rather than a rewrite**, and — new — **a
concrete cell rather than an aggregate**.

## The objection, and it is golden-free

    at TP-xxxx, edge E, port P:
      all thirteen independently written designs produce X
      this design produces Y
      your check DECIDED here and PASSED

Derived from the anomaly detector (§9ap): 80.4% cell-level precision, 42.9x over
the base rate, reading only spec-derived designs. **No golden anywhere**, so
`oracles_stage.py:66-73` is satisfied — this is a control that rejects, and the
evidence it quotes is the population's, never the reference's.

## The independence protocol, because the targets come from a design

The targets are computed against **run 6** (the delivered design, 146 of 348
differing). A set authored to object at run 6's anomalies must not then be
scored on run 6, or the set is tuned to its own test.

* **AUTHOR** against run 6's anomalies.
* **FREEZE** the set.
* **GRADE** by running the Sonnet RTL editor from **design L** — written from
  the specification by an agent forbidden to open any other design, held out of
  the 13-design population, of the anomaly targeting, and of every selection.

Design L is the goal's *"arbitrary unchecked LLM-generated design"*, and it
played no part in building the set that will judge it.

## The round

* **Population:** 20 requirements drawn deterministically (uid order) from the
  40 whose frozen check is blind at ≥ 1 anomalous cell.
* **Ladder:** 5 rungs per requirement, spanning weak → strong. Rung 1 adds only
  the single obligation that catches the target cell; rung 5 asserts every
  obligation the sentence states. **100 calls.**
* **Each author sees:** its own requirement sentence, the contract with probes,
  the target cell, and the rung index with what that rung is for. It does **not**
  see the reference, any reference trace, any equivalence verdict, or any other
  rung's answer.
* **Leak check before scoring:** 0 lines of the reference's source, 0 testpoint
  ids from the reference suite, 0 equivalence verdicts, 0 mentions of design L.

## Selection — every leg golden-free, applied in this order

1. compiles
2. decides on the witness
3. not vacuous — objects to ≥ 1 population design or live mutant
4. **objects AT ITS TARGET CELL** — the new, sharp discrimination signal
5. **minority rule** — objects to ≤ 2 of the 13 population designs

The kept rung is the **highest** index satisfying all five; ties break to the
lowest `h`. A requirement contributes at most one check.

## Bands, fixed now

Requirements gaining a check that clears all five legs:

| reading | consequence |
|---|---|
| **≥ 8 of 20** | the ladder plus a concrete cell is the lever the strength round lacked. Build the set, run the editor from L, report the grade |
| **3–7** | real but weak. Record the rate beside the strength round's 0 of 34 and the narrowing ladder's 1 of 16, and **build nothing** |
| **≤ 2** | a concrete golden-free counterexample does not help either. Authoring into the adequate cell is closed on this corpus, and the residue is the specification's |

**AND THE AUDIT IS REPORTED BESIDE THE COUNT, ALWAYS.** How many kept rungs
convict the reference is computed last, selects nothing, and is quoted with the
yield. A yield without its audit is the defect this document has retracted
headlines for; an audit without the yield says nothing about whether the
instrument is worth having.

## What a passing result would still not be

Not equivalence, and not a golden-free score until the editor has run. The
detector's own ceiling bounds it in advance: **recall 20.4%** of the design's
differing cells, because the population can speak about only 21.6% of them. So
even a perfect round reaches about a fifth of the blindness residue, and the
remaining four fifths lie in split cells where nothing built from this population
can say anything. **A round that clears its band closes a fifth of the gap and
names the rest as specification-limited.**
