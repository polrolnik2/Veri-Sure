# qualitative-cf: what repair did in the checks-feedback rerun

One report per module. Each was written by an investigating agent working from `BRIEF.md`:
`or1200_sb.md`, `or1200_dc_fsm.md`, `i2c_master_bit_ctrl.md` and `i2c_master_byte_ctrl.md`. Each
covers every arm of that module's jobs:
- the start → final diffs;
- the requirements each edit moved;
- single-edit ablations against golden and the run's reference model;
- a classification of every substantive edit.

The synthesis across modules is `../CHECKS-FEEDBACK-QUALITATIVE.md`.

**Re-checked independently in this session** (scripts or direct inspection):
- **byte_ctrl codes:** every byte_ctrl design swaps READ/WRITE relative to
  `i2c_master_defines.v`, and the spec gives no values. The swap alone, and with luna14's held
  command, gives the figures in `../BYTE-CTRL-CODES.json` (`../../e7_behaviour/byte_ctrl_codes.py`).
- **byte_ctrl `i2c_al`:** activity matches golden once the codes are fixed.
- **byte_ctrl abort:** the three arms that narrowed the abort do contradict the spec sentence and
  golden's `rst | i2c_al`.
- **luna12 model final, unknown cells:** 4.83% in the four-state grading simulation, against 0%
  for golden, the start and the checks final.
- **`find_signal` defects:** it reports `` `ifdef `` alternatives as two conflicting drivers, and a
  child-driven net as undriven (toy-module demonstration).
- **dc_fsm luna12 `ifdef`:** the model arm deletes the store-refill `ifdef`, as the original job
  did. The checks arm keeps it.
- **Latch rule:** a tie on passing requirements latches on the arm's own progress count (the
  "LATCHED ON THE GRADIENT" path in `eda_agent/rtl_editor.py`).

**Not re-checked:**
- per-edit attributions inside multi-edit commits;
- the bit_ctrl golden-verdict counts, which come from the run's hand-bound audit;
- the Verilator half of the luna12 byte_ctrl multi-driver mechanism.

**Not committed:**
- the agents' scratch scripts and their outputs, because those embed the editor's reasoning;
- the editor logs.

The editor's own words are paraphrased, never quoted. Tool messages, spec sentences and RTL are
quoted as they are. `BRIEF.md` lists the session's local paths as given to the agents.
