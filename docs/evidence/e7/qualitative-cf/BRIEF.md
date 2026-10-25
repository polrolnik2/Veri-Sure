# Brief: what did repair actually do, under checks-only vs model feedback?

## Background (read first)
- `/home/user/Veri-Sure/docs/evidence/e7/CHECKS-FEEDBACK.md` -- the experiment and its numbers. Each JOB
  repairs ONE start design twice with the RTL Editor (LLM repair loop, 3 rounds / 20 trials, a commit
  latches only if the count of PASSING shipped requirements rises):
  - **checks arm (`cfc`)**: the editor sees only the run's shipped checks (failing requirement text, the
    check's complaint + edge, the design's own port values, the checks' Python source). No reference-model
    values.
  - **model arm (`cfm`)**: additionally sees the run's reference model (`ref_model.py`) as "the expected
    behaviour" and DUT-vs-model mismatch rows.
  Both latch when passing shipped requirements rise. A tie also latches ON THE GRADIENT (nothing silenced and
  the progress count falls): that count is failing check instances in the checks arm and failing testpoints
  against the model in the model arm, which is a channel for model details (`rtl_editor.py`, "LATCHED ON THE
  GRADIENT").
- `/home/user/Veri-Sure/docs/evidence/e7/QUALITATIVE.md` and `.../qualitative/<module>.md` -- the earlier
  study's error modes per module (root causes 1-5, reading rules R1-R6). Map what you find onto those modes
  where they apply; say when something is new.
- The shipped checks are NOT derived from the reference model: they are written before it from the
  requirements, by the same LLM, and kept/dropped by a vote of spec-derived population designs. The
  reference model is later debugged to satisfy the frozen checks.

## Data (read-only; do NOT modify anything under /home/user/Veri-Sure; do NOT run git)
Repo evidence `E=/home/user/Veri-Sure/docs/evidence/e7`:
- Start designs:
  - sb / dc_fsm / bit_ctrl: `$E/<run>/editor/<module>/rtl_generated.sv` (the original job's round-0 design);
  - byte_ctrl: `$E/<run>/editor-cf-gen/i2c_master_byte_ctrl/rtl_generated.sv` (generated with the real child
    `i2c_master_bit_ctrl` available; earlier designs all had a stand-in child).
- Finals: `$E/<run>/editor-cf-checks/<module>/rtl.sv` and `.../editor-cf-model/<module>/rtl.sv` (with probe
  ports), plus `rtl_deliverable.sv` (spec interface; what is graded). luna12 dc_fsm's model arm has only
  `rtl_deliverable.sv` (its rtl.sv was lost; see NOTE.md there).
- The ORIGINAL job's final (model feedback, older code): `$E/<run>/editor/<module>/rtl.sv`.
- `editor_summary.json` in each arm dir: `history` = one entry per round with `pass/fail/abstain` and the
  `failing` / `abstaining` requirement uid lists -> which requirements each round repaired or broke.
  `chipverilog.json` = formal verdict vs golden (`bounded_seq` k=16 passes are weak; `induction` is a proof).
Run artefacts (corpora) `EQ=/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq2`
(THIS work dir only -- `eq-STALE-before-reset-fix` is wrong, never use it):
- `$EQ/corpora/<run>/<module>/`: `requirements.json` (uid -> text), `shipped.json` (shipped check bodies,
  their req uids and Python source), `normalized.json`, `contract.json`, `ref_model.py` (the run's reference
  model), `stimulus.json`, `population/`.
- `$EQ/stim/<run>/<module>.json`: `{"inputs", "outputs", "tps": {tp: {"rows": [[inputs per edge]],
  "ref": [[the run's ref-model outputs per edge]]}}}`.
- `$EQ/out/<module>/<design>.json`: OPEN-LOOP traces `{stim_run: {tp: [[output hex per edge]]}}`, all designs
  driven by the same input rows (outputs in the stim file's `outputs` order; golden 'x' = don't care).
  `$EQ/cl_out/<module>/<design>.json`: CLOSED-LOOP traces (waits resolve on the design's own outputs).
  Design names: `golden`, `<run>.r0` (start for sb/dc_fsm/bit_ctrl), `<run>.cfg` (byte_ctrl start),
  `<run>.cfc` (checks arm final), `<run>.cfm` (model arm final), `<run>.final` (original final),
  `<run>.gen1..3`.
- Per-design metrics: `$EQ/latency.json` (rows with module, run, kind, g_edge, g_tp, cl_order, ref, ship...).
- Editor logs (local only, may be large; the editor's reasoning, tool calls, commit results with LATCHED /
  "did NOT latch" messages): `/home/user/runs-cf/<run>/results/<module>/cf-checks/editor.log` and
  `.../cf-model/editor.log`. luna12 dc_fsm's logs were overwritten (no "why" available there). luna13
  byte_ctrl's checks arm ran in pieces: `.../cf-checks.oom-killed`, `.cf-checks.crashed-apierror`,
  `.crashed-connreset`, `.crashed-connreset2`, `.interrupted-restart`, then `cf-checks` (final resume).
- Golden (GRADING ONLY -- use it to locate errors, never to justify a reading):
  `/home/user/Veri-Sure/benchmarks/chipverilog/Des/*/<module>/<module>.v`; the spec the editor saw:
  `.../<module>/description.txt`.
- Python with project imports: `/home/user/Veri-Sure/.venv/bin/python3`; iverilog/vvp/yosys installed.
  Traces are large for i2c modules (hundreds of MB): load one file at a time; use `nice -n 19`.

## Questions, for every job/arm of your module
1. **What changed.** Diff start -> checks final and start -> model final (`diff -u`, or read both). Describe the
   edits in RTL terms: which blocks, which behaviour (state machine, timing, conditions, config macros,
   probes, resets...). Note added artefacts (macro definitions, probe-only logic, `initial` blocks,
   simulation-only constructs, dead code).
2. **Why.** Which requirements each change repaired or broke (summary `history` lists, the log's LATCHED
   lines). Quote the requirement text briefly. For the model arm, did it copy the reference model's code or
   expressions (compare with `ref_model.py`)?
3. **What it did to behaviour.** At edges/testpoints where start and final differ, does the final agree with
   golden, the ref model (`ref` rows), both or neither? Give counts on the run's own stimulus. Which outputs?
4. **Classify each substantive change:**
   - (a) a real fix toward golden that the spec text justifies;
   - (b) importing a shared misreading the checks require;
   - (c) check-gaming (satisfies a check without changing the spec behaviour the check is about);
   - (d) neutral refactor;
   - (e) a regression that breaks behaviour the start had right.
5. **Arms compared.** Do the two arms make qualitatively different moves from the same start? Did the
   checks arm avoid things the model arm did, or find different routes to the same checks? Where one arm
   stalled (no latch), why (from the log)?

## Deliverable
Write `/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual-cf/<module>.md`
(max ~800 words) and return the same text as your final message:
- a short table per job, with columns: arm | main edits | requirements repaired/broken | effect vs golden /
  ref (numbers) | class;
- then one paragraph on the qualitative difference between the arms for your module.

Be concrete and evidence-based (file:line, requirement uids, counts); say what you could not establish. Keep
scratch files under `qual-cf/<module>/`.
