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

## The validation clause, run: the loop stopped at TWO, and both are the unsound two

The goal's own criterion — *can a Sonnet RTL editor, driven by this set alone,
produce a design equivalent to the reference* — run on the keep set the loop
produced. **Answer: no, and the way it fails is the best result on this plan.**

* **The set.** 21 checks over 16 of 89 requirements, selected by the golden-free
  band rule on 330 testpoints. *Its population descends from a soundness-selected
  set, so this is not the corrected 49% set — that arm is separate.*
* **The design.** `L`, written from the specification by an agent forbidden to
  open any other design, held out of every selection that produced the set.
* **The editor.** Sonnet through the shipped `_EditSession` policy — staged
  buffer, content-anchored splice, commit as the one trial. No reference design,
  no reference trace, no expected value.

| | objections of 21 | testpoints differing | cells | trials |
|---|---|---|---|---|
| L at init | **8** | 279 of 348 = **80%** | 4,450 | 0 |
| **L after the loop** | **2** | **223 of 348 = 64%** | **3,969** | **3 of 14** |

**Objections fell 75%, divergence fell 20% and cells fell 11% — all three the
same way — in three trials, with eleven unused.** Grade: `DIFFERS`, with all
three pins green in the same process (reference vs itself `EQUIVALENT`,
reference+probes `NO-DIFF-40`, a live mutant `DIFFERS`).

### And the two objections it could not clear are exactly the two unsound checks

The audit says **2 of the 21 convict the reference: `REQ-0081.control` and
`REQ-0081.merge_merge`.** Those are the two the loop stopped on, and the editor
refused them with a reason it could check rather than argue:

> `OR1200_DC_STORE_REFILL` is false in this build, so the SREFILL4 entry path is
> inside a dead `ifdef`; the check fires an "incremented on SREFILL4 entry"
> template on a back-to-back store that is legitimate pipeline behaviour.

Verified independently, and it is exact: **`in_srefill4` is true in 0 of the
reference's 5,723 rows across all 348 testpoints.** The state does not occur, so
no design can be wrong about it and no edit can satisfy a check that demands
something there.

| run | the editor's soundness judgement | |
|---|---|---|
| the earlier ceiling run | **1 of 3** | refused one unsound check and two sound ones, and its stated reason was false |
| **this run** | **2 of 2** | refused exactly the unsound pair, for a reason readable off the trace |

**THE DIFFERENCE IS THAT THE STATE IS A DECLARED PROBE.** *"This state never
occurs"* stopped being a belief the editor argues for and became a fact it reads
out of recorded rows. That is the probe architecture earning its keep somewhere
this plan never looked — not in the author, in the EDITOR — and it is the first
time on this plan that the editor's soundness judgement was right for a reason
that can be verified rather than asserted.

### What this settles, and what it does not

* **The gradient is right on a golden-free-selected set.** Objections, testpoints
  and cells moved together, which the rule-B run did not manage and the MAXSOUND
  run reversed over its final approach.
* **The loop terminated for a correct reason with 11 trials in hand.** Every
  earlier stop on this plan was either the budget or a criterion that was
  satisfied while the design was wrong.
* **And it is still `DIFFERS` at 64% of testpoints.** 16 of 89 requirements is
  not enough to finish, which is a statement about the set's SIZE and not its
  direction — the same reading the clean ceiling run reached, now on a set no
  known-good design selected.

## The 49% set, run: tripling the span moved the grade by one point

The corrected keep set — 111 checks over **44 of 89 requirements = 49%**, audit
12% — put through the identical experiment: unedited held-out `L`, a Sonnet
editor through the shipped policy, the same 348-testpoint suite, the same grade.

| set | span | objections | testpoints differing | cells | trials |
|---|---|---|---|---|---|
| band, 21 checks | 16 reqs = 18% | 8 -> **2** | 279 -> **223 = 64%** | 4,450 -> 3,969 | 3 of 14 |
| **keep, 111 checks** | **44 reqs = 49%** | 23 -> **7** | 279 -> **220 = 63%** | 4,450 -> **3,834** | 5 of 14 |

**THREE TIMES THE SPAN LANDED THE DESIGN THREE TESTPOINTS CLOSER.** Both runs
`DIFFERS`, pins green. This is the plan's earlier rule-B-against-ceiling
comparison reproduced at a much larger span gap, on one design, with one editor
family and one evidence set: **"spans a majority of the specification" and
"drives a design to correctness" are independent properties of a set**, and the
second does not follow from the first at any span this corpus can reach.

### RETRACTED: the editor's soundness judgement is 1 of 5, not 2 of 2

The band run stopped on two checks and both were the unsound pair, which I
reported as the editor's soundness judgement being right. **On the larger set it
named FIVE requirements as the check's fault and exactly one of them is
unsound.**

| the editor's claim | audit |
|---|---|
| REQ-0081 — the state it names is compiled out of this build | **UNSOUND — correct** |
| REQ-0026 — the requirement demands one increment and the check wants two | *sound* |
| REQ-0068 — same | *sound* |
| REQ-0059 — `dc_en` governs acceptance, not continuation | *sound* |
| REQ-0060 — same | *sound* |

**So the 2-of-2 was a small-n artefact and the rate is the same 1-in-3-to-5 this
plan measured before.** What survives is a sharper distinction the two runs
together make, and it is worth more than the rate:

* **An OCCURRENCE claim is checkable and the editor got it right.** *"This state
  never happens"* is a count over recorded rows, and the state is a declared
  probe, so the editor counted it: 0 of 27,278 edges. Verified independently.
* **A MEANING claim is not, and the editor got 0 of 4.** *"The requirement owes
  one increment, not two"* and *"`dc_en` need not be held to the acknowledge"*
  are readings of a sentence. The editor supported each with real counted
  evidence from the traces — and the evidence was about what the design does,
  never about what the requirement means, which is the question it was actually
  answering.

**A probe makes an occurrence claim decidable and does nothing for a meaning
claim.** That is the honest version of what the band run seemed to show, and it
is a bound on what any amount of trace evidence can buy an editor arguing with a
check.

## The mutant leg: 27 of 84, all sound, and it still must not select

Invariant 8 said the VACUOUS state has no instrument and named the one this
project already has — a mechanical one-line mutant of a candidate, wrong by
construction, with no known-good design in its provenance. It was run: 15
mutants of candidate `D`, **2 excluded as behaviourally identical to their
parent** (the control firing exactly as it must), 13 live, differing from `D` on
8 to 348 testpoints.

| of the 84 checks that convict no candidate | checks | requirements | *audit* | *adequate* |
|---|---|---|---|---|
| **a live mutant convicts it — demonstrably CAN fail** | **27** | 14 | ***0%*** | *5* |
| no live mutant convicts it | 57 | 25 | *0%* | *3* |

**0 of the 27 promoted checks convict the reference.** That reproduces this
module's `refuted_by` figure — 19 of 19 sound before, 27 of 27 now — on a
different population, a different mutant parent and wider evidence.

**AND IT STILL MUST NOT SELECT, for the reason the plan wrote down before it was
measured.** Rejecting the 57 that no mutant convicts would discard **3 of the
corpus's 14 adequate checks** — 21%, the identical fraction the earlier round
measured. A check that catches nothing here is usually a check the seven
candidates and the thirteen mutants all happen to satisfy, not a check that
cannot fail.

### And that is the refutability requirement failing a second time, with a second instrument

| set | checks | requirements | of 89 | *audit* | *adequate* |
|---|---|---|---|---|---|
| **convicts at most 3 of 7 — the keep rule** | **111** | **44** | **49%** | ***12%*** | ***14*** |
| ...and must convict a candidate | 27 | 14 | 16% | *48%* | *6* |
| ...and must convict a live mutant | 54 | 25 | 28% | *24%* | *11* |

**Both refutability requirements make every column worse — span, false rejects
and adequacy — and they do it independently of each other.** The rule to carry is
the plain one: *keep a check that convicts at most half of an independently
written population, including none of it.* Refutability is a fact worth
REPORTING beside a check and is not a criterion for keeping one.

## Selection is exhausted: the corpus supplies SIX sound catchers, and the keep set already holds five

The 49% set drove the held-out design to 7 objections and `DIFFERS` at 63% of
testpoints. There are two explanations and they demand opposite work — either no
body in the corpus objects to what remains wrong (**authoring**), or bodies do
and the rule dropped them (**selection**). All 484 authored bodies were
re-decided against that design:

| | |
|---|---|
| corpus bodies OBJECTING to it | **278 of 484, over 60 requirements = 67% of the spec** |
| of those, SOUND on the reference | **6** |
| of those 6, already inside the 49% keep set | **5** |
| requirements a SOUND body catches it on | **6 = 7% of 89** |

**THE CORPUS KNOWS THE DESIGN IS WRONG ACROSS 67% OF THE SPECIFICATION AND CAN
SAY SO SOUNDLY ON 7%, AND THE GOLDEN-FREE RULE HAS ALREADY FOUND FIVE OF THE
SIX.** 272 of the 278 catches are bought by also condemning the reference. So
this is not a selection failure with a better rule waiting to be found: **there
is one more sound catcher in the entire corpus, and no rule can select what was
never written.**

### And the residue has a number on this set: 1.5%

Restricted to the 111 keep-set checks and to the decisions where **a port the
check itself reads is wrong** — a check watching `burst` is not blind for
passing a defect on `saved_addr`:

    decisions on exposed testpoints    6,521
    of those, objections                  95 = 1.5%

The plan measured 3.9% twice, on two earlier sets, against designs no editor had
worked on. **1.5% is what is left after an editor has cleared everything the set
could see**, which is the same statement one round further on: the remaining
wrongness is exactly what these checks are blind to.

**So the binding constraint is AUTHORING, and it is not the number of checks —
it is what a check asserts.** The corpus has 484 bodies over 68 requirements and
six of them can soundly convict a design wrong on 63% of the suite.

## A MAJORITY: 50 of 89 = 56%, at an 11% false-reject rate, and all three columns moved together

Selection is exhausted, so the remaining lever is authoring — and exactly one
authoring move on this plan has ever had a positive measured yield: **narrowing
an over-strict check**. It was aimed at the only population where it can add
span: the **23 requirements that have an OVER-STRICT body and no keepable one.**
One body each, the least over-strict, one call.

**Admissible, and checked before dispatch.** The objection is *"your check
objects to N of seven independently written implementations of this
specification"* — no known-good design, no held-out design, no equivalence
verdict. Leak check: **0 violations over 23 prompts against 182 lines of the
reference's source.**

**Integrity: 23 of 23 returned, 23 of 23 parse, 0 duplicates, 0 unchanged** —
after one filename correction, recorded rather than absorbed: a worker wrote
`REQ-0065.t2.json` for the key `REQ-0065.t2.prompt`, the plan's own
suffix-stripping event. It was verified distinct from every other answer and
from the body it was given before being renamed.

    23 calls, 6 accepted by the gate = 26%
      REQ-0015  REQ-0019  REQ-0064  REQ-0065  REQ-0071  REQ-0076
      all six SOUND; two of them ADEQUATE
      17 not accepted: 16 still over-strict, 1 silent, 0 gone vacuous-and-blind

| the golden-free keep set | checks | requirements | of 89 | *audit* | *adequate* |
|---|---|---|---|---|---|
| before round 3 | 111 | 44 | 49% | *12%* | *14* |
| **after round 3** | **117** | **50** | **56% — A MAJORITY** | ***11%*** | ***16*** |

**SPAN UP, FALSE REJECTS DOWN, ADEQUACY UP — the first round on this plan where
all three moved the right way at once.** And the landing rate is 26%, against
narrowing round 1's 15% and round 2's 4%, because the population was chosen
tightly: one body per requirement, the least over-strict, only where span could
be gained, with the cut re-derived for the seven-design population.

**The score, stated as the pair and nothing else.** A golden-free rule reading
only seven independently written spec-derived designs keeps **117 checks over 50
of 89 requirements = 56% of the specification**, and **13 of the 117 — 11% —
convict the known-good design**, which is computed last and feeds nothing.

**And 56% span is not 56% adequacy, which is the distinction this document exists
to keep.** The set carries **16 measured-adequate checks**: sound, and objecting
to a design held out of every selection. That is 16 of 89 = 18% of the
specification, and it is the number the goal's optimisation target actually
names.

## The golden-free substitute for adequacy: it collapses to the refutable leg

Adequacy cannot be a reported score — soundness needs the known-good design and
discrimination needs a held-out one — and against the only thing that matters it
did not predict: **6 adequate checks landed a design at 64% of testpoints
differing and 14 landed it at 63%.** So a golden-free replacement was proposed
and measured: *on the situations where independently written implementations
DISAGREE about a port you read, how often do you say anything?* The predictor is
computed on the seven candidates and the outcome on a design held out of
everything, so the two share no evidence.

| rule | checks | catch the held-out design | precision | *lift over the 22% base* |
|---|---|---|---|---|
| every check that decides | 113 | 25 | 22% | *1.00x* |
| **convicts >= 1 candidate — the refutable leg** | **28** | **16** | **57%** | ***2.58x*** |
| **objects in a DISPUTED situation** | **28** | **16** | **57%** | ***2.58x*** |

**THE TWO SETS ARE IDENTICAL — the same 28 checks, nothing in either
difference.** The disputed filter removes nothing, because at testpoint
granularity **64% of (testpoint, port) pairs are already disputed**, against the
11% the plan's 8.6x localisation reports per CELL. So the substitute is the
refutable leg wearing a new name, and it is refuted as a new instrument.

**WHY THE WEAKER TEST WAS THE ONLY ONE AVAILABLE, and it is a structural limit
rather than an excuse.** `transactional_view` compresses each design's rows
independently, so row *i* of one candidate is not row *i* of another and a
cell-level comparison has nothing to align on. Testpoint-level is what can be
computed across designs, and it is far too coarse to localise. A cell-level
disagreement strength is untested and would need raw-edge alignment.

### What survives, and it is worth having

**The refutable leg predicts DISCRIMINATION at 57% against a 22% base — 2.58x,
n = 28, golden-free, no model call.** That is a real instrument for the half of
adequacy that has never had one.

**And it still must not select, which is the same conclusion from a third
direction.** It **misses 9 of the 25 catchers** — sound-and-blind checks that
catch a wrong design the seven candidates happen to get right — and using it as a
keep rule was already measured to cost 30 requirements of span and quadruple the
false-reject rate. So: **report with it, never select with it**, and the reason
is now a number on both halves rather than a warning.

### The honest position on the metric

There is no cheap golden-free proxy here that beats what was already in hand.
Adequacy is not reportable and did not predict; its proposed replacement is the
refutable leg; the refutable leg predicts one of adequacy's two halves and cannot
be selected on. **The measure of a check set is the validation run**, and its
cost — roughly an hour of simulation plus an editor — is the real constraint on
how often a set can be judged.

## THE VALIDATION, ON THE MAJORITY SET: every sound check satisfied, and still `DIFFERS`

The finish condition, run on the set that spans a majority. 117 checks over 50 of
89 requirements = 56%, selected by a conviction-count rule over seven
spec-derived designs and nothing else. Design `L`, written from the
specification by an agent forbidden to open any other design and held out of
every selection. A Sonnet editor through the shipped `_EditSession` policy.

| trial | objections of 117 | |
|---|---|---|
| init | 25 | over 18 requirements |
| 1 | 9 | |
| 2 | 4 | |
| 3 | 4 | *did not latch — the requirement ratchet refused it, and correctly* |
| **4** | **2** | **49 of 50 requirements pass** |

**THE TWO IT STOPPED ON ARE EXACTLY THE TWO THE AUDIT CALLS UNSOUND** — both
`REQ-0081` bodies, demanding something on entry to a state whose feature is
compiled out. The editor called it an occurrence claim and counted it; verified
twice independently and exactly: **`in_srefill4` is true in 0 of the reference's
5,723 rows and 0 of the accepted design's 6,127.**

So the design satisfies **every sound check the set contains**, in 4 of 14
trials.

| | testpoints differing | cells |
|---|---|---|
| L at init | 279 of 348 = 80% | 4,450 |
| **L after the loop** | **236 of 348 = 68%** | **3,533** |

**GRADE: `DIFFERS`, with all three pins green in the same process.**

### Three sets, one design, and span does not move the grade

| set | span | objections | testpoints differing | cells | trials |
|---|---|---|---|---|---|
| 21 checks | 16 reqs = 18% | 8 -> 2 | **223 = 64%** | 3,969 | 3 of 14 |
| 111 checks | 44 reqs = 49% | 23 -> 7 | **220 = 63%** | 3,834 | 5 of 14 |
| **117 checks** | **50 reqs = 56%** | **25 -> 2** | **236 = 68%** | **3,533** | 4 of 14 |

**SPAN TRIPLED AND THE GRADE MOVED FIVE POINTS, IN THE WRONG DIRECTION AT THE
TOP.** The majority set clears the most objections and produces the fewest
differing CELLS — 3,533, the best of the three — while differing on the most
TESTPOINTS. Errors got shallower and more widespread. Cells and testpoints
disagree, so neither alone is the grade, and the bounded miter is.

### And the residue is now ZERO, which is the sharpest form of the finding

On the accepted design, restricted to the 117-check set and to decisions where
**a port the check itself reads is wrong**:

    decisions on exposed testpoints    6,542
    of those, objections                   0 = 0.0%

**THE DESIGN IS WRONG ON 236 TESTPOINTS AND EVERY SOUND CHECK IN A SET SPANNING
A MAJORITY OF THE SPECIFICATION WATCHES IT HAPPEN AND SAYS NOTHING.** 3.9% was
measured twice on earlier sets; 1.5% after an editor had worked on the 49% set;
0.0% here. That is not a set that ran out of things to say — it is a set whose
every member is satisfied by a design that differs from the reference on more
than two thirds of the suite.

**So the finish condition is NOT met, and the mechanism is named and measured
rather than inferred.** It is not soundness (every sound member is satisfied),
not span (a majority), not selection (five of the corpus's six sound catchers
were already kept), not stimulus (348 testpoints, the design driven wrong on
236 of them), not the editor (4 of 14 trials, stopping on demonstrably wrong
checks), and not the gradient (objections, cells and testpoints all fell within
the run). **It is what a check ASSERTS: a fragment of its requirement, satisfied
by designs that violate the rest of the sentence.**
