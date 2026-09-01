# RETRACTED IN PART: Luna caches a prefix fine — it needs a `developer`-role item, not a flat string

Everything below through "So how DO you run Luna on this pipeline?" measured
real, correct numbers under a request shape nobody had varied: `input` sent as
one flat `user` string (or one flat `user` item in a list — tried too, see
below). Every conclusion drawn from that shape is retracted as a description
of Luna's cache; it stands only as a description of *that shape's* cache
behaviour, which turned out not to be the one that matters.

**The missed variable.** `eda_agent`'s ReAct agents never showed this problem
because they never sent that shape: `to_responses_input` maps the agent's
`system` role to Responses' `developer` role on every turn, so their shared,
stable content (system prompt + tool schema) has always gone out as its own
`developer`-role item, separate from the `user` turn. `specflow`'s stages
build one string (`shared_block(...) + item_text`) and send it whole. Nobody
had isolated "structured `input`" from "`developer`-role item" as two
different things until asked to check specifically whether what already works
for eda_agent's multi-turn agents would work here.

**The clean isolation**, live, nonce prefix never seen before, matched
cache-key family, `gpt-5.6-luna` only, one variable changed at a time:

| shape | cached |
|---|---|
| flat `user` string (what `specflow` sends today) | 0% |
| structured list, one `user` item (prefix+suffix combined) | 0% |
| + streamed + `include: reasoning.encrypted_content`, still one `user` item | 0% |
| `developer` item (prefix) + `user` item (suffix), nothing else changed | **99.6%** |

Streaming and `include` are not the fix -- they read 0% on their own, same as
the flat string. The `developer`/`user` role split, alone, with NONE of
eda_agent's other machinery, is what reads 99.6%, on the same nonce
discipline that read a clean 0% every time before this. Full sequence,
`effort=low`, no tools, `prompt_cache_key` matched to one family per
condition:

    -- split_roles ONLY (no stream, no include) --
    call 0: input=6080 cached=0     (0.0%)
    call 1: input=6080 cached=6057  (99.6%)
    call 2: input=6080 cached=6057  (99.6%)

    -- stream+include ONLY (single user item) --
    call 0: input=6075 cached=0  (0.0%)
    call 1: input=6075 cached=0  (0.0%)
    call 2: input=6075 cached=0  (0.0%)

Confirmed once more end to end through the real `eda_agent` transport
(`SafeReActAgent` + `OpenAIResponsesModel`, WITH a live tool schema, WITH
streaming) before the isolation above traced it down to the role split alone:
0% cold, then 99.7% / 99.7% on a fresh nonce system prompt.

**What retracts, what survives:**

* RETRACTED: "Luna does not cache a shared prefix on this gateway... nothing
  left to test client-side" (this doc's own prior conclusion, one commit
  before this one). It caches at parity with gpt-5-mini once the shared part
  is a `developer` item.
* RETRACTED as a general claim, survives as a shape-specific measurement: "Luna
  caches on exact input, not on a prefix" (this doc's title until this
  section). True of a flat `user` string; false of a `developer`+`user` split.
  The exact-input numbers (row B, byte-identical, 100%) are unaffected --
  those were never about prefix vs. developer-role, just about repeats.
* SURVIVES UNCHANGED: the seeding retraction (`previous_response_id` does not
  populate the cache at any delay) and the routing-key conflict finding
  (`prompt_cache_key` alongside `previous_response_id` costs the hit). Neither
  experiment touched the role of the shared content, so neither is affected
  by this correction.
* REOPENED, NOT ANSWERED: "So how DO you run Luna on this pipeline?" below
  recommends scoping Luna to the 13 repair calls specifically *because*
  caching a 225-call fan-out looked impossible. That premise no longer holds.
  Whether Luna belongs back on the full fan-out is a run-scale question this
  doc does not answer -- the numbers above are a ~6k-token nonce prefix with
  filler content and 3 calls, not a 225-call run against real oracle prompts
  under real fan-out concurrency. Re-measure at run scale before reversing
  that recommendation.

**The fix, shipped**: `PortSettings.developer_role_prefix` (`specflow/model_io.py`),
off by default pending the run-scale re-measurement above. When on, a prompt
built with `fanout.shared_block`'s sentinel is split at that boundary into a
`developer` item and a `user` item instead of sent as one flat string; a
prompt with no sentinel (a whole-artifact stage) is untouched. `_seed_id`'s
dead-but-kept splitting logic now shares the same splitter
(`_split_shared_prefix`) so the two ways of finding the boundary cannot drift
apart.

---

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


## The attempted fix, and its retraction

`previous_response_id` looked like the way to reach the exact-input hit: seed
the shared prefix once with `store=True`, then send each item with only its own
text, so the carried context is a byte-identical server-side object.

**A first A/B said it worked and it was wrong.** Four items on luna:

| | input | cached | full-price |
|---|---|---|---|
| flat | 33,752 | 0 | 33,752 |
| seeded | 33,860 | 33,848 | **12** |

The prefix in that test had already been sent about ten times by earlier probes
in this session, so the gateway held it warm for reasons that had nothing to do
with seeding. Repeating it with a nonce-prefixed, **never-before-seen** prefix:

    item 1  input=11989  cached=0   (0%)
    item 2  input=11989  cached=0   (0%)
    ...
    item 6  input=11989  cached=0   (0%)

**Seeding does not populate the cache.** The claim is withdrawn, and
`PortSettings.prefix_seed` ships off with the refutation in its own docstring
rather than in a commit message. The warm-up hypothesis is dead as well: seeded once, then queried
at t+0, +60s, +120s and +240s against the same seed, **0% at every one**.

### One real finding survives

With `previous_response_id` set, sending `prompt_cache_key` costs the cache hit
outright. Same seed, two continuations, everything else held:

| request | cached |
|---|---|
| `previous_response_id` alone | 100% |
| + `include: reasoning.encrypted_content` | 100% |
| + streaming | 100% |
| **+ `prompt_cache_key`** | **0%** |

Both are routing hints and they disagree: the seed lives on the backend that
served it, and the key sends the request to whichever backend it hashes to.
Streaming and the encrypted reasoning items are harmless. The transport drops
the key on the seeded path -- it matters the moment seeding works, and is
silent when it does not.

### Methodological note

Two probes in this sequence were wrong before they were right, both the same
way: an earlier identical request had warmed something. The first named three
calls in three different stage families, so each got its own cache key and BOTH
models read 0%, which would have exonerated luna. The second reused a hot
prefix, which would have shipped a no-op as a fix. **A cache measurement is only
valid against an input the backend has never seen** -- hence the nonce.

## Reconfirmed live, through `ApiPort._complete_responses` itself

The open question after the above was whether the 0% was a property of luna, or
an artifact of whatever ad-hoc script produced the earlier numbers -- neither is
checked in, so neither could be re-run. This time the measurement goes through
the actual production transport, unmodified: `specflow.model_io.ApiPort` with
`api_flavor="responses"`, which is `_complete_responses` -- streamed, chunked,
`reasoning.encrypted_content` carried on continuation, the exact same
`stream_policy` module `eda_agent`'s multi-turn ReAct agents share. Not a
simplified stand-in for the hardened path; the hardened path itself.

Same discipline as before -- one nonce per run, one stage name per condition (no
per-item suffix, so `family()` cannot split it and every call in a condition
shares one `prompt_cache_key`), 2 warm-up + 3 measured calls, `effort="low"`:

    nonce=1454eeab359daeb3  prefix chars=26895

    stage                      model          calls  input   cached  hit%
    liveprobe2_mini_responses  gpt-5-mini         5  40,360  31,744  98.3%
    liveprobe2_luna_responses  gpt-5.6-luna       5  40,360       0   0.0%

mini's 98.3% is the positive control: it lands within a point of the original
99%, on the same transport, in the same run, so the harness is not the reason
luna reads zero. luna's 0.0% is exact -- not a small residual, zero cached
tokens out of 40,360 measured, across all 5 calls including the two nominal
"warm-up" ones. The endpoint question (does luna cache over `/v1/chat/completions`
instead) is now moot for a different reason than expected: this session's
ambient `OPENAI_EXTRA_BODY` carries `reasoning.effort="xhigh"`, which
`_responses_body`'s deep-merge (by design, see its docstring) always lets win
over whatever effort a caller passes -- and `gpt-5-mini` rejects `xhigh` on
chat-completions ("`Unsupported value: 'xhigh'`"), while luna silently accepts
it. That is exactly the failure mode `_responses_body`'s own comment predicts
("this container is launched with exactly that value... harmless because
`.env.local` clears the key") for a container with no `.env.local` -- which
this one has none of. Clearing `OPENAI_EXTRA_BODY` for the run above is what
made mini answer at all.

**What this run actually established, kept after the correction at the top of
this document:** the 0% is not an artifact of an unreproducible probe or a
broken harness -- mini's 98.3% positive control, in the same run, on the same
transport, proves the measurement apparatus is sound. What it does NOT
establish, and what the paragraph that used to stand here claimed, is that
"nothing left to test client-side" and that luna cannot cache a shared prefix
at all. It cannot cache *this shape* of shared prefix -- one flat `user`
item, whether a bare string or a single-item list, streamed and chunked or
not. See the retraction at the top of this document for the shape that
reads 99.6%. The `OPENAI_EXTRA_BODY`/`xhigh` finding above is unaffected by
the correction and stands as a genuine operational trap for any container
launched without `.env.local`.

## So how DO you run Luna on this pipeline?

Not on the fan-out. The affordable place is the repairs, and the numbers say so
plainly. Counting c1-i2c's recorded calls by round:

| stage | calls | first pass | repairs |
|---|---|---|---|
| oracle | 225 | 212 | **13 (6%)** |
| normalize | 309 | 127 | 182 (59%) |
| whole run | 2578 | 1801 | 777 (30%) |

**The oracle stage's repairs are 13 calls.** Putting luna there instead of
across all 225 is a 17x reduction in luna traffic, and it aims the spend exactly
where the standing finding already places the benefit -- a stronger author helps
on REPAIR, not on generation. The uncached-prefix penalty is then paid 13 times
rather than 225.

What it needs: `run_stage` takes ONE port and uses it for the first pass and
every repair round alike, so the split does not exist yet. That is the change
worth making, and it is smaller than anything attempted above.

Two levers deliberately not taken. **Trimming the shared prefix** would cut the
cost on every model but changes what the author is told, which is an instrument
change dressed as an optimisation. **Batching k items per call** amortises the
prefix k-fold and is model-agnostic, but this pipeline has already measured
monolithic per-item calls degrading badly at scale -- on 167 testpoints, three
rounds returned stimulus for ten of them and the fourth returned all 167 with
one step each.
