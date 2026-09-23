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
