# The frontier: span is met everywhere, blindness and audit trade against each other

Every figure below is `full2`'s frozen artifacts re-scored by the current code
against golden RTL run through a suite regenerated from the corpus, whose 482
traces digest-match the corpus's own stimulus 482 of 482. Zero model calls.
Golden is RUN and never read.

    target     span > 90%      blindness < 10%     audit = 0

## With `TRIPLE.md`'s two rules applied at every depth

    bodies   span            blindness       audit            eff_size
       122   0.9737 MET      0.1416          1/40  = 0.0250         100
       241   0.9737 MET      0.0518 MET      6/44  = 0.1364         165
       349   0.9737 MET      0.0513 MET      8/47  = 0.1702         206
       476   0.9737 MET      0.0477 MET     11/50  = 0.2200         267

**REPRODUCED FROM A COMMITTED PATH, ALL FOUR ROWS.** The 241/349/476 rows were
first measured by a scratch driver and `e6_admit_corpus.py --rules` reproduces
every figure to four places. The 122 row additionally cross-checks
`e6_corrected_triple.py` -- a different driver, the same 0.1416 and the same
1/40 = 0.0250 -- which is the first time either of those has been confirmed by an
independent path.

One bug is recorded because it reached a printed table before the reproduction
caught it: the scratch driver's `limit=0` appended a body before testing the limit,
so its "accepted only (122)" row was the 241-body result under a wrong label. The
committed driver special-cases zero and does not have it, which is why the
reproduction was worth running rather than assuming.

**SPAN IS PINNED AT 0.9737 THROUGHOUT.** A second body for a requirement that
already had one covers no new requirement, so depth is free in that column.

**BLINDNESS AND AUDIT MOVE IN OPPOSITE DIRECTIONS, MONOTONICALLY.** And the shape
is not linear: the FIRST extra body per requirement buys **9.0 points** of
blindness (0.1416 -> 0.0518) for 11 points of audit, and everything after it buys
0.4 more points of blindness for another 8.4 of audit. The knee is at one extra
body each.

    lever                     blindness        audit
    +1 body per requirement   -9.0 points      +11.1 points
    +2 and +3 more            -0.4 points      + 8.4 points

## Why this is a frontier and not a tuning gap

Rejections UNION -- "a design is rejected when ANY of 114 members objects" -- so
476 bodies are 476 chances to convict the control where 122 are 122. **There is no
way to admit more objectors and convict a correct design less.** The two are the
same act seen from the two ends the project names: constriction toward the correct
class, and constriction past it.

The only grade-blind instrument for suppressing the extra convictions is a
soundness filter, and `SELECT.md` measures what it costs: `max_convictions` drops
the checks that convict MANY designs, which are the best separators, taking
`effective_size` from 273 to 141 and blindness from 0.0477 to 0.2191. It hands the
blindness straight back. The plan's own sentence, confirmed:

> selecting for predictable soundness is selecting for blindness, the same
> predicate read twice

## What each lever actually costs, all measured on this corpus

    lever                       span      blindness            audit
    depth (122 -> 476)          0.0000    -9.4 points          +19.5 points
    licence rule                0.0000    -0.4 points          -1 conviction
    phase rule                  0.0000     0.0000             -8 convictions at 122,
                                                              -9 at 476
    max_convictions t=2         -21 pts   +17 points (at 476)  (one class accepted)
    floor of one body per req   +21 pts   +17 points           -6 convictions

**The licence and phase rules are the only levers that cost nothing.** Both are
derived from the requirement's own words or from the specification's own equation,
applied uniformly, and neither reads the audit column. Everything else trades.

## Where that leaves the three targets

    span            MET in every configuration measured, 0.9737
    blindness       MET from 241 bodies upward, best 0.0477
    audit           NOT MET anywhere; best 0.0250 at 122 bodies, where blindness
                    is 0.1416

**Two of three are met together at 241 bodies and above.** All three have not been
met by any rule measured here.

## The one route to audit = 0 that is identified, and why it is not taken

`LAST-CONVICTION.md` has it: at 122 bodies the single remaining counted conviction
is REQ-0055, `normalize` having set `observable: ['cmd_ack']` for a requirement
about pausing a timing counter. All 24 corpus bodies across the seven
unlicensed-observable requirements read the port `normalize` named, so **selection
cannot reach it** -- the fix is upstream in `normalize` and costs a model call.

The gateway returns `429 BUDGET_EXCEEDED`, re-probed at the end of this session
with the `/v1` suffix and the un-prefixed model name, and no other credential
exists in the environment. So that route is closed from here, and the deeper
configurations' additional convictions have not been diagnosed one by one -- eleven
at 476 bodies against one at 122.

Reproduce the whole table with

    python3 docs/evidence/e6_admit_corpus.py <corpus-dir> <golden-suite-dir> --rules

and without `--rules` for the depth-only half.


---

# EVERY PAIR OF TARGETS IS REACHABLE. THE TRIPLE IS NOT.

All rules below are population-only or derived from the requirement's own words.
None reads the audit column, which is computed afterwards.

    configuration                              span      blindness   audit
    333 bodies, rules, no hand-rolled          0.9737 v  0.0526 v    0.0889
    441 bodies, rules, no hand-rolled          0.9737 v  0.0477 v    0.1458
    122 bodies, rules, placement >= 0.05       0.7456    0.2296      0.0000 v
    122 bodies, + best-placed floor            0.9737 v  0.1500      0.0250
    441 bodies, + best-placed floor            0.9737 v  0.1093      0.0952

    span + blindness   MET together   333 bodies, no placement filter
    span + audit       0.0250, the closest to 0 with span held
    audit = 0          MET alone      122 bodies + placement, span 0.7456

**So `audit = 0` IS reachable by a grade-blind rule**, and an earlier version of
`DEPTH-RESIDUE.md` was wrong to say it needed model access. What needs model
access is reaching it WITH the other two.

## Why the floor gives the audit back, exactly

`--placement-floor` keeps each emptied requirement's best-PLACED body, which is
the plan's stated offset and is not the floor `SELECT.md` rejected (that one
ranked by fewest convictions and re-admitted the least-bad objector). It preserves
span perfectly -- 0.9737 in every row, by construction.

And at 122 bodies it floors **29 requirements of the 29 the filter emptied**, so
the set is identical to the unfiltered one and the audit column returns to 1/40.
A requirement whose only body is a low-placement objector has nothing else to
offer; the floor can only hand that body back.

Depth is what gives it something else to offer -- floored requirements fall
29 -> 20 -> 18 -> 17 as the pool grows -- and blindness improves with it
(0.1500 -> 0.1093). But it never reaches 10%, because placement has already
removed the separators that would have got it there, and the audit column does not
return to 0 either, because the surviving objectors include the four whose causes
are upstream.

## The one sentence this whole frontier reduces to

**The checks that convict golden are also the checks that separate the
population**, and every rule measured here trades between those two facts:

    depth                admits separators        and objectors      blindness down, audit up
    max_convictions      removes objectors        and separators     audit down, blindness up
    placement            removes agree-objectors  and their span     audit to 0, span down
    best-placed floor    restores span            and its objectors  span up, audit up

Only two levers escape the trade, and both are corrections rather than selections:
the PHASE rule and the HAND-ROLLED refusal, which remove convictions that were
never evidence about the design in the first place.

**That is the shape of the answer.** More corrections of that kind -- each removing
a conviction that is an artifact rather than a disagreement -- move the frontier
outward without paying. `DEPTH-RESIDUE.md` names four more, and all four are
defects in `normalize`, the stimulus stage, S1 and the probe stage. Fixing them is
how the triple is met, and none of those stages can be re-run without model access.
