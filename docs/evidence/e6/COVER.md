# The minimum cover: blindness preserved exactly, and audit falls

`FRONTIER.md` reduced the whole frontier to one sentence -- the checks that convict
golden are also the checks that separate the population -- and showed every
selection rule trading one column for another. This is the rule that cannot,
because what it drops is defined as what changes nothing.

    does this body separate any cell that no other KEPT body separates?

If not, dropping it leaves the separated SET unchanged, so blindness is identical
by construction -- and one fewer body is one fewer chance to convict a correct
design, because rejections union.

## Greedy set cover over the disagreement cells

    pool (from `oracles_stage.admitted_pool`)   333 bodies
    disagreement cells                          26,549
    cells the whole pool separates               24,969

    greedy cover                                 34 bodies
    ...reach the pool's ENTIRE separated set     all 24,969
    span floor: requirements with no body in it  91, best contributor restored
    final set                                   125 bodies

**THIRTY-FOUR BODIES OF 333 CARRY EVERY SEPARATION THE POOL ACHIEVES.** The other
299 are redundant with respect to blindness -- not silent, not wrong, just adding
no cell another body has not already separated.

    configuration      bodies   span            blindness       audit
    the whole pool        333   0.9737 MET      0.0595 MET      4/45 = 0.0889
    the greedy cover      125   0.9737 MET      0.0595 MET      1/38 = 0.0263

    blindness identical?  0.0595 vs 0.0595   YES

**Span held, blindness held to four places, audit 0.0889 -> 0.0263.** Three of the
four convictions gone at zero cost in either other column, which no rule before
this managed.

    remaining   REQ-0055 [behavioural]   the one counted conviction
                REQ-0058 [scaffolding]   uncounted by the audit column

## Why it cannot trade, stated as the three invariants

  * **Blindness.** Greedy cover changes how MANY sets are used, never which cells
    the union holds; it stops when no remaining body adds a cell. So the separated
    set is bit-identical and so is blindness.
  * **Span.** The per-requirement floor gives any requirement whose bodies all
    became redundant its best single contributor back, so every requirement covered
    by the pool is covered by the cover.
  * **Audit.** The kept set is a SUBSET. A subset of objectors cannot convict more
    than the whole, so audit can only fall or stay.

Everything it reads is the spec-derived population: cells from the designs,
per-body separation from the shipped `V.blind_at` asked with one body's table
alone. The audit column is scored afterwards and never consulted.

## The floor's two keys, and why the second is not decoration

"Best contributor" is `(most cells separated, then fewest population
convictions)`. The first key leaves ties -- among 91 floored requirements many
bodies separate the same number of cells, and a single-key `max` then takes
whichever came first, which is source order. The second prefers the less
over-strict body where separation is already equal, so **it cannot cost a cell.**

This is `max_convictions` used as a tie-break INSIDE a requirement, never as a
global filter -- which is what made it destroy separators in `SELECT.md`
(`effective_size` 273 -> 141). Separation is fixed by the first key before the
second is consulted.

## The tie-break, measured: it moves `effective_size` and not the audit column

Adding "fewest population convictions" as the floor's second key moved
`effective_size` 106 -> 105 and left audit at **1/38, the same two convictions**.
So the tie-break is correct -- it prefers the less over-strict body where separation
is equal, and it cannot cost a cell -- and it does not reach REQ-0055.

The reason is informative: the floor only applies to requirements with NO body in
the cover, and REQ-0055's body is IN the cover. It is kept because it separates
cells, not because a floor put it back.

## What remains, and it is one requirement

REQ-0055: `normalize` set `observable: ['cmd_ack']` for a
requirement about pausing a TIMING COUNTER, and the accepted body computes the
invariant under both temporal readings and keeps whichever fails
(`LAST-CONVICTION.md`). `OBSERVABLE-LICENCE.md` measures the field at 34% of forms
unlicensed, and all 24 corpus bodies across the seven unlicensed-observable
requirements read the port `normalize` named -- so no selection over this corpus
reaches it. The fix is upstream in `normalize` and costs a model call.
