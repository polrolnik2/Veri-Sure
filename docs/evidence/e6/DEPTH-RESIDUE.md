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
