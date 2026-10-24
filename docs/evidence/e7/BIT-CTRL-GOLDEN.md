# bit_ctrl's low scores: how much is golden's own

bit_ctrl designs score far below the other modules against golden. The luna12 start matches it on
18.4% of edges and 3.2% of testpoints, and agrees with its three peers on 86%. The qualitative
analysis (`qualitative/i2c_master_bit_ctrl.md`) traced most of the gap to two quirks of the
reference itself. This rebuilds a reference without each quirk and rescores every bit_ctrl verdict
in the e7 evidence against it. Figures come from `e7_behaviour/bit_ctrl_golden.py`, written to
`BIT-CTRL-GOLDEN.json`; the corrected references are built in `e7_behaviour/golden_variants.py`.

## The two quirks

- **gB: golden never resets `dout`.**
  - The harness runs testpoints back to back, so golden's `dout` at the start of a testpoint is
    whatever the previous testpoint left.
  - The spec's reset list does not name `dout`. All 20 generated designs and all 4 ref models
    reset it.
  - gB is the reference with `dout` reset to 0 on `nReset` and `rst`. Against golden it differs
    on `dout` only (126,965 cells), as it should.
- **gC: golden resets the raw capture registers `cSCL`/`cSDA` to 00.**
  - The designs reset them to 11 ("filtered SCL/SDA are initialized high").
  - With `clk_cnt` < 4, golden's 00 makes a filter glitch after every reset: a fake SCL rise,
    a fake STOP, and a clock-sync reload.
  - gC is gB with the capture registers reset to 11. It changes `scl_oen`, `sda_oen`, `busy`, `al`,
    `cmd_ack` and `dout` across many testpoints.

## Absolute scores: mostly golden's

Edges / testpoints equal to each reference, on all runs' stimulus:

| design | golden | gB | gC |
|---|---|---|---|
| luna12 start | 18.4% / 3.2% | 55.3% / 15.9% | 83.5% / 37.6% |
| luna12 peer gen1 | 17.0% / 1.9% | 50.8% / 9.2% | 74.1% / 21.1% |
| luna12 peer gen2 | 18.8% / 3.6% | 55.4% / 17.4% | 81.6% / 43.8% |
| luna12 peer gen3 | 17.5% / 2.2% | 51.5% / 10.4% | 76.6% / 22.7% |

Against a reference without the two quirks, the start is at 83.5% of edges, not 18.4%. The
remaining gap is the designs' own readings: M1–M7 in the qualitative analysis, most of them shared
by every design.

## Verdicts on commits: unchanged

Both quirks act on the design before and after an edit alike, so they cancel when a commit is
scored by cells fixed minus broken.
- **Audited commits, both arms:** 35. Golden's direction differs from gB's on 0, and from gC's
  on 0. The consensus latch's record is identical under all three: it keeps 11 better / 2 worse
  and refuses 3 better / 15 worse.
- **Commits the spec judge decided:**

| commit | judge (variant 3) | golden net | gC net |
|---|---|---|---|
| offline, cf-checks luna12 commit 12 | +0.15 | +9,608 | +9,576 |
| offline, cf-checks luna12 commit 16 | −0.61 | −15 | −11 |
| offline, cf-model luna12 commit 9 | −0.57 | −1,993 | −2,001 |
| live, latch + judge, commit 1 (kept) | +0.26 | −4,068 | −7,048 |

- **The live judge's bit_ctrl keep is a larger regression against gC than against golden.**
  - That session's final scores 83.5% → 82.0% of edges and 37.6% → 30.3% of testpoints against
    gC. Against golden it read as +0.1 points of edges.
  - The latch-alone session's five refused commits were all regressions under every reference.

**So:** every bit_ctrl number reported as a level against golden is understated. Every number
reported as a change, and every keep/refuse verdict, stands. Reports of bit_ctrl levels now
give gC beside golden (`arbiter_live_report.py`).
