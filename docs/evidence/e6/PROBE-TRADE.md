# Span and audit are traded through ONE mechanism, and it is the probes

Measured on the frozen 122-check set for `i2c_master_bit_ctrl`, against golden
RTL run and never read.

## The decomposition

    checks reading NO probe (port-only)                 16 of 122
      decided on golden                                 16 of 16
      silent on golden                                   0
      CONVICTING golden                                  0      AUDIT = 0.0%

    checks reading at least one probe                  106 of 122
      silent on golden                                  75
      CONVICTING golden                                 15

**ALL FIFTEEN CONVICTIONS OF GOLDEN READ A PROBE.** Not most -- all. Verified
as set containment, not by inspection.

And the span the two halves buy, over the 114 behavioural requirements:

    whole set        111 covered   = 97.4%
    port-only         15 covered   = 13.2%

## What that means

A check restricted to the declared interface was right about golden **sixteen
times out of sixteen**, and never once declined to speak. A check that reaches
for spec-named internal state is silent on golden 71% of the time and convicts
it 14% of the time.

So the span/audit trade on this module is not diffuse. It runs through a single
mechanism. Probes buy 84 points of span and they are the entire audit column.

## Why the mechanism does this

Probes name internal state the SPECIFICATION mentions. The probe stage asks the
design population for those signals, and the population provides them -- so
every member factors its internals the same way, and a check reading `fscl` or
`start_sequence` works on all of them.

Golden computes those quantities inline. Eight probes bind to nothing on it
(`active_command`, `cnt_zero`, `filter_cnt_expired`, `filtered_scl_rise`,
`read_sequence`, `start_sequence`, `stop_sequence`, `write_sequence`) and five
more bind a signal of the same name carrying a different quantity -- `fSCL` is
a three-bit shift register where the probe means a one-bit level.

That is not a fact about golden. It is a fact about **any** design outside the
population's factoring. The set can only judge designs shaped like the ones it
was authored against.

## What this says about the target

The target is span > 90%, blindness < 10%, **audit = 0**, reached by the
pipeline without interference.

    configuration        span      audit vs golden
    whole frozen set     97.4%     12/41 = 29.3%   (clean denominator)
    port-only subset     13.2%      0/16 =  0.0%

Both ends are already reachable. Neither end is the target, and the two are
joined by the probe mechanism.

**AND THE REPORTED `audit = 1/12` WAS NEVER THE THIRD COLUMN OF THE FIRST ROW.**
The control is a transliteration of golden, so it shares golden's factoring and
most of the set goes silent on it. `1/12` is audit over twelve checks of a
hundred and twenty-three -- a denominator the port-only row explains exactly.

## What this does NOT license

Shipping the port-only subset. Choosing a ruleset by its audit column is
gating on the grade, which this project bars, and 13.2% span is not a suite.
The number is here to locate the mechanism, not to pick a winner.

The honest statement of the open problem: **make a check that reads spec-named
internal state judgeable on a design that does not carry that state as a
signal.** Until that exists, span above 90% and audit at 0 are not jointly
reachable on this instrument, and no selection rule over these 122 bodies
changes it -- selection cannot add a property no member has.


---

# CORRECTION: the tree already holds the opposite framing, and I skipped it

The section above says the silences are "a fact about **any** design outside the
population's factoring". That states one reading of a disputed point as if it
were settled. `scorecard.py` holds the other, and it was written first:

    **THE GAP IS THE CONTROL'S, NOT THE CHECKS'.** A probe is a `dir: "probe"`
    entry in the contract, so a design is REQUIRED to expose it. [...] It is
    the other way round: the checks name state the contract declares, and the
    control predates probes and implements none of it.

On that reading the 75 silences are golden's NON-CONFORMANCE, not the set's
narrowness, and `audit = 1/12` has a cause I also got wrong: I wrote that the
control "transliterates golden and shares its factoring". It does not. **The
control predates probes and implements none of them** -- which the tree says
plainly and I inferred around.

The same note records a measurement sharper than anything here: point the frozen
set at a module that declares the contract's ports and ties EVERY OUTPUT TO A
CONSTANT -- **14 pass, 0 FAIL, 108 abstain of 122.** A design that does nothing
is convicted by nothing.

## What survives both framings

Contract-conformance decides who is at fault for the SILENCES. It does not
touch these:

1. **All 15 convictions of golden read a probe; 0 of the 16 port-only checks
   convict it, and all 16 decide.** That is a property of the check set,
   measured, and it holds whoever is non-conformant.

2. **Five probes bind a same-named signal carrying a different quantity.**
   `fSCL` matches by name modulo case, binds, and holds a three-bit shift
   register where the check expects a one-bit level. **Conformance cannot
   repair this**: a design may declare a probe named `fscl` and still mean
   something else, and nothing in the pipeline checks the meaning. A
   `dir: "probe"` entry obliges a NAME and a WIDTH; the check depends on a
   QUANTITY. That gap is the contract's, not the control's and not golden's.

3. `audit = 1/12` is audit over twelve checks of a hundred and twenty-three
   however the twelve came about, and the scorecard already prints that caveat
   rather than reporting a rate over a denominator it does not have.

## Why "the probes are spec-derived" does not close the gap

A probe is a NAME-BASED observability obligation, not a meaning-based one. The
specification names the concept "filtered SCL"; the probe stage mints the
identifier `fscl`; binding is `getattr(dut, "fscl")`, a symbol-table lookup.

Golden HAS the concept -- a three-bit shift register holding the last samples,
with the level derived from it. What it lacks is a one-bit signal NAMED `fscl`
meaning that level. So spec-derivation of the probe transfers to a design that
was handed the contract and to no other. The population was handed it. Golden
was not.

The width mismatch is the proof that this is about names and not about
conformance: name identity was achieved and meaning identity was not.
