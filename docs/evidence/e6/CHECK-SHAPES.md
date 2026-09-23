# Two mechanical defect shapes, found by an editor that never saw golden

A Sonnet editor driving the real edit session spent 2 of 20 trials, latched
nothing, and stopped -- reporting that what it could trace back to a cause was
in the CHECK SET, not the design. Its brief told it to say so rather than mangle
a design to satisfy a check it believed wrong, and it did.

That report is model output and carries no authority. What follows is the part
of it that survives mechanical verification against the frozen sources, plus
what a census of all 122 checks says about how common each shape is.

**THE CONVERGENCE IS THE POINT.** The editor was barred from golden, from
`benchmarks/`, and from every Verilog file but its own. It named REQ-0034 and
REQ-0128 from the oracle sources and the traces alone. Both are on the
independently-measured list of 15 checks that CONVICT GOLDEN. Two instruments
that cannot see each other agreeing is worth more than either alone.

## Shape 1: an abort predicate that fires in the normal case

    REQ-0051

        def not_reset(row):
            return (row['inputs'].get('nReset') != 0
                    and row['inputs'].get('rst') != 1)

        windows = after(trace, applies,
                        until=lambda row: row['outputs'].get('slave_wait') == 0,
                        aborts=not_reset)

`not_reset` is true on every row where the design is NOT being reset -- which is
almost every row of every trace. Bound to `aborts`, it collapses every window
the instant it opens. **REQ-0051 cannot decide anything about any design.**

The measurement agrees without being told: REQ-0051 is one of exactly two
checks silent on BOTH golden and the pipeline's own repaired design. A check
that is dark on two designs that disagree everywhere is dark for a reason that
has nothing to do with either.

Census over the frozen set: **1 of 122.** Rare, and terminal where it occurs.

## Shape 2: `throughout` over a window that runs to the end of the trace

    REQ-0034

        windows = after(trace, start_or_stop, until=TO_END)
        ...
        throughout(window, lambda row: row['outputs'].get('busy') == expected)

`after` opens one window PER event, and `TO_END` means each runs to the end of
the trace. So a START at edge 4 obliges `busy == 1` for the whole remainder --
and a legitimate STOP at edge 11 clearing `busy` breaks the FIRST window.
**Any trace carrying more than one transaction fails this by construction**,
whatever the design does.

REQ-0128 is the same shape against `al`: one window per arbitration-loss row,
running to end of trace, demanding idle-and-released throughout. A design that
correctly RECOVERS from arbitration loss fails it.

Census over the frozen set: **3 of 122** -- REQ-0034, REQ-0046, REQ-0128.
**Two of the three convict golden.**

## What this accounts for

Of the 15 checks that convict golden:

    3   rest on a WIDTH-MISMATCHED probe      REQ-0061, REQ-0096, REQ-0102
    2   are `throughout` over a TO_END window REQ-0034, REQ-0128
    10  not yet explained by a known shape

So against the clean denominator of 41, convictions go 12 -> **10 of 41 =
24.4%** once the TO_END shape is discounted. That is not audit 0 and no amount
of discounting gets there; but two of the twelve now have a mechanical,
design-free cause rather than a judgement call about what the spec means.

## Why these belong in a blocking gate and the faithfulness gates did not

Both shapes are decidable from the SOURCE, with no design, no population, no
reference and no model. That is the same standing as `well_formed`, the replay
break and `DEAD_ORACLE` -- the three mechanical grounds the plan keeps
blocking. Neither asks whether the check is RIGHT about the specification;
each asks whether the check can be wrong about any design at all:

* an `aborts` predicate true in the normal case decides nothing, ever;
* `throughout` over `TO_END` convicts every trace with a second event.

A check that cannot discriminate is not a strict check. It is a broken one,
and it costs span and audit at once.

## One claim of the editor's that does NOT survive

It reported REQ-0073 unresolvable because `after_activation=True` requires the
effect strictly after the row where `al` rises, and the closing row is excluded.
The exclusion is real but it is the ACTIVATION row, not the closing row:
`eventually` reads `body` (`rows[1:]`), which still contains the close. The
conclusion stands for that different reason -- a design releasing on the same
row the loss is detected puts the discharge on `rows[0]` -- and `temporal.py`'s
own docstring names this hazard: `after_activation=True` "asks for a change the
requirement never demanded" on a requirement describing a STATE.

## Not a constraint breach, but worth recording

The editor flagged that `suite/results/TP-*.trace.json` carries a `model`
column and `TP-*.json` carries `mismatches`/`expected`, both holding
differential reference-model output, and that its brief permitted reading them.
That model is `ref_model.py`, the pipeline's OWN spec-derived artifact -- not
golden and not a known-good design -- so it is in-family and no constraint was
broken. It is still a second opinion an editor can anchor on, and a brief that
means to exclude silver references should say so about those fields by name.
