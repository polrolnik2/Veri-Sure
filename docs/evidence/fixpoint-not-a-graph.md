# The discipline is fixpoint iteration, the material was there, and the pipeline threw it away

## The discipline exists and it does not need the graph

The general shape is **stratified bottom-up evaluation**: Datalog's semi-naive
iteration, chaotic iteration in dataflow analysis, worklist fixpoint algorithms.
The property that matters here is that **no dependency order is required as
input**. Run the whole fleet each round; keep whatever could be discharged from
the vocabulary currently available; publish those results into the vocabulary;
repeat until a round adds nothing. The dependency graph is the *output*.

That is exactly what dissolves the circularity in the graph-first approach: a
graph derived from the RTL cannot exist in a job whose product is the RTL, but
a fixpoint needs no graph at all — only a test for "could this be discharged
now", which is what the oracle stage's gates already are.

Cost is bounded by depth, not by requirement count: bit_ctrl's chain is 6 deep,
so at most ~6 rounds of a 118-way fan-out.

## The material was there. Every level had a definition.

Only a *definition* can be discharged into the next round's vocabulary
("`sSCL` **is** the majority of three samples"), not a use ("when `sSCL` is
high"). The specification supplies one at every level of the filter chain:

| depth | signal | defining requirement | h3's disposition |
|---|---|---|---|
| 0 | cSCL, cSDA | REQ-0076, REQ-0077 | **ABANDONED, ORACLE_INVALID** |
| 0 | filter_cnt | REQ-0016 | **ORACLE_INVALID** |
| 1 | fSCL, fSDA | REQ-0048 | **ABANDONED** |
| 2 | sSCL, sSDA | REQ-0051 | **ORACLE_INVALID** |
| 3 | dSDA | REQ-0051 | **ORACLE_INVALID** |
| 4 | sta_condition, sto_condition | REQ-0051 | **ORACLE_INVALID** |
| 5 | slave_wait, clk_en, cnt | REQ-0041, REQ-0015 | TRUSTED |

**Every definition at depths 0 through 4 was discarded.** The only survivors sit
at depth 5, resting on a chain that was never built. That is the mechanism
behind the earlier measurement that 28 requirements each had to re-derive the
filter and none succeeded: the requirement that would have defined it once was
in the discard pile, and nothing in the pipeline knew that discarding REQ-0051
cost 28 downstream requirements their footing.

Two gaps are real: `dSCL` and `scl_sync` have no defining requirement at all,
so a fixpoint would stall there and should say so rather than guess.

## Neither existing dependency field can order the rounds

* **`needs`** is `['refmodel', 'testplan']` on all 118 requirements — one
  distinct value. It is a pipeline stage list, not an edge.
* **`supports`** is a genuine requirement-to-requirement edge on 82 of 118, and
  it is the wrong relation. Layering by it puts REQ-0051 (defines `sSCL`) at
  layer 1 and REQ-0057 and REQ-0052 (both consume the filtered bus) at layer 0
  — consumers before producers — while REQ-0076, the chain's root, lands at
  layer 9. It records which paragraph elaborates which, not what derives from
  what. Ordering by it would be worse than not ordering.

So the fixpoint discipline is not merely applicable, it is the only one of the
two that can run here: the ordering it would need does not exist in the
artifacts and cannot be derived from the RTL.

## The one thing this needs that Datalog does not

In Datalog the rules are given and sound. Here each round publishes a
MODEL-AUTHORED definition, and an error at depth 2 silently corrupts every
requirement at depths 3 and up. So the admission gate is load-bearing in a way
it is not in the classical algorithm — a definition must pass witness, liveness
and must_fail *before* it enters the next round's vocabulary.

And the failure mode changes shape. Today a rejected requirement is simply
dropped. Under stratification a rejected *definition* must block its dependents
explicitly, because the alternative is what h3 did: discard REQ-0051, leave 28
requirements to invent their own filter, and report 54 TRUSTED.

Run with `python docs/evidence/stratify_check.py`.
