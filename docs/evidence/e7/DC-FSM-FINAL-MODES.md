# dc_fsm luna14: why every check passes on a design that is still wrong

Both full sessions (`ARBITER-LIVE.md`) stopped after round 1 with every shipped check passing:
74 pass, 0 fail, 5 abstain. Both still differ from golden on about 25% of testpoints. This fits
each design with the qualitative analysis's replica model of golden (`qualitative/or1200_dc_fsm.md`,
19 switchable deviations). The model reproduces golden exactly with no flags. The figures come from
`e7_behaviour/dc_fsm_final_modes.py`, written to `DC-FSM-FINAL-MODES.json`.

| design | cells off golden | modes it carries (residual cells) |
|---|---|---|
| start (generated, before repair) | 1,818 | M2, M4, M3, M6, M7b, M7d (0) |
| original job's repaired design | 1,762 | M2, M4, M3, M7a (0) |
| full session, latch alone | 1,825 | M2, M4, M3 (82) |
| full session, latch + judge | 1,745 | M2, M4, M3 (2) |

**Repair removed the modes the checks can see:** M6, M7b and M7d. Three modes remain in every
repaired design, and together they account for all of each final's disagreement with golden.

| mode | share of the judge final's cells | what it is | spec | do the luna14 checks see it? |
|---|---|---|---|---|
| **M2** cache-inhibit sensed live | 39% | The designs mask burst and the write enables with the live `cycstb & ci` in the first cycle. Golden uses the registered flag, set one edge later, for those; it uses the raw `dcqmem_ci_i` for the acks and exits. | **Ambiguous.** One phrase, "not cache-inhibited", is implemented two ways in golden. The write-enable half follows from "the cache_inhibit flag is cleared on entry … detected later"; no uniform reading reaches golden. | **The checks require the misreading.** Golden itself fails REQ-0002 and REQ-0078. |
| **M4** `biu_read` gated by load | 33% | The designs raise no `biu_read`/`tag_we` in a store's miss-evaluation cycle. Golden does. | **Clear; misread.** The condition has no load term, and the hit/miss evaluation flag is set for stores too. | **No.** The run's reference model encodes the same reading. |
| **M3** no page re-capture | 29% | Golden reloads `saved_addr[31:13]` from `start_addr` in the first evaluation cycle. No design does. | **Silent.** The spec never mentions it; it is probably the OR1200 MMU's page arriving one cycle late. | **The checks require the designs' behaviour.** Golden fails REQ-0016. |

The 5 abstaining requirements (REQ-0028, 0049, 0082, 0089, 0093) are never exercised by the
stimulus.

## Why the checks are wrong

The shipped checks are derived from each run's reference model, and the same model wrote that
reference from the same spec. They encode its readings: they pass whatever the reference does, and
fail golden where the reference departs from it.

- **Of the three modes, one is a spec gap, one is ambiguous, and one is plain misreading.**
  - **M3: true underspecification.** No reading of the text can produce golden's behaviour.
  - **M2: half ambiguous.** Its write-enable half can be derived, and the judge derived it: that
    is the 470-cell fix it kept.
  - **M4: a misreading.** The spec is clear; the generator, the reference and the checks all read
    a load term that is not there.
- **So "the checks are wrong" mostly means "the checks share the generator's reading".** That
  holds whether or not the spec is underspecified. A check written by an independent reader would
  catch M4, and half of M2.
- **For the loop:** when every check passes, the session stops. No signal from the checks, the
  peers (who share M2–M4) or the judge, which is only asked about commits, points at these
  modes. Fixing them needs a source of disagreement that does not share the generator's reading.
