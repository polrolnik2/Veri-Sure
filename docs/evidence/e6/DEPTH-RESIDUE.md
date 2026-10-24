# Every conviction at 241 bodies, decomposed

`FRONTIER.md` met span and blindness together and left the audit column
undiagnosed above 122 bodies. This is that diagnosis. At 241 bodies -- the knee,
where blindness first clears 10% -- **eight bodies over seven requirements convict
golden**, six of them behavioural, which is the `6/44` the scorecard reports.

    body          kind          origin    where              cause
    REQ-0051#1    behavioural   corpus    TP-0004 edge 6/7   DEGENERATE STIMULUS
    REQ-0055      behavioural   accepted  TP-0004 edge 7     normalize's observable
    REQ-0055#1    behavioural   corpus    TP-0004 edge 7     same, and SPARED by the
                                                             corrected licence rule
    REQ-0058      scaffolding   accepted  TP-0000 edge 25    hand-rolled window
    REQ-0064#1    behavioural   corpus    TP-0000 edge 7     hand-rolled window
    REQ-0109#1    behavioural   corpus    TP-0000 edge 8     hand-rolled window
    REQ-0116#1    behavioural   corpus    TP-0000 edge 7/8   a DEFINITION checked as
                                                             an obligation
    REQ-0118#1    behavioural   corpus    TP-0091 edge 12    strong existential, the
                                                             response never arrived

## REQ-0051 is the degenerate-stimulus finding, confirmed

    requirement  "The bit-level controller shall hold its timing counter and keep
                  clk_en LOW while slave_wait is asserted."
    TP-0004      drives clk_cnt = 0
    golden       clk_en = 1 on every row of the trace, both slave_wait rows included

`clk_cnt = 0` is divide-by-one: there is no counter to hold and `clk_en` is high
every cycle **by design**. `DEGENERATE-STIMULUS.md` already recorded the scale --
342 of 422 testpoints drive `clk_cnt == 0` and golden's `clk_en` is 100% high
there -- and this is that finding arriving as a conviction.

**So it is a STIMULUS defect: not the check's, not the design's.** The check is a
faithful reading; the scenario it needs was never driven. Fixing it means driving
`clk_cnt > 0`, which is the stimulus stage and a model call.

## REQ-0116 is a definition given an obligation's check

    "An asserted slave_wait signal INDICATES that a slave or another bus
     participant is holding SCL low."

A sentence saying what a signal MEANS is not a sentence saying what the design
must DO. `OBSERVABLE-LICENCE.md` measures the same class on a different field --
"A definition has no effect to follow anything ... it is a default" -- and this is
the shape reaching the audit column directly.

## What the corrected licence rule did, and did not, do

`--licence-existential-only` corrects a real defect in the rule's sign: demoting
`after_activation` True -> False relaxes an existential and TIGHTENS an invariant,
because the two families read `body`/`rows` and `governed`/`extent` respectively.
The correction is derived from the module's semantics, applies to 21 bodies of
which 16 convict nothing, and reads no audit column.

**AND IT BUYS EXACTLY NOTHING HERE.** Measured at every depth:

    bodies   blindness (flat)   blindness (corrected)   audit (both)
       122   0.1416             0.1500                  1/40  = 0.0250
       241   0.0518             0.0598                  6/44  = 0.1364
       349   0.0513             0.0526                  8/47  = 0.1702
       476   0.0477             0.0477                 11/50  = 0.2200

Identical audit at every depth, and blindness slightly WORSE -- excluding a row
means fewer decisions and so fewer separations.

I predicted it would remove four convictions. It removes none, and the reason is
worth more than the prediction was: **REQ-0051#1 and REQ-0116#1 convict either
way.** With the activation row excluded they fail at the row after it instead.

    REQ-0051#1   as authored (True)  FAIL at edge 7, window opened at 6
                 demoted to False    FAIL at edge 6
    REQ-0116#1   as authored (True)  FAIL at edge 8, window opened at 7
                 demoted to False    FAIL at edge 7

Those are genuine disagreements about the requirement across the whole window, not
boundary artifacts. Only `REQ-0055#1` behaves as predicted -- it abstains with
`True` -- and its requirement still convicts through the ACCEPTED body, which
computes both readings and keeps whichever fails (`LAST-CONVICTION.md`).

So the sign fix ships on correctness grounds and must not be advertised as an
audit lever.

## Which causes are reachable from stored artifacts, and which are not

    cause                              bodies   reachable offline?
    hand-rolled window                      3   YES -- refuse at admission; census
                                                29 of 241, 26 convicting nothing
    normalize's wrong observable            2   NO  -- normalize re-run, model call
    degenerate stimulus                     1   NO  -- stimulus stage, model call
    definition checked as obligation        1   NO  -- S1/normalize, model call
    strong existential unmet                1   not diagnosed further

**One of five causes is reachable without the gateway**, and it accounts for 3 of
the 8 convicting bodies (2 behavioural, since `REQ-0058` is `scaffolding`). The
other four are defects in stages upstream of anything a frozen artifact can
express.

So `audit = 0` is not reachable offline on this corpus, and that is now a
decomposition rather than an assertion: every conviction has a named cause, and
four of the five causes live in a stage that cannot be re-run without model access.

## The one offline lever, applied -- and the decomposition's prediction held

`--no-hand-rolled` refuses a body that builds its own window, at admission:

    bodies   span            blindness       audit           (without the refusal)
       122   0.9737 MET      0.1500          1/40 = 0.0250   1/40 = 0.0250
       235   0.9737 MET      0.0595 MET      4/43 = 0.0930   6/44 = 0.1364
    ** 333   0.9737 MET      0.0526 MET      4/45 = 0.0889   8/47 = 0.1702 **
       441   0.9737 MET      0.0477 MET      7/48 = 0.1458  11/50 = 0.2200

**AUDIT HALVES AT +2 BODIES AND BLINDNESS DOES NOT MOVE** -- 0.0526 to four places
either way. Besides the phase rule, this is the only lever measured on this branch
that improves the audit column at no cost to the other two.

    best joint configuration measured
      333 bodies, licence rule (existentials only), phase rule,
      hand-rolled bodies refused at admission

      SPAN       0.9737   MET
      BLINDNESS  0.0526   MET
      AUDIT      4/45 = 0.0889   NOT MET

## The decomposition's prediction, checked

Re-run at that exact configuration, 9 bodies convict over FOUR counted
requirements -- and they are precisely the four the decomposition attributed to
upstream stages:

    REQ-0051 (#1, #2)              degenerate stimulus
    REQ-0055 (accepted, #1, #2)    normalize's observable
    REQ-0116#1                     definition checked as an obligation
    REQ-0118 (#1, #2)              see below
    REQ-0058 (accepted)            hand-rolled -- but `scaffolding`, so uncounted

`REQ-0064` and `REQ-0109`, the two hand-rolled CORPUS bodies, are gone. `REQ-0058`
survives because it is the ACCEPTED body and the refusal applies at admission only
-- a deliberate choice, since dropping an accepted body with no replacement costs
its requirement's span outright.

The censuses corroborate at the larger pool: `reads-over-width` 82 of 333 bodies
with **0 convicting**, which is the width guard working at scale, and
`TO_END-invariant` 3 with 0.

## REQ-0118 is the probe-width problem wearing a different face

    requirement  "When the module has released SCL high and the EXTERNAL SCL LINE
                  FALLS, the module shall synchronise..."
    TP-0091      36 edges; the window opens at edge 12 with 23 rows after it
    golden       scl_sync = 0 on EVERY row; scl_oen released throughout;
                 scl_i dips low for exactly ONE edge at 12, and again at 15

**Those are glitches, and golden's three-sample majority filter is right to reject
them** -- which is what REQ-0064 says the filter is for. The check reads the RAW
`scl_i` where the requirement means the FILTERED line.

And the filtered line is not readable: `fscl` is one of the six probes the width
guard refuses, declared 1 bit against a 3-bit register. So the signal the
requirement is about is unavailable, the author read the raw input instead, and the
raw input glitches. The cause is the probe stage minting `fscl` at width 1 --
upstream, and `probes.py` already records it: "the stage minted `fscl`, `fsda` and
`filter_cnt` at width 1, beside its own `spans` quoting those very phrases".

A truncation hypothesis was tried first and is refuted: the window has 23 rows
after it and the trace is 36 edges, against a median of 33 and a minimum of 20
across all 482 testpoints.

## So all four counted convictions are attributed to a stage

    REQ-0051   stimulus stage      clk_cnt = 0 on the testpoint; the obligation
                                   is unobservable under divide-by-one
    REQ-0055   normalize           observable: ['cmd_ack'] for "timing counter"
    REQ-0116   S1 / normalize      a definition given an obligation's check
    REQ-0118   probe stage         `fscl` minted at width 1, so the filtered line
                                   the requirement is about cannot be read

**None of the four is a defect in a check, in the design, or in any gate.** Each
is a defect in a stage that produced the inputs a check was authored against, and
none of those stages can be re-run without model access.

## CORRECTION: `audit = 0` IS reachable from stored artifacts, alone

The sentence above was wrong and `FRONTIER.md` has the measurement. A
population-only `placement >= 0.05` filter on the accepted set drops 29 of 122
objectors and **not one survivor convicts golden: 0 of 29**.

What is not reachable is `audit = 0` TOGETHER WITH the other two. The filter costs
span 0.9737 -> 0.7456 and blindness 0.1500 -> 0.2296, because at that depth a
dropped objector is a requirement's only body; a best-placed floor restores span
exactly and hands the audit column back with it, flooring 29 requirements of the
29 the filter emptied.

The four stage defects are why the filter has to be so aggressive: they are the
convictions it has to reach past. Fixing them upstream is what would let a gentler
filter -- or none -- reach the same audit column while span and blindness hold.
That is the claim the evidence supports, and it is narrower than the one this
document made.
