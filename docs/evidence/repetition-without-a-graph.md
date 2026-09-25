# Repetition finds the shared cause, and the testplan hides it

The dependency-graph route to attribution has a circularity that rules it out
of the pipeline: the graph is built from the RTL, and the RTL is the artifact
under test. `rtl_depth.py` reads golden source, so it can analyse a benchmark
and can never run inside a real job. The alternative needs nothing but the
oracles and their traces — if N requirements each had to re-derive the same
missing concept, they should fail *together*.

This measures whether that works, against a grouping whose answer is already
known: the six h3 convictions that a filtered-bus substitution clears
(`i2c-filter-substitution.md`).

## First finding: scoped, the question cannot be asked at all

h3's testplan is a strict partition — all 455 testpoints cover **exactly one**
requirement each, 455 of 455. Deciding each oracle over its own `tp_uids`
therefore gives a co-failure matrix that is **identically zero for every pair**,
because no two requirements ever share evidence.

That zero is a harness artifact wearing the costume of "no shared cause". Any
repetition-based attribution is structurally blind under the current scoping,
and no amount of better clustering fixes it.

## Second finding: unscoped, the signal is strong and specific

Deciding every oracle against every trace (54 × 455), 36 oracles convict
somewhere. Jaccard over the testpoints where each convicts:

| | co-failure | co-firing | **co-failure given co-firing** |
|---|---|---|---|
| within the cleared six | 0.198 | 0.199 | **0.813** |
| across the boundary | 0.059 | 0.112 | **0.369** |
| among the other 30 | 0.053 | 0.145 | **0.245** |

Raw co-failure confounds *failing for the same reason* with *being exercised
together*, and co-firing separates too (+0.087), so the raw lift overstates the
case. Conditioning on co-firing removes the confound: **where two of the six are
both exercised, they fail together 81% of the time, against 25% for unrelated
pairs.** That is the number a clustering heuristic would rest on, and it is a
3.3x separation with no RTL read anywhere.

## What this costs, stated plainly

Unscoping evidence is the plan's §5.1, and it was refuted for **separation** —
deciding every oracle everywhere collapses golden-versus-candidate
discrimination to zero. This measurement does not overturn that. It says the
same change is a **precondition for attribution**, which is a different job:
scoped evidence gives a sharper verdict and no way to see a shared cause;
unscoped evidence gives a blurrier verdict and makes the shared cause visible.

Two numbers for two jobs, as with the ratchet in §6.2. Judge on the scoped
verdict; attribute on the unscoped co-failure.

Run with `python docs/evidence/failure_repetition.py`.
