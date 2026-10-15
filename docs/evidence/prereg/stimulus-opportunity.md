# Pre-registration — what is the stimulus loop worth on the design we actually deliver?

Fixed before any count was computed. Committed before the scorer ran.

## Why this, and why now

The goal predicts it outright: *"For this you will likely need to finish the
stimulus loop."* Every measurement of that prediction so far has been **per
check, on older sets, against older designs** — the sharpest was 3 of 50 checks
silent where their own port is wrong, on design L against the 50-check ceiling
set. None of them is about the artifact this pipeline now delivers.

**The right unit is the TESTPOINT, not the check.** A check is silent or not as a
property of itself; whether the suite can ever catch a defect is a property of
the *testpoint* — if no check in the set decides there, no check can object
there, whatever its strength. That number has never been computed.

## The decomposition

Of the testpoints where the delivered design is still wrong, each is in exactly
one of two classes, and they demand opposite work:

| class | definition | the lever |
|---|---|---|
| **SILENCE** | **no check in the set decides at this testpoint** | the STIMULUS loop — nothing can object here until the suite drives the design somewhere a check can judge |
| **BLINDNESS** | at least one check decides here, and none objects | check STRENGTH / authoring — the set looks and says nothing |

## The instrument

* **Set:** the 169-check audit-zero criterion (audit 0 of 169, all 169 decide —
  no sound-by-silence members), the criterion behind the best delivered design.
* **Design:** the run-6 draw, the one the golden-free positive-count argmin
  selects, at 146 of 348 testpoints differing.
* **Contrast:** the same computation on the start design, so the figure is read
  against where the loop began rather than in isolation.
* **Golden-free half, reported first and standing alone:** per-testpoint
  **decide coverage** — the share of the 348 testpoints where at least one check
  in the set decides. This reads no reference at all and is a score in the goal's
  own terms.
* **Calibration half, computed last and selecting nothing:** split the differing
  testpoints into SILENCE and BLINDNESS.

**SILENCE IS AN UPPER BOUND ON THE STIMULUS OPPORTUNITY, AND THAT IS DELIBERATE.**
A testpoint where no check decides may be one the stimulus never drives into an
activation, or one where every check's window is wrong for check-side reasons.
This measurement does not separate those. It therefore **over-states** what the
stimulus loop could buy, which is the direction that makes a small number
decisive: if the upper bound is small, the lever is closed without needing the
split.

## Bands, fixed now

Share of the delivered design's differing testpoints that are SILENT:

| reading | consequence |
|---|---|
| **≥ 20%** | the stimulus loop is a real lever on the deliverable. Size what closing it would buy and run it |
| **5–20%** | partial. Record the rate beside the earlier 3-of-50 and **build nothing on it** — the same band discipline the narrowing rounds were held to |
| **< 5%** | the stimulus loop is worth essentially nothing on the current best configuration. The goal's own prediction is then answered with a number on the actual deliverable, and the residue is entirely check strength |

## What this cannot show

It cannot reach equivalence and nothing here is a route to it. A closed stimulus
lever does not make the set complete; it relocates the residue. And a large
SILENCE share would not by itself mean the testpoints are reachable — that is the
next question, not this one.

**One design, one corpus, one set.** Nothing here is claimed for i2c.
