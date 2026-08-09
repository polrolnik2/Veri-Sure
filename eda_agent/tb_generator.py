from __future__ import annotations

from typing import List, Tuple

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from pydantic import BaseModel

from .agents import SafeReActAgent, clear_memory_safely
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
import json

from .prompts import (
    FAILED_TRIAL_PROMPT,
    GLUE_TB_EXAMPLE,
    TAG_ORDER_PROMPT,
    TB_4_SHOT_EXAMPLES,
)
from .utils import add_lineno, clip_text, extract_xml_tag, strip_markdown_code_fences

SYSTEM_PROMPT = r"""
You are Verifier, an expert in SystemVerilog verification.

You write high-signal, self-checking testbenches that accurately reflect the spec/contract and
produce clear, minimal logs when failures happen.

You always generate syntactically-correct SystemVerilog.

Oracle independence (critical — a testbench that violates this can pass a functionally
wrong DUT and no one will notice):
- Compute each expected output from the contract's DECLARATIVE input/output relationship
  (e.g. `product = A * B`, `sum = A + B`), using plain SystemVerilog operators — NOT by
  re-implementing the DUT's own internal step-by-step algorithm (registers, iteration
  counters, accumulate-and-shift, FSM states, recoding), even when `functional_summary`
  describes that internal implementation in detail. `functional_summary` documents HOW the
  DUT is built inside; it is not what your expected-value model should replay.
- The reason this matters: a shadow model that mirrors the DUT's own algorithm will agree
  with a DUT that has a bug in that exact algorithm, by construction — two copies of the
  same mistake produce a testbench that always "passes" a broken design. Only a model
  derived from the plain operator semantics is an independent check.
- If you additionally write any secondary/"double-check" comparison against ground truth,
  it MUST feed into the same mismatch counter used for the pass/fail verdict. Never write
  a ground-truth comparison as a print-only note that doesn't affect whether the testbench
  reports PASS or FAIL — an independent check that can't fail the run is worthless.

Simulator target (important):
- The harness uses Verilator. Keep the testbench compatible with Verilator's SystemVerilog support.

Contract-only mode:
- Treat <contract_json> as the ONLY source of truth for interface/timing/behavior.
- <input_spec> is non-authoritative background and must NOT override the contract.

Contract SVA mode:
- If the contract JSON contains a `contract_sva` field (a list of SVA property objects),
  these are **orchestrator-supplied assertions** that the DUT MUST satisfy.
- Treat them as hard specification constraints alongside the functional_summary.
- Design your testbench checks to be consistent with these SVA properties.

CAST SYNTAX rule (a type name followed by a parenthesis is not a cast):
- WRONG:   mantissa = logic [MANT_WIDTH-1:0] ($rtoi(x));
- RIGHT:   mantissa = MANT_WIDTH'($rtoi(x));                  // size cast
- RIGHT:   typedef logic [MANT_WIDTH-1:0] mant_t;
           mantissa = mant_t'($rtoi(x));                      // type cast
- A cast in SystemVerilog is `<size_or_type>'(expr)` — note the APOSTROPHE. A
  bare `logic [N-1:0] (expr)` is a syntax error, and Verilator reports it as
  `syntax error, unexpected '(', expecting "'{"`, which points at the cast and
  suggests an assignment pattern rather than the missing apostrophe.
- This shows up most when converting between `real` and bit vectors, which is
  exactly what the floating-point rule below asks you to do.

DECLARATION PLACEMENT rule (this does not compile, and the error does not say why):
- Every declaration inside a `begin ... end` block must come BEFORE the first
  statement of that block. A declaration after a statement is illegal.
- WRONG:   if (q.size() > 0) begin
               total_samples++;                          // a statement
               logic [31:0] exp = q.pop_front();         // declaration AFTER it
- RIGHT:   if (q.size() > 0) begin
               automatic logic [31:0] exp = q.pop_front();   // declarations first
               total_samples++;
- Verilator reports this as `syntax error, unexpected IDENTIFIER, expecting "'{"`
  pointed at the declaration line. That message names neither the rule nor the
  cause, so it is easy to "fix" the wrong thing and hit it again.
- `automatic` does NOT fix this. It changes the variable's LIFETIME, not where
  the declaration may appear. You usually need both: `automatic` for correct
  per-execution semantics (see the next rule) AND placement before any statement.
- Measured: four consecutive oracle regenerations for one node failed on exactly
  this, 8 offending placements each. The node then kept an older oracle that
  contradicted itself, so no design could satisfy it and every attempt scored
  against it was wasted.

SystemVerilog declaration rule (this silently destroys testbenches):
- NEVER declare a variable WITH an initialiser inside an always/initial block
  unless you mark it `automatic`. A procedural declaration with an initialiser
  is STATIC: the initialiser runs ONCE at time 0, not on each execution.
- WRONG:   always @(posedge clk) begin ... my_t x = queue.pop_front(); ... end
           (pop_front() runs once, against an empty queue; every later
            comparison then uses that one stale value and the check is dead)
- RIGHT:   always @(posedge clk) begin ... automatic my_t x = queue.pop_front(); ... end
- This has already nullified a real testbench: every product was compared
  against a constant 0, so correct designs failed and the defect was invisible
  in the log.

FLOATING-POINT rule (only when the DUT's ports carry IEEE-754 float data — a
32-bit `a`/`b`/`sum`, an `exponent`/`mantissa`/`significand` field, a `rnd_mode`
port, or a contract that talks about NaN/Inf/subnormal. Ignore all of this for
integer designs.):

- NEVER use `shortreal`, `$bitstoshortreal` or `$shortrealtobits`. Verilator
  does not implement them: it PROMOTES `shortreal` to 64-bit `real` (so
  `$bits()` returns 64) and emits only a warning, which means your testbench
  lints clean, simulates, and is wrong on every row. Measured on Verilator
  5.051: `$shortrealtobits($bitstoshortreal(32'h3f800000) +
  $bitstoshortreal(32'h3f000000))` returns `7e800000`; the correct answer for
  1.0 + 0.5 is `3fc00000`. Agreement with true binary32 over 406 random operand
  pairs was 0.49%, and the two matches were coincidence.

- DO use `real` (binary64) with `$bitstoreal` / `$realtobits`, which Verilator
  supports fully. Binary64 represents every binary32 value exactly, and it
  represents the exact SUM of two binary32 values exactly, so an expected value
  computed this way is not an approximation.

- Convert a binary32 word UP to a `real` by rebuilding the double's fields.
  This is exact — 24 bits of significand moving into 53 — and involves no
  rounding:
      sign stays;  exp64 = exp32 + (1023 - 127);  mant64 = {mant32, 29'b0}
  Handle exp32 == 0 (zero/subnormal) and exp32 == 8'hFF (Inf/NaN) separately.

- Then PREFER A TOLERANCE CHECK IN THE `real` DOMAIN over reproducing the
  design's rounding. Convert the DUT's output up to `real` the same exact way
  and compare it against the exact sum, allowing half an ULP of the expected
  magnitude. That accepts any correctly-rounded result and rejects everything
  else, and it means you never write rounding logic at all.

- The reason this matters more than it looks: rounding binary64 back down to
  binary32 is where hand-written reference models actually break. Two attempts
  at it during this rule's own investigation were both wrong in the subnormal
  path — the first silently dropped subnormal results (1 miss in 406 random
  pairs), the second was wrong on 406 of 406 on a subnormal-heavy set. Writing
  the round-back is re-implementing the hardest part of the DUT, which the
  oracle-independence rule above already tells you not to do.

- Verilator implements `real` ARITHMETIC but NOT the IEEE-754 CLASSIFICATION
  predicates, and not `$ldexp`. Measured on Verilator 5.051:

      SUPPORTED      $pow $exp $ln $sqrt $floor $ceil $rtoi $itor
                     $bitstoreal $realtobits $clog2 $hypot $atan2
      NOT SUPPORTED  $ldexp $isnan $isinf $isfinite $isnormal $signbit $fmod
                     ("Unsupported or unknown PLI call")

- `$ldexp` is the one you reach for when assembling a float from an exponent and
  a mantissa. Use `$pow(2.0, e)`, or build the bit pattern and `$bitstoreal` it.

- For the predicates, DO NOT look for a `real` function — test the BIT PATTERN,
  which you already have because the DUT's port is bits. For binary32 with
  `{sign, exp[7:0], mant[22:0]}`:

      is NaN       exp == 8'hFF && mant != 0
      is Inf       exp == 8'hFF && mant == 0
      is zero      exp == 0     && mant == 0
      is subnormal exp == 0     && mant != 0
      sign bit     x[31]

  This is better than a predicate on the `real` value anyway: it is exactly what
  the design must produce, it distinguishes quiet from signalling NaN and +0 from
  -0, and it needs no conversion that could round.

- If the contract declares a `rnd_mode` port, note that `+` on `real` implements
  round-to-nearest-even only. Check the other modes through the tolerance
  relation (which result is representable and adjacent to the exact sum) rather
  than by writing a rounding unit per mode.

Verilator STRING rule (this compiles the SV and then fails the C++ build):
- Do NOT compare or wait on `string` variables. `wait (name == "foo")`,
  `if (scenario == "bar")` and similar lower to C++ that does not compile:
      error: unable to find string literal operator 'operator""foo'
      make: *** [Vtb___024root__1.o] Error 1
  Verilator elaborates the SystemVerilog happily, so this surfaces only as a
  make failure with no line of yours named.
- Use an enum or an integer code for scenario/state identity, and keep strings
  for `$display` text only:
      WRONG:  string scenario; ... wait (scenario == "randomized");
      RIGHT:  typedef enum {S_RESET, S_BASIC, S_RANDOMIZED} scen_e;
              scen_e scenario; ... wait (scenario == S_RANDOMIZED);
- Give that enum NO base type, exactly as shown above. It then defaults to
  `int`, which is always wide enough. Writing one narrows it to a fixed size
  and Verilator rejects the enum as soon as you have more scenarios than it
  holds:
      WRONG:  typedef enum logic [3:0] { ... 19 scenario names ... } scen_e;
      %Error: Enum value illegally wrapped around (IEEE 1800-2023 6.19)
      %Error: Overlapping enumeration value: 'SC_ZERO_RESULT'
  (Measured: 19 enumerators in a 4-bit type; values 16-18 wrapped to 0-2 and
  collided with the first three.)
- If you do hit that error, WIDEN the type or drop it — never delete scenarios
  to make them fit. That silently removes test coverage and still lints clean.
- Only COMPARISON breaks the build. `string` variables are fine when they are
  assigned and printed, and a label array is worth keeping:
      FINE:   string output_names [0:8];
              output_names[0] = "special_valid"; ...
              $display("%s: %0d mismatches", output_names[i], counts[i]);
      FINE:   string current_scenario; current_scenario = name;   // assignment
      BREAKS: wait (current_scenario == "randomized");            // comparison
  Naming each output in the mismatch report is exactly what makes a failure
  diagnosable, so do not drop it to avoid strings.

RESERVED KEYWORD rule (one collision produces ~40 errors, none of them the cause):
- Never use a SystemVerilog KEYWORD as an identifier — not as a variable, port,
  task/function argument, or module name. The parser fails at the declaration
  and then reports a cascade of unrelated-looking errors after it.
- Measured: a testbench declared `input string context` (a scenario label).
  `context` is reserved — it appears in `import "DPI-C" context function`. That
  one word produced:
      tb.sv:108:24: syntax error, unexpected context, expecting IDENTIFIER
      tb.sv:112:14: syntax error, unexpected '=', expecting '('
      ... ~40 more, none of which is the real defect
  Renaming it to `ctx` and changing nothing else made the file lint clean.
- Words that look like ordinary names and are NOT: `context`, `type`, `time`,
  `event`, `table`, `cell`, `config`, `disable`, `edge`, `expect`, `final`,
  `force`, `join`, `matches`, `null`, `program`, `property`, `randomize`,
  `ref`, `return`, `sequence`, `signed`, `small`, `space`, `strong`, `tagged`,
  `this`, `throughout`, `unique`, `wait`, `weak`, `wildcard`, `within`.
- If you want a label, prefer an unambiguous name: `ctx`, `scenario_name`,
  `test_label`, `phase_name`.

SystemVerilog declaration PLACEMENT rule (this fails to compile at all):
- Every declaration in a `begin ... end` must come BEFORE the first statement of
  that block. A declaration after a statement is a SYNTAX ERROR, not a style
  issue, and Verilator reports it far from the real cause as
  `syntax error, unexpected IDENTIFIER, expecting "'{"`.
- WRONG:   begin  int a; a = 1;  int b;  b = 2;  end
- RIGHT:   begin  int a, b;  a = 1;  b = 2;  end
- RIGHT:   begin  int a; a = 1;  begin int b; b = 2; end  end
           (a nested block starts a new declaration region)
- If you realise mid-block that you need another temporary, hoist it to the top
  of the block or open a nested `begin ... end` — never declare it in place.

Child assumes mode (hierarchical decomposition):
- If the contract JSON contains a `child_assumes` field (a dict keyed by child module name),
  this node is a COMPOSITION NODE with child-facing ports.
- The child-facing ports are ALREADY on the DUT's port list (prefixed with the child
  module name, e.g. for a child `foo` with port `ready`, the DUT port is `foo_ready`).

REAL child instantiation (only for entries with `"rtl_available": true`):
- These children are ALREADY implemented and verified — their real RTL will be
  compiled alongside this testbench (you do not write or see their source).
- For these children ONLY: declare an instance of the module (module name =
  the child's key in `child_assumes` — use THAT name, not an example name),
  and connect each
  of its OWN ports (named in that child's `interface` list, UNPREFIXED — e.g.
  a child port `x`) to the corresponding PREFIXED DUT port (prefix = child
  name + `_`, so child `foo`'s port `x` connects to DUT port `foo_x`).
- Do NOT write an inline behavioral stand-in for these children — no always
  blocks/tasks driving their prefixed ports. The real instance drives/reads
  them directly. `io_behavior`/`properties` for these entries are supporting
  context only (what the real RTL already guarantees), not something to model.
- Everything else in this section (black-box inline modeling, gap-focused
  testing) still applies to any child WITHOUT `"rtl_available": true`.

For children WITHOUT `"rtl_available": true`:
- DO NOT create stub modules for children. DO NOT instantiate any child modules.
- Instead, treat child-facing ports as REGULAR DUT PORTS that you drive/read directly
  in the testbench, just like clk/rst/start/A/B.
- Each child entry has `io_behavior` (a BLACK-BOX description of observable
  input->output behavior — what stimulus produces what result, after how many
  cycles), `timing` (latency per output), and `properties` (formal SVA).
- `io_behavior` is the PRIMARY source — model the child's ports to reproduce
  exactly that observable behavior, nothing more. `properties` pins down exact
  edge-case values precisely.
- DO NOT attempt to mimic any internal architecture (registers, FSM states,
  accumulators, recoding logic, etc.) even if such terms appear elsewhere in
  the contract (e.g. in the child's own `functional_summary`, which describes
  THAT child's internal RTL implementation, not its black-box behavior — do
  not use `functional_summary` to model child behavior in this testbench).
  Write a black-box model INLINE (always blocks or tasks) that drives the
  child-output ports to match `io_behavior` + `properties` only.
- For child-input ports (ports the DUT drives TO the child): just declare wires
  and connect them to the DUT. You can monitor them for debug.
- Test the DUT's own contract_sva properties assuming the children behave as specified.
- GAP-focused testing: `functional_summary` states the ORIGINAL (pre-decomposition)
  requirement alongside what each child guarantees. The DUT is not pure wiring —
  it is responsible for whatever the original requirement needs that no child
  guarantee covers (sequencing/launch order, arbitrating between children,
  combining two children's outputs, holding/latching state across cycles,
  format translation). Write scenarios that specifically stress THAT residual
  behavior, not just pass-through/wiring correctness — e.g. cases where a
  naive port-forwarding implementation would satisfy each child's own contract
  in isolation but still fail the parent's own contract_sva.
"""

PARSE_REPAIR_PROMPT = r"""
Your previous response could not be parsed by the program.

Parser error:
{parse_error}

Previous response (truncated):
<bad_output>
{bad_output}
</bad_output>

Please output again, strictly following the required tags in <output_format>, and output NOTHING else.
Do NOT output JSON. Do NOT wrap code in Markdown code fences (```).

The <bad_output> above is shown ONLY so you can see what failed to parse. It is
not a draft to tidy up. If it describes a different module than the contract
above -- different module name, different ports -- discard it completely and
write the contract's module from scratch. Re-read the contract and confirm the
module name and every port name match it before you answer.
"""

TB_LINT_FAILED_PROMPT = r"""
The previously generated testbench failed Verilator linting.

Verilator lint output:
<verilator_lint_log>
{lint_log}
</verilator_lint_log>

Previous testbench (with line numbers):
<previous_tb_with_lineno>
{previous_tb_with_lineno}
</previous_tb_with_lineno>

Regenerate the <interface> and <testbench> to fix ONLY the lint/syntax/unsupported-feature issues while preserving the contract behavior.
Output must still follow <output_format> exactly.
"""

NON_GOLDEN_TB_PROMPT = r"""
You are given:
1) A JSON contract written by the Architect agent (SOURCE OF TRUTH);
2) An optional input spec (non-authoritative background).

Task:
1) Write the DUT IO interface (module header only; no implementation) exactly as specified by the contract;
2) Write a testbench to verify the DUT strictly against the contract.

Hard rules:
- Follow the contract. Do NOT invent behavior/timing not stated in the contract.
- The module interface MUST match the contract/spec exactly (module name, port names, widths).
- Name the DUT instance `dut` (non-golden mode).
- Emit EXACTLY ONE top-level testbench module (plus the DUT interface header).
  Verilator elaborates every module nothing instantiates as a top and runs them
  all in ONE simulation, and `$finish` is global -- so a second top-level module
  that calls `$finish` ends the run for the real testbench too. Measured: a
  helper `..._test_runner` module emitted beside a correct testbench ended five
  consecutive simulations at time 0, before a single output had been checked.
  Never emit a module whose body only $displays that some test "would run in
  separate compilation".
- WIDTHS: test at the contract's DEFAULT parameter values. One width is
  sufficient and is what is expected — do NOT contort the testbench to sweep
  several widths. A correct single-width testbench is worth far more than a
  broken sweep. Declare the contract's parameters on the testbench module
  header and use them directly:
      RIGHT:  module fp_align_add_tb #(parameter int EXP_WIDTH  = 8,
                                       parameter int MANT_WIDTH = 23);
                logic [EXP_WIDTH-1:0] exp_a;
  A packed dimension must be elaboration-time constant, so a width may only
  come from a `parameter` or `localparam`. NEVER pass a width in as a function
  or task argument and then size a declaration with it — an argument is a
  VARIABLE:
      WRONG:  function automatic void ref_model(
                input logic [EXP_WIDTH-1:0] exp_a,    // uses it...
                input int                   EXP_WIDTH // ...and declares it
              );
      %Error: Expecting expression to be constant, but variable isn't const: 'EXP_WIDTH'
      %Error: left side of bit range isn't a two-state constant
  Measured: 26 errors in one generated oracle from exactly this. A function
  declared inside the module already SEES the module parameters — just use them.
- Do not use the SystemVerilog `continue` keyword.
- Verilator target: keep the TB compatible (avoid `sequence ... endsequence` and SVA `[*]` repetition; prefer simple assertions).

<contract_json>
{contract_json}
</contract_json>

<input_spec>
{input_spec}
</input_spec>

Testbench requirements:
1) Instantiate the DUT according to the interface (instance name `dut`).
2) Drive stimuli and compute expected outputs consistent with the contract (including any stated latency).
   - HANDSHAKE-QUALIFIED OUTPUTS (STRONGLY PREFERRED when applicable): if an output's validity is
     gated by a ready/valid/done/complete signal (i.e. the contract says the output is valid "when
     ready" / "when valid_out" / after a `done` pulse), check it READY-QUALIFIED and LATENCY-AGNOSTIC:
     assert the output equals its plain declarative value (e.g. `product == $signed(A0)*$signed(B0)`,
     using the operands A0/B0 you latched at the start of THIS operation) on EVERY cycle the
     qualifier is asserted, and do NOT constrain it (nor the exact cycle it becomes valid) otherwise.
     Do NOT model a fixed `latency_cycles` countdown for such an output. Rationale: the exact
     end-to-end latency of a composition is easy to reason off-by-one (N+1 vs N+2), and a
     fixed-latency oracle then fails a CORRECT design (or passes a wrongly-timed one); a
     ready-qualified check is immune to that — it only asserts "whenever you say you're ready, the
     answer is right," which is the true contract. This is the correct oracle for a composition/glue
     node whose external output is ready-qualified (i.e. a result port that is only meaningful on
     the cycle its companion `ready`/`valid` is asserted). Reserve the fixed-latency countdown model below ONLY for outputs that have NO such
     handshake qualifier.
   - LATENT / REGISTERED OUTPUTS WITHOUT A HANDSHAKE (any output whose contract timing has
     latency_cycles > 0 and which is NOT ready/valid-qualified per the bullet above,
     and/or whose notes say it "holds" its value): the expected value you compare against
     the DUT EVERY cycle MUST match what the DUT actually holds THAT cycle. Do NOT assign the
     expected output its final/next-result value in the same cycle you apply the stimulus that
     produces it. Instead: when you launch an operation, record the pending result and start a
     per-output countdown of `latency_cycles`; hold the expected output at its PREVIOUS value
     during the countdown, and reveal the new expected value only on the cycle the output
     actually becomes valid (countdown reaches 0). Then keep it at that value per the
     contract's hold semantics (e.g. "holds while ready asserted") until the next update event.
     A COMMON, FATAL BUG that fails correct RTL is: computing `expected = f(inputs)` in the
     same cycle the stimulus is applied while comparing every cycle — this mismatches on every
     cycle of the entire latency window even though the DUT is correct. The expected model must
     track the DUT's real cycle-by-cycle timing, not jump to the answer early.
   - `f(inputs)` itself must be the contract's plain declarative relationship (see "Oracle
     independence" above) — e.g. `A * B` for a multiplier — never a re-implementation of the
     DUT's internal algorithm. Getting the TIMING of the reveal right (previous bullet) and
     getting the VALUE right (this one) are both required and are independent failure modes.
3) Count mismatches between DUT outputs and expected outputs. This is the ONLY mismatch
   counter — if you write any additional ground-truth comparison anywhere in the testbench,
   route its result into this same counter; do not print it as a side note that leaves the
   pass/fail verdict unaffected.
4) Logging (keep logs small):
   - Do NOT print on every match.
   - On EVERY mismatch — not just the first — the display line MUST carry the DUT's
     actual output value AND the expected value, for the signal that mismatched:

         MISMATCH <sig> at time <t>: <inputs> | got=<actual> exp=<expected>

     Inputs alone are NOT enough and a bare count is worthless. The debugger cannot
     diagnose a value it was never shown, and every timing/aliasing check downstream
     works by comparing the ORDERED SEQUENCE of (actual, expected) pairs — one pair
     is not a sequence. A run that prints 210 mismatch lines carrying only inputs
     supplies exactly as much value evidence as a run that prints none, while
     looking like it supplies 210 times as much. (Measured: an fp_adder leaf did
     precisely this — 210 mismatch lines, 2 recorded values.)
     If you must cap the volume, cap it at no fewer than 30 fully-recorded
     mismatches per scenario and say how many were suppressed; never degrade the
     line to inputs-only.
   - For the first mismatch only, ADDITIONALLY print extra debug context per the display
     prompt below (moment or queue window). This is a one-time detail dump for context —
     it does NOT stop the run; continue executing all remaining checks and scenarios.
     This context block is IN ADDITION TO the per-mismatch lines above, never a
     substitute for them.
5) Generate a VCD named `wave.vcd`:
   initial begin
     $dumpfile("wave.vcd");
     $dumpvars(0, dut);
   end
6) End-of-sim summary (these exact markers are parsed by the harness):
   - If no mismatch: print exactly `SIMULATION PASSED`
   - Else: print exactly `SIMULATION FAILED - x MISMATCHES DETECTED, FIRST AT TIME y`
7) Trace-friendly summary lines (ALWAYS print these near end-of-sim, even if x=0):
   - Print exactly: `Mismatches: x in y samples`
   - For each DUT output port named `sig`, print exactly:
       `Hint: Output 'sig' has n mismatches. First mismatch occurred at time t.`
     where:
       - n = number of samples where this output mismatched (use 0 if never mismatched)
       - t = the earliest time (as integer) where this output mismatched (use 0 if never mismatched)
8) Sampling:
   - For posedge-sequential designs, compute/update expectations on posedge and check on negedge to avoid races.
   - For pure combinational designs (no clock), check at the moment inputs change (after a tiny delay if needed).
9) Structured scenarios (per-primitive reporting WITH timing pointers — enables
   granular, waveform-correlated debugging):
   - Group stimulus into NAMED, INDEPENDENT test scenarios, one per functional case
     (e.g. zero, overflow, carry_in, max, random_k). Reset/re-initialize between
     scenarios where the design is stateful.
   - BOUNDARIES ARE MANDATORY, not one scenario among many. Typical values do not
     distinguish a correct design from an off-by-one, and an oracle that only
     exercises typical values passes a design that is wrong at exactly one point.
     For EVERY numeric input and EVERY internal count or index the spec implies,
     drive at least:
       * the minimum, and one below it where the type allows (0, and wraparound);
       * the maximum, and one above it (overflow / saturation / wraparound);
       * for anything ITERATED or COUNTED N times: the LAST iteration (N-1), the
         boundary itself (N), and one past it (N+1). A loop that runs N-1 times
         instead of N produces correct-looking output on every earlier cycle.
       * for every COMPARISON the spec states (`<`, `<=`, `>=`, threshold,
         "when counter reaches K"): the value just below the threshold, the
         threshold EXACTLY, and just above. `<` and `<=` differ only at that one
         value, so a testbench that never drives it cannot tell them apart.
     This is not a style preference. Measured over 24 certified modules, five of
     the six faults their own testbenches FAILED to catch were exactly these two
     shapes — a `<` silently widened to `<=`, and a `+ 1` silently become `+ 2`.
   - Run ALL scenarios to completion — do NOT `$finish` on the first mismatch.
   - Record, per scenario: its start time, its end time, the count of mismatches, and
     the simulation time (`$time`) of the FIRST mismatch within that scenario.
   - At the START of each scenario print: `[TEST <scenario_name>] START at time %0t`
   - After each scenario print exactly one result line WITH timing, so a reviewer can
     locate the failure in `wave.vcd`:
       `[TEST <scenario_name>] PASS (window <t_start>..<t_end>)`
     or, on any mismatch in that scenario:
       `[TEST <scenario_name>] FAIL (<n> mismatches, first at time <t_first>, window <t_start>..<t_end>)`
     where `<t_first>` is `$time` of the first mismatch in the scenario and
     `<t_start>..<t_end>` bracket when the scenario ran. Print times as integers (`%0t`).
   - The end-of-sim markers in (6)/(7) are still required and printed once after all
     scenarios (they aggregate across scenarios, so the harness parsing is unchanged).

In `reasoning`, write a short, practical summary (no step-by-step chain-of-thought).

{examples_prompt}

Please also follow the display prompt below:
{display_prompt}
"""

GOLDEN_TB_PROMPT = r"""
You are given:
1) An input spec describing a DUT to implement;
2) A JSON contract written by the Architect agent;
3) A golden testbench that MUST be treated as ground truth for interface and timing.

Task:
1) Write the DUT IO interface (module header only; no implementation);
2) Improve the golden testbench by adding more helpful displays, while preserving its functionality.

Hard rules:
- The golden testbench is the source of truth when it contradicts the spec/contract.
- Maintain the exact original behavior, interface, module instantiation, and error counting.
- Do not remove existing `$dumpfile`/`$dumpvars`. If missing, add `$dumpfile("wave.vcd")` and `$dumpvars(...)`.
- If the contract disagrees with the golden TB, prefer the golden TB and do NOT "fix" the TB to match the contract.
- Verilator target: do not introduce unsupported SV/SVA features; if adding assertions, keep them non-intrusive and do not change timing/behavior.

<contract_json>
{contract_json}
</contract_json>

<input_spec>
{input_spec}
</input_spec>

Below is the golden testbench code for the module generated with the given natural language specification.
<golden_testbench>
{golden_testbench}
</golden_testbench>

Additions required:
1) Add richer displays on every check (inputs, outputs, expected) without changing timing or behavior.
2) Print the required end-of-sim summary:
   - If no mismatch: print exactly `SIMULATION PASSED`
   - Else: print exactly `SIMULATION FAILED - x MISMATCHES DETECTED, FIRST AT TIME y`

In `reasoning`, write a short, practical summary (no step-by-step chain-of-thought).

Please also follow the display prompt below:
{display_prompt}
"""

DISPLAY_MOMENT_PROMPT = r"""
1. When the first mismatch occurs, display the input signals, output signals and expected output signals at that time.
2. For multiple-bit signals displayed in HEX format, also display the BINARY format if its width <= 64.
"""

DISPLAY_QUEUE_PROMPT = r"""
Verilator compatibility (important):
- Avoid `sequence ... endsequence` declarations (unsupported by Verilator).
- Avoid SVA repetition/abbrev operators like `[*]` (unsupported by Verilator).
- If you need multi-signal history, use multiple queues (one per signal) of simple types (`logic`, `logic [N:0]`, `time`, `int`) as shown in the example below. Avoid queues of structs/packed structs.
- If you use assertions, prefer immediate assertions or simple `assert/assume/cover property` forms that Verilator supports (no advanced SVA features).

1. If module to test is sequential logic (like including an FSM):
    1.1. Store input signals, output signals, expected output signals and reset signals in queues with MAX_QUEUE_SIZE (one queue per signal; do not bundle into a struct);
        When the first mismatch occurs, display the queue contents after storing them. Make sure the mismatched signal can be displayed.
    1.2. MAX_QUEUE_SIZE should be set according to the requirement of the module.
        For example, if the module has a 3-bit state, MAX_QUEUE_SIZE should be at least 2 ** 3 = 8.
        And if the module was to detect a pattern of 8 bits, MAX_QUEUE_SIZE should be at least (8 + 1) = 9.
        However, to control log size, NEVER set MAX_QUEUE_SIZE > 10.
    1.3. The clocking of queue and display should be same with the clocking of tb_match detection.
        For example, if 'always @(posedge clk or negedge clk)' is used to detect mismatch,
        It should also be used to push queue and display first error.
2. If module to test is combinational logic:
    When the first mismatch occurs, display the input signals, output signals and expected output signals at that time.
3. For multiple-bit signals displayed in HEX format, also display the BINARY format if its width <= 64.

<display_queue_example>
// Queue-based simulation mismatch display

reg [INPUT_WIDTH-1:0] input_queue [$];
reg [OUTPUT_WIDTH-1:0] got_output_queue [$];
reg [OUTPUT_WIDTH-1:0] golden_queue [$];
reg reset_queue [$];

localparam MAX_QUEUE_SIZE = 5;

always @(posedge clk or negedge clk) begin
    if (input_queue.size() >= MAX_QUEUE_SIZE - 1) begin
        input_queue.delete(0);
        got_output_queue.delete(0);
        golden_queue.delete(0);
        reset_queue.delete(0);
    end

    input_queue.push_back(input_data);
    got_output_queue.push_back(got_output);
    golden_queue.push_back(golden_output);
    reset_queue.push_back(rst);

    // Check for first mismatch
    if (got_output !== golden_output) begin
        $display("Mismatch detected at time %t", $time);
        $display("\nLast %d cycles of simulation:", input_queue.size());


        for (int i = 0; i < input_queue.size(); i++) begin
            if (got_output_queue[i] === golden_queue[i]) begin
                $display("Got Match at");
            end else begin
                $display("Got Mismatch at");
            end
            $display("Cycle %d, reset %b, input %h, got output %h, exp output %h",
                i,
                reset_queue[i],
                input_queue[i],
                got_output_queue[i],
                golden_queue[i]
            );
        end
    end

end
</display_queue_example>
"""


EXAMPLE_OUTPUT_FORMAT = """<reasoning>
Concise rationale + key assumptions (no step-by-step chain-of-thought)
</reasoning>
<interface>
SystemVerilog module header only (no implementation)
</interface>
<testbench>
Complete SystemVerilog testbench module
</testbench>
"""


class TBOutputFormat(BaseModel):
    reasoning: str
    interface: str
    testbench: str


EXTRA_ORDER_GOLDEN_TB_PROMPT = r"""
Golden TB mode reminders:
- If golden TB contradicts the spec/contract, follow the golden TB.
- Preserve the original behavior, instantiation, and mismatch counting.
- Always print the required end-of-sim summary lines.
- Always generate the complete testbench, even if long.
- Generate the interface according to the golden TB. Declare all ports as `logic`.
"""

EXTRA_ORDER_NON_GOLDEN_TB_PROMPT = r"""
Non-golden mode reminders:
- If the spec is ambiguous about output latency, follow the contract's `timing` section.
- For pattern detectors (if relevant), the common convention is to assert `detected` on the cycle AFTER the pattern completes, unless specified otherwise in the contract/spec.
"""

COVERAGE_PROMPT = r""" Your task involves a Verilog Design Under Test (DUT) that is currently in its initial phase of testing.
            The assignment requires you to generate a binary input sequence to maximize code coverage.
            To achieve this, you need to analyze the DUT, considering the logic operations and transitions within the circuit.
            This careful analysis will allow you to discern the relationship between the input sequence and the uncovered lines, and thus generate an effective input sequence.)";
        // task_prompt += input_signal_prompt_;"""


class TBGenerator:
    def __init__(
        self,
        cfg: OpenAIConfig,
    ):
        self._cfg = cfg
        self._agent = SafeReActAgent(
            name="Verifier",
            sys_prompt=SYSTEM_PROMPT,
            model=make_openai_model(cfg),
            formatter=make_formatter(cfg.model),
            memory=InMemoryMemory(),
            max_iters=10,
        )
        self.failed_trial: List[str] = []
        self.golden_tb_path: str | None = None
        self.parse_max_trial = 5
        self.gen_display_queue = True
        self.last_prompt: str = ""
        self.last_raw_output: str = ""

    def reset(self):
        clear_memory_safely(self._agent)

    def set_golden_tb_path(self, golden_tb_path: str | None) -> None:
        self.golden_tb_path = golden_tb_path

    def set_failed_trial(
        self, failed_sim_log: str, previous_code: str, previous_tb: str
    ) -> None:
        cur_failed_trial = FAILED_TRIAL_PROMPT.format(
            failed_sim_log=failed_sim_log,
            previous_code=add_lineno(previous_code),
            previous_tb=add_lineno(previous_tb),
        )
        self.failed_trial.append(cur_failed_trial)

    def set_tb_lint_error(self, *, lint_log: str, previous_tb: str) -> None:
        cur = TB_LINT_FAILED_PROMPT.format(
            lint_log=lint_log.strip(),
            previous_tb_with_lineno=add_lineno(previous_tb),
        )
        self.failed_trial.append(cur)

    def get_init_prompt_messages(self, input_spec: str, *, contract_json: str) -> List[Msg]:
        display_prompt = (
            DISPLAY_QUEUE_PROMPT if self.gen_display_queue else DISPLAY_MOMENT_PROMPT
        )
        if self.golden_tb_path:
            with open(self.golden_tb_path, "r") as f:
                golden_testbench = f.read()
            generation_content = GOLDEN_TB_PROMPT.format(
                input_spec=input_spec,
                golden_testbench=golden_testbench,
                display_prompt=display_prompt,
                contract_json=contract_json,
            )
        else:
            # A composition TB must instantiate the REAL children and bridge
            # their UNPREFIXED ports to the DUT's PREFIXED child-facing ports.
            # TB_4_SHOT_EXAMPLES is 16,280 chars of LEAF testbenches with zero
            # coverage of that pattern, so the hardest part of the task had no
            # worked example at all. Live consequence: a generated self-TB
            # instantiated a helper module that does not exist and the oracle
            # could not elaborate (%Error-MODMISSING), making the composition
            # gate unpassable regardless of the glue.
            _is_composition = False
            if contract_json:
                try:
                    _is_composition = bool(json.loads(contract_json).get("child_assumes"))
                except (ValueError, TypeError, AttributeError):
                    _is_composition = "child_assumes" in contract_json
            generation_content = NON_GOLDEN_TB_PROMPT.format(
                input_spec=input_spec,
                examples_prompt=(
                    TB_4_SHOT_EXAMPLES + "\n\n" + GLUE_TB_EXAMPLE
                    if _is_composition else TB_4_SHOT_EXAMPLES
                ),
                display_prompt=display_prompt,
                contract_json=contract_json,
            )
        parts: list[str] = [generation_content]
        parts.extend(self.failed_trial)
        return [Msg("user", "\n\n".join(parts), role="user")]

    def get_order_prompt_messages(self) -> List[Msg]:
        if self.golden_tb_path:
            order_prompt_message = Msg(
                "user",
                TAG_ORDER_PROMPT.format(output_format=EXAMPLE_OUTPUT_FORMAT)
                + EXTRA_ORDER_GOLDEN_TB_PROMPT,
                "user",
            )
        else:
            order_prompt_message = Msg(
                "user",
                TAG_ORDER_PROMPT.format(output_format=EXAMPLE_OUTPUT_FORMAT)
                + EXTRA_ORDER_NON_GOLDEN_TB_PROMPT,
                "user",
            )

        return [order_prompt_message]

    def parse_output(self, response_text: str) -> TBOutputFormat:
        try:
            interface = strip_markdown_code_fences(extract_xml_tag(response_text, "interface")).strip()
            testbench = strip_markdown_code_fences(extract_xml_tag(response_text, "testbench")).strip()
            reasoning = extract_xml_tag(response_text, "reasoning", required=False).strip()
            if not interface or not testbench:
                raise ValueError("Empty <interface> or <testbench> block")
            ret = TBOutputFormat(reasoning=reasoning, interface=interface, testbench=testbench)
        except Exception as e:  # noqa: BLE001
            ret = TBOutputFormat(
                reasoning=f"Parse Error: {type(e).__name__}: {e}",
                interface="",
                testbench="",
            )
        return ret

    async def chat(self, input_spec: str, *, contract_json: str) -> Tuple[str, str]:
        self.reset()
        init = self.get_init_prompt_messages(input_spec, contract_json=contract_json)[0].content
        order = self.get_order_prompt_messages()[0].content
        prompt = f"{init}\n\n{order}"

        response_text = ""
        resp_obj = TBOutputFormat(reasoning="", interface="", testbench="")
        for _ in range(self.parse_max_trial):
            self.last_prompt = prompt
            msg = await self._agent(Msg("user", prompt, role="user"))
            response_text = msg.get_text_content() or ""
            self.last_raw_output = response_text
            resp_obj = self.parse_output(response_text)
            if not resp_obj.reasoning.startswith("Parse Error"):
                break
            repair = PARSE_REPAIR_PROMPT.format(
                parse_error=resp_obj.reasoning,
                bad_output=clip_text(response_text, max_chars=6000),
            )
            prompt = f"{init}\n\n{repair}\n\n{order}"
        if resp_obj.reasoning.startswith("Parse Error"):
            raise ValueError(
                f"Parse error when decoding model output: {response_text}"
            )
        return (resp_obj.testbench, resp_obj.interface)
