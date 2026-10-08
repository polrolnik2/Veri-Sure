# Rework: the requirement oracles become a stage

**Status:** proposal. Nothing below is built.

## 1. The defect, stated precisely

`run_oracle_gen` is called from `_debug_turns`, which is called from
`run_refmodel` (`compose.py:367`, reached from `integration.py:485`). Oracle
generation is therefore *inside* reference-model generation.

Every other artifact in this pipeline is a **stage**: a prompt, a gate, a
bounded repair loop, a file on disk, and a `--reuse` path (`stage.run_stage`,
`integration._reuse`). The oracles have none of those. That is not a cosmetic
difference — the four open problems are each a direct symptom of it:

| symptom | the missing stage property |
|---|---|
| an oracle failing its gate twice is silently dropped (5 of 77 on h-i2c, landing as `UNDECIDED`) | a stage records a disposition for every item |
| nothing regenerates an `ORACLE_INVALID` / `VACUOUS` oracle; they only accumulate (4 → 5 → 8) | a stage has a bounded repair loop |
| over-strict oracles surfaced at turn 2, after the agent had spent two turns editing the model toward them | a stage gates *before* its consumer runs |
| `VACUOUS` wandered 16 → 18 → 16 with the oracle set frozen | a stage's gate does not re-run against a moving input |

And one more, which is the reason to do this rather than patch:

**Oracle isolation is currently a discipline, not a fact.** `build_prompt` has
no parameter a design could arrive through and a test reads the constructed
prompt back — but the model source exists in the same process, in the same call
stack, one frame up. Generating oracles *before* the reference model exists
makes isolation a property of time rather than of a signature. Nothing can leak
from an artifact that has not been produced yet.

## 2. Target order

    normalize → stimulus → [1] ORACLES → [2] refmodel → [3] debug
                                ↑                            ↓
                                └────── [5] feedback ── [4] mutation adequacy

### [1] Oracle stage (new)

**In:** requirements, normalized form, contract ports, `covers` (for `tp_uids`),
stimulus (to replay during verification).
**Out:** `specflow/oracles.json` — a disposition for **every** requirement.
**Never in:** the reference model. It does not exist yet.

Its gate is the verification the current design scatters through the loop:

| check | runs against | catches |
|---|---|---|
| `well_formed` | oracle, contract, testplan | structural nonsense |
| executability | the witness | raises, wrong shape, wrong arity |
| **over-strictness** | known-good control, else the **witness** | a demand no correct design meets |
| **vacuity** | requirement-derived variants | a check nothing can fail |

A failure is a repair prompt, not a discard: `trust.screen` already writes those
messages (`conflicts`) and the oracle-driven path currently throws them away.
Bounded retries, then a recorded verdict.

**The witness.** Over-strictness needs a design believed correct, and at this
point in the flow none exists. Where `benchmarks/controls/<top>/ref_model.py`
exists, use it. Otherwise generate one — today's `conform.conforming_implementation`
— and call it the *witness* rather than the "conforming implementation", because
it is not the deliverable: it is held out, never debugged, never shipped, and
exists only to bound the oracles from above. The two must be reported
separately and never summed; the witness shares an author with the oracles and
is strictly the weaker instrument.

**What this stage must NOT decide.** `NOT_EXERCISED` is a property of the
stimulus and the model together, so an oracle whose scenario no stimulus reaches
is still a *valid oracle*. It passes verification and is marked
trusted-but-unexercised. Rejecting it here would delete exactly the findings the
stimulus tool exists to act on.

### [2] Reference model — unchanged

Generation gated on `validate` alone.

### [3] Debug — no screening

The oracle set arrives verified and frozen. Per turn: decide → classify →
route → edit, one route per turn. **The per-turn verdict space shrinks from
seven to three** — `CONFORMS`, `VIOLATES`, `NOT_EXERCISED`. The oracle-quality
verdicts were settled in [1] and cannot move here, which removes the wandering
outright rather than compensating for it.

### [4] Mutation adequacy — after debug, not before

Mutate the **final** model; every mutant that changes what some oracle reads
must be caught by that oracle. A survivor means the oracle set is inadequate for
the model about to ship.

Why here: before debug the model is wrong, so "does this oracle fire on a
mutant" is confounded by its already firing on the base model — `sensitivity`
concedes this by only running on oracles that currently pass. After debug every
trusted oracle passes by construction, so all of them are eligible and the
question is clean.

### [5] Feedback — the loop that does not exist today

A surviving mutant goes back to [1], scoped to the requirements whose oracles
should have caught it, with the mutant as the counterexample in the prompt.
Re-verify, re-freeze under a new hash, re-run [3] and [4]. Bounded rounds; an
oracle strengthened to catch a mutant can become over-strict, which [1] then
rejects, so oscillation is possible and must be recorded rather than looped on.

## 3. Module impact

| module | change |
|---|---|
| `specflow/oracles_stage.py` | **new** — [1] end to end: generate, verify, repair, freeze, persist |
| `refmodel/oracle_gen.py` | absorbed into the stage; prompt unchanged |
| `refmodel/conform.py` | becomes the **witness** generator, called from [1] |
| `refmodel/freeze.py` | moves to [1]; semantics unchanged |
| `refmodel/variants.py` | used by [1] for vacuity and by [4] for adequacy |
| `refmodel/trust.py` | splits: model-independent gates → [1]; `sensitivity` → [4]; `screen` disappears |
| `refmodel/compose.py` | `_oracle_driven_turns` loses screening; `_debug_turns` and the judge path deleted |
| `refmodel/verdict.py` | enum unchanged; the per-turn classifier emits three of them |
| `refmodel/judge.py` | deleted, with `reconcile` |
| `integration.py` | new stage between stimulus (`:444`) and refmodel (`:485`) |

## 4. Sequencing — a working pipeline at every step

1. **Extract, do not move.** Pull [1] into its own module with a real gate,
   repair loop and artifact, still called from where it is. Pure refactor; the
   existing tests pin behaviour.
2. **Move the call site** into `build_artifacts`, before `run_refmodel`.
   Isolation becomes temporal. `--reuse` picks up `oracles.json`.
3. **Strip screening from the debug loop.** Per-turn verdicts shrink to three.
4. **Add [4]** as reported, non-gating, so its rate is measured before anything
   depends on it — the discipline step 3 of the migration plan used.
5. **Close [5]**, bounded.
6. **Delete the judge**, `reconcile`, `_debug_turns`.

## 5. Risks and open questions

1. **The witness costs a model call per run and is redundant where a control
   exists.** Recommendation: control when present, witness otherwise, both
   reported separately.
2. **The witness shares an author with the oracles.** Unchanged from today; a
   shared misreading passes. Mitigation, cheap and partial: generate it with a
   different model or effort than the oracles.
3. **Adequacy is scoped to one model.** [4]'s verdict is about the model it
   mutated, so it must re-run after every feedback round.
4. **Re-baselining.** Every measurement so far — h-i2c r0's
   `CONFORMS 25 / VIOLATES 9 / NOT_EXERCISED 18 / ORACLE_INVALID 4 / VACUOUS 16`
   — was taken on the interleaved architecture and is not comparable to the new
   one. One run on the new order is needed before any claim about it.
5. **Deleting the judge deletes `reconcile`**, the only oracle-repair path that
   has ever existed. [1]'s repair loop is its replacement and must be measured
   as such, not assumed.
