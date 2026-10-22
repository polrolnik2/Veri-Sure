# luna13 i2c_master_byte_ctrl, checks-feedback arm -- a resumed run

The start is the generation with the real child (`../../editor-cf-gen/`, 49/27/21). The arm
needed five launches to finish; `editor_summary.json` and `chipverilog.json` cover the last.

1. **First attempt:** killed by the container's memory cgroup after round 1 (58/20/19). The
   reviewer held every check's per-testpoint rows at the time; fixed in 4eba03f. Discarded;
   the arm restarted from the start.
2. **Second attempt, from the start:**
   - Round 0's repair used 10 trials; review: 55/21/21.
   - Round 1's repair died on a provider 5xx after the stream retries ran out.
3. **Two resumes from the accepted 55 design, each with 2 rounds and 10 trials:** both died
   on a gateway connection reset (`upstream connect error ... connection termination`), with
   2 and 1 commits judged and none latched. Discarded: each re-ran round 1's repair from the
   same design. The crash came in a model call, not inside a commit, so the on-disk `rtl.sv`
   was the accepted design both times.
4. **Third resume, same start and budget, `EDA_STREAM_RETRIES=20` (transport only):**
   - one commit latched (55 -> 67);
   - one commit was rolled back (67 -> 58);
   - then a container restart interrupted it during a model call, so `rtl.sv` held the
     latched 67 design.
5. **Final resume, from that latched design, with the 8 trials left (2 rounds):**
   - review 67/10/20, then 72/7/18, then 75/5/17;
   - ChipVerilog: `function_fail`.

The trials that latched or were judged in the chain that produced the final design total 20
(10 + 2 + 8), over 3 repair rounds, matching every other job. The 3 commits of the two
discarded resumes did not latch and are not counted. The round-1 repair was therefore
attempted more than once, which a single uninterrupted run would not do.
