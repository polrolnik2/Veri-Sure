# Two defects, both design-independent, and two of my own claims retracted

The goal is span > 90%, blindness < 10%, audit = 0, reproducibly. Three
completed runs sat at blindness 5.7% / 14.6% / 24.5% with audit 0 / 0 / 1, and
`CEILING.md` had concluded the residue was a property of the corpus a run
happens to draw. That conclusion was wrong twice over.

## 1. An invariant was asserted over the row that ENDED its window

`after` appends a row and *then* tests it for the close, so `Window.rows` ends
on the first row at which the window's scope has already ended. `throughout`,
`stable` and `never` all read `rows`. "While A, B holds" was asking B to hold
at the row where A stopped.

**The proof needs no design, no population and no reference.** Assert a
window's own defining condition:

    trace  p = 1 0 0 0 1 1 0 1
    after(trace, p == 0, until=WHILE_ACTIVE)  ->  rows [1, 2, 3, 4]
    throughout(w, p == 0)                     ->  (False, 4, ...)

A check asserting exactly what its window is defined by cannot be wrong about
any design -- its verdict does not depend on what the design did -- so that
FALSE is the operator's error. One run had frozen that check verbatim:
REQ-0044's body is `after(sda_oen == 0, until=WHILE_ACTIVE)` then
`throughout(sda_oen == 0)`, failing **168 of the 168 testpoints it decided**
against the known-good control. REQ-0005 failed **299 of 299** on the same
shape with a predicate release.

`Window.extent` is the rows without the boundary. The invariants read it; the
existentials keep reading `rows`, and the asymmetry is LTL's -- in `A U B` the
antecedent is not required where B holds, but B is required to hold somewhere,
and the closing row is exactly where it may land.

**Nothing in 2570 tests pinned which rows an invariant holds over**, so the
semantics could be read either way and the reading that can only convict was
the one in the code.

## 2. The refutation guard was in the wrong place -- twice

`_choose_bodies` prefers a body the spec-derived population does not
unanimously convict. It applied that as a TIER -- `spared or per_req[uid]` --
so a refuted body lost to ANY body the population spares, whatever either one
separated. On run 3 that was 53% of the corpus and fifteen points of blindness.

The tier existed to answer an over-strictness symptom. Defect 1 was the cause.
So I removed the tier -- and put the term BELOW marginal separation, which is
too far. REQ-0001 then froze a body convicting all seven spec-derived designs
and the control:

    body  separates  refuted
      #0      18242    yes
      #1       5525    yes    <- chosen with refutation below separation
      #2      10711    yes
      #3          0    no
      #4      15626    yes
      #5       2601    no     <- chosen with refutation above it

**A refuted check closes cells BY convicting**, so the more over-strict the
body, the more it "separates" -- and a key reading separation before
refutation reads over-strictness as reach. It belongs where this tree already
moved the dissent guard: **separation first, then the guards, then more
separation.**

    placement    run 1    run 2    run 3
    tier          6.5%    9.91%   24.41%
    guard            *    7.91%    9.23%
    below it      1.4%    6.13%    9.17%

The guard gives up six hundredths of a point on run 3 against the most
permissive placement and buys back the fifteen the tier was costing.

## What I published that was wrong

**"These describe OPEN-DRAIN BUS SEMANTICS ... the checks over-claim."**
`CEILING.md` diagnosed four convicting checks by reading the requirement TEXT.
Three of the four assert only on real module outputs. The defect was in
`throughout`. The remedy that paragraph proposed -- removing a class of checks
written for text stating no module-boundary obligation -- would have been aimed
at a symptom.

**"Refutation as a tie-break below separation."** Chosen because it minimised
blindness, which optimises one leg of a three-legged target. REQ-0001 is what
that costs.

## The triple, all three corpora, post-fix

    corpus   placement   span    blindness   audit
    run 1    tier       99.1%         6.5%    0/15
    run 1    none       99.1%         1.4%    1/14
    run 2    tier       97.4%         9.9%    0/14
    run 2    none       97.4%         6.1%    0/13
    run 3    tier       98.2%        24.4%    0/13
    run 3    none       98.2%         9.2%    0/14

Before the operator fix, run 3 read audit 1/14 at the tier and 1/11 without it,
and `CEILING.md` reported 23.3% as a floor no rule could pass.

## The three corpora are a LOWER BOUND, not a prediction

Runs 1-3 were **authored and repaired against the buggy operator semantics**
and are re-scored here under the fixed ones. Every repair round those runs
spent, every body the liveness and refutation legs pushed the author to
relax, and every `_inert_where_it_should_decide` note they raised, was
computed from verdicts an off-by-one had already corrupted. A corpus authored
under correct semantics is a different corpus.

So the table above says what the FIX is worth on fixed inputs. It does not say
what the pipeline now produces, and only a fresh end-to-end run can.

## What still convicts, and it is one testpoint

Under the shipped placement, run 1 reads audit 1/14 on **REQ-0095**, "The READ
command ends with cmd_ack", failing **1 of 59** testpoints:

    e 4  cmd=8 ena=1  cmd_ack=1    <- the window opens here
    e 5  cmd=0 ena=1  cmd_ack=0

**The control acknowledged the command on the same edge it accepted it.** The
check cannot see that, for two reasons that compose:

  * `after` never tests `until` at the activation row -- deliberately, so that
    "after A, until B" does not collapse when A and B can hold together;
  * `after_activation=True` excludes that same row from the consequent search.

So the release happened, at the activation, and both halves of the check look
past it. The requirement states no cycle count, and `after_activation=True` is
a claim that the effect cannot be simultaneous with the trigger -- a
positional claim. `positional_claims()` screens `nexttime(`, `trace[i + 1]`,
`rows[j + 1]` and `next_row` for exactly this and does NOT screen
`after_activation=True`, though `eventually`'s own docstring calls it "`|=>`
against `|->`".

Recorded as the next candidate, not fixed here: it is an authoring-licence
question rather than an operator bug, and a corpus authored under the fixed
operators may not produce the shape at all.
