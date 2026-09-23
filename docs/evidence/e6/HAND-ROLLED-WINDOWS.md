# 17 checks build their own window, and every window fix in the library misses them

## What an editor found

A Sonnet editor driving the real edit session reported REQ-0135 as containing a
provable off-by-one. Its report is model output and carries no authority; this
is the verification.

The check hand-rolls its window:

    end = len(trace)
    for k in range(start, len(trace)):
        ...
        if k > start and not in_start(trace[k]):
            end = k                     # first row where start_sequence is FALSE
            break
    ...
    idle = None
    for j in range(scl_low, end):       # ... which this range EXCLUDES
        if value(trace[j], 'idle'):
            idle = j

`idle` and `start_sequence` are mutually exclusive, so `idle` first becomes
true exactly at the row where `start_sequence` goes false -- which is `end`,
and `range(scl_low, end)` stops one short of it.

## Measured, on every START window in the suite

    design      START windows   idle found INSIDE the range   idle only AT the excluded row
    CANDIDATE            184                             0                            184
    EDITOR-A             236                             0                            236
    GOLDEN                 0                             0                              0

**184 of 184 and 236 of 236.** Never once inside the search range. The check
cannot pass for any design that returns to idle when the sequence ends, which
is every correct one. (Golden shows zero windows because `start_sequence` is
one of the eight probes it does not expose.)

## It is the boundary defect again, with the sign reversed

`temporal.Window.extent` was added this morning because `after` INCLUDED the
closing row in an invariant -- "the row the window closes on is the boundary,
not the interior". REQ-0135 EXCLUDES the closing row where the evidence lives.
Both are boundary errors and both can only convict.

**And the library fix does not reach this one, because this check does not use
the library.** It scans `range()` over trace indices and builds its own window,
so `extent`, `governed`, `body` and every future correction to them pass it by.

## The census

    checks                                                122
      hand-roll a window with range() over trace indices   18
        ...and also use `after`                             1
        ...use range() ONLY, no `after` at all             17

    REQ-0002 0014 0015 0018 0031 0032 0033 0041 0058 0064
    REQ-0066 0078 0114 0120 0122 0135 0150

Two of the ten that convict golden are in this set: REQ-0058 -- the one whose
cause has resisted two measured hypotheses -- and REQ-0066.

**So 14% of the check set is outside the reach of every window-semantics
guarantee the temporal module offers**, and nothing reports it. That is
mechanically detectable from the source, with no design and no model: a check
that indexes the trace by `range()` is writing its own `after`.

## What this does NOT establish

That all 17 are wrong. A hand-rolled scan can be correct, and some of these
may be doing something `after` cannot express. What it establishes is that
they are UNGUARDED -- the boundary rules the library enforces are not enforced
for them, and REQ-0135 shows what that costs when one of them gets it wrong.

Nor does it explain REQ-0058. Being hand-rolled makes it a candidate for the
same class of error; two hypotheses about it have already been measured and
refuted, and this is a third lead rather than an answer.
