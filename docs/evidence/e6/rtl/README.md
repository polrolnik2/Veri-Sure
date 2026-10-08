# Debugging RTL against the frozen check corpus

`e6_rtl_debug.py`, against one run's own 122 frozen checks and 24 declared
probes, starting from an independently written 518-line candidate. No reference
model is generated: `SpecflowReviewer._decide_requirements` decides the frozen
set over the recorded DUT trace with `decide_rtl`, and `ref_model.py` is read
only so the cocotb runtime has something to advance in lockstep.

## The corpus reaches a conformant design

    port-only stub        14 pass    0 FAIL   108 abstain
    the candidate         84 pass   35 FAIL     3 abstain

**Three abstentions against the stub's 108.** 106 of the 122 checks name a
probe, so a design that does not expose them is judged by 16; one that honours
the probe contract is judged by 119. The "16 checks" ceiling measured earlier
was the stub's missing interface, not the set's reach -- and 35 checks convict
an independently written spec-derived design, so the set is not vacuous either.

## rtldbg1 -- the editor damaged the design, and its own tool told it to

    ROUND 0   84 pass   35 FAIL   3 abstain   246 failing tp   6 trials
    ROUND 1   86 pass   31 FAIL   5 abstain    51 failing tp   0 trials
    ROUND 2   86 pass   31 FAIL   5 abstain    51 failing tp   3 trials

Four checks closed, then a stall: the same twelve requirements named every
round, and a turn that spent nothing.

`find_signal` had reported

    "signal": "filt_reload", "driver_count": 0,
    "note": "... it is a module input, or its driver was removed."

about a net driven by its own declaration, `wire [13:0] filt_reload = ...`.
`parse_rtl_blocks` produced no driver for a net declared with an initialiser,
and `find_signal` reads drivers straight out of `RtlBlock.writes`. The editor
believed it and added `assign filt_reload = clk_cnt[15:2];` beside the
declaration. Two drivers, on the net feeding `fcnt <= filt_reload`, and the two
checks that stopped deciding are the 3 -> 5.

**It did NOT delete behaviour**, which was the first hypothesis and was wrong:
`always` 12 -> 12, `reg`/`wire` declarations 20 -> 20, `assign` 26 -> 35, and
the only identifiers that vanished were eight comment words. 518 -> 380 was
comments.

## rtldbg2 -- the same candidate, after the parser fix

    ROUND 0   84 pass   35 FAIL   3 abstain   215 failing tp
      abstain: REQ-0051, REQ-0073, REQ-0128

Round 0 reproduces rtldbg1's verdict exactly, which is the control: the fix
changes the editor's diagnosis, not the measurement. (215 against 246 failing
testpoints because the pruned backfill runs 422 modules, not 482.)

Mid-repair, the editor's working copy read

    drivers of filt_reload: [('C3', 'assign')]

one driver, not two -- so it no longer makes the damaging edit. **The run was
stopped before round 1 reported**, so whether that converts into fewer failing
checks is UNMEASURED. It is the open question here, and it can still
disappoint.

## What the abstentions are

REQ-0051 is one of the three baseline abstentions AND appears in a separate
end-to-end run's "not staged -- normalize states no observable obligation"
list. Same requirement, two independent runs: that abstention belongs to the
specification, not to the design and not to the check.
