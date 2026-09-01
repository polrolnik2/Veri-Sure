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

### D2 · No `##[n:m]`; `[*n:m]` exists ONLY where the spec states the number

Phases 3–6 severed pacing from latency and stopped `latency_cycles` gating,
because the specification does not state edge counts. A check asserting one
either fails correct designs or asserts nothing.

`##1` (`nexttime`) survives because a row is a state, so "the next row" means
"the next time anything changed" — which is what "then" means in a
specification.

**AMENDED: consecutive repetition is now present, as `runs`.** The ban above is
on *inventing* pacing, and it was over-read as a ban on transcribing a duration
the specification gives. A requirement whose entire content is a threshold —
"a majority of the three consecutive samples" — cannot be checked at all
without one, because the property *is* the count. `normalize.Sustain` carries
`stated_by` for exactly this: if you cannot quote the phrase the number comes
from, D2's original rule still applies and you are guessing.

    runs(t, port, value=v, at_least=N)    (port == v)[*N:$]
    runs(t, port, value=v, at_most=M)     (port == v)[*1:M] ##1 (port != v)
    runs(t, port, value=v, at_least=N,
                          at_most=M)      (port == v)[*N:M] ##1 (port != v)

Three differences from the SVA it corresponds to, and none is incidental:

**The anchor is the START of the run, not the end.** SVA's `|->` fires where
the antecedent match *completes*, so `sig[*3] |-> p` evaluates `p` after the
third tick. `runs` returns the `edge` where the run BEGAN, and `after` opens
the window there. That is the useful anchor for a `sustains` activation — the
question is what the design did *in response to* the glitch, and the response
starts when the glitch does — but it is not `|->`'s anchor and a check
transcribed as if it were will read the outputs several edges early.

**The upper bound needs the terminator; the lower bound does not.** `[*1:1]`
alone matches the first tick of a run of any length, so bounding a run ABOVE
requires witnessing it end: `##1 !sig`. That is why a run still open at the end
of the trace is excluded under `at_most` and admitted under `at_least` — its
length is a lower bound, not a measurement. In SVA's vocabulary an upper bound
is a *strong* obligation and a lower bound is a weak one, and the asymmetry is
forced there for the same reason it is forced here. Admitting the trailing run
under `at_most` would let the trace running out masquerade as a short glitch,
which is a false activation, which is how a check convicts a correct design.

**It counts EDGES, and D3 bites hardest here.** `[*n]` counts clock ticks;
`runs` sums `held` over a state-compressed trace. A five-edge level is one row,
so a row count would call it a one-edge glitch — inverting precisely the
short-against-long distinction a majority filter is about.

One non-difference worth stating: SVA's `[*n:$]` is nondeterministic and is
usually wrapped in `first_match`. `runs` returns EVERY qualifying start, so
each opens its own window — which is `after`'s existing behaviour under D4, not
a new choice.

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
D2's rationale does not cover it.

**CORRECTED: it was built all along, and only unnamed.** `sequence` steps are
`##[1:$]` and each strictly advances, so `sequence(w, p, p, p, p)` *is* `p[->4]`
— verified on a trace pulsing four times: four steps pass, five stall. The
claim that it was "simply not built" was made from the operator table, where it
does not appear, rather than from the semantics, where it does. It is now
`nth(w, holds, n)`, sugar over exactly that.

**It counts OCCURRENCES where `runs` measures DURATION**, and they are the two
distinct cycle-accurate axes — neither substitutes for the other. The worked
case for this one is not in `i2c_master_bit_ctrl` at all: its FSM's observable
effects are output pulses, covered by `pulse(width=1)`, and its internal state
sequence has no port. It is the BYTE controller, where `dcnt` loads 7 and
decrements per shift, so "all eight data bits have been transmitted" and "the
ninth ACK/NACK bit" are `core_ack[->8]` and `[->9]`.

### D9 · `disable iff` exists, as `aborts_on`, and an aborted attempt is UNKNOWN

**This was an absence, and it cost checks.** Reset exclusion went in the
activation predicate by hand, or — far more often — it did not go anywhere, and
the abort was written as a close. `until` and an abort are indistinguishable
once folded together, so a strong obligation over a cut-short attempt convicts a
design for not doing what it was never asked. Measured on c1-i2c: **13
requirements closed on reset and 40 on `al`, all as `until`**, and REQ-0055
convicts the known-good RTL because an `al` pulse the design is *right* to emit
ended its window at edge 7 -- and the START it checks drives `sda_oen` low at
edge 28 and acks at edge 38.

**Now:** `Activation.aborts_on` carries it, `after(..., aborts=)` applies it, and
`Window.aborted` records it. Three semantics, each a deliberate choice:

* **An abort returns `None`, not `True`.** SVA's `disable iff` makes the attempt
  *never have happened*; here it is a fact worth reporting, so the verdict is
  UNKNOWN with the abort edge named. Same reasoning as D1 and D5 — "could not
  answer" stays separate from a verdict — and it keeps an aborted attempt out of
  the coverage numerator, where a silent pass would inflate it.
* **An abort BEATS a close on the same row.** A row satisfying both `until` and
  `aborts_on` is one instant read from two sides. The ambiguity resolves toward
  saying nothing rather than toward convicting.
* **It is a row predicate, not a continuously-evaluated expression.** SVA
  evaluates the `disable iff` condition at every tick of the attempt including
  the clocking block's own; `aborts` is tested per recorded row inside `after`'s
  scan, which is the same granularity every other operator here works at (D3).

**What is NOT derivable, and so is asked rather than inferred:** on 11 of those
40, `al` is the requirement's own declared observable — the response the check
exists to test. Rewriting those to aborts would delete the check. Whether a
condition ends a span or voids it is a reading of the sentence, which is why it
is a normalisation field and not a rule in this module.

Pins: `tests/test_temporal.py` under "`disable iff`: aborts_on";
`tests/test_normalize.py` for the schema and the gate.

### D10 · Sampling is post-edge on both sides; SVA samples preponed

`replay` records after `model.step()`. `Env` samples after `RisingEdge` plus
`Timer(1, "step")` (`tb/runtime.py:591`) — one simulator time step, deliberately,
because a read in the same delta as the edge returns the previous cycle's value.
SVA samples in the preponed region, i.e. *before* the edge.

**Why it matters beyond trivia:** the reference-model trace and the DUT trace
share a convention, which is what lets the same frozen check decide against
either one. An assertion ported to real SVA would see different values.

---

### D11 · `$past(p, n)` for n > 1 is absent, and on a compressed trace that is a FEATURE

`Window.past(port)` is depth 1 — the row before the activation — and there is
no `$past(p, 2)`. That looks like the obvious gap for a sample-history
requirement, because the canonical SVA transcription of the i2c glitch filter
is not a repetition at all:

    $countones({s, $past(s), $past(s,2)}) >= 2

**Measured against the requirement set, this is the only cycle-accurate axis
that pays.** Scanning all 127 c1-i2c requirements for what each absent SVA
feature would serve:

| absent feature | requirements that would use it |
|---|---|
| `[->n]` goto repetition, "the nth occurrence" (D8) | **0** |
| `##[n:m]` bounded delay (D2) | **0** |
| sample-history depth — `$past(p, n)` | **5** — REQ-0010, 0045, 0046, 0047, 0048 |

So D2's and D8's absences are vindicated rather than gaps: this specification
states no latencies and counts no occurrences. Every cycle-accurate requirement
it has is the same cluster, and they are all the majority filter.

**And a depth-n past is the wrong primitive HERE, for D3's reason.** `$past(p, 2)`
means two TICKS ago. The trace is state-compressed, so two rows back can be
forty edges back, and two edges back can be inside the row you are standing on.
An edge-accurate lookback would have to walk backwards summing `held` and split
a row to land mid-run — reintroducing exactly the index arithmetic the operator
set exists to keep out of checks, in the one place it is hardest to get right.

`runs` expresses the same property without that. "A majority of three
consecutive samples" and "a run shorter than the filter window" are the same
statement seen from two sides: SVA counts the samples because its trace is
ticks, and `runs` measures the duration because ours is states. The count is
recoverable from the duration; the duration is not cleanly recoverable from a
row-indexed past.

Left absent deliberately, then, and recorded here so it does not look like an
oversight — with the note that a design whose spec DID state "the nth
occurrence" would need `[->n]`, and nothing in the operator set approximates it.

## What to do when a requirement needs something absent

Say so in the check's `reasoning` rather than approximating it. A check that
silently asserts a cycle count the specification does not state, or that
hand-rolls a goto repetition with index arithmetic, is the failure mode this
whole vocabulary exists to replace — and `range()` in an oracle is the tell.
