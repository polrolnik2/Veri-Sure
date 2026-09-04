# Recovering the discarded oracles: what was measured, and what to change

Every number here comes from a run on disk plus subagent authoring done against
the pipeline's own prompt builders. Nothing is projected from a model of the
pipeline; where a figure is arithmetic on measurements rather than a measurement,
it says so.

## The instrument, and why it is not golden RTL

Everything is scored with **`liveness.assess` against the WITNESS** -- the
pipeline's own vacuity instrument. Its verdicts:

| verdict | meaning | owner |
|---|---|---|
| `live` | some perturbation of a port it reads moves its verdict | -- it works |
| `dead-oracle` | no perturbation moves it | the author |
| `dead-stimulus` | it can fail, but not near anything staged | the testplan |
| `unknown` | it decides nothing at all, so there is no verdict to move | -- |

An earlier draft of this work scored on "passes the golden RTL". That is wrong
twice: the oracle stage runs BEFORE the design exists, so a golden-passing
criterion cannot be evaluated where it would have to run; and it discounts
`dead-stimulus`, which is a testplan finding that added stimulus fixes, not a
defect in the check. Both readings are withdrawn.

## The population

`k1-dcfsm`, 89 requirements: 36 TRUSTED, **53 discarded** (25 ABANDONED,
24 ORACLE_INVALID, 2 VACUOUS, 2 NOT_ASSERTABLE). Every discarded body was
recovered from `agent_io` -- the artifact keeps sources only for TRUSTED, so a
rejected check's body is otherwise unavailable for audit.

### The residue is 36% not behaviour

`unit_kind` (in `requirements.json`; advisory, never a filter):

| unit_kind | in residue | pass rate entered -> TRUSTED |
|---|---|---|
| behavioural | 34 (64%) | 33/67 = **49%** |
| interface | 18 (34%) | 3/21 = **14%** |
| scaffolding | 1 (2%) | 0/1 |

Of the 25 ABANDONED, **14 are interface** -- the abandonment class is largely
the staging loop spending three attempts each on glossary entries. The 40%
headline is a mixed denominator; on units a check is actually owed for it is 49%.

NOT a licence to exclude interface units: on `h3-i2c` they did *better* than
behavioural (7/13 = 54%). The collapse is design-specific.

### Liveness on the 53, before any change

```
                live   dead-stimulus   dead-oracle   unknown
behavioural (34)  18         3              1          12
interface   (18)   6         0              1          11
scaffolding  (1)   0         0              0           1
-----------------------------------------------------------
total       (53)  24         3              2          24
```

**Two of 53 are bad checks.** Twenty-four are live checks that were thrown away.

## Per-iteration recovery (k1-dcfsm)

Cumulative UNION over arms actually run, not a sum of separate experiments.

| # | change | +new | cum | TRUSTED | of 89 |
|---|---|---|---|---|---|
| 0 | as the run stands | 0 | 0 | 36 | 40% |
| 1 | keep a discarded check liveness calls `live` (F2) | 24 | 24 | 60 | **67%** |
| 2 | + route `_diagnose` to the author (F1) | 10 | 34 | 70 | **79%** |
| 3 | + `<failure_evidence>` rows (F4, no measurable gain) | 4 | 38 | 74 | 83% |

Of the cumulative 38: behavioural 26, other 12.

Iteration 3's +4 is a union effect, not a demonstrated improvement -- see F4.

### Cross-design replication of iteration 1

| run | reqs | TRUSTED | discarded | live-and-discarded | -> TRUSTED |
|---|---|---|---|---|---|
| c1-i2c | 127 | 110 (87%) | 17 | 11 (65%) | 121 = **95%** |
| a2-i2c | 105 | 75 (71%) | 30 | 19 (63%) | 94 = **90%** |
| h3-i2c | 118 | 54 (46%) | 64 | 35 (55%) | 89 = **75%** |
| d1-i2c | 97 | 48 (49%) | 49 | 20 (41%) | 68 = **70%** |
| k1-dcfsm | 89 | 36 (40%) | 53 | 24 (45%) | 60 = **67%** |

41-65% of every run's residue is checks liveness already calls live. This is the
single largest and most reproducible finding.

## The fixes

### F1 -- the diagnosis IS routed; the defect is that most requirements never get it

**CORRECTED TWICE. The mechanism I proposed already exists.**

`_unreached` (`oracles_stage.py`) already embeds `_diagnose(last)` in an
`unreached:` objection and returns it as a REJECTION, which flows through
`rejected`/`quotable` into `repairs` and so into `build_prompt`. The claim in an
earlier draft -- "the diagnosis is computed 107 times and shown to nobody" --
was **wrong**, and so was the follow-on claim that this is a routing fix.

*What IS true, measured on k1-dcfsm's 25 ABANDONED requirements:*

| | |
|---|---|
| carry an `unreached:` objection in `repairs` | **7** |
| never reached a repair round at all (highest is `fix0`) | **19** |
| staging attempts each | 3 of 3, and **no** budget exhaustion |

So the channel works and 18 of 25 were silenced inside `_unreached` -- which
returns `""` through five separate guards. **Which guard fired could not be
recovered from `oracles.json`**, because the staging record keeps the attempts
but not the verdict this function reached on them. Replaying the guards against
the FINAL bodies attributes 7 to `route_never_moved` and 1 to "decides on some
testpoint", but that replay uses end-of-run state and the guards were evaluated
per round, so it does not establish the cause.

*The offline experiment stands and is not affected by any of this*: on the 21
requirements that never reached an author, a prompt carrying the diagnosis
yielded 8 live and the bare `"never reached in 3 attempt(s)"` yielded 0 --
paired 0 vs 8, and the bare reason also destroyed the 5 the baseline had. That
measures the VALUE of the diagnosis reaching an author. It does not measure a
missing channel, because the channel is there.

*Shipped instead: the guards now name themselves.* Each of the five `return ""`
paths logs which one fired. It changes no behaviour and it is the thing that
makes the next measurement possible -- without it the cause of the 18 cannot be
established on a fresh run either.

*NOT shipped: any change to when or whether `_unreached` fires.* The residual
defect is real, but its cause is unestablished, and this fix has already been
wrong twice. A guard should not be loosened against a hypothesis.

### F2 -- overturn a REACHABILITY discard when liveness says `live`

**IMPLEMENTED** (`oracles_stage._reprieved` + the reprieve at the `trusted`
construction). Smaller than first claimed -- see the correction below.

*Defect.* A discard is terminal. Liveness runs every round but its verdict is
never weighed against the ground the check was discarded on, so a claim the
stage has already measured false still ends the requirement.

*What a `live` verdict does and does not refute.* Liveness decided the check on a
real replay and then moved its verdict. That is a counter-example to
**"never reached"** and nothing else:

| ground | refuted by `live`? | why |
|---|---|---|
| `never reached` / `unreached` | **yes** | the check DID decide |
| `off-target` | no | whether it tests ITS requirement is invisible to liveness |
| `not-assertable` | no | a claim the REQUIREMENT states no obligation, not about the check |

*THE CORRECTION THIS FIX WENT THROUGH, recorded because the first number was
wrong by 3x.* The original proposal was "keep any discarded check liveness calls
live", sized at 24/53 on k1 and 41-65% across five runs, projecting TRUSTED
36 -> 60. Classifying the 24 by the ground they were actually held on:
**16 were `off-target`** and 2 were `not-assertable`. Liveness speaks to neither.
The first draft of the predicate still matched the `not-assertable` string, and
`test_correspondence.py` caught it -- a hollow requirement was being promoted to
TRUSTED. The sound reprieve is **6 of 53**, not 24.

*Measured on the implemented predicate*, k1-dcfsm:

| | n | CONVICTS golden | passes | silent |
|---|---|---|---|---|
| frozen set as shipped | 36 | 8 (22%) | 20 | 8 |
| the 6 the reprieve admits | 6 | 1 | 1 | 4 |
| extended set | **42** | 9 (**21%**) | 21 | 12 |

TRUSTED **36 -> 42** (40% -> 47% of 89). Golden is known-good, so a conviction is
a FALSE conviction: the rate is flat, 22% -> 21% of the set and 29% -> 30% of
deciders. The reprieve does not buy coverage at the cost of false alarms.

*Caveat.* 4 of the 6 admitted are SILENT on golden -- live against the witness,
but they do not fire against the real design. They are legitimate members of the
set and they add no decisions to it.

*Sound reprieve across runs* (live-and-discarded whose ground is a reachability
claim, so the `off-target` majority is excluded): k1 6, and on the wider
"reachability or not-assertable" reading 8/53, 7/64, 5/49, 8/30, 8/17 -- the
per-run figures should be recomputed under the narrowed predicate before being
quoted as projections.

### F3 -- keep the better body across a repair round

**ALREADY IMPLEMENTED on the defensible axes. NOT shipping the third.**

The repair loop already refuses a replacement that is worse:

* `verify_one` on the replacement -- rejects `malformed:` / `vacuous:`, and the
  previous check stands;
* a `_decides` comparison -- "a replacement that stopped deciding is not a
  repair", blocking only a STRICT loss.

The axis my proposal added -- reject a replacement that is less LIVE -- was
present and **removed deliberately**. The reasoning is recorded in the source
against REQ-0055: the guard treated liveness as the only axis of improvement,
discarded a replacement that was better on trigger coverage (a dimension neither
`_is_live` nor `_decides` can see), and the requirement was lost two rounds
later to the defect that replacement had already fixed. *"A predicate that
cannot see the dimension a repair moved must not be the thing that decides
whether the repair survives."*

My +10/-9, +8/-4, +0/-5 gain/loss measurements are real, but they score
single-shot re-authorings on liveness -- exactly the axis that decision bars
from gating. They are evidence that repair rounds destroy work; they are not
evidence that this guard should come back.

If the destruction is to be addressed it should be at FREEZE time (ship the best
body seen across rounds) rather than by refusing replacements mid-loop, which is
what was already tried and reverted. That variant is unmeasured.

### F4 -- the `<failure_evidence>` block

**NO MEASURABLE DIFFERENCE. Do not ship on current evidence.**

Adds ~1.5 KB naming the objecting edge and surrounding rows, with edge numbers
shown (17.2% of adjacent rows in a transactionally collapsed trace are NOT
adjacent clock edges; 25,305 raw edges collapse to 4,693 rows).

*Measured*, all 53, liveness: evidence 28 live vs diagnosis 25. Paired
discordance **8 vs 11 -- not significant**. It is less destructive (-4 vs -9),
which is suggestive and under-powered at n=53.

*History, recorded because it is a lesson about method.* A 10-requirement pilot
read 0/6 -> 3/6 and was reported as a strong positive; the full population did
not reproduce it. It was then called REFUTED on a golden-passing criterion
(A=10, B=8) which was itself the wrong instrument. The honest verdict on the
right instrument is "no measurable difference".

### F5 -- do not cap the repair author's output

**UNTESTED.** Noted because a "keep it under 60 lines" instruction given to a
subagent correlated with unfalsifiable checks. Harness observation, not a
pipeline measurement.

### F6 -- stage what the CHECK said it did not see, not the normalized activation

**IMPLEMENTED.** `specflow/oracles_stage.py`, with tests in
`tests/test_stimulus_loop.py`.

`unexercised_against` runs the real `decide_all` and then throws away the one
thing the run produced. An abstaining `decide` returns `(None, None, detail)`,
and `detail` is the author's own sentence about the thing the check waited for
and did not see -- the only description of the missing scenario written in the
check's terms. The function replaced it with one fixed string for every
requirement:

```python
return {r.req_uid: "the check never saw its scenario in this stimulus"
        for r in results if r.unexercised()}
```

So every abstainer arrived at the staging loop described identically, and the
loop had nothing left to aim at but the NORMALIZED activation -- a different
stage's reading of the same requirement. Where the two diverge, stimulus aimed
at the activation stages a scenario the check does not recognise; the attempt is
spent, the check still abstains, and the record says "never reached" about a
scenario nobody tried to reach.

*Measured on k1-dcfsm.* Re-aiming the loop at the check's own account reached
**3** abstainers that aiming at the normalized activation had not reached in any
attempt: 0 -> 3.

The change is three lines of plumbing and one paragraph of prompt:
`unexercised_against` returns `r.detail`; `stage_unexercised` binds it (the dict
value was previously read only for its key); `_hint` names it as the target
alongside the activation rather than instead of it, because the two are both
true and the check's is the one that has to fire. An empty detail is not an
account, so it falls back to `NO_ACCOUNT` and `_hint` stays silent rather than
quoting a constant back at the generator.

**This is the correction to the negative result below**, which was measured with
the loop still aimed at the activation and is a finding about that target, not
about stimulus.

### F7 -- a requirement gated on a COMPILED-OUT option is unreachable by construction

**NOT IMPLEMENTED. Measured, and the largest single unexplained block on k1.**

`or1200_defines.v` carries `// \`define OR1200_DC_STORE_REFILL` -- commented
out. So `OR1200_DCFSM_SREFILL4`, and every transition into it, is behind an
`ifdef` that is FALSE in the design under test. The state does not exist in the
build.

**The fact is NOT missing. It is carried and never consulted.** The contract
holds it explicitly:

```json
"build_config": {"OR1200_DC_STORE_REFILL": false, "OR1200_DCLS": 4}
```

That block appears in **13 of 13** oracle-author prompts, and **no file under
`specflow/` or `eda_agent/` reads `build_config` at all** -- it is threaded into
every prompt and consumed by nothing. No gate asks whether a requirement's own
precondition holds in this build; `normalize` has no disposition for it; the
staging loop spends attempts reaching a state that is not compiled.

That the fact is USABLE from where it sits is not a conjecture: one of the three
repair arms read `build_config` unprompted while fixing an unrelated defect and
flagged it in its own report -- *"this build's contract_json sets
OR1200_DC_STORE_REFILL: false, meaning the feature this requirement describes is
compiled out in the design actually being verified"* -- then correctly declined
to act on it because the gate had not raised it. The information reached the
author. Nothing gave the author authority to use it, and no gate used it either.

**7 of 89 k1 requirements name that option, and they are three different
problems, which is why a blanket exclusion would be wrong:**

| group | uids | what it is |
|---|---|---|
| wholly unreachable | REQ-0025, REQ-0080, REQ-0085 | the whole obligation is "when the option is enabled, ... SREFILL4 ..." |
| reachable core, dead clause | REQ-0002, REQ-0036, REQ-0088 | asserts CLOAD/LREFILL3 behaviour AND "... and throughout SREFILL4 when enabled" |
| about the option being OFF | REQ-0079 | "when OR1200_DC_STORE_REFILL is **not** enabled, ... returns to IDLE without a refill" -- this build exactly |

*Dispositions, as shipped.* The three wholly-unreachable ones are all
ORACLE_INVALID: the repair budget was spent, three times each, on behaviour that
cannot occur. Of the middle group, REQ-0036 is **TRUSTED and decides `None` on
both testpoints it names** -- a vacuous trust counted as a recovered
requirement; the other two are ORACLE_INVALID. REQ-0079 is **TRUSTED and
convicts golden**, which is an ordinary over-strict check and not an
unreachability artefact at all -- it describes the live configuration.

**None of the seven is a sound trusted check**, and no single fix addresses all
three groups:

* **wholly unreachable** -> a fourth disposition, UNREACHABLE, out of the
  denominator and never sent to the author. Behavioural denominator 67 -> 64.
* **reachable core** -> the check must assert the reachable conjuncts and drop
  the dead one. This is an authoring instruction, not an exclusion; excluding
  them would discard real obligations about `burst` in CLOAD and LREFILL3.
* **REQ-0079** -> nothing to do with configuration. Ordinary repair.

*Detection is mechanical and needs no model call, and needs no new plumbing
either* -- `contract["build_config"]` already says which options are off, and a
requirement quoting an option that is false there is answerable before the
author is ever called. The distinction between the first two groups is NOT mechanical -- it is
whether the option gates the whole obligation or one conjunct -- so the safe
automatic action is to ROUTE the requirement with the configuration fact
attached, and let the author drop the dead clause, rather than to exclude on a
keyword match.

**This is a k1 finding and its generality is unmeasured.** The i2c designs were
not checked for the same pattern, and 41 of 541 OR1200 defines are commented out,
so the k1 count is a lower bound for this design family only.

### F8 -- the three-arm capability experiment REFUTES my structural claim

**RETRACTION. Not a capability problem, and not the structural problem I said it
was.** Haiku, Sonnet and Opus each answered the same 13 real repair prompts,
built through the pipeline's own `build_prompt` and carrying each requirement's
real objection. Scored CLEAN = live AND passes golden AND decides AND not
CONVICTED of vacuity. Golden scores; it never selects, and no arm saw it.

| class (n) | baseline | haiku | sonnet | opus |
|---|---|---|---|---|
| spec-names-state (4) | 1 | 1 | **2** | 0 |
| gate-overspecifies (4) | 0 | **2** | 0 | **2** |
| other (5) | 3 | 3 | 3 | 2 |
| **ALL (13)** | **4** | **6** | **5** | **4** |

**There is no capability gradient.** Opus scores exactly the baseline, BELOW
Haiku. Opus is also the only arm that regressed -- it lost REQ-0063 and REQ-0087,
both of which the baseline body already got right -- and its REQ-0002 answer is
the one the vacuity axis caught: `passes/live/CONVICTED`, a check that stopped
convicting golden by ceasing to assert. Without `must_fail` in the criterion it
would have scored as a recovery.

**And the structural claim is refuted on its own pre-registered terms.** Before
seeing results I wrote: *if the structural reading is right, all three arms score
about 0 on the four `spec-names-state` requirements regardless of capability*,
and *if an arm beats the baseline on that class, that is enough to stop me
asserting it*. Sonnet scored 2 of 4, taking REQ-0017 from CONVICTS to passes --
the requirement whose objection demands "the FSM being in LREFILL3 with cnt
nonzero".

*How it did it, because the mechanism is the useful part.* I had proved from the
golden RTL that the state is not pointwise identifiable:

```verilog
assign burst = (state == CLOAD) & tagcomp_miss & !cache_inhibit | (state == LREFILL3);
assign first_miss_ack = ((state == CLOAD) | (state == CSTORE)) & biudata_valid;
```

so CLOAD-with-miss-pending-before-data presents `burst=1, biu_read=1,
first_miss_ack=0` -- identical to LREFILL3 on exactly those ports. That much is
correct. What is wrong is the conclusion I drew from it. Sonnet did not try to
identify the state pointwise: it took the whole `burst==1` SPAN (which spans the
CLOAD entry and LREFILL3 together, collision included) and excluded the first
and last `biudata_valid` pulse positionally, so only the pulses that provably had
`cnt` nonzero are asserted. **The claim "you cannot key a window to LREFILL3 from
declared ports" is true pointwise and false at span level.** A span-relative
construction sidesteps state identification entirely, and no arm was told about
it -- one found it.

**What the data actually shows is VARIANCE.** Each arm fixed a different subset
and no arm dominates:

| | gained over baseline | lost |
|---|---|---|
| haiku | REQ-0006, REQ-0084 | none |
| sonnet | REQ-0017 | none |
| opus | REQ-0006, REQ-0084 | REQ-0063, REQ-0087 |

Union of all four bodies: **7 of 13**, against 4 for the baseline and 6 for the
best single arm.

**That union is an UPPER BOUND, not an achievable number, and the distinction is
the whole point.** Picking per requirement the body that passes golden is using
golden to SELECT, which this project does not permit. The selector actually
available to the pipeline is correspondence + liveness + `must_fail`, and whether
it picks the same bodies is unmeasured. What the spread does establish is that
re-authoring is nearly independent between attempts, which is the first evidence
for the freeze-time variant recorded under F3 -- *ship the best body seen across
rounds* -- and that variant remains unmeasured.

**The 6 no arm fixed decompose, and only 2 are unexplained:**

* REQ-0025 -- the compiled-out feature (F7). Correctly unfixable; Opus and Sonnet
  both said so unprompted.
* REQ-0002 -- reachable core with a dead SREFILL4 clause (F7).
* REQ-0028, REQ-0031 -- `silent` in EVERY arm including baseline: they decide
  nothing on golden. Not repair failures at all; an observability and stimulus
  finding.
* REQ-0067, REQ-0074 -- convict golden in every arm. These two are the genuine
  unexplained residue, and they are 2 of 13, not 4 of 4.

**Caveats that bound all of this.** n=4 per class, so Sonnet's 2/4 against
baseline's 1/4 is a one-requirement difference; one design (k1-dcfsm); one
single-shot re-authoring per arm with no repair rounds, where the pipeline gives
the author two; and subagents rather than the pipeline's own gateway, so the
prompt is identical but the serving path is not.

### F9 -- the port gate asks for a declared port, and meant a declared OUTPUT

**IMPLEMENTED.** `specflow/refmodel/oracles.py`, tests in
`tests/test_refmodel_oracles.py`.

```python
if not ports_read(oracle, contract):
    # An oracle naming no declared port cannot be about observable
    # behaviour, and the mutation gate could never scope a mutant to it.
    return "names no declared port, so it decides nothing observable"
```

`ports_read` returns any DECLARED port, inputs included. So a check reading only
`dc_en` and `dcqmem_cycstb_i` satisfied a gate whose own comment says "decides
nothing observable" -- and it does decide nothing, because no design drives its
own inputs, so no design can fail such a check. The comment stated the intent
exactly; the predicate did not implement it. `liveness.py:240` has had the right
set all along -- `ports_read(oracle, contract) & set(widths)`, commented
"outputs only".

*Measured over every run's oracle bodies, discarded ones recovered from
`agent_io`:*

| run | bodies | read no declared OUTPUT | dispositions |
|---|---|---|---|
| k1-dcfsm | 89 | **6** (7%) | 6 ABANDONED |
| d1-i2c | 97 | **5** (5%) | 2 ABANDONED, 2 ORACLE_INVALID, **1 TRUSTED** |
| a2-i2c | 105 | 0 | -- |
| c1-i2c | 110 | 0 | -- |

Eight of the eleven were **ABANDONED** -- "never reached in 3 attempt(s)", a
verdict that blames the TESTPLAN and spends three staging attempts first. One
was **TRUSTED AND FROZEN**: a shipped check that decides nothing observable.
k1's REQ-0001 is six lines and never touches `row["outputs"]` at all.

The two i2c runs with the later normalization score zero, so this is not
universal -- but where it bites it is misattributed in the most expensive
direction, and it is answerable statically, before any staging attempt or model
call.

**What it does NOT do is recover those requirements.** It moves the objection
from the testplan to the author and makes it mechanical and quotable; whether
the author then writes a check that reads an output is unmeasured. The three
k1 behavioural cases (REQ-0001, REQ-0009, REQ-0010) are an upper bound of +3,
not a measured gain.

*Three test fixtures had to change, and the reason is the finding.*
`UNEXERCISED` in `test_oracles_stage.py`, the inline body in
`test_oracle_promotion.py`, and the staging fixture all used an input-only check
as a convenient ABSTAINER. Abstention is what those tests are about; naming no
output never was. Each now reads the declared output and abstains on the same
condition, so the tests assert what they always meant.

## Negative results

**Adding stimulus aimed at the NORMALIZED ACTIVATION does not recover the
abstaining checks.** The qualifier is load-bearing and was added after the fact:
re-running this with the stimulus aimed at the check's own abstention detail
recovered 3 (F6). Read what follows as a result about the TARGET, not about
whether stimulus can help. For the 15
behavioural discards liveness called `unknown`/`dead-stimulus`, new stimulus was
generated through the pipeline's own path (`_hint` -> `build_suite_prompt_one` ->
author -> the real `gate_suite`) and added as a new testpoint, with the check
untouched. 11 of 15 gate-clean; the new testpoints replay (19-27 rows, 3-4
distinct output states, comparable to the existing median of 5 steps/tp);
**0 of 11 moved to live**, and 13 of 13 activations were staged. For this group
the stimulus is not the binding constraint -- the check does not recognise a
scenario that is present in its trace. That is F1's territory, not the testplan's.

One harness bug was found and fixed mid-run: the first scorer REPLACED a
testpoint's stimulus instead of adding one, deleting evidence the check already
had. Gate-clean went 8 -> 11 after the fix. The 0-moved result is from the
corrected run.


### F10 -- the acceptance test, with a control: +3, and `off-target` is not reproducible

**The measurement nothing else in this document had run.** Every other number
here scores a repaired body against GOLDEN. Golden is not the acceptance
criterion: these 13 were rejected by CORRESPONDENCE, and only correspondence can
make them TRUSTED. So the pipeline's own `build_prompt` was used to ask
correspondence about each repaired body, and the pipeline's own `rejects()` to
read the answer. No golden in that path.

**And a control, without which the result is uninterpretable.** The same
reviewer, the same builder, the ORIGINAL body -- the one the pipeline rejected.
"9 of 13 accepted" is equally consistent with a good repair and a permissive
reviewer, and only the paired movement separates them.

| | original | repaired |
|---|---|---|
| accepted by correspondence | **7 / 13** | **9 / 13** |

| movement | n | which |
|---|---|---|
| repair fixed it | 4 | REQ-0006, REQ-0017, REQ-0067, REQ-0087 |
| repair made it WORSE | 2 | REQ-0002, REQ-0031 |
| both accepted | 5 | REQ-0025, REQ-0032, REQ-0069, REQ-0074, REQ-0084 |
| both rejected | 2 | REQ-0028, REQ-0063 |

**Net paired movement +2. Attributable recovery +3**: control rejected, repair
accepted, AND clean on golden -- REQ-0006, REQ-0017, REQ-0087. REQ-0067 moved on
the gate but still convicts golden, so it recovers nothing.

**The headline is the control arm, not the repaired one.** The pipeline rejected
all 13 as `off-target`. An independent reviewer, given the same body and the same
prompt, **accepts 7 of them** -- a 54% disagreement with the shipped gate. Three
of the six requirements that pass both gates (REQ-0032, REQ-0069, REQ-0084) were
already accepted in the CONTROL arm, so the repair changed nothing for them by
this instrument; only the shipped gate had ever objected.

Two things follow, and they cut in opposite directions:

* **Against the repair story.** The naive read of the repaired arm -- "9 of 13
  accepted, +6 recovered" -- is wrong, and was corrected by the control from +6
  to +3. Half of the apparent recovery is reviewer disagreement with the
  original rejection, not any improvement in the check.
* **Against the gate.** A rejection a peer reviewer reproduces less than half the
  time is not a stable verdict. `off-target` is the disposition behind **23 of
  k1's 34 non-trusted behavioural requirements** -- the single largest block --
  and this is the first measurement of whether it replicates. It does not.

**What this does NOT license.** It is one reviewer, one model, one design, n=13,
single-shot with no repair rounds, and the reviewer is a subagent rather than the
pipeline's own gateway -- so it is a proxy for correspondence, not correspondence.
The 54% figure is a reason to measure the real gate's reproducibility directly,
by running the shipped correspondence twice on the same bodies. It is NOT a
licence to overturn any individual rejection, and nothing here was overturned.

*One harness bug, recorded because it changed the sign.* Five replies wrote
`"what_is_missing": null` against a bare `str` field, so `Review.model_validate`
threw and the scorer counted them unusable -- reading 4 accepted, 5 unusable.
Every one of the five was an ACCEPTANCE, so the bug biased the result against the
repaired bodies by exactly enough to make the experiment look negative. Dropping
nulls is serialization, not a verdict.

## Is 90% of behavioural reachable on k1? No, and here is the arithmetic

k1-dcfsm has **67 behavioural** requirements; 90% is **60**. As shipped, **33**
are TRUSTED (49%). The whole available pool is the 34 that are not, and it has
exactly three shapes:

| blocker | n | reason |
|---|---|---|
| ORACLE_INVALID | 23 | every one `off-target` -- the correspondence gate |
| ABANDONED | 10 | every one "never reached in 3 attempt(s)" -- the staging loop |
| VACUOUS | 1 | passed every variant of its own requirement |

Best case per bucket, using only what was measured this session:

* **the 10 ABANDONED.** Running liveness over their recovered bodies: **3 live**
  (F2 reprieves these -- and this is where the ledger's +3 behavioural comes
  from, not a larger number), **3 that read only inputs** (F9; recovery
  unmeasured), **1 `dead-oracle`** which cannot fail and is correctly rejected,
  and **3 genuinely unexercised** (F6's target). Ceiling **+9 of 10**.
* **the 23 ORACLE_INVALID.** rx7's union of four bodies was 7 of 13 on GOLDEN,
  which scaled to **+12** -- but F10 then ran the actual acceptance test with a
  control and the attributable recovery was **+3 of 13**, not 7. Scaled to 23
  that is **+5**, and the scaling is still an assumption.
* **the 1 VACUOUS.** +0.

**Optimistic ceiling, with F10's controlled figure in place of the golden-only
one: 33 + 9 + 5 = 47 of 67 = 70%. The target is 60. It is short by 13**, and even
that is not achievable, because it assumes all three of:
per-requirement selection on golden (which this project forbids -- golden scores,
it never selects); every routed author fix landing; and the 54% rate measured on
13 holding across all 23.

The binding constraint is the 23 `off-target` rejections, and the honest state of
that lever is that **its acceptance test has not been run**. Everything measured
here scores bodies on golden. Whether a repaired body PASSES CORRESPONDENCE --
the gate that actually rejected it, and the only thing that would make it TRUSTED
-- is unmeasured, and is the next experiment worth running.

## Order to implement

F2 first (largest, no model calls, replicated on five designs), then F3 (makes
the rest safe), then F1 (largest per-requirement effect), then F6 (small, no
model calls, and it corrects the target the staging budget is spent on). F4
needs a higher-powered trial before it earns a place. F5 needs a trial at all.
