# Getting each stage to converge, and RTL out the other side

**Status:** plan. Phase 0 and Phase 1 are DONE and their results are recorded
inline; Phase 2 steps 8-10 are landed (commits 9ffe2a8, 268ad11); step 11 is
running. Phase 2b is triaged and unbuilt. Phases 3-5 are unbuilt.
**Supersedes nothing.** `oracle-stage-rework.md` describes the architecture this
plan runs on; every measurement below was taken after that rework landed.

---

## Where this starts

Six full runs on `i2c_master_bit_ctrl` (n, q, r, s, t, v/w). The oracle stage
works, the debug loop works, and **no run has produced RTL**. The reason is not
model quality, and finding that out took measuring the gate rather than the
oracles:

`refmodel_gate` blocks on 34 issues and only **9 (`VIOLATES`) are anything the
debug loop can clear**. The rest are carried out of `[O]`:

| verdict | count | who can act |
|---|---|---|
| VIOLATES | 9 | the loop — and ~7 of those are over-strict |
| VACUOUS | 11 | `[O]` regeneration |
| UNOBSERVABLE | 7 | spec authoring — a human, by design |
| NOT_EXERCISED | 5 | the stimulus route |
| ORACLE_INVALID | 1 | `[O]` regeneration |

`verdict.BLOCKING` is every verdict except `CONFORMS`, so G4 requires all 77
requirements discharged by a conforming oracle. **At zero VIOLATES there would
still be 25 blockers.** s-i2c had the best model of the series — 57/168 at
separation +24, the only positive separation ever measured — and produced
nothing.

### What the series measures

`golden_check`, cv-j3's 168-testpoint suite at `--hold 60`:

| run | golden | separation | dead oracles | discrimination |
|---|---|---|---|---|
| control (known-good) | 168/168 | +140 | — | — |
| g-i2c | 31/168 | −41 | — | — |
| n-i2c | 30/168 | −50 | 20/70 | 3 (4%) |
| q-i2c | 29/168 | −38 | — | — |
| r-i2c | 31/168 | −30 | 9/56 | 7 (12.5%) |
| **s-i2c** | **57/168** | **+24** | **6/58** | **10 (17%)** |
| t-i2c | 30/168 | −24 | 5/58 | 12 (21%) |

**s-i2c and t-i2c drew from the same 58 oracles and scored 57/168 and 30/168.**
Generation variance is large enough that every separation figure here is n=1 and
none of them is yet a rate. That single fact constrains how much any other
number in this document is allowed to carry.

---

## Phase 0 — DONE, and mostly negative

1. **`reconsider` alone: REFUTED.** `control_violates` 15 -> 15, discriminating
   10 -> 10. It rewrote 3 oracles, fixed REQ-0014, broke REQ-0003. Attributing
   t-i2c's net zero to `strengthen` fighting it was WRONG -- the relax edge does
   not work on its own either. **Do not retry it; it needs a different idea.**
2. **`--advisory-unobservable`: WORKS.** w-i2c's gate reads `error 25 /
   warning 7`. The 7 UNOBSERVABLE stop being errors.
3. **`golden_check` on w-i2c: 30/168, separation -29.** Which, with s-i2c at
   +24 and t-i2c at -24 from the SAME 58 oracles, is what overturned the +24
   headline. s-i2c was the outlier.

The original questions, kept for what they were asking:

1. **`reconsider` alone.** t-i2c ran it beside `strengthen` and netted zero — 2
   over-strict oracles fixed, 2 created, `control_violates` 15 before and 15
   after. That is the oscillation the rework predicted, arriving as a net zero
   because both directions were applied to one set at once. `strengthen` is what
   *manufactures* over-strictness: tighten until you catch this mutant, and a
   check tightened past what the requirement states is one no correct design
   satisfies. The two are now gated apart. **Number: does `control_violates`
   fall from 15?**
2. **The gate.** Does `--advisory-unobservable` open G4? The mechanism is
   verified in isolation — those 7 become warnings and `has_errors` returns
   False when they are the only blockers — but no run has ever reached a gate
   with it on.
3. **`golden_check` on w-i2c's model**, against the table above.

---

## Phase 1 — offline measurements, zero model calls

These are free and two of them can invalidate Phase 2, so they come first.

4. **Liveness on w-i2c's final set.** Dead-oracle count against s-i2c's 6.
   Catches the failure mode where `reconsider` relaxes a check into deadness.
5. **Attach precision — the f-i2c guard.** Hand-write necessary inputs for 10 of
   the 57 no-input requirements, attach, and count how many oracles actually
   fire versus return `ok=None`. **This settles Phase 2's risk before the prompt
   is touched.** The prior measurement it guards against: deciding oracles
   against every testpoint traded 1 true finding for 27 false on f-i2c.
6. **Replicate `golden_check` on models already on disk.** Every separation
   figure is a single draw. Re-scoring costs nothing and bounds how much of ±24
   is noise.
7. **Classify structural requirements.** How many of the 77 are interface facts
   rather than behaviours — REQ-0019 is *"the module provides a 4-bit input
   named cmd"*. No runtime oracle can decide that and none needs to; the
   contract enforces it at elaboration.

---

## Phase 2 — normalization under-extracts activation inputs

The largest lever, and it is one clause in one prompt.

### The measurement

| | |
|---|---|
| activations **with** `inputs` | 20 of 77 |
| activations **without** | 57 of 77 |
| …of those, naming a command or reset **in their own activation text** | **32** |

Several state the encoding literally and still leave the field empty:

```
REQ-0001  "A START (cmd = 0001) or STOP (cmd = 0010) command is issued"       -> inputs={}
REQ-0040  "A supported (non-NOP) command is presented while enabled (ena=1)"  -> inputs={}
REQ-0039  "cmd holds a recognized command (START=0001, STOP=0010, ...)"       -> inputs={}
REQ-0043  "during the controller's READ command data-bit phase"               -> inputs={}
```

Against `REQ-0003` — *"READ"* — which normalized to `{'cmd': 8, 'ena': 1}`. Same
command, extracted for one and not the other.

### The cause

One clause in `normalize.py`'s SYSTEM prompt (~line 112):

> `"while the state machine is idle"` and `"after arbitration has been lost"`
> **cannot**, because they are about internal state rather than about what is
> driven. Leave `inputs` empty in those cases.

The model follows it correctly. The clause conflates two different conditions:

* **not statable as inputs at all** — true for *"after arbitration has been
  lost"*; no input drives it;
* **necessary but not sufficient** — you cannot be in the READ data-bit phase
  without `cmd=READ` having been driven.

`check_static` (`obligation.py:130`) tests set membership per port — *is this
value driven anywhere in these steps*. It gates **attachment, not truth**. After
attaching, the oracle still runs and returns `ok=None` if the scenario did not
occur, so a false attach costs one replay, not a false verdict. The prompt's
stated fear — *"a later stage will drive them and conclude the scenario was
staged when it was not"* — is correct for a sufficiency claim and does not apply
here.

### Blast radius

57 of 77 requirements cannot receive new stimulus through `_attach`, capping the
stimulus route at **26% of the suite**. That is why t-i2c added 48 testpoints and
moved `NOT_EXERCISED` by zero, and v-i2c added 12 and did the same.

### Steps

8. Rewrite the clause to ask for input conditions **necessary** for the
   activation, keeping the genuine exclusion for activations no input can reach.
9. Re-normalize — 77 small-model calls.
10. **Gate on measurement:** how many of the 57 gain `inputs`? If it does not
    clear ~32, the diagnosis is wrong and this stops here rather than paying for
    a pipeline run on it.
11. One fresh full run (~500 calls) — re-normalizing invalidates the frozen
    oracle set, because the activations the oracles were written against change.
    **Decider: `NOT_EXERCISED`, which has never once fallen from added
    stimulus.**

---

## Phase 2b — over-strictness is three phenomena, and 13 of 15 are mechanical

The blocker recorded above as having no mechanism. It had none because 15
oracles were being treated as one thing. Taking every oracle the KNOWN-GOOD
control fails on w-i2c and asking *where* each one fails:

| class | n | what it actually is | owner |
|---|---|---|---|
| liveness / truncation | **7** | asserts "eventually X"; the trace ends first | the stimulus |
| level-not-transition | **5** | matches the idle state instead of the scenario | the oracle author |
| oracle: missing activation guard | **1** | asserts WRITE semantics on a READ trace | regenerate — *Phase 2 prevents it* |
| requirement over-reads the spec | **1** | the design is right and the requirement is wrong | spec authoring |
| ambiguous | 1 | fails one testpoint, passes three | the testpoint |

### The liveness class (7)

`"al never asserted before end of trace"`, `"never returned both lines to
released idle afterwards"`. REQ-0066 fails on **the last edge of its trace**
(edge 210 of 210) and REQ-0025 three edges from the end. These are not
over-strict about behaviour; the stimulus ends before the scenario completes.

**They are `NOT_EXERCISED`, not `VIOLATES`** -- which is why the debug loop
could never discharge them. Routed to the model agent, they ask for an edit that
cannot exist.

### The level-not-transition class (5)

Open-drain makes the idle state and the deasserted state the same value. The
control's reset state is `scl_oen = 1, sda_oen = 1` -- exactly the value every
"release the line" requirement tells an oracle to look for. Five of seven early
failures scan for `port == value` and never compare consecutive rows, so they
match edge 0 and report that the prior action never happened.

Worked example, REQ-0070. It demands SDA driven low before SCL is released, and
the control does exactly that:

```
edge 4   sda_oen=0  scl_oen=0     <- SDA driven low
edge 5   sda_oen=0  scl_oen=1     <- SCL released, SDA still low
```

The oracle searches for the first `scl_oen == 1` at or after activation, finds
edge 0, and fails. Not a disagreement about the protocol: REQ-0042 states the
same ordering, so the sibling requirement agrees. The check reads a level where
the requirement means a transition.

The contract does **not** declare `idle_value` for any output -- only for
inputs -- so the author has the polarity in a notes field and no
machine-readable statement that the value it is hunting for is also the resting
one.

### Three detectors, none needing a design

Each is computable from the trace the oracle already ran on, so none of them
gives the control or the witness any authority.

20. **Truncation detector.** An oracle that fails only by reaching the end of
    the trace is making a liveness claim the stimulus cannot decide. Reclassify
    `VIOLATES` -> `NOT_EXERCISED`, which routes it to the stimulus instead of the
    model. Removes 7 of the 15 and stops the debug loop spending its budget on
    them.
21. **Idle-match detector.** An oracle that fails at an edge before its
    activation could have occurred, on a port sitting at its reset value, is
    matching idle. Removes 5.
22. **Disagreement-with-itself detector.** An oracle a single design PASSES on
    several named testpoints and fails on one has a testpoint problem, not a
    strictness problem -- REQ-0066 passes 4 and fails 1, REQ-0060 passes 3 and
    fails 1. Works against the witness, so it needs no control at all.

### And one generation fix

23. Populate `idle_value` for OUTPUT ports in the contract, then tell the oracle
    author: where a requirement's target value equals a port's declared idle
    value, assert on the transition into it, not the level. A rule with a
    machine-checkable premise rather than a caution -- and the premise is
    currently absent from the artifact.

### The two mid-trace cases, triaged

Both are done, and neither is an over-strict check.

**REQ-0074 -- oracle defect, and Phase 2 already prevents it.** The requirement
is about WRITE. Its failing testpoint TP-0158 drives `cmd = 8`, and the spec's
assumed encoding is `WRITE = 0100 (4)`, `READ = 1000 (8)` -- so the trace issues
a READ, during which the controller releases SDA regardless of `din`, which is
exactly what the control does. The oracle asserts `sda_oen == din` without first
checking that a WRITE occurred.

Its normalized `inputs` is `{}`, which is the Phase 2 defect precisely: with
`{cmd: 4}` present, `check_static` would never have attached TP-0158 to it. So
this needs no new mechanism -- it needs the fix already committed, and a
verification that the attachment stops happening.

24. After the Phase 2 re-run, assert TP-0158 is no longer attached to REQ-0074.
    Offline, no model calls.

**REQ-0038 -- the requirement is wrong, not the oracle and not the model.** The
control advances a phase and completes a command while `ena = 0`:

```
edge 26   ena=0   scl_oen=0  sda_oen=0
edge 29   ena=0   scl_oen=1              <- phase advanced
edge 31   ena=0   cmd_ack=1              <- command completed
```

The requirement claims the FSM advances only on a timing tick and the oracle
checks that faithfully. But the spec says only that `ena` low *"reloads the
clock divider and resets the input filter counter, preventing normal bit-timing
progression"* -- it never says a phase already in flight cannot finish. The
control matches golden RTL at 168/168, so the design is right and the
requirement over-reads its source.

25. Route REQ-0038 to spec authoring. This is the ONLY one of the 15 that lands
    there, and like the 6 genuine spec holes it is not fixable from inside the
    pipeline.

**What this changes.** Over-strictness stops being the blocker with no path, and
stops being a phenomenon at all: **zero of the 15 are over-strict checks of
correct requirements.** It was five different things sharing one symptom, and it
looked mechanism-less because the symptom was what was being counted.

**Verify before building:** confirm the level-not-transition reading on each of
the 5 individually. The diagnosis generalised from REQ-0070, and this document
already records two occasions where I generalised too fast.

### Gaps this agenda did not have until they were audited for

26. **`ORACLE_INVALID` (1).** Named in the blocker table and given no item. Same
    route as `VACUOUS` -- `[O]` regeneration -- and it should be measured with
    it rather than discovered again later.
27. **Correspondence costs 154 calls for 3 rejections.** Measured precise but
    very low yield at the shipping calibration. It closes a real gap no other
    check covers, so this is a cost/keep decision to take deliberately, not a
    silent cut. It is the largest saving available in the oracle stage, which is
    66 of a 105-minute run.
28. **Author oracles at full strength. The VACUOUS experiment settled it.**

    Of the first 5 re-authored on `gpt-5.6-luna`/xhigh, **1 cleared** a check
    that `gpt-5-mini`/medium could not write.

    The comparison is deliberately unfair, and it runs TOWARD the conclusion:
    the originals had **three attempts with the counterexample fed back** --
    `oracles_stage.verify_one` returns `"vacuous: passed all N variants"` as a
    quotable rejection that seeds the next prompt -- while this arm got **one
    shot with no feedback at all**, because `run_oracle_gen`'s repair loop gates
    on `gate_one`, which is structural only. So 20% is a FLOOR: the small model
    with help lost to the large model without it.

    Price, measured: ~23k output tokens and 6 continuations per oracle, against
    ~150 oracles a run. That is the number to weigh, not whether the effect is
    real.

    A second arm (full strength WITH feedback) was considered and dropped. It
    could only widen a gap the asymmetry already demonstrates.

31. **Two entry points, one capability.** The repair loop that carries vacuity
    feedback lives in `oracles_stage`, not in `run_oracle_gen`, so any caller
    invoking oracle generation directly silently gets the weaker loop -- as this
    experiment did. Same shape as the switch-threading gap that killed a run:
    two paths, one carrying something the other does not, with nothing marking
    the difference.
29. **x-i2c is confounded and its successor should not be.** `--reuse` correctly
    regenerates the testplan and stimulus when `normalized.json` changes, so a
    "controlled" re-run of a normalization change is not controlled. Any future
    single-variable test has to freeze downstream artifacts deliberately or
    accept that it is measuring a new draw as well.
30. **The 6 dead-oracle requirements** liveness finds. Item 15 wires the
    instrument in; nothing yet says what happens to what it accuses.

---

## Phase 3 — the populations that block the gate

12. **VACUOUS (11) — MEASURED: 5 of 11 clear, and iteration is the lever.**

    The framing was wrong. "All 11 went through both `[O]` repair rounds and
    came back vacuous" was true and misleading: `[O]`'s repair loop gates on
    `gate_one`, which is **structural only**. Vacuity is decided later, in
    `oracles_stage.verify_one`, and a vacuity conviction was never fed back to
    the author. The 11 had three attempts at a gate that cannot see the defect.

    Given the real loop — generate, score with `must_fail`, re-prompt with
    `_repair_issue`'s own text on a conviction — `gpt-5-mini` at **medium**
    cleared **5 of 11** (`scratchpad/vac_loop.py`, 26 calls, every one verified
    `gpt-5-mini`/`medium` from its own `_meta.json`):

    | | cleared |
    |---|---|
    | mini/medium, real feedback loop, 3 rounds | **5 of 11** |
    | luna/xhigh, blind, one shot, no loop | 1 of 5 |

    **The cheap model told what it missed beat the expensive model told
    nothing.** 4 cleared at round 0 — from the counterexample alone, before any
    feedback — and 1 more at round 1. Round 2 cleared nobody, so iteration
    helps once and then stops: the remaining 6 are not a budget problem.

    The variant-supply confound does not explain the split. Of the 8 convicted
    on fewer than `MIN_IN_SCOPE` variants, 4 cleared; of the 3 with a full 3,
    1 cleared. Thin evidence did not predict clearing, in either direction, at
    n=11.

    **What this makes actionable:** the vacuity verdict has to reach the oracle
    author. Today it is computed after the author's loop has closed, which is
    the same shape as the `ORACLE_INVALID` defect the stage rework fixed — a
    rejection with no route back. Wiring `must_fail` into `[O]`'s repair loop
    is worth 5 of the 11 blockers on the measurement above, and needs no new
    mechanism.
13. **A structural disposition.** A requirement about the interface should never
    reach an oracle at all. This removes REQ-0019-class blockers legitimately,
    rather than by downgrading anything.
14. **UNOBSERVABLE's genuine 6.** Slave-wait detection, multi-master detection,
    divider reload on `ena` low, the `clk_en` tick, `scl_sync`, timing-counter
    reload — every one names an internal signal no declared output reflects.
    These route to a human by design. **Not fixable from inside the pipeline;
    they need a spec decision.**

---

## Phase 4 — instruments that exist but are not load-bearing

15. **Wire `liveness` as a gate in `[O]` — DONE, this item was stale.**
    `oracles_stage.py:609` measures it per repair round and `:615` gives the
    liveness note its own repair attempt beside gate 1; `compose.py:302`
    carries the verdicts into `[D]`. Validated against an ad-hoc probe
    (31 → 26 dead, 5 rescued by extra sample points, none newly accused, so it
    is the strictly more conservative instrument). It splits by owner:
    dead-oracle → the author, dead-stimulus → the testplan.
16. **Mutant supply for adequacy.** 44 of 70 oracles came back `UNKNOWN` because
    fewer than `MIN_IN_SCOPE = 3` mutants reached what they read. Scoping was
    already refuted as the cause — supply is what remains. Raise `MUTANT_LIMIT`,
    or target mutation at the ports each oracle asserts on.
17. **Dynamic `_attach`.** Replay-and-ask instead of `check_static`. Worth doing
    **only if** step 5 shows the false-attach rate is low.

---

## Phase 5 — making any of the above trustworthy

18. **Three draws at the final configuration.** Every claim about separation
    rests on a single run, and the s-i2c/t-i2c pair — 57/168 and 30/168 from one
    oracle set — shows that is not enough to distinguish a result from a draw.
19. **A second design.** Everything here is i2c, and `benchmarks/controls/` holds
    one design. The rework doc already names this as the weakest joint in the
    architecture; nothing since has strengthened it.

---

## Not to be done without an explicit decision

* **Downgrading `VACUOUS` or `ORACLE_INVALID` to warnings.** Passing a build on a
  check that demands nothing is the exact failure this pipeline exists to
  prevent.
* **Reclassifying a verdict to make a number look better.** Phase 2b moves 7
  oracles from `VIOLATES` to `NOT_EXERCISED`, and that is legitimate ONLY
  because "failed by reaching the end of the trace" is a computable property of
  the run, not a judgement. Any reclassification that cannot be computed from
  the trace is the same failure as downgrading the gate.
* **Changing what the gate accepts in order to make RTL appear.**
* **Touching the 6 genuine spec holes.**

---

## Ordering, and why

Phase 1 is free and can invalidate Phase 2. Phase 2 is upstream of Phases 3 and
4, so doing it first avoids measuring them twice against activations that are
about to change. Phase 5 is the only phase that makes any earlier number
trustworthy, and it is last only because it is pointless to replicate a
configuration still being changed.

**Honest expectation, revised after Phase 2b.** Phase 2 addresses the stimulus
cap; Phase 2b addresses 13 of the 15 over-strict oracles, 7 of them by routing
a liveness claim to the stimulus where it belongs rather than to the model. What
remains after both is roughly 2 genuine behavioural disagreements, whatever
`VACUOUS` survives, and 1 `ORACLE_INVALID`.

That is real progress on convergence and **may still not produce RTL**, because
`VACUOUS` and `ORACLE_INVALID` block correctly and nothing here is permitted to
change that. The honest ceiling on this benchmark is set by the 6 genuine spec
holes, which route to a human by design.
