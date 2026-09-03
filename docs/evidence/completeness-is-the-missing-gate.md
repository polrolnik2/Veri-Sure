# The completeness gate exists, is tested, and has never once been called

The argument that per-part verification is only safe when each part is verified
*completely* -- so that "one thing not hooked" is impossible rather than
unlikely -- is the operational-property / gap-free discipline, and its criterion
is not "the part passes its checks" but "the check set DETERMINES every output
at every time, leaving no gap".

`specflow/qualify.py` is that instrument, and its own docstring already makes
the argument:

> "G7 asks whether every spec testpoint was exercised. G8 asks the complementary
> question the spec cannot answer, because **a suite can cover every testpoint
> and still be unable to fail.**"

> "A surviving mutant is a **witness, not a score**: a concrete perturbation the
> suite cannot see, which points at the missing check far more precisely than an
> uncovered bin does."

It even disposes of the standard objection: mcy's `test_eq` leg formally
separates UNCOVERED from NOCHANGE, so an equivalent mutant is discarded by proof
rather than by argument. And EQGAP -- the suite fails while the design is
provably unchanged -- is a harness-defect detector obtained free from a gate
already being paid for.

## It has no production call site

```
$ grep -rn "import qualify" --include=*.py .
./tests/test_specflow_qualify.py:14:from specflow.qualify import (
```

The only importer in the repository is its own test file. `loop.py` mentions G8
in prose and never calls it. No run in `/home/user/runs/` has ever produced a
qualification report. The gate is fully built, fully tested, and has gated
nothing.

Plan §9 then leaves it dangling: with the bin subsystem deleted it "becomes
unwired... should be either re-pointed at the oracle set or explicitly parked."

## Scope note against an earlier finding

An earlier note recorded "mutant survival is not evidence a check is weak" as
refuted. That was about attributing a survivor to an INDIVIDUAL check, and it
stands. Completeness uses survival against the SET, with the formal equivalence
filter deciding what counts. Different granularity, different claim; the
docstring above already draws the line.

## What follows for composition

Completeness is what earns the right to assemble: a part verified completely can
be replaced by its specification, which is exactly what "discharged component"
is supposed to mean. Without it, lifting a child's interface asserts a discharge
nobody measured -- see `runs/m2-bytectrl/CAVEAT.md`, where this repository does
precisely that, on a child h3 scored at 54 TRUSTED of 118 with 20 convicting
golden.

The ordering constraint that follows is small and needs no new machinery: run
G8 on the child's frozen oracle set, require every survivor to be either killed
or explicitly accounted for, and only then permit the lift.
