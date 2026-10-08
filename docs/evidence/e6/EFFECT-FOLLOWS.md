# normalize over-claims "the effect follows", and nothing checks it

## The chain

`normalize` records `activation.effect_follows` -- whether the requirement's
effect comes AFTER its trigger or WITH it. That is exactly the `|=>` versus
`|->` decision, and `after_activation=True` is how a check states it.

`SYSTEM` then tells the oracle author, verbatim:

    THE `normalized` BLOCK ALREADY CONTAINS YOUR WINDOW. TRANSCRIBE IT.
    [...] You are not inventing a window, you are copying one.

The specification is in the prompt as background, but the instruction is to
copy, not to re-derive. And `oracle_gen`'s own comment names the consequence:

    It is NOT a claim that the window is correct, and nothing in the pipeline
    makes it one. `normalize.gate_one` checks that the response parsed, that
    there is one block, that `clk` is not in the window and that the port names
    are declared. It never asks whether `opens_on`, `until` and `aborts_on` are
    licensed by the requirement's own words [...]

    So a wrong window arrives as an instruction and departs as the author's
    defect.

With a measurement already on record beside it: on the c1-i2c re-authoring run,
**eight of nine** rejected checks whose requirements were well-formed and
boundary-observable were rejected for a condition transcribed verbatim out of
`activation.opens_on` or `activation.until`.

## The measurement, on full2

Taking "licensed" to mean the requirement's own text carries sequence language
(`after`, `then`, `once`, `following`, `in response to`, ...) or licenses a
cycle count, which is `correspondence`'s existing test:

    requirements where normalize set effect_follows=True        52
      text licenses the claim                                   13
      **UNLICENSED**                                            39   (75%)

    of the unlicensed, those a SHIPPED CHECK acted on           27   (22% of 122)
      of those, convicting golden                                2   REQ-0053, REQ-0055

Many of the 39 are not obligations at all:

    REQ-0028  "The din input is the data bit transmitted during a WRITE operation."
    REQ-0036  "The al output is an arbitration-lost indicator."
    REQ-0116  "An asserted slave_wait signal indicates that a slave [...] is holding SCL low."
    REQ-0146  "During all command sequences, the module uses open-drain behavior [...]"

A definition has no effect to follow anything. `effect_follows=True` on one is
not a reading of the sentence; it is a default.

## REQ-0053, end to end

    specification   "`slave_wait` is asserted WHEN the master has JUST RELEASED
                     SCL high through `scl_oen`, but `sSCL` remains low."
    S1 mints        "...shall assert slave_wait when it has released SCL high..."   ("just" dropped)
    normalize       expectation: "...is asserted while the filtered SCL remains
                     low AFTER SCL has been released", effect_follows=True
    the check       eventually(w, slave_wait==1, strong=True, after_activation=True)
    golden          slave_wait already 1 at the activation row, which is the LAST
                    state of the trace -> body empty -> strong=True convicts

Relaxing EITHER flag spares golden, and the population-shaped candidate passes
in every variant:

    as shipped   (strong=True,  after_activation=True )   GOLDEN=FAIL  CANDIDATE=pass
    |-> not |=>  (strong=True,  after_activation=False)   GOLDEN=pass  CANDIDATE=pass
    weak         (strong=False, after_activation=True )   GOLDEN=pass  CANDIDATE=pass
    both relaxed (strong=False, after_activation=False)   GOLDEN=pass  CANDIDATE=pass

So the check is over-strict, and it is over-strict because it was TOLD to be.
Blaming the author is the mis-attribution `oracle_gen`'s comment predicts.

## Where a gate belongs, and where it does not

The gate that exists -- `effect_follows` against what the CHECK did -- finds
almost nothing (2 mismatches on full2, neither convicting), because checks obey
the instruction nearly perfectly. **It cannot see the case that matters, which
is normalize being wrong and the check being obedient.**

The gate that is missing asks the question `correspondence` already asks of a
check, of the WINDOW instead: is `effect_follows=True` licensed by the
requirement's own words? That is mechanical, design-free, needs no model, and
would have flagged 39 of 52 here.

It is NOT shipped in this commit. 39 of 52 is too large a share to gate on
without first knowing how many of the 27 acted-on cases are actually harmful
rather than merely unlicensed -- a check can claim `|=>` and still pass every
design if the effect does in fact arrive later. Two are known harmful. The
other 25 are latent, and measuring them needs a design that responds
simultaneously, which is the same instrument the phase question needs.

## One caveat on REQ-0055

REQ-0055 appears in the acted-on list, but its body uses `throughout` rather
than `eventually`, and the flag test above was run on REQ-0053 only. Its
failure -- golden holds `clk_en` HIGH through the slave-wait window where
REQ-0051 says to keep it low -- has not been traced to `effect_follows`, and
the `clk_en` meaning question raised in SLAVE-WAIT.md is still open. Listed
because the scan found it; not claimed as explained.
