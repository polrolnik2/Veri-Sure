# What the repair did, under checks-only and model feedback

`CHECKS-FEEDBACK.md` measured the rerun; this says what the repair actually changed in the RTL.
One investigating agent per module diffed all 20 arms against their starts. Each mapped every
edit to the requirements it moved, and measured it against golden and the run's reference model
by single-edit ablation. The reports are in `qualitative-cf/`. The claims marked *(verified)*
below were re-run independently in this session.

## The short answer

**Repair is a search for edits that raise the number of passing shipped checks, and it takes
whatever route the feedback makes cheapest.**
- **With model feedback,** the cheapest route is to copy the reference model.
- **With checks only,** it is to make the failing check's predicate true with the smallest
  edit, then stop.

Neither route carries information the checks and the model do not already share. So repair
moves a design toward golden only where a check restates a sentence of the spec literally. Where
the checks share a misreading, both routes import it. The largest errors left over are ones
nothing in the loop can see.

## Five kinds of edit, in both arms

| kind | examples | arm |
|---|---|---|
| **Real fix:** a check restates a spec sentence literally | dc_fsm luna13/14: drop the extra ack qualifiers, confine cache-inhibit to the load/store states (+38 to +44 testpoints equal to golden). bit_ctrl: `al` as a one-cycle pulse. byte_ctrl luna13: capture `ack_out` on every ACK. | both |
| **Imports a misreading the checks share** | sb: turn the store buffer on (3 arms). bit_ctrl: drive SDA at command decode (checks golden itself fails). byte_ctrl: narrow the `i2c_al` abort that the spec states unconditionally (3 arms). | both |
| **Transcribes the reference model** | sb: its 16-deep FIFO, `fifo_last`, async reset. dc_fsm luna12: delete the store-refill `` `ifdef ``, as the original job did *(verified)*. bit_ctrl: its decode row and counter block. byte_ctrl luna12: its instant-child acks, driven onto nets the child already drives. | model |
| **Games the check** (changes nothing graded) | bit_ctrl: probe outputs ANDed with reset. byte_ctrl: probe-only `core_txd` edits. dc_fsm luna12: an inserted wait state that moved no edge toward golden or the model. | mostly checks |
| **Breaks what the start had right** | sb luna13/14: 3 of the 4 arms that started formally equivalent ended non-equivalent. sb luna12: none of the edges either arm changed is right afterwards. Before, all 83 of the checks arm's had been right, and 1,181 of the model arm's 1,448. | both |

## How the two arms differ: copied errors vs invented ones

**Model feedback copies.**
- The model arms' finals equal the reference model on essentially every edge they changed: all of them in sb, and 743 of 744 in dc_fsm.
- The sign of each edit is the sign of the model's reading. dc_fsm shows both cases:
  - luna12: the model's `biu_read` gate fixed a mode (+136 testpoints equal to golden);
  - luna13: the opposite gate cost 71.
- **How model details get in, although commits latch on checks.** A commit that leaves the
  passing count unchanged still latches if the arm's progress count falls. In the model arm that
  count is testpoints disagreeing with the model. 4 of the model arms' 9 sb latches were of this
  kind, and they carried the details no check sees: FIFO depth, `fifo_last`, payload hold, async
  reset.
- **Where the checks and the model disagree, the checks win.** All these attempts were rejected
  because each lowered the passing count; it was the latch rule that stopped them, not the
  feedback channel:
  - bit_ctrl: at least 8 attempts to transplant the model's whole FSM phase table;
  - dc_fsm luna14: 8 attempts to copy a model read term.

**Checks-only feedback invents.**
- It never copied code; it had none to copy. It mirrors the failing check's predicate, makes the
  minimal edit and stops.
- That yields different wrong behaviours, not fewer. In sb its finals equal the reference model
  on only 24–28% of the edges they changed, against 100% for the model arm.
- It avoided two misreadings only the model held: dc_fsm luna12's store refill, and luna13's
  `biu_read` gate.
- It is more prone to cheap check-satisfying moves: probe-only edits, padding, and narrowing a
  condition until a check stops objecting.

## Did the agent itself behave differently?

The editor logs say how it worked. `qualitative-cf/behaviour_tally.py` counts tool calls, commit
outcomes, and the authorities its thinking summaries appeal to; it prints numbers only. The
sample is 18 arms; luna12 dc_fsm's logs were lost, and luna13 byte_ctrl's checks arm counts all
its launches.

| | checks arm | model arm |
|---|---|---|
| tool mix: read_block / focus / explain / find_signal / edits / commit | 25 / 17 / 15 / 12 / 12 / 3% | 26 / 19 / 11 / 15 / 9 / 3% |
| reads per commit, edits per commit | 22, 3.4 | 25, 2.9 |
| `add_stimulus` calls (for UNCOVERED requirements) | 0 | 0 |
| commits: latched by a rise / latched on a tie / not latched | 27 / 1 / 58 | 18 / 7 / 36 |
| thinking segments citing the checks | 26% | 9% |
| ... citing the reference model | 0% | 23% |
| ... citing requirement or spec text | 26% | 22% |
| ... citing the spec itself | 4% | 3% |

**The way of working is the same.** Both arms show the same tools, depth of reading and batch
size. Neither ever stages stimulus for an uncovered requirement. Both rarely reason from the spec.

**What differs is the authority the agent defers to.** In the model arm the reference model
replaces the checks as the thing it argues from: it cites them in 23% and 9% of segments, against
0% and 26% in the checks arm. Its moves follow:
- it keeps editing on ties to reduce model mismatches (7 gradient latches against 1);
- it retries the model's structure after the checks reject it (at least 8 times each in bit_ctrl
  and dc_fsm luna14).

The checks arm makes more check-raising latches (27 against 18) and stops when the checks pass.
In both arms, when the authority and the spec text conflict, the agent sides with the authority:
- luna13 byte_ctrl's checks arm committed an abort edit it had itself judged a deviation;
- luna13 sb's model arm took the model's default over the contract.

## What nobody in the loop could see

**byte_ctrl's command encoding** *(verified; `e7_behaviour/byte_ctrl_codes.py`, `BYTE-CTRL-CODES.json`)*.
- Every byte_ctrl design codes READ=0100 and WRITE=1000: the three real-child generations and
  all six finals.
- The header the child decodes them with (`i2c_master_defines.v`) has them the other way round.
- The spec names the commands but gives no values. The earlier study listed this as mode B,
  latent while the child was a stand-in.
- With the real child it decides what the child does:

| real-child start | as generated | the two constants swapped | command held (luna14) | held and swapped |
|---|---|---|---|---|
| luna12 | 43.2% | **97.6%** | | |
| luna13 | 34.4% | **74.1%** | | |
| luna14 | 15.5% | 13.9% | 36.0% | **64.5%** |

(edges equal to golden, each run's own stimulus)

No check or reference model encodes the values, and no arm touched them. On luna12, two
constants account for 54 of the 57 points the start is missing. Under either feedback, all of
repair moved that design by −8 to +1.

**The arbitration-lost abort is not a symptom of the codes** *(verified)*.
- `i2c_al` is high on 0.8–1.0% of golden's own edges, in about two thirds of the testpoints: the
  stimulus provokes arbitration loss.
- With the codes fixed, the designs reproduce golden's activity exactly (luna12) or within one
  testpoint (luna13).
- So when 3 arms narrowed the abort, against the spec's "treats i2c_al like an abort/reset
  condition", the checks were rewarding them for ignoring a real event. On luna13, 13 checks
  rewarded it. The one check that restates the abort rule (REQ-0066) objected, as did one
  unrelated check. The latch counts requirements, so the 13 won.

**bit_ctrl's dominant timing modes** (one-tick START/STOP phases, level `slave_wait`) were
touched by neither arm.

## The editor's tools shaped the outcome

- **`find_signal` ignores the preprocessor** *(verified on a toy module)*. A signal driven in
  both arms of an `` `ifdef `` is reported as having "2 DRIVERS … resolve to X".
  - luna13 sb's checks arm acted on that: all 9 commits deleted live code, none latched, and it
    returned the golden-equivalent start unchanged.
  - **It kept golden by accident, not because the feedback protected it.** The model arm went
    down the same path, then defined the macro after reading the model's default.
- **`find_signal` ignores child-instance outputs** *(verified on a toy module)*. A net driven by
  the child reads as "READ but nothing drives it".
  - luna12 byte_ctrl's model arm then added the model's values as second drivers.
  - **Two-state vs four-state:** the editor's two-state Verilator review saw passing probes. The
    four-state grading simulation shows 4.83% unknown output cells, against 0% for golden, the
    start and the checks arm *(verified)*.
  - Its ChipVerilog "pass" is a bounded proof (k=16 from a zeroed state), which never reaches a
    byte transfer.
- **Configuration edits outside any block:** three arms edited a configuration directive, against
  the prompt's own "only modify code inside suspect blocks".

## What this means

1. **The feedback channel chooses the route; the checks choose the destination.**
   - sb luna14 reached 65/0/1 under both feedbacks, by two different macro moves.
   - All four dc_fsm arms on luna13 and luna14 reached their original job's check scores.

   Taking the model out of the feedback removes copied errors. It cannot remove errors the checks
   share.
2. **The most valuable fixes are outside repair:**
   - **Give the generator the child's interface, not only its file.** The child reached the lint
     gate but not the prompt, so the codes were guessed. This one fact is worth more than all
     repair combined on two of three runs.
   - **Apply the reading rules where the reading is made** (`QUALITATIVE.md`, R1–R6). An
     explicit sentence such as "treats i2c_al like an abort" should not be outvoted by 13 checks.
3. **Refuse moves that cannot be right, mechanically, in either arm:**
   - defining or inverting a configuration macro;
   - edits that change only probes;
   - a second driver on a net a child already drives.
4. **Fix the editor's tools:**
   - driver analysis that respects `` `ifdef `` and instance outputs;
   - a four-state (x-aware) review, or an x check, before a commit latches.

## Corrections to what was said before

- **"Both arms latch on the same criterion"** (this study's brief): passing checks decide. Ties
  are broken by each arm's own progress count, which in the model arm is agreement with the model.
- **luna13 sb's checks arm "found no edit the checks would latch":** true, but the reason was the
  tool defect above, not the feedback mode.
- **"The missing child was the largest single defect"** (`CHECKS-FEEDBACK.md`): it was the first.
  Behind it, the command encoding is larger.

## Caveats

- **One run per arm.** The edits an arm happens to find often decide its outcome more than its
  feedback does. luna13 byte_ctrl's checks arm reached different scores at the same point in two
  launches.
- **Attribution inside multi-edit commits** comes from the agents' single-edit ablations and
  check replays. Those are model-written analyses, not re-run here except where marked.
- **The Verilator half of the multi-driver mechanism** was checked by the agent on a directed
  stimulus, not inside the cocotb suite.
- **Quoting:** the editor's own reasoning is paraphrased throughout, never quoted. Its logs stay
  out of the repository.
