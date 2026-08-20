# specflow: status and migration

`specflow/` implements the spec-grounded verification pipeline described in
`docs/spec-testplan-coverage-chain.md` and motivated by
`docs/tb-hardening-research.md`.

## What it replaces, and why

The existing path generates one monolithic `tb.sv` that is simultaneously the
correctness oracle and the only channel describing failures to the repair agent.
Three structural problems follow, all verified in the code rather than inferred:

1. **The spec never reaches the verification side.** `TopAgentConfig.contract_only`
   is `True` and `_contract_only_context` (`top_agent.py:460-474`) truncates the
   contract to at most six `functional_summary` bullets. That string, not the
   spec, is what the Verifier, Coder and Debugger see.
2. **There is no post-simulation testbench feedback.**
   `TBGenerator.set_failed_trial` (`tb_generator.py:587-595`) has no callers.
   Once the testbench lints clean it is frozen; only RTL is ever repaired.
3. **The verdict is two-valued and parsed from prose.** `sim_review` returns a
   bool plus a mismatch count, so `is_pass=True, mismatch_cnt=0` means both
   "everything was checked and passed" and "nothing ran".

## Pipeline

```
prompt.txt ──S1──▶ requirements ──S2──▶ testplan ──S3──▶ bins + checks
                        │                                      │
                        └────────── reference model ───────────┤
                                          │                    │
                                          └──── cocotb suite ──┴──▶ verdict
```

Five agent calls; every gate is pure code. Gates: **G1** spec attribution,
**G2** requirement→testplan, **G3** testplan→bin+check, **G4** reference model,
**G5** rendered suite, **G6** two-sided control, **G6b** record reconciliation,
**G7** accept decision, **G8** mutation qualification.

| Module | Role |
| --- | --- |
| `schema.py`, `ids.py` | artifact types; `UID@rev` references |
| `assure.py` | one traceability engine, four defect classes |
| `stage.py` | the bounded agent-plus-gate loop, implemented once |
| `model_io.py` | `FilePort` / `ReplayPort` / `ApiPort` |
| `s1_requirements.py`, `s2_testplan.py`, `s3_coverage.py` | the three stages |
| `refmodel/` | Python reference model, G4 |
| `tb/runtime.py` | hand-written, protected: clock, scoreboard, verdict record |
| `tb/render.py` | emits the cocotb suite; owns every check and bin call |
| `run.py`, `coverage.py`, `gate.py` | execute, join, decide |
| `unreach.py` | formal discharge of unreachable bins |
| `qualify.py` | mcy mutation gate |
| `loop.py`, `testcase_agent.py` | the hard-gated loop |
| `integration.py` | bridge to `eda_agent`'s node-level run |

## Status

Milestones M0–M9 are implemented and tested; 186 tests pass with no model in the
loop, because every stage replays a recorded fixture
(`tests/fixtures/specflow/hadd`, a real VerilogEval-v2-EXT problem).

Demonstrated on real tooling rather than asserted:

- the reference model agrees with `Prob024_hadd_ref.sv` exhaustively, and a
  seeded wrong model is detected;
- the suite passes golden RTL and fails a tied-off DUT (the two-sided G6 control);
- RTL with two independent bugs reports **both**, with per-mismatch values and
  stimulus, in one run;
- a bin on a tied-low output is proved unreachable by k-induction; a live one is
  not discharged;
- a rigged bug converges in one repair; a rigged stall terminates inside budget.

## Retirement of the SystemVerilog path

`tb_backend` now defaults to `"specflow"`. `TopAgent.run` dispatches to
`_run_instance_specflow`, which builds and certifies the oracle *before* any RTL
exists, then repairs against the three-valued verdict.

Retired:

- **`TB_4_SHOT_EXAMPLES` and `GLUE_TB_EXAMPLE` are deleted** from `prompts.py`
  (31.8KB → 13.3KB). They taught the defects the harness then compensated for:
  none of the four examples emitted the `[TEST …]` markers the prompt mandated,
  and all four latched a single global `first_mismatch_time`, which is precisely
  what `utils.py:49-83` exists to detect. `FAILED_TRIAL_PROMPT` stays — it is
  shared with `rtl_generator`.
- **`eda_agent/tb_generator.py` is deleted**, along with `_run_instance`, the
  475-line SystemVerilog node path it served. `top_agent.py` drops from 1165 to
  675 lines, and `TopAgent` now exposes only `_run_instance_specflow` and the
  ablation path. Removing it orphaned five imports (`asyncio`, `List`,
  `RTLEditor`, `SimReviewer`, `TBEditor`), which is a fair measure of how much of
  that module existed to serve the monolithic testbench. An unknown `tb_backend`
  raises rather than silently falling back, since there is nothing to fall back
  to. A test walks `top_agent`'s module-level imports so the dependency cannot
  return.

`RTLEditor` needed no changes: it is parameterised on a reviewer object, so
`SpecflowReviewer` — same `(is_pass, mismatch_cnt, sim_output)` shape as
`SimReviewer.review()` — is the seam that swaps the oracle underneath it.

### Live-model results

Both items that previously needed an API key are settled, and the first live run
found four defects that no amount of local testing had. Model: `gpt-5.6-luna`
(served `gpt-5.6-luna-2026-07-09`) at `reasoning_effort=xhigh`.

**One node end to end through `top_agent`, at xhigh on every call: ACCEPT.**
S1 1 round, S2 1 round, S3 2 rounds (3 issues repaired), reference model
1 round, RTL accepted on iteration 0; 10m34s wall clock for a half adder. The
suite was separately driven outside pytest against golden RTL (ACCEPT, 5/5) and
a tied-off DUT (REPAIR_RTL, 5/5 FAIL with per-mismatch values and stimulus),
which is G6's two-sided control on live-generated artifacts rather than
fixtures.

What the run exposed, in the order it surfaced:

1. **Reasoning effort was silently dropped.** `load_openai_config` resolved
   every field from the environment except `reasoning_effort`, so `ApiPort`
   always sent `None`.
2. **The reference model had no dispatch.** The prompt asked the agent to emit
   one while the response schema had nowhere to put it, so a model following
   the schema literally returned correct fragments and no `evaluate`. G4 caught
   it only dynamically and its issue text never named the defect, so four
   repair rounds could not converge. `compose.py` now synthesises the dispatch;
   the same stage went from 4 rounds and a hard failure to 1 round, with
   reasoning falling from 11,877 tokens to 465.
3. **The rendered suite could not import `specflow` outside pytest.** cocotb
   overwrites `PYTHONPATH` from the parent's `sys.path`, so `run.py`'s
   `extra_env` value was dead code, and a relative `''` entry means the
   repository in the parent but the test directory in the child. Every test
   passed while a production node would have failed on every node.
4. **`_run_instance_specflow` had never executed**, and crashed on its first
   real statement with a plain `TypeError`.

Each has a regression test, and (3) was confirmed to fail without its fix
rather than assumed to be covered.

### Reaching the model

Three settings are not optional on the SDC gateway, and each fails differently:

| | Value | Symptom if wrong |
| --- | --- | --- |
| model id | `gpt-5.6-luna`, no vendor prefix | `404 MODEL_NOT_FOUND` |
| base URL | must end in `/v1` | requests hit the wrong path |
| effort | flat `reasoning_effort` | `400 unknown_parameter` |

The nested `{"reasoning": {"effort": ...}}` form is the Responses API shape and
is rejected by chat-completions. Note also that `load_env_file` overrides only
the keys it names, so a conflicting `OPENAI_EXTRA_BODY` already in the
environment survives any file that omits it.

**Tools and reasoning effort cannot coexist on chat-completions here.** The
gateway directs callers to `/v1/responses`, and every `eda_agent` agent is
tool-using, so without that surface the RTL loop runs at the endpoint's default
effort while only specflow's five tool-free calls honour the configured one.
`eda_agent/responses_model.py` is the adapter; select it with
`OPENAI_API_FLAVOR=responses`. specflow's `ApiPort` stays on chat-completions
deliberately, since its calls carry no tools.

Reasoning models also reject an explicit `temperature`, which both entry points
sent by default. `--temperature` now defaults to unset.

### The ~300s request ceiling

The gateway cuts a single request at ~301s. This is not a client setting and
cannot be raised from inside the container: a 2400s client timeout dies at the
same 301s, and so does a streamed request, whose failure is the informative one
--

    STREAM FAILED after 301s (first chunk at None): APIConnectionError

no chunk ever arrived, because reasoning emits no content deltas. A streamed
reasoning request therefore looks exactly as idle as a non-streamed one, and
`stream=True` does not buy anything against this particular ceiling. (It is
supported anyway, off by default, since the same limit elsewhere may be
idle-based.)

Measured on the `or1200_ctrl` S1 prompt (37.9KB, from a 14.3KB spec):

| effort | max tokens | wall clock | |
| --- | --- | --- | --- |
| `medium` | 16000 | 57s | fits |
| `high` | 24000 | 220s | fits, ~80s margin |
| `xhigh` | 40000 | 301s | **cut** |

**No client-side bypass exists.** Three were tried:

| approach | result |
| --- | --- |
| client timeout raised to 2400s | cut at 301s |
| `stream=True` | cut at 301s, `first chunk at None` |
| `background=True` + poll | submission accepted, retrieval unroutable |

Background mode is the near miss and the one worth escalating. The submission
succeeds -- `status=queued` in 3.3s -- but every retrieval 404s with
`MODEL_NOT_FOUND: model ''`, on the bare path, with `?model=`, and with `x-model`
or `model` headers alike. The gateway routes by the model in the request *body*,
and a `GET` has none, so a queued response can be created and never fetched.
That is a gateway defect rather than a limit: background mode is precisely the
feature designed for generations that outlast a connection, and it is one
routing fix away from working. Raising the ~300s cap or fixing
`GET /v1/responses/{id}` would restore `xhigh` outright.

**Continuation does not work either, and the reason is specific.** The obvious
answer is to cap `max_output_tokens` below the ceiling and stitch segments
together, re-sending each length-terminated partial to be continued. Measured on
the same S1 prompt, it does not converge, because at `xhigh` a capped call
spends its *entire* cap on reasoning and returns no content at all:

| probe | cap | result |
| --- | --- | --- |
| single capped call | 6000 | 75s, `finish_reason=length`, 6000 reasoning tokens, **0 chars of content** |
| single capped call | 12000 | 145s, `finish_reason=length`, 12000 reasoning tokens, **0 chars of content** |
| 4-segment chain carrying the reasoning summary | 8000 | 4 x ~88s, 8000 reasoning tokens each, **0 chars each** |

`max_completion_tokens` caps reasoning and content *together*, so a cap set low
enough to fit the ceiling is a cap the model never finishes reasoning inside.
There is nothing to continue from -- the partial answer is empty.

Carrying the reasoning forward does not fix that. The Responses API returns a
summary even when content is empty, so each segment was re-sent the accumulated
summary (3816, then 1705, then 2407, then 1034 chars) and asked to finish. The
reasoning did not shorten: every segment spent its whole 8000-token cap
re-reasoning and emitted nothing. `previous_response_id` fares no better -- the
gateway accepts the parameter and drops the context. Four segments cost ~350s
and produced zero output, which is worse than the single 301s failure it was
meant to replace.

So the ceiling is not a budgeting problem to be worked around client-side; at
`xhigh` on this prompt the model needs more than 24,800 tokens of *uninterrupted*
reasoning, and the ~12.1ms-per-output-token generation rate makes that
structurally impossible inside 300s. `high` (220s, and it does produce content)
is the setting that works today.

Two consequences worth stating plainly.

**The failure is silent and expensive.** The OpenAI SDK retries connection
errors and logs those retries at DEBUG, so a call that structurally cannot fit
burns `max_retries` x ~300s writing nothing at all. Both ChipVerilog arms sat in
that loop for 47 minutes with an empty log and no error signature -- a watchdog
grepping for errors could not see it, because there were none. `ApiPort` now
translates the death into a message naming the ceiling, and
`OPENAI_MAX_RETRIES=2` keeps the failure cheap.

**S1 is the stage that will breach it first.** It must attribute verbatim spans
across the entire specification in one call, so its prompt and its output both
scale with spec size. 220s of a 300s ceiling on a 14.3KB spec leaves no room for
a larger one. Splitting S1 is the only option that preserves both high effort
and ChipVerilog-scale specs; that is now a measured constraint rather than a
design preference.

### Still open

- **No VerilogEval-v2-EXT baseline.** Not a missing key any more, a runtime
  one: S1 alone took 5m44s on a half adder at this effort, so 209 problems runs
  into days. It needs a lower effort or a much longer window.
- **No ChipVerilog baseline yet.** The first attempt at `or1200_ctrl` was lost
  to the request ceiling above; both arms now run at `high` rather than the
  `xhigh` originally asked for, which is a condition change the baseline records
  rather than hides.
- **ChipVerilog is the sharper target** and has its own runner
  (`benchmarks/run_chipverilog.py`). Note that specflow is scoped to leaf
  nodes, so the 16 hierarchical tasks of its 64 are out of scope by
  construction rather than by accident.

### How the node path is wired

`_run_instance_specflow` (in `top_agent.py`) builds the contract, merges any
orchestrator-supplied `contract_sva` / `child_assumes` / `child_rtl`, then calls
`specflow_node.run_specflow_node`, which:

1. calls `build_artifacts` — S1→S3, reference model, rendered suite, gate by
   gate, stopping at the first failure and naming the stage. **The oracle is
   certified before any RTL exists**, which is also what keeps the reference
   model independent: there is no `rtl.sv` to contaminate it.
2. generates RTL and syntax-checks it;
3. repairs against `SpecflowReviewer`, whose `review()` returns the three-valued
   verdict and a payload in which every mismatch names its check, both values and
   the stimulus that produced it.

`EXTEND_TB` and `STALLED` return without invoking repair: neither is an RTL
problem, and reporting them as one is what sends a repair agent after the wrong
artifact.

## Running a stage by hand

With no API key, each stage emits its prompt and stops:

```bash
python -m specflow.cli s1 --run-dir runs/<r> --model-port file   # writes the prompt, exits 3
# ...answer it at runs/<r>/agent_io/s1_r0_response.txt...
python -m specflow.cli s1 --run-dir runs/<r> --model-port file   # ingests, gates
```

Then `s2`, `s3`, `refmodel`. Once answered, `--model-port replay` reproduces the
whole chain deterministically and for free.

## S1 by division: measured

The generative S1 collapses to the same shape on every real spec — a handful of
token requirements plus one catch-all blanketing the whole document, which
satisfies the coverage gate on its own. Division replaces it: `divide.py` cuts
only where the specification's author cut (blank lines, list items, headings,
table rows) and a per-unit classifier does everything below that boundary,
emitting offsets rather than spec text.

**Why the divider stops at authorial boundaries.** Sentence-level splitting
reaches a similar granularity but severs meaning. Of the sentences that follow
another sentence inside one paragraph, 28% (`i2c_master_bit_ctrl`) and 15%
(`or1200_ctrl`) open with a back-reference — `it`, `also`, `otherwise`. Cutting
where the author cut cannot do that, and it is asserted over all 209 VerilogEval
prompts and all 64 ChipVerilog specs: **0 mid-sentence boundaries, 0 overlapping
units, 0 gaps carrying a word.**

**Live, on `i2c_master_bit_ctrl` with `gpt-5-mini` at `low` effort:**

| | generative | divided |
| --- | --- | --- |
| requirements | 24 | **69** |
| span p50 | 221 ch | 111 ch |
| **largest single requirement** | **15,713 ch — 100% of the spec** | **1,819 ch — 11.6%** |
| spec coverage | 100%, via the catch-all | 97.6%, honestly |
| restatements opening with a back-reference | — | **0 of 69** |
| units clean at G1' on the first pass | — | **65 of 65** |
| wall clock | 13–18 min | **1 min 54 s** |

The catch-all is gone: no requirement now claims more than 11.6% of the
specification, against a target of 10%, and the one that reaches 11.6% is a
single large authorial unit rather than an evasion. The residual 2.4% of
uncovered text is units the classifier marked non-behavioural — headings and
cross-references — which is the intended outcome, not a gap.

**Concurrency is a cost decision, not a speed one.** Parallel calls race the
prompt-cache write, so more workers buys wall clock and pays in tokens. 24 units
through the classifier:

| workers | warmup | wall | hit rate | billed input |
| --- | --- | --- | --- | --- |
| 8 | 2 | 72s | 88.6% | 13,592 |
| **4** | **2** | **76s** | **96.8%** | **3,864** |
| 4 | 6 | 67s | 93.1% | 8,216 |
| 2 | 2 | 85s | 92.9% | 8,472 |

8 workers costs 3.5x the input tokens for 5% less wall clock. The ordering among
the lower rows is within run-to-run noise — 2 workers is not better than 4 — but
8's token cost is well outside it. The default is 4.

**This also makes the ~300s ceiling irrelevant rather than worked around.** Every
call in the divided, fanned-out chain is a small one: 7–26s measured across
`gpt-5-nano`, `gpt-5-mini` and `gpt-5.6-luna`. Nothing comes within 30x of the
limit that killed the monolithic S1.

## The oracle, measured against golden RTL

The oracle had never been scored against RTL that is known to be correct. The
first time it was, the **golden `i2c_master_bit_ctrl` failed 120 of 168
testpoints** — worse than the LLM-written candidate it was supposed to judge. A
known-correct design scoring below a generated one means the oracle is the
broken part, and the repair loop had been deforming correct RTL to match it.

`benchmarks/golden_check.py` is the instrument. Debug only: it is never a gate,
and its cycle-exact verdict never reaches an agent.

### The testbench verifies content, not cycles

`contract.timing.cmd_ack.latency_cycles` came back **3** in one run of this
specification and **1** in the next. Golden takes **5** `clk_en` phases. The
specification cannot settle it — it describes START as three transitions, golden
implements five, and two of those five are invisible (`start_a`/`start_b` are
no-ops from reset and `start_d` is byte-identical to `start_c`, a pure hold).
The phase count appears nowhere in 15,715 characters, because it is an
arbitrary-but-fixed choice of that core.

So cycle-exactness was being enforced against a fiction: the full cost of
strictness — rejecting correct RTL, which was observed — and none of the
benefit, since it still did not match golden.

A check now compares the **ordered sequence of distinct output states** and
ignores how long each is held. A skipped state, a spurious state and a wrong
value all fail; only duration is ignored, and the durations are returned rather
than discarded so a requirement that states one can be checked on top.

Same oracle (a line-by-line transliteration of golden), same stimulus, two DUTs,
each vector held 60 edges so a command can actually complete:

| DUT | cycle-exact | transactional | cycle-exact, less `dout`-only | transactional, less `dout`-only |
| --- | --- | --- | --- | --- |
| golden (correct) | 36 / 168 | 69 / 168 | 89 / 168 | **129 / 168** |
| generated (wrong) | 20 / 168 | 28 / 168 | 56 / 168 | **31 / 168** |
| **separation** | **16** | **41** | **33** | **98** |

Ignoring durations discriminates ~2.6× better on every output and ~3× better
once the one known asymmetry is set aside, because phase noise from a guessed
latency was swamping the behavioural signal.

**Read both numbers, never one.** A criterion that passes everything scores well
on the pass rate and is worthless. The pass rate of a *correct* design says how
much of the harness is defect; the separation says whether the criterion
discriminates at all.

**The inversion is gone.** With `dout` included the harness used to rank the
wrong candidate above golden — golden's `dout` has no reset and samples the idle
bus, while the wrong RTL resets it to 0 exactly as the model does, and
`ports.inactive_value` was handing the model `scl_i=0, sda_i=0`: an open-drain
bus held *low*. Every input now has a declared `idle_value` and both sides start
there.

**Accepted cost, stated plainly.** A transactional testbench will accept RTL
that fails the benchmark's sequential-equivalence scoring — proven by
experiment, golden with one invisible hold phase removed is `function_fail`. It
will not lift the score by itself. It stops the oracle destroying correct RTL,
which is a precondition for anything else working.

### Duration obligations: measured, and not built

Where a requirement states a duration, that duration is worth checking — on the
recorded DUT trace directly, never through the reference model. So the question
is how many such requirements exist. `benchmarks/timing_obligations.py` answers
it across all 64 specifications:

| | |
| --- | --- |
| candidate sentences with a quantified cycle count | 36 |
| — naming no declared output port | 23 |
| — a port-glossary noun phrase, no assertion | 8 |
| — a *latency* claim ("one-cycle delayed"), not a width claim | 4 |
| — a clause that **denies** the duration | 1 |
| **real obligations** | **3, in 2 of 64 modules** |
| distinct claims among them | 1 (`cmd_ack` is one `clk` wide) |
| validated against golden | 3 hold, 0 golden-fails |

Both modules are in the i2c family. The word "exactly" occurs **once in the
entire corpus** — the canonical example is the strongest timing sentence in the
benchmark, not a representative one.

**So Phase 5 does not ship as a pipeline feature.** One sentence is not a
feature. The extractor stays as a measurement, and its own development produced
two live examples of the failure the measurement exists to prevent: it read
`or1200_except`'s "except_start is a combinational level signal, **not** a
one-cycle pulse" as an obligation and generated a check golden fails, and it
scanned the golden Verilog for `output` without stripping comments, matching the
word inside `// i2c clock line output enable (active low)` — so
`i2c_master_bit_ctrl` acquired ports named `enable`, `end` and `yet`, and "At the
**end** of a command sequence" became a claim about a port. Both are tests now.

### `latency_cycles` gates nothing

The field was load-bearing in three places at once — it gated a reference-model
check (G4e), set the testbench's stimulus hold length, and picked the reference
model's dispatch — and the architect had been told, in as many words, to
"choose 0 or 1" where the specification named no count. G4e is deleted, pacing
is severed (a stimulus step states its own `hold` or waits `until` a condition),
and the field is now optional with one definition quoted into every prompt that
mentions it: **edges of the declared clock**, not enable ticks. On a prescaled
design that distinction is the difference between 5 and 26.

### Breadth: does the harness discriminate on all 64 designs?

The measurements above are one design. `benchmarks/harness_discrimination.py`
asks the same question benchmark-wide and costs no model calls: build a real
specflow suite against each golden reference, hand it a reference model that is
**deliberately wrong** — every output zero, forever — and require the harness to
report FAIL. A design that passes an all-zeros oracle was not verified.

Unlike `harness_liveness.py`, this drives the real `Env`: declared idle values,
the reset sequence, the per-edge lockstep advance, the recorded trace and the
sequence comparison.

| | first sweep | after the fixes below |
| --- | --- | --- |
| rejected the null oracle | 29 | **45** |
| passed it | 2 | 1 |
| no record written | 7 | 0 |
| did not elaborate | 26 | 18 |

**Of the 46 designs that elaborate, 45 reject a null oracle.** The one that
passes (`instruction_mem`) has outputs that never move under the liveness probe
either, so its agreement is honest. **No design whose outputs move passes a null
oracle** — that is the discrimination claim, benchmark-wide.

The 18 that do not elaborate are the corpus, not the harness: 13 instantiate
vendor RAM macros (`rf_sub`, `dc_ram_sub`, `ic_tag_sub`, the TLB RAMs) that are
**defined nowhere in the ChipVerilog release**, and 5 `double_fpu` designs trip
Verilator on duplicate signal declarations.

Six defects the sweep found, all now fixed:

* **A crash was costing the evidence, not just the testpoint.** `drive()` raised
  on a port the DUT lacks and `sample()` raised on a missing output, so a
  candidate that omitted a declared port produced **no record at all** rather
  than a verdict naming the port — 7 designs. A port that cannot be found, a
  value the port cannot hold (2 on a 1-bit input) and a handle the simulator
  refuses to write are now all verdicts, and `reset()` is guarded too, since it
  drives every input to idle one step before the first vector.
* **A uniform random sweep never decodes a decoder.** `default_stimulus` drew
  32-bit inputs uniformly, so `or1200_cfgr` — which gates its whole decode on
  `~|spr_addr[31:4]` — sat at its reset value for the entire run and then
  *agreed* with the all-zeros model. Corner vectors come first now, including
  each input walked through small values while the rest sit at zero.
* **`--no-timing` and `-Wno-fatal`.** Every non-blocking assignment in the
  OpenCores i2c core is written `sda_oen <= #1 1'b1;`, and Verilator stopped
  with NEEDTIMINGOPT before a single check ran; the i2c core then stopped on a
  WIDTHTRUNC *warning*. Lint findings belong to the lint gate — which runs
  `-Wno-fatal` itself — so leaving them fatal here rejected a correct design at
  build time for a reason about the invocation.
* **Child modules were collected one level deep.** `i2c_master_top` instantiates
  `i2c_master_byte_ctrl`, which instantiates `i2c_master_bit_ctrl`, and the
  grandchild was never supplied. Collection is transitive now.
* **The contract recovered from RTL took the first module in the file**, not the
  one named after it — so on `cordic.v`, which opens with an iteration stage,
  the probe drove ports belonging to a different design and reported a harness
  failure that was entirely its own.
