# The alternating stimulus/repair loop

*A design for `oracles_stage`, written from measurements on k1-dcfsm. Every state
and every routing decision here is computable WITHOUT a known-good design; the
audit columns are computed last, stored separately, and reach no prompt and no
routing decision.*

## Why alternating, and not two rounds

The oracle stage today has one response to a check that does not decide: mint a
testpoint, replay, ask whether it decided. Repair is a separate path a check
enters for a different reason, and `oracles_stage` makes the two **one-way** — a
rejected check can never afterwards be staged.

That ordering throws away the fact each move produces for the other:

| a move | what it produces | which is the other move's input |
|---|---|---|
| new stimulus makes a silent check DECIDE | the check now says something | if what it says is wrong, that is a repair objection |
| new stimulus makes a passing check CONVICT | **the check is DISPROVED** | repair it; do not book it as a loss |
| a repair NARROWS a check | it may stop deciding | that is a stimulus request, not a failure |
| a repair changes a window | its old evidence no longer applies | its testpoints must be re-run |

**Measured**: staging two testpoints against a 126-check set that was sound on
318 testpoints made **2 of its members convict the reference**. Under today's
pipeline those are silent regressions in a set whose entire selling point is a
zero audit. Under the loop they are the two best-evidenced repair objections the
round produced.

## The state of a check, and it is golden-free

Computed from replay against the spec-derived candidate population only:

    decides_on_evidence     testpoints in the current suite where it returns a verdict
    decides_on_candidates   how many candidate designs it decides on at all
    convicts_of_N           how many candidate designs it objects to

    SILENT       decides_on_candidates == 0        -> STIMULUS
    VACUOUS      convicts == 0                     -> REPAIR: strengthen
    BAND         1 <= convicts <= threshold        -> KEEP
    SUSPECT      threshold < convicts <= N/2       -> REPAIR: narrow
    OVER_STRICT  convicts > N/2                    -> REPAIR: narrow

`threshold` is the minority rule's, measured at 100% precision on soundness over
59 checks of a 13-design population. **The threshold is a property of the
population size and must be re-derived when N changes** — a 13-design cut applied
to a 7-design population is a different rule.

## The invariants, each of which cost something to learn

**1. A before/after over EVIDENCE must be taken inside ONE RENDER.** Two runs
sharing a design, a stimulus file and a tp_uid set can still differ in every row:
the probe declaration fixes `transactional_view`'s compression key. Measured
across two drivers, **all 318 shared testpoints differed at row 0 and 13 checks
flipped verdict — 7 gaining objections and 6 losing them.** The baseline for a
staged round is therefore *the extended run restricted to the pre-existing
tp_uids*, never the previous run. The stimulus digest does not catch this,
because the stimulus is identical and only the row shape moves.

**2. New stimulus must be replayed against the WHOLE candidate population.** The
routing signal is a conviction count over candidates. Simulate a staged testpoint
on the reference alone and the audit moves while the routing signal cannot, so
the loop has nothing to alternate on. This is a required edge, and it is N extra
suite runs per staged testpoint batch.

**3. Success for a staged testpoint is read FROM THE ROW.** Did the target state
occur — never "did a check then decide". `stage_unexercised` conflates these
today, in capitals, and the conflation hides the case where the stimulus worked
and the check is the defect.

**4. Row count is a count of DISTINCT SITUATIONS, not of time.** Consecutive rows
with identical inputs and outputs collapse, so a held condition contributes ONE
row however long it is held. A stimulus prompt that says "hold the condition"
scores nothing. Measured: three cache-inhibited loads held for eight cycles each
produced exactly 3 rows; rewriting the prompt to ask for twelve *varied* accesses
was **2-3x more productive per testpoint**.

**5. A check that loses soundness under new evidence is a repair candidate, not a
discard** — and the objection handed to its author must be the conviction count
over candidates, never the reference's behaviour, which `oracles_stage.py:66-73`
forbids quoting.

## What the loop is worth, measured so far

The population it addresses is real and was mis-sized. Of a 126-check sound set,
**104 members are sound and silent**; splitting them by why:

| | |
|---|---|
| decide on under a quarter of the suite | 43 |
| name a state the suite never enters | 3 |
| decide widely and never object — genuinely blind | 42 |

median decide-rate **88 of 318**, first quartile 32. So roughly half that
population is short of evidence rather than blind — against a prior sizing of
"3 of 50", which only counted checks that abstain outright.

**And the first alternation is a negative so far**: twelve staged testpoints
raised the thinnest state's distinct situations from 45 to 61 and made **2 of 104
silent checks speak, while disproving 2 others**. The gain and the cost cancel.
That is one alternation of a loop designed for many, on a suite whose staged
fraction is 12 of 330, and it is reported here as the current figure rather than
as a verdict on the design.

### What invariant 6 cost, measured

Before the recorder was fixed, the loop's first state read **SILENT = 26** — 26
checks deciding on no candidate design at all, which routes to STIMULUS. With the
probe list corrected and nothing else changed:

    SILENT   26  ->  0
    VACUOUS  69  ->  95

**Every one of those 26 was reading dead probe columns, not waiting on stimulus.**
Routed on the broken recording the loop would have spent 26 stimulus budgets on
checks that needed none, and the plan would have carried "26 checks are
stimulus-starved" as a finding. This is why a run whose probes are dead must
refuse rather than report: the failure is silent, it looks exactly like the thing
the loop exists to detect, and it points the loop's most expensive move at the
wrong population.

**And it changes what the residue is.** With live probes, on a 7-design
population and 318 testpoints, **95 of 119 checks that are sound on the reference
object to NOTHING across seven independently written implementations.** Not
silent — deciding, and finding all seven acceptable. That is the vacuity problem
in its starkest form and it is what the loop's repair move has to move.

## Invariant 7: a repair is ACCEPTED only if it improved the state

The repair move must not bank its own output. Measured on 101 repair calls, each
carrying the objection its own latest evidence implied:

| | BAND (keep) | VACUOUS | OVER_STRICT | SILENT | *audit unsound* |
|---|---|---|---|---|---|
| before repairing | 18 | 83 | 18 | 0 | *6 of 119* |
| **every repair accepted** | 21 | 36 | **59** | 3 | ***59 of 119*** |
| **accepted only if improved** | **21** | 82 | 16 | 0 | ***6 of 119*** |

**Both columns reach the same 21. Only one of them destroys the set.** Accepting
unconditionally moved 49 checks straight from VACUOUS to OVER_STRICT and took the
set from 113 sound of 119 to 60 — the oscillation this plan has measured seven
times, at scale, in one round.

The gate is one line and it is GOLDEN-FREE, because BAND is a conviction count
over spec-derived candidates:

    accept the repaired body iff its new state is BAND and the old state was not;
    otherwise discard the repair and keep the original.

3 of 101 were accepted. **The landing rate is unchanged at 3% — the gate does not
make repair work, it makes repair FREE**, and a move that lands 3% is worth
running only when its failures cost nothing.

## The economics of the two moves, which is the actionable result

One full alternation, same population, same evidence, everything logged:

| move | cost | BAND | *audit* |
|---|---|---|---|
| start | -- | 9 | *0* |
| **STIMULUS** -- 12 staged testpoints, **zero authoring calls** | 12 sims | **18** | *6* |
| **REPAIR** -- 101 authoring calls, gated | 101 calls | **21** | *6* |

**Stimulus bought +9 keepable checks with no model calls at all; repair bought +3
for 101.** Per call the stimulus move is not merely better, it is the only one of
the two that scales. The golden-free keep set went from **8 of 89 = 9%** span to
**16 of 89 = 18%**, at a false-reject rate of 10%.

**So the prescription reverses where this plan has spent.** Nine authoring rounds
and one stimulus round is the wrong ratio; the loop should stage first, re-derive
every check's state from the wider evidence, and only then repair what the new
evidence disproves — with the accept gate on, so that the 97% which do not land
cost nothing.

## What to build, in order

1. `reachability.observed()` over the run's own replays -> the pool, per state,
   with distinct-situation counts and a shortest reproducer per state.
2. The check state machine above, emitted as one JSONL record per check per
   round, with the audit in a separate key.
3. Routing: SILENT -> stimulus for its activation state; VACUOUS/SUSPECT/
   OVER_STRICT -> repair with the conviction count as the objection; BAND -> keep.
4. The re-run edge (invariant 2) and the one-render rule (invariant 1) as
   harness refusals, not conventions.
5. Alternate until no check changes state or the budget is spent, logging every
   transition with the move that caused it.

## Invariant 6: the trace-internals list is PER DESIGN

The reference design has no probe PORTS — its probes are decoded from internal
signals, so recording it needs `state,cnt,hitmiss_eval,...`. Every GENERATED
design declares the probes as real output ports and has **none** of those
internal names. Hand it the reference's list and its `dut_internal` comes back
empty: every probe is present as a key and never true.

Measured on one held-out design, same stimulus, two recordings:

| recording | probes ever true |
|---|---|
| probe-port list (correct) | **9 of 10** |
| reference's internal list | **1 of 10** |

and the single survivor is `hitmiss_eval` — the one name that exists on both
sides, which this plan already records as a probe/internal collision.

**A probe that is never true is, to a check, a probe that does not exist**, so
every probe-reading check silently stops deciding and the whole candidate
population reads as port-only. Nothing fails; the counts just quietly change.
The recorder must take the probe list from the contract for a generated design
and the internals list only for the reference, and a run whose probes are all
dead should refuse rather than report.

## Invariant 8: the cut is not a soundness gate inside the loop, and VACUOUS is not a defect state

The minority cut was calibrated on the **whole 259-body corpus** against a
**13-design** population, where it read 59 of 59 precise on soundness against a
**31% base rate**. Only seven of those thirteen can be re-run, so the cut the
loop actually applies is `conv <= N//2 = 3`, and what that is worth had never
been measured on the population it runs against.

Measured on round P3 — 119 bodies, every one of them deciding both on a
candidate and on the reference:

| cut `t` | kept | sound | precision | recall | *lift* |
|---|---|---|---|---|---|
| base rate | 119 | 113 | **95%** | -- | -- |
| 0 | 82 | 82 | 100% | 73% | *1.05x* |
| 1 | 98 | 98 | 100% | 87% | *1.05x* |
| **3 — the cut the loop uses** | **103** | **101** | **98%** | **89%** | ***1.03x*** |
| 7 — no cut at all | 119 | 113 | 95% | 100% | *1.00x* |

**THE CUT IS WORTH 1.03x HERE, AND THAT IS NOT A REFUTATION OF THE RULE — IT IS
THE WRONG POPULATION TO ASK.** This body set descends from MAXSOUND and from a
gated repair round, so it is 95% sound before any rule touches it. A soundness
filter cannot be calibrated on a set already selected for soundness, and the
100%-at-31% figure stands on the corpus it was measured on. What this table does
answer is the question the loop needs: *inside the loop, the cut is not buying
soundness.*

**WHAT IT DOES BUY IS THE SEPARATION BETWEEN A CHECK THAT SAYS SOMETHING AND ONE
THAT DOES NOT**, and the price is legible:

| state | checks | sound | *adequate — sound AND catches the held-out design* |
|---|---|---|---|
| VACUOUS — convicts 0 of 7 | 82 | **82 = 100%** | ***8*** |
| **BAND — convicts 1 to 3** | **21** | **19 = 90%** | ***6*** |
| OVER_STRICT — convicts 4 to 7 | 16 | 12 | *0* |

**The keep set is the only state that is BELOW the base rate on soundness, and it
is the only state worth keeping.** #99 at the level of the routing: the two
unsound members of BAND are the price of the six adequate ones, and the 82 that
spare the reference perfectly are the 82 that mostly say nothing.

### And the routing sends 8 of the 14 adequate checks to REPAIR

The audit column above is the sharp part. Of the **14 adequate checks in the
whole set, 8 are classified VACUOUS**, so `classify` routes them to
`REPAIR:STRENGTHEN` — the move measured to trade soundness for discrimination 34
times out of 34. **The loop's largest single risk is that it repairs checks that
are already adequate.**

This is not a threshold to retune: at every cut from 1 to 7 the adequate count is
the same 14, because those 8 convict **zero** candidates. The rule cannot see
them, and the reason is the one this plan wrote down before it was measured —
*"'no candidate objected' is weak evidence a check cannot fail, because every
candidate may simply be RIGHT."* It was 3 of 14 when first observed. It is now
**8 of 14**.

**The fix is not a threshold and it is not golden.** It is the instrument the
plan already specifies for exactly this: a one-line mechanical mutant of a
candidate design. A VACUOUS check that convicts a live mutant has demonstrated it
CAN fail, on the artifact the editor edits, with no golden and no model call —
and it should be KEPT rather than strengthened. Until that leg runs, the accept
gate is what contains the damage: a strengthened check is discarded unless it
lands in BAND, so an adequate VACUOUS check survives the round unchanged.

## Invariant 9: new stimulus and the audit named the SAME eight checks, 8 of 8

Stimulus round 3 staged **18 testpoints on axes the suite had never exercised** —
bus errors, requests aborted mid-transaction, reset arriving while a transaction
is outstanding, back-to-back refills, and the data-valid strobe pausing
mid-sequence. Evidence went 330 → 348 testpoints, and both halves of the
comparison were taken **inside one render**, as invariant 1 requires.

**Eight checks changed state, all eight in the same direction, and the audit
agrees with the routing exactly:**

| | 330 testpoints | 348 |
|---|---|---|
| BAND (keep) | 21 | **17** |
| its span | 16 of 89 = 18% | **12 of 89 = 13%** |
| VACUOUS | 82 | 78 |
| OVER_STRICT | 16 | **24** |
| *audit: convict the reference* | *6 of 119* | *14 of 119* |
| *audit: **adequate*** | ***14*** | ***14*** |

    checks whose golden-free STATE changed        8
    checks that BECAME unsound on the audit       8
    intersection                                  8
    state-changed but still sound                 0
    newly unsound but state unchanged             0

**EVERY CHECK THE GOLDEN-FREE RULE MOVED TO OVER_STRICT IS EXACTLY A CHECK THAT
STARTED CONVICTING THE KNOWN-GOOD DESIGN, AND NO OTHER CHECK DID EITHER.** That
is not a fitted threshold: the movement was caused by stimulus that no part of
the rule or the audit had seen, both columns were computed independently, and
they agree in both directions with nothing left over. The eight went from 0 or 1
convictions to **6 or 7 of 7**, so it is a decisive conviction event rather than
a marginal one.

This is the mechanism the minority rule claims, observed rather than assumed: *a
demand no independent implementation satisfies is more likely one the check
misread than one all those authors got wrong* — and here, on all eight, the
known-good design agrees with the authors.

### And round 3 bought no span at all, which is the honest half

The keep set lost four members and four requirements. **It also lost zero
adequate checks: 14 before, 14 after, and all six of BAND's adequate members
survived.** What the wider evidence removed was four false keeps — checks that
looked like a minority conviction on 330 testpoints and demand something no
design satisfies on 348.

| round | cost | BAND | span | *audit unsound* | *adequate* |
|---|---|---|---|---|---|
| P0 — original 318 | -- | 9 | 8 = 9% | *0* | -- |
| **STIMULUS r1+r2** — 12 testpoints, 0 authoring calls | 12 sims | **18** | 14 = 16% | *6* | -- |
| REPAIR — 101 authoring calls, gated | 101 calls | 21 | 16 = 18% | *6* | *14* |
| **STIMULUS r3** — 18 testpoints, 0 authoring calls | 18 sims | **17** | **12 = 13%** | *14* | *14* |

**SO THE STIMULUS LEVER'S RETURN IS NOT MONOTONE IN SPAN, AND SPAN IS THE WRONG
THING TO SCORE IT ON.** Stimulus is an EVIDENCE move: it can only make the
measurement more nearly right, and a measurement getting more nearly right looks
like a loss whenever the previous number was too high. The user's prediction for
this loop was exactly that — *"the testpoints differing on golden will not be
monotone with the number of checks; one bad behaviour can wreck everything"* —
and one round of new behaviours removed a fifth of the keep set.

**The consequence for reporting is a rule.** A keep-set span is only meaningful
beside the evidence it was measured on, and a span that falls when the evidence
widens was never a span — it was an artefact of what the suite did not do. Quote
both, or quote neither.

## Invariant 10, and it corrects this document's own keep rule: KEEP must include the zero

Every keep-set figure above was measured on **119 bodies that descend from
MAXSOUND**, which was selected BY the known-good design. The selection RULE was
golden-free; the POPULATION was not, and a keep set is only as golden-free as the
weaker of the two. It also capped the loop's span at the 52 requirements those
119 bodies happen to cover, against 68 for the corpus.

Re-run with the same rule, the same 348-testpoint evidence and the same seven
candidates, over **all 484 authored bodies**:

| rule — reads only the seven spec-derived designs | checks | requirements | of 89 | *audit: convict the reference* | *adequate* |
|---|---|---|---|---|---|
| convicts 1–3 of 7 — **the KEEP state as this loop defines it** | 27 | 14 | **16%** | ***48%*** | *6* |
| convicts 1–2 of 7 | 26 | 13 | 15% | *46%* | *6* |
| convicts exactly 1 of 7 | 16 | 8 | 9% | *38%* | *5* |
| **convicts AT MOST 3 of 7 — the same cut, without the refutable leg** | **111** | **44** | **49%** | ***12%*** | ***14*** |
| convicts 0 of 7 alone | 84 | 35 | 39% | ***0%*** | *8* |
| convicts 4–7 of 7 — OVER_STRICT | 313 | 61 | 69% | *96%* | *1* |
| everything that decides | 424 | 67 | 75% | *74%* | *15* |

**THE REFUTABLE LEG COSTS 30 REQUIREMENTS OF SPAN AND QUADRUPLES THE FALSE
REJECT RATE.** Requiring a keep to convict at least one candidate takes the set
from 44 requirements at a 12% audit to 14 at 48%, and throws away 8 of the
corpus's 15 adequate checks. It is not a filter that trades reach for precision;
it loses on both.

**So the loop's keep state is wrong and the fix is one comparison:**

    BAND    1 <= convicts <= N//2       ->    KEEP    convicts <= N//2

That is not a new idea — this project measured it once before and wrote *"the
golden-free rule loses a leg and gets better"* — and the loop then reintroduced
the leg as the boundary of its KEEP state. Invariant 8 saw the same thing from
the adequacy side; this is the same finding with a span and an audit attached.

**AND IT IS THE BEST GOLDEN-FREE PAIR THIS PROJECT HAS PRODUCED: 44 of 89 = 49%
of the specification at a 12% false-reject rate, holding 14 of the corpus's 15
adequate checks.** One requirement short of a majority, and the first time reach
and precision have moved the same way at once.

### The audit correction that comes with it, and it is mine

The loop has been reporting a **10% false-reject rate** on its keep set all
session. That figure is an artefact of the golden-selected population: the same
rule on the honest corpus reads **48%**. Every "audit" column measured on
`bodies_P3` should be read as a lower bound whose denominator was chosen by the
instrument it is auditing.

### And the minority cut, properly re-derived at N = 7

The cut was calibrated at 100% precision on **thirteen** designs and 259 bodies
against a 31% base rate. On seven designs and 484 bodies, with soundness as the
thing predicted and never an input:

| cut `t` | kept | sound | precision | recall | *lift over the 26% base* |
|---|---|---|---|---|---|
| 0 | 84 | 84 | **100%** | 75% | *3.79x* |
| 1 | 100 | 94 | 94% | 84% | *3.56x* |
| 2 | 110 | 98 | 89% | 88% | *3.37x* |
| **3 — the cut the loop uses** | **111** | **98** | **88%** | **88%** | ***3.34x*** |
| 5 | 125 | 108 | 86% | 96% | *3.27x* |
| 7 — no cut | 424 | 112 | 26% | 100% | *1.00x* |

**The 100% does not survive the population shrink, and the rule does: 88%
precision at 3.34x over a 26% base, n = 111.** The plan's own warning was that
the threshold is a function of the population SIZE; it is now re-derived rather
than carried across, and the majority cut is still the right one — it holds 14 of
the 15 adequate checks where the strict cut at 1 holds 13.
