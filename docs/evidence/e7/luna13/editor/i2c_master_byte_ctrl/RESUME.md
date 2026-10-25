# luna13 i2c_master_byte_ctrl -- a resumed RTL Editor run

The attempt started 2026-10-14T12:25Z (9618620) generated rtl.sv (244 lines) and
reviewed it at 73 pass, 5 FAIL, 19 abstain of 97 requirements, 90 failing
testpoints. Rounds 0 and 1 each used 7 trials and latched none of their 14
commits, and round 2 reviewed at the same tally. Round 2's repair latched one
commit (passing 73 -> 79, failing testpoints 90 -> 133), staged one further
edit, and was simulating that edit's commit when the machine rebooted at about
01:15Z on 2026-10-15 (321 model calls; the log is
`../../../editor-usage/luna13-i2c_master_byte_ctrl-20261015T0117Z.jsonl`).

This record is the resume (669f875, `e7_module.py --rtl`, on fe7275d) with the
budget round 2 had started with -- 1 round, 6 trials -- so the total matches
every other job (3 rounds, 20 trials). It re-runs round 2's repair rather than
continuing it: that repair's model conversation and its two commits are not
carried over. `editor_summary.json` and `usage.jsonl` cover the resume only.

**It started from the wrong RTL.** It took the `rtl.sv` on disk at the reboot,
and `RTLEditor.commit` writes the staged batch there BEFORE judging it -- so
the file held the unjudged edit, not the latched design. That edit restores the
default `core_cmd <= I2C_CMD_NOP`, which makes the latched commit's other lines
redundant: the file behaves as round 2's input, and the resume's round 0
reproduced that tally exactly (73/5/19, 90 testpoints). The latched candidate
(79 passing by the editor's count) was not the starting point. It can be
rebuilt by deleting that one line.

**Its final RTL is a candidate the editor rejected.** The resume's one commit
did not latch (passing 73 -> 71: five requirements repaired, five broken, three
went dark), yet the final review scored it at 71/6/20, 119 testpoints. That is
`restore_best()`. `note_best` records every judged commit before the latch
decision, and the design the round started from is never recorded, so a round
that latches nothing hands back its best REJECTED candidate even when it is
worse than its input. Passing falls between rounds in 5 of the 17 editor jobs
(see `../../../EDITOR-RESULTS.md`), and that is the only way it can fall. The
ChipVerilog verdict is function_fail.
