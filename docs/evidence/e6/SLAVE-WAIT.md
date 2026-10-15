# The `slave_wait` convictions, in detail -- and my earlier account was wrong

RESIDUE.md filed REQ-0053 and REQ-0055 under "`slave_wait` EXTENT
under-determination: the sentence admits a level and an event". **That was
wrong twice**, and both errors came from measuring something the check does not
do.

## Error 1: the sentence is NOT ambiguous

The specification span, preserved verbatim in the probe entry:

    `slave_wait` is asserted when the master has JUST RELEASED SCL high
    through `scl_oen`, but the filtered SCL input `sSCL` remains low.

"has just released" is an EVENT. The sentence does not admit a level reading.

S1 dropped the word when minting: REQ-0053 says "when it has released SCL high"
and REQ-0115 "when scl_oen releases SCL high". `normalize` recovered it for
REQ-0053 -- its activation reads "the master has just released SCL" -- and did
NOT for REQ-0115. And REQ-0053's check body is faithful to the event:
`released = edges(trace, "scl_oen", "rise")`. So the word was lost and then
recovered, and the check is right about it.

## Error 2: I measured the level, and the check uses the rise

The "254 of 1950" figure counted rows where `scl_oen == 1 and sscl == 0` -- the
LEVEL. The check activates on a RISE of `scl_oen`. The two populations of rows
are not the same and the figure says nothing about this check.

## What actually convicts golden: REQ-0053

Golden, TP-0206, transactional view -- the window opens at edge 30, the LAST
state in the trace:

     edge ena scl_i | scl_oen  sscl  slave_wait  clk_en
       27   1     0 |       0     0           1       1
       28   1     0 |       0     0           1       1
       30   1     0 |       1     0           1       1   <-- window opens

**`slave_wait` is already 1 at the activation row, and has been since edge 27.**
The check is

    eventually(window, slave_wait == 1, strong=True, after_activation=True)

`after_activation=True` reads `body` -- the window WITHOUT its activation row --
so the response that is already true does not count. Edge 30 is the last state,
so `body` is empty. `strong=True` then turns "ran out of trace" into a
conviction rather than an abstention.

**This is the hazard `temporal.py` documents, on the two flags, verbatim:**

    On a requirement describing a STATE rather than an event -- "is high while
    X", "remains released" -- a correct design may hold the value from before
    the activation and never change it, and it may still be holding it when the
    trace ends. `strong=True` then convicts the design for the trace being
    short, and `after_activation=True` asks for a change the requirement never
    demanded. Neither flag is a default to reach for.

`slave_wait` "is asserted when..." is a state. Both flags are set. Both are
wrong for it, and the module says so where the operator is defined.

So REQ-0053 is **our defect, not a specification ambiguity and not a probe
problem** -- the same class as `throughout` over a `TO_END` window: a check that
convicts on a technicality of window shape.

## REQ-0055 and REQ-0058 do not discriminate at all

Measured against real golden traces and the population-shaped candidate
separately:

    REQ-0053   GOLDEN FAIL (TP-0206 edge 30)   CANDIDATE pass
    REQ-0055   GOLDEN FAIL (TP-0017 edge 7)    CANDIDATE FAIL (TP-0017 edge 19)
    REQ-0058   GOLDEN FAIL (TP-0011 edge 5)    CANDIDATE FAIL (TP-0088 edge 37)

**REQ-0055 and REQ-0058 fail on BOTH designs.** They are not rewarding a move
away from correct behaviour; they are simply failing checks that also happen to
convict golden. They entered the "passes here and fails on golden" list only
after editor A repaired them on its own design.

On REQ-0055, golden holds `clk_en` HIGH throughout the slave-wait window --
edges 6,7,8,9,10 all read 1 -- where REQ-0051 says "keep clk_en low while
slave_wait is asserted". Either golden violates that, which is implausible for
the reference, or golden's `clk_en` names the UNGATED prescaler tick while the
requirement means the gated one. That would be a third probe-meaning mismatch:
same name, same width, different quantity -- and the width guard cannot see it.
**Not established. Recorded as the next thing to measure.**

## The residue, reclassified

    cause                                       checks                       class
    probe PHASE                                 REQ-0066 0067 0110 0111 0112  ours
    downstream of phase                         REQ-0035                      ours
    `throughout` over TO_END                    REQ-0034                      ours (gated)
    both-flags hazard on a state requirement    REQ-0053                      ours
    fails on both designs, cause open           REQ-0055 REQ-0058             open

**Nine of ten are now defects of this pipeline rather than ambiguities of the
specification.** The earlier claim that two were irreducible specification
under-determination does not survive reading the span.
