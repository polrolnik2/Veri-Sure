# CEIL editor report — or1200_dc_fsm

Start: 155 objecting of 502. End (latched, accepted): **86 objecting of 502**
(407 → 417 on the broader passing-requirements count the ratchet also reports).
21 trials available; 15 spent (2 latched, 13 rejected-but-informative).

Note on requirement sentences: every `report`/`failing` call returned
`"sentence": ""` and `"requirement": "... requirement text unavailable"` for
every check, in every trial, from the first call onward. I never had access
to the specification sentence itself — only each check's own generated
`check_said` narrative and its `ports` list. Everything below that would
normally quote "the sentence" quotes `check_said` instead, since that is all
the tool ever gave me.

## Commit 1 — LATCHED (155 → 96 objecting)

Root-caused from `report`/`focus`/`blocks`/`readblock` on the initial 155
objections, all clustering on `biu_read`, `burst`, `dc_addr`, `dcram_we`,
`tag_we` at the same handful of testpoints/edges. Three structural bugs, one
shared root cause:

1. **Dead first-word capture.** `load_miss_in_cload` required `~load_r`, but
   `load_r` is set the same cycle the FSM enters `CLOAD` (same block that
   sets `hitmiss_eval_r`), so it is already `1` by the time `state==CLOAD` is
   ever observed. The guard could never be satisfied — `first_word_load_miss`
   was dead code, so the refill's word count (`cnt`) and address increment
   never initialized correctly.
2. **A spurious extra "bubble" cycle.** The `CLOAD` case's miss branch did
   `next_state = CLOAD` unconditionally, without checking `biudata_valid`, so
   even after the first word arrived the FSM stayed in `CLOAD` one extra
   cycle before moving to `LREFILL3` — dropping `burst` for exactly that
   cycle (confirmed against `TP-0009`, `check_said`: *"hit/miss evaluation ...
   so the transfer ... belongs to the refill burst, yet burst=0 there"*).
3. **Cache-inhibited accesses resolved like tag hits.** `CLOAD`'s decision
   branch treated `is_hit || cache_inhibited` identically — going straight to
   `IDLE` the cycle after entry — instead of waiting for the actual BIU
   response for a CI access. Confirmed by a consensus split at `TP-0011`
   (`ci_i=1`, `tagcomp_miss=0`, `biudata_valid=0`): seven designs show
   `first_hit_ack=0`, this design produced `1`. Also, on top of that, several
   outputs (`load_hit`, `biu_read`'s miss term, `burst_load`) gated on the
   *registered* `cache_inhibit_r`, which lags the live `cache_inhibited` wire
   by exactly one cycle (it's explicitly cleared on entry and only set the
   following cycle) — so the very decision cycle for a CI access was
   evaluated with a stale "not inhibited" reading.

Fix: dropped `~load_r`; restructured `CLOAD`'s decision to check
`biudata_valid` before deciding hit/miss/CI outcome (no more bubble cycle,
CI now waits for the real response); switched the decision-cycle uses of
`cache_inhibit_r` to the live `cache_inhibited` wire; corrected
`cnt <= OR1200_DCLS - 2` to `OR1200_DCLS - 1` (four words per line: one
captured during `CLOAD`, three more in `LREFILL3`); added a CI term to
`biu_read` (it had **no** term asserting it for cache-inhibited loads at
all — the read was simply never issued for CI accesses).

Result: `checks_objecting` 155 → 96. `cells_disagreeing_with_the_consensus`
9857 → 3847.

## Commits 2–9 — rejected, but each isolated a real fact

These did not latch (they never simultaneously beat the 96-objecting
baseline), but each pinned down something true that fed the final design:

- **`dc_addr` when `dc_en=0`.** Disagreement at `TP-0002` (`dc_en=0`,
  `cycstb=1`, `start_addr=4096`): seven designs show `dc_addr=4096`, this
  design showed `0`, because `dc_addr`'s mux only ever looked at
  `hitmiss_eval_r`, which never gets set when `dc_en=0` (the FSM can't leave
  `IDLE`). A broad `~dc_en ? start_addr : ...` overshot — it also fired with
  no live request (`cycstb=0`), producing garbage instead of holding
  `saved_addr_r`; narrowing to `(~dc_en && dcqmem_cycstb_i) || hitmiss_eval_r`
  fixed both without regressing the other. **Kept in the final design.**
- **Simultaneous `biudata_valid` + `biudata_error`.** Disagreement at
  `TP-0005`: with both asserted, seven designs hold `saved_addr` at its
  pre-refill value; this design still advanced it, because
  `first_word_load_miss`, `store_hit_response`/`store_miss_response`, and the
  `LREFILL3`/`SREFILL4` word-received blocks all keyed only on
  `biudata_valid`, never excluding a simultaneous error. Added `~biudata_error`
  to each. **Kept.**
- **`abort_request` checked throughout the wait, not just at the decision.**
  This is the fix that mattered most and took the most trials to find. Once
  a `CLOAD`/`CSTORE` access is decided (even the *same* cycle, since
  `biu_read`/`biu_write` assert immediately), the read/write is already
  outstanding on the external bus — it cannot be un-issued. But
  `abort_request (~dcqmem_cycstb_i)` was checked unconditionally on every
  cycle of `CLOAD`/`CSTORE`, so a `dcqmem_cycstb_i` deassert anywhere in a
  long wait yanked the FSM back to `IDLE` mid-transaction. This is exactly
  `R2::REQ-0001/0002/0012@biu_write` (`TP-0047`/`TP-0050`,
  `check_said`: *"the FSM left CSTORE for IDLE and dropped biu_write although
  ... the request was still being presented ... and no external transfer had
  complet[ed]"*) and the `TP-0030`/`TP-0127`/`TP-9203` `biu_read`/`burst`
  failures (*"neither biudata_valid nor biudata_error returned, yet the FSM
  went back to IDLE"*). Removing `abort_request` from `CLOAD`/`CSTORE`
  entirely over-corrected (it broke `saved_addr` broadly — a *real* abort,
  where the CPU truly withdraws before anything is issued, must still work
  on the decision cycle). The fix that actually held: honor
  `abort_request` only on the one-cycle decision, ignore it for the rest of
  the wait. **Kept**, and refined further in the final commit (see below).
- Confirmed **`OR1200_DC_STORE_REFILL` is not compiled** in this harness — a
  `cnt <= OR1200_DCLS - 1` → `OR1200_DCLS` edit to the (dead) `SREFILL4`-entry
  path had exactly zero effect on any run, twice. Left the corrected value in
  since it's a straightforward reading of that block's own comment
  ("`saved_addr_r[3:2]` NOT incremented on entry to `SREFILL4`" — i.e. zero
  words pre-consumed, unlike the `CLOAD`→`LREFILL3` path — so it needs the
  full line count, not line-count-minus-one) but it is inert either way.

## Commit "committed_r" — LATCHED (96 → 86 objecting)

The `abort_request`-only-on-decision fix (and a parallel fix for the same
"decision made once, then must not re-examine live inputs" problem in
`load_miss_in_cload`/`burst_load`, needed because `tagcomp_miss` is not
stable for the duration of a long wait) both worked by making
`hitmiss_eval_r` itself **one-shot**: cleared unconditionally the cycle after
being set, instead of persisting until `biudata_valid`/`biudata_error` as it
originally did. That combination latched at 407→395 passing in isolation,
then round-tripped downward again once I also touched `first_miss_ack`
timing — while `hitmiss_eval_r`'s *own* clearing timing had changed. That
strongly suggested some of the still-failing checks read `hitmiss_eval`
(the observation port) directly and depend on its original persist-until-
response behavior, which the one-shot rewrite had altered as a side effect
of fixing something unrelated.

The fix: introduce a second, **internal-only** register, `committed_r`,
that captures exactly "the hit/miss/CI decision for this access has already
been made" — set to `0` on entry to `CLOAD`/`CSTORE`, set to `1`
unconditionally the following cycle, and never observable on any port. Use
`committed_r` (not `hitmiss_eval_r`) everywhere the FSM needs to stop
re-examining live `tagcomp_miss`/`cache_inhibited`/`abort_request`
(`CLOAD`'s and `CSTORE`'s next-state decision branches, `load_miss_in_cload`,
`burst_load`). Meanwhile `hitmiss_eval_r` itself was restored to its
*original* semantics — held until `biudata_valid`/`biudata_error`, in both
states — so its own port-facing timing is unchanged from the very first
commit.

This latched: 96 → 86 objecting; 407 → 417 passing. It repaired
`R2::REQ-0001@first_miss_ack`, `R2::REQ-0002@biu_write`,
`R2::REQ-0011@biu_read`, `R2::REQ-0012@biu_write`, `R2::REQ-0012@burst`,
among many `.off@` sub-checks, at the cost of two: `R2::REQ-0002@burst` and
`R2::REQ-0002@tag_we` moved to a new testpoint (`TP-0076`, see below), and
`R2::REQ-0003@dc_addr` appeared newly at the same testpoint. Net, clearly
positive, and this is the accepted design.

## Commits after the latch — all rejected, budget spent chasing two clusters

### `TP-0027`: refill burst ends one word early — unresolved

`biu_read`, `burst`, `dcram_we`, and `tag_we` all diverge from the seven
reference designs at the identical edge in `TP-0027`: our design produces a
clean 3-word-then-stop refill burst; the reference designs hold `burst`
(etc.) for one further edge after the last real `biudata_valid` sample.
Using `explain` (which is live/fresh right after a commit — `failing` is
not; see caveat below) I confirmed with actual signal traces that
`biudata_valid` here is a **held level for four consecutive edges**, not a
discrete pulse per word — my original arithmetic (`cnt <= OR1200_DCLS - 1`,
one word captured in `CLOAD`, three more counted down in `LREFILL3`) uses
exactly those four edges and finishes correctly, with no off-by-one in the
count. The seven reference designs apparently keep the refill-in-progress
outputs asserted for one *additional* edge beyond that — after
`biudata_valid` has already dropped back to `0` — which reads like a
one-cycle drain/flush before returning to `IDLE`, not a fifth data word.

I tried the direct fix (`cnt <= OR1200_DCLS` instead of `OR1200_DCLS - 1`)
under both the pre-`committed_r` and post-`committed_r` architectures. Both
times it made the aggregate result *worse* (395→377, then 417→383), and by
hand-tracing the second attempt I can show why: with one more count needed,
the FSM never reaches its `cnt==1 && biudata_valid` finish condition once
`biudata_valid` drops (there is no more data forthcoming), and `state` gets
stuck in `LREFILL3` forever — a genuine deadlock, not merely a worse
mismatch count. Whatever the seven reference designs do to hold the output
one cycle longer without waiting on a phantom fifth `biudata_valid`, it is
not simply "count one higher," and I did not find it in the remaining
budget. **This is my strongest recommendation for follow-up**: something
that decouples "the last-word decrement has been made" from "return to
`IDLE`" by exactly one cycle, without requiring a further external response.

### `TP-0076`: `load_hit`/`biu_read`'s live-`tagcomp_miss` reads — found the cause, could not land the fix

Separately, `R2::REQ-0002@burst`/`@tag_we` and `R2::REQ-0003@dc_addr` at
`TP-0076` (`check_said`: *"FSM entered LREFILL3 although no first refill word
was returned (biudata_valid=0 in the cycle before the transition), so no tag
was written for it"* / *"burst=0 while the FSM is in a cache-line refill
state"*) traced to `load_hit`, which I had **not** migrated to `committed_r`
along with everything else — it still reads `hitmiss_eval_r && is_hit`
directly. Since `hitmiss_eval_r` (correctly, per above) persists for the
whole wait, and `tagcomp_miss` is not stable for that whole wait (the same
fact that motivated `committed_r` in the first place), `load_hit` can fire
*mid-wait* on a stale `is_hit` reading, wrongly clearing `load_r` out from
under an in-progress refill and explaining all three symptoms at once
(`dc_addr` jumps because `saved_addr_r`'s bookkeeping is corrupted mid-burst;
`burst`/`tag_we` drop because `load_r` cleared early while `state` is still
`LREFILL3`).

`biu_read`'s first term has the identical shape
(`hitmiss_eval_r && (is_miss || cache_inhibited)`) and the same exposure.

I moved both to `~committed_r`/`committed_r` (matching `load_miss_in_cload`
and `burst_load`, which already use this pattern successfully). Tested three
ways — `load_hit` and `biu_read` together, then `load_hit` alone — and both
times the aggregate result got *worse* (417→388, 417→389) even though
`TP-0076`'s specific symptoms were confirmed fixed (`R2::REQ-0002@burst` and
`R2::REQ-0003@dc_addr` left the broken list both times). What came back
broken instead: `R2::REQ-0002@first_miss_ack`, `R2::REQ-0011@first_miss_ack`
(previously fixed by the `committed_r` latch), and, in the combined attempt,
a new `REQ-0065@first_hit_ack`. So `load_hit` legitimately needs to fire in
at least one scenario where `committed_r` is already `1` — i.e., a hit that
is only decidable after the one-cycle window I've been treating as "the
decision cycle" for every other purpose. I could not characterize that
scenario with the trials remaining, so I reverted both attempts and left
`load_hit`/`biu_read`'s first term as they were at the successful latch.
**Second recommendation for follow-up**: whatever makes a hit resolve on a
cycle after entry needs its own, narrower carve-out — not a blanket swap to
`committed_r` — probably keyed on some condition I haven't isolated (address
timing? a different, later "hit" indication distinct from `tagcomp_miss`?).

### A likely genuine tension, not chased further

`REQ-0002.off@55e6ead02997` (`TP-0062`, `check_said`: *"biu_write and
first_miss_ack both asserted"*) — `first_miss_ack` legitimately must assert
on a `CSTORE` write-through's completion cycle (that is exactly what
`R2::REQ-0001@first_miss_ack` requires, and is now fixed), but `biu_write
(=store_r)` has not yet cleared on that same cycle (it clears the cycle
*after*, via the generic `next_state==IDLE` flag-clear). Making these
mutually exclusive as this check wants, without breaking
`R2::REQ-0001@first_miss_ack`'s requirement that the ack land exactly on the
completion cycle, looks like it needs `biu_write` to drop one cycle earlier
than "the write completed" — which I could not justify from anything else in
the design without more information. Flagging it rather than guessing.

## Tooling caveat that cost real trials

`report`, `failing`, and `explain` are **not live views of the staged
buffer** — `report.json`/`failing`'s underlying data only refresh on an
actual `commit` call (latched or not), and `explain`'s per-testpoint detail
likewise reflects the *last committed attempt*, not anything staged since.
`check` and `status`'s `staged`/`trials_used` fields are the only things
that update between commits. I lost real turns early on assuming
`report`/`explain` reflected my currently-staged edits; once I understood
this, I stopped trying to "preview" a fix for free and just accepted that
verifying anything costs a trial.

## Final state

Accepted (latched) design: `checks_objecting = 86` of 502 (down from 155 at
start), `cells_disagreeing_with_the_consensus = 4169` (down from 9857 at
start; not scored, shown for context only). 6 of 21 trials remained unspent
at stop — all recent attempts to close the two remaining clusters above were
net-negative and reverted (`discard`), so the accepted RTL was left at its
best-known state rather than gambling the last trials on more guesses in the
same two spots.
