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
13 at trial 12 and stopped at 19. **Zero of four stopped at their best.** The
ratchet on the accepted design is what preserved every grade in §9 — without it
each run would have shipped a design worse than one it had already found, and
nothing in the loop's own reading tells it which trial was its best.

### The oscillation is between a quarter and a half of all trials

Up-moves on the criterion's own count: 1 of 4, 3 of 11, 7 of 13, 4 of 14. Run 8's
sequence is the plainest — 21, 39, 21, 34, 33, 16, 22, 28, 14, 15, 23, 13, 13,
**19** — six reversals of two or more, ending above where it stood two trials
earlier. Run 9's proxy units churn the same way: its 160 majority units read 91,
101, 90, 42, 90, 42, 53, 42, 48, 42 across fifteen trials, traded back and forth
without converging.

### Trials spent and the grade are perfectly rank-ordered, and the confound is not separable

**Spearman +1.000 on n = 4**: 5 trials → 146 testpoints, 12 → 214, 14 → 221,
15 → 271, against a start design at 279. But **the criterion determines how much
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
2. **The minority rule** — keep a check convicting ≤ t of the population — is the
   only golden-free selection knob measured to work: **95 of 95** agreement with
   the audit on its reject side.
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

**AND THE LOOP DOES NOT WANT MORE ROOM — §9s.** Four graded runs shared a
21-trial budget and none reached it; each stopped voluntarily with 6 to 16 trials
unspent, and all four stopped on a trial *worse* than their own best. So the
cheapest remaining lever — give the editor more budget — is closed by counters
already on disk, and the ratchet on the accepted design is what preserved every
grade quoted here.

**Scope.** One design, one corpus of 594 bodies, one population of nine. Every
figure names its denominator. Nothing here is claimed for i2c, which remains
unmeasured because no i2c run retains traces.
