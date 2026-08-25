# Getting each stage to converge, and RTL out the other side

**Status:** plan. Phase 0 is in flight; nothing in Phases 1–5 is built.
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

## Phase 0 — land what is in flight

No new work; w-i2c is running.

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

## Phase 3 — the populations that block the gate

12. **VACUOUS (11).** All 11 went through both `[O]` repair rounds and came back
    vacuous; the repair loop is not skipping them, regeneration from the same
    requirement text does not produce a non-vacuous check. First test whether
    Phase 2 resolves any *for free* — a sharper trigger may be a less vacuous
    check. 9 of the 11 also lack input activations, but against a 74% base rate
    that is **barely above chance and is not claimed as a cause.** If Phase 2
    does not move it, VACUOUS needs its own mechanism and that decision should
    be taken deliberately rather than folded into this plan.
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

15. **Wire `liveness` as a gate in `[O]`.** Built, validated against an ad-hoc
    probe (31 → 26 dead, 5 rescued by extra sample points, none newly accused,
    so it is the strictly more conservative instrument), and currently advisory
    only. It splits by owner: dead-oracle → the author, dead-stimulus → the
    testplan.
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
* **Changing what the gate accepts in order to make RTL appear.**
* **Touching the 6 genuine spec holes.**

---

## Ordering, and why

Phase 1 is free and can invalidate Phase 2. Phase 2 is upstream of Phases 3 and
4, so doing it first avoids measuring them twice against activations that are
about to change. Phase 5 is the only phase that makes any earlier number
trustworthy, and it is last only because it is pointless to replicate a
configuration still being changed.

**Honest expectation.** This plausibly clears `NOT_EXERCISED` and the ~7
over-strict `VIOLATES`, leaving roughly 3 real model defects and whatever
`VACUOUS` survives. That is real progress on convergence and **may still not
produce RTL**, because `VACUOUS` and `ORACLE_INVALID` block correctly.
