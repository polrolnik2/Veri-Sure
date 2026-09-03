# What the session's measurements say to do, ranked

The problem in its general form is "make good assertions for complicated
designs". The measurements narrow it a long way, and the narrowing is the
useful part.

## The failure is not diffuse. It is concentrated and named.

On h3-i2c, bucketing requirements by the deepest derived signal each names:

* **ports only — 90 of 118, and 53% become TRUSTED.** This class works.
* **depth 0–3 — 11 requirements, 0 TRUSTED.** Total failure.
* depth 4+ — 17 requirements, 35%.

So "complicated" does not degrade assertion quality across the board. It fails
completely on a small, identifiable set, and that set is upstream of everything
else: the eleven include every requirement that DEFINES the filter chain, and 28
other requirements had to re-derive it because those eleven were discarded.

## It is not an information problem, and not an authoring problem

Three interventions supplied more context and moved nothing:

| intervention | result |
|---|---|
| whole specification as tie-breaker (arms B, C) | **zero** oracles reconstructed the filter |
| full annotated normalized form of every linked sibling (arm D) | convictions 3/6 → 3/6 |
| shipped prompt (arm A control) | 3/6 |

And the author is capable when the material is executable: k1's REQ-0007 built
a correct per-request window verbatim from a supplied `spec_spans` quote. The
difference is depth — at depth 1 a supporting span IS a guard; at depth ≥2 it
names something the author cannot read.

## Ranked by measured value

**1. Wire G8.** `specflow/qualify.py` is built, tested, and its only importer in
the repository is its own test file. Completeness — "can this suite detect a
behaviour change at all" — is the one gate that catches a check set with a hole
in it, and it has never run. *(completeness-is-the-missing-gate.md)*

**2. Give `spec_spans` to the stimulus author and s3.** Both receive zero today;
normalize, testplan, oracle and witness all receive them. The stimulus stage is
the one that must MAKE an activation occur, and it is also the consumer of
`opens_on`, empty on 71 of 89. Prompt tokens, no model calls. *(spans-are-executable-only-when-shallow.md)*

**3. Two mechanical gates on the activation, using regexes that already exist.**
Refuse an activation whose `text` names a declared port inside a conditional
clause when no temporal field mentions it — 15 of 89 on k1. And report an
`aborts_on` value shared by more than half the requirement set — 54 of 89 share
one pair. *(boilerplate-activations.md)*

**4. Ask spans for DEFINITIONS, not support.** Every one of the 169 span-overlap
edges across both runs is positionally adjacent; the graph is a layout graph.
Changing the question — "cite the span that defines each non-port term you use,
wherever it is" — makes the same field a typed, checkable, spec-derived
derivation edge. *(spans-build-a-layout-graph.md)*

**5. Record the derived signals.** `Env` already writes `dut_internal`; nothing
but the recording list stops it carrying `sSCL`. A definition can then be
DISCHARGED against the design's own signal instead of synthesised, which is
what keeps attribution intact. *(retire-the-ingredients.md)*

**6. Stratify, and let a violated assumption DISCHARGE its dependents rather
than fail them.** The spec supplies a defining requirement at every level of the
chain; h3 discarded all of them and nothing noticed the cost.
*(fixpoint-not-a-graph.md)*

## The constraint worth accepting rather than fighting

A property whose vocabulary is not in the port list cannot be asserted at the
port boundary until something defines it there. That is what "observable" means,
not a limitation of this pipeline. The three honest responses are: expose the
signal (a recording choice), discharge its definition once and depend on it, or
abandon the requirement explicitly.

The failure mode to eliminate is the fourth one, which is what happens today —
silently substituting the raw pin and shipping a confident wrong check. Twenty
of h3's 54 frozen oracles convict known-good RTL, and six of those clear the
moment the filtered value is supplied.
