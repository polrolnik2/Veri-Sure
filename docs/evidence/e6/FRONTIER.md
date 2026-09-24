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
