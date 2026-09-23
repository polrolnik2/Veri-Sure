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


---

# CORRECTION: the mechanism of shape 2 is not what either of us said

The editor reported REQ-0034 as *"`after(...)` opens one window PER START/STOP
event, each checked all the way to the end of the trace"*, and I verified the
source shape, the census and the convictions -- but not the window semantics --
and repeated it.

`after` takes `overlap=False` by DEFAULT, and the scan for the next activation
resumes past the previous window's end. With `until=TO_END` the first window
runs to the end of the trace, so the scan resumes past the end and **there is
exactly one window**. Later activations open nothing; they are already inside
it. A test asserting "one window per activation" is what caught this:

    after(trace, sta == 1, until=TO_END)  over  sta = 1 0 0 0 1 0
      -> 1 window, not 2

**The conclusion survives and the reason does not.** The shape still convicts a
trace the requirement permits, for a simpler cause: the window never CLOSES.

    trace  sta = 1 0 0 0 1 0
           busy= 1 1 1 0 1 1

The requirement is "after a START, busy is high until the transaction ends".
This trace starts, is busy, ends at index 3, starts again, is busy again --
exactly what the requirement describes. One window opens at index 0 and runs to
index 5, so the legitimate idle gap at index 3 falls inside it and `throughout`
returns False. No design, no population, no reference.

So the defect is not "one window per event". It is **an invariant asserted over
a window with no closing condition**, which claims the invariant from the first
trigger to the end of the run rather than for the situation the requirement
describes.

## What shipped

`temporal.unbounded_invariant(source)` -- an AST walk, no design and no trace --
returns the invariant operators (`throughout`, `stable`, `never`) applied to a
window opened with `until=TO_END`. `well_formed` refuses such an oracle and
names the operator, which buys it a repair round rather than letting it convict.

Existentials are deliberately NOT flagged: `eventually` over a long window has
MORE chances to find its witness, so an unbounded window cannot convict there.

The objection offers the legitimate reading rather than banning it -- a
requirement that genuinely obliges something for the rest of the run keeps
`TO_END` and says so in the clause, so the claim is visible rather than
incidental.

On the frozen i2c set it flags exactly REQ-0034, REQ-0046 and REQ-0128 -- the
same three the hand census found.
