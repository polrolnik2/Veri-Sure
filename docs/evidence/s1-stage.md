# S1 in detail, and where the granularity floor leaks

## The three modules

**`divide.py` — mechanical, no model.** Cuts the spec only at blank lines, list
items, headings, table rows and fences: "boundaries a human put there
deliberately". 65 units on i2c_master_bit_ctrl's 15,713 chars. It holds itself
to `splits_a_sentence`, `overlaps` and `coverage`, and passes all three by
construction. Explicitly **a floor, not a partition**.

**`s1_classify.py` — one model call per unit**, fanned out, with the WHOLE spec
in the cached prefix (measured 97% hit) and neighbouring units marked so a
back-reference has its referent in view. Per unit it returns:

    kind                behaviour | scaffolding | ...
    continues_previous  chains this unit onto the one before
    obligations         [{start, end, text, ports}]   <- offsets RELATIVE to the unit
    underdetermined     honest "the spec does not say"

**`s1_requirements.py` + `assure.py` — assemble and validate.** The check is
that each quote is verbatim and locatable. Offsets are, in `assure.py`'s own
words, "a HINT, not the check" -- deliberately, because exact-offset arithmetic
rejected 30 of 31 good attributions and made vacuity cheap.

## The three claimed properties, against what is actually enforced

| claimed | enforced |
|---|---|
| the model emits offsets, never spec text | **yes** -- `Obligation.start/end` are ints |
| the model cannot choose top-level granularity | **half** -- see below |
| context preserved, back-references resolvable | **yes** -- whole spec at 97% cache |

The middle one is the leak, and it is enforced **structurally in one direction
only**. An obligation is a pair of offsets *inside one unit*, so it cannot reach
a non-adjacent unit: the catch-all that once claimed 15,709 of 15,714 chars is
impossible by construction, which is exactly what `divide.py` was built for.

But `start` and `end` **within** the unit are unconstrained. The model may carve
a 22-character fragment out of a 380-character unit, and nothing in
`s1_classify`, `s1_requirements` or `assure` looks at where the cut falls.

## What that produces, measured on c1-i2c

| | |
|---|---|
| spans that are a union of whole units | **6 of 127** |
| spans that subdivide a unit | **121 of 127** |
| spans that BEGIN MID-SENTENCE | **41 of 127** |

`divide()` holds itself to zero on the third row. S1 was never asked to.

The dominant shape is a sentence cut at its commas:

    REQ-0002  "The module supports generation of I2C START and STOP conditions,"
    REQ-0003  "single-bit WRITE cycles, "
    REQ-0004  "single-bit READ cycles, "
    ...
    REQ-0010  " and glitch filtering."

Nine requirements that are noun phrases and assert nothing. REQ-0010 is
fragment nine, and it is the requirement whose oracle convicts the golden
design and acquits the one that deleted the glitch filter -- because its text
had to describe a mechanism its span does not contain.

## Four things you could do

**A. Reject mid-sentence obligations.** Add `splits_a_sentence` to the S1 gate,
per obligation, relative to its unit. Mechanical, no model call. **41 of 127**
enter repair. Catches REQ-0010, 0045, 0046 and 0083 -- every requirement in the
filter story.
*Cost:* a 32% repair bill, on a loop whose convergence has been uneven.

**B. SNAP obligations to sentence boundaries.** Same test, but the harness
*extends* each obligation's offsets to the enclosing sentence instead of
rejecting it. No model call, no repair round, no rejection possible.
*Effect:* the model keeps choosing granularity ABOVE the sentence and stops
choosing below it -- which is the floor `divide.py` states and never enforced.
REQ-0002..0010 collapse into one requirement covering one sentence.
*Cost:* requirement COUNT changes materially, and uids are the spine of every
downstream artifact. Not reusable against an existing run; needs a fresh S1.

**C. Require an obligation to state something.** A bare noun phrase -- "
single-bit READ cycles, " -- is not an obligation. A finite-verb test would
reject those nine directly.
*Cost:* judgement, and the module records that two THRESHOLD attempts were tried
and reverted (a 24-char minimum rejected the half adder's legitimate
`' - output cout'`). A verb test is a different test from a length test, but it
is the same family and deserves the same suspicion.

**D. Leave S1 alone; add a `defined_by` link.** Let a requirement cite the one
that defines a term it uses, so REQ-0046 could name REQ-0083 for `clk_cnt >> 2`.
*Cost:* new schema surface, and it does not touch the nine noun phrases -- it
only helps requirements that are real but incomplete.

## Recommendation

**B, then A as its gate.** Snapping is deterministic, cannot reject a good
requirement, and restores the exact invariant the floor was built to hold; A
then becomes a cheap assertion that snapping worked rather than a repair loop
that has to converge. C is worth measuring but not shipping first -- the
threshold precedent is a real warning. D is orthogonal and can wait for evidence
that requirements survive S1 intact and are still incomplete.

The thing to decide first is whether a changed requirement count is acceptable,
because B implies a fresh S1 and everything downstream of it.
