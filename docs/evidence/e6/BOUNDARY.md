# The window's closing row was being asserted over

`after` appends a row and *then* tests it for the close, so `Window.rows` ends
on the first row at which the window's scope has **already ended**. Every
invariant operator -- `throughout`, `stable`, `never` -- read `rows`. So the
commonest idiom this tree has, "while A, B holds", was asking B to hold at the
row where A stopped.

## The proof needs no design, no population and no reference

Assert the window's OWN defining condition over it:

    trace  p = 1 0 0 0 1 1 0 1
    after(trace, p == 0, until=WHILE_ACTIVE)   ->  rows [1, 2, 3, 4]
    throughout(w, p == 0)                      ->  (False, 4, "the invariant broke")

A check asserting exactly the condition its window is defined by cannot be
wrong about any design -- its verdict does not depend on what the design did --
so a FALSE there is the operator's error and nothing else's.

**And one run had frozen that check.** REQ-0044's chosen body, verbatim:

    windows = after(trace, lambda r: r['outputs'].get('sda_oen') == 0,
                    until=WHILE_ACTIVE)
    worst([throughout(w, lambda r: r['outputs'].get('sda_oen') == 0,
                      after_activation=False) for w in windows])

It failed **168 of the 168 testpoints it decided** against the known-good
control. So did REQ-0005 -- 299 of 299 -- whose windows run from one change of
a port to the next and assert the port holds the value it opened with; at the
closing row it has changed, by construction.

## The rule, and why it is asymmetric

An **invariant** (`throughout`, `stable`, `never`) reads `Window.extent` -- the
rows without the boundary. An **existential** (`eventually`, `pulse`,
`sequence`, `until`, `nth`) keeps reading `rows`. That asymmetry is LTL's: in
`A U B` the antecedent is not required where B holds, but B is required to hold
somewhere, and the closing row is exactly where it may land. Dropping the
boundary from the second would read a response arriving precisely at the
release as absent -- the same defect pointed the other way.

An unclosed window met no release, so it has no boundary to drop.

## What it was costing, on run 3's own frozen corpus

Checks convicting the known-good control, before and after, at the two
settings of the refutation preference:

    rule                 before the fix                       after
    preference ON    REQ-0018 (behavioural)            REQ-0018 (behavioural)
    preference OFF   REQ-0005 (behavioural)            REQ-0042 (interface)
                     REQ-0042 (interface)              REQ-0045 (interface)
                     REQ-0044 (interface)
                     REQ-0045 (interface)

REQ-0005 and REQ-0044 were boundary artifacts and are gone. The two survivors
are `interface` units -- outside the span and audit denominators, which count
`behavioural` requirements only.

## Why nothing caught it

The full suite passes unchanged at 2570 tests. Not one of them pinned which
rows an invariant holds over, so the semantics could be read either way and
the reading that can only convict was the one in the code. Five tests now pin
it, each shown failing against a mutant that restores the old reading.
