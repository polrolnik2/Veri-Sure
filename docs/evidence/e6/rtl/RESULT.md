# The check set as an RTL Editor testbench

One run's 122 frozen checks used as the testbench, and an RTL design produced
by iterating on the errors they report. No reference model is generated:
`SpecflowReviewer._decide_requirements` decides the frozen set over the
recorded DUT trace with `decide_rtl`, and `ref_model.py` is read only so the
cocotb runtime has something to advance in lockstep.

Driver `e6_rtl_debug.py`; the design starts from an independently written
518-line candidate and is edited by `RTLEditor`/`_EditSession` -- staged block
edits, `check_staged` before `commit`, rollback on regression, 40 trials over
6 rounds.

## Performance

    round   pass  FAIL  abstain   failing testpoints   trials spent
      0       84    35        3                  215              3
      1       85    34        3                  191             11
      2       93    25        4                   29              1
      3       92    26        4                   29              0
      4       92    26        4                   29              3
      5       93    25        4                   29              -

**84 -> 93 passing, 35 -> 25 failing, failing testpoints 215 -> 29.** Ten
checks closed, a 29% reduction in failures and 86% in failing testpoints, for
18 of the 40 trials.

An abstention is never counted as a pass. The set gained one (3 -> 4): REQ-0051
moved OUT of abstain into FAIL -- it began deciding, which is an improvement --
while REQ-0089 and REQ-0125 went silent.

## The set reaches a conformant design

    port-only stub        14 pass    0 FAIL   108 abstain
    this candidate        84 pass   35 FAIL     3 abstain

106 of the 122 checks name a probe, so a design that does not expose the
contract's probes is judged by 16 of them and one that does is judged by 119.
The earlier "16 checks" ceiling was the stub's missing interface, not the set's
reach. And 35 checks convict an independently written spec-derived design, so
the set is not vacuous at the other end either.

## What stops it going further

The editor STALLS with budget unspent -- 18 of 40 trials used, a round that
spent 0 -- and the residue is dominated by checks no edit can discharge:

    round 0    7 of 34 failing are scaffolding/interface   21%
    round 5    4 of 12 named are scaffolding/interface     33%

The share RISES as it converges, because the fixable failures clear and the
unfixable ones remain. These four survived every single round:

    REQ-0008 [scaffolding] "The Bit Command Controller performs START, STOP,
                            read, and write bit-level signal generation..."
    REQ-0014 [interface]   "The input port clk is the system clock."
    REQ-0025 [scaffolding] "The supported bit-level command list includes
                            `I2C_CMD_STOP`."
    REQ-0026 [interface]   "The bit-level command input cmd supports the
                            I2C_CMD_WRITE command."

No RTL edit makes "the input port clk is the system clock" pass or fail, and
its check complains that `cmd_ack` was not asserted. Two more are truncated:
`list_failing_requirements` cuts requirement text at 200 characters, and
REQ-0002 (255) and REQ-0050 (236) lose theirs.

So the editor's floor here is set by its INPUTS, not its tools. The tooling is
sound -- `explain` returns the requirement, the activation, the window, what
the check said, the objecting edge and a per-edge boundary trace, and
`check_staged` reports syntax, warnings and multidriven nets before a commit.

## Against the previous run

    rtldbg1 (before the driver-detection fix)   86 pass  31 FAIL  5 abstain
    rtldbg3 (after)                             93 pass  25 FAIL  4 abstain

`rtldbg1` plateaued at 31 with a round that spent 0 trials and never recovered.
Its `find_signal` had reported `driver_count: 0` for `filt_reload`, a net driven
by its own declaration, so the editor added a second driver and put it in
contention -- which is what silenced two checks there (3 -> 5 abstain). With
`parse_rtl_blocks` taught that a net declared with an initialiser is a driver,
that damage does not recur and the floor moves from 31 to 25.
