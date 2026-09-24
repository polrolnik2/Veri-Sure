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
