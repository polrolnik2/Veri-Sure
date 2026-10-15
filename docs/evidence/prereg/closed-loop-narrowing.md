# Pre-registration — does a halting point exist between over-strict and vacuous?

Fixed before any body was authored. Committed before dispatch.

## What every previous narrowing round did, and what it could not see

Three narrowing rounds landed 7 of 47, 1 of 28 and 0 of 24. **All three were ONE
BLIND STEP**: the author was told its check convicts N of M independently written
implementations, rewrote once, and the result was scored. Round 3 then measured
the conviction count and the objection **falling together** — 18 of 24 unmoved,
and 3 of the 4 that fell below nine stopped objecting.

**But one step is not a search.** The question those rounds answer is *"does a
single narrowing edit land on the boundary"*, which is not the question that
matters. The question that matters is **does a halting point exist at all** — is
there any narrowing of this check that convicts a minority AND still objects?

The golden-free instrument for that is already measured and cheap: `h(c)`, the
number of the nine spec-derived designs the check convicts, ~100% precise on its
reject side. It costs no model call, so a search can consult it at every step.

## The instrument

Rather than an interactive loop — which would spend a call per step and give one
sample per check — each author returns a **LADDER**: five variants of its own
check, progressively narrower, rung 1 barely narrowed and rung 5 the narrowest
reading its requirement's sentence still licenses. Scoring every rung is Python.
**This tests the existence of a halting point with five samples per check instead
of one, at one call per check.**

* **Population:** 16 checks, one per requirement, each of which **objects to the
  delivered design** and **fails the minority rule** (`h > 2` of 9). Both legs
  read only spec-derived artifacts. **7 of the 16 sit on requirements the
  169-check set does not cover**, where a landing rung adds an opinion the set
  does not already hold.
* **What the author sees:** its requirement's sentence, its own check's source,
  and the sentence *"you convict N of nine independently written
  implementations"*. Nothing else. No reference, no held-out design, no grade.
* **A rung LANDS iff** `h ≤ 2` **and it still objects to the delivered design.**
* **Vacuity is a LOSS.** A rung that objects to nothing has lost the property the
  check was kept for, and is scored as a failure, not as a soundness gain.
* **The audit runs last and selects nothing:** of the landing rungs, how many
  spare the reference. A landing rung that is also sound is an **authored
  both-cell check** — the thing seven rounds have failed to produce.

## Bands, fixed now

Checks with at least one landing rung, of 16:

| reading | consequence |
|---|---|
| **≥ 4** | the halting point exists and one blind step was simply missing it. Closed-loop narrowing is the route: rebuild the set with the landing rungs and run the editor on it |
| **1–3** | it exists and is rare. Record the rate beside 15% / 4% / 0% and **build nothing** |
| **0** | the conviction count and the objection are coupled with no point between them, across five narrowing depths on sixteen checks. The authoring route closes completely, and round 3's reading becomes structural rather than a rate |

## Integrity, run before any score is read

16 of 16 returned; every rung compiles; **0 duplicate bodies** across checks (the
fabricated-response signature); no rung byte-identical to the original; and a leak
check over every prompt and every returned body for reference source, testpoint
ids, equivalence verdicts, or the word "golden".

## What a pass would and would not mean

It would mean the both-cell is **authorable with a golden-free objective**, which
is the first time any route has produced one. It would **not** mean equivalence:
the landing rungs would then have to be assembled into a set and driven through an
editor run, and the 62-testpoint structural gap is measured against the corpus as
it stands, not against a corpus with these added.
