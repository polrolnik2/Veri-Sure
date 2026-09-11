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

## 9b. How to assure it golden-free — blindness saturates at four designs

Blindness reads a set's incompleteness with no reference, and its weakness was
never sized: measured against the designs you have, it says nothing about the
next one. Per pair the two counts are independent, so one pass over the 36 pairs
gives every subset's blindness by summation.

| designs in the population | 9 (7 written + 2 accepted) | 7 independently written |
|---|---|---|
| 2 | 50.4% | 37.3% |
| 3 | 54.2% | 40.9% |
| **4** | **55.1%** | **42.0%** |
| 5 | 55.3% | 42.4% |
| 7 | 55.3% | 42.9% |
| 9 | 55.1% | — |

**Four independently written designs estimate a set's blindness as well as
nine**, within a point, on both populations. The instrument is cheap.

**And a particular two can read zero.** The spread across subsets of the seven:
min 0.0% at n=2, 3 and 4; 6.7% at n=5; 42.9% only at n=7. **Designs B and D
disagree on 23 testpoints and the set objects on all 23 — a clean sheet, on a
set that is 42.9% blind against seven.** So the prescription is both numbers:
at least four spec-derived designs, and the per-pair spread beside the
aggregate, never the aggregate alone. Blindness zero on a small population is
the same shape of evidence as a check that passes because it never fired.

**The designs your own checks accepted belong in the population, and they are
the valuable ones.** The two columns differ by two editor-produced designs, and
adding them moves the estimate **42.9% → 55.1%, twelve points**. Whatever a set
could see was edited out of them, so what remains is exactly what it cannot —
adversarial selection for free, since the pipeline produces them anyway.

**What this does not say.** Saturation of the *estimate* is not completeness of
the *set*: 55.1% stays 55.1%, and section 9's fifth run shows a design can
satisfy every check at that blindness and sit 151 testpoints away. The
instrument is trustworthy and cheap; the number it reports is not good.

## 9c. Authoring at named holes does not escape the trade — the controlled pair

Section 9b's instrument says blindness is cheap and trustworthy to measure.
This says what it costs to move.

Two arms, 76 authoring calls, the same 3,119 blind cells, same brief, same
exemplar rule, same accept rule. They differ in one thing: which requirements
were asked, by *breadth* — how many of the ten hole ports a requirement's
normalization names.

| arm | calls | accepted | over-strict | vacuous | **cells closed** | ***audit*** |
|---|---|---|---|---|---|---|
| BROAD — 11 reqs, breadth 4–10 | 40 | 2 | 32 | 6 | **1,293** | ***2 of 2*** |
| SPECIFIC — 27 reqs, breadth 1–3 | 36 | 2 | 33 | 1 | **0** | ***0 of 2*** |

**One end buys 1,293 cells at a 100% false-reject rate; the other buys nothing
at zero.** Both are negatives against rules fixed before either ran. Together:
**76 calls on the corrected targeting closed zero cells soundly**, against round
1's 102 from 37 calls on the regex population.

### The mechanism, over all 76 rather than as two anecdotes

Of the 69 checks that object anywhere:

| | n | mean cells closed |
|---|---|---|
| kept by the minority rule (≤3 of 7) | 4 | **74** |
| rejected (>3 of 7) | 65 | **638** |

Spearman(cells objected, designs convicted) = **+0.350** over 76 checks. **The
checks that would close the residue are exactly the ones the golden-free
soundness rule rejects** — measured inside the one lever that was supposed to
sit off that curve. The three biggest closers each shut over a thousand cells
and each convicts all seven designs.

### This re-reads §9's positive rather than retracting it

Round 1's six accepted closed 102 cells — **17 each**, inside the kept band's
own mean of 74. That round was never off the anti-correlation; it was the same
narrow band with six members instead of two. What stands is its narrow claim: a
sound hole-closer is **writable** where the corpus contains none, at audit zero.
What is refuted is the reading placed next to it — that the residue is
addressable at zero audit cost *at a usable rate*.

**Projected from the measured rates:** 3,119 cells at 17–74 cells per accepted
check needs 40–180 accepted checks; at an accept rate that fell from 16% to 5%
between rounds, that is **250 to 3,600 authoring calls**.

## 9d. The residue is closeable, and none of it soundly — the decisive number

§9c left one thing open: whether the 65 checks the minority rule rejects are
genuinely over-strict or whether the rule is discarding real completeness at
exactly the place the residue lives. Audited as a calibration: **0 of 65 spare
the reference.** The rule's reject side is 65 of 65 precise, at the residue. It
is discarding nothing, and the hedge placed on §9c is withdrawn.

So the constraint is neither the rule, nor the corpus, nor the targeting. Take
the 3,119 blind cells and classify each by what kind of authored check closes
it — a classification that reads only the population's disagreements:

| of the 3,119 blind cells | cells | share |
|---|---|---|
| closed by a check the minority rule **keeps** | 1,293 | 41.5% |
| closed **only** by a check it rejects | 1,826 | 58.5% |
| **closed by nothing among the 76 authored** | **0** | **0.0%** |

**Every blind cell is closeable.** 76 checks authored at the residue cover 100%
of it. The author is not failing to reach the cells.

**The calibration, computed last, says what the cover costs:**

| | |
|---|---|
| of the 76 authored checks, sparing the reference | 9 |
| **of those 9, blind cells closed** | **0** |
| of the 65 rejected checks, sparing the reference | 0 |
| **soundly closeable residue** | **0 of 3,119 = 0.00%** |

*Corrected, and the error was mine.* The first version read **21 of 3,119 =
0.7%**, taken from "cells the sound checks object on" — every cell, blind or
not. All 21 are cells the 169-check set already covers, and the tell sat in the
same table: adding those two checks moved blindness from 3,119 to 3,119.

*And a second leg was never implemented.* Every write-up here says an accepted
check "decides at the named cell, objects to one of the two designs there, and
convicts at most 3 of 7". The scorer accepts on *decides anywhere* plus the
minority rule. Measured afterwards: of the four accepted, the two that do close
their own cell are the two that convict the reference, and the two that spare it
close some other cell instead. **Zero of 76 checks both closed the cell it was
given and spared the reference.**

**An author asked to close a named blind cell succeeds every time, and every
time the check it writes convicts a correct design.** That is the
completeness/soundness trade as a property of the *cells*, and it is why every
lever on this plan lands in the same place.

### What it gives a golden-free pipeline

The partition needs no reference — it asks *does every check I can author for
this cell convict a majority of the population*. The calibration says that
question tracks soundness at 65 of 65 on the reject side. **A pipeline with no
golden can therefore determine that a cell is irreducibly blind:** author at it,
read the conviction counts, and if they are all majorities the cell is not
soundly closeable. What it cannot do is close it anyway.

### And blindness should be reported as a pair

Reporting 55.1% invites the reading that 55.1% is work outstanding. On this
evidence **none of it is** — 55.1% of the disagreements two competent readers
produce are cells where no adjudicating check spares a correct design. A set
should report *residue, and the share of it any check could soundly close* — the
second is what further authoring buys, and here it is zero.

**Limits, and the first is load-bearing now the number is zero.** 76 checks are
a cover, not an exhaustive search; a 77th could be the sound closer for a cell
these close only unsoundly, so 0.00% is a floor and the gap to the truth is
unmeasured — which is what the narrowing round pre-registered in
`PREREG_NARROW.md` measures. And "closed" means the check objects to one of the
two designs there — not that it is right about which.

## 9e. Narrowing moved the conviction count by nothing — the route is closed

§9d's zero came with its own limit: 76 checks are a cover, not a search. So the
30 largest hole-closers were re-authored with the narrowing objection — the one
lever aimed at this population, measured at 7 of 47 = 15% on its first round
elsewhere. Pre-registered in `PREREG_NARROW.md`: ≥4 of 30 means the zero is an
artifact of one attempt per cell; ≤1 means it is close to the truth.

| | |
|---|---|
| integrity | 30/30 returned, 30 compile, 0 duplicates, **0 unchanged** |
| still closes its own named cell | 29 of 30 |
| passes the minority rule (≤3 of 7) | 1 of 30 |
| **both — the pre-registered measure** | **0 of 30** |
| ***audit*, computed last** | ***29 of 30 convict the reference*** |

**The conviction count did not move.** 28 of 30 went 7-of-7 → **7-of-7**; one
went 6-of-7 → 7-of-7, *stricter*; the single check that passed the minority rule
went 7-of-7 → 0-of-7 on zero cells — it narrowed into vacuity, this round's known
failure mode, counted as a loss.

Each author named the demand it deleted: a cycle-alignment rule the sentence
never stated, a holding time, a converse clause, word-count arithmetic, an
over-wide scope. **The deletions were real and the checks still convict
everyone.** Over-strictness here is not an accretion of removable extras — what
survives narrowing is the *core* reading of the sentence, and the population
violates that.

### The rule and the audit agree on 95 of 95

With §9d's 65, every check the golden-free minority rule rejects at this residue
convicts the reference — **95 for 95**. The rule is not discarding completeness;
there is none to discard.

### Which leaves one reading, and it is the specification's

At these cells the sentence — asserted as its own author reads it *after being
told to assert less* — is violated by all seven independent implementations and
by the reference. That is not check over-strictness as measured elsewhere here.
It is the requirement text and the design disagreeing, at exactly the cells where
two competent readers of that text disagree with each other.

**Three levers have now been aimed at the blindness residue — selection,
authoring, narrowing — and all three are closed with a measurement rather than a
budget running out.** What would change it is not a check or a prompt: it is a
decision on the underdetermined cells from outside the specification-plus-reader
loop. The disagreement map localises them exactly, 3,119 cells named by pair and
testpoint, and it needs no reference to produce.

## 9f. Blindness is a property of the stimulus too — and it predicts the grade

Blindness is holes ÷ disagreements over *(pair, **testpoint**)* cells. Three
levers moved the numerator by authoring checks and all three are closed. The
denominator is the **stimulus**, and it had never been looked at.

| the same 169-check set, per testpoint | tps | disagreements | blind |
|---|---|---|---|
| no pair disagrees at all | 91 | 0 | — |
| **every disagreement caught** | 61 | 1,217 | **0.0%** |
| partly blind | 126 | 3,235 | 59.2% |
| **every disagreement blind** | 70 | 1,204 | **100.0%** |

**One set is perfectly complete on 61 testpoints and perfectly blind on 70.**
Blindness is a property of the *(check set, stimulus)* pair, and every figure
above attributes it to the set alone.

### The classification predicts the grade

§9's fifth run drove objections to 0 of 169 and its design still differs from the
reference on 151 of 348 testpoints. Scored against each testpoint's golden-free
class — the class reads only the population's disagreements and the checks'
verdicts; the divergence is computed last and is what is being predicted:

| class of the testpoint | tps | differ | rate |
|---|---|---|---|
| no pair disagrees | 91 | 1 | **1%** |
| every disagreement caught | 61 | 15 | 25% |
| partly blind | 126 | 75 | 60% |
| every disagreement blind | 70 | 60 | **86%** |

**Monotone across all four classes, 1% to 86%, 3.5× between the extremes.** The
chain is complete and every link measured: a blind testpoint gives the editor no
objection, so it makes no edit there, so the design still differs there. **135 of
the 151 differing testpoints — 89% — are partly or fully blind.**

The top row is an independent reproduction: where nine spec-derived designs agree,
the edited design matches the reference on 90 of 91 testpoints — §5's 99.82%
per-cell consensus accuracy arriving again per testpoint.

### What it licenses, and what it must not

It does **not** license adding easy testpoints to move the ratio: blindness would
fall while the 3,119 blind cells stayed exactly where they are. That is metric
gaming, and the absolute count catches it.

What it licenses is the question the goal names and this plan never asked —
**whether a different testpoint exercising the same scenario produces its
disagreements at cells the specification determines.** The target is exact: 70
testpoints, 1,204 cells, 100% blind, carrying 86% of the residual divergence.

This reframes the three closed levers rather than reopening them. No sound check
closes those cells — 95 of 95 attempts convict the reference, and that stands.
What it says is that the cells were never the only variable: they are the
disagreements *this* stimulus happens to produce.

### Why a testpoint is blind — the sizing that decides the stimulus loop

Both classes are already on disk, so the discriminator costs nothing. If they
disagree on *different ports*, blindness is about which outputs the specification
underdetermines and no stimulus helps. If the *same ports* appear in both, it is
about the scenario those ports are put in, and stimulus is a lever.

| port | caught | blind | ratio |
|---|---|---|---|
| `biu_write` | 8.0% | 40.5% | **5.06×** |
| `first_miss_ack` | 15.1% | 18.3% | 1.21× |
| `biu_read` | 18.2% | 14.7% | 0.81× |
| `dc_addr` | 10.8% | 12.3% | 1.13× |
| `first_hit_ack` | 5.7% | 3.6% | 0.64× |
| `tag_we` | 7.3% | 3.6% | 0.48× |
| `saved_addr` | 6.5% | 3.3% | 0.50× |
| `dcram_we` | 10.1% | 2.2% | 0.22× |
| `burst` | 14.7% | 1.6% | **0.11×** |
| `first_miss_err` | 3.7% | 0.0% | **0.00×** |

Total-variation distance between the profiles: **0.372**.

**It is both, and the scenario half is larger.** 63% of the mass overlaps and **8
of 10 ports carry >2% in both classes** — the same output is adjudicated on one
testpoint and invisible on another. There is also a port component with a name:
`biu_write` at a 5× concentration in the blind class, `burst` and
`first_miss_err` essentially never blind. The store write-through path is where
blindness collects.

**This is the first positive sizing for the stimulus loop here.** The earlier one
— *worth 3 checks of 50* — asked whether checks are silent rather than blind on
one design; that answer stands and does not bear on this.

**What it does not establish.** That a port is caught somewhere and blind
elsewhere does not mean a stimulus author can reach the caught kind on demand.
The settling experiment is a stimulus round aimed at the 70 fully-blind
testpoints' scenarios, scored on whether the new testpoints are also fully blind.
That is not run. And `biu_write`'s concentration is a co-occurrence, not a cause.

### CORRECTED out of sample — the monotone ordering does not survive

The four-class table above was read off ONE design. The sixth graded run (§9i)
is a held-out test, and it reads **1% → 48% → 44% → 87%**: the middle two
classes invert. **The four-point predictor is withdrawn; the two endpoints
hold.** See §9j.

## 9g. The stimulus loop, run — a different route is blinder, not clearer

§9f licensed the question; this answers it. The 20 fully-blind testpoints
carrying the most blind cells (460 of 1,204, disagreeing on `biu_write` 445,
`first_miss_ack` 418, `biu_read` 160, `tag_we` 80) were handed to four authors,
who were given only the driven inputs of a testpoint that already runs and which
outputs two spec-derived designs disagree on there, and asked for a new testpoint
reaching the same scenario **by a different route**. All nine designs then ran on
the result. Pre-registered in `PREREG_STIM.md`: ≥40% fully caught means the
scenario is the lever; <15% closes it.

| the 20 new testpoints | tps | disagreements | blind |
|---|---|---|---|
| inert — no pair disagrees | **0** | 0 | 0 |
| **fully caught** | **1** | 8 | 0 |
| partly blind | 4 | 111 | 59 |
| **fully blind** | **15** | 267 | 267 |

| | |
|---|---|
| **fully caught, of the 20 that disagree** | **1 = 5%** (bar was 40%) |
| cell blindness on the new testpoints | **326 of 386 = 84.5%** |
| the suite they were drawn from | 55.1% |

**Inert is 0 of 20** — the pre-registered failure mode did not occur. The routes
were genuinely different (zero-latency versus 12-cycle stalled bus; back-to-back
versus ragged refill pacing; request withdrawn mid-refill; preceded by load hits,
cache-inhibited accesses, full refills, error-then-retry; three misses back to
back) and every one reached its scenario.

**5% against a 40% bar — and the new testpoints are blinder than the average old
one.** That second figure is the stronger half: four independent authors, five
materially different routes each into the same scenario class, produced
disagreements the set sees *less* of than the suite average. **The blindness
travels with the scenario, not with the route.**

**Four levers have now been aimed at the residue — selection over the corpus,
authoring at named holes, narrowing the over-strict closers, and the stimulus —
and all four are closed by measurement rather than by a budget running out.**

**Scope.** The sample was deliberately the worst scenarios and inherits their
difficulty; a round aimed at a random testpoint might do better and this does not
measure it. What is settled is the case that carries the residue.

**And the ratio was not the headline, as pre-registered.** These 20 lower
nothing: the old 3,119 blind cells are where they were and these add 326 more.

## 9h. Can the population's VOTE adjudicate a blind cell? No — it is inverted on the dominant blind port

Four levers aimed at the blindness residue are closed (§9d, §9e, §9g). But a
blind cell is not evidence-free: the population *disagrees* there, and at most
one side of a disagreement can be right. So the last untried thing is to hand an
editor the disagreement itself. Before doing that, the obvious adjudicator —
**the vote** — was measured on the artifact built to carry it: 60 cells, each
the earliest cell of a fully-blind testpoint where nine independently written
spec-derived designs disagree on a declared output.

| on the 60 cells | |
|---|---|
| the larger side matches the reference | **20 = 33%** |
| the reference is on a MINORITY side | **40 = 67%** |
| *corpus-wide over all split cells* | *53%* |

**The vote does not merely say nothing there — it points the wrong way.**

### And the tidy explanation is confounded, which was checked before it was written down

The selection takes the FIRST split of each testpoint, and first splits separate
sharply by blindness — 33% against 95%. **That 62-point separation is PORT
COMPOSITION and is not quotable as a blindness effect.** Blind first splits are
47 of 70 `biu_read`; the rest are 130 of 187 `burst`, whose majority is right
130 of 130. Broken out, the effect REVERSES:

| first split, by port | fully blind | other testpoints |
|---|---|---|
| `biu_read` | **3 of 47 = 6%** | 34 of 38 = 89% |
| `biu_write` | **20 of 20 = 100%** | 8 of 13 = 62% |
| `dcram_we` | 0 of 3 | 4 of 5 = 80% |
| `burst` | — | 130 of 130 = 100% |

Margin does not rescue it: at a majority of 8 of 9, blind cells read 34% and the
others 97%.

**So the claim is the narrow one: the population's vote swings from 6% to 100%
between two ports at the same margin, and no golden-free feature measured here
tells them apart.** Blindness is not that feature — it is confounded with the
port. A pipeline that adjudicates a blind cell by majority is, on the port
carrying two thirds of this residue, wrong two times in three.

**Integrity — not a decode defect on one port**, which is the shape eight
counting-shaped defects on this plan have had. Where all nine designs agree, the
reference agrees on `biu_read` **97.63%** of 40,867 unanimous cells, alongside
`tag_we` at 97.62% and `saved_addr` at 98.27%, against 99.10% overall. The port
is read correctly; the 6% is the population being wrong.

**What it does not say.** The disagreement is still evidence — at most one side
can be right, whatever the counts do. What is closed is resolving it *by vote*.

**PARTLY REOPENED BY §9k.** That closure is right about the PLAIN majority and
about these 60 first-split cells. De-duplicating the population first — a
golden-free operation with no fitted parameter — takes the vote from 56% to
**73%** on blind cells generally. See §9k.

## 9i. The sixth graded run — the disagreement report did not move the cells it named

§9h closed the population's *vote* as an adjudicator. The disagreement itself
remained: at most one side of a split is right, and no run had ever handed that
to an editor. This is that arm, and it is the fifth lever aimed at the residue.

**Identical to run 5 in every respect** — same start design `gen/L.v`, same
Sonnet editor and policy, same 21-trial budget, same 169-check set at audit
zero, same baseline of 24 objections — **plus one artifact**: 60 cells on 60
distinct fully-blind testpoints, each giving the port, edge, driven inputs, FSM
states, and how nine spec-derived designs split. Verified cell by cell against
the traces, 0 mismatches, no design named.

| trial | objections | consensus cells | ratchet |
|---|---|---|---|
| init | 24 | 9,857 | — |
| 1 | **27** | 3,074 | **rejected** |
| 2 | 14 | 1,982 | latched |
| 3 | 6 | 1,999 | latched |
| 4 | **1** | 2,840 | latched |
| 5 | 3 | 3,307 | **rejected** |

| | control (run 5) | this arm |
|---|---|---|
| objections at rest | 0 of 169 | **1 of 169** |
| trials spent | 21 of 21 | **5 of 21** |
| **testpoints differing** | **151 of 348** | **146 of 348** |
| pins, same process | green | **EQUIVALENT / NO-DIFF-40 / DIFFERS** |
| grade | `DIFFERS` | **`DIFFERS`** |

**146 is the pre-registered `121-160` band: no effect distinguishable from
run-to-run variance.**

### And the attribution says the five testpoints are not the report's

Both groups sit in the same run under the same editor, so variance subtracts out:

| group | control | this arm | change |
|---|---|---|---|
| **NAMED by the report** | 53 of 60 = 88% | **54 of 60 = 90%** | **+1 — worse** |
| UNNAMED, fully blind | 7 of 10 = 70% | 7 of 10 = 70% | 0 |
| **not fully blind** | 91 of 278 = 33% | **85 of 278 = 31%** | **−6** |

**The aggregate gain is entirely outside the report.** The run improved by five
testpoints; the group the report says nothing about improved by six, and the
sixty cells it names got one worse. The n = 10 matched control is not quoted —
registered in advance as too small — because the NAMED group carries the reading
at n = 60.

### The editor's reading is confirmed and its conclusion refuted

It reported working all sixty cells and finding **59 of 60 already matched its
design's behaviour under the governing requirement text**. At **54 of those 60
testpoints the design still differs from the reference**. It read the
specification at each cell, concluded its design was right, and was wrong 90% of
the time — with the disagreement in front of it, the design in front of it, and
16 trials unspent.

**That is the targeted-question result arriving on an editor.** A reader asked
one question about an underdetermined cell reproduced the population's wrong
answer 7 times in 9 with no design in view; an editor with the design, the split
and the budget reproduces it too. The shared misreading is not a shortage of
context.

**Five levers are now closed by measurement** — selection, authoring at named
holes, narrowing, the stimulus, and disagreement evidence. What is *not* closed
is that the disagreement is evidence: at 54 of 60 named cells the design is on
the wrong side of a split. What is refuted is that handing that split to a
spec-reading editor resolves it.

## 9j. The golden-free predictor, tested out of sample — a two-point instrument

§9f reported a monotone four-class predictor fitted on run 5. Run 6's design is
an independent editor session's product, never seen when the classes were
computed. The classes are golden-free; divergence is predicted, computed last.

| golden-free class of the testpoint | tps | run 5 (fitted) | run 6 (held out) |
|---|---|---|---|
| inert — no pair disagrees | 91 | 1 = **1%** | 1 = **1%** |
| every disagreement CAUGHT | 61 | 15 = 25% | **29 = 48%** |
| partly blind | 126 | 75 = 60% | **55 = 44%** |
| every disagreement BLIND | 70 | 60 = **86%** | 61 = **87%** |
| total | 348 | 151 = 43% | 146 = 42% |

**The monotone ordering does not hold.** The middle two classes invert and the
blind-against-caught ratio falls 3.5x → 1.8x. The four-point predictor is
withdrawn.

**What survives, and survives well, is the pair of endpoints.** A testpoint no
two spec-derived designs disagree on carries a design that is right there — 1%
in both runs. A testpoint whose every disagreement is unadjudicated carries a
design that is wrong there — 86% and 87%, 60 of 70 and 61 of 70, across two
independent editor sessions. **That is the golden-free warning a practitioner
can be given: not a ranking, two points.**

### And `CAUGHT` does not mean the set catches this design's errors

A vocabulary defect of mine, visible here for the first time. On the 61
fully-caught testpoints run 6's design differs from the reference on **29**,
while the set raises **one objection in the entire suite** — and that objection
sits on a caught testpoint. `CAUGHT` says the set can adjudicate the
*population's* disagreements there. It says nothing about whether it catches the
errors of the design under test, and every use of the word on this page should
be read that way.

## 9k. The population is five opinions, not nine — and de-duplication recovers the vote

§9h closed the population's vote as an adjudicator. That is right about the
*plain* majority, and it left the mechanism unexamined. The mechanism turns out
to be a fixable defect in the rule rather than a property of the evidence.

**At every one of the 812 blind split cells, designs B, D, E, F and H produce
identical values.** Grouped by behavioural signature — golden-free, just a
comparison of traces — the nine designs are **five distinct opinions**: a bloc
of five, plus C, G, FULL and SD alone.

**So a majority over nine is structurally the bloc's answer, always.** The bloc
holds 5 of 9 votes, so the vote is capped at the bloc's own accuracy however
many designs are added — which is the saturation §9b measured from the outside
and never explained. A tenth design from the same distribution makes it worse.

| rule | the 60 NAMED cells | all blind split cells |
|---|---|---|
| MAJORITY — all 9 | 20/60 = 33% | 456/812 = 56% |
| **DEDUP — one vote per bloc** | 23/60 = 38% | **595/812 = 73%** |
| LEAST-5 — calibrated k | 23/60 = 38% | 637/812 = 78% |
| *ORACLE-BEST (C) — ceiling* | 23/60 = 38% | 637/812 = 78% |

**DEDUP is golden-free and has no fitted parameter**: group by behavioural
signature, one vote per group. It moves the vote **56% → 73%**, recovering most
of the distance to the best single design. 4% of its decisions are ties broken
by order, reported as such. **LEAST-5** — vote among the five designs the check
set convicts least — hits the ceiling exactly (637 of 812, the same cells as C)
with zero ties, but its k was read off the audit, so it is a **calibration**
exactly as rule C's threshold at two is.

### And on the cells that carry the residue, nothing helps

Every rule ties at **38%** on the 60 named cells, **including the ceiling**.
Those are the *first* split of each blind testpoint, and there even the best
design in the population is wrong 62% of the time. So §9h stands where it was
measured — and this supplies the reason §9i's arm could not have worked: the
report was drawn from the one sample on which no rule over this population beats
any other.

### CORRECTED — whether de-duplication helps depends entirely on the denominator

On **raw edges** the same blocs on the same blind cells read plain majority
**82%** and de-duplicated **54%** — the reverse of the 56%/73% above, and by
more. Neither denominator is privileged: transactional rows weight transitions,
raw edges weight sustained stretches, and the population is right on stretches
and wrong at transitions. Per design on raw-edge blind cells: C 89%, the bloc
**82%**, SD 54%, FULL 53%, **G 20%** — one vote per bloc gives G's 20% the same
weight as the bloc's 82%. **The structural claim stands; the claim that
correcting for it improves the reading is withdrawn.** See §9n.

### It also prices the phrase "independently written"

Nine agents, each forbidden to read another's work, produced **five** opinions
where the checks are blind. Every majority figure on this page is a bloc of five
wearing the authority of nine, and every population-widening result should be
read against that.

## 9l. The seventh graded run — unscored evidence does not move an editor

§9k explained why §9i's arm could not have worked: it named the first split of
each blind testpoint (where every rule ties at 38%, ceiling included) and
reported raw nine-design counts over a population holding five readings. This
arm rebuilt the artifact to remove both defects — 97 cells on 54 fully-blind
testpoints, chosen because the *start design* disagrees with the reading held by
the most distinct implementations, readings merged by value, the bloc named as a
bloc. Selection golden-free throughout; 97 of 97 re-derived from traces, 0
mismatches. Bands fixed in `PREREG_DIS2.md` before dispatch.

| | run 5 | run 6 | **run 7** |
|---|---|---|---|
| objections at rest | 0/169 | 1/169 | **5/169** |
| trials spent | 21 | 5 | **12 of 21** |
| **testpoints differing** | 151 | 146 | **214 of 348 (61%)** |
| grade | `DIFFERS` | `DIFFERS` | **`DIFFERS`** |

**214 is the pre-registered `> 160` band: the run drove the design away.** Pins
all green in the same process.

| group | n | run 6 | run 7 | change |
|---|---|---|---|---|
| **NAMED by the report** | 54 | 48 = 89% | **53 = 98%** | **+5 worse** |
| unnamed, fully blind | 16 | 13 = 81% | 13 = 81% | 0 |
| **not fully blind** | 278 | 85 = 31% | **148 = 53%** | **+63 worse** |

### The editor did not use the report

Re-read on the accepted design, the 97 named cells show it **adopted the leading
reading at 1** and **kept its own value at 96**. So the +63 is not the advice
going wrong — it is the editor's check-driven structural edits, with the report
inert. The worst output is `first_hit_ack` at 963 differing cells, a port the
report never names.

### The calibration was right and my inference from it was wrong

Before the run I measured that changing exactly those cells to the leading
reading fixes 91 of 97, and called it the strongest lever on this plan. **That
was an over-claim.** 91-of-97 is a true statement about *cells*, and **an editor
cannot change a cell** — it changes RTL, and every structural edit moves
thousands of cells at once. A per-cell counterfactual does not transfer to an
agent whose only instrument is a structural edit.

### What the two runs show together

Run 6's editor judged 59 of 60 cells already fine; run 7's adopted 1 of 97 — the
report built to fix run 6's defects was used **less**, not more. The common cause
is in the brief both carried: *the checks remain the latch and
`checks_objecting` is the number you drive down; the disagreements are not scored
and nothing counts them.* **An editor optimises what is scored.** Unscored
evidence, however accurate and however well aimed, does not move it.

**So the next thing to try is not a better report** — it is putting the
de-duplicated disagreement *in the latch*, which is golden-free and has never
been run. Nothing here claims that would work; it is named as the untested
option, and what is closed is handing an editor unscored evidence.

## 9m. The eighth graded run — a criterion cannot take a design past its own accuracy

§9l named putting the disagreement *in the latch* as the untested option and
refused to claim it would work. It was run. `drive10.py` added **160 units**
beside the 169 checks — one per (blind testpoint, declared output) pair carrying
a split cell, passing when the design matches the population's de-duplicated
reading there. Golden-free throughout; bands fixed in `PREREG_LATCH.md`.

| | run 5 | run 6 | run 7 | **run 8** |
|---|---|---|---|---|
| checks objecting | 0 | 1 | 5 | 13 of 169 |
| **dedup units failing** | — | — | — | **0 of 160** |
| **testpoints differing** | 151 | 146 | 214 | **221 of 348** |
| grade | `DIFFERS` | `DIFFERS` | `DIFFERS` | **`DIFFERS`** |

**The golden-free criterion was driven to a perfect score and the design is the
worst of the eight runs.**

| group | n | run 6 | run 7 | run 8 |
|---|---|---|---|---|
| **fully blind — the units cover this** | 70 | 61 = 87% | 66 = 94% | **66 = 94%** |
| not fully blind | 278 | 85 = 31% | 148 = 53% | **155 = 56%** |

Pre-registered question 2 — regression net, bar ≤ 85 on `not fully blind` — read
**155. Not met**, and worse than the run with no such latch.

### The mechanism, exact

On the 3,827 blind split cells the units score:

| | right |
|---|---|
| the de-duplicated **reading** | **2,070 = 54%** |
| the **start** design L | **2,209 = 58%** |
| the **accepted** design | **2,070 = 54%** |

**The accepted design's accuracy equals the reading's to the cell** — it matches
the reading everywhere it is scored and inherits its error rate by construction.
On the 1,757 cells where the reading is *wrong*, the start design was right at
174 and the accepted design at **0**.

**A criterion cannot take a design past its own accuracy, and this design
started above it** — 58% → 54%, by satisfying it perfectly. That is §9's
zero-objections finding on a *golden-free* criterion, and sharper: there a wrong
design satisfied an over-strict set; here a perfect score is arithmetically a
cap.

### A defect in my own reasoning, and it is the cause

The arm was motivated by the reading measured at **73%** over blind cells and
93% over a targeted subset. **Those were on transactional rows; the latch was
built on raw edges, where the same reading is 54%.** Rows collapse runs of
identical values, so the denominators weight cells differently — they are not
the same instrument. The coordinate change was right (raw edges survive an edit;
row indices do not), but I did not re-measure accuracy in the new coordinates
before building a latch on it. **A 54% reading cannot drive a 58% design
anywhere good, and that was knowable before the run from data already on disk.**

### What this closes

Scoring the population's reading is the **seventh** lever aimed at the blindness
residue and the last one this population offers: selection, authoring at named
holes, narrowing, the stimulus, unscored disagreement evidence, and now scored
disagreement evidence. **The population's reading is 54% accurate where the
checks are blind, so no criterion built from it can certify a design better than
that** — the ceiling of the whole route, stated as a number rather than as
another failed round.

## 9n. The de-duplication reversal, and what it says about run 8

§9k reported that de-duplicating the population takes the vote from 56% to 73%
at blind cells and called it a golden-free fix with no fitted parameter. On the
other available weighting of the same cells it goes the other way, and by more.

| at blind cells | plain majority | de-duplicated |
|---|---|---|
| **raw edges** (3,827 cells) | **82%** | **54%** |
| transactional rows (812 cells) | 56% | 73% |

**Neither figure is quotable without its denominator, and §9k quoted one as the
answer.** Transactional rows collapse runs of identical values and so weight
transitions; raw edges weight sustained stretches. The population is right on
stretches and wrong at transitions — that is the entire reversal.

Per design on raw-edge blind cells: **C 89%, the bloc B/D/E/F/H 82%, SD 54%,
FULL 53%, G 20%.** One vote per bloc gives G's 20% reading the same weight as
the bloc's 82%. **The bloc of five is the most accurate group in the population,
and its multiplicity is what made the plain majority good.** The a priori
argument for de-duplicating — five copies are one opinion — is not obviously
right against the alternative that five independent agents agreeing is evidence,
and I took the first without measuring.

**This explains run 8 completely.** It put the de-duplicated reading in the latch,
drove it to a perfect score, and produced the worst design of the eight — the
design's accuracy ending at the reading's 54%, from a start of 58%. The plain
majority was available in the same coordinates at **82%**. §9m's law (a criterion
cannot take a design past its own accuracy) is confirmed and was applied to the
wrong reading.

## 9o. The ninth graded run — a proxy's aggregate accuracy is not its effective accuracy

§9n showed run 8 scored the *worse* of two available readings. Run 9 is identical
but scores the **plain majority**: 82% accurate on the same cells in the same
coordinates, 24 points of headroom over the start design's 58%, where run 8's was
minus four. Bands and a mechanism check fixed in `PREREG_MAJ.md`.

| | run 5 | run 6 | run 7 | run 8 | **run 9** |
|---|---|---|---|---|---|
| checks objecting | 0 | 1 | 5 | 13 | 18 of 169 |
| units failing | — | — | — | 0 of 160 | 42 of 160 (from 91) |
| **testpoints differing** | 151 | 146 | 214 | 221 | **271 of 348** |

**The worst of the nine.** The pre-registered `> 160` band reads: scoring the
population's reading drives the design away whichever reading is used, and the
route is closed on both.

### The mechanism check failed in the informative direction

It predicted blind-cell accuracy would rise toward 82%. **It fell, 58% → 53%**,
while the criterion improved by 49 units.

| unit transition | units | cells | the **reading** is right | design before → after |
|---|---|---|---|---|
| pass → pass | 72 | 2,171 | 87% | 87% → 87% |
| **FAIL → pass** | **43** | 387 | **17%** | 66% → **17%** |
| **FAIL → FAIL** | **42** | 1,269 | **94%** | 6% → 6% |

**The editor repaired exactly the units where the reading is worst (17%) and left
the ones where it is best (94%).**

### The law

**A proxy's aggregate accuracy is not its effective accuracy.** What governs is
its accuracy on the subset an optimiser can *move*, and for a population-derived
proxy those anti-correlate: a unit the population gets systematically wrong is
wrong for a **structural** reason — a whole port's convention most designs share
— so one edit flips it; a unit it gets right demands the design be genuinely
correct there, which no single edit buys. **The criterion is easiest to satisfy
exactly where it is most wrong.**

This explains all three preceding runs at once — the unscored report (adopted at
1 of 97), the de-duplicated latch (perfect score, worst design), and this one.
None failed for want of a more accurate reading.

### And it names my own error, which was the same one three times

Run 7 priced on a per-cell counterfactual an editor cannot perform; run 8 on a
figure from a different denominator; run 9 on the reading's aggregate accuracy.
**All three are statements about cells that ignore what an optimiser does with
them.** The per-unit table is the measurement that would have predicted every
one, and computing its *split* needs no reference — only scoring it does.

## 9p. Finishing the stimulus loop — measured at zero opportunity, on three designs

The goal names the stimulus loop as likely necessary. §9g sized it as a
*blindness* lever at 1 of 20 and closed it there. §9o makes a different question
the right one: the 169 checks are audit **zero**, so where they speak they are
right, and the only thing that could be wrong with them is **reach** — which is
exactly what stimulus buys.

Two ways a set can fail to speak where a design is wrong, demanding opposite
work: **silence** (no check *decides* there — a stimulus gap) and **blindness**
(a check decides on a port that *is* wrong there and passes — no stimulus fixes
that). Restricted to testpoints where a port the check itself reads differs.

| design | differing | objects | **silent** | blind | strength |
|---|---|---|---|---|---|
| the start design L | 279 | 169 | **0** | 110 | 6.4% |
| run 5 accepted | 151 | 0 | **0** | 151 | **0.0%** |
| run 6 accepted | 146 | 20 | **0** | 126 | **0.4%** |

**The stimulus opportunity is zero on all three** — not small, zero. And the
fourth class, *no check watches a wrong port at all*, is **also zero**. The suite
already drives every one of these designs into its wrong behaviour, on the exact
ports the checks read, and the checks decide there and pass.

**So finishing the stimulus loop cannot move this set**, and that is a
measurement on three graded designs rather than an estimate on a different set.
It is a stronger form of §9's `3 of 50`: for the 169-check set it is 0 of 146, 0
of 151, 0 of 279.

### The strength column is a mechanism nobody has named

Objections per exposed decision fall **6.4% → 0.4% → 0.0%** as the loop works.
**The editor consumes the set's discriminating power.** It does not fail to
satisfy the checks — it satisfies exactly the few percent they can see, and what
remains is what they were always going to decide on and pass. That is why every
run ends quiet and wrong.

**The residue is check strength and only check strength** — 0.4% of 4,529 exposed
decisions. And strength is the one thing measured to cost soundness one for one:
the strength round raised it 24x, **23 of 34 checks began convicting the
reference**, and the both-cell was **0 of 34**, the minimum the marginals allow.
The lever that raises 0.4% is the lever that destroys the audit-zero property,
and §9o says accuracy where a criterion acts is what governs.

**What this does not claim** is that stimulus is worthless in general — a set
whose checks did not already decide everywhere would have a real gap. It
measures that this set is not one.

## 9q. The set is complete over the corpus — the closure is exhaustive, not inferential

§9p closed on an argument about *authoring*: the residue is check strength, and
raising strength costs soundness. That left a cheaper question unasked — of every
check body this session produced, does a **sound** one object to a graded design
that the 169-set simply does not contain? Selection is far cheaper than
authoring, and a yes would make the closure wrong.

| design | corpus bodies objecting | of those, **sound** | **missing from the set** |
|---|---|---|---|
| the start design L | 331 | 24 | **0** — all 24 already in |
| run 5 accepted | 305 | **0** | **0** |
| run 6 accepted (best) | 302 | 1 | **0** — already in |

**Not one sound check in 640 corpus bodies is missing from the set, on any of the
three designs.** Selection is exhausted — provably, not by inference.

### The corpus knows the designs are wrong and cannot say so soundly

302 of 640 bodies object to the best graded design, which differs from the
reference on 146 of 348 testpoints. **301 of those 302 buy the catch by also
convicting the reference.** The corpus can see the design is wrong three hundred
ways and can say it soundly in exactly one.

### And the sound column collapses as the editor works: 24 → 1 → 0

The start design is caught soundly by 24 checks, run 6's accepted design by one,
run 5's by none. **The editor consumes the corpus's soundly-expressible
discriminating power** — the same phenomenon as strength falling 6.4% → 0.4% →
0.0% in §9p, seen from the corpus's side rather than the set's.

### So the closure is exhaustive on both legs

**Selection:** 0 of 640 sound bodies missing, on three designs. **Authoring:** the
strength round moved 23 of 34 checks into convicting the reference, both-cell 0
of 34. The set is **complete with respect to everything this session can
author**, and its residue is neither selectable nor soundly authorable.

**What it does not say:** not that no sound check exists — the reference
satisfies the specification, so a check capturing what it does at those cells is
possible in principle. It says **no author working from this specification
produced one in 640 attempts**, which is the specification-plus-reader limit
measured over the corpus rather than over a round.

## 9r. The last untouched stage — requirement extraction is not the limit

Every figure above sits downstream of S1: the 89 requirements an extraction stage
read out of the specification. If divergence lived on the ports those
requirements barely constrain, re-extracting S1 would be a live lever nothing has
tried, and the goal puts regenerating oracles to new standards explicitly in
scope. This is the measurement of that, and it shuts the lever.

Two golden-free readings of *does the specification constrain this port*, per
declared output: how many of the 89 requirements **declare** it in their own
`ports` list, and how many of the 169 checks **read** it. Divergence from the
reference is the calibration, computed last, on five graded designs — the start
design L and the four accepted designs of runs 6, 7, 8 and 9.

### There is no dark port, and that alone closes it

| port | REQ declare | checks read | L | run 6 | run 7 | run 8 | run 9 |
|---|---|---|---|---|---|---|---|
| `first_hit_ack` | 7 | 37 | 1063 | 6 | 963 | 963 | 81 |
| `biu_read` | 10 | 51 | 584 | 373 | 542 | 573 | 550 |
| `burst` | 10 | 24 | 412 | 168 | 331 | 308 | 294 |
| `tag_we` | 10 | 32 | 299 | 153 | 358 | 313 | 320 |
| `biu_write` | 9 | 39 | 262 | 73 | 262 | 270 | 180 |
| `first_miss_ack` | 5 | 36 | 222 | 13 | 217 | 297 | 290 |
| `first_miss_err` | 3 | 21 | 13 | 1 | 3 | 1 | 0 |

**EVERY DECLARED OUTPUT IS DECLARED BY 3 TO 16 REQUIREMENTS AND READ BY 17 TO 51
CHECKS.** No port the specification failed to reach, so *re-extract S1 to cover
where the divergence lives* has no target. (The table is the seven **one-bit**
ports. `saved_addr` and `dc_addr` are 32 bits and `dcram_we` is 4, and a wide port
has far more ways to be wrong; controlling that matters, because the check
correlation reads **+0.01 uncontrolled and +0.45** across the narrow seven.)

### And the correlation runs the wrong way for the lever

Spearman against divergence, seven one-bit ports, each of the five designs:

| | run range |
|---|---|
| requirements declaring the port | **+0.52 to +0.93**, five of five positive |
| checks reading the port | **+0.36 to +0.54**, five of five positive |

A port that more requirements constrain and more checks watch is **more** wrong,
not less.

### The activity control settles it, and corrects the reading in both directions

A port that is almost always idle has almost no opportunity to diverge, so
activity on the reference — rows the port is high, transitions it makes — is the
rival explanation for the whole table. It is not a rival; it is the answer.

| predictor of divergence, seven one-bit ports | five designs |
|---|---|
| **golden HIGH rows, alone** | **+0.46 .. +0.93** |
| checks reading the port, alone | +0.36 .. +0.54 |
| checks, *holding HIGH rows fixed* | **−0.48, −0.03, −0.12, −0.15, +0.07** |
| requirements, *holding HIGH rows fixed* | +0.03, +0.13, +0.05, +0.88, +0.81 |

**CHECK COUNT CARRIES NO INFORMATION ONCE ACTIVITY IS HELD FIXED — four of five
designs go negative.** The reason is one number: **Spearman(checks reading a port,
golden transitions) = +0.857.** How many checks watch a port is very nearly a
restatement of how busy that port is, so the raw +0.45 was activity wearing
coverage's name. This is §9p's check-strength collapse at port granularity: the
checks are where the action is and they say nothing there.

**The requirement correlation is not robust either** — it survives holding
transitions fixed and collapses on three of five designs holding high rows fixed
— so the honest statement is the weak one: requirement coverage does not predict
divergence in the direction the lever needs, and may not predict it at all.

`first_miss_err` is the clean instance from the other end: 3 requirements, 21
checks, 62 high rows of 5,714, and 0 to 13 differing cells across five designs.
**The thinnest coverage in the set sits on the port nothing gets wrong.**

### A ninth counting-shaped defect, mine, caught before it was reported

The first version of the script looked for the requirements in the scratch
directory, found nothing, **loaded zero of them**, and printed a clean ten-row
table in which every port had no requirement mentioning it — which reads exactly
like the finding the run was looking for. The check and divergence columns of that
run were valid; the requirements column was void, and nothing in the output said
so. The loader now reads the same path the driver reads and refuses on a short
set. **Same signature as the other eight: a plausible table that is an artifact of
a file never opened.**

### What it does not claim

Seven ports and five designs that share a common ancestor, so no single
coefficient is significant and none is offered as one. What is solid is the raw
table — no dark port — and activity dominating both coverage instruments.

## 9s. The oscillation, and the trial budget nobody spent

The goal asks for oscillations between repairs to be taken into account. This is
that, read off artifacts the four graded runs already wrote — the loop's own
`state.json` for trials spent and its tracker for the objection count after each
one. No new run, no model call. All four used the same 21-trial budget, the same
start design, and the same 169-check reporting instrument; they differ only in
what extra evidence the criterion carried.

| run | used | declined | best | at trial | stopped at | up-moves | testpoints |
|---|---|---|---|---|---|---|---|
| run 6 `loopDIS` | 5 | **16** | **1** | 4 | 3 | 1/4 | **146** |
| run 7 `loopDIS2` | 12 | 9 | 5 | 10 | 7 | 3/11 | 214 |
| run 8 `loopLATCH` | 14 | 7 | 13 | 12 | 19 | 7/13 | 221 |
| run 9 `loopMAJ2` | 15 | 6 | 13 | 7 | 18 | 4/14 | 271 |

### Not one of the four reached its budget

Each stopped **voluntarily**, with 6 to 16 of 21 trials unspent. So *give the
editor more trials* is not a lever — **the editor already declines the budget it
has** — and that closure costs nothing, because the counters were on disk.

### And 4 of 4 stopped on a trial worse than their own best

Run 6 reached 1 objection at trial 4 and stopped at trial 5 with 3. Run 8 reached
13 at trial 12 and stopped at 19. **Zero of four stopped at their best** — *amended
by §9t to four of five: the replicate's last trial equals its best, so the claim
weakens from "always" to "usually"* — and
nothing in the loop's own reading tells it which trial was its best — so what a
run *ships* is decided by the latch, not by where it stopped.

### And the latch is where the proxy did its damage

The editor latches on the **highest count of passing entries in `req_results`**
(`note_best(..., passing=…)`). Runs 6 and 7 publish the 169 checks there; runs 8
and 9 publish **160 proxy units beside them**, so the proxy holds 160 votes
against the checks' 169. Reconstructed trial by trial from the trackers, and
**pinned against the grader's own objection count on each accepted design, which
it reproduces 4 of 4**:

| run | units in latch | what the latch picked | fewest objections seen |
|---|---|---|---|
| 6 | no | trial 4 — 1 objection | 1, at trial 4 |
| 7 | no | trial 10 — 5 objections | 5, at trial 10 |
| 8 | yes | trial 12 — 13 obj, 0 units | 13, at trial 12 |
| 9 | **yes** | trial 11 — **18 obj**, 42 units | **13, at trial 7** |

**RUN 9's LATCH REJECTED THE STATE WITH THE FEWEST CHECK OBJECTIONS.** Moving
from 13 objections to 18 cost 5 check votes and bought 48 proxy votes — 90
failing units down to 42 — so **the proxy outvoted the checks 48 to 5**, and the
design it chose is the worst of the four at 271 of 348. Run 8 escapes only
because its proxy units hit zero at trial 10 and stopped voting.

**So the harm has a mechanism and it is arithmetic, not judgement.** Adding units
to a latch is not neutral: it re-weights what the loop ships. 160 units of a
reading measured 54% accurate per unit (§9n) will outvote 169 checks whenever the
checks disagree by less than the units do, and here they did. **A proxy may inform
an editor and must not enter the criterion that decides which design is kept.**

### The oscillation is between a quarter and a half of all trials

Up-moves on the criterion's own count: 1 of 4, 3 of 11, 7 of 13, 4 of 14. Run 8's
sequence is the plainest — 21, 39, 21, 34, 33, 16, 22, 28, 14, 15, 23, 13, 13,
**19** — six reversals of two or more, ending above where it stood two trials
earlier. Run 9's proxy units churn the same way: its 160 majority units read 91,
101, 90, 42, 90, 42, 53, 42, 48, 42 across fifteen trials, traded back and forth
without converging.

### Trials spent and the grade are perfectly rank-ordered, and the confound is not separable

**WITHDRAWN — see §9t.** A pre-registered replicate of run 6's configuration
spent 9 trials and landed at 207, so 5 → 146 and 9 → 207 on the identical setup
run the same direction as the correlation and cannot be told from it. The
paragraph is kept because the withdrawal is unreadable without it.

*Superseded:* **Spearman +1.000 on n = 4**: 5 trials → 146 testpoints, 12 → 214,
14 → 221, 15 → 271, against a start design at 279. But **the criterion determines how much
the editor edits**, so trials are an *output* of the criterion rather than an
independent variable, and the runs carrying more scored proxy evidence are the
runs that edited more. Read as one mechanism, not two: **more units on a criterion
barely better than chance means more edits, and the harm scales with the
volume.** That is §9o's law — a proxy's aggregate accuracy is not its effective
accuracy — expressed as a budget.

### One positive reading, and it does not generalise

Each run's **minimum** objection count ranks the four designs at **+0.949**
against the grade. That is the check set ordering designs *it itself drove*,
which is not the condition under which §8's −0.223 over sixteen designs was
taken. A golden-free pipeline must rank designs it did not drive, and nothing
here shows it can.

**Scope.** Four runs from one start design against one check set. The budget
closure is exact — the counters are on disk. The ordering correlations are n = 4
and are shape, not significance.

## 9u. Where the check strength went — nine ports of ten, not a uniform dimming

§9p measures strength — objections per exposed decision — collapsing 6.4% → 0.4%
→ 0.0% as an editor works, and an earlier set's blindness was measured *uniform
across checks* (36 of 50). It has never been split by **port**, and that split is
what decides whether a targeted authoring round has anywhere to aim.

Per (check, testpoint, port): a check is **exposed** on port *p* at testpoint *t*
if it reads *p* and *p* differs from the reference there; it **decides** if
`decide` returns a verdict and **objects** if that verdict is False. A check
reading two wrong ports counts for both, because nothing says which one it should
have caught.

| design | exposed | decided | objected | strength | ports at zero |
|---|---|---|---|---|---|
| start design L | 30,906 | 17,656 | 1,013 | 5.7% | 1 of 10 |
| run 9 (worst) | 29,361 | 17,624 | 550 | 3.1% | 0 of 10 |
| **run 6 (best)** | 11,300 | 5,927 | **20** | **0.3%** | **9 of 10** |

**THE COLLAPSE IS NOT A UNIFORM DIMMING.** On the best design exactly one port
still draws an objection — `burst`, at 4.2% — and the other nine draw **zero in
5,283 decisions between them**. Strength is a rate, so this is not the design
simply having fewer wrong ports to be exposed on.

### The sharpest cell: the most-watched port is the blindest

| on run 6's design | |
|---|---|
| checks reading `biu_read` | **51**, more than any other port |
| decisions at testpoints where `biu_read` is wrong | **2,383** |
| objections | **0** |
| differing cells it carries | **373**, more than any other port |

### And the editor consumes the strength port by port

On the start design `burst` reads **31.9%** — an order of magnitude above every
other port, and where this set's discriminating power actually lives. The best
run drove it to 4.2% and silenced the other nine outright. So "the editor
consumes the strength" is not a set-wide metaphor: the set loses ports one at a
time until one is left.

### And run 9's design is not one the set had run out on

It stands at 3.1% strength with objections on **all ten ports** and 18 of 169
checks objecting — a design the checks were still talking about. Its run ended
there because its latch preferred a state 48 proxy votes better and 5 check votes
worse (§9s). **The proxy did not merely pick a worse design; it picked one the
checks were still objecting to.**

### What this does and does not open

It is a sharper target than any authoring round here has had — not *a blind cell*
but *the port where 51 checks decide 2,383 times and say nothing*. It is **not a
new lever**, because §9q already answers it: of 640 authored bodies, 302 object
to that design, exactly one is sound, and that one is already in the set. A check
for `biu_read` there would have to be one 640 attempts did not produce.

## 9v. Set blindness is dominated by port width — and inverts there

§9u's strength table is calibration: it asks where a port is *wrong*, which needs
the reference. The golden-free instrument this document has quoted all session —
**set blindness**, a cell where two spec-derived designs differ on a port and no
check watching it objects to either — needs none. Both now exist per port, so the
goal's own question can be asked directly: **does the reference-free instrument
point at the ports the reference-based one would have named?**

Nine designs, 348 testpoints, 36 pairs, 169 checks, 17,681 split cells.

| port | width | GF sighted (1 − blindness) | golden strength |
|---|---|---|---|
| `first_hit_ack` | 1 | 66.0% | 2.8% |
| `burst` | 1 | 49.3% | **31.9%** |
| `biu_read` | 1 | 26.1% | 5.8% |
| `dcram_we` | 4 | 21.8% | 2.5% |
| `first_miss_ack` | 1 | 8.6% | 0.1% |
| `tag_we` | 1 | 7.7% | 2.7% |
| `first_miss_err` | 1 | 6.9% | 0.0% |
| **`dc_addr`** | **32** | 1.8% | 4.3% |
| `biu_write` | 1 | 0.8% | 1.5% |
| **`saved_addr`** | **32** | **0.4% — worst of ten** | **7.0% — second best** |

**OVER ALL TEN PORTS THE TWO BARELY AGREE: Spearman +0.200, and 26 of 45 port
pairs = 58% ordered the same way against a 50% chance.** Restricted to the seven
**one-bit** ports it is **+0.714**. The whole difference is width, and the
inversion is total — `saved_addr` sits at opposite ends of the two rankings.

### The mechanism is the denominator, not the checks

On a 32-bit port two independently written designs differ almost everywhere —
`saved_addr` and `dc_addr` carry 1,939 and 2,694 split cells — and a check must be
right about a specific 32-bit value to catch any of them. So *two designs disagree
here* is nearly always true, and is a far weaker signal than *the design disagrees
with the reference*. **The golden-free denominator explodes with width; the golden
one does not.**

### So the headline figure is dominated by the ports its own instrument is worst on

| population | split cells | caught | blind | blindness |
|---|---|---|---|---|
| all ten ports | 17,681 | 3,074 | 14,607 | **82.6%** |
| seven one-bit | 11,276 | 2,632 | 8,644 | **76.7%** |
| three multi-bit | 6,405 | 442 | 5,963 | **93.1%** |

**41% of every blind cell in the set sits on three ports of ten**, and on those
three the instrument is measured not to track the reference-based one at all.

**The prescription is narrow and checkable: stratify set blindness by port width,
or do not quote it.** A single number over mixed widths is a weighted average of a
signal that works and one that inverts, with the inverting half carrying 41% of
the weight. **Every blindness figure in §§8–9 is over mixed widths and should be
read that way.**

**What this does not claim.** Ten ports and seven, so +0.714 is not significant at
that n and is not offered as significant; the 58% of ordered pairs is the
assumption-free reading and is barely above chance. What is solid is the inversion
itself and the arithmetic share of blind cells the wide ports carry.

### And its reach is reporting, not selection — which bounds the correction

The inversion is a defect in the per-**port** reading. Whether it matters for
anything concluded here depends on the per-**check** reading, because that is what
every sweep in §8 ranked on.

| | mixed vs one-bit ranking |
|---|---|
| Spearman across the 149 live checks | **+0.613** |
| overlap keeping the least-blind 50% (74) | 59 = **80%** |
| overlap keeping the least-blind 75% (111) | 99 = **89%** |
| overlap keeping the least-blind 25% | **not comparable** — see below |

**And the correction identifies not one clean check the mixed reading did not
already identify:**

| population | n | requirements | *audit* |
|---|---|---|---|
| checks reading a real output | 149 | 69 | *0* |
| …of those, reading a one-bit output | 116 | — | — |
| …reading only multi-bit outputs | **33** | — | *clean by construction* |
| mixed-clean (blind on no cell at all) | **8** | 7 | *0* |
| one-bit-clean, as printed | 38 | 18 | *0* |
| **one-bit-clean, reading a one-bit port** | **5** | **5** | ***0*** |

**The five are exactly the mixed-clean eight restricted to narrow readers —
8 = 5 + 3, and all five are mixed-clean.** The other 33 were the vacuity. So the
corrected clean population is *smaller* than the mixed one, and **the §8 sweeps
are not invalidated by any of this.**

### Two counting-shaped defects on the way, both mine, both caught before publication

* **The tightest cut is tie-dominated.** The raw run reported the two rankings
  overlapping on 13 of 37 = 35% at the least-blind 25% cut — which reads as the
  correction being decisive exactly where selection bites. The corrected
  instrument leaves **38 checks tied at zero**, so a 37-check cut picks 37 of 38
  equal values and which 37 is sort order. **Figure withdrawn.**
* **The clean population is an empty denominator.** The raw run reported clean
  checks going 8 → 38, a 4.75x gain. A check reading only 32-bit or 4-bit outputs
  has no one-bit cells to be blind on and scores clean *by construction* — the
  same conflation `stage_unexercised` names in capitals, in a new place.

Both have the signature the other nine on this plan have: a clean, plausible
number that flatters the hypothesis under test, invisible in the output, and
needing a second measurement aimed at the first.

## 9w. The baseline nothing here had drawn — the loop beats one-shot generation

Every graded run in §9 is reported against the *start design*. It has never been
reported against the only baseline that says whether running the loop was worth
anything: **what a competent author writes from the same specification in one
shot.** Seven such designs exist — B, C, D, E, F, G, H, each written from the same
specification and the same brief by an agent forbidden to open any other design.

| design | testpoints differing from the reference |
|---|---|
| C | **151** of 348 |
| B | 176 |
| E | 182 |
| D | 184 |
| G | 185 |
| H | 190 |
| F | 230 |
| **L — the start design of every graded run** | **279** |
| **run 6's accepted design** | **146 — better than all seven** |

**Seven independent draws span 151 to 230, mean 185, sd 23.** That is what writing
this module from this specification costs before any loop runs, and it is the
number every one-run comparison in §9 should have been read against.

**And the loop took the worst start and beat the best draw.** L is a bad draw —
279, outside the population's range on the wrong side — and the 169-check
criterion drove it to **146**, past C's 151. **The best design this plan produced
is better than any of the seven a competent author wrote from the same
specification in one shot.** That is the first statement here of what the pipeline
is *for* that survives its own measurement.

**AND IT DOES NOT REPLICATE — §9t.** A pre-registered second run of the same
configuration on the same start design landed at **207 — inside the population's
151–230**, not below it. So the loop's output beat every independent draw in **one
of two** runs and was merely typical in the other. The claim is not *the loop
beats one-shot generation*; it is ***the loop can beat one-shot generation, about
half the time in two attempts*** — and the difference matters because the first
phrasing is what a reader would act on.

**And it is not equivalence, which is the bar.** 146 of 348 testpoints still
differ and the miter says `DIFFERS`. A loop that beats one-shot generation and
does not reach equivalence is a useful loop and an unmet goal, and reporting the
first without the second is the defect this document has retracted headlines for.

**The other three graded runs did not beat one-shot generation at all** — 214, 221
and 271 sit inside or above the population's own range. That is the sharpest
reading available of what their added proxy evidence cost (§9s).

**And it sizes §9t's question.** A generation process with sd 23 makes a
60-testpoint gap between two runs unremarkable and the four-run spread of 125 only
about five sd — so the pre-registered ±20 band on the replicate is roughly **one
generation sd**, which is the right order without having been chosen for that
reason.

## 9t. PRE-REGISTERED, and running: is a single graded run a measurement?

*Written and committed before the replicate was dispatched. The outcome is not
known at the time this section is committed.*

Every graded run on this plan is **n = 1**. §9s reads four grades — 146, 214,
221, 271 of 348 — as ordered by trials spent, and every one-run comparison in §9
assumes a single editor session's grade is a measurement. **That has never been
checked.** The check is the run-6 configuration run a second time.

**Identical, and verified rather than assumed:** start design `gen/L.v` (md5
`34a7fd66…`, and the fresh loop's `dut.v` is byte-equal to it); the same 169
checks with **only the checks in the latch**; `disagreements.json` copied
byte-identical; `MAXTRIALS=21`; the same driver, suite and reference; and a brief
that differs from run 6's only in three path substitutions, asserted by a diff
that shows zero other lines. The fresh loop reports **24 objections of 169 at
init**, which is where run 6 started. What differs is the one thing under test: a
fresh editor session.

| |R − 146| testpoints | reading, fixed in advance |
|---|---|
| **≤ 20** | a single graded run resolves to about ±20. §9s's ordering stands, and so does every one-run comparison in §9 at that resolution |
| **21 – 50** | adjacent runs are not separable — run 7 at 214 against run 8 at 221 becomes noise — while the extremes are. Every §9 comparison closer than ~50 testpoints must be restated as unresolved |
| **> 50** | **a single editor session's grade is not a measurement at the resolution this plan reports.** Every one-run comparison in §9, *including §9s's own four-run table*, is under-powered and must carry that caveat, and the trials/grade correlation is withdrawn |

### THE RESULT: 207 of 348. |207 − 146| = 61 — the worst band

| | run 6 | the replicate |
|---|---|---|
| trials used | 5 of 21 | 9 of 21 |
| objections per trial | 27, 14, 6, **1**, 3 | 27, 20, 12, 11, 11, **8**, 16, 14, 8 |
| accepted design | 1 of 169 | 8 of 169 |
| **testpoints differing** | **146** | **207** |
| differing cells | 1,358 | 3,674 |
| grade | `DIFFERS` | `DIFFERS`, all three pins green |

**The pre-registered consequence applies, and is applied rather than argued.**

* **The trials-versus-grade Spearman of +1.000 (§9s) is WITHDRAWN.** 5 trials gave
  146 and 9 trials gave 207 on the identical configuration — the same direction
  the correlation asserted, and indistinguishable from it.
* **No two graded runs differing by less than ~60 testpoints may be read as
  differing for a reason.** Runs 7, 8 and 9 at 214, 221 and 271 are not separable
  from each other, and 214 is not separable from the replicate's 207 at all.
* **§9w's headline becomes "in one of two runs."** Run 6 at 146 beat all seven
  independent draws; the replicate at 207 is *inside* their 151–230 range.
* **§9x's placement drops to 3 of 6**, with the replicate a third disagreement and
  a third optimistic one.
* **§9s's "4 of 4 stopped past their own best" becomes 4 of 5** — the replicate's
  last trial equals its best.

**What survives, and it is not nothing.** 146 against 271 is 125, about twice the
observed gap, so the extremes remain ordered. Both runs stopped voluntarily with
16 and 12 trials unspent — the fifth and sixth confirmation that the editor
declines its budget. And every claim resting on a **count over a fixed
population** rather than a **spread between runs** is untouched: the audit, the
corpus-completeness closure (§9q), the per-port strength and blindness tables
(§9u, §9v), and the requirement-extraction closure (§9r).

**The uncomfortable reading, stated because it is the point.** The replicate spent
nearly twice the trials and reached 8 objections where run 6 reached 1, and its
design is 61 testpoints worse. Nothing distinguished the two runs but the session.
**The variance of this loop is comparable to the entire effect this plan has been
measuring**, and no amount of care within a single run recovers that.

**Two things it cannot do, stated now.** Two samples give a range, not a
variance: n = 2 bounds nothing tightly, and a replicate landing at 146 is
consistent with high variance and a lucky draw. And the reading is about the
GRADE, which is golden-derived — it is a fact about how much a one-run comparison
can support, not a golden-free result, and it selects nothing.

**The goal's own bar is unchanged:** equivalence. `NO-DIFF-40` on the accepted
design would meet the finish condition; anything else is `DIFFERS` and is not
partial credit.

## 9x. How to assure it golden-free — the procedure, and what each step is worth

The goal's last clause asks how completeness is assured without a reference. This
document has metrics for it and no **procedure**. Here is the procedure, with each
step's measured reliability and the thing it cannot do.

| step | what it is worth, measured |
|---|---|
| **1. Build the population** — ≥ 4 spec-derived designs, none of them one your own checks accepted | blindness **saturates at four** (§9b); two designs read 0.0% on a set that is 42.9% blind, and a design your checks accepted is worth ~12 points of over-estimate |
| **2. Select with the minority rule** — keep a check convicting ≤ *t* of the population | **95 of 95** agreement with the audit on its reject side; on the grown corpus 105 of 108 spare the reference (97%). The only golden-free selection knob measured to work |
| **3. Report a PAIR, never a number** — span *and* set blindness, blindness **stratified by port width** | mixed-width blindness is a weighted average of a signal that works (+0.714 on one-bit ports) and one that inverts (+0.200 over all ten), with the inverting half carrying **41%** of the weight (§9v) |
| **4. Keep the proxy OUT of the latch** | 160 proxy units beside 169 checks **outvoted the checks 48 to 5** and shipped the worst of four designs (§9s). A proxy may inform an editor and must not decide which design is kept |
| **5. Never read zero objections as done** | a set whose over-strict count is unknown — every set outside a benchmark — can reach zero and be *further* from correct. Score on requirements satisfied; stop on a trial budget |
| **6. Expect the editor to decline its budget** | 4 of 4 runs stopped voluntarily with 6–16 of 21 trials unspent, and 4 of 4 stopped on a trial worse than their own best. The latch is what preserves the grade (§9s) |

### Step 7 is the only verdict available on a finished design, and it is half right

With no reference you cannot ask *how far from correct is this*. You can ask where
it sits relative to the population that selected its checks. Scored on five
designs whose grade is known:

| design | objections of 169 | golden-free placement | grade | reference placement | |
|---|---|---|---|---|---|
| L (start) | 24 | ABOVE (pop 13–23) | 279 | ABOVE (pop 151–230) | agree |
| **run 6** | **1** | **BELOW** | **146** | **BELOW** | agree |
| **the replicate** | **8** | **BELOW** | **207** | **inside** | **disagree** |
| run 7 | 5 | BELOW | 214 | inside | **disagree** |
| run 8 | 13 | inside | 221 | inside | agree |
| run 9 | 18 | inside | 271 | **ABOVE** | **disagree** |

**The placement agrees on 3 of 6, and all three errors are optimistic.** Run 7 and
the replicate the checks call *better than any independent design* and the
reference calls typical. Run 9 the checks call *typical* and the reference calls
**worse than every one of the seven**. No error would reject a good design; all
three would ship a bad one.

**And the three "BELOW" designs do not even order within their own class:** 1, 5
and 8 objections give 146, 214 and 207 testpoints, so the count inverts between
the second and third. The instrument places, and *within* a placement it says
nothing.

**So the instrument can say "outside the population" and cannot reliably say "on
the good side."** That is §8's Spearman −0.223 arriving as a concrete
misplacement, and it is the honest limit of what a reference-free pipeline can
certify about a finished artifact.

**It is still worth computing, for a narrow reason.** A design scoring 1 against a
population scoring 13–23 is outside anything the specification's readers produced
— much better or much worse than they are, and worth a human look either way. What
it must not do is decide which: **run 9 sits inside the range and is worse than
every member of it**, so "inside the population" is not a clean bill.

**And it qualifies §9w.** "The loop beats one-shot generation" rests on the
*reference* grade. Its golden-free counterpart — 1 objection against 13–23 — points
the same way, and the table above is exactly why that agreement cannot be
generalised from one design.

**Scope.** Six designs from one lineage on one specification. 3 of 6 is a count,
not a rate, offered as the *shape* of the failure — optimistic in both directions
— rather than as a reliability figure.

## 9y. Best-of-N — the variance has a golden-free answer, and it is a selector

§9t made one graded run unquotable: two runs of an identical configuration landed
61 testpoints apart. That is a problem for the science and an **opportunity for
the pipeline** — if the spread is real, running the loop several times and picking
is worth more than tuning it, and the picking can be done without a reference.

**Five draws of one configuration.** Same start design (md5 `34a7fd66…`, verified
byte-equal in every loop), same 169 checks with only the checks in the latch, same
disagreement report (one md5 across all copies), same 21-trial budget, same brief
but for paths. Each reported **24 objections of 169 at init**. Only the session
differed.

**The selection rule was fixed before any grade was read:** fewest objections of
169 on the accepted design, ties broken by fewest consensus cells. It reads no
reference. Every count comes from the **grader** re-scoring `dut.v` in a clean
directory — never from the editor's own summary, because one editor reported its
accepted design as 14 objections where the re-score says 11.

| draw | trials | objections | testpoints | cells |
|---|---|---|---|---|
| **run 6** | 5 | **1** | **146** | 1,358 |
| N3 | 19 | 4 | 192 | 3,572 |
| replicate | 9 | 8 | 207 | 3,674 |
| N2 | 21 | 11 | 220 | 3,973 |
| N1 | 11 | **16** | **192** | 3,367 |

**Five identical runs span 146 to 220 — range 74, mean 191, sd 28.** That sd lands
within a point of the **23** measured across seven independently *written* designs
(§9w). **Re-running this loop is about as noisy as re-writing the module from
scratch.**

### The golden-free rule picked the best of the five

It selects run 6 at 1 objection — which is the 146, the best design available.
**0 of 5 draws beat the selected one**, and the selected design is **45 testpoints
better than an average draw** (146 against 191), a 24% reduction bought with no
reference and no new checks.

### The ordering is only partial, and the pre-registered bar says so

Spearman(objections, testpoints) = **+0.564**, inside the +0.5–0.9 band fixed in
advance as *partial* rather than the ≥ +0.9 that would make the count a reliable
order. **N1 is the counterexample and it is stark: 16 objections — the worst
golden-free score of the five — and 192 testpoints, tied with N3's 4.** A design
can score four times worse on the checks and be exactly as good.

**So the rule works as a SELECTOR and not as a RANKING**, and that distinction is
the finding: picking the *minimum* of five is robust to an ordering that is wrong
in the middle, because the minimum here is a clear outlier (1 against a next-best
4). A rule that had to separate 4 from 8 from 11 would not have this property.

### And it does not produce equivalence

146 of 348 testpoints still differ, the miter says `DIFFERS`, and all three pins
are green on every one of the five. **Best-of-N buys the best member of a bad
distribution; it does not move the distribution.**

### Two counts these draws correct, both against findings landed the same day

* **N2 spent 21 of 21 trials.** So the editor declines its budget in **6 of 7**
  runs, not 7 of 7 (§9s).
* **Across the two resumed sessions, eight late-run trials latched zero commits** —
  every one repaired two or three checks and broke more. Late trials are not
  merely noisy; on this evidence they are unproductive.

**Scope.** Five draws, one configuration, one specification. "Picked the best of
five" has a one-in-five chance of happening by luck and is not significant alone;
it is offered together with the +0.564, which points the same way and is also not
significant at n = 5. **Two of the five were interrupted by a machine restart and
resumed in a fresh session**, so they are not single continuous runs — recorded
because it is a deviation from the protocol, not a detail.

## 9z. The set holds 53 opinions, not 169 — and the span figure is wrong by 30 points

Every count in this document treats the set as **169 checks**. But a check's usable
content is its **verdict vector** — what it says about each (design, testpoint) it
decides. Two checks with identical vectors are one opinion counted twice: they can
never separate a pair the other cannot, they add nothing to blindness, and an
editor satisfying one satisfies the other. That had never been counted.

| over the nine population designs | checks |
|---|---|
| live, reading a real output | 149 |
| **distinct verdict vectors** | **77** |
| exact duplicates of another check | **72 (48%)** |
| largest identical group | **21 checks, one vector** |
| vectors that never object | 49, covering **108 checks** |

### The population under-reports, which is why the follow-up ran

"Never objects on the nine" is not "never objects" — a check silent on the
population may still object on a design an editor produced, and reading the first
as the second is the conflation `stage_unexercised` names in capitals. So every
population-mute check was re-decided against the **six graded designs** too:
**12 of the 108 do object** (11 on the start design, 1 on an edited one). 11% of
the population-mute set is merely unexercised, and the nine-design figure alone
would have overstated the result.

### But 96 of 149 never object on any of fifteen spec-derived designs

| the effective set | checks | requirements |
|---|---|---|
| ever object on any of fifteen | **53** | **43** |
| never object on any of fifteen | **96** | 31 requirements have nothing else |

**SO THE SPAN FIGURE IS WRONG BY THIRTY POINTS, AND THE ERROR IS MINE.** This
document quotes **69 of 89 requirements = 78%**. Counted by requirements holding a
check that ever objects on *anything*, it is **43 of 89 = 48%**. The remainder is
span made of checks that have never said a word.

### And the minority rule selects for them

The rule keeps a check convicting **at most t** of the population — and a check
convicting **none** passes it trivially. Its 95-of-95 precision on the *reject*
side is real and unaffected; what is new is that its **accept side is dominated by
silence**. §5's endorsement of it should be read with this beside it.

### What this explicitly does not say: that the 96 are useless

§9 already measured the opposite case — of 14 checks that caught a held-out
design, **three convict none of the thirteen candidates**, and they are not
unfalsifiable; the population simply happens to be right about those requirements
and a fourteenth design is not. A check silent on fifteen designs may catch the
sixteenth. What is established is narrower and still large: **the 96 contribute
nothing to any golden-free instrument built on this population, they inflate every
span figure here by thirty points, and the endorsed selection rule prefers them.**

### The lever this opens — and §9aa shuts it

Every authoring round in §9 scored a new check on which requirement it cites, or
on the sound-and-discriminating pair. **Neither notices that 21 checks can share
one vector.** Score a candidate on whether its **verdict vector is new** —
computable over the population with no reference, mechanical, and it rejects the
48% duplicate rate by construction.

**That target was then applied to the 640 bodies that already exist, and it
selects 19 checks of which all 19 convict the reference — see §9aa.** Novelty is a
real property and it is not a soundness-preserving one.

## 9aa. Every new opinion the corpus holds is bought by convicting the reference

§9q closed the corpus at the level of *catches*: no sound body is missing that
objects to a graded design. That does not close it at the level of **opinion** — a
body can hold a vector the set lacks without catching those particular designs,
and **blindness is closed by new opinions, not by catches.**

Three reference-free filters, applied in order to every corpus body outside the
set; the audit runs last and selects nothing.

| 640 corpus bodies, 169 in the set, 77 vectors held | |
|---|---|
| outside the set with a **new** vector | 349 |
| of those, **ever object** on the nine | 285 |
| of those, passing the **minority rule** | **19** |
| *audit: convict the reference* | ***19 of 19*** |

**Not one is sound.** They span 9 requirements, 5 new to the set, and adding any
would break the audit-zero property that §8 measures as the whole difference
between a criterion that discriminates and one that does not.

### The contrast is exact — same corpus, same population

| ever-objecting opinions | n | *audit* |
|---|---|---|
| already **in** the set | 53 | ***0*** |
| **new**, passing the minority rule | 19 | ***19*** |

**The set already contains every sound opinion this corpus holds** — *against a
population of nine designs.* That is strictly stronger than §9q: not merely that
no sound *check* is missing, but that no sound *opinion* is, and the 349 that
exist are mute, over-strict, or both.

> **AMENDED BY §9ab, WITHIN THE HOUR, AND THE UNQUALIFIED FORM WAS MINE.** I wrote
> that sentence without the nine-design qualifier, and §9ab measures it against
> **29** designs — every one this pipeline has produced. It finds **one** sound
> opinion the nine could not see. So the claim holds as a statement about this
> population and is false as a statement about the corpus, which is exactly the
> caveat the paragraph below names and did not carry up into the headline. The
> superseded wording is kept because the correction is one check wide and the
> reading barely moves.

### And it puts a number on the minority rule's defect

Over the corpus the rule spares the reference **105 times in 108 — 97%**.
Restricted to bodies that actually *say* something and say something *new*, it
spares it **0 times in 19**. **Its accept-side precision is carried entirely by
checks that convict nothing.** Strip the silence away and it is not 97% but zero.

**What stays open, narrowly.** 640 bodies, one specification, one nine-design
population. A sixteenth design could make a currently-mute vector object — three
checks in §9 did exactly that. What is closed is **selection over what exists**:
there is nothing sound left in this corpus to select, at the level of catches or
of opinions. ***§9ab tested exactly this sentence against twenty more designs and
it is right in shape and wrong in the last clause: one sound opinion is left, and
it saturates.***

## 9ab. Twenty more designs wake one sound opinion, and reveal four points more blindness

§9aa closed the corpus at the level of opinion and named its own limit: *"A
sixteenth design could make a currently-mute vector object."* **There are twenty**
— every editor run this plan drove to its own stopping point, each with a complete
348-testpoint trace set, none of them in the population that every golden-free
figure here is measured against. §9b says these are the valuable ones: *"whatever
a set could see was edited out of them."* Pre-registered in
`docs/evidence/prereg/wide-population.md` before any number was read.

**The population goes 9 → 29.** Seven written independently, twenty-two accepted
by this criterion or a variant. All 29 are behaviourally distinct, on outputs and
on outputs-plus-probes alike — which does **not** contradict §9k's *"five
opinions, not nine"*, measured **at the 812 blind split cells** where five of them
agree. Distinct over a whole trace and identical where the checks are blind are
different facts.

**The minority threshold is deliberately NOT scaled or applied across the 29.**
Twenty of them are edits of one start design, so a check catching that design's
defect would convict every descendant and be rejected as over-strict — the rule's
premise inverted by correlation, discarding exactly the checks worth having. It
stays at `convicts ≤ 2` over the nine it was calibrated on; the widened population
supplies only the legs that detect a *new opinion*.

### Q1 — the closure was population-limited, by one check

| | nine designs | **29 designs** |
|---|---|---|
| vectors the set holds | 77 | 86 |
| outside the set with a **new** vector | 349 | 350 |
| of those, **ever object** | 285 | 287 |
| of those, passing the **minority rule** | 19 | **21** |
| *audit: convict the reference* | *19* | *19* |
| **spare the reference** | **0** | **2** |
| of those, **sound by silence** — decide **nothing** on the reference | — | **1** |
| **GENUINELY SOUND** | **0** | **1** |

Both extra survivors are mute on the nine and object only on the twenty, so the
widening is what found them. **One is real and one is not**, and the one that is
not reproduces §9aa's own finding one level down: `REQ-0006.off` decides **0 of
348** testpoints on the reference, so "spares the reference" is silence, not
soundness. Counting it would be the exact defect §9aa measured.

The survivor that stands is `R2::REQ-0008@saved_addr` — **decides 329 of 348 on
the reference and objects nowhere on it**, convicts 2 of 29, and **catches a
graded design** (N2, wrong on 220 of 348). It is a genuine both-cell check for a
requirement the set does not cover.

**The nine-design legs are PINNED to §9aa — 77 / 349 / 285 / 19, reproduced
exactly — or the run refuses.** The first version of the script disagreed (85 /
466) because it omitted `novelvec.py`'s fourth filter: a body reading **no real
declared output** cannot close a blind cell and must be dropped. 640 bodies became
502. That is the twelfth counting-shaped defect on this plan and it was caught by
the disagreement with a prior measurement, not by the headline looking wrong.

### And it saturates at one, which is what closes the lever

Sound survivors against population size, several random subsets per size, the
audit and the silence check run once over the union of every survivor any subset
produces:

| designs | 9 | 12 | 15 | 18 | 21 | 24 | 27 | 29 |
|---|---|---|---|---|---|---|---|---|
| survivors | 19 | 19.4 | 20.0 | 20.6 | 20.6 | 21 | 21 | 21 |
| **SOUND survivors** | **0** | 0.2 | 0.5 | 0.8 | 0.6 | **1** | **1** | **1** |

**The union of survivors over every subset is 21 bodies, of which exactly ONE is
sound.** So this is not a rate that keeps paying — it is a one-off, flat by 24
designs, in the same shape as §9b's blindness *estimate* saturating at four.
**Widening the population is not a lever.**

### Q2 — and blindness rises, exactly as §9b's mechanism predicts

Pre-registered direction, and it is confirmed. §9b's unit — the (pair, testpoint)
cell — **pinned to its published 55.1% or the run refuses**:

| population | mixed | one-bit |
|---|---|---|
| the nine (every figure on this page) | **55.1%** *(pin)* | 55.9% |
| **all 29 the pipeline actually made** | **59.4%** | **61.2%** |

**So 55.1% was optimistic**, because the population held only two loop-accepted
designs where the pipeline produces them by the dozen. Per-pair spread over the
29: min 0.0%, median 69.6%, max 100.0%, with **13 of 405 pairs reading zero** —
the clean-sheet hazard §9b flags, now at scale.

### The two halves move apart, and that is the result

| | |
|---|---|
| blindness the wider population **reveals** | 55.1% → 59.4%, **+4.3 points** |
| blind cells the one sound opinion **closes** | **78 of 41,998 = 0.19%** |
| the same check, on the nine | **0** — it is mute there |

**The population that finds the residue and the corpus that would close it scale
apart by a factor of twenty-two.** Every design added shows the set more it cannot
see and supplies almost nothing sound to see it with. That is the strongest form
the closure has taken: not that the corpus is exhausted against one population,
but that **enlarging the population makes the gap wider, not narrower.**

**What this does not do.** It does not raise the graded score — equivalence is
unmet at **146 of 348** on the best of five draws and nothing here touches that.
One check that catches the *worst* graded draw and not the best is a correction to
a closure, not progress toward equivalence.

## 9ac. The seventh graded run — a golden-free set with a perfect audit reaches zero, and is wrong on half the suite

Pre-registered in `docs/evidence/prereg/dedup-set-editor-run.md` before dispatch.
§9z found the 169-check set holds 77 opinions, 48% of its checks exact duplicates
and one vector carried by 19 — and reported it as a *span* correction. It bites
where §9z never looked: **the editor counts objections**, so an opinion carried by
19 checks casts 19 votes. Every graded draw so far ran on that weighting.

**The set.** One check per distinct verdict vector over all 29 designs, plus
§9ab's one sound opinion. De-duplication removes nothing by construction — two
checks with the same vector agree on every (design, testpoint) either decides.

| | 169-check set | **de-duplicated** |
|---|---|---|
| checks | 169 | **87** |
| reads no real declared output | 20 | **0** |
| ***audit: convict the reference*** | *0* | ***0*** |
| decide nothing on the reference | — | **0** |
| objections on the start design | 24 | **22** |

### The run, and it terminates on its own criterion

A Sonnet editor, same arbitrary unchecked LLM start design, same stimulus, same
21-trial budget as the five controls. **Objections 22 → 0 of 87 in 12 trials,
with nine unspent** — it stopped because the criterion was satisfied.

Passing counts: 65 → 66 → 72 → 77 → 80 → 81 → 84 → **87**. **The ratchet refused
all three regressions it was offered** (77→77, 84→73, 84→78) and the loop never
returned to a design it already had. **There is no oscillation in this run** —
the failure mode §9s and the earlier RTL rounds measured does not appear.

### The grade, re-scored in its own clean directory, all three pins green

| | testpoints differing | cells |
|---|---|---|
| the start design | **279 of 348 (80%)** | 4,450 |
| **after the loop** | **174 of 348 (50%)** | **2,071** |

**`EQUIVALENT` / `NO-DIFF-40` / mutant `DIFFERS` in one process, so the verdict is
quotable: `DIFFERS`.** All ten declared outputs still differ; **none was repaired
to never-differing.**

### Against the pre-registered bar: de-duplication is not shown to do anything

Five control draws of the 169-set from this same start design graded at **146,
192, 192, 207, 220**. This one lands at **174 — inside that spread**, better than
the median and worse than the best. By the rule fixed before the run, that is the
outcome that says the lever did nothing, and it is the outcome that was predicted.

### AND IT IS THE STRONGEST NEGATIVE ON THIS PAGE, BECAUSE OF THE AUDIT

§8's rule-B run reached zero objections on a set **7 of whose checks convict the
reference**, so zero was *arithmetic proof of non-equivalence* — the design scored
0 where a correct one scores 7. **Here the audit is zero, so reaching zero is
CONSISTENT with equivalence.** The criterion could have been satisfied by a
correct design. It was satisfied by one wrong on half the suite.

**And every available explanation is excluded by the run's own properties:**

* **not unsoundness** — audit zero, verified before dispatch;
* **not redundancy weighting** — this is the de-duplicated set, one opinion one vote;
* **not thinness** — 86 of the 87 decide on the accepted design;
* **not an editor stopping early** — nine trials unspent, criterion satisfied;
* **not a wrong gradient** — objections, testpoints and cells all fell together,
  279 → 174 and 4,450 → 2,071, the largest correct-direction move this plan has
  recorded;
* **not oscillation** — the ratchet refused every regression.

**MAXSOUND reached the same shape and was selected BY the reference, so it was
labelled a ceiling. This set is selected golden-free** — a partition over the
population's own traces plus the minority rule, with the audit computed last and
confirming zero. **So the negative now holds for a set a production pipeline could
actually build.**

### What it says about blindness, which is what the goal asks

The set is **59.4% blind** on the population the pipeline produces (§9ab), and the
design it accepted differs on **50% of testpoints**. Those are different
denominators and the agreement is not a numerical claim — but the direction is the
whole point: **a criterion that cannot see most of what two spec-derived designs
disagree about will terminate on a design that is wrong about most of it.**
Completeness, not soundness and not weighting, is the binding constraint, and
blindness is the measure of it.

## 9ad. All 154 sound checks in the corpus pass the design; 255 unsound ones catch it

§9ac left completeness as the only standing explanation. This is the exhaustive
test of it, and it is the sharpest number on this page.

Every one of the 502 live corpus bodies re-decided against **the design the
de-duplicated set accepted** — the closest design to the reference this pipeline
has produced, and one that did not exist when §9q closed the corpus at the level
of catches. Pre-registered binary bar: **one sound objector means the set is
improvable by selection; zero means selection is finished.**

| of 502 live corpus bodies | n | |
|---|---|---|
| **SOUND** — decide on the reference and spare it | **154** | 31% |
| **OBJECT** to the accepted design | **255** | 51% |
| **BOTH** | **0** | |
| *expected overlap if the two were independent* | *78* | |

**ZERO AGAINST AN EXPECTED SEVENTY-EIGHT.** Not below chance — at the floor the
marginals allow, on the best design this pipeline has produced, judged by the best
set it can build.

### And the set already holds every sound check that could have helped

The 87-set is audit-zero and all 87 decide, so all 87 are among the 154. **That
leaves 67 sound checks in the corpus outside the set, and not one of them objects
to this design either.** So the result is not an artifact of the design having
been optimised against the 87: *all 154 sound checks in the corpus pass it*, and
the 255 that catch it are exactly the ones a sound set may not contain.

**The 255 objectors span 60 requirements.** The corpus knows this design is wrong
across 60 requirements of the specification and **can say so soundly with zero
checks.**

### What this settles, and it is the end of one road

**SELECTION IS FINISHED.** Not "no better rule was found" — there is nothing left
to select. Every check that would reject the best design convicts a correct one,
so the golden-free soundness rule, whose reject side is measured 95 of 95, will
correctly discard all 255. A sound set that rejects this design does not exist in
this corpus at any size, under any rule, with or without the reference.

**So the residue is UNAUTHORED, not unselected** — and §9c already priced
authoring it: 76 calls aimed at named blind cells closed **zero** cells soundly,
with the checks that close the residue measured as exactly the ones the soundness
rule rejects (Spearman +0.350). Both halves of the remaining route are now
measured and both are closed.

**This is why the loop terminates at 174 of 348 and no set on this corpus can do
better.** It is not a tuning failure, a weighting failure, a stimulus failure or
an editor failure — §9ac excluded each of those individually. It is that
soundness and discrimination are, on this specification and this population,
very nearly disjoint properties, and the finish condition needs their
intersection.

> **QUALIFIED BY §9ae: that last sentence is true of CHECKS and too strong of
> OBJECTIONS.** Soundness here is a suite-wide property — a check is discarded for
> convicting the reference *anywhere* on 348 testpoints. Asked per objection
> instead, **879 of these checks' objections to the accepted design land on
> testpoints where they spare the reference**, and they cover 133 of its 174 wrong
> testpoints. The evidence is not disjoint from soundness; the per-check
> aggregation is what makes it look that way. §9ae then measures whether any
> golden-free rule can separate those 879, and none can.

## 9ae. The discarded objections are locally right, and nothing golden-free can tell which

§9ad asked a **per-check** question — *is any check sound?* — and answered zero of
255. Soundness there is suite-wide: a check is discarded for convicting the
reference anywhere on 348 testpoints. **The per-OBJECTION question is different,
and this plan's own record says it can come out the other way:** *"each fired on a
testpoint where golden PASSES, so each objection was locally legitimate."*

A check convicting the reference at testpoints {A,B} and catching the accepted
design at C is, **at C**, making a correct objection. The per-check rule throws
away the whole check, C included. Two legs, **both required**, fixed before any
number was read.

### Leg 1 — the phenomenon is real, and it is most of the residue

| | |
|---|---|
| unsound objectors with ≥1 objection where they spare the reference | **84 of 255 = 33%** *(bar: ≥20%)* |
| objection **cells** that are locally legitimate | **879 of 15,795 = 6%** |
| distinct testpoints those 879 land on | **133** |
| the accepted design is wrong on | 174 of 348 |

**So 76% of the design's remaining wrong testpoints carry an objection that is
locally correct** — already authored, already in the corpus, and currently
discarded. That is the opposite of "there is nothing left", and it is why §9ad's
closing sentence needed the qualifier now attached to it.

### Leg 2 — and no golden-free rule separates them. FAILED, at every threshold

The candidate is the minority rule moved down a level: admit an objection at
testpoint T if the check spares at least *k* of the nine population designs **at
T**. It reads no reference.

| k | admitted | legitimate | precision | lift |
|---|---|---|---|---|
| 4 | 3,195 | 730 | 23% | 4.11x |
| 5 | 3,019 | 727 | 24% | 4.33x |
| **6** | 1,374 | 720 | **52%** | **9.42x** |
| 7 | 671 | 321 | 48% | 8.60x |
| 8 | 329 | 171 | 52% | 9.34x |
| 9 | 117 | 58 | 50% | 8.91x |

**Precision plateaus at about half and never approaches the 70% bar. The curve is
FLAT, so this is not a threshold to retune** — tightening from 6 to 9 costs 92% of
the volume and moves precision by two points.

**The lift is real and large — up to 9.4x over a 6% base rate**, among the best
predictive signals on this page. It is still a coin flip on the question that
matters: an admitted objection is legitimate about half the time, so a criterion
built on it hands the editor one demand no correct design can meet for every one
it should. The ordering argument names that condition as fatal, which is why the
bar was set at 70% and why 52% fails it.

### What this settles, and it is a sharper closure than §9ad's

**By the pre-registered rule this is a NEGATIVE and is recorded as one.** Both
legs were required; Leg 2 failed at every threshold. It is the thirteenth
instrument to fail on this plan and **the first aimed at the objection rather than
the check.**

But it relocates the obstruction precisely, and the relocation is the result:

* **the evidence EXISTS** — 879 correct objections covering 76% of the residue,
  already written, sitting in the corpus;
* **the per-check soundness rule discards it** — correctly, since the checks are
  unsound suite-wide and no rule can keep a check only where it is right without
  knowing where that is;
* **and the golden-free instrument that would tell it where is measured at ~50%**,
  flat across its whole range.

**So the residue is not unauthored after all — it is unSEPARABLE.** §9ad's
"unauthored, not unselected" holds for *sound checks*; for *correct objections* the
truth is that they were authored, they are in hand, and the only instrument that
identifies them is the reference. That is the same wall the plan has hit twelve
times, reached for the first time from below the level of the check — and it is
the strongest form of the case for a decision on the underdetermined cells from
outside the specification-plus-reader loop.

## 9af. The CEILING run: seven times more vetted objections produced a worse design

**A CEILING. It uses the reference and no figure from it is a golden-free score** —
the same status as MAXSOUND and the reference-derived probes, and the use of the
reference the goal permits. Pre-registered in
`docs/evidence/prereg/ceiling-editor-run.md` before dispatch.

§9ae left one question unanswered: thirteen instruments show no golden-free *rule*
separates good objections from bad, but nothing had tested whether **the checks
themselves suffice.** The ceiling answers that by removing the separation problem
entirely: all 502 live corpus bodies, each masked to the testpoints where it does
**not** convict the reference, so **every objection it can raise is one a correct
design would not draw.** Audit verified zero by re-scoring the reference through
the mask, 90.6% of cells admitted, no check left empty.

### The result, graded in its own clean directory with three pins green

| arm | criterion | objections | testpoints differing | cells |
|---|---|---|---|---|
| the start design | — | — | 279 of 348 | 4,450 |
| **DEDUP** — 87 checks, **golden-free** | audit 0 | 22 → **0** | **174** | 2,071 |
| **CEILING** — 502 checks, **every objection vetted** | audit 0 | 155 → **86** | **261** | 2,526 |

*Five golden-free control draws for scale: 146, 192, 192, 207, 220.*

**THE MAXIMALLY-INFORMED CRITERION PRODUCED A DESIGN WORSE THAN EVERY ONE OF
THEM**, and 87 testpoints worse than the golden-free set that had a fourteenth of
its objections.

### What it does NOT settle, stated first

**The criterion was never satisfied**, so the pre-registered binary does not apply.
The editor stopped at 86 objections with **six trials unspent and thirteen commits
rejected** — it ran out of theories, not budget. MAXSOUND's own pre-registration
fixes the reading: *objections remaining with trials left measures the editor, not
the set.* **So this does not show the checks are insufficient**, and it must not be
quoted as though it did. It is also **one draw**, against a control spread with
sd 28.

### What it does show, and it is about proxy metrics rather than about checks

**Objection count and design quality came apart, hard.** Objections fell 44%
(155 → 86) while divergence fell 6% (279 → 261). The DEDUP arm fell 100% on
objections and 38% on divergence. **More correct objections did not convert into a
better design; the arm with far fewer of them won by 87 testpoints.**

~~**The mechanism the editor's own report points at: a locally-correct objection
from a globally-wrong check carries a globally-wrong EXPLANATION.** The editor
does not act on a verdict; it reads the requirement sentence and the check's
detail and builds a structural theory. So vetting the objections is not
sufficient — the explanations have to be right too.~~

> **WITHDRAWN BY §9ag, AND IT WAS MINE.** I inferred that mechanism from one run
> plus the editor's self-report, pre-registered a test of it, and **the test
> refutes it**: suppressing the checks' reasoning entirely made the design
> *worse* (276 against 261), not better. The explanations were not poisoning the
> run. What survives from this section is the measurement — 7x the vetted
> objections produced a worse design — and not the reason I gave for it.

### And it reverses the natural prior about set size

More signal was assumed better throughout this plan: §9z treated redundancy as a
reporting defect, and §9ab chased more designs. **Here 7x the objections, every one
of them correct, made the outcome worse than a 87-check set** — which says the
editor's budget is spent on *prioritising* objections, and that a large correct
criterion can exhaust it before a small one does. The DEDUP arm's advantage was
never its soundness, which the ceiling also has; it was that 22 objections are
actionable and 155 are not.

## 9ag. The explanation channel is REFUTED — suppressing the reasons made it worse

§9af's mechanism was mine and rested on one run plus an editor's self-report,
which is the evidence shape this plan has retracted mechanism claims for before.
So it was pre-registered and tested
(`docs/evidence/prereg/explanation-channel.md`), with the refutation branch
written in advance.

**The isolation.** Same ceiling set, same mask, same **155** starting objections,
same start design, stimulus and budget. One change: each objection's account of
what is wrong is replaced by the **ports that check reads** — the editor is told
where to look and not what to conclude.

| arm | objections | testpoints differing | cells |
|---|---|---|---|
| the start design | — | 279 of 348 | 4,450 |
| **DEDUP** — 87 checks, theory shown, **golden-free** | 22 → 0 | **174** | 2,071 |
| CEILING — 502 checks, theory shown | 155 → 86 | 261 | 2,526 |
| **ND** — 502 checks, **theory suppressed** | 155 → 122 | **276** | 3,959 |

**THE BAR WAS ≥261 MEANS REFUTED, AND IT LANDED ON 276.** Removing the checks'
reasoning made the design worse on testpoints (276 vs 261) and much worse on
cells (3,959 vs 2,526), and left more objections standing (122 vs 86) after three
*more* trials. **The explanations were not poisoning the run — on this evidence
they were net helpful.** §9af's mechanism is withdrawn.

### What survives, and what is now the leading candidate

The **measurement** in §9af stands untouched: seven times the vetted objections
produced a worse design than a golden-free set with a fourteenth of them. Only
the *reason* is withdrawn.

Of the two mechanisms §9af named, **volume is the one left standing** — both
155-objection arms land at 261 and 276 while the 22-objection arm lands at 174.
**It is not isolated either**: the arms differ in set size (502 vs 87) *and* in
soundness profile, so volume is a candidate and not a finding, and saying more
than that would repeat the mistake this section exists to correct.

### And the run says something the ceiling did not

Given only *where* to look and no theory at all, the editor still found real
structural defects: an inverted `~load_r` guard, an off-by-one refill counter
(`OR1200_DCLS-2` for `-1`), error responses misread as completions, and a
spurious `IDLE` cycle between back-to-back requests. **Localisation alone is
enough to diagnose** — which is why suppressing the reasons did not collapse the
run, only made it modestly worse.

### A defect in my own briefs, found by the editor rather than by me

Every brief this session states that `checks_objecting` *"is the only thing in the
latch."* **It is not.** `req_results` carries **ten consensus-derived per-output
units alongside the checks**, and the ratchet counts passing units across both.

| arm | checks | consensus units | consensus share |
|---|---|---|---|
| DEDUP | 87 | 10 | **10%** |
| CEILING / ND | 502 | 10 | **2%** |

The consensus is measured **28.5% right against the checks' 71.4%**, so weight on
it should hurt — and **DEDUP carried five times more of it and still won by 87
testpoints**, so the confound runs against DEDUP's advantage rather than
explaining it. The comparisons stand; the brief was wrong, it was mine, and every
editor this session acted on it.

## 9ah. ITERATION DESCENDS — 279 to 174 to 112, the best design this plan has produced

**A CEILING for the second loop** — its criterion is reference-masked, so **112 is
not a golden-free score.** Pre-registered in
`docs/evidence/prereg/chained-run.md` before dispatch, with the bar fixed at
**under 146 = best ever**.

Every graded run on this plan had been a **single loop from one start design** —
seven draws, three sets, one starting point. Iteration was never tested.

| stage | criterion | testpoints differing | cells |
|---|---|---|---|
| the arbitrary unchecked LLM design | — | 279 of 348 | 4,450 |
| **after loop 1** | 87 checks, **golden-free**, driven to 0 objections | **174** | 2,071 |
| **after loop 2** | 502 checks, vetted, chained onto loop 1's output | **112** | **813** |

*Seven prior draws span 146–220; the previous best was 146.*

**112 BEATS EVERY DRAW THIS PLAN HAS EVER GRADED**, by 34 testpoints, and the
differing cells are down **82% from the start design** and 61% from where loop 1
left off. The miter still says `DIFFERS`, three pins green.

### So the stopping point of a loop is not the floor of its design

Loop 1 **terminated on its own criterion** — 0 objections of 87, nine trials
unspent. Every reading available at that moment said it was done. It was 62
testpoints from where a second loop took the same design. **A criterion reaching
zero means the criterion is exhausted, not the design**, and that is now measured
rather than argued.

What made loop 2 possible is that a *different* criterion had 84 vetted
objections on a design its own set called finished. The four repairs it landed
were a missing `biu_read` term for cache-inhibited loads, an off-by-one fetching
**five words per four-word line**, a `dcqmem_ci_i`/`biudata_valid` race
oscillating `saved_addr_r`, and — the largest, +11 requirements with zero
regressions — removing `abort_request` from the refill states, since a
`dcqmem_cycstb_i` drop during a BIU-owned burst is not a cancellation.

### AND THE GOLDEN-FREE PIPELINE CANNOT DO THIS, WHICH §9ad ALREADY SETTLED

The obvious prescription is golden-free: *loop, re-select checks against the
design produced, loop again.* **It does not work here, and the reason is
measured.** §9ad re-decided all 502 live corpus bodies against exactly this 174
design:

| of the corpus, against loop 1's output | n |
|---|---|
| OBJECT to it | 255 |
| of those, **SOUND** | **0** |

**The 84 objections that powered loop 2 are drawn from those 255, and not one of
their checks is sound.** A golden-free re-selection keeps only sound checks, all
154 of which pass this design — so it would find **zero** objections and the
second loop would never start. That is precisely what loop 1's own set reported.

**So iteration is real, it is worth 62 testpoints, and its fuel is exactly what a
golden-free soundness rule must discard.** The two halves have to be quoted
together: the mechanism works and the golden-free pipeline cannot run it.

### What this changes, and what it does not

It **does not** reach equivalence — `DIFFERS` at 112 of 348, and the goal's finish
condition remains unmet after eight graded draws.

It **does** retire "the loop has converged" as a reading of zero objections, and
it makes the per-testpoint vetting of §9ae the thing worth an instrument: 133 of
174 wrong testpoints carried a locally-correct objection, and this run converted a
chunk of exactly that into 62 testpoints of grade. **The residue is reachable —
what is missing, still, is a reference-free way to tell which objections are the
right ones**, measured at ~50% precision in §9ae and flat across its range.

## 9ai. The golden-free second loop is EMPTY — and the rule is right, which is why

§9ah's descent is real and its grade is a **ceiling**: the chain's criterion was
reference-masked, so 112 is not a golden-free score. The goal's standing demand
is that final scores not depend on the reference, so the question that decides
whether §9ah means anything for a production pipeline is whether **a golden-free
rule can assemble the second-loop criterion at all.**

It cannot, and it is not close.

**The golden-free analogue, with no reference anywhere.** A pipeline re-selecting
against the design its first loop produced cannot ask about soundness. It applies
what it applies at first selection — the minority rule, whose reject side is
measured 95 of 95:

    OBJECTS    to the design loop 1 accepted
    MINORITY   convicts at most 2 of the nine population designs

| | n |
|---|---|
| live corpus bodies | 502 |
| **OBJECT** to loop 1's design | **255** |
| of those, passing the **minority rule** | **0** |

### It is a structural exclusion, not a threshold that needs tuning

| the check convicts, of nine | checks | minority rule |
|---|---|---|
| 4 | 8 | rejects |
| 5 | 3 | rejects |
| 6 | 1 | rejects |
| 7 | 3 | rejects |
| **9 — all of them** | **240** | rejects |

**The minimum over all 255 is FOUR of nine, against a threshold of two**, and
**94% convict every single population design.** There is a gap between the
threshold and the nearest candidate, so no retuning reaches them: t=3 still keeps
nothing, and t=4 would keep eight checks while abandoning the rule's entire
rationale — a check convicting nearly half the population is the signature the
rule exists to reject.

### And the rule is CORRECT to reject them, which is the whole point

§9ad already measured these same 255: **not one is sound.** So the minority rule
is not making an error here. It is doing exactly its job, correctly identifying
255 over-strict checks — **and in doing so it removes the entire fuel supply for
the second loop.**

**THE CHAIN'S 62 TESTPOINTS ARE BOUGHT ENTIRELY WITH CHECKS THAT CONVICT A
CORRECT DESIGN.** Every one of them. A golden-free pipeline that kept them would
be accepting a criterion no correct design can satisfy; one that rejects them —
as it must, and as this one does — finds nothing to say about the design its
first loop produced and stops there.

### So this is the answer to the goal's last clause, and it is a negative

The goal asks to *"ultimately check how to assure that with a golden-free
pipeline."* On this corpus the answer is now measured rather than inferred:

* **iteration is the one mechanism that moves the grade** — 174 → 112, better
  than all seven single-loop draws;
* **its fuel is 255 checks of which zero are sound and none passes the
  golden-free rule**, by a margin of two convictions with nothing in between;
* **so the golden-free pipeline reaches 174 and stops**, which is exactly what
  loop 1 reported when it terminated at zero objections with nine trials unspent.

**The gap between the golden-free pipeline and the ceiling is therefore 62
testpoints, and it is not a gap in the rule, the prompt, the stimulus or the
editor. It is the corpus containing no sound check that objects to a design its
own criterion has finished with.**

## 9aj. Narrowing cannot author the second loop's fuel either — 0 of 24, and the trade is exact

The last route the goal leaves open. Every closure this session treated the corpus
as fixed; the goal does not — *"regenerating oracles up to new standards are fair
game."* So: can a check with the objection the second loop needs be **written**
rather than **selected**? Pre-registered in
`docs/evidence/prereg/narrowing-the-chain-fuel.md`.

**Fully golden-free, and the design had to be changed to keep it so.** The
informative population is the 84 objections that powered the chain — but those
were vetted *by the reference*, so naming one to an author would put a
reference-derived finding into an authoring prompt, which the control-leak rule
forbids. **The population is therefore the 255**, both of whose legs read only
spec-derived artifacts: *objects to the design loop 1 accepted*, and *convicts all
nine independent implementations*. 24 checks, one per requirement.

**Integrity, run before scoring:** 24 of 24 returned, **24 compile, 0 duplicate
bodies** (the fabricated-response signature), 0 returned unchanged. Leak check
over every prompt: clean.

| of the 24 narrowed checks | n |
|---|---|
| **VACUOUS** — object to nothing at all | **2** *(counted as losses)* |
| still OBJECT to loop 1's design | 19 |
| **passing the MINORITY rule** | **0** |
| *audit: sound* | *0* |

### And the trade is exact, which is the finding rather than the zero

| convicts, of nine | checks | still objects? |
|---|---|---|
| **0** | 2 | **no — vacuous** |
| **5** | 3 | **no** |
| 6 | 1 | yes |
| **9 — unmoved** | **18** | yes |

**Eighteen of twenty-four did not move on the population at all**, and of the four
that fell below nine, **three stopped objecting**. The one that kept its objection
still convicts **six of nine** — three times the threshold.

**So the conviction count and the objection fall together.** There is no setting
of this edit where one drops and the other survives: narrow enough to satisfy the
golden-free soundness rule and the check stops saying the thing that made it
worth keeping. That is #99 — over-strictness and vacuity as one defect with two
signs — measured on the one population where the objection was known to be worth
something.

### The third narrowing round, and the decay is now complete

| round | population | landed |
|---|---|---|
| narrowing 1 | over-strict, catches a held-out design | 7 of 47 = **15%** |
| narrowing 2 | the 28 still over-strict | 1 of 28 = **4%** |
| **narrowing 3 (this)** | **convicts 9 of 9, objects to loop 1's design** | **0 of 24 = 0%** |

The route was projected to converge near 31% of the specification and it has now
reached zero on the population that matters most. **By the pre-registered reading:
narrowing cannot reach a population that convicts nine of nine, and the structural
reading of the closure stands.**

### What this closes

All three routes to a golden-free second loop are now measured and closed:

* **selection** — 255 objectors, 0 sound, 0 passing the minority rule, minimum 4
  of 9 against a threshold of 2 (§9ai);
* **population widening** — saturates at one sound opinion by 24 designs (§9ab);
* **authoring by narrowing** — 0 of 24, with the conviction count and the
  objection measured to move together.

**So the 62-testpoint gap between the golden-free pipeline's 174 and the ceiling's
112 is structural on this corpus, and it is structural for a reason now stated
three ways rather than inferred once.**

## 9aj-bis. The stimulus closure, independently reproduced — and the sixteenth counting-shaped defect

§9p closed the stimulus question at zero opportunity. It was re-run from scratch
this session against the 169-check audit-zero criterion, per-testpoint rather than
per-check, because the goal names the stimulus loop explicitly and every earlier
measurement of it used a different unit. **It reproduces exactly.**

| design | differing | CAUGHT | **SILENT** | BLIND |
|---|---|---|---|---|
| start design L | 279 | 169 | **0** | 110 |
| **run 6 — the selected draw** | **146** | 20 | **0** | **126** |

**And the coarse golden-free upper bound is now on record beside it: decide
coverage is 348 of 348 = 100%, at a median of 67 checks per testpoint.** Not one
testpoint in the suite is dark, so there is no reach for stimulus to buy — the
`SILENT` column is zero because it cannot be anything else. The pre-registered
band was `< 5% → closed`; it is 0.0%.

**The loop spends the class it can see.** CAUGHT falls 169 → 20 while BLIND rises
110 → 126. The set's discriminating power is a finite resource the editor
consumes, and what remains is 126 testpoints it decides on and passes.

### THE SIXTEENTH COUNTING-SHAPED DEFECT, AND IT IS MINE

The first run of this scorer read the reference from `run/golden/suite/results` —
**a 318-testpoint suite** — while every graded design carries **348**. It
intersected two different suites and reported **124 differing where the published
grade is 146**, with a clean-looking split beside it.

**The tell was disagreement with a prior measurement, not the headline looking
wrong** — 124 against 146 — which is the signature all sixteen have shared. The
scorer now **refuses to print the split** unless divergence reproduces the
published grades (279 and 146). With the correct reference both pin exactly.

**Two reference trace sets exist on disk with different testpoint counts, and
nothing in either directory says which is current.** That is the reusable half of
this defect.

## 9ak. The only golden-free number that orders a loop's draws is the one the editor descended on — and its argmin is not its best design

Pre-registered in `docs/evidence/prereg/held-out-selector.md`, bands fixed before
anything was computed.

**The lever.** §9y measured the one pipeline change that improves what is
delivered: five draws of one configuration span 146 to 220, and selecting among
them by the golden-free objection count picks the best of the five. **That lever
has never been applied to the configuration that delivered 174, and it cannot be
as written** — those five draws never satisfied their criterion, running 1, 4, 8,
11 and 16 objections at rest, while the audit-0 87-check run **terminated at zero
with nine trials unspent**. A selector that reads zero for every draw picks
arbitrarily. So the question is whether an instrument the editor never saw can
break the tie.

**THE PIN, AND IT IS GREEN.** Before any held-out number was read the scorer had
to reproduce §9y's in-set counts for the same five designs. It reads **1, 4, 8,
11, 16** — exact — and the in-set Spearman comes back **+0.564**, also exact. The
draw-to-directory mapping and the decide path are the ones §9y measured, so what
follows is about the instrument rather than about the harness.

### The primary result: the corpus outside the criterion is ANTI-correlated

Held-out instrument: the 502 live corpus bodies minus the 169 in the criterion =
**353 checks, bodies resolved 353 of 353**, never shown to the editor.

| draw | in-set / 169 | **HELD OUT / 353** | grade |
|---|---|---|---|
| run 6 | 1 | **254** | **146** |
| N3 | 4 | 255 | 192 |
| replicate | 8 | **251** | 207 |
| N2 | 11 | 254 | 220 |
| N1 | 16 | 264 | 192 |

| | |
|---|---|
| Spearman(in-set, grade) | **+0.564** |
| **Spearman(HELD OUT, grade)** | **−0.368** |
| held-out spread | **251 to 264 — a range of 13 in 353** |
| the held-out rule picks | **replicate → 207**, the second-worst draw |

**By the pre-registered band this is CLOSED: < +0.2.** And the spread says why
before the correlation does. The held-out corpus objects to about **72% of
everything** whatever the design, varying by 13 checks across designs that span
**74 testpoints** of grade. It is the over-strict bulk — §9ai measured that of the
255 corpus checks objecting to a finished design, *zero* are sound — and a set
that objects to everything cannot tell designs apart.

**SO THE ORDERING SIGNAL IS MANUFACTURED BY THE OPTIMISATION, NOT HELD IN THE
CORPUS.** A check the editor descended on carries information about the design
because the editor moved the design with respect to it. A check it never saw
carries essentially none. That is the opposite of the usual held-out intuition,
and it is the reason best-of-N cannot be given an independent referee here.

**AND THE OBVIOUS NEXT IDEA IS EXCLUDED BY ITS OWN ARITHMETIC.** The natural
response is that the held-out corpus failed for being *unsound* rather than for
being *held out*, so an audit-zero set should be tried instead. The 87-check
DEDUP set scores **+0.564 and picks the best draw** — and it overlaps the
criterion at **86 of its 87 checks**. It is not an independent instrument; it is
the criterion under another name, and quoting its agreement as corroboration
would have been counting one measurement twice.

### The secondary finding: ordering improved while selection got worse

*Not pre-registered — it arose from the start-design pin and is reported as the
exploratory result it is.*

Both criteria are **audit ZERO with every check deciding** — the 169-set 0 of 169,
the 87-set 0 of 87 — so neither is sound-by-silence. The two arms' start design
was pinned from behaviour rather than asserted, because no artifact records either
init command: **the 87-check criterion reads 22 objections on `p4_L`, exactly the
DEDUP arm's recorded init.** Same start design, so the arms are comparable.

**The 169-check criterion reads ZERO on the design the 87-check loop accepted**,
which puts all six designs on one instrument:

| design | 169-set | grade | stopped |
|---|---|---|---|
| **DEDUP loop** | **0** | **174** | **TERMINATED, 9 trials unspent** |
| **run 6** | **1** | **146** | budget |
| N3 | 4 | 192 | budget |
| replicate | 8 | 207 | budget |
| N1 | 16 | 192 | budget |
| N2 | 11 | 220 | budget |

| population | Spearman | argmin picks | best available |
|---|---|---|---|
| the five budget-limited draws | +0.564 | run 6 → **146** | run 6 → 146 ✓ |
| **all six** | **+0.696** | **DEDUP → 174** | run 6 → 146 ✗ **−28** |

**ADDING ONE DESIGN RAISED THE CORRELATION BY 0.13 AND COST THE ARGMIN 28
TESTPOINTS.** Ordering and selection are different properties of the same rule,
and a rule can get better at the first while getting worse at the second. The
pre-registration anticipated the mirror case — *"a selector may order poorly and
still identify the minimum"* — and this is the other half of it.

**The mechanism is §9ah's zero arriving as a selection rule.** A design at zero
has exhausted its criterion, not demonstrated that it is the best draw: **the
design scoring ZERO grades 28 testpoints WORSE than the design scoring ONE**, on
the same audit-zero set, from the same start design. So the rule that follows is
one line and it is golden-free:

> **Select the argmin over draws with a STRICTLY POSITIVE count. A draw that
> reached zero is unselectable, not best.**

On these six that rule recovers 146 where naive argmin loses 28 testpoints.

### What this changes about the deliverable, and what it does not

**Two golden-free deliverables now exist on this corpus, and the better one is not
the terminating run:**

| | criterion | audit | how it stopped | grade |
|---|---|---|---|---|
| single terminating run | 87 checks | 0 | zero objections, 9 trials unspent | **174** |
| **best-of-5, positive-count argmin** | **169 checks** | **0** | **trial budget** | **146** |

Both read no reference in selection; the grade is calibration computed last. The
second costs five times the compute and is subject to §9t's variance caveat in
full — it is *selection over* a noisy distribution, not a tighter distribution.

**What it does not do is reach equivalence, and no part of it reopens anything.**
146 of 348 is a design differing from the reference on 42% of the suite. The
three routes to a golden-free second loop stay closed: this measures how to pick
the best member of one loop's output, not how to run a second one.

## 9al. The field's own golden-free completeness metric reads 100% on a set that leaves the design 42% wrong

The one instrument this session had not tried is the one the verification
literature actually prescribes for this question, and it is **built into this
repository and unwired**. `specflow/qualify.py` is an mcy mutation-qualification
gate, and its docstring already states the property every instrument here has
lacked:

> *"Mutate the candidate, not a golden. ... 'This mutant provably changes
> observable behaviour AND the suite still passes' convicts the SUITE, whatever
> the base design's correctness."*

That is **functional qualification** — Certitude's measure, mcy's measure,
mutation adequacy in the testing literature — and it needs no reference at all.
It is precisely what this document has been calling blindness residue: a
surviving live mutant is a concrete perturbation the set cannot see.

**Bands were fixed before the number was read:** ≥80% the set pins behaviour
tightly; 40–79% a real residue with named witnesses; <40% measurably blind with
each survivor naming a hole. The live filter is the `m02` lesson — a mutant that
changes no observable behaviour is EQUIVALENT and excluded, never counted as a
miss, and liveness is decided against the mutant's own parent with no reference
involved.

| | |
|---|---|
| mutants available | 15 |
| **EQUIVALENT, excluded** | **2** |
| live mutants | 13 |
| **the 169-check audit-zero set kills** | **13 of 13 = 100%** |
| the whole 502-body corpus kills | 13 of 13 = 100% |

**THE SET SCORES PERFECT ON THE FIELD'S GOLDEN-FREE COMPLETENESS METRIC, AND THE
DESIGN IT ACCEPTS DIFFERS FROM THE REFERENCE ON 146 OF 348 TESTPOINTS.**

### So mutation score is disqualified as a proxy, and the column that says why is in the table

The goal asks for proxy metrics *"chosen by how well they facilitate the RTL
Editor succeeding."* **Mutation score fails that test by saturation**: it reads
100% for both the 169-check set and the 502-body corpus, so it cannot even
separate those two, let alone rank a set by whether it forces correctness.

The reason is visible in how much each mutation moves: **the live mutants change
7 to 318 testpoints, median around 150 of 318.** A single-operator mutation of an
FSM this tightly coupled breaks behaviour across half the suite, so almost any
check that fires at all catches it. **The fault model is far coarser than the
residue it is being asked to measure** — the delivered design's remaining errors
sit in positions where nine independent implementations cannot agree, and no
operator substitution produces a fault of that shape.

**This reproduces the mutant leg's earlier result from the opposite side.** That
round measured checks promoted by mutants as 100% sound and 0% discriminating and
read it as a property of the promoted checks. It is a property of the
**instrument**: mechanical mutants are easy on both legs, so they neither reject a
good check nor reward a strong one.

### What follows for the gate, and it is not "wire it up"

`qualify.py` should stay a **hygiene floor, not an adequacy measure**. A set that
fails mutation qualification is certainly broken; a set that passes it has been
told nothing about whether its demands are correct. Reporting a 100% mutation
score beside a design wrong on 42% of the suite would be the most defensible-looking
number this document could publish and among the least informative.

**And it answers the standing methodological question — can a proxy be validated
before equivalence is chased — with a worked negative.** Mutation score is
golden-free, cheap, standard, and measured here to be saturated. Validating it
first cost one afternoon of compute and would have cost an editor run and a false
conclusion otherwise.

**Scope.** These are mutants of one spec-derived design, not of the delivered one,
so this measures the set's sensitivity to perturbations of that parent. The
saturation conclusion does not depend on the parent — 13 of 13 with a median
mutation moving 150 testpoints is coarse whatever it is mutating — but a kill rate
against mutants of the delivered design has not been run.

## 9am. The halting point EXISTS — and narrowing depth does not track the conviction count

Pre-registered in `docs/evidence/prereg/closed-loop-narrowing.md`. Sixteen
over-strict checks, each asked for a **ladder of five progressively narrower
variants** instead of one blind rewrite. Integrity: **16 of 16 returned, 80 rungs,
every rung parses and defines `decide()`, none identical to its original or to a
sibling, 0 duplicate bodies across checks.** Six originals read a probe and
**none was de-probed**, so the 12-of-12 hazard did not fire.

| | |
|---|---|
| checks with at least one LANDING rung | **1 of 16** |
| **and the audit, read last** | **SOUND — an AUTHORED both-cell check** |

**THAT IS THE FIRST ADEQUATE CHECK THIS PROJECT HAS AUTHORED.** Seven rounds —
two-sided authoring, the strength round, three narrowing rounds, two repair
rounds — produced none. By the pre-registered band 1 of 16 reads *"rare; record
the rate and build nothing"*, and that is honoured. But the *shape* of the
sixteen ladders is worth more than the count.

### The landing rung is at depth 3, and depths 1, 2, 4 and 5 all fail

    check        h0   rung 1  rung 2  rung 3  rung 4  rung 5
      REQ-0002    9     9*      9*    **2***    9*      9*     <= LANDS
      REQ-0010    7     5x      4x      0x      0x      9*
      REQ-0013    5     7*      7*      7*      5x      0x

*(`*` = still objects to the delivered design; `x` = vacuous on it, a LOSS.)*

**THE CONVICTION COUNT IS NOT MONOTONE IN NARROWING DEPTH.** REQ-0002 goes
9, 9, **2**, 9, 9 — it passes through the target and comes back out. REQ-0010
descends 5, 4, 0, 0 and then jumps to 9. REQ-0013 **rises** from 5 to 7 under
narrowing, so removing an obligation made it convict *more* implementations.

**This is why one blind step found nothing.** Narrowing rounds 1–3 took a single
rewrite per check and measured where it landed. If `h` is non-monotone in depth,
one step samples one point of a bumpy landscape, and the landing band is narrow.
**0 of 24 is what that procedure should be expected to return even when a halting
point exists** — and here one demonstrably does.

### The other two shapes, and they are the coupling

Of the fifteen that did not land: **six never moved at all** — `h` identical
across all five depths, every rung still objecting. The rest **collapse to zero
and go vacuous in the same step**, which is §9aj's conviction-and-objection-fall-
together reproduced across five depths instead of one.

**So the narrowing decay of 15% → 4% → 0% is re-read, not retracted.** It
measures a one-sample-per-check procedure on a non-monotone landscape. The
landscape has at least one reachable point; the procedure was not built to find
it.

## 9an. The minority rule's precision does NOT survive the full corpus

The full six-gate conjunction — compile ∧ fires-on-witness ∧ ¬vacuous ∧
`h(c) ≤ 2` ∧ discriminating — applied as a **selection** rule over all 502 live
bodies. Zero model calls.

| | |
|---|---|
| scanned | 502 |
| **kept** | **38** over 23 requirements = 26% of the specification |
| rejected by first failing gate | sound 248, discriminating 137, compile 34, fires 6 |
| **survivors convicting the reference** | **13 of 38 = 34%** |

**AND THE SPLIT IS PERFECT, WHICH IS WHAT MAKES IT DIAGNOSTIC:**

| | unsound |
|---|---|
| the 25 survivors already in the 169-check set | **0 of 25** |
| **the 13 the conjunction ADDED** | **13 of 13** |

**EVERY CHECK THE FULLER BATTERY CONTRIBUTED IS UNSOUND, AND EVERY CHECK IT KEPT
FROM THE EXISTING SELECTION IS SOUND.** The five extra gates added nothing to
soundness; the only soundness signal in the conjunction is the minority rule, and
on this population it is **66% precise, not ~100%**.

### That corrects a figure quoted throughout this document

This scorecard reports the rule at **59 of 59** and **7 of 7** — perfect
precision. That was measured at **t = 2 of THIRTEEN designs on a 259-body
corpus**. Here it is **t = 2 of NINE on 502 bodies**, and it reads 66%.

Two candidate causes, and this measurement cannot separate them: the threshold is
looser relative to the population (2 of 9 is 22% where 2 of 13 is 15%), and the
corpus is nearly twice the size with a different composition. **What is
established is the negative — the perfect-precision figure does not transfer to
this population, and every use of "~100% precise" in this document should carry
its `(t, N, corpus)` or not be quoted.**

### What it says about gating the selection regime

It answers the question directly and unfavourably: **on this corpus the extra
gates do not find checks the minority-rule selection missed.** The 169-check
audit-zero set remains the better artifact — same span class, audit 0 against the
conjunction's 34%. The gates did not break anything, they simply had nothing to
add at selection time.

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

**AUTHORING IS OFF THAT CURVE AND IS NOT A WAY AROUND THE TRADE — §9c.** A
hole is named without any reference, and six checks written at named holes moved
blindness 56.9% → 55.1% at an audit of zero, closed 102 cells, produced the
best-driven design measured here, and two of them convict the design the base set
itself stopped on. Selection cannot do that at any price, and that claim stands.
But 76 further calls closed **zero** cells soundly, and across all 76 the checks
that close hundreds of cells convict the whole population (638 cells against 74,
Spearman +0.350). **So authoring escapes the corpus, not the anti-correlation** —
the residue is reachable in principle and expensive in practice, at a projected
250–3,600 calls with the accept rate falling.

**No run reached equivalence — SIX now, and the residue is named.** Six graded
runs, one held-out start design, six `DIFFERS`, best 146 of 348. **The goal's
terminal condition is not met.** What has changed is that the reason is no longer
a candidate list:

| aimed at the blindness residue | result |
|---|---|
| selection over 594 corpus bodies | 296 hole-closers, **0 sound** |
| authoring at named holes (76 checks) | cover 100% of the residue, **0** cells closed soundly, 95 of 95 sound attempts convict the reference |
| narrowing the 30 largest closers | **0 of 30** |
| the stimulus loop (20 new testpoints) | 1 of 20 caught; new routes **84.5%** blind against 55.1% |
| **the disagreement report (§9i)** | **NAMED cells 53 → 54 of 60 — worse.** The run's whole 5-testpoint gain is in the group the report says nothing about |

**Five levers, all closed by measurement rather than by a budget running out.**

### What a golden-free pipeline can actually report, validated

This is the goal's last clause, and it is the part that survives:

1. **Set blindness**, from **four or more** spec-derived designs — it saturates
   there (§9b). Two designs can read 0.0% on a set that is 42.9% blind, and a
   design your own checks accepted is worth about 12 points of over-estimate.
   **And it must be STRATIFIED BY PORT WIDTH or not quoted (§9v):** against the
   reference-based instrument it agrees at +0.714 over the seven one-bit ports
   and at +0.200 over all ten, because on a 32-bit port two spec-derived designs
   differ almost everywhere and the denominator explodes. 41% of the set's blind
   cells sit on the three multi-bit ports, where the instrument inverts — the
   widest port is worst of ten golden-free and second best against the reference.
   Every blindness figure in §§8–9 is over mixed widths.
2. **The minority rule** — keep a check convicting ≤ t of the population — is the
   only golden-free selection knob measured to work: **95 of 95** agreement with
   the audit on its reject side. **But its ACCEPT side is dominated by silence
   (§9z):** a check convicting *none* of the population passes "convicts ≤ t"
   trivially, and 96 of 149 checks never object on any of fifteen spec-derived
   designs. The reject-side precision is unaffected; the accept side must be
   paired with an ever-objects filter or it selects for mute checks.
3. **A two-point warning, held out across two independent editor runs (§9j).** A
   testpoint no two spec-derived designs disagree on carries a design that is
   right there (**1%**, both runs); a testpoint whose every disagreement is
   unadjudicated carries one that is wrong there (**86%** and **87%**). The
   monotone four-class ranking that stood this morning **does not survive out of
   sample and is withdrawn**.

**What it cannot do, and both are measured rather than assumed.** It cannot
adjudicate a blind cell by the population's vote — that swings from **6% to 100%
between two ports at the same margin** (§9h). And it cannot resolve one by
handing the disagreement to a spec-reading editor: given all 60, an editor
concluded 59 of 60 already satisfied the requirement text and was **wrong at 54
of them**, with 16 trials unspent (§9i).

**So the obstruction is located outside the pipeline.** A check that closes a
blind cell convicts the reference, 95 times out of 95; a reader asked what the
specification requires there reproduces the population's answer whether or not a
design is in front of them. **The specification underdetermines those cells and
the misreading is what it produces in a competent reader** — so completeness is
not reachable by any instrument built from the specification plus a reader, and
the missing input is a decision on those cells from outside that loop.

**AND THE OBSTRUCTION IS NOT UPSTREAM EITHER, WHICH WAS THE LAST PLACE IT COULD
HAVE BEEN — §9r.** Everything above sits downstream of S1's 89 extracted
requirements, so a specification whose extraction missed the divergent ports
would have made re-extraction a live lever. It did not miss them: **every declared
output is declared by 3 to 16 requirements and read by 17 to 51 checks**, so no
port is dark and the lever has no target. What predicts a port's divergence is
how ACTIVE it is on the reference, and check count is very nearly a restatement
of activity — **Spearman +0.857 against the reference's transitions**, and once
activity is held fixed the check correlation goes negative on four designs of
five. **Coverage follows difficulty; it does not overcome it.**

**AND THE SET IS A THIRD THE SIZE ITS CHECK COUNT SUGGESTS, WHICH CORRECTS THE
SPAN QUOTED THROUGHOUT — §9z.** 149 live checks hold 77 distinct verdict vectors;
72 are exact duplicates and one vector is shared by 21 checks. Re-decided against
the six graded designs as well — fifteen spec-derived designs, no reference — 12
of 108 population-mute checks wake up and **96 never object on any of them**. The
effective set is **53 checks over 43 requirements = 48% of the specification**,
against the **78%** this document has been quoting. And the minority rule keeps a
check convicting none of the population by construction, so its accept side is
dominated by silence. What it does NOT say is that the 96 are useless — three
checks that caught a held-out design convict none of the thirteen candidates.

**AND THE VARIANCE HAS A GOLDEN-FREE ANSWER, WHICH IS THE ONE PIPELINE CHANGE
THIS SESSION FOUND THAT IMPROVES WHAT IS DELIVERED — §9y.** Five draws of one
configuration span 146 to 220 testpoints, sd 28 — within a point of the sd across
seven independently *written* designs, so re-running the loop is about as noisy as
re-writing the module. **Selecting among them by the golden-free count picks the
best of the five: 0 of 5 draws beat it, and it is 45 testpoints better than an
average draw.** The ordering behind that is only partial (+0.564; one draw scores
four times worse on the checks for an identical grade), so it is a **selector of a
clear minimum, not a ranking** — and it buys the best member of a bad
distribution rather than moving the distribution. **It does not reach
equivalence.**

**AND ONE GRADED RUN IS NOT A MEASUREMENT, WHICH UNDERCUTS SEVERAL OF THE ABOVE
— §9t.** Every graded run here is n = 1. A pre-registered replicate of run 6's
configuration — byte-identical start design and brief, same budget, differing only
in the session — landed **61 testpoints away**: 146 against 207. That is the worst
of the three bands fixed in advance, and its consequence is applied rather than
argued. **The trials-versus-grade correlation of +1.000 is withdrawn**; no two
graded runs differing by less than ~60 testpoints may be read as differing for a
reason; §9w's headline becomes *in one of two runs*; §9x's placement drops to 3 of
6. **What survives is every claim resting on a COUNT over a fixed population
rather than a SPREAD between runs** — the audit, §9q's corpus closure, §9r's
extraction closure, and §9u/§9v's per-port tables. The variance of this loop is
comparable to the entire effect this document has been measuring.

**AND THE PROCEDURE IS WRITTEN DOWN AT LAST, WITH THE THING IT CANNOT DO — §9x.**
Six steps, each with its measured worth, and a seventh that is the only verdict a
reference-free pipeline can pass on a finished design: where it sits relative to
the population that selected its checks. **That placement agrees with the
reference on 3 of 5 designs and both errors are optimistic** — one design the
checks call better than any independent draw is merely typical, one they call
typical is worse than every member of the population. So the instrument can say
*outside the population* and cannot reliably say *on the good side*, which makes
it a trigger for a human look and never a clean bill.

**AND THE LOOP IS WORTH RUNNING ABOUT HALF THE TIME, WHICH IS THE ONE POSITIVE
THIS DOCUMENT CAN STATE ABOUT ITS OWN PRODUCT — §9w, AS AMENDED BY §9t.** Seven designs written from this
specification by independent authors span 151 to 230 differing testpoints, mean
185, sd 23. The start design of every graded run is a bad draw at 279, and the
best run drove it to **146 — better than all seven**. **The replicate of that same
run landed at 207, inside the population's range**, so the loop beats one-shot
generation in one of two attempts. **It still does not reach equivalence, and all
three halves have to be said together.** The other three graded runs land at 214, 221 and 271, inside or above
the population's own range, and did not improve on one-shot generation at all.

**AND THE LOOP DOES NOT WANT MORE ROOM — §9s.** Four graded runs shared a
21-trial budget and none reached it; each stopped voluntarily with 6 to 16 trials
unspent, and all four stopped on a trial *worse* than their own best. So the
cheapest remaining lever — give the editor more budget — is closed by counters
already on disk. **And the latch is where the added proxy did its damage:** it
keeps whichever trial has the most passing entries, so 160 proxy units published
beside 169 checks hold 160 votes — and in the worst of the four runs they
rejected the state with the fewest check objections, 5 check votes lost against
48 proxy votes gained. A proxy may inform an editor and must not enter the
criterion that decides which design is kept.

**Scope.** One design, one corpus of 594 bodies, one population of nine. Every
figure names its denominator. Nothing here is claimed for i2c, which remains
unmeasured because no i2c run retains traces.
