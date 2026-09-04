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

### F1 -- route `_diagnose` to the repair author, with the right wording

**CONFIRMED. Largest per-requirement effect measured.**

*Defect.* `stage_unexercised` (`oracles_stage.py:~2243`) computes
`_diagnose(evidence)` per attempt and returns `(abandoned, record)`. `abandoned`
merges into a terminal disposition; `record` goes to the artifact. **Neither
writes `repairs`**, and `repairs` is the sole source of `issues` for
`oracle_gen.build_prompt`. On k1 the diagnosis was computed 107 times and shown
to nobody. 19 of the 25 ABANDONED ended on their ORIGINAL body, never repaired.

*The wording is load-bearing, not cosmetic.* What production records is
`"never reached in N attempt(s)"`. Its own evidence says the opposite: 78 of 107
attempts were diagnosed "the activation was driven and the check still saw
nothing". Independently confirmed here -- new gate-clean stimulus was generated
for 15 abstaining checks and **13 of 13 had their activation staged** (the
activation inputs hold for 18-24 rows) while every check still returned `None`.

*Measured*, 21 k1 requirements that never reached an author, liveness only:

| arm | live / 21 |
|---|---|
| baseline (no repair round) | 5 |
| **N** -- bare `"never reached in 3 attempt(s)"` | **0** |
| **A** -- + the diagnosis | **8** |

Paired: N-only 0, A-only 8, both 0 (sign test p ~ 0.008). The bare reason is
**worse than not asking**: 5 -> 0, because the author reads "never reached" as
"unassertable" and writes a check that abstains by construction (median source
320 chars vs 886 with the diagnosis; the agents' own summaries say
*"correctly return (None, None, ...) to indicate no testable requirement"*).

*Change.* Write `_diagnose(evidence)` into `repairs[uid]` phrased as
**"the activation was driven and the check saw nothing"**, never "never reached".

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

**CONFIRMED as a defect; the rule itself is arithmetic on it.**

*Defect.* Repair replaces the body unconditionally, and every re-authoring arm
measured here both gains and destroys:

| arm | gains | destroys |
|---|---|---|
| diagnosis (53) | +10 | -9 |
| evidence (53) | +8 | -4 |
| bare reason (21) | +0 | **-5** |

`oracles_stage.py:1218` already records this shape for REQ-0055.

*Change.* After a repair round keep whichever of {pre, post} is `live`. Costs
nothing and is what makes F1 and F4 safe to apply.

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

## Negative results

**Adding stimulus does not recover the abstaining checks.** For the 15
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
the rest safe), then F1 (largest per-requirement effect). F4 needs a
higher-powered trial before it earns a place. F5 needs a trial at all.
