# Run 7: the best evidence, the worst outcome

Third live session of the real `_EditSession` against the repaired 90-oracle
suite, driven over `AgentPort` by a local Sonnet subagent. Same baseline, same
model, same budget as runs 5 and 6. It was started specifically to exercise
`add_stimulus`, which had just been wired.

**It made zero `add_stimulus` calls and ended worse than both predecessors.**
This records why, because the causes are defects in what I built, not noise.

## The three runs

| | rounds | trials | check_staged | FAILING 19 → | UNCOVERED 25 → | errored rounds |
|---|---|---|---|---|---|---|
| run 5 | 34 | 4 | 4 | **5** | 27 | 4 (all commits) |
| run 6 | 40 | 4 | 4 | **5** | 27 | 4 (all commits) |
| run 7 | 45 (cap) | 2 | 3 | **7** | 28 | **11 (9 of them tool misuse)** |

Runs 5 and 6 spent four trials each and converged on the same five. Run 7 hit
the round cap with two trials unspent, and 24% of its rounds returned an error
against 10-12% in the others. The tool surface was strictly richer — the rooted
causal chain, the decimal-annotated VCD readout, the corrected transition
timing, `stage_edit`. It did not help. Two things ate the run.

## 1. Eleven rounds guessing whitespace

`read_block` renders the buffer with line-number prefixes, so **no tool returns
a verbatim substring**. `stage_edit` demanded an exact one.

Run 7's first anchor was one space wider than the file — 25 leading spaces
against 24 — and was refused. The agent then degraded:

```
r6   "                         CMD_STOP: begin\n..."   FAIL  (25 spaces, file has 24)
r8   "state <= ST_STOP_A;"                             FAIL  (file has "state   <=")
r9   "endmodule" -> "endmodule\n"                      ok    <- a PROBE, not a repair
r11  "state\t<= ST_READ_A;"                            FAIL
r13  "state<="                                         FAIL
r14  "(state)" -> "( state )"                          ok    <- a second PROBE
r16  "<= ST_WRITE_A;"                                  FAIL  (ambiguous: 2 matches)
r18  replace_block A4                                  ok    <- gave up, retyped 4.7KB
```

Rounds 9 and 14 are the tell: the agent spent edits purely to discover what the
buffer contained. Run 6, same model and same tool, transcribed the indentation
correctly on its first try and made **seven edits with zero errors**. That is
the whole difference between the runs' outcomes, and it turned on one space.

Rounds 10 and 15 also show a swap-without-a-temp: renaming `ST_STOP_A` →
`ST_WRITE_A` and then `ST_READ_A` → `ST_STOP_A` in sequence made the third
rename ambiguous. The editor could report the ambiguity but had no way to show
the agent it was mid-permutation.

**Fixed** (commit 6b8d9f2): the anchor matches on the token sequence, any
whitespace matching any whitespace, reported in the response. Pin 7 is intact —
a destroyed anchor still matches nothing, a repeated one is still refused — and
the not-found message now says whitespace was already ignored, so the agent
cannot re-enter the loop.

## 2. It was never shown a single uncovered UID

`list_failing_requirements` returns uncovered rows. `budget()` in
`edit_drive.py` dropped them first, keeping a count:

```
edit5  r0: failing 19, uncovered 0  <- DROPPED, count only: 25
edit6  r0: failing 19, uncovered 0  <- DROPPED, count only: 25
edit7  r0: failing 19, uncovered 0  <- DROPPED, count only: 25
       r22: failing 7, uncovered 0  <- DROPPED, count only: 28
       r38: failing 7, uncovered 0  <- DROPPED, count only: 28
```

The agent knew "28 uncovered" as a number and could not name one. `add_stimulus`
takes a `req_uid`. I wired the tool and starved it of its arguments — the run
was launched to test a tool it could not call.

**Fixed** (commit 1ad75d3): uncovered rows shed to UIDs, never a count; failing
rows shed field text at 200/120/60 before any row drops. All 19 failing rows and
all 28 uncovered UIDs now fit in 606 characters.

## 3. What the run exposed that I was not looking for

Chasing why round 36's commit latched a junk probe, the multi-driver guard turned
out to be blind where it matters. `multidriven_signals` is a regex over
Verilator's MULTIDRIVEN, and on 5.038 under `check_syntax`'s exact flags:

| | Verilator |
|---|---|
| `output c; assign c = a; assign c = ~a;` | fires — "multiple combinational drivers" |
| `always @(posedge clk1)` / `@(posedge clk2)` on one reg | fires — "different clocking" |
| **`wire w; assign w = a; assign w = b;`** | **silent, exit 0** |
| **two same-clock always blocks on one reg** | **silent, exit 0** |

The guard sees the module boundary and goes blind inside it, which is where the
editor edits. **All three sessions latched an i2c design carrying `assign
scl_sync` twice** — internal wire, and the ChipVerilog candidate they start
from (`Result/codex/i2c_master_bit_ctrl/i2c_master_bit_ctrl_t1.v`, confirmed by
rebuilding run 8's baseline from it and reproducing 19 failing / 25 uncovered /
46 passing exactly) has one driver, and `overdriven_signals` reports nothing on
it. In run 6 the two came to disagree:

```
line  82   assign scl_sync = scl_oen & ~sSCL & dSCL;
line 315   assign scl_sync = cSCL[1] & ~scl_i & scl_oen;
```

Two continuous assignments resolve to **X wherever they differ** (verified in
iverilog), and `scl_sync` is read by the clock divider's reload condition at line
137. Run 6 reported 19→5 as a success; the design it shipped has an X-generating
wire feeding its core timing. Worse, the agent had spent rounds 27 and 33
refining the two copies **separately**, taking them for one expression, because
nothing it could call would tell it there were two.

**Fixed** (commit 6b8d9f2): `overdriven_signals(text)` counts writing blocks from
the parsed text — the mirror of `undriven_signals`. It finds `scl_sync` in all
three latched designs and nothing in the pristine candidate or the golden RTL.
Run 4's latched RTL is also clean, so the duplication entered at run 2 and again,
independently, at run 5.

## Honest reading

Run 7 is a negative result for the causal chain and I should not bury it: the
richest evidence path produced the worst outcome. But the trajectory does not
support "the chain made each decision cost more rounds" — 7 `explain` calls in
run 7 against 11 in run 6. The rounds went to tool misuse the tools invited, and
the binding constraint was the round cap, not the trial budget: **run 7 ended
with two of its four trials unspent.**

What the chain's value actually is remains unmeasured. Runs 5 and 6 both found
the reversed command encoding without it. A run on the fixed editor is the test,
and it is not yet run — the numbers above are the last ones taken on the old
tooling and should not be quoted as the current state.
