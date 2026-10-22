# or1200_dc_fsm: what the errors are, and how the generated and repaired arms differ

**How I measured this.**

- **Exact replicas.** I wrote a Python model of golden. It matches golden on all 24,563 known edges. I then added 19 switchable deviations. For every one of the 15 designs, golden plus a subset of those deviations reproduces the design's open-loop trace with **0 residual cells** on all three stimuli. The same holds for all three runs' reference models (fresh state per testpoint).
- **Shipped checks.** I ran each run's shipped checks over replica traces. My verdicts reproduce the editor's failing sets in all 12 reviews I compared. 2-4 checks per run also fail the ref model in my harness, so I excluded them.
- **Reset correction.** Only 53-65% of testpoints begin with a reset. I therefore measured shares with each replica reset at every testpoint. Total disagreement over the 15 designs is then 22,495 edges. In the back-to-back traces, carried-over state inflates mode M5 about 7×.

Scripts and data are in `qual/or1200_dc_fsm/`: `model.py`, `fit*.json`, `share_fresh.json`, `checks.py`, `vis*.json`.

## 1. Error modes

The share columns give the fraction of disagreement edges in the generated arm (12 designs) and in the repaired arm (3 designs).

| Mode | Design vs golden | Spec sentence | Designs gen/rep | Share gen/rep | Example (design, stim, testpoint, edge) |
|---|---|---|---|---|---|
| **M1 store-miss refill always on** | Store miss + valid → SREFILL4, which raises load/burst/biu_read for 4 more words. Golden goes to IDLE (`OR1200_DC_STORE_REFILL` is commented out in or1200_defines.v). | "If the store misses in the cache, the **default behavior** is to complete the external write-through transaction and then return to IDLE without refilling the cache." | 3/12, 2/3 | 28.1% / **54.4%** | luna13.gen1, luna13, TP-0014, e2: golden burst/biu_read/dcram_we = 0/0/0, design 1/1/F |
| **M2 cache-inhibit sensed live** | Live `cycstb&ci` masks burst/tag_we/dcram_we in the first CLOAD/CSTORE cycle. Golden masks only with the registered flag, which is set one edge later. | "The cache_inhibit flag is cleared on entry; cache-inhibit status is detected later in CLOAD or CSTORE when dcqmem_cycstb_i & dcqmem_ci_i is observed" | 12/12, 3/3 | 19.0% / 13.6% | luna13.gen1, luna13, TP-0006, e1: ci=1, miss=1; golden burst=1, design 0 |
| **M3 no page re-capture** | Golden reloads `saved_addr[31:13]` from start_addr in the first CLOAD/CSTORE cycle. No design does this. | Only "start_addr is captured into saved_addr_r" at accept | 12/12, 3/3 | 23.1% / 15.8% | luna13.gen1, luna13, TP-0102, e4: golden 0xa0001678, design 0x12345678 |
| **M4 biu_read gated by load** | No biu_read or tag_we in a store's miss-evaluation cycle | "biu_read is asserted when the FSM is evaluating a miss and tagcomp_miss=1, or when … a refill load sequence is active" | 10/12, 2/3 | 19.5% / 9.9% | luna13.final, luna13, TP-0014, e1: golden biu_read=1, tag_we=1; design 0/0 |
| **M5 miss decision frozen at evaluation** | tagcomp_miss is tested only while hitmiss_eval=1. A word returning with miss=0 starts LREFILL3, which then waits forever. Golden treats it as a hit and goes to IDLE. | "During hit/miss evaluation, tagcomp_miss determines whether the access hits" vs "performs hit/miss evaluation in the CLOAD state" | 11/12, 1/3 | 4.8% / 1.4% (back-to-back: 12-38% per design) | luna12, TP-0308, e66 (the only testpoint that stages it): golden first_hit_ack=1 then IDLE; designs hold burst/biu_read for 80 edges |
| **M6 extra qualifiers on the hit ack** | first_hit_ack is suppressed on an aborting cycle (cycstb=0) or on error | "first_hit_ack is asserted combinationally while the FSM is in CLOAD" | 4/12, 0/3 | 1.0% / 0 | luna13.r0, luna13, TP-0025, e2: golden ack=1, design 0 |
| **M7 minor variants** | (a) refill dcram_we also needs biu_read; (b) live ci masks refill writes outside CLOAD/CSTORE; (c) error aborts LREFILL3; (d) biu_read on a ci hit | (a) "if load=1, biudata_valid=1, and … not cache-inhibited, all four byte lanes are written"; (c) the LREFILL3 paragraph lists no error exit | a 4/12, 1/3; b 9/12, 1/3; c 2/12, 0; d 5/12, 0 | ≤0.5% each | luna14.final, luna14, TP-0125, e1: golden dcram_we=F, design 0 |

**Why each mode happened, how to classify it, and what encoded it.** "Ref" below means the run's reference model.

- **M1.**
  - *Cause:* an option described in detail was read as a feature to build.
  - *Class (a):* the default is stated in the spec. Reading rule: the stated default is the unconfigured build, and the named macro guards the option. luna12.r0 did exactly this with an `ifdef`.
  - *Encoded:* the luna12 and luna13 refs hard-code `store_refill_enabled=True`. Golden fails luna13 REQ-0026, 0027, 0034 and 0088, and luna12 REQ-0036, all of which pass the M1 designs. luna12's repair deleted r0's correct `ifdef` "while the reference model exercises store refill as enabled". The luna14 ref reads the spec correctly, and its checks convict M1 (REQ-0040, 0088).
- **M2.**
  - *Cause:* "not cache-inhibited" was read as a live attribute.
  - *Class (b), and golden's choice cannot be derived.* Golden implements the same phrase two ways: the flag for burst and the write enables, but raw `dcqmem_ci_i` (without cycstb) for the acks and exits. Neither uniform reading reaches golden. Flag-only gives 431 edges off golden; live-only, the designs' choice, gives 282.
  - *Encoded:* in all refs. Golden fails luna13 REQ-0058/0075 and luna14 REQ-0002/0078.
- **M3.**
  - *Cause:* the spec never mentions the re-capture.
  - *Class (c).* This is probably the OR1200 DMMU's translated 8 KB page arriving one cycle late, which the spec does not say.
  - *Encoded:* in all refs. Golden fails luna14 REQ-0016.
- **M4.**
  - *Cause:* a "read request" during a write-through store looked like a bug.
  - *Class (a).* The condition has no load term, and hitmiss_eval is set for stores too ("hitmiss_eval is set to 1, and either the store or load flag is set").
  - *Encoded:* in the luna13 and luna14 refs. Golden fails luna13 REQ-0088 and luna12 REQ-0022; the luna12 ref fails REQ-0022 too. luna13's repair added the gate, reasoning that biu_read could otherwise assert for a store miss, because the hit/miss term was not gated by the load flag.
- **M5.**
  - *Cause:* the generator's habit of latching the miss decision once.
  - *Class (b), with some textual support for golden.* The hit is stated as a condition of the state ("while the FSM is in CLOAD"), while the spec names hitmiss_eval explicitly where it applies (abort, biu_read, dc_addr). The port is also described as "Combinational tag-compare miss indication".
  - *Encoded:* in no ref, and no check sees it.
- **M6.**
  - *Class (a).* The checks see it in every run, and repair removed it.
- **M7.**
  - (a) is class (b): the formula supports golden and the prefix "During load refill" supports the designs. The luna14 ref encodes it, and luna14's repair added it.
  - (b) is class (a) ("detected … in CLOAD or CSTORE"). It is check-visible in 7 designs (6 of them generated).
  - (c) is class (a). It is never staged after a reset.

## 2. Hypotheses

- **H1 visibility: SUPPORTED. The silence comes from a shared misreading, not from missing coverage.**
  - Adding one mode to golden shows that the checks' verdict follows the run's ref. A mode the ref shares is never penalised and is often *required*: M1 in luna12/13, M2 in luna13/14, M3 in luna14, M4 in luna12/13. A mode the ref does not share is caught if it is staged: M1 in luna14, M6 everywhere, M7b. M5, M7a and M7c are silent everywhere.
  - Finals: luna13 and luna14 fail 0 checks. luna12 fails 6, all from M7b (latent in r0) combined with the M1 path that repair introduced.
  - Ref-shared modes account for 100% / 97% / 100% of the finals' disagreement, against 58-97% for generated designs. 7 of 12 generated designs carry a check-visible mode (M6, M7b), against 1 of 3 finals.
  - luna13.gen1 scores 84/84 because 97% of its gap is the ref's own readings (two of them, M1 and M2, are required by checks) and the rest (M5) is never staged in luna13.
- **H2 reference-model pull: STRONGLY SUPPORTED.**
  - On own stimulus, with a reset per testpoint, ref agreement from r0 to final went 0.906→0.999, 0.989→1.000 and 0.996→1.000. **Each final equals its ref** on that stimulus.
  - Golden agreement over the same step went 0.955→0.907, 0.906→0.899 and 0.961→0.963.
  - At the edges where r0 and final differ (738/88/34), final matches the ref at 735/88/33 and golden at 143/15/24. r0 had matched golden at 521/73/9 of them.
  - 11 of the 12 deviation changes moved toward the ref, and every move away from golden adopted a ref reading. The exception, luna14's removal of M7d, was forced by a check (REQ-0051) that convicts the ref itself.
  - luna12 even accepted a new check failure (REQ-0022) in order to match the ref's outputs. Repair minimises ref mismatches, not check failures.
- **H3 common mode: SUPPORTED.**
  - M2 and M3 appear in 15/15 designs and 3/3 refs, about 39% of all disagreement.
  - M5 appears in 11/12 generated designs and is a generator habit that no ref shares.
  - M1 is the largest single mode (35%), and it follows the corpus's ref.
- **H4 fixes vs regressions.**
  - luna12 fixed M5 and M4 but added M1: disagreement went 1,054→2,269 edges.
  - luna13 fixed M6 and M7b but added M4: 2,387→2,563.
  - luna14 fixed M6, M7b and M7d but added M7a: 1,021→983.
  - Of the edges repair changed, r0 had been golden-correct at 603 of 860.
- **H5 patching style: local term edits.**
  - r0→final changed 18 / 8 / 22 lines, against 107-267 lines of difference between ablation samples.
  - There were no latency tweaks and no restructuring: one `ifdef` was deleted, and otherwise conditions were toggled inside existing expressions.
  - Every deviation in a final also occurs in some generated sample.
- **H6 timing vs function: REFUTED.** In closed loop, 0 of the 3,840 mismatching testpoints are equal after dedup, in either arm.

## 3. Qualitative difference between the arms

There is one, and it is in kind rather than amount.

**Generated designs** mix two error sources:
- spec readings they share with the ref (M2, M3, sometimes M1/M4);
- the generator's own idiosyncrasies (M5, ack qualifiers, error exits, ungated ci).

**Repair** strips the idiosyncrasies that the ref disagrees with and imports the ref's readings in their place. The result converges, edge for edge, on the run's reference model.

**Residual errors after repair** are therefore fewer in kind, systematic, corpus-specific, and silent to the checks by construction. The largest is M1, a default the spec states that two refs inverted.

## Justifiable readings

Shares are of the 22,495 disagreement edges, measured with a reset per testpoint.

1. **"Build the stated default; guard the named option with its macro."**
   - Justified by: "the default behavior is … without refilling the cache"; "optional … when OR1200_DC_STORE_REFILL is enabled".
   - Closes **34.9%** (54% of the repaired arm's gap).
2. **"Implement output equations literally; add no qualifiers suggested by port names or intent."**
   - Justified by the biu_read, first_hit_ack and dcram_we sentences.
   - Closes M4, M6 and M7a: **≈18%**.
3. **"A condition stated for a state holds on every cycle of that state unless a first-cycle qualifier is named."**
   - Closes M5: **3.9%**.
   - Weaker, class (b), but supported by the spec's explicit use of hitmiss_eval elsewhere.
4. **"Add no transitions the state's paragraph omits; confine ci detection to the states named."**
   - Closes M7b and M7c: **≈0.4%**.

Together these give about **57%**.

**Not reachable from the text:**
- M3 (21%).
- Golden's flag/raw split in M2 (18%). The best uniform reading is already the designs' choice.

**Could not establish:**
- Whether the 2-4 checks per run that the ref fails in my harness are artefacts of my open-loop rows or genuine. For luna14 the editor reports some of them, so they may be real.
- The M5 share rests on a single staged testpoint.
