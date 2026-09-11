# Pre-registration — can a HELD-OUT golden-free instrument order draws of one loop?

Fixed before any count was computed. Committed before the scorer ran.

## The gap this is aimed at

§9y measured the one pipeline change that improves what is delivered: five draws
of one configuration span 146 to 220 testpoints, and **selecting among them by the
golden-free objection count picks the best of the five** (0 of 5 draws beat it,
45 testpoints better than an average draw). Spearman +0.564 — a selector of a
clear minimum rather than a ranking.

**That lever has never been applied to the configuration that delivered 174**, and
there is a structural reason it cannot be applied as written. The five draws of
§9y never satisfied their criterion — objections at rest ran 1, 4, 8, 11, 16 of
169 — so the selector had variance to read. **The audit-0 87-check DEDUP run
TERMINATED at zero objections with nine trials unspent.** A second draw of it will
very likely also terminate at zero, and a selector that is zero for every draw
picks arbitrarily.

## The question

**Among draws that all satisfy their own criterion, can a golden-free instrument
the editor never saw order them by grade?**

The candidate is the rest of the corpus: the live spec-derived check bodies that
are NOT in the criterion the editor descended on. It is golden-free on both legs
— every body is authored from the specification, and membership is decided by set
difference against the criterion, which reads no reference. It is **held out** in
the sense that matters here: the editor optimised against the criterion and never
saw these checks, so they cannot have been fitted.

## The instrument

* **Population:** the five draws of the §9y configuration — one start design, one
  169-check criterion (`specsetHOLE`), one 21-trial budget, differing only in the
  session. Their accepted designs are the `p4_*` trace sets already on disk.
* **Criterion (what the editor saw):** `specsetHOLE`, 169 checks.
* **Held-out instrument (what it did not):** the live corpus `specsetCEIL` (502)
  minus the 169. Objection counted per check, at most once, over the 348
  testpoints — the same decide path `chkscore.py` uses.
* **Grade:** testpoints differing from the reference, computed last, used only to
  score the ordering. It selects nothing.

## THE PIN, AND THE SCORER REFUSES WITHOUT IT

Before any held-out number may be read, the scorer must **reproduce §9y's in-set
objection counts** for the same five designs: **1, 4, 8, 11, 16**. A mismatch
means the design-to-draw mapping or the decide path is wrong, and every held-out
number would be a measurement of the harness. **It refuses to print in that case
rather than reporting a plausible table** — the fifteen counting-shaped defects on
this plan all had that signature.

## Bands, fixed now

Spearman between the held-out objection count and testpoints differing, n = 5:

| reading | consequence |
|---|---|
| **≥ +0.5** | the held-out corpus orders draws. Best-of-N is runnable on a terminating configuration: draw N of the DEDUP loop, select with this instrument, grade the selected one |
| **+0.2 to +0.5** | weak. Record the rate beside §9y's +0.564 and **do not build on it** — the same band discipline the narrowing rounds were held to |
| **< +0.2** | the held-out corpus does not order draws. Best-of-N cannot be steered once the criterion terminates, and the last delivery-improving lever on this corpus is closed |

**The operational question is scored separately and is not the correlation:** does
the rule *pick the best available draw* (146)? A selector may order poorly and
still identify the minimum, which is exactly what §9y's did.

**And a degenerate spread is an answer, not a null result.** If the held-out count
varies by less than the population's own noise across the five draws, it cannot
discriminate them whatever its correlation, and that is reported as the finding
rather than as a failed run.

## What this cannot show

It cannot show that best-of-N reaches equivalence. §9y's selector bought the best
member of a bad distribution and did not move the distribution; this one, if it
works, does the same on a distribution whose best member is 174 or nearby. **No
outcome here reopens the three closed routes to a golden-free second loop.**
