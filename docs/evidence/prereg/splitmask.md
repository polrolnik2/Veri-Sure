# Pre-registration — SPLITMASK: golden-free admission of an objection, per site

Fixed before anything was computed. Committed before the scorer ran.

## The seam the closures leave open

Every closure this session selects **whole checks**. The minority rule keeps or
drops a check; the audit scores a check; narrowing rewrites a check. And the
measured result is that no whole check both objects to the delivered design and
spares the reference — **255 objectors, 0 sound**.

**But over-strictness is LOCAL, and the plan has already measured that it is.**
The ceiling run recorded a check *"sound suite-wide and still making a demand no
design should meet on a path the suite does not reach"*, and the reference-vetted
per-site mask (TPMASK — admit an objection only where the check spares the
reference) takes the chained loop to **112 of 348**. So the corpus holds the
information; what is missing is a golden-free way to localise it.

**There is one candidate instrument and it has never been built.** The split-cell
finding is a statement about *cells*, not about checks: where all 13 spec-derived
designs agree, the agreed value matches the reference **99.82%** of the time. It
has only ever been used to accept or reject whole checks (84% precision). Used
per site it becomes the golden-free analogue of TPMASK.

## The rule

> **Admit check `c`'s objection at testpoint `tp` iff, at the objection row, the
> design under test DIFFERS from the population consensus on some port `c`
> reads. Mask it where the design MATCHES consensus on every port `c` reads.**

Rationale, and it is the split-cell argument applied at the objection site: if the
design does exactly what 13 independent implementations unanimously do on every
port the check is looking at, and the check objects anyway, then at ~998:1000 the
**check** is what is wrong *there*. If the design departs from consensus on a port
the check reads, the objection stands.

**Both legs are golden-free.** The consensus is built from spec-derived designs;
the mask reads the design under test. The reference appears only in the audit,
computed last.

## What it is measured against

* **Population for the criterion:** the 169-check audit-zero set **plus** the 255
  corpus checks that object to the delivered design — the ones every whole-check
  rule correctly rejects as unsound.
* **Design:** run 6, the golden-free selected draw, 146 of 348 differing, of which
  **126 are BLIND** — the set decides there and passes.
* **The number that matters:** of those 126 blind testpoints, how many acquire an
  **admitted** objection under SPLITMASK.
* **The audit, last:** how many admitted objections land where the reference
  itself would be convicted. That is the false-reject rate of the masked
  criterion, and it is reported beside the yield — never alone.

## Bands, fixed now

Blind testpoints acquiring an admitted objection, paired with the masked audit:

| reading | consequence |
|---|---|
| **≥ 25 of 126 with a masked audit ≤ 5%** | SPLITMASK is the missing fuel. It is golden-free, so build the criterion and run the editor on it |
| **≥ 25 with audit > 5%**, or **8–24 at any audit** | partial. Record the pair and **build nothing** — a yield bought with false rejection is the trade every section here has refused |
| **< 8 of 126** | the locality of over-strictness is not recoverable from population unanimity either, and the per-site route closes with the per-check ones |

**THE PAIR IS THE RESULT.** A yield quoted without its masked audit is the defect
this document has retracted headlines for; an audit quoted without the yield says
nothing about whether the instrument is worth having.

## What would still not follow

A passing result is an instrument, not equivalence. It would have to be run as an
editor criterion and graded before any claim about the delivered design, and the
97%-of-errors-in-split-cells finding predicts a hard limit: SPLITMASK can only
remove the over-strictness that **contradicts consensus**. A demand that is wrong
inside a split region survives the mask, because the population has no opinion
there — and that is exactly where the design's errors live.
