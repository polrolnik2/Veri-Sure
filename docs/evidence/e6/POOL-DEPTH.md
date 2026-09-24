# Volume buys blindness here, and `POOL.md`'s numbers were the collapse

`POOL.md` recorded this sweep reading

    accepted only     122   blind 0.1454   audit  9/37
    +1 body each      241   blind 0.1644   audit 15/40
    +2 bodies each    349   blind 0.2336   audit 16/43

and identified the impossibility itself: "Blindness rising and `effective_size`
FALLING as separators are added is not how adding separators behaves. It is not
what happened." `scorecard.score` keyed checks by `req_uid`, so those rows were
122 checks every time, with the accepted body REPLACED by a corpus alternative.

`score` now carries a set. The same sweep, same corpus, same golden control:

    config             bodies   span            blindness       audit           eff_size
    accepted only         122   0.9737 MET      0.1457          9/42 = 0.2143         99
    +1 body each          241   0.9737 MET      0.0657 MET     15/46 = 0.3261        168
    +2 bodies each        349   0.9737 MET      0.0652 MET     17/49 = 0.3469        208
    all well-formed       476   0.9737 MET      0.0586 MET     20/52 = 0.3846        273

**BLINDNESS 0.1457 -> 0.0586, UNDER THE ORIGINAL 10% BAR**, at no cost to span --
0.9737 to four places in every row, because admitting a second body for a
requirement that already had one covers no new requirement.

## The three things this settles

**Volume buys blindness on this corpus.** The plan's contrary finding -- "the
first 100 bodies buy 26 points, the last 164 buy 2.7. Saturated" -- was measured
on k1 at 50% blindness with a driver that did its own scoring. `full2` starts at
14.6% and the first extra body per requirement buys **8.0 points**, which is the
largest single move any lever has produced on this branch.

**The extra bodies are SEPARATORS, not copies.** `effective_size` -- distinct
verdict vectors, never a count of checks -- goes 99 -> 168 -> 208 -> 273. Adding
119 bodies to reach 241 added 69 distinct vectors. That is the number the plan
asks for in place of a check count, and it says the pool has real variety in it:
the "69% identical among sound pairs" that resampling produces is a fact about
pairs of bodies, not about what a corpus of 616 contains.

**Audit rises, and it must.** 0.2143 -> 0.3846. Rejections UNION -- "a design is
rejected when ANY of 114 members objects" -- so a bigger set constricts harder and
convicts the control more. This is the trade the plan predicts and the reason
`placement` exists: "fill the pool, then select", where selection chooses WHICH
constriction to keep.

## Against the target

    target            span > 90%    blindness < 10%    audit = 0
    all well-formed   97.4%  MET    5.9%   MET         38.5%  NOT MET

**Two of three met at once, for the first time on this branch, and on the
ORIGINAL blindness bar rather than the relaxed one.** What remains is entirely
the audit column, and it is now larger than it was before -- which is what
admitting 354 extra objectors is supposed to do.

Whether selection can take that back without giving up the span or the blindness
is the other half, and it is measured in `SELECT.md` rather than assumed here.

Reproduce: `docs/evidence/e6_admit_corpus.py <corpus-dir> <golden-suite-dir>`.
No model calls. Golden is RUN and never read.


---

# Both rules ON the deep pool: blindness 0.0477, and audit halves but not to zero

`TRIPLE.md`'s two rules -- the licence rule (`|=>` demoted to `|->` where the
requirement's words carry no sequence word) and the phase rule (the control's
`sta_condition`/`sto_condition` read one edge early) -- applied to all 476 bodies,
with no selection at all:

    configuration                              span      blindness   audit
    pool 476, no rules                         0.9737 v  0.0586 v    20/52 = 0.3846
    pool 476 + licence + phase                 0.9737 v  0.0477 v    11/50 = 0.2200
    accepted 122 + licence + phase             0.9737 v  0.1416      1/40  = 0.0250

**Blindness 0.0477 is the lowest figure measured on this branch**, and span is
unmoved to four places. The rules cost neither column: they are the only levers
here that do not trade.

**But the phase rule's effect SHRINKS with depth.** On the accepted set it takes
audit 9/42 -> 1/40, a factor of 9. On the pool it takes 20/52 -> 11/50, a factor of
1.75. The convictions it removes are the same phase-shaped ones either way; what
changes is everything ELSE the pool admits. The accepted set had already been
screened once by the oracle stage, and 354 extra bodies bring in convicting checks
of many other shapes, which no single rule addresses.

## Which is the tension, stated plainly

    best blindness measured   0.0477   at audit 0.2200
    best audit measured       0.0250   at blindness 0.1416

**Depth strictly raises audit risk, because 476 bodies are 476 chances to convict
the control and 122 are 122.** Rejections union; there is no way to admit more
objectors and convict a correct design less. So low blindness and `audit = 0` pull
against each other structurally, and the only grade-blind instrument for
suppressing the extra convictions is a soundness filter -- which removes
separators preferentially and gives the blindness straight back
(`effective_size` 273 -> 141, measured in `SELECT.md`).

That is not a tuning gap. It is the over-strictness/vacuity trade the whole
project is about, arriving as a frontier rather than as a defect:

    span is met everywhere -- 0.9737 in every configuration above
    blindness < 10% and audit = 0 have NOT been met together by any rule here
