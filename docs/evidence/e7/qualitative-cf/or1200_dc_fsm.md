# or1200_dc_fsm: checks-only vs model feedback, same start

**Method.**
- **Sources.** Start→final diffs, plus the editor logs for luna13/14. luna12's logs are lost.
- **Check replay.** I re-ran each run's shipped checks on the re-simulated probed RTL, with the per-testpoint reset and the settle tail marked. This reproduces every editor review; the one exception is luna12 REQ-0009, a harness artefact.
- **Ablations.** Single edits applied to r0 attribute requirements and behaviour to each edit.
- **Units.** *edges* = own-stimulus edges the arm changed. *tp* = testpoints equal to golden, out of 952.
- Analysis scripts ran in a scratch directory and are not committed. Mode labels M1–M7 are those of `../qualitative/or1200_dc_fsm.md`.

### luna12 (start 66/1/13; golden fails REQ-0036 and REQ-0022)

| arm | main edits | repaired / broken | effect | class |
|---|---|---|---|---|
| checks (2 trials) | The ifdef's new `else` (rtl.sv:194-221) holds CSTORE one extra cycle after `biudata_valid`. The RTL comment says the extra cycle keeps the write-through request active so the address selection stays observable. `first_miss_ack &(cnt==0)` (:87) hides the second ack. | REQ-0036 ("dc_addr from saved_addr during subsequent BIU transfers"): its `eventually after_activation` check needs a second row. Without the gate, REQ-0061 breaks. | 223 edges: **0** golden, **0** ref (r0: 182 golden, 116 ref). tp 718→662 (−56/+0). | (c)+(e). New mode: an inserted wait state. Ifdef kept. |
| model (10 trials) | **Ifdef deleted, so store refill is always on** (ref: `store_refill_enabled=True`). ci confined to CLOAD/CSTORE (ref's `ci_observed`). biu_read: load gate removed, plus `~(store_r&ci_now)`, which the ref lacks. | Store refill: REQ-0036, and 10 SREFILL requirements go from abstain to pass. Alone it fails 6 SREFILL checks; the ci edit fixes them. The biu_read edit is check-neutral; golden's plain form breaks REQ-0022. | 631 edges, all equal to the ref; 60 golden (r0: 521). The biu_read edit alone takes tp 718→854; store refill then removes 77 (final 777). | Store refill: (b), M1, violates R1. ci: (a). Gate removal: (a), M4 fix; its REQ-0022 qualifier: (b). |

### luna13 (start 76/8/0; golden fails REQ-0058 and REQ-0075, which both finals pass)

| arm | main edits | repaired / broken | effect | class |
|---|---|---|---|---|
| checks (1 commit) | C1: ci confined to CLOAD/CSTORE. C16: `cycstb` dropped from the load first_hit_ack. C21/22: dcram_we and tag_we use `cache_inhibit_r`, the REQ-0036 check's own `cache_inhibit==0`. | C1: REQ-0036/0038/0039/0081/0097. C16: REQ-0002/0040/0058. C21/22: check-neutral given C1. | 89 edges: 15 golden (r0: 1). At 73 edges r0 matched the ref and the final matches neither, though its write enables equal golden there. tp 752→791 (+39/−0). | (a). C21/22 is unforced; it is golden's write-enable form (partly undoes M2). |
| model (1 commit) | C1 as above. C16: the ref's `load_hit` verbatim. C13: biu_read gated by `load_r`, the ref's gate. The editor's stated rationale: BIU reads should no longer be asserted for store misses. | Same 8 repaired. C13 is check-neutral. | 88 edges, all equal to the ref; 15 golden (r0: 73). C13 alone: tp 752→681; final 717 (+36/−71). Identical to the original final. | C1, C16: (a). C13: (e), M4 copied from the ref, violates R3. |

### luna14 (start 65/9/5; golden fails REQ-0078, 0002 and 0016)

| arm | main edits | repaired / broken | effect | class |
|---|---|---|---|---|
| checks (2 commits) | Acks cut down to REQ-0025's `cache_inhibit==0` (`!ci_req` and the cycstb qualifier dropped). biu_read loses its `ci_req` term. dcram_we/tag_we: commit 1 makes them flag-only (golden's form); commit 2 adds back `!(CLOAD&&ci_req)`. | Commit 1: 8 repaired; it **broke REQ-0078**. Commit 2: REQ-0051 and 0078. Restoring the acks' `!ci_req` still gives 74/0/5. | 41 edges: 24 equal golden and the ref (r0: 16 golden). tp 675→713 (+43/−5). The acks' ci drop costs 42 edges (40 in the tail). | M6/M7d removal: (a). CLOAD mask: (b), M2 forced by REQ-0078. Acks' ci drop: (e). |
| model (2 requirement latches, 13 trials) | Acks: the ref's (keeps `!ci_req`). biu_read and the mask as in the checks arm. Then **8 rejected commits** re-added the ref's `CLOAD&ci` read term. Four of them matched the ref on all 316 testpoints but broke REQ-0051. One masked the `hitmiss_eval` probe to hide the term. A later gradient latch is not in the returned design. | 65→73, breaking REQ-0078; then 73→74. | 25 edges: 24 equal golden and the ref. tp 675→719 (+44/−0). | (a), except the mask: (b). |

**No arm touched M3, or added defines or `initial` blocks.** The luna12 model arm also drops a probe-only `cache_inhibit_r` clear, as the ref does: (d).

### How the arms differ

**Where the edits come from.**
- **Model arm:** it transcribes the ref's expressions, whether or not a check asks for them. So the golden effect of each edit has the sign of the ref's reading.
- **Checks arm:** it mirrors the failing check's predicate.

**What that did.**
- **The checks arm avoided both ref-only misreadings:** M1 in luna12 and M4 in luna13.
- **Once, it landed on golden's form unasked:** luna13's write enables.
- **When padding is the cheapest way to satisfy a check, it pads.** luna12's wait state is the only latency change in any of the six finals, and it moved no edge toward golden or the ref.
- **Shared readings bind both arms.** Examples: REQ-0078's first-cycle mask, and REQ-0036.
- **Where checks and ref disagree, the checks win in both arms.**
  - The checks rejected all eight attempts to copy the ref's read term, at 231 calls vs 75.
  - REQ-0022 forced a qualifier the ref lacks.

**The testpoint splits are single check-neutral edits.**
- luna12 favours model because of its ref-driven M4 fix (+136 tp).
- luna13 favours checks because that model arm copied the opposite M4 reading (−71 tp).

**Not established:**
- luna12's reasoning in either arm.
- 62% of edges are settle-tail rows, which open no check window.
