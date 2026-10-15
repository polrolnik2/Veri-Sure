# Why REQ-0010 got no normalization, traced to the response

REQ-0010 survived into the frozen suite as an INVERTED check -- it passes run 10,
which deleted the input glitch filter, and convicts the golden design that has
one. It has no entry in `normalized.json`. This is the trace of why, replayed
against the responses the live c1-i2c run actually recorded.

## The oscillation, and what each round now does

Four rounds were recorded and all four were spent. Replaying each through the
current parser and gate:

| | r0 | r1 | r2 | r3 |
|---|---|---|---|---|
| REQ-0010 | 1 error | **PASS** | 1 error | **PASS** |
| REQ-0017 | 1 error | **PASS** | 1 error | **PASS** |
| REQ-0078 | 1 error | **PASS** | 1 error | **PASS** |
| REQ-0100 | 1 error | **PASS** | 1 error | **PASS** |
| REQ-0048 | 1 error | parse fail | 1 error | 1 error |

Round 0 gives no route and draws the base-case error. Round 1 gives
`observed_via` as a **dict keyed by port name** -- which used to be a parse
failure, short-circuiting the gate to a raw pydantic complaint, so round 2 saw
a narrower message, emptied the field, and reproduced round 0. Two wrong shapes
trading places until the budget ran out.

Both halves of that are now closed and they are independent:

* the shape **coercion** in `NormalizedRequirement` recovers the dict form
  losslessly, so round 1's answer parses;
* the shape **explanation** (`_OBSERVED_VIA_TASK` / `_OBSERVED_VIA_SHAPE`) is
  now shown at both points a model can reach without having seen it, so a round
  that guesses the dict is told what to write instead of guessing again.

**Four of the five requirements lost this way pass the gate at round 1 on their
own recorded answers.** They needed one repair round, not four.

## REQ-0048 is a different fault, and a worse one

Its round 1 has the right shape. The response is invalid JSON: the model wrote

    "reasoning": "... add until [{"busy":0}] so the window closes ..."

with the inner quotes unescaped, which ends the JSON string early. Recovery
scraped the balanced `{"busy":0}` out of the middle of the broken document --
and **`NormalizeOutput` validated it**, because both its fields carry defaults.
The result was an empty output with empty reasoning, indistinguishable from a
model that answered nothing, so the next round was handed a complaint about
CONTENT (*"observable at ['busy'] but no route given"*) for a response that had
supplied the route. It was asked to fix a field it did supply.

That is the same short-circuit the shape gate exists to prevent, one layer up:
a syntax fault reported as a content fault. `parse_response` now rejects an
extraction carrying neither `normalized` nor `reasoning`, names the keys it
actually recovered, and says to escape inner quotes. **3 of the run's 348
recorded normalize responses took this path** (REQ-0048 r1, REQ-0057 r0,
REQ-0098 r0); only REQ-0048's was fatal, because the other two were round 0
and recovered later.

An empty `normalized` WITH reasoning is still a real answer and is untouched --
that is the only honest way to report a requirement that cannot be normalized.

## What the recovered REQ-0010 says, and the gap it exposes

REQ-0010 is the same requirement as REQ-0046 -- the three-sample majority
filter -- with the same three observables. Its recovered form:

    activation.inputs   {nReset: 1, rst: 0, ena: 1}
    activation.sustains []                       <- the field did not exist yet
    observable          [busy, dout, al]
    observed_via        3 routes, when="" on ALL THREE

Both fields that the REQ-0046 work showed to be load-bearing are empty here, and
for different reasons. `sustains` did not exist when this ran. **`when` was
never asked for**: `gate_one` checked `port`, `through_req` and `shows`, and
never `when`.

Across the frozen set that is **180 of 238 routes (76%), spanning 76 of 122
requirements**, carrying an empty `when`.

This is not cosmetic. A route with no `when` tells the check author to watch a
port with no scope, and an unscoped observation cannot separate a response to
this requirement from anything else the design does in the same window --
measured, in `req46.md`, as a check that convicted the golden design on an
unreset `dout`'s power-on capture in 180 of 311 testpoints where no glitch was
present at all. `gate_one` now rejects an empty `when`, with a deliberately low
bar: restating the activation is an acceptable answer, saying nothing is not.

**Blast radius, replayed over each requirement's final recorded round: 78 of
127 fail ONLY on the new check**, 33 pass, 16 already failed for other reasons.
That is a large number to send into repair and it has not been run live.
