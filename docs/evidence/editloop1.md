# The first live RTL-editor loop: 30 rounds, 1 trial, zero change

A Sonnet agent drove the real `_EditSession` through `docs/evidence/edit_drive.py`
against the paced 90-check instrument (`docs/evidence/instrument.py`), on the
ChipVerilog codex t1 candidate. The golden RTL was withheld: the agent saw the
requirement text, the check's own complaint, the recorded boundary trace, the
suspect blocks' VCD internals and the candidate's source, and nothing else.

**Result: 19 failing requirements before, the same 19 after.**

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
