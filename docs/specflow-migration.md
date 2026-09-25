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
  (`benchmarks/run_chipverilog.py`).

  > **CORRECTION.** This bullet used to end "specflow is scoped to leaf nodes,
  > so the 16 hierarchical tasks of its 64 are out of scope by construction
  > rather than by accident." That was true when written (`ad7adbb`, 08:32) and
  > stopped being true thirty-three minutes later (`c25bc8e`, 09:05), which
  > added `specflow_extra_sources`. The chain is live end to end today:
  > `run_chipverilog.py:287` -> `TopAgentConfig` -> `specflow_node.py:197` ->
  > `specflow/run.py`'s `extra_sources`, and `submodules()` walks the subtree
  > transitively so a grandchild is supplied too.
  >
  > 16 of the 64 tasks are hierarchical, and **none has ever been run** --
  > both committed baselines (`i2c_master_bit_ctrl`, `or1200_ctrl`) are leaf.
  > So the support is landed and unexercised, not proven.
  >
  > What hierarchy support DOES and does not mean, in `specflow/run.py`'s own
  > words: the children are *libraries*, not part of the oracle. Supplying them
  > makes a hierarchical design **elaborate and simulate**; the reference model
  > still has to derive the COMPOSED behaviour from the specification alone.
  > That is the hard half, and it scales with the subtree: `i2c_master_top` has
  > 2 children, `or1200_top` has 38.

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

| DUT | cycle-exact | transactional |
| --- | --- | --- |
| golden (correct) | 63 / 168 | **168 / 168** |
| generated (wrong) | 20 / 168 | **28 / 168** |
| **separation** | **43** | **140** |

**A correct design scores 168/168** — every testpoint, all 219 checks invoked,
no timeouts. That is the plan's stated target for the control, and reaching it is
what licenses reading the rest of the table: on this design the harness produces
**no false failures at all**.

Cycle-exact is 63/168 on the same isolated harness with the same oracle, so a
criterion built on the contract's guessed `latency_cycles` would still reject a
correct design in 105 of 168 places. That is the argument for comparing content
rather than cycles, and the separation it buys is 140 against 43.

An earlier revision of this table read a 5x ratio between the two criteria off a
mismatch — a post-isolation transactional column against a pre-isolation
cycle-exact one. Both columns here are post-isolation.

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

**Re-verified after testpoint isolation.** The sweep above was measured before
"every testpoint gets its own simulator process" landed, and that change alters
how every suite runs, so the figure was stale evidence for a current claim. The
re-run reproduces it exactly: 45 rejected, `instruction_mem` the sole pass, the
same 18 build failures in the same two groups.

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

### G1: a requirement may not assert a number its evidence does not contain

Found while measuring the duration obligations, and worth fixing independent of
any timing work. On `i2c_master_bit_ctrl`, **seven of 72 requirements** assert
that `cmd_ack` is one clock cycle wide while each cites a span reading only
"asserts `cmd_ack`" — no duration at all. REQ-0068, citing a span that likewise
says only "asserts `cmd_ack`", did *not* assert a duration. The same
specification produced both readings, which is what a claim arriving from
outside the evidence looks like. The rate is stable: 3–10% of requirements in
every recorded run, and the flagged quantity is the same one every time.

The claim happens to be true — the specification states it in a global sentence
elsewhere. That is exactly why it is worth catching. Nothing downstream can
check a claim against evidence that does not contain it, and everything
downstream treats a requirement as given, so the number becomes an obligation
the design is held to that no gate can question.

G1 now extracts quantities — a number *and* a unit, so bit indices and state
encodings are not flagged — from each requirement's text and requires them in
the spans it cites. `one clock cycle`, `1 clk cycle` and `a single cycle` are
the same claim; `clk_cnt[15:0]` states a width of 16 on the evidence side.

**Severity is proportionate to which failure it is.** A quantity that appears
nowhere in the specification was invented, and blocks. A quantity the
specification states somewhere the requirement did not cite is an attribution
gap — the evidence exists, it is simply not linked — and warns, because the fix
is to add a span and G1 blocks the whole run. Across every recorded run the
split is **0 errors, all warnings**: nothing was invented, and everything was
uncited. The S1 prompt now states the rule up front, so the first attempt should
carry the extra span rather than a repair round adding it.

### What this work does not establish

**The control model is at 113/168, not 168/168.** 55 testpoints still fail with
a correct DUT and an oracle transliterated line by line from it, spread across
`scl_oen` (21), `al` (16), `sda_oen` (11), `cmd_ack` (11) and `busy` (3) — no
longer dominated by any single output, which is what testpoint isolation
removed. Each remaining cluster is its own question and none has been chased.

The `dout` residual this section originally described as an open question about
a post-reset filter transient was settled and that guess was wrong: it was state
leaking across testpoints, fixed above.

**Two of the plan's verification items need a live model run and did not get
one.** Whether Phase 3 actually removes the 61 testpoints that end mid-command
depends on the testcase agent emitting `hold`/`until`, and the benchmark score
depends on RTL a live run produces. Neither could be checked from this session:
the configured gateway no longer serves `openai/gpt-5.6-luna` — it now exposes
only Google Gemini models — and `OPENAI_BASE_URL` is missing its `/v1` path, so
every call 404s twice over. Switching models would make any result
incomparable with the baselines recorded above, which is a decision for whoever
owns the experiment, not a default to pick.

**The benchmark score is expected to be unmoved by this work**, and that was
stated before any of it was written. A transactional testbench accepts RTL that
fails sequential equivalence; it stops the oracle destroying correct RTL, which
is a precondition for anything else, not a scoring improvement.

### Every testpoint gets its own simulator process

The `dout` residual above was **not** a reference-model fidelity problem. It was
state leaking between testpoints.

cocotb runs every test module in **one** simulator process, and the DUT is
elaborated once. Any register the design does not reset keeps whatever the
previous testpoint left in it, and `Env.reset()` cannot clear it — there is no
reset path to drive. Golden `i2c_master_bit_ctrl` writes `dout` with

```verilog
always @(posedge clk) if (sSCL & ~dSCL) dout <= #1 sSDA;
```

and no reset at all. TP-0002 **passes run alone** and **fails inside the
168-test suite**, because TP-0000 and TP-0001 left `dout` at 1 while the
reference model — a fresh `Model()` per test whose `reset()` sets it to 0 —
starts at 0.

That is worse than a wrong number: verdicts depended on test **order**, so a
testpoint could pass for a reason that had nothing to do with it, and reordering
the suite changed the score. A testpoint is supposed to be an independent claim
about the design.

`run_suite` now runs one simulator process per testpoint. The build is shared;
only the run repeats, measured at ~0.39s per extra process — about a minute more
for 168 testpoints. Per-process coverage files are merged with
`verilator_coverage --write`, the same reduction `coverage.py` already performs
across iterations, and the waveform handed to the repair agent is the first
**failing** testpoint's.

| | before | after |
| --- | --- | --- |
| golden | 69 / 168 | **113 / 168** |
| generated (wrong) | 28 / 168 | 28 / 168 |
| **separation** | **41** | **85** |

`dout` disappears from golden's diverging outputs entirely. The wrong candidate
does not move, which is the check that matters: isolation removed a false
failure, not discrimination. The remaining 55 golden failures are `scl_oen` 21,
`al` 16, `sda_oen` 11, `cmd_ack` 11, `busy` 3 — the next layer, and no longer
dominated by one output.

Pinned by `tests/fixtures/harness/unreset_reg`, a design with one deliberately
unreset register, driven by two testpoints where the first loads it and the
second never does. Both the behaviour and the mechanism are asserted: batching
the modules back together fails both tests.


### What the control measurement is, and is not

Only the **DUT** in that measurement is known-good. Three of the four things
making up the "testbench" are unvetted:

| component | status |
| --- | --- |
| `specflow/tb/runtime.py` + renderer | repo code — the thing under test |
| the oracle (`scratchpad/goldmodel/ref_model.py`) | a hand transliteration of golden into Python; best-effort, never verified |
| the stimulus | LLM-generated in the cv-j3 run, re-expressed at `hold=60` |
| the checks and coverage model | LLM-generated in cv-j3 |

So a failure in it is **not** attributable to the harness by construction, and
the 113/168 figure is a ceiling on the *pair*, not a measurement of the harness
alone. The only known-good-TB measurement in this repo is
`tests/test_harness_conformance.py`: seven hand-matched (RTL, model) pairs that
agree by construction, each also required to reject a tied-off DUT. Those score
100%, on designs far smaller than an i2c core.

**All 55 were attributed, and every one was the oracle.** They came from exactly
two bugs in the transliteration, both the same mistake — reading a value from the
wrong clock generation — and neither in the harness.

**1. `sta_condition`/`sto_condition` computed combinationally (46 of 55).**
Golden registers them (`sta_condition <= #1 ~sSDA & dSDA & sSCL;`) and `busy`/
`al` read the *registered* value. Collapsing that stage made `al` fire one edge
early, which aborted the command the DUT was completing; the model then fell a
whole command period behind and missed a command window at the next stimulus
vector boundary. That single error produced the `al` cluster, the `busy` cluster,
the "`scl_oen` alone, model 1, DUT 0" cluster (the FSM releases both lines when
`al` fires), and every "one side ran out of states" report. Golden went
**113 → 159**.

**2. The FSM gated on `clk_en` after the divider overwrote it (the other 9).**
Golden's `if (clk_en) case (c_state)` sits in an `always @(posedge clk)` block,
so it reads the value latched on the *previous* edge. Reading the freshly
computed one advances the machine one edge early. Invisible while `ena = 0` —
`clk_en` is then 1 every cycle, so old and new agree — and it appeared the
instant the prescaler started toggling: DUT and model agreed exactly for the
first twelve `cmd_ack` pulses, then the model sat one edge behind for the rest of
the run. Golden went **159 → 168**.

How each was pinned: dump both sides' internals edge by edge through the real
`Env` and compare against the Verilog. The filter chain (`cSDA`, `fSDA`, `sSDA`,
`dSDA` and the SCL equivalents) matched on every edge in both investigations,
which is what ruled the harness out — the reset alignment and the lockstep
advance were doing their job, and the divergence was downstream of them in the
model's own logic.

**The wrong candidate scored 28/168 before, during and after both fixes.** That
is the control that matters: correcting the oracle removed false failures on a
correct design without softening the criterion on a wrong one.

What this does and does not establish. It establishes that the harness produces
**no false failures** on this design, this stimulus and this coverage model —
which is precisely the property the repair loop needs, since a false failure is
what deforms correct RTL. It does not establish the absence of false *passes*;
that is what the null-oracle sweep across all 64 designs is for, and what the
tied-off-DUT half of the conformance suite is for.

## Generated reference models, measured the same way

The control measurement above used a **hand** transliteration of golden. That
answers "can the harness be driven correctly", not "does the pipeline produce a
correct oracle". This section runs the pipeline end to end and scores what it
generated, with no hand-written model anywhere in the loop.

Two designs were chosen to contrast: `alu` (`mips_16`, combinational, 3-bit
command mux) and `or1200_gmultp2_32x32` (sequential, two pipeline stages, one
reset). `i2c_master_bit_ctrl` is the third and is reported separately.

Every model is scored twice — against golden RTL and against a wrong RTL — and
**both numbers are reported**. The pass rate alone cannot distinguish a correct
model from a vacuous one, which the gmult result below demonstrates the hard way.

| design | model vs golden | model vs mutant | separation |
| --- | --- | --- | --- |
| `alu` | 40 / 40 | 0 / 40 | **40** |
| `or1200_gmultp2_32x32` | 36 / 36 | 4 / 36 | **32** |

Both generated models are correct on the golden design and fully discriminating
against a wrong one. Neither needed a repair iteration.

### The first gmult measurement was an artefact of the instrument

It first read **36/36 against golden and 36/36 against the mutant** — separation
0, which is the exact signature of a vacuous oracle. Longer holds (4, 12) drove
both columns to 2/36 with separation still 0, ruling out a stimulus-reach
explanation.

The oracle was fine. `benchmarks/mutate.py` masked comments, strings and
`` ` ``-directive lines but not `[msb:lsb]` ranges, so `input [`OR1200_W-1:0] X`
was an applicable mutation site. Changing that `-` to `+` widens the port to 34
bits; `xi` is an `integer`, so `xi <= X` truncates back to `X[31:0]`, and the
harness only ever drives the 32-bit contract port. The mutant was **behaviourally
identical to golden**, so a perfectly discriminating model was obliged to pass
both.

All five of gmult's applicable sites were ranges — the tool could not express a
wrong version of that design at all. With ranges masked and `*` added as an
operator, the design has exactly one site (`p0 <= #1 xi * yi` -> `xi + yi`, real
logic) and the same model scores 36/36 against golden and 4/36 against the
mutant.

Bit-selects without a colon (`x[i+1]`) stay mutable, because selecting a
different bit is a genuine behavioural change. When masking leaves a design with
no site the tool raises rather than returning golden unchanged, so the failure is
loud instead of a silently passing check. The `mips_16/alu` mutant is
byte-identical before and after the fix, so the alu column is unaffected.

**The general lesson is about the measurement, not the tool.** "Model passes
golden" is unfalsifiable on its own, and the check that is supposed to falsify it
is itself a piece of code that can be wrong in a direction that manufactures
agreement. A separation of 0 should be read as "the instrument is suspect" before
it is read as "the model is vacuous".

### One SystemVerilog keyword decided the `alu` score

The generated `alu` RTL scored `function_fail`. Rewriting **only** its port
declarations from `input logic [15:0] a` to `input [15:0] a` — body byte-for-byte
identical, verified — scores `pass`. The generated gmult RTL has the same
`input logic` ports and scores `pass` regardless.

The difference is which oracle ChipVerilog reaches, and the chain has two links:

1. `alu` is one of the 16 tasks that ship a self-checking testbench, so it is
   scored by simulation. That testbench is plain Verilog and iverilog rejects
   `logic` in a port list — `Net data type requires SystemVerilog`. The scorer
   falls back to formal equivalence.
2. **The formal fallback for `alu` cannot be passed by any correct design.**
   Golden's first case arm is `` `ALU_NC `` = `3'bxxx`, and yosys treats `x` in a
   case item as a don't-care that matches every `cmd`. Yosys synthesises golden
   itself to `assign r = 16'hxxxx;` — the whole design. Anything computing real
   values is "not equivalent" to that.

So the keyword does not merely change a verdict; it diverts scoring from a
passable path to an unpassable one. Confirmed at both ends: iverilog simulation
of golden against the candidate agrees on every `cmd` including yosys's own
counterexample (`a=0x8000, b=13, cmd=6`), and the candidate passes the shipped
testbench once its ports are portable.

`rtl_generator`'s prompt now requires Verilog-2005 port declarations while
leaving the body free to be SystemVerilog; `tests/test_rtl_port_dialect.py`
pins it.

**How far the yosys degeneracy reaches: one task.** Synthesising all 64 golden
designs and looking for a constant-`x` driver on a declared output port finds
`alu` and nothing else. Four `double_fpu` designs (`fpu_add`, `fpu_div`,
`fpu_round`, `fpu_sub`) emit constant-`x` assignments, but every one is an
internal don't-care pad on a shift or mux node, not an output. This is a
one-design defect in the benchmark, not a systematic one — worth knowing so that
an `alu` equivalence result is never quoted as a function verdict.

### Localising a model defect: what the edge-by-edge dump can and cannot see

`benchmarks/divergence_trace.py` exists because scoring does not localise. A
model at 118/168 gives no clue which of the 50 failures share a cause, and the
cause is never at the edge the score points to.

Validated against a defect with known ground truth, by reintroducing the
control oracle's own bug into the corrected model. Two variants, because they
answer different questions.

**The stored-state variant — the tool sees the cause before any output moves.**
Computing `sta_condition`/`sto_condition` from the freshly updated filter
outputs instead of the previous generation (golden registers them:
`sta_condition <= #1 ~sSDA & dSDA & sSCL`) reproduces the original defect. On
`TP-0054`:

```
e7   outputs-differ: -            internals-differ: ['sto_condition=0/1']
e8   outputs-differ: ['al=0/1']   internals-differ: ['sto_condition=1/0']
e9   outputs-differ: ['al=1/0', 'scl_oen=0/1']
```

The internal fires **one edge early and one edge before any output moves**, and
the tool names the signal. That is the whole claim, demonstrated rather than
asserted.

**The transient-read variant — the tool sees the signature, not the signal.**
Leaving the computation correct but making `busy`/`al` *read* the fresh value
scores 118/168 with the same `al`-dominant profile, and the internal trace shows
**no disagreement on `sta_condition` at all**: the stored end-of-edge value is
identical, and only the intermediate read is wrong. What survives is the
fingerprint — `al=0/1` at one edge, `al=1/0` at the next — which identifies the
class ("one clock generation early") without naming the signal.

So the honest statement of what the instrument buys: it converts "50 testpoints
failed" into "these failures begin at edge N on signal S", whenever the
wrongly-read value is stored state. When the mis-read value is a transient, it
still bounds the search to one edge and identifies the class, and the analyst
reads the remaining step off the Verilog. Neither variant required looking at
the failing testpoint's score at all.

Two numbers worth keeping alongside: the reintroduced bug costs the control
model **168/168 → 118/168**, and the wrong candidate stays at 28/168 through
both variants. A defect that moves only the correct design's score, never the
wrong one's, is the shape a false-failure defect has.

**The committed control is the 168/168 one.** Everything above rests on that,
and until now only the scratch copy had been scored. `benchmarks/controls/
i2c_master_bit_ctrl/ref_model.py` scores **168/168 against golden and 28/168
against the cv-j3 candidate, separation 140** — so the artifact in the
repository is the one the claims were measured on, not a near copy of it.

## Phase 3: a defect taxonomy across three shapes

Three designs, one generation configuration (`gpt-5.6-luna`, effort `xhigh`,
monolithic reference model plus per-requirement judge). Every model is scored
against golden RTL and against a wrong DUT, and **both numbers are reported**.

| design | shape | vs golden | vs wrong DUT | separation | refmodel rounds |
| --- | --- | --- | --- | --- | --- |
| `alu` | combinational | **40 / 40** | 0 / 40 | +40 | 1 |
| `or1200_gmultp2_32x32` | 2-stage pipeline | **36 / 36** | 4 / 36 | +32 | 1 |
| `i2c_master_bit_ctrl` (round 0) | prescaled FSM + 4-stage input filter | 34 / 181 | 11 / 181 | +23 | — |
| `i2c_master_bit_ctrl` (round 4) | " | 18 / 181 | 27 / 181 | **−9** | 5 |

The i2c baseline is not assumed. The hand-written control oracle scores
**181/181 on this run's own testplan** (wrong candidate 11/181, separation 170),
so 181/181 is reachable with this stimulus and this coverage model, and the
generated model's shortfall is a model defect rather than a harness or stimulus
limit.

### Shape predicts it, in this sample

The two designs whose entire behaviour is one expression or two registers were
correct on the first round and needed no repair. The design with a
synchroniser, a majority filter, a prescaler and a twelve-phase FSM was not, and
five rounds did not fix it. That is a sample of three and should be read as
such — but the split is not marginal, it is 40/40 and 36/36 against 34/181.

Notably, gmult contains the exact trap that defeated the hand-written control
oracle twice, and the generated model handled it correctly:

```python
previous_p0 = self.p0                    # capture BEFORE overwriting
self.p0 = self.mask(product, 64)
if not reset_active:
    self.p1 = self.mask(previous_p0, 64)  # p1 reads the PREVIOUS p0
```

It also reproduces golden's asymmetric reset — `RST` is asynchronous and
affects only `p1`, while `p0` advances unconditionally. So "reads a value from
the wrong clock generation" is not a defect the generator commits merely
because a design contains the opportunity.

### It is NOT the control's defect class, and it is not point-localisable

The control's two bugs were both one-line, single-stage, and independently
repairable: fixing them took it 113 → 159 → 168. The generated i2c model is not
like that.

**Localised, by the three-way trace** (DUT / control / generated) on `TP-0006`.
The generated model's `sSCL` and `sSDA` never move at all, where both the DUT
and the 181/181 control drop them at edge 1 and restore them at edge 4:

| edge | `scl_i` | DUT `sSCL` | control | generated |
| --- | --- | --- | --- | --- |
| e1–e3 | 1 | 0 | 0 | **1** |
| e9 | 0 | 0 | 0 | **1** |

The cause is visible in `_update_filter`: `if not ena:` takes a branch that
skips the filter shift entirely. Golden gates only `filter_cnt`, and forcing it
to zero makes `~|filter_cnt` **true**, so golden's filter shifts on every cycle
while disabled — it runs faster, it does not stop.

**But repairing it does not help, and that is the finding.** Two attempts, both
measured rather than reasoned:

| repair | vs golden | separation |
| --- | --- | --- |
| none (round 0 as generated) | 34 / 181 | +23 |
| the whole filter transliterated faithfully | 18 / 181 | −12 |
| ONLY the `ena` gating, phase left alone | 11 / 181 | −10 |

Both make the model match the **wrong** RTL better than golden. The model's
phase convention is load-bearing across every downstream stage, so a
single-stage repair desynchronises the rest. On this design the shortfall is
**not attributable to a point defect** — which matters for the repair loop,
because an agent shown a failing check can fix a point defect and cannot fix a
global disagreement about pipeline phase.

The divergence is behavioural, not phasing. All 184 mismatches are "a state has
the wrong value" and none are "one side ran out of states" — and the
transactional criterion already ignores durations, so the model emits a
different sequence of output *values*, not merely different timing.

### The judge cannot see it, and made it worse

Four judge rounds, 231 judgements each, and `ena` still freezes the filter in
every one of rounds 0 through 4. The judge compares the model against the
**specification**, and the specification licenses what the model wrote:

> `ena`: Core enable signal. **It gates normal timing/filter operation.** When
> `ena` is low, the clock divider is reloaded and the input filter counter is
> reset, preventing normal bit-timing progression.

The model implemented the summary clause. Golden implements the precise one
that follows it — the *counter* is reset — which has the opposite effect. A
judge that compares a model to the specification cannot catch a defect the
specification supports. Only golden RTL exposes it, and production has no
golden.

Worse, the loop **degraded** the model. Round 0 was wrong but active and
discriminating (+23). Round 4 is inert: driven through 60 edges of varied
stimulus it emits **one distinct output state**, where round 0 emits five. Its
score inverts to −9 because a constant model agrees with whichever DUT is
quietest, and the wrong candidate is quieter than golden.

### The gate that should have caught it does not exist

`refmodel/validate.py`'s behavioural checks are: it imports, it instantiates,
it is deterministic, and it writes every declared output. **A constant model
passes all four.** The conformance suite already holds the DUT side to the
right standard — every fixture must also *reject a tied-off DUT* — and there is
no equivalent requirement on the model itself.

That is the concrete, actionable gap this measurement found: a reference model
whose outputs never move cannot discriminate anything, and nothing in the
pipeline says so.
