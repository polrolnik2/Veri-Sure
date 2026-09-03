# Transitive citation is free, predicts nothing today, and buys a refusal

## Cost is not the objection

Transitive closure of the span-citation graph, per requirement:

| | closure size | chain depth | extra prose |
|---|---|---|---|
| h3-i2c | mean 2.1, max 11 | mean 1.8, max 11 | mean 644 chars, max 3394 |
| k1-dcfsm | mean 1.3, max 6 | mean 1.1, max 6 | mean 419 chars, max 2018 |

Handing every author its full citation closure costs a few hundred characters.
Whatever the objection to doing it, prompt budget is not it.

## On the current graph, chain depth predicts nothing

h3's 54 frozen oracles, bucketed by citation-chain depth, against a 37% base
rate of convicting golden:

| chain depth | frozen | convict golden |
|---|---|---|
| 0–1 | 38 | 13 (34%) |
| 2 | 8 | 5 (62%) |
| 3+ | 8 | **2 (25%)** |

Depth 3+ sits *below* the base rate, and n = 8 in both deep buckets. The signal
is absent. That is consistent rather than surprising: the graph is positional
(`spans-build-a-layout-graph.md`), so its "depth" counts paragraph chaining, not
derivation. It measures the wrong quantity, so it predicts nothing — which is
one more reason the edges have to become definitional before any of this works.

## And the intervention has a poor prior

Two experiments already tested "give the author more text about the chain":

* **Arm B/C** handed over the ENTIRE specification as a tie-breaker. Zero
  oracles reconstructed the filter, though its definition was present verbatim.
* **Arm D** handed over the full annotated normalized form of every linked
  sibling. Convictions went 3/6 to 3/6 — no movement, with per-cell churn
  dominated by the author's own sample variance.

A better-chosen chain is the same intervention with better inputs, which arm D
cannot rule out. Arm C is the harder counterexample: the text was there and
nothing was built from it.

## What changes at depth 2, and it is not more prose

At depth 1 the span **is** the guard. dc_fsm's "the FSM accepts a new request
only when dc_en=1 and dcqmem_cycstb_i=1" is directly writable, and k1's oracle
author wrote it. At depth 2 and beyond the author must IMPLEMENT the chain, and
that burden is what three measurements say does not get paid.

The version that works passes the discharged **implementation**, not the prose:
REQ-0051's frozen `decide` becomes callable, so REQ-0057 calls rather than
rebuilds. That is the stratified fixpoint, and transitive citation is how its
edges get found.

## The value your proposal buys anyway

Independent of whether any check improves: presenting the closure tells the
author **that a chain exists and how deep it is**. Today the i2c author
silently substitutes `scl_i` for the filtered bus and emits a confident wrong
check. With the chain visible, "this rests on N levels of derivation you cannot
read" is grounds for an explicit UNOBSERVABLE.

That converts a silent wrong answer into a refusal. Given that 20 of 54 frozen
oracles confidently convict known-good RTL, and 6 of those clear the moment the
filtered value is supplied, an abandonment would have been strictly better than
the check that shipped.
