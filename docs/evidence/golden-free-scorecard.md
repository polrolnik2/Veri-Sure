# The golden-free scorecard for k1-dcfsm

Every number above the audit line was produced by a rule reading only artifacts
the specification produced: nine designs written independently from the spec by
agents forbidden to open any other design, and the recorded traces of those
designs. **No reference, no equivalence verdict, and no trace of one enters any
of them.** The audit column is computed last, feeds nothing, and is reported
because a span without its false-reject rate is meaningless — never because it
approves a result.

## 1. The metrics, and why these

| metric | definition | golden-free? |
|---|---|---|
| **span** | requirements with at least one check in the set, of 87 (2 removed: their state is compiled out of this build and proved unreachable by k-induction) | yes |
| **acceptance** | how many of the nine designs the set accepts | yes |
| **set blindness** | of the (pair, testpoint) cells where two designs DISAGREE on a declared output, the share where NO check in the set objects to either | yes |
| *audit* | *checks that decide on the reference and convict it* | **no — calibration only** |

**SET BLINDNESS IS THE COMPLETENESS NUMBER AND IT REPLACED A WRONG ONE.**
Blindness was first scored per check. Adding 17 checks each measured *less blind
than its parent* took the blind-check count from 121 to 136 — because a set
gains a blind check whenever it gains a check. Rejection is a union, so a metric
that worsens when you add a check is measuring the denominator. Set blindness
composes: adding a check can only close holes.

## 2. The sets

| set | selected by | checks | span | accepts of 9 | **set blindness** | *audit* |
|---|---|---|---|---|---|---|
| rule B *(earlier)* | population | 68 | 52% | — | — | *10%* |
| CEIL2 | **the reference** | 163 | 68% | **0** | **56.9%** | *0%* |
| FREE (convicts ≤2 of 7) | population | 167 | 70% | 1 (design B) | — | *13%* |
| **ZERO (convicts 0 of 7)** | **population** | **126** | **56%** | 1 (design B) | **99.8%** | ***0%*** |

CEIL2 is a **ceiling**, not a score: it is selected by asking the reference which
checks to keep. It is reported to bound what the corpus can do, exactly as the
goal permits golden to calibrate.

## 3. The golden-free soundness rule, and a retraction

The rule previously quoted here — *convicts at most 2 of the population* — was
measured 59 of 59 sparing the reference and called the best golden-free
soundness instrument. Re-run over all 594 corpus bodies instead of the 114 that
had been scored:

| golden-free rule | checks | *audit* |
|---|---|---|
| convicts **0** of 7 | **126** | ***0 = 0%*** |
| convicts 1 of 7 | 23 | *48%* |
| convicts 2 of 7 | 18 | *61%* |

**The step is at ZERO and it is sharp, not monotone.** A cut fitted at 2 on a
fifth of the corpus read as perfect and is 13% false-reject on the whole of it.

## 4. What the rule costs, which is the session's central result

    CEIL2   selected by the reference       set blindness  56.9%
    ZERO    selected golden-free            set blindness  99.8%

The golden-free set objects to **12 of 5,656** disagreements. The mechanism is
the rule itself: *convicts none of the population* is, by definition, *does not
discriminate on the population*. **Selecting for predictable soundness is
selecting for blindness — the same predicate read twice.**

## 5. What is nonetheless real

The ZERO set objects **11 times to design L**, which was held out of the seven
that selected it. Sound *and* discriminating on an unseen design, from a rule
that read no reference, is a property measured at 3–5% per check across this
project and never before obtained golden-free at set level.

## 6. Routes closed, each with the measurement that closed it

| route | result |
|---|---|
| more stimulus | **0** — every uncaught disagreement is on a testpoint the suite already runs, where two designs already differ. The evidence is present and the set is silent on it |
| re-authoring checks (39 calls, with a witness) | **0 cells newly reached.** The rewrites' objections were a strict subset of what the set already caught |
| selection over the whole corpus | **0** of 431 unused bodies close a hole while demonstrably sound. 296 close one; 288 convict the reference; 2 never decide on it |
| a golden-free completeness certificate | the pair instrument RANKS blindness at Spearman **+0.908** but its CLEAN cell is 5 of 8, and all five correct cleans are clean *by silence* |

## 7. The metric is validated against editor progress — a matched pair

Two editors, **the same unchecked starting design**, same model, same brief and
budget; the only difference is which set drove them.

| set | **blindness** | objections | testpoints differing | grade |
|---|---|---|---|---|
| CEIL2 163, reference-selected | 56.9% | 22 → 5 (−77%) | 279 → 190 (**−32%**) | `DIFFERS` |
| ZERO 126, golden-free | 99.8% | 11 → 1 (−91%) | 279 → 271 (**−3%**) | `DIFFERS` |

Both grades taken in a clean run directory with three miter pins green in the
same process. **The golden-free set spent 91% of its objections and moved the
design 3%.**

So set blindness is not a description of a set after the fact: it says in
advance how much of a design's divergence a loop driven by that set will close.
That was pre-registered before the second run was dispatched, and the run landed
on it. **This is the proxy metric the goal asks for — chosen by how well it
facilitates the editor succeeding, computable from spec-derived designs alone,
and validated against what the loop achieves rather than against how a set looks.**

*Trial counts are an output, not a confound: 10 of 21 and 19 of 21, neither
stopping for budget. A blinder set stops giving feedback sooner. Scope is two
runs — the gap is large and monotone, and two points do not establish a slope.*

## 8. The trade is a curve, not two points — and the reference is off it

Section 2's four sets were built separately and read as anecdotes. They are four
samples of ONE golden-free knob, and sweeping it end to end turns the trade into
a measurement. The knob: **keep a check that convicts at most t of the seven
independently written spec-derived designs.**

**The sweep reproduces three of the separately-built sets byte for byte** —
t = 0 is ZERO, t = 2 is FREE, t = 7 is the minimum-blindness set — which is what
says it is the same instrument rather than a new one. The five intermediate
thresholds had never been scored.

| t | checks | span of 87 | **set blindness** | population objections | spread/mean | *audit* |
|---|---|---|---|---|---|---|
| 0 | 126 | 55 = 63% | **99.8%** | 0 – 0 | — | *0 = 0.0%* |
| 1 | 149 | 63 = 72% | 93.5% | 0 – 19 | 578% | *11 = 7.4%* |
| 2 | 167 | 68 = 78% | 66.5% | 0 – 32 | 380% | *22 = 13.2%* |
| 3 | 171 | 68 = 78% | 64.2% | 0 – 34 | 335% | *23 = 13.5%* |
| 4 | 179 | 69 = 79% | 61.9% | 7 – 34 | 184% | *27 = 15.1%* |
| 5 | 188 | 70 = 80% | 52.7% | 11 – 34 | 109% | *27 = 14.4%* |
| **6** | **201** | **71 = 82%** | **40.4%** | 22 – 38 | 50% | *38 = 18.9%* |
| 7 | 464 | 73 = 84% | **0.0%** | 285 – 301 | **5.4%** | *299 = 64.4%* |

**BLINDNESS FALLS AND THE AUDIT RISES ACROSS THE WHOLE SWEEP.** Completeness
and soundness are not two properties a better rule could optimise jointly.
Golden-free, on this corpus, they are one knob read in two directions.

### The cumulative table overstates how orderly that is

The thresholds nest, so the audit **count** cannot fall as *t* grows — its
monotonicity is a property of the construction and carries no information. The
**rate** is not monotone either; it dips at t = 5. Per bucket rather than
cumulative:

| the check convicts | checks | convict the reference |
|---|---|---|
| 0 of 7 | 126 | **0 = 0.0%** |
| 1 to 6 of 7 | 75 | 38 = **50.7%** |
| 7 of 7 | 263 | **261 = 99.2%** |

**The rule is exact at both ends and a coin flip in between.** Convicting none
of the population spares the reference 126 times out of 126; convicting all of
it convicts the reference 261 times out of 263. In the middle band the rule has
no signal at all.

**And that middle band is exactly where the blindness reduction lives** — those
75 checks are everything between the sound-and-blind set and t = 6, and they
carry blindness from 99.8% to 40.4%. So the trade is not a smooth price to pay;
it is a region where the golden-free rule stops discriminating altogether, and
every point inside it is bought blind.

### And CEIL2 is not on this curve, which is what the reference is worth

CEIL2 is **56.9% blind at an audit of zero**. To reach 52.7% golden-free costs
14.4% false rejection. The arithmetic closes exactly: 161 of CEIL2's 163 checks
lie inside t = 6, t = 6 holds exactly 38 audit failures, and CEIL2's other two
are the only two checks in the corpus that convict all seven and still spare the
reference. So **CEIL2 is t = 6 with its 38 audit failures removed and those two
added, with nothing left over — and removing the 38 takes blindness from 40.4%
back to 56.9%.** Those 38 checks close 933 disagreement cells and nothing sound
replaces them.

### The second opposition, and it is independent of soundness

Set blindness asks whether SOME check objects somewhere in a disagreeing cell.
It says nothing about whether the objection COUNT orders designs — and at the
completeness floor it does not. **Eight designs that differ across a large
fraction of the suite are separated by sixteen checks of 464.** The bodies that
close the last holes convict every design, so they contribute a constant to
every score.

So a loop descending the raw count of a complete set descends a signal with a 5%
dynamic range. **Completeness and drivability are opposed too, for a different
reason than the audit.** What is measured is a limit on the RAW COUNT, which is
what every loop here has descended; a weighting or a per-requirement fold could
in principle recover a gradient it does not have.

## 9. Five graded runs, and blindness does not order them

Five Sonnet editors, **the same arbitrary unchecked design**, same brief, same
21-trial budget. Blindness and the objection counts are golden-free; the audit
and the testpoint column are computed last.

| set | blindness | *audit* | objections | testpoints differing | closed | grade |
|---|---|---|---|---|---|---|
| ZERO 126, sound | 99.8% | *0%* | 11 → 1 | 279 → 271 | −3% | `DIFFERS` |
| **CEIL2 163, sound** | 56.9% | *0%* | 22 → 5 | 279 → **190** | **−32%** | `DIFFERS` |
| T6 201, golden-free | 40.4% | *19%* | 39 → 11 | 279 → 200 | −28% | `DIFFERS` |
| MIN 464, the floor | **0.0%** | *64%* | 295 → 277 | 279 → 241 | −14% | `DIFFERS` |
| **CEIL2 + 6 authored = 169** | 55.1% | *0%* | 24 → **0** | 279 → **151** | **−46%** | `DIFFERS` |

**Ranked by what the editor achieved: the authored set, CEIL2, T6, MIN, ZERO.**
The set that sees every disagreement in the population came fourth, beaten by
one 55 points blinder.

### Split by soundness and it resolves cleanly

Among the two sets that convict no correct design, blindness predicts exactly as
the matched pair said — 99.8% closes 3%, 56.9% closes 32%. Among the two bought
with false rejection it inverts — 40.4% closes 28%, 0.0% closes 14%.
**Blindness helps while soundness is held, and stops helping the moment it is
spent.**

### The audit cost is lost work, not only a rate

On the floor set the editor found a real defect — a refill servicing three words
where the requirement states four, worth ~970 consensus cells in one change —
and the commit was refused every time, by two checks that are in the audit's
unsound list. **A set at 64% false rejection does not merely accept wrong
designs; it rejects right repairs.**

*The floor run's figure cannot be attributed to soundness alone, and that was
recorded before it ran: its objection count spans 5.4% of the population, so its
gradient is nearly flat regardless of its audit — and the run showed it live,
moving the count 6% while divergence moved 14%.*

### The fifth run is the only one authoring produced, and it is the best

Runs 1–4 are SELECTIONS over a fixed corpus. Run 5 is run 4's set plus **six
checks authored at named holes** — a (pair, testpoint, port) cell where two
spec-derived designs disagree and no check in the base objects to either.

**It is the only run to reach zero objections on a set whose audit is also zero
and broad enough to be worth reaching, and it drove the design 39 testpoints
further than any other.** It is still `DIFFERS`, and section 8's number is the
golden-free explanation: **3,119 of 5,656 disagreement cells — 55.1% — are
invisible to that set.** A design can satisfy every check and sit 151 testpoints
from the reference because the checks cannot see the other 55%. Blindness and the
residual divergence are the same fact measured twice, and only the first needs no
reference.

**The six are attributable without any run-to-run comparison.** Scored directly
against each graded accepted design:

| design | of the six, objecting |
|---|---|
| `L_afterHOLE` (run 5's own) | 0 of 6 |
| `L_afterSOUND` | 0 of 6 |
| `L_afterZERO`, `L_afterSD` | 1 of 6 |
| **`L_afterFULL` (run 4's own)** | **2 of 6** |
| `L_afterT6` | 2 of 6 |
| `L_afterMIN` | 4 of 6 |

**Two of the six convict the design run 4 stopped on** — `REQ-0029@dc_addr` at
TP-9203 edge 22 and `REQ-0087@biu_read` at TP-0033 edge 5 — defects the
163-check set that produced it could not see, named by checks that convict the
reference nowhere. That is the blindness residue closing on a fixed design, with
no editor in the loop and no run variance in the comparison.

**And blindness did not predict the improvement.** Runs 4 and 5 differ by **1.8
points of blindness** and **39 testpoints of drive**. At the margin the aggregate
is not what moved; six checks aimed at named cells were. Report the cells closed
and which ones, not the percentage alone.

## 10. The bottom line

**Completeness cannot be assured golden-free on this corpus, and section 8
makes that a measured curve rather than an inference from two sets.** Every
golden-free step toward completeness is a step into false rejection, monotonically,
across all eight thresholds — so the obstruction is a trade rather than a missing
instrument that a thirteenth route might supply. The blindness ranker is
excellent and the soundness rule is perfect at n=126; composing them yields a set
that is sound, spans 56% of the specification, and is blind to 99.8% of the
disagreements it is shown. The 288 corpus bodies that *do* close holes all convict
a correct design.

**And the reference is doing work no rule over the population reproduces.** A
set at 56.9% blindness and zero false rejection exists; it is reachable only by
asking the reference which checks to keep. That is the sharpest statement this
corpus supports of what a golden-free pipeline gives up.

**A second, independent opposition:** the set that reaches the completeness floor
cannot order the population by its own count — 5.4% dynamic range over eight
visibly different designs — so completeness costs drivability as well as
soundness.

**And the graded runs in section 9 close the loop the goal actually asks
about — with one correction the fifth run forces.** *By selection*, reducing
blindness residue makes a set a better driver only along the sound frontier, and
golden-free this corpus reaches exactly one point on that frontier — 99.8% blind,
the worst driver of the five. Every selection step toward completeness admits
checks that convict correct designs, and those cost more than the completeness
gains. **So "reduce blindness by selecting from this corpus" and "do it
golden-free" are incompatible instructions**, and that is a property of the
corpus rather than of a missing instrument.

**AUTHORING IS NOT ON THAT CURVE, AND IT IS GOLDEN-FREE.** A hole is named
without any reference — it is a cell where two spec-derived designs disagree and
nothing objects, and at most one of the two can be right. Six checks written at
named holes moved blindness 56.9% → 55.1% **at an audit of zero**, closed 102
cells, produced the best-driven design measured here, and two of them convict the
design the base set itself stopped on. Selection cannot do that at any price. So
the incompatibility above is real *for selection* and the goal's instruction is
not, on this evidence, self-defeating: **the lever is authoring at named holes,
and its measured cost in false rejection so far is nothing.**

**No run reached equivalence.** Five sets spanning the whole blindness range, one
held-out design, five `DIFFERS`. The goal's terminal condition is not met. What
changed with the fifth run is the reason it is not met: not soundness, not
termination, not the gradient, but **3,119 disagreement cells the best available
sound set still cannot see** — a golden-free number, and the named target for the
next round.

**Scope.** One design, one corpus of 594 bodies, one population of nine. Every
figure names its denominator. Nothing here is claimed for i2c, which remains
unmeasured because no i2c run retains traces.
