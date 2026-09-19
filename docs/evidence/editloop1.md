# The first live RTL-editor loop: 30 rounds, ZERO simulations, zero change

> **CORRECTION.** An earlier version of this file framed the run as a result
> about the agent. It is not. **No simulation ran at any point in the session**,
> so the loop's core path -- edit, simulate, re-decide, latch or not -- is still
> untested. What this run exercised is the STATIC half only, and the two
> findings below are about evidence the agent was never given.

A Sonnet agent drove the real `_EditSession` through `docs/evidence/edit_drive.py`
against the paced 90-check instrument (`docs/evidence/instrument.py`), on the
ChipVerilog codex t1 candidate. The golden RTL was withheld: the agent saw the
requirement text, the check's own complaint, the recorded boundary trace and
the candidate's source, and nothing else. (It was MEANT to see the suspect
blocks' VCD internals too. It did not -- see below.)

**Result: 19 failing requirements before, the same 19 after, and the simulator
was never invoked.**

Three things compounded to make that so, and only the third is a defect:
`--reuse-baseline` decided the frozen set on the recording `loop_run.py` had
already written rather than re-running it; the agent never called
`run_simulation`; and the single `commit()` was rejected at the static
pre-flight, before `_judge_replace_action_execution` reached
`sim_reviewer.review()` -- which is why it took 0 seconds.

```
trials used        1 of 3
check_staged       3
rounds            30 (the cap)
failing           19 -> 19      uncovered 25      passing 46
```

## What the loop did right

The requirement surface works, and the agent used it the way the tools intend:
`explain` → `focus` → `read_block`, repeatedly, before touching anything. It
never chased an UNCOVERED requirement. It read eight blocks across four
requirements before staging its first edit. The staged buffer behaved: two
`discard_staged` calls returned it cleanly to the accepted RTL, and the accepted
RTL is byte-identical at the end of the session.

**The undriven-driver guard fired and was right.** The agent's edit removed the
last driver of `scl_oen`, `sda_chk`, `sda_oen` and `state`. Verilator runs
`-Wno-fatal`, so that would have compiled, gone X at simulation, and surfaced
only as coverage quietly falling. The commit was rejected before simulating —
plan §7.1 pin 15, working, on a real agent's real edit.

## The defect it found, which cost the session its only trial

At round 19 the agent called `check_staged()`. It was told, in `warnings`:

> `scl_oen, sda_chk, sda_oen, state are still read but have LOST their last driver`

At round 20 it committed. The commit was rejected for exactly that.

The information was there. **The shape was not.** `commit` is emphatic —
"Commit rejected: … Add the replacement driver to this batch, or restore the
block you removed." `check_staged` returned the same fact as a bare string in a
`warnings` list, under a field reading `is_syntax_correct: true`, beneath nine
hundred characters of Verilator build report whose most prominent line is a
DECLFILENAME warning about the harness's own scratch file being called
`staged.sv`. Nothing in that payload says *this batch would be rejected*.

A dry run whose answer has to be inferred from a warnings list is one the agent
will read past — and the whole reason `check_staged` is free is to stop a trial
being spent on a question it can answer.

Fixed: `would_commit_be_rejected(text)` is now one function used by both the
free check and the paid one, so they cannot drift, and `check_staged` returns
`would_commit_be_rejected` plus the verdict text. `syntax_output` collapses to
`"clean"` on success.

## The second defect: the agent never saw one internal signal

`block_internals` was empty in all five `explain` calls. Two causes, both the
harness's:

* `loop_run.py` ran the suite with `trace=False`, so **no waveform was dumped
  at all**; and
* `SpecflowReviewer.vcd_path` is only assigned inside `review()`, which
  `--reuse-baseline` skipped.

So §5.6 item 3 -- "the trace says the boundary misbehaved; the VCD says what
the suspect blocks were doing while it did" -- was dark for the whole session,
and **nothing in the payload said so**. `_block_internals` returns `{}` both
when the blocks had nothing to report and when there is no waveform, and those
are different facts. The agent read boundary ports and source believing it had
been shown everything: exactly the evidence poverty B21 records the debugger
inventing a timing theory from.

Fixed three ways. `explain` now emits `internals_warning` naming which of the
two states it is in. `loop_run.py` dumps a waveform. And the waveform is now
paired PER TESTPOINT (`vcd_by_tp`), because `run_suite` writes one per
testpoint -- one simulator process each -- so a single session-wide `vcd_path`
cannot be right for every requirement, and showing the wrong testpoint's
waveform is worse than showing none: it looks like data.

## A third: `focus` silently retired block ids

The agent read block `C3` at round 7. At round 8 it focused a different
requirement, which rebuilt `blocks_by_id` from that requirement's slice --
without `C3`. At round 29 its `replace_block("C3")` came back "Unknown
block_id 'C3'. Use list_suspect_blocks() first", which reads as the agent
having invented an id it had in fact been given, and points it at a tool that
would not have helped. (`C9` and `C1`, at rounds 11 and 12, WERE inventions.)

`focus` now reports `ids_no_longer_in_scope` and says re-focusing reaches them
again.

## Unmeasured, and worth not over-reading

`what_would_satisfy_it` returned "NO single-value change at the deciding edge
satisfies this check, so the defect is TEMPORAL" on **five of five** calls. That
may be true of these five checks -- all are `eventually`/`throughout` over a
window -- but a field that answers identically every time carries no
information, and it has not been shown to discriminate. Do not cite it as
working until it has been seen to say the other thing.

## What is still wrong, and is the agent's problem rather than the harness's

After the rejection the agent thrashed: rounds 21–29 are stage, check, discard,
re-stage, discard, and a final `replace_block` on a block id it invented (`C3`,
after inventing `C9` and `C1` earlier — `read_block` refused all three
correctly). It never re-committed, and the round cap ended the session with two
trials unspent. Spending 30 rounds and one trial to change nothing is the
outcome to beat; it is not evidence the tools are wrong, and the loop's own
record is what makes that legible.

## What this does not measure

One agent, one candidate, one design, one session, a 3-trial budget and a
30-round cap it hit. Nothing here says the loop converges with a larger budget,
and nothing says a different agent would thrash the same way.

**And, most of all: the simulate-and-judge path was never executed.** Whether a
committed edit is correctly re-decided against the frozen 90, whether the
ratchet accepts or rolls back, and whether the loop can move a single
requirement from FAILS to passes are all still open. This run says the static
half works and names three things the agent was not told; it says nothing about
the half that costs twenty minutes.
