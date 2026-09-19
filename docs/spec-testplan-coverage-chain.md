# The doc → testplan → coverage chain

Scoped design note. Covers only the traceability chain from specification text to
coverage verdict. Oracle independence, mutation grading, failure-report design and
trace localization are out of scope — see `tb-hardening-research.md` for those.

The chain has three links, and **each needs a check in a specific direction**. The
recurring failure across published systems is checking only the easy direction.

```
spec clause  ──1──▶  testpoint  ──2──▶  cover bin + check  ──3──▶  verdict
   (UID)               (UID)                  (UID)              per testpoint
```

---

## Link 1 — spec clause → testpoint

**Artifact.** Every spec clause carries a UID. Every testpoint carries a UID and
declares which clause it covers. GoGoTB's testpoint tuple is a good shape:
⟨stimulus, expected response, check method, dimension⟩ over seven dimensions —
data boundaries, control flow, timing constraints, FSM transitions, protocol
compliance, error injection, microarchitectural interaction.

**The check, and its direction.** Three defects must be reportable:

| Defect | Meaning |
| --- | --- |
| **Uncovered** | a spec clause no testpoint covers — *the load-bearing one* |
| **Orphaned** | a testpoint claiming a clause that doesn't exist |
| **Unwanted** | coverage of a clause that never requested it — the anti-padding guard |

Naming is not checking. GoGoTB anchors every bin to "a named specification
behavior" — that is testpoint → clause, a label. Nothing there establishes clause →
testpoint. Its own text concedes the consequence: *"Testpoint completeness sets a
hard ceiling on verification quality. Any behavior not enumerated at this stage
cannot be verified downstream."* It names the ceiling and does not measure it.

**Why this is the whole ballgame.** If the denominator is the agent's own testpoint
list, the coverage figure means "% of behaviours I thought of," and an omitted
clause is invisible rather than penalised. GoGoTB's headline 83.2% functional
coverage is computed against LLM-derived bins with nothing checking those bins
against the spec text. Without link 1 the metric cannot detect the failure mode it
is named for.

**Tooling.** StrictDoc `RELATIONS`, or OpenFastTrace `Needs:` / `Covers:`. OFT's
model is the stricter fit because the *requirement* declares what must cover it —
the denominator originates in the spec, not in the agent.

---

## Link 2 — testpoint → cover bin + check

**Artifact.** Each testpoint maps to ≥1 cover bin (was the scenario reached?) and
≥1 check (did the DUT behave correctly there?). These are different questions and
need separate records.

**The check.** A bin whose associated check cannot fail is vacuous: reached, and
proves nothing. Require a dataflow path from each check's result to the variable
deciding the verdict — this generalises ChipVerilog's `tb_is_self_checking()`,
which only asks whether any string literal can express a failure.

**Invariants.**

- **Freeze the denominator at loop entry.** The agent may add testcases that hit
  existing bins; it may not add bins. Otherwise it pads with easy bins and coverage
  climbs without any spec being covered.
- **The agent must never author both a bin and its threshold.** Derive the
  threshold once from a reference run and store it as task metadata (CVDP's CID12
  convention). Self-authored threshold plus self-authored bin is self-report.
- **Never report a ratio over agent-added checks.** Adding trivially-passing
  testcases inflates any "% passing" figure. Absolute failing-check counts, plus
  ratios only over the frozen denominator.
- **Append freely, retract only with evidence.** Withdrawing or amending a check
  requires a witness — reference precheck, formal counterexample, or N-version
  disagreement — never repair-agent discretion. Versioned UIDs make this
  mechanical: OFT flags every check still covering a superseded clause revision as
  `outdated`. Log retractions as a distinct event; a rising retraction rate means
  testpoint extraction is bad.

**Tooling.** `pyvsc` (SystemVerilog-style covergroups in Python, exports UCIS) or
`cocotb-coverage`; `pyucis` for the coverage database and merge.

---

## Link 3 — coverage → verdict

**Three-valued, per testpoint.** `PASS` / `FAIL` / `NOT-EXERCISED`. Today
`sim_review()` returns a single bool plus a mismatch count, so `is_pass=True,
mismatch_cnt=0` means "everything checked and passed" and "nothing ran" identically.
Bolting coverage onto that loop without widening the verdict yields a system that
reports success on unexercised spec. **No overall PASS while any testpoint is
NOT-EXERCISED without a recorded disposition.**

**Discharge unreachable bins formally, not by assertion.** For each uncovered bin,
assert the negation of its condition and run `sby mode prove`. A proof means
genuinely unreachable — it leaves the denominator *with the proof and its assumption
set recorded*. `UNKNOWN` or a counterexample means a real hole. GoGoTB removes
structurally unreachable bins with no stated criterion; doing it with a recorded
proof is the difference between an exclusion and an excuse. Re-check every exclusion
when the contract changes — an exclusion proved under a wrong constraint environment
is indistinguishable from a real one.

**Instrument the testbench, not just the DUT.** Verilator will instrument `tb.sv` as
readily as `rtl.sv`, and **coverage on the mismatch-counter increment line is a
provable dead-check detector**: PASS with zero hits on that line means the check
never executed. Every published system (GoGoTB, LLM4Cov, CovAgent, HAVEN, LLM4DV)
instruments only the design. This is a one-flag experiment.

**Report toggle before line.** Line coverage saturates and stops discriminating;
toggle is what separates a real run from a shallow one.

**Classify residual gaps, don't just count them.** GoGoTB's taxonomy routes each
uncovered bin to a different remedy: stimulus gap → directed test; sequence gap →
multi-transaction test; cross hole → constraint refinement; state unreached →
state-routing sequence; timing dependent → cycle-precise stimulus; transition gap →
edge-condition test; seed insufficient → more seeds. Veri-Sure needs an **eighth
category its seven lack — *covered and failing*** — because GoGoTB's RTL is fixed
and ours is generated. That category is the existing correctness loop.

Temper the expectation: on GoGoTB's I2C case, closure ran 56.0% → 71.6% → 84.1%,
and **16 of the 24 residual bins were stimulus or sequence gaps** — the system knew
exactly which bin and what stimulus was needed, and the agent could not produce the
test. Their conclusion: *"The coverage model itself is not the bottleneck."* This
chain buys measurement and routing, not closure.

---

## Loop structure

Coverage closure is the **outer** loop, correctness repair the **inner** one. Repair
to convergence on currently-covered bins, then expand coverage; a newly covered bin
that fails re-enters repair. Interleaving wastes stimulus generation on RTL about to
change; repairing first lets the run declare victory on unexercised spec.

## Toolchain

| Link | Tool | Notes |
| --- | --- | --- |
| doc | StrictDoc | bidirectional ReqIF — Polarion stays authoritative |
| 1 | OpenFastTrace, or StrictDoc `RELATIONS` | OFT: GPL-3.0, Java 17, CI tool in its own process. Tags Python natively, **not SystemVerilog** — an argument for cocotb testbenches |
| 2 | pyvsc / cocotb-coverage | covergroups in Python |
| 2–3 | pyucis | Accellera UCIS model, merge, HTML report |
| 3 | `verilator --coverage-line --coverage-toggle --coverage-user` | merge `verilator_coverage --write merged.dat cov_*.dat`; lcov via `--write-info merged.info` |
| 3 | SymbiYosys `mode prove` | unreachability discharge |

Everything is text in Git, so retractions and exclusions arrive as reviewable diffs.

## Verified mechanics (Verilator 5.038 + cocotb 2.0.1)

Measured rather than assumed, because two details here were wrong on first
writing:

- **There is no `--coverage-fsm` flag.** The real set is `--coverage-line`,
  `--coverage-toggle`, `--coverage-user`.
- **`verilator_coverage` takes input files positionally.** `-read` appears in
  5.020's perl documentation but is rejected by 5.038:
  `verilator_coverage --write merged.dat cov_0.dat` and
  `verilator_coverage --write-info merged.info cov_0.dat` both work.
- **cocotb emits coverage with no extra wiring.** Its Verilator harness
  (`cocotb/share/lib/verilator/verilator.cpp:66-70`) calls `VerilatedCov::write()`
  under `#if VM_COVERAGE`, a macro Verilator defines when compiled with
  `--coverage`. So the flags belong in `build_args` (compile time); passing them
  at test time silently yields nothing.
- **Set the output filename per run.** The harness defaults every run to
  `coverage.dat`, so iterations clobber one another;
  `plusargs=["+verilator+coverage+file+cov_<n>.dat"]` fixes it.
- **lcov `.info` carries line (`DA:`) and branch (`BRDA:`) records, not toggle.**
  Toggle lives only in the raw `.dat`, but in a more tractable form than
  expected — one record per point, e.g.
  `C 'f<file>l<line>n<name>ttogglepagev_toggle/<module>o<signal>h<hier>' <count>`.
  Parseable when toggle-driven gap categorisation is wanted.

## Known gaps

- StrictDoc's source traceability is marked **experimental**; named language support
  is C/C++/Rust, so verify Python marker support before committing to it for link 1.
- Neither StrictDoc nor OFT knows anything about coverage databases — the link-2/3
  join (testpoint UID ↔ cover bin) is glue you write.
- No open-source equivalent exists to Verification IQ's analytics half: closure
  ranking, cross-run history, collaboration. You get the data model and the gap
  report, not the prioritisation.
