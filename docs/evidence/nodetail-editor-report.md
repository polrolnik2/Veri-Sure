# ND editor report — or1200_dc_fsm

Starting point: **155 objections of 502** (`checks_objecting`), 348 passing
requirements, 9,857 cells disagreeing with the nine-implementation consensus.

Final accepted state, after 18 of 21 trials (3 left unspent): **122 objections
of 502**, 381 passing requirements — a reduction of 33 checks (21%). Every
number below is `checks_objecting` from `report`, read immediately after each
`commit` and before any further edit, so it reflects exactly that trial's run.

**Important measurement note, discovered the hard way:** the brief states
`checks_objecting` "is the only thing in the latch." Empirically, in this
harness `commit`'s own accept/reject decision is driven by a broader
`passing requirements` count that also includes the ten legacy per-output
"does this design ever disagree with the 7/9-way consensus" pseudo-requirements
(the same consensus data the brief says "no longer counts toward anything").
Several of my commits moved `checks_objecting` and `passing requirements` in
*opposite* directions (see trials 3, 5, 6 below). I kept `checks_objecting`
as the metric that decides whether a change is "good," but a change can only
become part of the accepted RTL if it also satisfies the tool's own
`passing requirements` ratchet — I could not get a checks-objecting
improvement to stick unless it also cleared that bar.

## Commits, in order

1. **Trial 1 — large combined batch. REJECTED, discarded.**
   `~load_r` → `load_r` in `load_miss_in_cload`; `OR1200_DCLS-2` →
   `OR1200_DCLS-1` for the load-refill word count; a full rework of
   `cache_inhibit_r`'s latch timing (captured at IDLE-exit instead of one
   cycle late) plus splitting `CLOAD`'s cache-inhibited path out of the
   hit/miss branch; a `first_miss_ack` redefinition around
   `load_refill_complete`/`store_refill_complete`; and a state-based rewrite
   of `dc_addr`. Passing requirements 348 → 309. Too many simultaneous
   changes to attribute the regression, so I broke it apart from here on and
   tested pieces individually.

2. **Trial 2 — `load_miss_in_cload`'s `~load_r`→`load_r`, plus a `burst`
   gap term. LATCHED.** 348 → 352 passing.
   `load_miss_in_cload` gated the first refill word on `~load_r`, but
   `load_r` is already 1 throughout `CLOAD` for a load (set on IDLE-exit),
   so the term could never fire — `first_word_load_miss` never ran, `cnt`
   and `saved_addr_r` never advanced, and the refill collapsed to one word.
   Fixing the inversion also exposed that `burst` had no term for the cycle
   after `hitmiss_eval_r` clears but before `state` has registered
   `LREFILL3` (the same window `biu_read` already had a dedicated term for)
   — added `burst_load_gap` to match.

3. **Trial 3 — refill word count off-by-one. LATCHED.** 352 → 355 passing.
   `cnt <= OR1200_DCLS - 2` on entering refill undercounts by one: one word
   is taken in `CLOAD` via `first_word_load_miss`, so `OR1200_DCLS-1` more
   remain in `LREFILL3` (matching the `SREFILL4` entry, which already used
   `OR1200_DCLS-1` because it hasn't taken any words yet). Read afterward:
   `checks_objecting` was **175** here — *worse* than the 155 starting
   point, despite two latched, requirement-improving commits. This is the
   first evidence of the metric split described above.

4. **Trial 4 — full `cache_inhibit_r` rework (timing change + `CLOAD`
   split), on top of trial 3. REJECTED, discarded.** 355 → 327 passing;
   `checks_objecting` 175 → 190 (worse on both).

5. **Trial 5 — `first_miss_ack` redefinition alone
   (`load_refill_complete || store_refill_complete`/`store_miss_response`),
   on top of trial 3. REJECTED, kept staged.** 355 → 336 passing, but
   `checks_objecting` **167** (better than 175). Directionally right, net
   negative on requirements.

6. **Trial 6 — added the full `cache_inhibit_r` rework on top of trial 5.
   REJECTED, discarded (back to trial 3's state).** 355 → 312 passing;
   `checks_objecting` 190. Confirms the full `cache_inhibit_r` timing
   rewrite is the wrong shape of fix, not just badly combined — it lost on
   `checks_objecting` twice, independently.

7. **Trial 7 — narrow `dc_addr` fix. LATCHED.** 355 → 356 passing.
   `dc_addr = hitmiss_eval_r ? start_addr : saved_addr_r` shows a stale (or
   zero, pre-reset) `saved_addr_r` while genuinely idle — a request with
   `dc_en=0` still needs `dc_addr` to track the live `start_addr`. Changed
   only the `IDLE` case: `(state == IDLE || hitmiss_eval_r) ? start_addr :
   saved_addr_r`, leaving the already-correct gap-cycle behavior alone.
   `checks_objecting`: **147** — the first result under the original 155.

8. **Trial 8 — cache-inhibited access handling. LATCHED.** 356 → 370
   passing. `cache_inhibit_r` only latches one cycle into `CLOAD`/`CSTORE`
   (correctly, per the sequential block), so on that first cycle a CI
   access isn't yet recognized as one. Rather than changing that timing
   (trials 4/6 showed that breaks things), added
   `cache_inhibit_now = cache_inhibit_r || (hitmiss_eval_r && cache_inhibited)`
   — a same-cycle OR with the live signal — used only in the FSM's own
   decisions (`load_miss_in_cload`, `load_hit`, `burst_load`, `biu_read`,
   `tag_we`, `load_refill_write`); `cache_inhibit_r`/`cache_inhibit_flag`
   themselves are untouched. Also fixed `CLOAD`'s
   `if (is_hit || cache_inhibited) next_state = IDLE` — a cache-inhibited
   access has no hit/miss to speak of and was completing before the BIU
   even responded; split it into its own branch that waits for
   `biudata_valid`. Added a matching `biu_read` term so a CI load keeps
   requesting while it waits. `checks_objecting`: **133**.

9. **Trial 9 — back-to-back requests skip IDLE, applied everywhere.
   REJECTED, discarded.** 370 → 336 passing; `checks_objecting` 166
   (worse). Evidence for the underlying idea (below) is real, but applying
   it uniformly at all twelve `next_state = IDLE` sites broke far more than
   it fixed — see trial 15 for the version that actually works.

10. **Trial 10 — error response excluded from hit/miss completion.
    LATCHED.** 370 → 372 passing. `store_hit_response`/
    `store_miss_response`/`load_hit` didn't check `biudata_error`, so a
    response that carried both `biudata_valid` and `biudata_error` was
    treated as a genuine hit or miss completion *in addition to* being
    flagged as an error — `first_hit_ack` and `first_miss_err` could both
    fire on the same edge. Added `&& ~biudata_error` to all three.
    `checks_objecting`: **131**.

11. **Trial 11 — excluded the `CLOAD`-gap cycle from `dcram_we`/`tag_we`.
    REJECTED, discarded.** 372 → 360 passing; `checks_objecting` 143
    (worse). Theory: `load_refill_write`/`tag_we` could re-fire on the
    transitional gap cycle if `biudata_valid` stays high across it. Wrong
    — reverted.

12. **Trial 12 — latch `CLOAD`'s hit/miss verdict after its first cycle.
    REJECTED, discarded.** 372 → 353 passing; `checks_objecting` 150
    (worse). Theory: a long-held miss re-reads live `tagcomp_miss` every
    cycle while waiting, so if it isn't held stable the FSM could
    re-evaluate as a hit mid-wait. No evidence `tagcomp_miss` actually
    moves in these tests; the extra `is_miss_r`/`hitmiss_latched` machinery
    only introduced new timing gaps. Reverted.

13. **Trial 13 — narrower `dc_addr`: only show `start_addr` in `IDLE` when
    `dcqmem_cycstb_i` is actually asserted. NOT LATCHED (unchanged), but
    neutral, kept staged.** 372 → 372 passing (no change);
    `checks_objecting` **131** (no change) — noisy only on the deprecated
    consensus count. Revisited successfully in trial 18.

14. **Trial 14 — narrowed `first_miss_ack` in place
    (`&& is_miss && ~biudata_error`) instead of trial 5's full
    redefinition. REJECTED, discarded.** 372 → 360 passing;
    `checks_objecting` 143 (worse). The existing broad `first_miss_ack`
    is apparently relied on by other passing checks; neither this nor
    trial 5's full redefinition of it holds up. I could not find a
    working replacement and left the field as originally written.

15. **Trial 15 — back-to-back requests skip IDLE, scoped to just the
    `LREFILL3`/`SREFILL4` completion sites. LATCHED.** 372 → 376 passing.
    The same idea as trial 9, but only at the two sites where a refill
    (not a hit, not a cache-inhibited completion) finishes: added a
    `completing` flag set alongside `next_state` there, and a
    `pending_request_state` wire so a refill that finishes with another
    request already asserted (`dc_en && dcqmem_cycstb_i` still held) falls
    straight into `CLOAD`/`CSTORE` instead of taking a visible `IDLE`
    cycle; broadened the request-capture condition in the sequential block
    to `state == IDLE || completing`. `checks_objecting`: **127**.

16. **Trial 16 — extended trial 15's `completing` treatment to the
    cache-inhibited-load completion site too. REJECTED, discarded.**
    376 → 369 passing; `checks_objecting` 134 (worse). The skip-IDLE
    behavior is specific to refill completions; it does not generalize to
    single-cycle completions.

17. **Trial 17 — error response excluded from the first refill word.
    LATCHED.** 376 → 380 passing. `first_word_load_miss` didn't check
    `biudata_error` either (same class of bug as trial 10): a response
    carrying both `biudata_valid` and `biudata_error` was wrongly treated
    as the first real refill word, advancing `saved_addr_r`/`cnt` on an
    error. Added `&& ~biudata_error`. `checks_objecting`: **123**.

18. **Trial 18 — re-tried trial 13's `dc_addr` refinement on the new
    baseline. LATCHED.** 380 → 381 passing. Same change as trial 13
    (`(hitmiss_eval_r || (state == IDLE && dcqmem_cycstb_i)) ? start_addr :
    saved_addr_r`); this time it cleared the ratchet. `checks_objecting`:
    **122** — the final accepted state.

Trials 19–21 were left unspent: three more speculative variants in this same
area (extending trial 15's pattern, another `first_miss_ack` shape, a
`dc_addr` variant) were the only remaining ideas I had evidence for, and each
of the last several attempts along those exact lines (11, 12, 14, 16) had
made things worse. Given the accumulating fragility, I judged further guesses
in the same territory more likely to cost a trial than to help, and stopped
to write this report while the accepted state was solid.

## Commits the ratchet refused that I believe were correct

None outright. Trial 13's `dc_addr` refinement (trial 18's eventual, working
version) is the closest case: it was directionally right and
`checks_objecting`-neutral when first tried, but I would not call a neutral
result "correct and refused" — it simply hadn't paid off yet. Every other
rejected trial (4, 6, 9, 11, 12, 14, 16) also made `checks_objecting` worse,
not just the broader ratchet, so I do not believe any of them were correct.

## Checks I could not resolve, with the sentence quoted

**`TP-0047` (a `CSTORE` write-through, held with no error): `biu_write` and
`first_miss_ack`/`first_hit_ack` drop or never assert although nothing in the
FSM's `CSTORE` case should let that happen.** Representative check text
(truncated at 160 characters by the tool itself):

- `R2::REQ-0001@biu_write`: *"a store was under hit/miss evaluation in CSTORE
  at edge 7 (request held, no BIU error), so its write-through transaction
  was only being presented that cycle; at"*
- `R2::REQ-0002@biu_write`: *"edge 7: biu_write was dropped at the next edge
  although the write-through response had not arrived (biudata_valid=0,
  biudata_error=0) and the store request was "*
- `R2::REQ-0012@biu_write`: *"the FSM left CSTORE for IDLE and dropped
  biu_write although at edge 7 the request was still being presented,
  biudata_error=0 and no external transfer had comple"*
- `R2::REQ-0001@first_miss_ack`: *"CSTORE left for IDLE after edge 7 with
  first_miss_ack=0 first_miss_err=0 (biudata_valid=0, biudata_error=0): the
  write-through was completed without acknowledgi"*

I read `CSTORE`'s `next_state` logic line by line repeatedly: with
`abort_request` and `error_response` both false and `hitmiss_eval_r` true,
the only paths are "wait" (`biudata_valid` false) or a real completion
(`biudata_valid` true) — there is no way, as written, to reach
`next_state = IDLE` under the stated conditions. I could not identify what
actually drives this transition; it is possible (given the "edges are
collapsed runs" caveat in `explain`'s own output) that the `dc_addr`-style
already-pending-request pattern from trials 9/15 applies here too in a form
I didn't find, but my one attempt at extending that pattern past refill
completions (trial 16) made things worse rather than better.

**`TP-0127` / `TP-9203` (a held, non-cache-inhibited load miss): `biu_read`
and `burst` drop although the request is still asserted, no error, no
response yet.**

- `R2::REQ-0002@biu_read`: *"edge 7: biu_read=1 for a cacheable miss with the
  request still asserted and neither biudata_valid nor biudata_error
  returned, yet the FSM went back to IDLE at t"*
- `R2::REQ-0011@biu_read`: *"tagcomp_miss=1 had marked this non-cache-
  inhibited access a miss and the read for it was outstanding at edge 7, yet
  the FSM is back in IDLE with biu_read=0 with"*
- `R2::REQ-0012@burst`: *"the refill burst that was running at edge 7 is
  abandoned - the FSM is in IDLE with burst=0 - although the request was not
  aborted (dcqmem_cycstb_i=1), biudata_e"*
- `R2::REQ-0010@biu_read` / `@burst` (`TP-9203`): *"biu_read=0 at edge 23,
  the edge on which the first BIU response (valid=1 err=0) is returned for a
  held non-cache-inhibited load miss at start_addr=12480; the FS"* /
  *"burst=0 at edge 23 while a non-cache-inhibited load miss on
  start_addr=12480 is still outstanding (no BIU response seen yet)"*

Same shape as the `TP-0047` family: `CLOAD`'s "stay for a miss" branch
(`else if (is_miss) next_state = CLOAD`) has no route to `IDLE` under the
stated conditions either. I tried freezing the hit/miss verdict after the
first evaluation cycle (trial 12) on the theory that a live re-read of
`tagcomp_miss` was the culprit; it made things worse, which is evidence
against that specific theory, not for it. I did not find the actual
mechanism.

**Residual `burst`/`biu_read`/`tag_we`/`dcram_we` tail-of-refill disagreement
(`TP-0036` and kin).** Before trial 15, `explain burst` on this testpoint
showed the design dropping `burst` to 0 for one cycle at the tail of a
refill where the seven-design consensus keeps it at 1 (a back-to-back
pattern — a second load-miss request, held on the same `dcqmem_cycstb_i`
that never dropped, starting immediately). Trial 15 addressed the
`LREFILL3`/`SREFILL4` version of that pattern; re-checking after it landed,
the same testpoint's divergence has moved (`explain burst` now flags
edge 24 instead of edge 13, and with the sense of the mismatch flipped —
consensus now wants 0 where the design gives 1), suggesting a second,
related instance of the pattern later in the same trace that trial 15's
narrower fix doesn't reach. I did not chase this further given the
budget remaining and the fact that widening trial 15's fix in the two ways
I could think of (trial 9, trial 16) both regressed.

**`first_miss_ack` at `TP-0009`.** Consensus says `first_miss_ack` should be
0 on the cycle the first load-refill word arrives (still mid-`CLOAD`, before
`LREFILL3` is registered); the design gives 1, because `first_miss_ack`'s
condition is simply `(state == CLOAD || state == CSTORE) && biudata_valid`
with no `is_miss`/`is_hit` distinction at all. Two attempts to narrow or
redefine this (trials 5 and 14) each fixed this class of case but broke a
larger number of other, currently-passing checks and legacy requirements —
the existing broad formula is evidently relied upon elsewhere in a way I did
not manage to reconcile with the `TP-0009` expectation. Left as originally
written.

## Files

- `dut.v` in `loopND/` — the accepted RTL, 122/502 objections.
- This file, `ND_EDITOR_REPORT.md`, in the working directory
  (`/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/e0d`).
