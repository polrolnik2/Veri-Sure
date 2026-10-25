# The RTL Editor testbench: three editors, one frozen check set

Three Sonnet editors drove `_EditSession` against the frozen 122-check set,
each on an identical private copy of `candidate-start.v`, each barred from any
reference implementation, from `benchmarks/`, from any Verilog outside its own
run directory, and from grepping the filesystem for module or signal names.
Every edit went through `apply`, so the trial budget, the syntax and
multi-driver check, the latch rule, the anti-silencing guard and the rollback
all applied.

    editor   trials used   latched   passing        failing testpoints
    A            13 of 20        6   86 -> 95       215 -> 121
    C            10 of 20        4   86 -> 91       215 -> 207
    B             2 of 20        0   86             215

The prior in-tree result was **88 passing after 17 commits** (`rtldbg5`). Two
editors cleared it, from DIFFERENT designs, and neither exhausted its budget.
**The 88 plateau was the agent's, not the check set's** -- which is what this
experiment was run to decide.

    candidate-start.v   the starting design, 86 passing
    editorA-90.v        A at trial 3    (90 passing)
    editorA-92.v        A at trial 8    (92 passing)
    editorA-95.v        A final         (95 passing, 121 failing testpoints)
    editorC-91.v        C final         (91 passing)

## What the passing count does NOT mean

Ten checks in this set convict a known-good design. A's earlier trial repaired
two of them, so part of its gain is movement AWAY from correct behaviour on
that axis. `90 passing` means "satisfies more of this check set", not "is a
better design", and the two are measurably different here.

## All three reported check defects, and the three I verified were real

  * **REQ-0051** (B): `aborts` bound to a predicate true whenever the design is
    NOT resetting, so every window collapses on opening. Confirmed: REQ-0051 is
    one of exactly two checks dark on both golden and the repaired design.
  * **`throughout` over a `TO_END` window** (B): 3 of 122, two convicting
    golden. Now refused by `well_formed`.
  * **REQ-0135** (A): sets `end` to the first row where `start_sequence` is
    false, then searches `range(scl_low, end)` for `idle` -- excluding that
    row, which is exactly where `idle` first becomes true. Confirmed over every
    START window in the suite: `idle` found inside the range 0 times, only at
    the excluded row 184 of 184 on one design and 236 of 236 on another.

B stopped at 2 trials specifically to report rather than contort the design,
which the brief asked for and which turned out to be the right call.
