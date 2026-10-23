# Targeted arbitration, tested offline

Some commits look the same to the consensus latch but go opposite ways by golden:
- dc_fsm luna14's real fix (470 cells fixed, 3 broken);
- sb luna12's regression (0 fixed, 1,733 broken).

Both raise passing requirements and cost about 0.85 points of agreement with the peers
(`LATCH-OFFLINE.md`). This tests whether a narrow judgment can decide such commits where the
latch cannot. The judge is shown only the cells the commit changed, and asked which behaviour the
spec requires. The script is `e7_behaviour/arbitration_offline.py`. Results are written to
`ARBITRATION-OFFLINE.json` (variant 1) and `ARBITRATION-OFFLINE-v2.json` (variant 2). The judge's
prompts and replies are kept out of the repository.

## Method

- **Commits.** 22 in all; golden scores 16 better and 6 worse. Each raised passing requirements,
  and its agreement neither rose by the 0.1-point margin nor fell by 2 points.
  - 13 are audited commits from both arms.
  - 9 come from the live consensus-latch runs: dc_fsm luna14's refused fixes and the tolerance-1
    smoke runs, deduplicated by behaviour.
  - 11 of the 22 are dc_fsm luna14, and most of those share one behaviour.
- **Excerpts.** For each commit, 4 testpoints where the design before and after the commit
  diverge on the run's own stimulus, drawn in proportion to the cells changed.
  - The judge sees the spec, the ports, and the testpoint's rows from reset (or the 24 rows before
    the divergence) to the end of the divergence.
  - The two designs are labelled X and Y. Each excerpt is asked twice with the labels swapped.
- **The judge never sees** golden, the peers, the checks, or which candidate is the edit. It is
  the same model as the generator.
- **A commit is kept** when the cell-weighted vote favours the edit; a zero vote refuses.
- **Golden scores** every cell, with golden's X values counted as don't-care.

## Variant 1: spec, ports, excerpt

| measure | result |
|---|---|
| decisive answers right per golden | 92 of 136 (68%) |
| abstained ("undetermined" / "both wrong") | 37 of 176 |
| same answer with labels swapped | 61 of 88 excerpts |
| output tokens | 944k (5.4k per call) |

**It decides both target commits wrongly,** with the same answer under both label orders.
- **dc_fsm luna14's fix is refused.** On cache-inhibited reads, golden writes the cache and tag
  RAM in the request's first evaluation cycle.
  - The spec implies this: the cache-inhibit flag "is cleared on entry" and is set "later",
    from the input, at the next edge.
  - The judge takes the natural reading, that a cache-inhibited access writes nothing. That is
    the start's defect, which all three peers share.
  - Here the judge makes the same error as the generator.
- **sb luna12's regression is kept.** The spec describes the module both with and without its
  store buffer. The task's `or1200_defines.v` leaves the buffer out, and golden is the
  pass-through. The judge did not see the configuration, so it judged by the store-buffer
  description.

## Variant 2: configuration, and rebuild the registers

This variant was designed from variant 1's errors on these same commits, so it is tuned, not
tested. It makes two changes, both generic:
- **Configuration.** Every macro the spec names is reported defined or not, with its value. The
  states come from preprocessing the design's own include files: for sb, `OR1200_SB_IMPLEMENTED`
  is not defined; for byte_ctrl and bit_ctrl, the `I2C_CMD_*` codes.
- **Procedure.** The judge must:
  1. quote the spec sentences governing each differing output;
  2. rebuild every register and flag they depend on, edge by edge from reset (a registered flag
     changes only after an edge);
  3. then compare.

| measure | variant 1 | variant 2 |
|---|---|---|
| decisive answers right | 92 / 136 (68%) | **112 / 120 (93%)** |
| — dc_fsm | 53 / 86 | 91 / 96 |
| — sb | 5 / 10 | 10 / 10 |
| — byte_ctrl | 23 / 27 | 6 / 8 |
| — bit_ctrl | 11 / 13 | 5 / 6 |
| abstained | 37 of 176 | 53 of 176; 48 of them on the I2C modules |
| same answer with labels swapped | 61 / 88 | 75 / 88 |
| output tokens | 944k | 1.69M (9.6k per call) |

**Commit decisions:**

| rule | kept better / worse | refused better / worse |
|---|---|---|
| consensus latch, tolerance 0.5 | 8 / 3 | 8 / 3 |
| consensus latch, tolerance 1 | 13 / 5 | 3 / 1 |
| variant 1 | 8 / 4 | 8 / 2 |
| **variant 2** | **11 / 1** | 5 / 5 |
| variant 2, and the tolerance-0.5 latch where it abstains (chosen after seeing the results) | 13 / 2 | 3 / 4 |
| a perfect judge on the same excerpts | 15 / 1 | 1 / 5 |

- **Both target commits are now decided correctly.** It keeps dc_fsm luna14's fix in every live
  and audited version (+1.00 each) and refuses sb luna12's regression (−1.00).
- **It refuses most real I2C fixes by abstaining.** Of its 64 I2C answers, 48 are "undetermined".
  - For byte_ctrl, 24 of its 30 abstentions are on excerpts whose start is cut off. The rebuild
    procedure cannot start from reset there.
  - I2C testpoints run up to 4,000 rows, because the bus clock is divided down.
- **Its one wrong keep** is a dc_fsm luna14 commit that breaks 32 cells. It answered "after" on
  both of that commit's 16-cell excerpts, under both label orders.

## What this does and does not show

- **The case is decidable from the spec, and variant 1's failure was a prompt failure.** Given
  the configuration and made to rebuild state, the same model reads the spec correctly where the
  generator, the peers and variant 1 did not.
  - The same model's errors were correlated with the generator's in one framing and not in
    another.
- **This is not yet evidence that arbitration works.**
  - Variant 2 was designed from these failures.
  - Most of its dc_fsm gain is one behaviour, the first-cycle cache-inhibit writes, judged
    correctly across several commits.
  - Its sb gain is one configuration fact.
  - The test that counts is commits it was not designed on.
- **The I2C abstentions need the full history.** Run-length encoding the repeated rows would fit
  a whole testpoint into an excerpt. Until then, abstaining and falling back to the latch is the
  safe behaviour.
- **Cost.** About 77k output tokens per commit judged. Only commits the latch cannot decide would
  be sent: 22 of about 180 here.
