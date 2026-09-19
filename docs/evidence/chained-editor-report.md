# CHAIN editor report

Loop: `loopCHAIN` (CEIL-brief rules, `./chaincli.sh`). Started at **84 objections of
502** (421 passing requirements at init). Ended at **431 -> 442 passing
requirements** on the accepted RTL (last accepted commit), with checks_objecting
tracked via `report`/commit deltas going **84 -> 82 -> 76 -> 74 -> 63**. 16 of 21
trials used; 4 commits latched, 12 were refused and discarded, leaving 5 trials
unspent because every further idea I could test cost more than it gained (see
"Where I stopped" below).

All work was done through `focus`/`explain`/`blocks`/`readblock`/`show`/`edit`/
`check`/`commit`, per the brief. No reference implementation, other loop
directory, log, or report file was opened.

## The design as I found it

`or1200_dc_fsm` (IDLE/CLOAD/CSTORE/LREFILL3/SREFILL4) had already been repaired
once. Its remaining defects clustered around two structural ideas the previous
editor got half right:

1. **`tagcomp_miss`/`dcqmem_ci_i` are only valid for one cycle** (the
   `hitmiss_eval_r` cycle right after a request is accepted), but several
   combinational terms kept re-reading them live for the whole wait, so a
   later, unrelated change in those signals (the tag/CI path moving on to
   probe something else) could flip a decision that had already been made.
2. **`dcqmem_cycstb_i` dropping was treated as "abort" everywhere**
   (`abort_request = ~dcqmem_cycstb_i`, checked in all four non-IDLE states),
   but a lot of the suite's stimulus drops `dcqmem_cycstb_i` the cycle after a
   request is accepted as a matter of course (single-cycle request pulses),
   which is not the same thing as the CPU cancelling a transfer that is
   already running on the bus.

## Commits, in order

### 1. REJECTED - combined hit/miss latch + abort removal (trial 1)
Introduced a `miss_r`/`cache_inhibit_r` latch keyed off `hitmiss_eval_r` for
*all* of CLOAD/CSTORE's hit/miss/CI decisions, and removed `abort_request`
from all four non-IDLE states at once. Passing 421 -> 373. Too many
independent ideas in one commit to tell which part helped; discarded rather
than committed a worse RTL.

### 2. REJECTED - same idea, abort restored (trial 2)
Kept the latch, put `abort_request` back. Passing 421 -> 383. Confirms the
latch-everything idea was itself a net loss on its own (broke `tag_we`,
`first_miss_ack` and a dozen `.off` checks it hadn't touched before) -
discarded.

### 3. REJECTED - abort removed everywhere, no latch (trial 3)
Isolated the other half of commit 1: drop `abort_request` from CLOAD, CSTORE,
LREFILL3 and SREFILL4, nothing else changed. Passing 421 -> 382, cell
mismatches actually fell a lot (2686 -> 1740), but the "requirements" ratchet
still went down: unconditional removal in **CLOAD and CSTORE** breaks a
cluster of checks (`REQ-0008.off`, the `.shipping`/`.band`/`.merge` consensus
units, `R2::REQ-0002@burst`) every time, in every variant tried later too.
Discarded.

### 4. REJECTED - `abort_request = ~dc_en` instead of `~dcqmem_cycstb_i` (trial 4)
Hypothesis: the sticky "cache enabled" signal, not the per-request strobe, is
the right abort source. Worse in every dimension (421 -> 372, cell mismatches
up to 4174). `dc_en` toggles just as often as `dcqmem_cycstb_i` in this
suite's stimulus, so it isn't a distinguishing signal either. Discarded.

### 5. ACCEPTED - cache-inhibited load never drove `biu_read` (trial 5)
**LATCHED. 421 -> 423 passing.**
`load_miss_in_cload` (the only term feeding `biu_read` besides the LREFILL3
term) requires `~cache_inhibit_r`, so a genuinely cache-inhibited load had
*no* term left to assert `biu_read` for the whole time it sat in CLOAD waiting
for `biudata_valid` (real OR1200 behaviour: a cache-inhibited access still
has to go out on the bus). Added
```verilog
wire ci_load_active = (state == CLOAD) && load_r && (cache_inhibit_r || cache_inhibited);
assign biu_read = load_miss_in_cload || ci_load_active || (state == LREFILL3 && load_r);
```
purely additive (only turns `biu_read` on in cases where nothing turned it on
before), so it could not regress the miss path. Repaired `REQ-0002.off`
("access presented but no outcome classification signals asserted") and six
`REQ-0010.off` instances; broke `REQ-0002.off@e4bf1fee0b5b`,
`REQ-0006.off@56198947baa3`, `REQ-0012.off@0f17bd3c12b4`, two `REQ-0067.off`
instances - net +2, and the fifth commit total but the first one that
latched.

### 6. ACCEPTED - refill word count was off by one (trial 6)
**LATCHED. 423 -> 429 passing.**
`first_word_load_miss` (the first refill word, delivered while still in
CLOAD) sets `cnt <= OR1200_DCLS` on entry to LREFILL3. LREFILL3's own loop
then needs `cnt` to walk down to 1 before it will leave, i.e. it waits for
`OR1200_DCLS` *more* words - so the design fetched `1 + OR1200_DCLS = 5` words
for a 4-word line. The store-refill entry path a few lines down already gets
this right (`cnt <= OR1200_DCLS - 1`, with the comment "one word was already
delivered"); the load path just didn't match it. Fixed to
`cnt <= OR1200_DCLS - 1` for symmetry with the (already-correct) store path.
Zero broken; repaired 6 checks (`REQ-0006.off`, two `REQ-0010.off`, two
`REQ-0012.off`, `REQ-0067.off`).

### 7. REJECTED - CSTORE-only abort removal (trial 7)
Isolated CSTORE from the earlier all-states removal, to see if the CLOAD side
was the one causing the collateral damage. Passing 429 -> 401: CSTORE alone
reproduces almost the identical broken cluster (`REQ-0008.off`,
`R2::REQ-0002@burst`, `R2::REQ-0007@biu_write`, `.shipping`/`.band`/`.merge`).
Discarded.

### 8. REJECTED - exclude live `cache_inhibited` from `load_miss_in_cload` (trial 8)
Root-caused a live race: `R2::REQ-0003@dc_addr`'s failing trace showed
`dcqmem_ci_i` going live-1 on the *exact* edge `biudata_valid` arrived, before
`cache_inhibit_r` had latched it - `next_state`'s own `cache_inhibited`
(live) branch treats that edge as a CI-access completion, while
`load_miss_in_cload` (gated only on the *registered* `cache_inhibit_r`, still
0 that cycle) fires anyway, so the address-step and the CI completion both act
on the same edge and `saved_addr_r` oscillates (8192/8196/8192/8196...).
Tried excluding live `cache_inhibited` from `load_miss_in_cload` itself
(`~(cache_inhibit_r || cache_inhibited)`), which also gates `biu_read`/`burst`
through the same wire - too broad: fixed `R2::REQ-0003@dc_addr` but broke
three `REQ-0037.off` burst-consistency checks that depend on `burst` staying
on `cache_inhibit_r` alone. Discarded in favour of #9.

### 9. ACCEPTED - narrower version: guard only the address step (trial 9)
**LATCHED. 429 -> 431 passing.**
Same diagnosis as #8, but the exclusion only guards `first_word_load_miss`
(the address-incrementing term), leaving `load_miss_in_cload` itself (and so
`biu_read`/`burst`) untouched:
```verilog
wire first_word_load_miss = load_miss_in_cload && biudata_valid && ~cache_inhibited;
```
Zero broken; repaired `R2::REQ-0003@dc_addr` and `REQ-0067.off@ae76661ecf6d`.

### 10-13. REJECTED - `abort_request` suppressed only once the transfer is under way (trials 10, 11, 12, 13)
Reasoning: `dcqmem_cycstb_i` dropping is only ambiguous with a real abort
*before* the FSM has committed to a bus transfer; once `biu_read`/`biu_write`
is actually asserted it should be BIU-owned. Tried, in order: gating all four
states on `~biu_read`/`~biu_write` (10: 431 -> 411, 13 repaired / 32 broken);
CLOAD+LREFILL3+SREFILL4 gated, CSTORE untouched (11: 431 -> 429, 11 repaired /
13 broken - closest to break-even of this family); CLOAD gated alone (12:
431 -> 418, 0 repaired / 14 broken - strictly worse, so the LREFILL3/SREFILL4
part of #11 was doing all the good work, not the CLOAD part); #11's next_state
change plus mirroring the fix into the sequential "Request abort" block that
independently clears `load_r`/`hitmiss_eval_r` on `abort_request` (13:
431 -> 423, 16 repaired / 24 broken - worse than #11, so making the two blocks
"consistent" was not the missing piece either). All four discarded. The
`R2::REQ-0002@burst`, `REQ-0008.off` (about IDLE's own acceptance conditions)
and the `.shipping`/`.merge` consensus-unit cluster broke in every CLOAD- or
CSTORE-touching variant regardless of exact gating, which is why #14 below
tries LREFILL3/SREFILL4 alone with no CLOAD change at all.

### 14. ACCEPTED - `abort_request` removed from LREFILL3/SREFILL4 only (trial 14)
**LATCHED. 431 -> 442 passing. Zero broken.**
`biu_read` is unconditionally 1 throughout LREFILL3 (and would be through
SREFILL4 under `OR1200_DC_STORE_REFILL`) whenever `load_r` is set, so once a
refill burst is actually running it is entirely a BIU-owned transaction - the
CPU's `dcqmem_cycstb_i` has already done its job (accepting the request) and
dropping it afterward is not a cancellation. Removed `abort_request` from
just these two states' `next_state` (kept `error_response`); left CLOAD and
CSTORE's `abort_request` exactly as found. Repaired `R2::REQ-0001@biu_read`,
`R2::REQ-0001@burst`, and eight `.off`/consensus checks; broke nothing. This
is the biggest single win of the run.

### 15. REJECTED - same idea, extended unconditionally into CLOAD (trial 15)
Having seen LREFILL3/SREFILL4 succeed with *unconditional* removal (not
gated), tried the same unconditional removal in CLOAD, on top of #14.
442 -> 429: reproduces the identical CLOAD-touching regression cluster
(`REQ-0008.off`, `R2::REQ-0002@burst`, `.shipping`/`.merge`) seen in trials
10-13. Confirms CLOAD's `abort_request` really is load-bearing for some
scenarios that LREFILL3/SREFILL4's is not, and there is no gating condition
tried so far that keeps the CLOAD-side fixes without this cost. Discarded.

### 16. REJECTED - CSTORE `abort_request` suppressed only during `hitmiss_eval_r` (trial 16)
Narrower than #7 by an order of magnitude: only ignore `abort_request` for the
*one* cycle right after CSTORE is entered (`hitmiss_eval_r == 1`), the cycle
`R2::REQ-0001@biu_write`'s and `R2::REQ-0001@first_miss_ack`'s failing traces
both pin the false abort to, leaving the rest of CSTORE's abort behaviour
untouched. Passing 442 -> 414, 0 repaired, 28 broken - the worst
repaired:broken ratio of any variant tried, despite touching only one cycle
of one state. Discarded.

## Where I stopped, and why (5 trials left unspent)

`failing` still lists (on the accepted RTL): `R2::REQ-0001@biu_write`,
`R2::REQ-0001@first_miss_ack`, `R2::REQ-0002@biu_read`,
`R2::REQ-0002@biu_write`, `R2::REQ-0003@biu_read`, `R2::REQ-0010@biu_read`,
`R2::REQ-0010@burst`, `R2::REQ-0011@biu_read`, `R2::REQ-0012@biu_write`,
`R2::REQ-0012@burst`, and several `REQ-0002.off` instances (all sharing the
requirement "must determine ... whether the access is an immediate load hit,
a load miss ..., a write-through store, ... or a cache-inhibited access").

Every one of the CLOAD/CSTORE items I could get a boundary trace for reduces
to the same story: `dcqmem_cycstb_i` drops one cycle before `biudata_valid`
would have arrived (sometimes literally the very next cycle), the FSM's
`abort_request` treats that as a cancellation, and the check objects that
`biu_read`/`biu_write`/`burst`/`first_miss_ack` was dropped or never asserted
for a transfer that should have been allowed to finish. I believe every one of
these objections is correct - `R2::REQ-0003@biu_read` at TP-0127 is the
cleanest example: `biudata_valid` arrives at the very next edge after the
"abort," with `dc_en` steady at 1 throughout, i.e. the true response was one
cycle away when the design gave up on it.

What I could not find in 6 commits' worth of trials (10, 11, 12, 13, 15, 16
above) is a way to stop CLOAD or CSTORE from treating `dcqmem_cycstb_i` as
abort *only* in the cases these checks care about, without also changing
behaviour for a large, seemingly unrelated cluster that always breaks
together: `REQ-0008.off` (IDLE's own acceptance conditions), the
`.shipping`/`.band`/`.merge` consensus units, and `R2::REQ-0002@burst`. That
cluster broke identically whether I touched CLOAD alone, CSTORE alone, both,
or just one cycle of CSTORE - which tells me it isn't sensitive to *which*
state I change, but to the fact that *some* CLOAD/CSTORE transaction in
whatever long testpoint those checks read now takes longer to reach
`biudata_valid` than it used to (because it can no longer be cut short by a
cycstb pulse), which shifts every later transaction's timing in that same
testpoint far enough to fail a check anchored to an absolute edge. I do not
have a design change that both keeps CLOAD/CSTORE transactions running to
their real completion (which the remaining `R2::REQ-000X` checks want) and
keeps every fixed-window check downstream of them satisfied at its original
edge, and I was not confident enough in a further guess to keep spending
commits on it once two structurally different attempts (gate by `~biu_read`/
`~biu_write`, and gate by `~hitmiss_eval_r` only) both failed by a wide
margin. Per the brief, I am writing this down rather than restructuring the
design around a theory I can't verify: **I believe the remaining
`R2::REQ-0001/0002/0003/0010/0011/0012` objections on `biu_write` and CLOAD's
`biu_read`/`burst` are legitimate, but I do not have a fix for them that
survives the suite as a whole.**

`R2::REQ-0010@biu_read`/`R2::REQ-0010@burst` (TP-9203, edge 30 in the run I
last inspected) looked distinct from the abort cluster at first read -
`dcqmem_cycstb_i` is held the entire window, and the check fires on the exact
edge a mid-burst `biudata_valid` arrives, with `biu_read` dropping for one
cycle and recovering the next. I worked through the LREFILL3 word count by
hand against the accepted `cnt <= OR1200_DCLS - 1` fix (commit #6) and it
comes out consistent with the trace (3 required pulses in LREFILL3, matching
the 3 observed), so I could not identify a further off-by-one to fix here
with the confidence the earlier commits had, and did not want to spend a
trial on an unverified guess this late in the budget. This is the other open
item I'm flagging rather than guessing at.

## Requirement text I could quote

Every `R2::REQ-000X@port` check in this set reports `requirement text
unavailable` (no sentence to quote); I worked from `check_said`, the
boundary traces, and `explain`'s dataflow slice instead, as the brief
anticipates. I found no check whose *sentence* (where one was available, i.e.
the `.off`-family checks) demanded something I believe is wrong - `REQ-0032.off`,
`REQ-0037.off`, `REQ-0008.off` and the others I could read all matched the
design's intended behaviour once I understood the scenario; the disagreements
were with the RTL's implementation, not the requirement.

## Final state

Accepted `dut.v` in `loopCHAIN`: 442 passing requirements (up from 421 at
init), cell-level mismatches against the seven-implementation consensus at
1898 (down from 2686 at init - consensus is background evidence per the
brief, not the ratchet, but it moved the same direction as the accepted
requirement count on every commit that latched). 16 of 21 trials spent; 5 left
unspent deliberately once further CLOAD/CSTORE abort experiments kept costing
more than they returned.
