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

## The strength round, GATED: 3 of 40, and the gate is the whole difference

The residue is 0.0%, and its mechanism is that a check asserts a FRAGMENT of its
sentence. The one lever aimed at that was measured once at **34 of 34 crossing
into over-strictness and 0 landing** — and that round banked every crossing as a
loss. Re-run with the accept gate, on the 40 requirements whose keep-set member
convicts none of the seven:

    accept iff the new body convicts 1 to 3 of the seven AND the old convicted 0

| | |
|---|---|
| calls | 40 |
| **accepted by the gate** | **3 = 8%** — all three SOUND, two of them ADEQUATE |
| crossed to over-strict and were discarded | **21** |
| still convict none, discarded | 16 |

**THE GATE IS THE ENTIRE DIFFERENCE BETWEEN THIS AND THE ROUND THAT FAILED.**
Banking every body would have taken the round's false-reject count from **0 to 19
of 40**; the gate keeps **0**. The authors did not get better — 21 of 40 still
crossed, exactly as before. What changed is that crossing now costs nothing.

**By the pre-registered bar this lands at 1-4: real, marginal, record the rate
and do not build on it.** No further editor run was dispatched on it, which is
what the bar says to do and is recorded here because moving a bar after seeing
the number is the defect this document exists to prevent.

### A prompt defect, mine, and it biases AGAINST the round

The prompt enumerated the declared OUTPUTS and the probes and said *"do not
invent any other signal name"* — **and never enumerated the declared INPUTS**,
though it said in the same breath that every row carries them. One author said so
outright, calling a declared input "NOT in the declared interface".

Measured: **11 of 40 strengthened bodies dropped an input the old body read**, 5
added one, 27 kept everything they had. A check that drops an input it needs
asserts LESS, which is the opposite of what the round asks for, **so 3 of 40 is a
floor and the round is not a clean test of the lever.** Recorded rather than
re-run, because re-running it would be a second sample of the same population and
the bar has already been read.

## THE FINAL GOLDEN-FREE SCORE

Selected by a rule that reads only seven independently written spec-derived
designs and mechanical mutants of one. The audit is computed last and feeds
nothing.

| | |
|---|---|
| **checks** | **117** |
| **requirements spanned** | **50 of 89 = 56% — a majority** |
| *audit: convict the known-good design* | ***13 = 11%*** |
| *adequate — sound AND catching a design held out of everything* | ***17 = 19% of 89*** |
| of the set, refutable — convicts 1 to 3 of the seven | 31 |

**And the validation it does not pass, stated beside it as the pair demands.** A
Sonnet editor on a design written from the specification and held out of every
selection drives this set from 25 objections to 2 in 4 of 14 trials, satisfying
**every sound check it contains**; the two it cannot clear are the two the audit
calls unsound, disproved by counting rather than argued. The bounded miter says
`DIFFERS` at 236 of 348 testpoints, and the set objects **0 times in 6,542
decisions where a port it reads is wrong.**

## A different proxy: the consensus as an ORACLE, and it separates where checks do not

The goal now asks for proxy metrics chosen by how well they help the editor
succeed. The 117-check set gives the editor **two objections on a design wrong
on 68% of the suite, and the audit says both are wrong.** So the proxy was
changed rather than the set.

**THE INSTRUMENT.** Seven designs written independently from the specification by
agents forbidden to open any other implementation, all run on the same
348-testpoint stimulus. Wherever **all seven produce the identical value** at a
(clock edge, declared output) sample, that value is the reference.

    240,573 unanimous cells, over 348 testpoints

**Declared outputs only, and that is a decision rather than an omission.** Two
output-equivalent designs may encode their states differently, so a probe
disagreement is a legitimate design choice and demanding the population's value
there would convict a correct design for its encoding — the port-only argument
this project proved once as a theorem, applied to a reference table.

**RAW EDGES, NOT TRANSACTIONAL ROWS.** Every design is driven by the same
stimulus, so edge *i* is the same moment in all of them; the transactional view
compresses each design independently and cannot be aligned across designs. That
is also why the testpoint-level version of the disagreement question, measured
earlier, could not answer anything.

| | cells disagreeing with the consensus |
|---|---|
| a member of the population (candidate D) | **0** — by construction, the control firing |
| ***the known-good design*** | ***2,073 = 0.86%*** |
| **held-out L, unedited** | **9,857** |
| held-out L, after the 117-check editor loop | 5,602 |

**THE KNOWN-GOOD DESIGN SCORES 4.8x BETTER THAN THE HELD-OUT ONE.** That is the
first instrument on this plan where it is clearly the best non-population
design, and the false-reject rate — 0.86% — is known IN ADVANCE, which no check
set's ever is.

**AND ZERO IS STILL NOT THE ACCEPT CRITERION.** A design scoring zero has matched
the population everywhere including the 2,073 cells where the population is
wrong, which is evidence against equivalence by exactly the arithmetic that made
an over-strict check set's zero fatal. The criterion is DESCENT under a trial
budget, and the floor is where the known-good design sits.

### It also supplies the one thing the editor has never had

The companion document names the editor's weakest point outright: *"expected/
actual is reconstructed, not observed ... a fabricated expected value would make
it CONFIDENT in a wrong theory."* **A unanimous consensus cell IS an observed
expected value** — not reconstructed, not synthesised, but what seven agents who
never saw each other's work all produced at that moment. The editor now gets,
per output: the testpoint, the edge, what all seven produce, what its design
produces, and the inputs driving that edge.

### CORRECTING THIS PLAN: the consensus route was closed on ONE held-out design

The earlier measurement reads *"a consensus over a population is satisfied by
that population BY CONSTRUCTION, and by anything drawn from the same
distribution — which is what J is. So the reference has nothing to say to any
design a specification-reading author would write."* Held-out J scored **0**.

**Held-out L scores 9,857.** L was written the same way, from the same
specification, by the same kind of agent, and held out of everything. So
*"nothing to say to any design a specification-reading author would write"* is
too strong: the instrument's discrimination is a property of the (reference,
design) PAIR, exactly as the both-cell turned out to be.

**THREE THINGS DIFFER BETWEEN THE TWO MEASUREMENTS AND I CANNOT SEPARATE THEM.**
The old table was over THIRTEEN designs, 318 testpoints, and all cells including
probes; this one is SEVEN designs, 348 testpoints, declared outputs only.
Unanimity over seven is easier than over thirteen, so this table has more cells
and more chances to disagree. The 0-against-9,857 gap is far too large to be
only that, and the honest statement is that **the earlier route was closed on a
sample of one held-out design and should not have been.**

## TWO DEFECTS IN MY OWN DRIVER, AND THE FIRST IS A PROXY-METRIC FINDING

The goal asks for proxy metrics chosen by *how well they facilitate the RTL
Editor succeeding*. The consensus run produced one before it produced any
trajectory, and it is about the shape of the criterion rather than its content.

### THE RATCHET'S GRANULARITY IS A PROXY-METRIC CHOICE, AND THE COARSE ONE REJECTS CORRECT WORK

`_EditSession.commit` latches an edit when the **count of passing requirements**
rises (`rtl_editor.py:2007`). That is the shipped accept rule and it is not
wrong. What is wrong is what a driver hands it as a "requirement" when the
criterion is not a check set at all.

Driving on the consensus reference, the obvious encoding is **one
pseudo-requirement per declared output** — ten of them, each passing iff that
output disagrees nowhere.

**THAT ENCODING CANNOT SEE PROGRESS, AND THE ARGUMENT IS ARITHMETIC RATHER THAN
EMPIRICAL.** A wrong design disagrees somewhere on nearly every output, so nearly
every pseudo-requirement is failing; an edit that removes most of the
disagreement on an output but not all of it leaves that pseudo-requirement
failing and the count does not move. Observed: an edit taking the disagreement
from **9,857 cells to under 3,000 — a ~70% reduction — read *passing
requirements 1 → 1* and was REFUSED and rolled back.**

**RE-ENCODED ON (OUTPUT, TESTPOINT) PAIRS THE SAME EDIT LATCHES.** A pair passes
iff that output disagrees nowhere in that testpoint, so an edit that fixes an
output on 200 testpoints and not on 30 raises the count by 200. Re-measured
serially from the unedited held-out design, one commit under the pair ratchet
takes **9,857 cells to 2,540**.

**SO TWO NUMBERS ARE NEEDED AND THEY ARE NOT THE SAME NUMBER**: a FINE one to
steer, which must fall whenever the design improves, and a COARSE one to judge,
which is the property being claimed. The companion document prescribes exactly
this for the check-set loop — *ratchet on (requirement, testpoint) pairs, accept
per requirement* — and this is that prescription arriving as a defect in a driver
that did not follow it. **A criterion coarser than the edits being made is not a
weak gradient; it is no gradient, and it rejects correct work.**

That is the mirror of this plan's other gradient finding. `conviction_count_is
_not_a_descent_criterion` is a count fine enough to move and pointing the wrong
way; this is a count pointing the right way and too coarse to move.

### AND A RUN DIRECTORY WRITTEN BY TWO AGENTS IS NOT A MEASUREMENT — TWICE, BOTH MINE

An editor run directory holds a staged buffer, an accepted design, a best-so-far
design, a trial counter and a re-scored result, and a commit rewrites several of
them in sequence over minutes of simulation. **Two agents pointed at one such
directory — or one agent plus me re-initialising it — leave those files
describing different moments, and nothing in the directory says so.**

It happened twice in this session. The first time I started a re-init while an
editor agent was mid-commit. The second time I dispatched a fresh agent into a
rebuilt directory while the previous agent was still registered and still
working in it; it staged a batch and issued `commit` at 13:46:18, and my stop
interrupted that commit mid-run.

**Both had the same tell: the accepted design's SIZE matched neither the design
the run started from nor the one the last recorded commit produced.** A file that
is not any of the versions the run is supposed to contain is the signature.

**NO NUMBER FROM EITHER DIRECTORY IS QUOTED ANYWHERE ON THIS PLAN.** Both were
archived unread and the run restarted from the unedited held-out design,
serially, with exactly one agent and the full 14-trial budget — which also makes
it directly comparable with the three check-set runs, each of which started from
unedited L. A partial result from a contended directory cannot be repaired by
inspection, because the question is not what the files say but which moment each
of them is from.

**The discipline is one line — one agent per run directory, and the operator does
not touch it while that agent holds it** — and it belongs beside the other
harness rules this plan has had to learn by breaking them: select over the same
corpus the score was taken over, re-score in a fresh directory rather than
comparing a design against itself, and give every arm the same row list.

## THE PRIZE IS 69% AND THE UNIT OF JUDGEMENT IS WHAT KEEPS IT AT 19%

Every measurement on this plan judges a check as a WHOLE BODY. A requirement's
sentence states several obligations, and a body asserting three of them convicts
a design if ANY of the three is violated — so **one over-reaching obligation
makes the body unsound and takes its other two down with it.**

Asked without authoring anything, by partitioning each body's convictions by the
DETAIL STRING it itself emitted. 547 authored bodies, 481 of which decide on both
the reference and held-out L.

| | |
|---|---|
| bodies that are UNSOUND **and** DISCRIMINATING — the class a split can rescue | **307** |
| **requirements they span** | **61 of 89 = 69%** |
| requirements with an adequate body today | 17 of 89 = 19% |

**69% AGAINST 19% IS THE SIZE OF THE PRIZE.** It is this document's central
anti-correlation asked as a granularity question instead of as a distribution:
the discrimination for two thirds of the specification **is already authored**,
sitting inside bodies whose soundness a single obligation ruins.

### The measured ceiling is +4, and it is GOLDEN-SELECTED

Keep only the reasons a body fires with on the held-out design and never on the
reference:

| requirement | the obligation to KEEP | the obligation to DROP |
|---|---|---|
| REQ-0016 | `saved_addr[…] not incremented` | `first_miss_ack not asserted` |
| REQ-0021 | cache-inhibited store asserted `dcram_we` | …asserted `tag_we` |
| REQ-0074 | FSM did not reach idle after the final refill word | load flag not cleared |
| REQ-0084 | store BIU error: `biu_write` not cleared | store ABORT: `biu_write` not cleared |

**Adequacy 17 → 21 of 89, 19% → 24%.** Choosing which reason to drop reads the
reference, so this is a ceiling in exactly the sense MAXSOUND is and **never a
score.** The golden-free form — keep a reason objecting to a MINORITY of the
candidate population, the minority rule applied per REASON instead of per BODY —
is not measured here.

### And the ceiling is itself a FLOOR, because the instrument is 78% blind

| of the 307 eligible bodies | |
|---|---|
| emit **one** message for every conviction they ever make | **239 = 78%** |
| name more than one | 68 |
| of those 68, one reason fires only on the held-out design | **24 = 35%** |

At the requirement level the instrument sees **24 of the 61 eligible = 39%**, and
of those 24 nine carry a held-out-only reason (38%), four of them new.

**WHAT BLINDS IT IS THE DETAIL STRING THE AUTHOR CHOSE, NOT THE CHECK.** A body
asserting three obligations behind one message cannot be cut along them by
anything reading its output. That is a reporting defect and it is free to fix:
**require every objection to name the obligation it fires on.** It costs an
author nothing and takes this instrument from 39% coverage to 100%.

### Even the optimistic extrapolation stops short of a majority

At the observed 38% over all 61 eligible requirements the split would reach
roughly **31 of 89 = 35%**, against the 45 a majority needs. That is an ESTIMATE
and not a measurement — the 37 requirements the instrument cannot see may split
at a different rate, and a body whose obligations share one `if` cannot be cut at
all whatever it prints.

### It is the ratchet finding at the other end of the pipeline

The ratchet defect above is a criterion coarser than the EDITS being made, and it
rejects correct work. This is a criterion coarser than the OBLIGATIONS being
asserted, and it rejects correct assertions. Both say one thing: **the unit you
JUDGE at should not be forced to be the unit you AUTHOR at.**

### The four were READ rather than trusted, and the false positive is the sharpest part

| requirement | how it cuts |
|---|---|
| REQ-0016 | two `return (False, …)` sites — delete one |
| REQ-0074 | two `return (False, …)` sites — delete one |
| REQ-0084 | two independent loops its own comments label `Case 1` and `Case 2` |
| REQ-0021 | ONE verdict over a conjunction of two asserted outputs — drop a conjunct, not a branch |

All four are real cuts, and three different mechanisms produce them.

**AND THE ONE FALSE POSITIVE WAS EXCLUDED BY SYNTACTIC LUCK.** REQ-0039 emits
`outputs changed without a rising clk edge: [a, b, c]` — **one** obligation whose
message varies with which signals witnessed it, on a check that convicts the
reference on 342 of 348 testpoints. REQ-0021 emits `asserted dcram_we=1,
tag_we=1` — **two** obligations whose message varies with which one fired. My
normaliser kept the second and dropped the first **because one used brackets and
the other used a comma-join.** That is a formatting accident, not a principle, so
the +4 is not robust either.

**SO THE PRESCRIPTION IS NARROWER AND STRONGER THAN "PRINT MORE".** The
obligation an objection fires on must be a **structured field the check returns**,
not a phrase inside a message written for a human to read. As prose it is
unreadable for 78% of the population and misreadable for the rest.

## PRE-REGISTERED, BEFORE THE CONSENSUS RUN REPORTS

Written while the editor is still working, so the reading cannot be chosen after
the numbers are in — the discipline this document has had to apply to itself
nine times.

**The conditions are matched to the three check-set runs.** Same held-out design
L, unedited, from a corrected brief and held out of every selection; the same
348-testpoint suite; the same shipped `_EditSession` policy; a 14-trial budget;
one Sonnet editor; one agent in the run directory and nothing else touching it.
The only thing that differs is what the editor is handed — an **observed expected
value** from seven independent implementations instead of **objections** from a
check set.

| criterion | span | testpoints differing of 348 | cells | trials |
|---|---|---|---|---|
| **L, unedited — the baseline** | — | **279 = 80%** | **4,450** | — |
| 21 checks | 16 reqs = 18% | 223 = 64% | 3,969 | 3 of 14 |
| 111 checks | 44 reqs = 49% | **220 = 63%** | 3,834 | 5 of 14 |
| 117 checks | 50 reqs = 56% | 236 = 68% | **3,533** | 4 of 14 |
| **the consensus reference** | — | *pending* | *pending* | *pending* |

All three check-set runs end `DIFFERS`, and the best figure on each measure comes
from a *different* run — 220 testpoints from the 111-check set, 3,533 cells from
the 117-check set — so "best" has to name its measure.

**How the outcome will be read, fixed now:**

| outcome | reading |
|---|---|
| **`NO-DIFF-40`** | the observed expected value is a sufficient criterion where four check sets were not. It answers the goal's validation question, and check authoring is superseded rather than improved |
| **`DIFFERS`, under 220 testpoints AND under 3,533 cells** | the best descent criterion measured on this plan, on both measures at once, which no check set has managed. Report it as that and not as sufficiency |
| **one measure better, the other worse** | mixed. Report both columns and claim nothing — the check-set runs already show the two can move apart |
| **`DIFFERS` in the 220–236 band** | indistinguishable from the check sets, and that is a STRONG negative rather than a null: it removes the one explanation the companion document offers for the editor's weakness, that *"expected/actual is reconstructed, not observed"*. Here it is observed, and it changes nothing |
| **worse than 236 testpoints or 3,969 cells** | the consensus actively misdirects, and the 2,073 cells where the population is collectively wrong are the mechanism to look at first |

**Two readings that are fixed in advance because they are easy to get wrong.**
A run that stops with trials unspent measures the EDITOR and must not be reported
as a result about the criterion. And a run that drives the consensus-cell count
very low while the miter gets worse is the over-strict-zero pattern arriving on a
new criterion — the reference is wrong about 2,073 of its own cells, so matching
it everywhere is evidence against equivalence, exactly as reaching zero against a
set carrying an unsound check is.

## CORRECTED WITHIN THE HOUR: THE REMEDY IS NOT A RULE, IT IS A LOCK

The section above ends *"the discipline is one line — one agent per run
directory, and the operator does not touch it while that agent holds it."*
**I then broke it a third time, within the hour, having just written it down.**

The rule was in every dispatch brief, in capitals, with both previous failures
named. The third instance was not an agent ignoring it. It was **me** stopping
one of two registered agents and dispatching a new one into the directory the
**other** was still holding, having never enumerated the live writers. The newly
dispatched agent detected the collision itself, refused to commit, and reported
it — which is the only reason it was caught.

**A rule that must be remembered by every operator and every agent on every
dispatch is not a rule; it is a hope, and this one failed three times out of
three.** Every mutating driver command now takes an exclusive lock on the run
directory:

    REFUSED: loopCONS is held by pid 15110 running 'commit' since 14:11:03.
    One writer per run directory -- wait for it, or stop it deliberately.

Reads are unlocked, so a reader can never block a writer. A lock whose pid is
gone is reclaimed and the takeover is printed rather than done silently, because
a killed writer must not wedge the directory forever. **Three destroyed runs is
what it cost to prefer the rule to the mechanism.**

## AND THE EDITOR'S DATAFLOW SLICE WAS DEAD IN EVERY RUN ON THIS PLAN

Found by the third agent, not by any number looking wrong — the thirteenth
counting-shaped defect here and mine.

Every driver command is a fresh process that rebuilds the edit session from
`state.json`. All three drivers test `s.focused` to decide whether to build the
slice **about thirty lines before the line that reads `focused` out of
`state.json`.** So `s.focused` is the constructor default when it is tested,
`blocks_by_id` is empty on every invocation, and `blocks` and `readblock` return
nothing and `unknown block_id`.

**So no editor run here — not the ceiling runs, not the golden-free rule runs,
not the 21-, 111- or 117-check runs — had `list_suspect_blocks` or `read_block`.**
What it had was the `focus` call's own output, computed in-process and therefore
correct, and nothing afterwards. Every editor read the whole module and worked
from that. The companion document puts the slice at the centre of the editor's
evidence — *"`focus(req_uid)`. Slice from one requirement's ports at a time"* —
and it was never delivered.

**The confound is CONSTANT ACROSS ARMS, which is the one piece of good news.**
Every run was degraded identically, so the comparisons *between* check sets
stand. What does not stand is any absolute reading: **every `DIFFERS` on this
plan was produced by an editor missing the tool the architecture puts at the
centre of its evidence**, so they are pessimistic by an unknown amount.

**And fixing it costs comparability, which has to be paid rather than avoided.**
A fixed driver running one new arm cannot be compared against arms run on the
broken one. The course taken is to fix the driver and re-run the arms that carry
the conclusion, not to leave a tool broken for the sake of a table.

## THE CONSENSUS RUN: IT DESCENDED THROUGH THE REFERENCE'S OWN FLOOR

One Sonnet editor, held-out design L unedited, 348 testpoints, 14 trials, one
writer under the lock, and — for the first time on this plan — a **working
dataflow slice.** The editor is handed an OBSERVED expected value instead of
objections.

| trial | consensus cells | (output, testpoint) pairs passing | failing | latched? |
|---|---|---|---|---|
| init | 9,857 | 2,975 | 515 | — |
| 1 | 3,022 | 2,975 → 3,167 | 515 → 323 | latched |
| 2 | 3,003 | 3,167 → 3,210 | 323 → 280 | latched |
| 3 | *2,721* | 3,210 → 3,192 | 280 → *298* | **refused** |
| 4 | *2,786* | 3,210 → 3,186 | 280 → *304* | **refused** |
| 5 | *2,216* | 3,210 → 3,205 | 280 → *285* | **refused** |
| 6 | 2,109 | 3,210 → 3,237 | 280 → 253 | latched |
| 7 | **1,758** | 3,237 → **3,278** | 253 → **212** | latched |

**82% off the criterion in 7 of 14 trials.** Graded in its own clean directory,
three pins green: **`DIFFERS`, 210 of 348 testpoints (60%), 3,890 cells.**

### THE FLOOR WAS 2,073 AND THE LOOP WENT UNDER IT

`the_consensus_is_an_oracle_even_though_it_is_not_a_ranking` measured the
reference wrong on **2,073 of its own 240,573 cells** — 0.86%, because seven
readers of one specification share misreadings — and that figure was written down
**in advance** as the floor.

**The design finished at 1,758. That is proof of non-equivalence before any miter
runs**: it agrees with the seven on at least 315 cells where the known-good
design does *not*, so it cannot be the known-good design. Exactly the arithmetic
that made zero fatal against a set convicting the reference seven times, arriving
on a criterion that is honest and merely incomplete.

### AND THE PROXY MOVED SEVERAL TIMES FASTER THAN THE TRUTH

| | start | end | move |
|---|---|---|---|
| the criterion | 9,857 | 1,758 | **−82%** |
| testpoints differing from the reference | 279 | 210 | −25% |
| cells differing from the reference | 4,450 | 3,890 | −13% |

Different denominators, so the percentages are not directly comparable — but the
loop reduced its own objective far faster than it reduced its distance from
correctness. **That is what Goodharting looks like when the criterion is honest.**

### It removes the companion document's own explanation for the editor's weakness

That document names the loop's weakest point outright: *"expected/actual is
reconstructed, not observed … a fabricated expected value would make it CONFIDENT
in a wrong theory."* **Here it was observed** — seven agents who never saw each
other's work — and the design still ends `DIFFERS`. Being real rather than
reconstructed is not what was missing.

### Against the pre-registered table: MIXED, and confounded

| criterion | span | testpoints of 348 | cells | trials |
|---|---|---|---|---|
| L, unedited | — | 279 = 80% | 4,450 | — |
| 21 checks | 18% | 223 = 64% | 3,969 | 3 of 14 |
| 111 checks | 49% | 220 = 63% | 3,834 | 5 of 14 |
| 117 checks | 56% | 236 = 68% | **3,533** | 4 of 14 |
| **consensus** | — | **210 = 60%** | 3,890 | 7 of 14 |

The pre-registration says: *one measure better, the other worse → mixed, report
both columns and claim nothing.* Honoured. **And it is confounded in the
consensus run's favour** — it had a working dataflow slice and the three
check-set runs did not. The 117-check arm is being re-run on the fixed driver so
the comparison is between two criteria rather than between two harnesses.

### The ratchet correction, which is the other half

Three times — trials 3, 4 and 5 — the raw **cell** count fell while the
**(output, testpoint) pair** count rose, and the pair ratchet refused all three.
Trial 5 was a 26% cell improvement that made the property worse. **The refusals
cost nothing on either measure**: a refused commit keeps the staged buffer,
trials 6 and 7 built on it, and the run ended at 1,758 — lower than any of the
three designs a cell ratchet would have taken.

So the earlier finding needs correcting. *"A criterion coarser than the edits is
no gradient and rejects correct work"* is true of the per-output ratchet and
false as a general claim. **Ratchet at the granularity of the PROPERTY being
claimed, not of the EVIDENCE.** A cell is evidence; a (output, testpoint) pair is
the property. Per-output is coarser than the property and refuses real progress;
per-cell is finer and accepts real regressions. Both are measured here, on one
criterion, in one run.

**One defect remains and it is in the brief, not the ratchet:** the editor was
told its score was cells while the loop latched on pairs, so three refusals
looked arbitrary from where it sat — it reported the discrepancy itself. **The
number an agent is asked to optimise must be the number that latches.**

### AND THE ROUTE IS BOUNDED BY THE SPECIFICATION, NOT BY THE EDITOR

The design the consensus loop produced, re-scored at **raw edges** — the
transactional view compresses each design independently, so only raw edges are
alignable across designs — with every cell classified by whether the seven agree
there:

| | cells | of all | still wrong | rate |
|---|---|---|---|---|
| the seven **AGREE** | 238,559 | 94% | 1,718 | **0.7%** |
| the seven **SPLIT** | 13,951 | 6% | 3,405 | **24.4%** |

**66% of what is still wrong is where the population cannot agree — a 12.0x
concentration — and those are exactly the cells the consensus criterion is
SILENT on, by construction.** A unanimous reference has nothing to say where
there is no unanimity.

**So the route is exhausted by the specification rather than by the editor.**
Even a perfect consensus-driven loop could address at most the 34% of the residue
in agreed cells. The other 66% sits where a targeted reader was measured
reproducing the population's own wrong answer 7 times in 9 — so no instrument
drawn from this text resolves it: not a check, not a consensus, not a better
editor.

**And it explains the floor result mechanically.** The loop drove the error rate
on cells the criterion *can* see down to **0.7% — below the 0.86% at which the
reference itself is wrong** — while the part it cannot see stayed wrong at 24.4%.
Descending through the floor and stalling at `DIFFERS` are one event seen from
two sides: the loop over-fitted the agreeable half of the behaviour because that
is the only half its criterion scores.

**One figure here was NOT pre-registered and must not be used as a tiebreak.** At
raw edges this design is wrong on **5,123** cells against **10,926** for the
design the 117-check loop produced — which looks decisive for the consensus
criterion, and is a *third* measure computed afterwards as the input to this
analysis. The pre-registered pair reads 210 against 236 testpoints and 3,890
against 3,533 transactional cells. **That is MIXED, and mixed is what stands.**

## THE HEAD-TO-HEAD, ON ONE HARNESS: THE CRITERION IS NOT THE BINDING CONSTRAINT

Every earlier comparison on this plan differed in the harness as well as the
criterion — the dataflow slice was dead in all of them. This pair shares one:
same held-out design L unedited, same 348-testpoint suite, same 14-trial budget,
one writer under a lock, and a **working slice on both**.

| criterion | testpoints of 348 | cells | trials | grade |
|---|---|---|---|---|
| L, unedited | 279 = 80% | 4,450 | — | — |
| **117 checks, 50 of 89 = 56%** | **206 = 59%** | **3,866** | 8 of 14 | `DIFFERS` |
| **the consensus of seven** | **210 = 60%** | **3,890** | 7 of 14 | `DIFFERS` |

**Four testpoints and twenty-four cells apart. They are indistinguishable.** A
golden-free check set spanning a majority of the specification and an *observed*
expected value from seven independent implementations drive the same design to
the same place, within 1.2%. Both `DIFFERS`, all pins green.

### And the consensus criterion is twice as good at what it measures, which bought nothing

| | AGREE cells (94%) | rate | SPLIT cells (6%) | rate | share of residue in SPLIT |
|---|---|---|---|---|---|
| 117 checks | 3,066 | 1.3% | 3,837 | 27.5% | 56% |
| consensus | **1,718** | **0.7%** | 3,405 | 24.4% | **66%** |

The consensus criterion scores *only* the agreed cells, and it halves the error
there — and none of that reaches the grade, because both designs' remaining
wrongness is concentrated where the seven **cannot** agree.

### So the criterion is not the binding constraint, and that is the session's result

Every route this plan has tried — more span, better selection, narrowing,
strengthening, volume, an ensemble of checks, an ensemble of designs, and now an
observed expected value — optimises something computed from the specification.
**The specification underdetermines the cells where these designs are actually
wrong**, and that bound is now measured from two directions at once.

**Two confounds, both named, both pointing the same way.** The check-set loop
ratchets per CHECK where the consensus loop ratchets per (output, testpoint)
PAIR, which handicaps the check set — so if anything it is the stronger of the
two, and it still only ties. And it spent 8 trials to the consensus arm's 7,
which is not enough to explain four testpoints.

**What the slice was worth, priced by the same pair.** The identical 117-check
set on the broken harness reached 236 testpoints and 10,926 raw-edge cells in 4
trials; on the fixed one, **206 and 6,903 in 8**. Better on both, confounded with
the trial count, so the slice is worth something and how much is not separable
here.

## AND THE EDITOR'S SOUNDNESS JUDGEMENT IS NOW MEASURED THREE TIMES: 1 OF 3, 1 OF 5, 1 OF 5

The 117-check editor reported *"a proven, structural contradiction, not a
diagnosis of mine alone"* between REQ-0035 and REQ-0059/REQ-0060, having flipped
the definition three times and watched the three requirements flip in lockstep.
**The audit refutes it in one column** — every one of those checks convicts the
reference design ZERO times, so a design satisfying all three exists and the
reference is it. What the editor measured is that *its* implementation could not,
which is a different claim.

| the check it judged over-strict | *audit: convicts the reference* | verdict |
|---|---|---|
| REQ-0035 (3 members) | *0* | **wrong** |
| REQ-0059 (4 members), REQ-0060 | *0* | **wrong** |
| REQ-0069.shipping | *0* — and it catches held-out L: **ADEQUATE** | **wrong** |
| REQ-0088.shipping | *0* — catches L **37 times**: **ADEQUATE** | **wrong** |
| REQ-0081 (2 members) | ***1 — genuinely unsound*** | **right** |

**1 of 5.** And the one it got right is the only one it hedged — *"my
best-evidenced hypothesis, not a certainty"* — while the two it was most
confident about are not merely sound but **adequate**, and it backed a fix out of
the design on the strength of judging one of them over-strict.

Three independent measurements now: **1 of 3** on the ceiling run, **1 of 5** on
the 111-check set, **1 of 5** here. And it is the **second** time an editor has
declared a sound set self-contradictory. The editor cannot substitute for a
soundness gate, its confidence runs the wrong way, and this is the one claim it
makes that it has no means of checking.

## THE FLOOR: 146 OF 348 TESTPOINTS, AND IT ANSWERS THE GOAL'S FINISH CONDITION

Grant a spec-derived criterion its best case. Suppose it drove the design to be
correct on **every cell the seven independent readings agree on** — perfect,
which no run here comes near. Where they disagree it has no opinion to drive
with: a check convicting there is as likely wrong as right, and a consensus is
silent by construction.

Per testpoint, on the design the consensus loop produced, at raw edges:

| | testpoints | |
|---|---|---|
| differing anywhere | 168 = 48% | |
| …at a cell the seven **AGREE** on | 84 = 24% | reachable |
| …at a cell the seven **CANNOT agree** on | **146 = 42%** | **THE FLOOR** |

**Only 22 of 348 testpoints — 6% — differ exclusively at cells a spec-derived
criterion has an opinion about.** Every other differing testpoint contains at
least one cell the specification, read seven independent times, does not
determine.

**So equivalence is not reachable by steering from this specification.** Not by a
wider check set, not by more adequate checks, not by an ensemble of checks or of
designs, not by an observed expected value, not by more trials or a better
editor — each of those is computed from the text, and the text is silent where
the design is wrong.

### One precision, because the claim is easy to overstate

This bounds what a criterion can **steer**, not what a design can **achieve**. A
design may be right in a split cell by luck, or because its author happened to
guess as the reference did — 94% of cells are agreed and the population is right
on 99.1% of those. What no check set, ensemble or consensus can do is *drive* it
there, having no opinion to drive with.

### And it is a trajectory, not two endpoints

| design | agreed-cell wrongness | split-cell wrongness | share of residue in SPLIT |
|---|---|---|---|
| L, unedited | 9,140 (3.8%) | 5,464 (39.5%) | **37%** |
| after the 117-check loop | 3,066 (1.3%) | 3,837 (27.5%) | **56%** |
| after the consensus loop | **1,718 (0.7%)** | 3,405 (24.4%) | **66%** |

The agreed-cell wrongness falls **81%**; the split-cell wrongness falls 38%; and
the share of what remains that sits in split cells rises monotonically. **The
loops clear what the specification determines and stall on what it does not** —
the mechanism, not a correlation.

### A fourteenth counting-shaped defect, mine, caught by the guard it now carries

The first run of `floorbound.py` printed **0 testpoints differing** on a design
the miter had already graded `DIFFERS` at 210. Cause: it read a recorded edge's
port values from `e["outputs"]` — the key a ROW has, not an EDGE — so every value
was `None`, all seven "agreed" on `None`, and nothing ever differed. A clean
sheet is the signature of an instrument that never ran, and this is the
fourteenth time on this plan. The script now **refuses to report zero on a design
known to differ.**

# THE GOAL, ANSWERED CLAUSE BY CLAUSE — FINAL

**Every figure below is golden-free except the audit column, which is computed
last and feeds no selection, no prompt and no routing decision.**

| the goal asked | the answer |
|---|---|
| *an adequate set spanning the majority of the spec* | **span met, adequacy not.** 117 checks over **50 of 89 = 56%**, selected by a conviction-count rule over seven spec-derived designs and nothing else. *Audit: 11% convict the reference.* Measured adequacy **17 of 89 = 19%** |
| *validated by a Sonnet RTL Editor loop producing a design equivalent to golden* | **No — five times, and the fifth removes the last explanation.** 21-, 111-, 117-check sets, the 117-check set again on a fixed harness, and an *observed* expected value from seven implementations. All `DIFFERS`, all pins green |
| *…and it is now a bound rather than a tally* | **146 of 348 testpoints = 42% differ at cells the specification does not determine.** Only 6% differ exclusively where a spec-derived criterion has an opinion. Equivalence is not reachable by steering from this text |
| *finish the stimulus loop* | **measured unnecessary, twice.** 3 checks of 50 are silent where their own port is wrong; 36 of 50 look at it and pass. And the residue is in cells the suite already reaches — adding stimulus in the split region *adds* unanswerable cells |
| *the untrusted-without-probes population* | **no better success rate**, p = 1.000 on 34 paired requirements — but the adequate sets are **disjoint**, so the union is 5 where the better arm alone is 3. An arm comparison decides which prompt to ship, never which bodies to keep |
| *take oscillations between repairs into account* | measured as a decay curve: repair lands 18% then 4%; narrowing 15% then 4%. Two levers, opposite directions, identical second-round rate |
| *an arbitrary unchecked LLM design as the source* | design L, written from the specification by an agent forbidden to open any other implementation, held out of every selection that produced the sets judging it |
| *proxy metrics chosen by how well they facilitate the editor* | three, all measured: **ratchet at the granularity of the property, not the evidence**; **a descent criterion needs a knowable floor**, and this one has one and the loop still walked past it; **the number an agent optimises must be the number that latches** |
| *prompts and gates are fair game* | a run-directory **lock** (three destroyed runs), the **dataflow slice** repaired (dead in every editor run on this plan), the **ratchet** re-encoded, narrowing and strengthening rounds re-authored |

## WHAT WOULD CHANGE THE ANSWER, AND IT IS NOT A LEVER IN THIS PIPELINE

A decision on the underdetermined cells, from outside the
specification-and-reader loop. The disagreement map localises them at **10–12x**
and is the artifact to put in front of whoever can make that decision. Nothing
here can make it: a targeted reader asked one question about one such cell
reproduces the population's own wrong answer 7 times in 9, and **0 of 20 noticed
the question was open.**

# THE STACKED SPEC-ONLY CRITERION: ONE TESTPOINT, AND THE FLOOR AGAIN

The strongest spec-only configuration this plan can build. Unanimity over seven
independently written implementations gives a dense gradient, right 99.1% where
it speaks and **silent** on the 6% of cells they split on — which is the whole of
the floor. The 117 requirement-derived checks are the only other spec-only
instrument that says anything *there*. Both in one ratchet, 30 trials, from
unedited L, one writer under the lock, working dataflow slice.

| criterion | testpoints of 348 | cells | trials | grade |
|---|---|---|---|---|
| L, unedited | 279 = 80% | 4,450 | — | — |
| consensus alone | 210 = 60% | 3,890 | 7 of 14 | `DIFFERS` |
| 117 checks alone | 206 = 59% | 3,866 | 8 of 14 | `DIFFERS` |
| **both, stacked** | **205 = 59%** | 3,608 | **27 of 30** | **`DIFFERS`** |

**Stacking a second spec-only instrument bought ONE testpoint, on nearly four
times the budget.**

## The split residue, for the fourth time, monotone

| design | agree-cell wrongness | split-cell wrongness | share of residue in SPLIT |
|---|---|---|---|
| L, unedited | 9,140 (3.8%) | 5,464 | 37% |
| after the checks | 3,066 (1.3%) | 3,837 | 56% |
| after the consensus | 1,718 (0.7%) | 3,405 | 66% |
| **after both** | **1,302 (0.5%)** | 3,129 | **71%** |

Each instrument clears what it can see. **Stacking them clears more of the
visible region and nothing of the invisible one.**

## The Goodhart measurement, now with seventeen trials behind it

The editor was resumed and explicitly told not to stop early. Trials 11–27:

| | proxy: cells | proxy: checks | **GRADE: testpoints** | **GRADE: cells** |
|---|---|---|---|---|
| after trial 10 | 1,924 | 8 of 117 | **204** | **3,577** |
| after trial 27 | **1,693** | **6 of 117** | **205** | **3,608** |

**−12% and −25% on what the loop optimises; backwards on both measures of what
it is judged by.** Once the region a spec-derived criterion can see is
exhausted, further descent on it is uncorrelated with correctness.

## And a majority vote cannot fill the silence — measured BEFORE this run

In the cells where the seven split, the majority value equals the reference's
**38.4% of the time.** Below chance: a majority criterion steers *away* in 62% of
the cells where it speaks. By margin:

| agreement | cells | majority right |
|---|---|---|
| 4 of 7 | 422 | 74.9% |
| **5 of 7** | 5,731 | **12.3%** |
| 6 of 7 | 7,820 | 55.5% |

At five-of-seven the two dissenters are right **87.7%** of the time — the
population converges on the wrong answer and the outliers read the specification
correctly. **So unanimity's refusal to speak there is OPTIMAL for a population
criterion, not conservative**, and the floor is a property of the specification
rather than of the choice of vote.

## AND A DEFECT IN MY OWN COMBINED CRITERION: TWO INSTRUMENTS, NO WEIGHTS

`_EditSession.commit` latches on a COUNT of passing units. Putting two
instruments in that count without weighting them makes the ratio of their
cardinalities the exchange rate between them, silently:

| | units |
|---|---|
| (output, testpoint) pairs | 3,480 |
| per-output | 10 |
| **checks** | **117 — 3.2% of the total** |

**One check weighs the same as one output on one testpoint — 1/29 of the
cell-derived mass.** The checks were nominally in the ratchet and effectively
powerless, which is the mechanism behind the stacked run gaining a single
testpoint.

**And it shipped a design violating a sound check, deliberately.** The editor
added a live cache-inhibit guard to `tag_we`, gained ~11 cells, and broke
REQ-0034 — a check all six of whose members spare the reference. It attempted the
revert **three times, in three forms, and the ratchet refused every one**, because
returning the pair-units cost more than the single check unit regained. It
documented the trade and could not act on it.

**So a combined criterion is a weighting decision and must be made explicitly.**
Summing two instruments does not combine them; it prices one in units of the
other at whatever ratio their cardinalities happen to have — and **the sparse
instrument is exactly the one that loses, because sparse is what it is for.**

## THE EDITOR'S SOUNDNESS JUDGEMENT, FOUR RUNS: 7 OF 29

This editor claimed REQ-0087.shipping and REQ-0087.control are unsatisfiable
together, having tested *both* formulations and concluded no third exists. Both
convict the reference **zero** times, so a design satisfying both exists and so
does the third formula. That is the **fourth** structural-contradiction claim in
four runs and the fourth refutation.

| flagged unsatisfiable | *convicts the reference* | |
|---|---|---|
| REQ-0087.shipping, REQ-0087.control | *0, 0* | **wrong** |
| REQ-0029.t2, REQ-0030.control, REQ-0030.band@band | *0* | **wrong** |
| REQ-0015.v2@n3, REQ-0064.t1@n3 | *0* | **wrong** |
| **REQ-0081.control, REQ-0081.merge@merge** | ***1, 1*** | **right** |

**2 of 8, and 7 of 29 across four runs ≈ 24%.** REQ-0081 is the one genuinely
unsound check in the set, and **the last two editors independently found it** —
a real signal inside a 24%-precision channel.

## A FINISHED RUN CANNOT BE ASKED WHAT ITS RATCHET REFUSED, AND THAT IS MINE

The combined criterion weighted its two instruments by the accident of their
cardinalities — 3,480 cell-pair units against 117 check units, so one check was
worth 1/29th of one cell-pair. That is recorded above. The obvious next question
is a counterfactual: **which of the finished run's 27 commits would a different
weighting have latched, and which would it have refused?** It is free to ask if
the run kept its per-commit numbers.

**IT DOES NOT. A 27-TRIAL RUN RECORDS 27 DECISIONS AND KEEPS ONE.**

| artifact | what it holds |
|---|---|
| `state.json` | the CURRENT counters — trials used, last latched score, best score |
| `report.json` | the LAST review. **Overwritten by every commit** |
| `best.v` | the design, with no provenance |

The accept criterion is the object under study on this whole plan, and its own
decisions are the one thing not written down.

### The cost is exact, and it was paid

Re-weighting is one line of arithmetic. Pricing it against the run it was
written for should have been a replay over recorded numbers — no simulation, no
model call, seconds. Instead it takes a fresh 30-trial run: a full 348-testpoint
suite per commit, plus an editor. **The change is trivial and the measurement is
not, entirely because of what was not kept.**

### And it bounds what may be claimed about every arm already run

Four arms landed at **205, 206, 210 and 205** testpoints of 348. Whether that
band is a property of the specification, of the design space, or of a ratchet
refusing correct work in all four is a question about the **refused** commits —
and not one of the four runs can be asked it. The band is reported as measured;
its **cause is not attributable** from the artifacts those runs left. Every
"the loop stops here" sentence on this plan should be read with that limit
attached.

### The remedy is one append per commit, and it is not a rule

A ratchet that decides must log what it decided and on what evidence: the
proposed unit counts, the latched unit counts, the verdict, and the
per-instrument numbers on both sides. Anything less makes the loop's own accept
criterion the only unaudited component of a pipeline built to audit criteria.

**This is the phantom-baseline defect again, in its quieter form.**
`req_results.json` was rewritten by every review including rolled-back ones, so
nothing ever latched and the tell was a stale timestamp. Both are the loop
failing to distinguish what it **considered** from what it **accepted**. That
one produced wrong numbers; this one produces no numbers at all, which is
harder to notice and took longer to find.

## THE WEIGHTING WAS THE LAST LEVER, AND IT MOVES THE GRADE BY ZERO

The combined criterion summed two instruments into one pass-count and thereby
priced them against each other at the accident of their cardinalities. This is
that defect fixed and nothing else changed: each of the 117 checks emitted as
**30** units, so the checks weigh 3,510 against the cells' 3,490, with the same
starting design, the same two instruments byte-for-byte, the same 348-testpoint
suite and the same 30-trial budget.

### The fix works, mechanically, and this time it is on the record

Between trials 5 and 6 the editor broke a sound check and fixed it forward. The
per-commit log — which no earlier run kept — shows what the ratchet did with
that:

| | cells | objecting checks | latched? |
|---|---|---|---|
| after trial 5 | 2,710 | 8 | — |
| after trial 6 | **2,728 (eighteen worse)** | **7** | **YES** |

That is the exact trade the unweighted run attempted three times and had
refused. The editor reports **zero refusals across nine commits**: *"every fix I
made was net positive under the 30-units-per-check weighting, so I never needed
to fight the scoreboard."*

### And the grade is identical

| criterion | testpoints of 348 | cells | trials | grade |
|---|---|---|---|---|
| L, unedited | 279 = 80% | 4,450 | — | — |
| consensus alone | 210 = 60% | 3,890 | 7 of 14 | DIFFERS |
| 117 checks alone | 206 = 59% | 3,866 | 8 of 14 | DIFFERS |
| both stacked, unweighted | 205 = 59% | 3,608 | 27 of 30 | DIFFERS |
| **both stacked, EQUAL WEIGHT** | **205 = 59%** | **3,696** | **9 of 30** | **DIFFERS** |

All three miter pins green in the same process.

### THE TWO MEASURES MOVE IN OPPOSITE DIRECTIONS BETWEEN THE ARMS

This is the cleanest Goodhart instance on the plan, and it is cleaner than the
within-run version because nothing else differs:

* **the proxy improved 22%** — 1,693 cells disagreeing with the consensus down
  to 1,325;
* **true divergence got 2.4% worse** — 3,608 differing cells up to 3,696;
* **the testpoint count did not move at all** — 205 against 205.

Every earlier Goodhart finding here shows a proxy falling faster than the grade.
This one shows a proxy falling while the grade rises.

### What it does not buy, said before anyone reads the trial count

Nine trials against twenty-seven for the same grade. That is one sample per arm
with one editor per arm, so **the 3× is not attributable to the weighting** —
editor variance is uncontrolled at n = 1.

**So the combination question is closed on its pre-registered reading.** Two
spec-derived instruments, stacked, at every weighting anyone has a reason to
choose, land the same design in the same place. The 205–210 band across five
arms is a property of what a specification-derived criterion can see, not of how
its parts are priced.

### The fifth contradiction claim, and the fifth refutation

The editor reported REQ-0087.shipping (`dc_addr == start_addr` while
`hitmiss_eval`) as mutually unsatisfiable with REQ-0087.control, REQ-0029.t2 and
REQ-0030.\* (`dc_addr == saved_addr` while `biu_read || biu_write`) on TP-9203,
and resolved the tie three-checks-to-one, calling it *"a trade, not a fix"*.

**All five members spare the known-good design** — 348, 348, 348, 256 and 279
decisions, zero convictions each — so a design satisfying the whole group
exists, and there was no trade to make.

**Its other claim is correct.** REQ-0081.control and REQ-0081.merge@merge both
convict the known-good design on TP-9202 edge 11, for exactly the reason given:
the check compares the entry row to the next row and cannot distinguish
*incremented on entry* from *correctly began receiving the first refill word*.
Three independent editors have now named REQ-0081 and all three were right.

**Running tally over five runs: 9 of 36 = 25%** — 1 of 3, 1 of 5, 1 of 5, 2 of
8, 2 of 7. An editor with the design, the trace and the requirement sentence in
front of it is right about a check one time in four, and cannot tell its correct
call from its incorrect one: both arrive as the same confident structural
argument. No gate can distinguish them either.

One part of its judgement did track the truth. It flagged REQ-0015.v2@n3 as *"a
hypothesis, not a finding"* because it could not get the evidence, and the audit
says that check is sound. **The hedge was the reliable half.**

## A CRITERION CORRECTS ONLY WHERE IT BEATS THE DESIGN IT IS JUDGING

Five arms have now landed at 205, 206, 210, 205 and 205 testpoints of 348. That
band has been reported as "where a spec-derived criterion stops" without a
mechanism. Two audits supply one, and the first refutes half of this plan's own
conclusion.

### The answer is IN the population, 94.5% of the time

The split region — the 6% of cells the seven spec-derived designs cannot agree
on, carrying 65% of what the best arm still gets wrong — was assumed to be where
the specification's answer is simply absent. It is not:

| in a split cell, the right value is held by | cells | |
|---|---|---|
| **at least one of the seven** | **13,210** | **94.5%** |
| none of them | 763 | 5.5% |

**So the problem is selection, not absence.**

### And the distribution is bimodal, which is why no vote can work

| the right value is held by | share of split cells |
|---|---|
| 1 of 7 | 24.5% |
| 2 of 7 | 31.4% |
| 3 of 7 | 0.2% |
| 4 of 7 | 2.3% |
| 5 of 7 | 5.0% |
| **6 of 7** | **31.1%** |

Fifty-six percent of split cells have the answer in a minority of one or two;
thirty-one percent have it in six of seven. **The two regimes want opposite
polarity**, so any threshold wins one and loses the other — which is exactly the
majority's measured 38.4%.

### Dissent predicts who holds it, and dissent is spec-only

| design | dissent rate (spec-only) | *audit: right in split cells* |
|---|---|---|
| G | 91.7% | *63.7%* |
| C | 38.3% | *63.9%* |
| F | 5.2% | *34.1%* |
| H | 3.9% | *38.8%* |
| E | 3.0% | *35.7%* |
| B | 2.5% | *36.4%* |
| D | 2.3% | *36.1%* |

**Pearson r = +0.882** over the seven — n = 7, so a shape rather than a
statistic. This is the outlier finding arriving *inside* the population:
correctness makes a design dissent.

### And every selector built on it is useless, for one reason

Each selector reads only the seven designs. Each is scored twice — accuracy over
all split cells, and **precision restricted to the cells where it would actually
object**, which is the only place it can do harm or good:

| selector | accuracy | objects on | **precision** |
|---|---|---|---|
| majority | 38.4% | 9,822 | **19.2%** |
| minority | 56.0% | 4,787 | **13.2%** |
| follow the top dissenter | 63.7% | 3,861 | **17.8%** |
| follow the 2nd dissenter | 63.9% | 6,217 | **30.8%** |
| anti-majority | 56.1% | 4,791 | **12.9%** |

**Not one reaches 50%, so obeying any of them makes the design worse** — and the
best accuracy in the table has the second-worst yield per objection.

### The law, and it is arithmetic

**The design under test is already right on 77.5% of split cells.** On the cells
where a 63.9%-accurate selector disagrees with a 77.5%-accurate design, the
selector is usually the one that is wrong. So its objections are mostly false
whatever its headline accuracy says.

> **A criterion corrects only where its accuracy exceeds the design's.**

That is why five arms land in the same place. Where the seven agree the
consensus is right 99.1% and beats the design comfortably, and every arm drives
the agreed-cell error under 1%. Where they split, **nothing spec-derived beats
it** — not a vote, not a minority, not the best single member — so the loop has
nothing to say and the grade stops at the floor.

### What this qualifies

This plan concludes that the missing input is *"a decision on the
underdetermined cells, from something outside the specification-plus-reader
loop."* **The first half is refuted: the decision is inside, 94.5% of the time.**
What is missing is an extractor, and extraction is hard for a reason the plan
never named — the design under test is a competent reader of the same
specification, and in the region that matters it is a **better** one than any
rule over the population that produced it.

## THE LOOP DROVE THE DESIGN PAST ITS OWN CRITERION, AND I RESUMED IT ANYWAY

The weighted run's editor stopped at 9 of 30 trials with 1,325 cells still
disagreeing with the consensus of seven. I read that as budget left on the table
and dispatched a resume telling it to spend the rest on those cells. Then the
precision test from the section above was applied to the criterion itself:

| at the 238,678 cells where the seven AGREE | |
|---|---|
| the consensus of seven is right | **99.13%** |
| **the design under test is right** | **99.30%** |

**The design has overtaken its own criterion**, and the objections it had left
say so outright. Of the 1,314 cells where the two disagree — which is every
objection the loop still had:

| | cells | |
|---|---|---|
| the consensus is right, the design wrong | 375 | 28.5% |
| **the design is right, the consensus wrong** | **773** | **58.8%** |
| both wrong | 166 | 12.6% |

**Twice as often as not, an objection is the criterion being wrong.** Driving
those 1,325 to zero would have repaired 375 cells and broken 773. The resume was
stopped before it committed anything.

### The mechanism: one accuracy is fixed and the other rises

A criterion built from a population is a fixed artifact — 99.13% is all the
seven will ever be. The design's accuracy climbs as the loop works. **They
cross.** After the crossing every remaining objection is more likely wrong than
right, while the objection *count* keeps falling — so the loop reads the whole
descent as progress and has no way to see the inversion.

### It explains the arm-to-arm Goodhart exactly

Between the unweighted and weighted stacked runs the proxy improved 22% while
true divergence rose 2.4% and the grade did not move. That is not two arms
disagreeing by chance; **it is what descending past the crossing point looks
like from inside.**

### The prescription is a stopping rule, not a better criterion

A loop driven by a fixed-accuracy reference must stop when the artifact reaches
that reference's accuracy. Everything after that is damage the loop scores as
progress. In a benchmark the crossing is measurable. **In production it is
not** — which makes the trial budget, the crude device this plan has been
treating as a cost, the only protection against it.

### And it reframes "the editor stopped early"

This plan has twice recorded a run stopping with budget unspent as a weakness of
that run. On this evidence the editor stopped at very nearly the right moment,
for reasons it could not have articulated — and **my correction of it was the
error**, not its stopping.

## A CONSENSUS CANNOT OUTRANK A COMPETENT READER, AT ANY POPULATION SIZE

The inversion above has an obvious remedy: 99.13% is a property of **seven**
designs, not of the specification, and the goal puts oracle regeneration
explicitly in scope. So make the fixed side less fixed — generate more designs,
and the unanimous set shrinks toward the cells everyone gets right.

**Priced on the designs already in hand, before generating a single new one.**
Headroom is the criterion's accuracy minus the design's, on the cells the
criterion actually speaks about, averaged over all subsets of each size:

| designs | coverage | consensus | the design there | headroom |
|---|---|---|---|---|
| 2 | 97.9% | 97.161% | 98.498% | **−1.337%** |
| 3 | 96.9% | 97.775% | 98.702% | **−0.926%** |
| 4 | 96.1% | 98.257% | 98.873% | **−0.615%** |
| 5 | 95.5% | 98.642% | 99.029% | **−0.387%** |
| 6 | 94.9% | 98.933% | 99.171% | **−0.238%** |
| 7 | 94.5% | 99.131% | 99.298% | **−0.167%** |

**Negative at every size, closing without ever crossing.** Each added design
removes about 35% of the remaining deficit, so thirteen designs projects to
−0.016% and twenty to −0.001% — **asymptotic to zero from below.** Growing the
population cannot restore the criterion's authority, and that is measured rather
than assumed: six generations and six suite runs unspent.

### The reason is in the column nobody would have watched

**The design's own accuracy on the surviving cells rises too**, 98.498% →
99.298%, in lockstep with the criterion's. Unanimity *selects for easy cells*,
and a design written from the same specification is a competent reader of
exactly those. Both curves are driven by the same hidden variable — how hard the
cell is to read correctly — so growing the population moves them together and
never apart.

### The crossing is real, and it is now located

The same measurement against the **unedited** held-out design, same population,
same suite:

| | consensus | the design | headroom |
|---|---|---|---|
| **L, unedited** | 99.163% | 96.160% | **+3.003%** |
| after 9 trials | 99.131% | 99.298% | **−0.167%** |

The criterion began as a far better reader than the design and was overtaken.
Interpolating the run's own per-commit log between those two measured endpoints
puts the crossing near **1,780 disagreeing cells, between trials 7 and 8** — so
the editor stopped **one trial after** the point where its criterion stopped
being right.

That is the first time this plan can say *when* a run should have stopped, and
it is sayable only because the per-commit log was kept. The previous section's
finding — that a finished run keeps no history — is what made the same question
unanswerable for the four arms before it.

### What it would take, stated as a property rather than a wish

A criterion that can drive a design to equivalence must be **a better reader
than the design on the cells it speaks about, and stay one all the way down.**
No consensus over spec-derived designs is, at any size, because it is made of
readers of the same text. The instrument that could be is one that reads the
**sentences** rather than voting over implementations — which is exactly what
the checks are, and 117 of them objecting 7 times is not enough coverage to
carry a design the rest of the way.

## THE TWO INSTRUMENTS CAME APART, AND ONLY ONE WAS OVERTAKEN

Every finding above measures the **consensus** and concludes that spec-derived
criteria are exhausted. That generalised from one instrument to a class without
checking the other member of it. The same precision test, both instruments, same
design, each restricted to where it would actually object:

| instrument | right | objections | **precision** |
|---|---|---|---|
| the consensus of seven | 375 | 1,314 | **28.5%** |
| the 117 spec checks | 5 SOUND | 7 | **71.4%** |

**One has inverted and the other has not**, and 71.4% against 28.5% is not a
margin that needs statistics.

### The mechanism predicts the split rather than excusing it

A consensus is a vote over **implementations**, so its accuracy tracks how hard a
cell is to read — the same variable that governs the design's accuracy. The two
move together and the design overtakes it, which is the population curve above.

A check reads one requirement **sentence**. Nothing ties its errors to the
population's errors and nothing ties its accuracy to cell difficulty, so it is
not overtaken by a design getting better at reading the same text.

### And the editor stopped because it disbelieved the instrument that was right

It reported the remaining objections as *"check-methodology artifacts or genuine
spec contradictions"* and stopped with 21 trials unspent. The audit:

| check | decides on the reference design | convicts it | |
|---|---|---|---|
| REQ-0015.v2@n3 | 132 | 0 | **SOUND** |
| REQ-0064.t1@n3 | 212 | 0 | **SOUND** |
| REQ-0073.shipping@narrow | 73 | 0 | **SOUND** |
| REQ-0081.control | 34 | **1** | unsound |
| REQ-0081.merge@merge | 34 | **1** | unsound |
| REQ-0087.shipping | 348 | 0 | **SOUND** |
| REQ-0088.shipping | 73 | 0 | **SOUND** |

Five of seven objections are real defects. Only REQ-0081's two bodies are
unsound, and the editor was right about those. **It threw away five true
objections along with two false ones, on one mis-diagnosis** — the REQ-0087
contradiction claim the audit refutes.

### So the plan's conclusion needs splitting, not repeating

*"A spec-derived criterion cannot carry this design further"* is **true of a
consensus over designs** and **not shown of checks over sentences.** The gap for
the checks is **coverage** — 117 of them produce 7 objections on a design wrong
at 205 of 348 testpoints — and coverage is the one thing the goal explicitly
licenses regenerating.

### What is calibrated here, stated before the arm runs

Choosing **which** instrument to keep was decided by an audit against the
reference design. That is calibration, which the goal permits, and it is
labelled. The criterion that then drives the editor reads only requirement
sentences. **No figure from a run built this way may be quoted as an
uncalibrated golden-free score.**

## SEQUENCING THE TWO INSTRUMENTS BREAKS THE BAND: 186 OF 348

The precision test says the consensus has inverted (28.5%) and the checks have
not (71.4%). Acting on that means using each instrument only where it is still
the better reader: run the dense population criterion until it is overtaken,
then switch to the sentence-derived checks.

The consensus carried the design from 279 differing testpoints to 205 and was
measured overtaken doing it. Starting the checks from exactly that point, with
the cell units out of the latch:

| arm | testpoints of 348 | cells |
|---|---|---|
| L, unedited | 279 = 80% | 4,450 |
| consensus alone | 210 = 60% | 3,890 |
| 117 checks alone, from unedited L | 206 = 59% | 3,866 |
| both stacked, unweighted | 205 = 59% | 3,608 |
| both stacked, equal weight | 205 = 59% | 3,696 |
| **consensus, then checks at the crossing** | **186 = 53%** | **3,052** |

All three miter pins green in the same process. `first_miss_err` is repaired to
never differing.

### Sequence is the whole of it, and the other arms isolate that

The same 117 checks driven from the **unedited** design reach 206. The same two
instruments **summed**, at either weighting, reach 205. Only using each where it
still has headroom reaches 186. **This is not a better criterion — it is the
same two criteria applied in the order their accuracies dictate.**

### The verdict is still DIFFERS, and the pre-registration says where it lands

The target was **two** objections, because REQ-0081's two bodies convict the
reference design and the other five spare it, so two is what a correct design
scores against this set. The run reached **five**:

| check | |
|---|---|
| REQ-0081.control, REQ-0081.merge@merge | unsound — cannot be cleared by a correct design |
| **REQ-0015.v2@n3** | **sound — a real defect, still standing** |
| **REQ-0064.t1@n3** | **sound — a real defect, still standing** |
| **REQ-0087.shipping** | **sound — a real defect, still standing** |

That is the pre-registered *partial* band.

### So the checks had not run out either — and the residue is coverage

Three of five remaining objections are real, their precision on this design is
**60%** — still above the 50% at which an instrument starts doing harm — and the
editor stopped with **8 of 21 trials unspent**.

So the binding constraint here is neither the criterion's authority nor the
budget. It is that **117 checks produce five objections on a design differing at
186 testpoints**, and the editor reported a genuine repair — an off-by-one in
the refill-completion count, traced concretely from the boundary data — that
moved the check count by **zero**.

**That is a coverage number, and coverage is the one thing the goal licenses
regenerating.** It is also the first time on this plan that the remaining gap
has been attributed to something with a known remedy rather than to a property
of specifications.

### The loop oscillates, which the goal asks about by name

The per-commit log, which no earlier arm kept:

    trial   0   1   2   4   5   6   7   8   9  11  12  13
    object  7  10  11   7  11   9   7   5   8   5  16   8

**Not a descent — an oscillation**, with the best point reached twice and left
twice, and one commit taking the count from 5 to 16. A 117-check criterion is
coarse enough that a structural edit flips several checks at once in both
directions, and a loop scored on the count alone cannot see which.

### A harness defect, mine, caught before the grade was quoted

`drive7` removes the consensus cell units from the ratchet but `note_best` still
tracks the **cell** count — so `best.v` in a checks-only run is selected by the
instrument the run deliberately does not use. The graded design is `dut.v`, what
the checks-only latch actually accepted. That is the fifteenth counting-shaped
defect here and it has the same signature as the other fourteen: a number that
reads as a result and is measuring something else.

## THE SOUNDNESS FILTER SELECTS EXACTLY THE CHECKS THAT SAY NOTHING

The residue after the sequenced run was attributed to coverage, so a coverage
round ran. **Population, spec-only:** the 21 behavioural requirements the
117-check set does not touch, ranked by the split-cells-per-check ratio of the
outputs their sentences name — `burst` at 839 against `dcram_we`'s 26. Two
independent draws each, 42 prompts.

**Standard, this plan's own measurement rather than the shipped default:**
authored STRICT, because the soundness boundary is findable from the over-strict
side (7 of 47) and not from the weak side (0 of 34), Fisher p = 0.0196.

Integrity, before any number was read: **42 of 42 answered, 0 broken, 0 bodies
shared across requirements.** Leak check over all 42 prompts: 0 lines of the
reference design's source, 0 testpoint ids, 0 equivalence verdicts, 0 divergence
evidence.

### The split, and it is total

The minority rule — keep a check convicting at most two of the seven, measured
59-of-59 precise against a 31% base rate — divided them 9 / 31. Each half was
then decided over the design the checks-only arm produced:

| | checks | **object to the design** | decide and pass |
|---|---|---|---|
| **kept by the minority rule** | 9 | **0** | 9 |
| **marked for narrowing** | 31 | **27** | 4 |

**Nine of nine silent; twenty-seven of thirty-one objecting.** The admissible
checks have nothing to say about the design; every check with something to say
is inadmissible.

### The mechanism is a coupling this session has now measured three times

A soundness filter built on a population of spec-derived designs **selects for
checks that spare spec-derived designs** — and the design under test is one. The
filter cannot tell *spares a correct design* from *spares this design*, because
on this evidence they are the same predicate.

That is the criterion-versus-design law arriving at the **selection** step
rather than the scoring step, and it explains why the filter's excellent
precision buys nothing here: **it is precise about the wrong population.**

### What the round bought, and what it did not

| | before | after |
|---|---|---|
| requirements with a check | 47 of 89 = 53% | **52 of 89 = 58%** |
| behavioural | 47 of 68 = 69% | **52 of 68 = 76%** |
| **objections on the design** | **5** | **5** |

**+5 requirements, +0 objections.** That is the volume round's result reproduced
on a targeted population with a better standard — it was +3 and +0 then. The
third time on this plan that span and signal have come apart.

**So span is not the metric, and this is the cleanest demonstration of it.** A
set can be grown to cover more of a specification by adding checks selected for
soundness and gain no ability whatever to say that a wrong design is wrong.

### A directory-purity slip, mine, caught before dispatch

The narrowing prompts were first written into `narrow/`, which already held an
earlier round's prompts and answers; moving them to `narrow2/` hit the same
problem again. Both were restored and the round now lives in a directory that
did not previously exist. This plan already records the rule — *arm purity is a
property of the directory, not the batch list* — and it is easier to break than
to remember.

## NARROWING CROSSES THE BOUNDARY WITHOUT LANDING ON IT: 0 OF 31

The gap round split 0-of-9 admissible-and-objecting against 27-of-31
objecting-and-inadmissible. Narrowing is the only route between those states,
and this plan measures it at 7 of 47 on a first attempt. So it was run: 31
over-strict checks, each given the admissible objection — *your check objects to
N of seven independently written implementations of this specification* — with
integrity clean (31 of 31 answered, 0 broken, 0 shared bodies) and a leak check
showing 0 reference-source lines, 0 testpoint ids, 0 equivalence verdicts and 0
occurrences of the word "golden".

| outcome | checks | convictions |
|---|---|---|
| narrowed to death — admissible, **silent** | 9 | **7 → 0** |
| still over-strict | 22 | 7 → 7, or 6 → 5 |
| **ADMISSIBLE AND OBJECTING** | **0** | — |

**Zero of thirty-one, against a measured 15%.**

### The conviction column is the finding, not the count

**Every check that became admissible went from seven convictions to zero.** Not
one landed at one or two. There is no gradual narrowing here — a check either
demands something all seven independent implementations violate, or it demands
nothing at all.

### Which is the strength round's result from the opposite direction

| round | direction | n | landed in between |
|---|---|---|---|
| STRENGTH — sound and blind, assert MORE | weak → strict | 34 | **0** |
| **NARROWING — over-strict, assert LESS** | strict → weak | 31 | **0** |

Both directions overshoot, and **the target between them is measured empty on 65
attempts.**

### So the coverage route closes on a transformation, not a yield

The residue after the sequenced run was attributed to coverage — 117 checks
producing five objections on a design differing at 186 of 348 testpoints — and
coverage is exactly what the goal licenses regenerating. It was regenerated: on
a targeted spec-only population, at the standard this plan's own measurements
prescribe, with both rounds' integrity clean.

| | before | after |
|---|---|---|
| requirements with a check | 47 of 89 = 53% | **52 of 89 = 58%** |
| behavioural | 69% | **76%** |
| **objections on the design** | **5** | **5** |

### What a second narrowing round is worth, priced rather than guessed

22 checks remain over-strict, and this plan measured a second attempt on the
same check at **1 of 28 = 4%**. The observed jump — 7 to 0 with nothing between
— predicts that whatever moves will overshoot as the first nine did. Expected
yield is about one check, and the shape says it will not be an admissible
objecting one.
