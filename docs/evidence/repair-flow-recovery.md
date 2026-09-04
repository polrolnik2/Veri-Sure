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

## Order to implement

F2 first (largest, no model calls, replicated on five designs), then F3 (makes
the rest safe), then F1 (largest per-requirement effect), then F6 (small, no
model calls, and it corrects the target the staging budget is spent on). F4
needs a higher-powered trial before it earns a place. F5 needs a trial at all.
