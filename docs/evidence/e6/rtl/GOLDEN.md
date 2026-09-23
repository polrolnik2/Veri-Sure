# The testbench improved and the design got worse

`e6_golden_diff.py` runs the same rendered suite with golden as the DUT, then
with each candidate, and counts where the recordings differ. Golden is RUN and
never read.

## The measurement

    design                  testpoints   cells differing        DEFECT   slack   row delta
    candidate-start.v        413 / 422   19034 / 147608 12.89%   17385    1649        1684
    rtldbg3-final.v          413 / 422   26989 / 147608 18.28%   24151    2838        2661

Over the same repair, the check set went **84 -> 93 passing** and failing
testpoints **215 -> 29**.

**Defect cells rose 39%.** Nine more checks satisfied; a design measurably
further from the reference on the ports the specification pins.

## It is ONE structural change, and the breakdown says which

    port        before    after     delta
    scl_oen       2441     6038    +3597   (2.5x)
    sda_oen       1155     4209    +3054   (3.6x)
    cmd_ack        548      956     +408
    busy           831      879      +48
    al             577      354     -223
    dout         11833    11715     -118
    scl_o            0        0        0
    sda_o            0        0        0

**`scl_oen` and `sda_oen` carry 6651 of the +6766 -- 98% of the increase.**
Those are the two I2C bus output-enables, the bit controller's core timing
signals, and they are what most of the check set is about.

    onset   diverges EARLIER in 189 of 413 testpoints, later in 20, same in 204
            median onset edge 8 -> 6
    reach   0 testpoints newly carry a defect; 0 stopped carrying one

**Nothing new broke anywhere new.** The same 413 testpoints fail before and
after. What changed is that each one leaves golden SOONER and stays wrong
LONGER -- the signature of a phase or timing change in the drive-enable
sequencing, not of scattered damage. One mechanism, billed across thousands of
cells, which is why the total on its own could not tell the two apart.

## And the data path was never touched

`dout` is 11833 cells before -- **68% of the original defect** -- and the repair
moved it by 118. The candidate's data path was broken at the start and is
broken at the end. The checks that would drive it are not the ones driving the
loop.

`scl_o` and `sda_o` read 0 in both: constant-driven open-drain outputs, with
nothing to get wrong.

## The boundary IS guarded, and the guard approved the regression

**AN EARLIER VERSION OF THIS FILE SAID "NOTHING IN THE LOOP WATCHES THE
BOUNDARY". THAT WAS WRONG AND THE MEASUREMENT THAT DISPROVES IT IS BELOW.** It
came from counting the checks that read ONLY declared outputs -- 16 of 122 --
when a check reading a probe AND `scl_oen` guards `scl_oen` perfectly well.

    port        checks reading it
    scl_oen                    47
    cmd_ack                    42
    al                         42
    sda_oen                    35
    busy                       12
    dout                       11
    scl_o                      10
    sda_o                      10

And what those guards said across the same repair:

    port       guards   before p/f/a   after p/f/a   fixed   broken
    scl_oen        47        30/15/2       34/ 9/4       4        0
    sda_oen        35        22/11/2       26/ 7/2       4        0
    cmd_ack        42        26/16/0       31/11/0       5        0
    al             42        29/11/2       33/ 7/2       4        0

**On the two ports the design moved 2.5x and 3.6x further from golden, the 47
and 35 checks guarding them got strictly happier -- failures 15 -> 9 and
11 -> 7 -- and NOT ONE check that passed before started failing.**

So the defect is not an absent guard. It is 47 checks that watch `scl_oen`,
fire, and are satisfied by a design measurably worse on exactly that port. A
guard that does not discriminate is worse than no guard, because it reports
success.

Two abstentions appeared on `scl_oen` (2 -> 4): checks that decided before and
decide no longer. That is the vacuity sign, and it moved the wrong way at the
same time.

## Why the raw difference is not the number

A spec-admissible design SHOULD differ from golden wherever the specification
leaves the behaviour open, so a raw count measures conformance to golden's
arbitrary choices. Earlier work here quoted exactly that -- "261 of 348
testpoints differing" -- and this tree already recorded the weakness in another
form: "on a 32-bit port two spec-derived designs differ almost everywhere ...
stratify set blindness by port width, or do not quote it".

The seven independently written spec-derived designs are the mask. Where all
seven agree on a port at an edge, seven readings of the specification pin that
value and differing from golden there is a DEFECT; where they disagree the
specification is under-determined and differing is not evidence.

**The mask barely changes the picture: 91.3% and 89.5% of the differences sit
where all seven agree.** The drift is not the specification's slack.

## What the comparison can and cannot see

    106 of the 122 frozen checks read a PROBE
     16 read only declared outputs

Golden predates the probe table and exposes none of the 24, so the comparison
is on the 8 declared outputs -- the surface 13% of the testbench is about.

That cuts both ways and both belong in the reading. It weakens "the editor made
the design worse", because probe behaviour is most of what the editor was
scored on and none of what this sees. It sharpens the concern, because those 8
ports are the entire module boundary: internal state improving while the
observable interface drifts is the worse outcome, not the better one.

## Three defects in the instrument, found by reconciliation

**Aligned by row index.** `cells()` zipped golden's rows against the
candidate's while the constrained split aligned by `edge`, and they disagreed
on the same pair -- 17969 against 19034. `transactional_view` collapses runs of
identical samples, so two designs that behave identically can still have
different row counts and row 7 is not the same instant in both. The module's
own docstring said rows are not comparable by index and the headline path did
it anyway.

**A saturated flag.** At testpoint granularity both designs read 413 of 422,
identical -- one differing edge in a several-hundred-edge recording sets it. It
cannot show movement, and the first version of this file reported it as though
the absence of movement were the finding.

**An unresolved port would read as 100% differing.** `Env.sample` returns None
for a port a design does not expose, so a naming mismatch would report a
missing signal as a behavioural gap. Now named per design; all 8 resolve on all
three designs here.

## Standing caveat

These figures are the OLD editor loop, whose rounds ended after two agent turns
because the stall counter charged it for turns that ran no trial. A loop that
was cut off before it could attempt anything hard is not evidence about what
the editor can do. `rtldbg4` re-runs it with that fixed.
