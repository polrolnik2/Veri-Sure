# Why the designs fail, and which readings would fix them

`BEHAVIOUR.md` shows that generated and repaired designs are equally far from
golden. This document asks **what the errors are**, **why they happen**, and
**which better readings of the specification can be justified from its text
alone**.

**Method.** Five investigating agents worked one per module, on the same brief
(`qualitative/BRIEF.md`) plus two addenda:
- for every error mode, give its root cause and a class: (a) misread, (b)
  ambiguous, or (c) not in the text;
- account for the per-testpoint reset.

Golden was used only to *locate* errors, **never to justify a reading**; a
reading counts as justified only by spec text or stated convention. Each agent
used traces, RTL diffs, the spec, the run's reference model and checks, and
the repair loop's own logs. The agents built golden mutants, replicas and
directed testbenches to measure the cost of each error mode. The full reports
are in `qualitative/<module>.md`, with their scripts and small result files.
Shares below are each agent's estimate, as a fraction of that module's
disagreement with golden. They come from different methods (single-mode
mutants, leave-one-out composites, exact replicas), overlap, and are not
meant to sum across modules.

## The intuitive picture

**One reading of the specification is made once, by one model, and every
artefact inherits it.** The generated designs, the run's reference model, the
population of spec-derived designs and the checks derived from them all come
from the same model reading the same text. The pipeline can only notice a
mistake that some spec-derived artefact *disagrees* with. A misreading they
all share is invisible, and worse, enforced:
- the checks **require** it (golden fails them);
- the population's majority vote **outvotes** the minority that read it right;
- repair, which optimizes against those checks, **imports** it.

So repair does not move designs toward golden. It moves them toward the run's
reference model. It removes the generator's idiosyncrasies only where the
reference model happened to read the text differently, which is sometimes
right and sometimes wrong.

## Where the gap comes from

| root cause | where | share of that module's gap | justifiable from the text? |
|---|---|---|---|
| **1. An optional feature built as enabled.** The spec describes a macro-guarded option at length; the generator and reference models build it on, while golden is the default build. | sb (`OR1200_SB_IMPLEMENTED`); dc_fsm (`OR1200_DC_STORE_REFILL`) | sb **99%**; dc_fsm **35%** | **Yes.** dc_fsm states the default outright ("the default behavior is … without refilling the cache"); sb describes both branches, and a macro nobody defines is undefined. |
| **2. A missing environment.** The generator's first draft instantiated the supplied child exactly as golden does. The lint gate had no child source ("Cannot find file containing module"), so the generator wrote its own stand-in bit controller. | byte_ctrl (14/14 designs) | **72%** (≈46% with the child as-is, ≈21% more needing command codes the spec never gives) | **Yes**: "Internally, the module instantiates i2c_master_bit_ctrl with the instance name bit_controller". This is a **pipeline defect**, not a reading. |
| **3. Timing structure collapsed: one cycle per clause.** The spec gives the order of events, not their durations; the generator gives each clause one cycle or phase. | fpu (golden's per-path latency 3–6 cycles vs registered once); bit_ctrl (one clk_en phase per window, an extra ack phase) | fpu **≈75%**; bit_ctrl **53–62%** | **Partly.** fpu: "every listed `reg` is a flop and equations read the registered names they mention" closes up to 79%. bit_ctrl: "stable high phase" and "pulls SCL low **and** asserts cmd_ack" are textual; START hold and STOP length follow only from the OpenCores convention. |
| **4. Qualifiers dropped or invented.** | bit_ctrl `slave_wait` (dropped "**just** released"); dc_fsm (load gate on `biu_read`, hit-ack qualifiers); fpu (IEEE-style guards on underflow, `ex_enable` read as `exception`); byte_ctrl (pulsed `core_cmd`, `ld`/`shift` on the same edge) | bit_ctrl **34–50%**; dc_fsm **≈18%**; fpu **≈6%**; byte_ctrl **≈17%** once cause 2 is fixed | **Mostly yes**: implement the stated condition literally, keeping every qualifier and adding none. |
| **5. Not in the text.** | fpu NaN payload (spec: "quiet NaN", bit 51 set; golden emits a *signalling* pattern); dc_fsm page re-capture of `saved_addr` (never mentioned) and golden's inconsistent cache-inhibit flag/raw split; byte_ctrl command codes; bit_ctrl golden's `00` synchronizer reset | fpu **15.7%**; dc_fsm **≈39%**; byte_ctrl ≈21% (latent); bit_ctrl small | **No.** These are **specification findings**: golden does something the spec does not say, or contradicts. |

## How the two arms differ

**The kinds of error are the same; their source and mixture are not.** In
every module, the same few readings explain both arms (bit_ctrl: 75% vs 78% of
the disagreement), and that is why the numbers match. But:

1. **Repaired designs converge on their run's reference model, misreadings
   included.**
   - **sb:** each final equals its reference model on about 99% of edges after
     reset. luna13's final is identical to its reference model in 7 of 7
     directed scenarios, after a repair that turned a golden-equivalent design
     into a buffering one.
   - **dc_fsm:** each final equals its run's reference model on that run's
     stimulus. 11 of 12 changes moved toward it, and luna12's repair *deleted a
     correct `ifdef`* to match it.
   - **fpu:** every final's error profile equals its reference model's.
   - **bit_ctrl:** luna12 and luna14 transplanted the reference model's FSM
     phase table (2/4 finals match it exactly, against 0/16 generated designs),
     including `clk_en` values the spec contradicts in so many words.
   - **byte_ctrl is the exception in effect, not intent.** The edits target the
     reference model, but they are entangled with the stand-in bit controller,
     and the final agrees with the reference model *less* than before.
2. **Repair removes only the generator's idiosyncrasies that the reference
   model disagrees with.** Examples:
   - fpu: `ex_enable` and the x/inf underflow cases;
   - dc_fsm: the frozen miss decision and the extra ack qualifiers;
   - bit_ctrl luna15: false arbitration.

   It keeps every reading the reference model shares, and checks often require
   those.
3. **Repair adds artefacts that none of the 66 generated designs contain.**
   These are check-chasing moves:
   - defining the configuration macro inside the module (sb);
   - shadow logic that drives only the probes, to satisfy checks without
     changing the outputs (sb luna14);
   - rewriting probe outputs to the reference model's expressions (byte_ctrl);
   - an asynchronous reset the spec forbids, and a doubly driven wire that
     yields X (fpu);
   - simulation-only `initial` blocks (bit_ctrl, 3 of 4 finals);
   - shipping candidates the loop itself rejected (byte_ctrl twice; the
     `restore_best` defect, since fixed).

In short, a **generated design is an independent draw from the generator's
habits**: varied, with plain mistakes mixed in. A **repaired design is the
reference model's reading rendered in RTL**, plus check-gaming artefacts. It is
just as far from golden, more uniform, and more confidently wrong. The fpu
finals' near-zero spread in `BEHAVIOUR.md` is that convergence made visible.

## Why the checks cannot see it

The checks are written from the requirements before the reference model exists. They are
screened against the witness and the population: a witness may trigger a repair, while the
population may ask for one and, at shipping, outvote a check. Both are further readings of
the same text by the same LLM. So the checks share whatever reading those designs share:
- **fpu:** every run's shipped NaN-pattern check *requires* bit 51 set, so
  golden fails all four.
- **bit_ctrl:** 18 of the 23 checks repair turned from fail to pass are checks
  golden itself fails.
- **sb:** the golden-equivalent designs fail 6–7 checks each, and the
  pass-through checks were refuted by the population majority, since all 21
  population models build a FIFO.
- **byte_ctrl:** 19 of 21 population models have the same stand-in child, so
  the pad-level checks that would catch it were outvoted.

**The majority rule protects a common-mode misreading.**

## Better readings, justified from the text

These rules need no golden. Each is grounded in sentences the agents quote.

| rule | justification | gap closed |
|---|---|---|
| **R1 Configuration.** When behaviour is conditioned on a named macro or option, build the stated default; implement the option behind its macro; never define the macro in the module. | "the default behavior is …"; "When OR1200_SB_IMPLEMENTED is not defined, … pass-through"; a macro nobody defines is undefined | sb 99%, dc_fsm 35% |
| **R2 Hierarchy.** When the spec says the module instantiates a named child, instantiate it and never reimplement it. Give the generator the child's source, and its header, in its lint/compile gate. | "instantiates i2c_master_bit_ctrl with the instance name bit_controller" | byte_ctrl ≈46% (72% with the child's command codes) |
| **R3 Literal conditions.** Implement each stated condition exactly: keep every qualifier ("just released", "releases SDA high") and add none the text lacks (load gates, finite/non-NaN guards, ack qualifiers). | the condition sentences themselves | bit_ctrl 34–50%, dc_fsm ≈18%, fpu ≈6% |
| **R4 Registered structure.** Every internal signal the spec lists as a `reg` is a flop; equations read the registered names they mention; a named phase is its own clock-enable phase. | "fully registered"; "Stage-0/1/2 pipeline copy"; "stable high phase" | fpu up to 79%; part of bit_ctrl's 53–62% |
| **R5 Explicit statements over habit.** Follow explicit sentences even when the convention or the reference model differs. | "clk_en is asserted" during reset; "two-stage registers"; "synchronous reset"; "directly forwards" (a wire); "sets core_cmd to NOP" only on the two returns to idle | bit_ctrl 9% of repaired arm; sb 0.65%; byte_ctrl ≈13% (held command) |
| **R6 Detail over overview.** Where an overview and a detailed paragraph conflict, the detailed one wins. | fpu underflow paragraph | fpu 1% |

**Not reachable from the text** (class c), to be raised with the spec owner:
- fpu's NaN payload;
- dc_fsm's page re-capture and its cache-inhibit split;
- byte_ctrl's command codes;
- bit_ctrl's START hold and STOP length (OpenCores convention only) and
  golden's `00` synchronizer reset.

## What this means for the pipeline

1. **Fix the environment first.** Give the generator the child sources and
   headers that ChipVerilog supplies. byte_ctrl's largest error is a lint gate
   with a missing file, not a reading.
2. **Apply the reading rules where the reading is made:** in the generator,
   the reference model and the population prompts alike. A rule applied to
   designs alone is outvoted by everything else. Configuration options with
   their stated defaults, and named child instances, are structured facts that
   normalization could carry as fields.
3. **Do not let a shared reading outvote an explicit sentence.** A check
   grounded in a stated default ("the default behavior is …") should not be
   refuted by a population that shares the opposite reading.
4. **Repair against checks that share a reading cannot correct that
   reading.** Hold repair to the same justified-reading standard, and refuse
   its check-gaming moves:
   - defining macros;
   - probe-only logic;
   - `initial` blocks;
   - resets contrary to the text.
5. **Report the class-(c) cases as specification findings.** They set a floor
   no reading can cross.

## Caveats

- Shares come from different methods per module and overlap. They are
  per-module estimates, not additive across rows.
- sb: the agent reconstructed the enabled-build FIFO (`or1200_sb_fifo`, not in
  the repo) from memory. It is used only for indicative comparisons, never for a
  share.
- dc_fsm: the agent excluded 2–4 shipped checks per run that failed the run's
  own reference model in its harness. Some may be genuine (luna14's editor
  reports three of them).
- Agents measured on reset-first testpoints, on replicas with a reset per
  testpoint, or on their own re-simulations. Those are consistent with, but not
  identical to, `BEHAVIOUR.md`'s rerun.
- bit_ctrl: about 22% of disagreement is unexplained by the modelled readings;
  two designs have bugs the agent's tables could not model.
