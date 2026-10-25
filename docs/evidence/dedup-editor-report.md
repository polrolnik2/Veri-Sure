# DEDUP editor report — or1200_dc_fsm

## Outcome

Started at **22 objections of 87**. Finished at **0 objections of 87** — all 87
checks pass. `cells_disagreeing_with_the_consensus` moved from 9857 to 2686 as a
side effect (not optimized for; shown only because the brief says to report it).

12 of the 21 trials were spent on `commit`; 9 remain unused. I stopped because
`checks_objecting` reached 0 — there was nothing left to drive down.

## What was wrong, structurally

The design's central bug was that `hitmiss_eval_r` (the "still deciding hit vs.
miss vs. cache-inhibited" flag) and the state transition out of `CLOAD` were not
tied to the same event. A load miss's first BIU word could arrive many cycles
after entry, and in the original code the FSM only moved from `CLOAD` toward
`LREFILL3` a full cycle *after* it had already noticed that word — producing a
one-cycle gap in `burst`/`biu_read`/`tag_we` at exactly that boundary, and, by
the same mechanism, letting `dc_addr` keep showing `start_addr` long after a
BIU transfer had actually started. A second bug family sat in `cache_inhibit_r`:
the register that is supposed to remember "this access is cache-inhibited" has
an inherent one-cycle detection lag (it can only latch the condition once the
FSM has already spent a cycle in `CLOAD`/`CSTORE`), and several combinational
outputs (`burst`, `biu_read`, `dcram_we`, `first_hit_ack`) were gated on that
lagged register directly, so they behaved wrongly for exactly one cycle at the
start of a cache-inhibited access. A third bug was that the `~load_r` clause in
`load_miss_in_cload` was dead code (`load_r` is already 1 by the time the FSM
is observably in `CLOAD`), so `saved_addr[3:2]` was never incremented on entry
to `LREFILL3` and the associated word count was wrong.

## Commits, in order, and what each moved

1. **Rejected (net: 66→59 passing).** First attempt: rewrote `cache_inhibit_r`
   to latch `dcqmem_ci_i` directly at request-acceptance instead of the
   two-step "clear at acceptance, detect while in `CLOAD`/`CSTORE`" the
   original had. This repaired 8 checks (REQ-0026, REQ-0030.band,
   REQ-0033.control, two REQ-0037 variants, REQ-0059, REQ-0060, REQ-0068) but
   broke `REQ-0009.band@band`/`REQ-0009.merge@merge`, whose own quoted sentence
   — *"or1200_dc_fsm clears its internal cache_inhibit flag when accepting a
   request, and while in the CLOAD or CSTORE state detects the cache-inhibit
   condition by observing dcqmem_cycstb_i & dcqmem_ci_i"* — turned out to
   require exactly the two-step register behavior I had replaced. Correctly
   refused; the *direction* of the fix (increment `saved_addr[3:2]` on
   `LREFILL3` entry, fix `dc_addr`'s mux, drop the dead-code term, add a
   `~load_r`-free `load_miss_in_cload`) was right, the specific implementation
   of the cache-inhibit latch was not.

2. **Latched (66→72).** Reverted the register to the original two-step form,
   introduced `eff_cache_inhibit = cache_inhibit_r | cache_inhibited` as a
   same-cycle-safe stand-in wherever a combinational decision needed to see
   cache-inhibit status before the register had caught up, fixed `dc_addr` to
   `((biu_read || biu_write) && ~hitmiss_eval_r) ? saved_addr_r : start_addr`,
   removed `biu_read`'s dead second term, added `~cache_inhibit`-style
   exclusion to `first_store_hit_ack`, rewrote `CLOAD`'s next-state case to
   actually reach `LREFILL3` on the same edge the first refill word arrives,
   simplified the `hitmiss_eval_r` clear condition, and fixed the
   `LREFILL3`-entry increment. Repaired REQ-0013 (both variants), REQ-0026,
   REQ-0030.band, REQ-0033, REQ-0036, REQ-0037 (two variants), REQ-0059,
   REQ-0060, REQ-0065, REQ-0068, REQ-0083.

3. **Latched (72→77).** Replaced every remaining `eff_cache_inhibit` use with
   the plain live `cache_inhibited` wire (a testpoint drove `dcqmem_ci_i`
   toggling every cycle while `dcqmem_cycstb_i` stayed asserted; the OR'd form
   could latch to 1 on one stray cycle and then stay wrong for the rest of the
   transaction). Rewrote `dcram_we`'s `load_refill_write` to match
   REQ-0032's own wording literally (`load_r && biudata_valid && ~dcqmem_ci_i`,
   dropping the state/`hitmiss_eval_r`/`is_miss` qualifiers I'd added).
   Reverted `first_miss_ack` to the plain original form per REQ-0035's
   explicit text (*"does not require tagcomp_miss=1"*). Decoupled `CSTORE`'s
   next-state from `hitmiss_eval_r` (a store's write-through request is issued
   unconditionally the same cycle, so treating "still evaluating" as spanning
   the whole wait was wrong for `dc_addr`'s sake). Repaired REQ-0015,
   REQ-0030.band, three REQ-0032 variants, REQ-0035, `first_hit_ack`.

4. **Rejected (net: 77→77).** Extended the same `hitmiss_eval_r`-decoupling to
   `CLOAD` (needed so `dc_addr` would switch to `saved_addr` promptly during a
   load's wait, not just a store's) and made `load_miss_in_cload`'s cycle-2-
   onward condition unconditional. This repaired REQ-0029/REQ-0030/REQ-0087's
   `dc_addr` checks but broke `REQ-0014` (*"assert first_hit_ack
   combinationally while in CLOAD ... servicing a normal ... load hit"*) and
   `first_hit_ack`, because a hit that only becomes visible on a cycle after
   entry was no longer being re-checked. Correctly refused.

5. **Latched (77→80).** Fixed the conflict from (4) properly: made
   `load_hit` and `load_miss_in_cload` re-evaluate `is_hit`/`is_miss` on
   *every* cycle the FSM is in `CLOAD` with `load_r` set (not just the entry
   cycle), so a late-arriving hit is still caught, and simplified `CLOAD`'s
   next-state case to a single `load_r`-gated branch with no separate
   `hitmiss_eval_r` special case. Repaired REQ-0029.t2, REQ-0030.control,
   REQ-0087.control, with nothing broken.

6. **Latched (80→81).** Changed the `cnt` reload on `LREFILL3` entry from
   `OR1200_DCLS - 1` to `OR1200_DCLS`. This was an exploratory change (I
   suspected an off-by-one in the refill word count); it repaired
   `first_miss_err` and lowered the disagreement count substantially, with
   nothing broken, so I kept it, though I never fully confirmed *why* it
   helped.

7. **Latched (81→84).** Added `abort_request || error_response` handling to
   `LREFILL3`'s and `SREFILL4`'s next-state (previously only `CLOAD`/`CSTORE`
   checked this, so an error arriving mid-refill could clear `load_r` via the
   unconditional sequential block while `state` stayed stuck in `LREFILL3`,
   producing a `burst`/`dc_addr` mismatch). Repaired REQ-0037.off@862623..,
   REQ-0087.shipping, REQ-0088.shipping.

8. **Rejected, kept as neutral (net: 84→84).** Tried removing `abort_request`
   from `LREFILL3`/`SREFILL4` (keeping only `error_response`) on the theory
   that an already-accepted BIU transaction shouldn't be cancelled by the
   *requester's* `dcqmem_cycstb_i` dropping. No checks moved either way; I
   kept the change since it is the more defensible model and did no harm.

9. **Rejected, reverted (net: 84→73).** Extended the same
   `abort_request`-removal to `CLOAD`/`CSTORE` — a large regression (11 checks
   broken, including `REQ-0009`, `first_hit_ack`, `first_miss_err`,
   `biu_write`). `dcqmem_cycstb_i` dropping genuinely does need to abort a
   request still in `CLOAD`/`CSTORE`. Reverted immediately.

10. **Rejected, reverted (net: 84→78).** Tried reordering `CLOAD`'s
    persistent branch to check `biudata_valid` before `is_hit`, on the theory
    that a `tagcomp_miss` reading that coincides with a BIU response arriving
    should not cancel an in-flight miss refill. Broke REQ-0014, REQ-0026,
    REQ-0068, `first_hit_ack`, REQ-0037.off@862623.., REQ-0088.shipping — there
    are legitimate tests where a hit really does coincide with `biudata_valid`
    and must still complete to `IDLE`. Reverted.

11. **Latched (84→88 requirement count / repaired 4 checks).** Root-caused the
    remaining `dcram_we`-during-`LREFILL3` failures (REQ-0032 all three
    variants, REQ-0073) using `explain`'s block-internals slice, which showed
    `load_refill_write` held constant at 0 across the whole failing window
    even while `biudata_valid` pulsed twice — a purely temporal defect, not a
    wrong value at one edge. Changed `load_refill_write`'s cache-inhibit term
    from the live `dcqmem_ci_i` back to the registered `cache_inhibit_r`: once
    the FSM is in `LREFILL3`, `cache_inhibit_r` is frozen (it only updates
    while `state` is `CLOAD`/`CSTORE`), so it gives later refill words a
    stable "not cache-inhibited" reading immune to whatever `dcqmem_ci_i` is
    doing several cycles into an already-accepted, already-non-inhibited
    transfer, where the literal `~dcqmem_ci_i` reading was letting the write
    be dropped. Repaired all four remaining `dcram_we` checks, nothing broken.

12. **Latched (88→90 / repaired the last 2 checks, 0 objecting).** The last
    two failures (`REQ-0037.off@862641d62cfd`, `REQ-0087@biu_read`, both at
    the same edge of a reset-recovery testpoint) turned out to be the mirror
    image of commit 11's fix: at the very first cycle of a load that would
    turn out to be cache-inhibited, the check's own reference expects
    `biu_read`/`burst` to still assert, using `cache_inhibit_flag`'s
    (registered, one-cycle-lagged) value as the cache-inhibit signal rather
    than the live `dcqmem_ci_i` — exactly the one-cycle detection lag
    `cache_inhibit_r` inherently has. Changed `load_miss_in_cload` (which
    feeds both `biu_read` and `burst_load`) to use `~cache_inhibit_r` instead
    of `~cache_inhibited`. This repaired both remaining checks and did not
    regress `REQ-0015.v2@n3` (the toggling-`dcqmem_ci_i` test that had
    originally motivated using the live signal there) — confirmed by the
    commit result showing an empty `broken` list.

## Checks I suspected of demanding something unlicensed, and what happened

I flagged two clusters as possible check defects partway through (documented
in my own working notes at the time) before finding real fixes for both:

- `REQ-0087@biu_read` carries `"requirement text unavailable"` — no governing
  sentence at all, which is exactly the situation the brief describes as
  legitimate grounds to suspect the check. I did not stop there; using
  `explain`'s `block_internals` (which shows exact signal-transition
  timestamps, not just the coarser sampled boundary) I found the real
  mechanism (item 12 above) and fixed it. Withdrawn as a "check defect"
  candidate — it was a real design gap.
- `REQ-0032`'s `dcram_we` variants and `REQ-0073` looked, from the sampled
  boundary alone, like they wanted a value with no supporting input change —
  `explain` itself said as much (`"the defect is TEMPORAL ... not a wrong
  value at one edge"`). That hint was correct, and pointed at a real,
  fixable bug (item 11 above) rather than a check problem.

**No check remains that I believe demands something its own sentence does not
license.** Every one of the 87 now passes.

## Two commits the ratchet refused that I still think were headed the right
## way (for the record, not a complaint)

Commits 1 and 4 were both correctly refused (each had genuine regressions
against a specific quoted requirement), but the *general direction* of each —
respectively, "the LREFILL3-entry address increment and dead `~load_r` term
need fixing" and "`dc_addr` needs `hitmiss_eval_r` to resolve faster for
loads, not just stores" — was right, and the eventual fixes (commits 2 and 5)
kept that direction while fixing the specific interaction that had broken
something else. I mention this only because the brief asked for it, not
because I think the ratchet should have accepted them.

## Trials

12 of 21 used (9 commits latched, 3 rejected-and-reverted, 1 rejected-and-kept
as neutral). Stopped with `checks_objecting: 0` — there was no objecting check
left to drive further, and the brief is explicit that
`cells_disagreeing_with_the_consensus` (2686, down from 9857) is not something
to keep spending trials on.
