# The spec arbiter in the editor loop: matched live sessions

`eda_agent/spec_arbiter.py` is variant 3 of the offline test (`ARBITRATION-OFFLINE.md`), wired into the
consensus latch (`RTLEditor(latch_arbiter=...)`; `--arbiter` in the e7 runner).
- **When it is asked:** passing requirements rise while agreement neither rises by the 0.1-point
  margin nor falls by more than 2 points.
- **What it decides:** its cell-weighted score keeps or refuses the commit. When every answer
  abstains, the 0.5-point tolerance decides.
- **Data:** golden is not used in the loop. Figures come from `e7_behaviour/arbiter_live_report.py`,
  written to `ARBITER-LIVE-smokem6.json`. The judge's prompts and replies stay in each run's
  `spec_arbiter/` directory.

**Design.** Four jobs, each run twice from the same start with the same budget (6 trials, 1 round),
checks feedback and the whole-design view:
- the consensus latch alone;
- the consensus latch with the arbiter.

The jobs are the ones where offline commits fell in the undecided range. Sessions are stochastic,
so the two runs of a job diverge from their first commit.

## Final designs, scored by golden

| job | start | latch alone | latch + judge |
|---|---|---|---|
| dc_fsm luna14 | 95.8% edges, 70.9% testpoints | 95.8%, 70.9% (unchanged) | **96.1%, 75.5%** (+77 / −2 cells) |
| sb luna12 | 56.1%, 36.7% | 44.5%, 34.1% (+93 / −9,997) | **54.5%, 35.7%** (+0 / −1,565) |
| byte_ctrl luna12 | 42.7%, 27.0% | 42.7%, 27.0% (+0 / −159) | 42.7%, 27.0% (unchanged) |
| bit_ctrl luna12 | 18.4%, 3.2% | 18.4%, 3.2% (unchanged) | 18.5%, **2.8%** (+5,343 / −9,411) |
| bit_ctrl, against the corrected reference gC | 83.5%, 37.6% | unchanged | **82.0%, 30.3%** (+3,853 / −10,901) |

bit_ctrl's golden never resets `dout` and resets its capture registers low, so its levels against
golden are mostly golden's own quirks (`BIT-CTRL-GOLDEN.md`). gC removes both. Changes and verdicts
are the same against either.

## The commits the judge decided

| session | passing | agreement | judge score | latch decision | golden, cells | right? |
|---|---|---|---|---|---|---|
| dc_fsm luna14 | 65 → 74 | 99.81 → 99.78% | +1.00 | kept | +77 / −2 | yes |
| sb luna12, commit 2 | 61 → 64 | 86.04 → 85.90% | −1.00 | refused | +87 / −9,983 | yes |
| sb luna12, commit 3 | 61 → 63 | 86.04 → 85.06% | +0.24 | kept | +632 / −1,803 | no |
| bit_ctrl luna12 | 77 → 80 | 86.12 → 84.95% | +0.26 | kept | +5,343 / −9,411 | no |

byte_ctrl's arbiter session made no commit in the undecided range, so the judge was never asked.

## What it shows

- **Only two of the four final-design differences trace to the judge.**
  - **sb luna12, where it helped:** it refused a 9,983-cell regression. In the session without
    it, the tolerance kept a near-identical one (9,997 broken), the largest loss in either arm.
  - **bit_ctrl luna12, where it hurt:** it kept a regression of net −4,068 cells. That commit
    lost 1.17 points of agreement, so the tolerance would have refused it, as it refused that
    session's four similar commits.
  - **dc_fsm luna14:** the difference is the editor's path. The commit the judge kept lost 0.03
    points, so the tolerance would have kept it too. The latch-alone session's only commit was a
    larger real fix the tolerance refused (0.85 points).
  - **byte_ctrl luna12:** no judgment was made.
- **Live, the judge decided 2 of 4 commits as golden does,** against 18 of 22 offline. With four
  decisions that gap could be chance.
- **Both wrong keeps were weak scores** (+0.24, +0.26), with the judge's answers split across
  the excerpts. Both commits lost more than 0.5 points, so the tolerance would have refused them.
  - Requiring a decisive score before overriding the tolerance would have fixed both here.
  - Offline it would have cost one commit net (bit_ctrl's fix +0.15 and sb luna13's regression
    −0.12 lost, byte_ctrl's regression +0.38 gained).
  - It is not adopted on this evidence.
- **bit_ctrl is where the judge is expected to be weakest.** The spec does not state the input
  filter's sampling interval, which fixes when the bus outputs change.
- **The live arbiter is variant 3, without variant 4's child-port columns.** That did not matter
  here, because byte_ctrl's judge was never asked.
- **Cost.** The judge used 0–111k output tokens per session, 200k in all. The editor used 37–165k
  per session.

**Verdict on correctness.** On these four pairs, adding the judge gave a better final design on two
jobs, a worse one on one, and a tie on one. Of the judge's own decisions, one prevented a large
regression and one let through a regression the tolerance would have stopped. This is too few
sessions and decisions to estimate the effect. The offline result (18 of 22 decided as golden does)
is not yet confirmed live.
