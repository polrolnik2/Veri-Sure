# Where these operators differ from SVA

`specflow/refmodel/temporal.py` gives requirement checks an SVA-shaped
vocabulary over a Python trace. The shape is deliberate — the oracle author is
told to "reach for the operator you would reach for in SVA" — but the analogy is
not exact, and every place it breaks has cost a check at some point.

This file is the whole list. It exists because the *deliberate* divergences are
the ones that get quietly "fixed" back into defects by a reader who assumes SVA
semantics were the goal. They were not. Where this framework and SVA disagree,
each disagreement below says which one this project wants and why.

## Why it matters more than it used to

The combinators shipped unused. #97 measured v1's uptake at **0 of 306** —
the prompt offered them and every author hand-rolled index arithmetic instead.
Under v2, on c1-i2c:

| | |
|---|---|
| oracles calling at least one operator | **96 of 110 (87%)** |
| still hand-rolling `range()` | 16 (15%) |
| call sites | `worst` 108, `after` 95, `edges` 72, `throughout` 47, `eventually` 43, `pulse` 10, `stable` 9, `never` 5, `sequence` 4 |
| `after(..., until=)` | 65 |
| `throughout`/`never` with `after_activation=` | 39 oracles |
| `eventually(..., strong=)` | 36 |

So a defect in one operator is now a defect in dozens of checks at once. That is
what turned the list below from documentation into work.

---

## Part 1 — divergences that were DEFECTS, now fixed

Each was verified by running the operator, not by reading it. Pins live in
`tests/test_temporal.py` under "SVA soundness fixes".

### U1 · An empty row set returned `True` from `throughout` and `never`

`after_activation=True` on a one-row window leaves `w.body` empty. `throughout`
and `never` fell through their loops and returned `True`; `stable` already
returned `None`, and `eventually` returned `False`.

An invariant that held over zero rows did not hold. This was a **vacuous pass in
the module written to remove vacuous passes**, reachable by 39 of 110 oracles.

**Now:** all four return `None` with a detail saying "no rows".

### U2 · `pulse` counted a run that was already active

A window opening while the port was already at `active`, and never seeing it
rise, returned `(True, "pulsed once for 1 edge(s)")`. A port **stuck high**
therefore passed the check that exists to catch it.

**Now:** `pulse` abstains when the preceding sample — `w.prev` reading `w.rows`,
the activation row reading `w.body` — shows the port was already active. It is
`None`, not `False`: "it was already high when I started looking" is a fact
about the window, not about the design.

**And the guard reads `prev`, not just `rows[0]`.** A port that rises exactly as
the window opens *has* pulsed. `prev is None` — the window opens on the trace's
first row — is not evidence of a missing rise either: the design has just come
out of reset. Only positive evidence of "already active" abstains.

### U3 · `edges` raised on a row carrying no sample

`_val` returns `None` both for a port absent from a row and for one the harness
could not read — a DUT not exposing a declared output samples as `None`. Neither
is a transition, but `None > 0` raised `TypeError` on `rise`/`fall`, killing the
whole check. On `change` it was quieter and worse: an edge reported where the
sample went missing, and another where it came back.

**Now:** rows with no sample are skipped and `prev` is left standing, so
`0, <absent>, 1` is one rise at the third row.

### U4 · Two `until`s disagreed about the trigger row, silently

`after(..., until=)` never tests the release on the activation row; the `until()`
operator does. Both are right — `after`'s `until` DEFINES a window, so a release
already true at the trigger must not collapse it to nothing, while `until()`
asserts inside a window someone else defined and reads every row it is handed.

**Now:** the rule is stated at both ends, in both docstrings, with
`after_activation=True` named as the way to exclude the trigger in `until()`.

### U5 · `worst` named the first passing window

The failing and unknown paths name the **earliest** offending window, because
the first counterexample explains the rest. The all-passing path also returned
the first, telling a reader the requirement held at the earliest place it could
have — which reads as weaker evidence than was gathered.

**Now:** the all-passing path returns the last verdict.

---

## Part 2 — divergences that are DELIBERATE

These are not bugs and must not be "fixed".

### D1 · An unmatched antecedent is UNKNOWN, not a vacuous pass

`a |-> b` with no matching `a` is **vacuously true** in SVA; only
`cover property` reports the miss. `worst([])` returns `(None, None, "the
activation never occurred")`.

**Why ours:** this pipeline keeps "could not answer" separate from a verdict at
every gate, and `NOT_EXERCISED` exists to refuse exactly this. A vacuous pass is
a false green, and false greens are the failure class the project is built
against.

### D2 · No `##[n:m]`, no `[*n]` — cycle counts are absent on purpose

Phases 3–6 severed pacing from latency and stopped `latency_cycles` gating,
because the specification does not state edge counts. A check asserting one
either fails correct designs or asserts nothing.

`##1` (`nexttime`) survives because a row is a state, so "the next row" means
"the next time anything changed" — which is what "then" means in a
specification.

### D3 · A row is a STATE, not a clock tick

`transactional_view` collapses consecutive rows with identical inputs *and*
outputs, carrying `held`. `len(w.rows)` is not a cycle count and never was.

**Why ours:** the transactional criterion measured 3× better at separating good
RTL from bad (separation 40 against 15). Any counting you do must sum `held`.

### D4 · `after` opens one window per RISE; SVA opens an attempt per TICK

SVA starts a new attempt at every tick the antecedent holds. `after` opens one
per rising activation, so a condition true for forty consecutive rows is one
window, not forty.

**`overlap=True` does NOT restore SVA's model** — the rising test runs in both
modes. What it changes is where the scan resumes: after the row the window
*opened* on rather than after it closed, so windows may overlap in extent.
The prompt described this as "SVA's attempt model" and was wrong; corrected.

### D5 · An incomplete window is UNKNOWN

SVA passes attempts still open when simulation ends. `throughout`, `never`,
`until` and weak `eventually` return `None` when the window ran off the end of
the trace. Same reasoning as D1.

`strong=True` is the opt-in to convict on truncation, and it is the caller's
answer to a question about the **requirement** — does it oblige a response? —
not a default to reach for.

### D6 · `throughout` and `stable` take different arguments from SVA's

`throughout(w, p)` takes a window and a predicate where SVA takes a sequence on
each side. `stable(w, port)` is "never changed anywhere in the window", not a
sampled-value function evaluated at one tick.

### D7 · `edges` rise/fall mean increased/decreased

SVA's `$rose`/`$fell` are defined on the LSB. On a 1-bit port the two coincide
exactly, which is every port these requirements name an edge of. On a wider one
they differ and `change` is usually what is meant. Warned about at
normalisation, where the port width is known.

Also: `$rose` is a sampled-value function you drop into an expression; `edges`
returns a **set** computed over the whole trace up front, because `after` takes
a predicate over one row and cannot see the previous one. Test membership:
`r["edge"] in fell`.

### D8 · No `until_with`, and no `[->n]` — and these are different omissions

`until` is SVA's `until`, not `until_with`: `holds` need not be true on the row
where `release` fires, because the release is tested first. `until_with` is a
one-line variant to add when a requirement needs it.

**`[->n]` goto repetition — "the nth occurrence" — is NOT a cycle count**, so
D2's rationale does not cover it. It is simply not built. Recorded here rather
than left to look like a principled absence.

### D9 · No `disable iff`

Reset exclusion goes in the activation predicate, by hand. This is the construct
an SVA-fluent author reaches for and does not find.

### D10 · Sampling is post-edge on both sides; SVA samples preponed

`replay` records after `model.step()`. `Env` samples after `RisingEdge` plus
`Timer(1, "step")` (`tb/runtime.py:591`) — one simulator time step, deliberately,
because a read in the same delta as the edge returns the previous cycle's value.
SVA samples in the preponed region, i.e. *before* the edge.

**Why it matters beyond trivia:** the reference-model trace and the DUT trace
share a convention, which is what lets the same frozen check decide against
either one. An assertion ported to real SVA would see different values.

---

## What to do when a requirement needs something absent

Say so in the check's `reasoning` rather than approximating it. A check that
silently asserts a cycle count the specification does not state, or that
hand-rolls a goto repetition with index arithmetic, is the failure mode this
whole vocabulary exists to replace — and `range()` in an oracle is the tell.
