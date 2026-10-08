# Two stages never see the spec spans, and a span only helps when it is shallow

## Who gets `spec_spans`

Counted over the first twelve round-0 prompts of each stage in k1-dcfsm, by
`"role": "supporting"` entries:

| stage | supporting spans |
|---|---|
| normalize | 9 |
| s2 (testplan) | 9 |
| oracle | 9 |
| witness | 63 (all 89 requirements in one prompt) |
| **stimulus** | **0** |
| **s3 (coverage)** | **0** |

The stage denied them is the one that has to MAKE the activation happen in a
trace. And it is the same stage that consumes `activation.opens_on`, which is
empty on 71 of 89 here. So the stimulus author is blind twice over: no
structured opening condition, and not the sentence that states what the
condition is.

## Why a span helped here and did not on i2c

The oracle for REQ-0007 built its window out of supplied material, not guesswork
-- `dc_en == 1 and dcqmem_cycstb_i == 1` is a verbatim `spec_spans` quote with
`role: "supporting"`, arriving twice (also as REQ-0006 in
`<linked_requirements>`), with `dc_addr == start_addr` coming from the
`observed_via` route's own `shows` field.

That works because of what the span NAMES. Counting the deepest derived signal
each span mentions, against `rtl_depth.py`'s layering:

| | spans naming a derived signal | of those, deepest named at depth >= 2 |
|---|---|---|
| h3-i2c | 32 | **23 (72%)** — 18 of them at depth 5 |
| k1-dcfsm | 49 | **4 (8%)** — 39 of 49 sit at depth 1 |

k1 names derived signals MORE often, so a naive count makes it look worse. What
differs is the depth: `load`, `store`, `saved_addr_r`, `cache_inhibit` are one
hop from ports, and a sentence about them is a guard an author can write.
"sSCL is the majority of three consecutive fSCL samples" names a depth-2 signal
that rests on a depth-1 signal that rests on a counter -- quoting it into the
prompt buys nothing, because the author still cannot read any of it.

**A supporting span is executable only when the signals it names are shallow.**
h3 did not withhold information; it supplied information at a depth where
supplying it does not help. That is the mechanism behind the depth measurement,
and it is why depth predicts convergence rather than merely correlating with it.

## What follows

Give `spec_spans` to the stimulus author and to s3. It costs prompt tokens and
no model calls, and on this design 59% of spans name a declared port outright --
which is exactly the material a stimulus author needs to drive an activation it
was otherwise told nothing about.
