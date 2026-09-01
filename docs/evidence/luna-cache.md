# Luna caches on exact input, not on a prefix — measured, not inferred

The claim was carried as a finding with no experiment attached. It is correct,
and here is the experiment.

## The discriminating probe

One ~16k-token prefix, three calls, **all in one stage family so they share a
`prompt_cache_key`** — the way a real fan-out does:

| | gpt-5-mini | gpt-5.6-luna |
|---|---|---|
| warm-up | 0% | 0% |
| **A. same prefix, different suffix** | **99%** | **0%** |
| **B. byte-identical to the warm-up** | 99% | **100%** |

Row A is prefix caching and row B is exact-input caching. Luna has B and not A.
`gpt-5-mini` has both.

**My first attempt at this probe was wrong and would have exonerated Luna.** I
named the three calls `probe_warm`, `probe_prefix`, `probe_exact` — three
different families, so `_cache_key` gave each its own key and routed them to
different backends. Both models read 0% across the board. The fix is what
`_cache_key`'s own docstring already says: "it groups exactly what `shared_block`
shares: the stage FAMILY, not the stage."

## The same thing at run scale

Same stage family, same prompt shape, correct cache key on both:

| run | model | stage | calls | input tok | cached | hit |
|---|---|---|---|---|---|---|
| f1-i2c | gpt-5.6-luna | oracle | 20 | 205,360 | 10,158 | **5%** |
| c1-i2c | gpt-5-mini | oracle | 20 (first) | 188,604 | 86,528 | **46%** |
| c1-i2c | gpt-5-mini | oracle | 225 (all) | 2,172,181 | 1,736,320 | **80%** |
| c1-i2c | gpt-5-mini | normalize | 309 | 1,820,504 | 1,563,392 | 86% |

The 20-call rows are matched for warm-up position, so 5% against 46% is not a
cold cache.

## How the codebase handles it: the big model never runs a fan-out

Not by a cache trick — by architecture, and there is a test holding the line.
`test_no_fanned_out_stage_is_full_strength_by_default`:

> *"The expensive model runs whole-artifact calls, never per-item ones. A fan-out
> is 77 calls on i2c; the two stages that must not be downgraded -- the reference
> model and the witness -- are ONE call each."*

That is the whole answer. `full_strength_stages` is `{refmodel, witness}`, both
single calls, where prefix caching is worth nothing anyway because there is no
second call to share with. Everything fanned out runs `small_model`, which
caches. Three supporting pieces:

* `_cache_key` = `specflow:{family(stage)}:{model}` — routes same-prefix calls to
  one backend. Necessary, and unable to create prefix caching where the model
  has none.
* `shared_block` / `shared_prefix` — makes the prefix byte-identical across a
  fan-out, so there is something to cache.
* `deep_effort_stages = {"oracle"}` — the documented cheaper lever for exactly
  the quality problem that tempts one to promote the model: *"Raising effort on
  the same model buys some of the same depth without changing which model serves
  a 77-call fan-out."* It ships disabled (`deep_effort` defaults to `None`) and
  its docstring says the open question is whether it buys enough.

## What this prices for the oracle stage

Running `[O]` on Luna deliberately breaks that invariant. Scaling c1-i2c's own
oracle numbers: 2.17M input tokens, of which 1.74M were cached at 80%. On Luna
that 1.74M is paid in full, so the stage's full-price input goes from ~436k to
~2.17M — **about 5x, before Luna's higher per-token rate.** Repair rounds do not
recover it either: a repair prompt is *near*-identical, not byte-identical, so it
misses exact-input caching too.

The exact-input hit is not useless — a retry after a dropped stream, and
`ResumePort`'s replay, both resend byte-identical prompts. Neither is the
fan-out.
