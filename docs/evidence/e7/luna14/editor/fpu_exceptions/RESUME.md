# luna14 fpu_exceptions -- a resumed RTL Editor run

The attempt started 2026-10-14T09:51Z generated rtl.sv (553 lines), repaired it once
(round 0: 103/136 shipped checks, 309 failing testpoints -> round 1: 131/136, 72 failing
testpoints; 8 trials) and died during its round-1 repair when the SDC gateway streamed
"The server is overloaded or not ready yet" past the two stream resends (187 model calls).

This record is the resume (669f875, `e7_module.py --rtl`): the round-1 RTL with the budget
the attempt had left -- 2 rounds, 12 trials -- so the total matches every other job
(3 rounds, 20 trials). Its round 0 is the attempt's round 1 (131/136, 72 testpoints,
reproduced exactly). `editor_summary.json` and `usage.jsonl` cover the resume only; the
attempt's calls are in `../../../editor-usage/`.
