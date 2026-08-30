# Re-authoring the 43: over-strictness is real, and the cure has a price

*c1-i2c, 2026-08-30. Every number here is from artifacts in `docs/evidence/`;
nothing is projected.*

## Why this was run

The frozen 110 oracles decided against the **known-good** OpenCores i2c RTL read
**43 convictions of a correct design**. That is the largest carried risk in the
oracles-as-testbench plan: pointing a debug loop at RTL does not fix it, it just
asks the loop to "repair" a correct design toward 43 wrong demands.

The question: does re-authoring those 43 under the current [O] ordering --
staging before the gates every round, the `_unreached` gate, correspondence,
liveness, three verification rounds -- make them stop convicting the control?

**Method.** The real `run_oracle_stage`, unmodified, driven through a blocking
rendezvous port (`model_io.AgentPort`) with local Sonnet 5 agents standing in for
the gateway model. 240 calls, 592s of stage time once every answer was banked.
Inputs are c1-i2c's own frozen artifacts; normalization is NOT regenerated,
because re-rolling it renames the requirements and the 43 lose their labels.

**The control never gates.** `control_source=None`. No agent in the run saw the
golden RTL, directly or through a verdict. It is the held-out scoring instrument
and nothing else.

## What happened to the 43

| outcome | n | |
|---|---|---|
| **converged** -- golden now passes | 15 | 35% |
| **no check survived the gates** (`ORACLE_INVALID`) | 19 | 44% |
| unchanged -- golden still convicted | 6 | 14% |
| **went silent** -- check exists, decides nothing | 3 | 7% |

"Went silent" is counted separately from "converged" on purpose. A check that
stops deciding also stops convicting, and folding the two together is exactly
the accounting error that lets un-exercising a requirement read as progress.

So: **21 of 43 still decide anything at all** (down from 43), and among those,
over-strictness is 6/21 = 29% (was 100%).

### Correction: four requirements minted stimulus, and the first scoring missed it

`add_stimulus` fired on REQ-0028, REQ-0089, REQ-0118 and REQ-0124, minting
TP-0318..TP-0325. The stage was handed a FILTERED testplan (106 of c1's 331
entries), so `next_index` restarted inside a range c1 had already used and every
staged id **collided with a real testpoint**. The first scoring silently read the
colliding traces, because the scorer guards a MISSING trace and not a
wrong-but-present one.

Re-rendering the staged testpoints against the golden RTL and re-deciding those
four requirements against their own traces changes **three of the 24 outcomes**:
REQ-0089 and REQ-0118 go silent -> converged, REQ-0028 goes silent -> unchanged.
The table above is the corrected count; the first pass reported 13 / 6 / 5. Two
of REQ-0124's three traces (TP-0324, TP-0325) were never recovered, so that one
requirement's golden verdict still rests on a collided trace.

The override has to be applied **per oracle**, not globally: REQ-0109 is a frozen
oracle that legitimately names one of the colliding ids, and a global swap would
hand it the wrong evidence. None of the four requirements that minted stimulus is
discriminating or inverted in either arm, so the separation figures below are
untouched by this correction.

## The 19 rejections: how many were the author's to fix?

`ORACLE_INVALID` is the correspondence reviewer refusing a check. It is not by
itself evidence that a better author would have converged -- so each of the 19
grounds was read against the requirement's own text, its normalized activation,
and the contract's 17-port list. **Nine are the author's failure. Ten are not.**

**Justified (9).** All nine decide directly on a port the DUT has
(`observed_via[].through_req` empty), and each defect has a one-line repair:

| req | the check's defect |
|---|---|
| REQ-0006 | trigger equates `din=1 & scl_i=1 & sda_i=0` with "expects SDA high", never inspecting `sda_oen` -- **which is a port** |
| REQ-0026 | `cmd_ack` on the same row that first satisfies the close; reviewer: "the window's OPEN and CLOSE are the right shape" |
| REQ-0030 | window closes on reset and `strong=True` converts that into a violation; the text never mentions reset |
| REQ-0063 | `al` is sticky, so a *previous* command's `al` closes this STOP's window instantly |
| REQ-0067 | tautology -- "can never return False at all"; opens on `scl_oen` rise, closes on its fall, asserts `scl_oen==1` between |
| REQ-0071 | closes on `al`/`cmd_ack` rather than on the WRITE high phase's own end |
| REQ-0093 | reset asserted inside the `ena==0` window counted as an FSM-timing violation |
| REQ-0095 | `any(sda_i==0)` -- one raw sample demands `al`, exactly the glitch the filter must suppress |
| REQ-0097 | same: raw `sda_i` rise where "filtered STOP" was meant |

So the reachable ceiling for a stronger author on this set is **24 + 9 = 33 of
43 (77%)**, not 43.

**Not justified (10)**, in three classes:

* **Not a falsifiable obligation (3).** REQ-0025 ("The cmd[3:0] input is the
  bit-level command provided by the byte-level controller") is a port definition
  with `activation.inputs`, `opens_on` and `until` all empty. REQ-0086 ("The
  slave_wait condition indicates that another bus participant is holding SCL
  low") is descriptive -- the reviewer says outright that the sentence which
  forbids the pulse belongs to REQ-0087. REQ-0080 ("The controller disables
  arbitration checking") lost its antecedent in extraction; the reviewer had to
  go back to the spec paragraph the `spec_span` was quoted from to find it.
* **The subject is an internal signal with no port (5).** REQ-0008, REQ-0021,
  REQ-0022, REQ-0043, REQ-0046 -- timing counter, clock-divider counter, filter
  counter, `sSCL`/`sSDA`. None appear in the 17-port contract, each is routed
  through a sibling's port, and in four the reviewer's ground is precisely that
  the proxy decides the sibling: REQ-0022's is that "nothing distinguishes 'dout
  froze because the input filter counter was held reset' (REQ-0022) from 'dout
  froze [for REQ-0020's reason]'." Unfixable by authoring.
* **The `cmd` encoding was invented (2).** REQ-0066 and REQ-0121 -- see the
  section on the defect re-authoring cannot fix.

### What actually decided a rejection, and a statistic withdrawn

The correspondence prompt offers five rejection grounds -- convicts on missing
evidence, triggers on the wrong situation, asserts the trigger instead of the
effect, convicts on unmentioned ports, convicts outside the claim's scope. Every
one asks whether the CHECK fits the REQUIREMENT. **None asks whether the
requirement states an obligation at all**, and the prompt separately FORBIDS the
ground that would catch an internal subject -- *"'It would need to observe
&lt;internal signal&gt;' is NEVER a valid rejection"* -- for the documented reason
that normalization once called 27 of 77 requirements unobservable by reading
their mechanism.

So a hollow requirement has exactly one way to be caught, and the prompt marks it
as unique: *"has the check silently become THAT requirement's check? ... That is
a NO, and it is a rejection only you can make."* It is answerable only from the
`route_requirements` block, which `correspondence._through()` builds from
`normalized.observed_via[].through_req`. No `through_req`, no block, no ground.

The four definitional requirements in the 43 split on exactly that:

| req | routes in normalization | route block | verdicts r1-r3 | final |
|---|---|---|---|---|
| REQ-0028 | none at all | absent | O O O | TRUSTED |
| REQ-0020 | 5 routes, every `through_req` empty | absent | O R O | TRUSTED |
| REQ-0025 | -> REQ-0104 / REQ-0016 / REQ-0056 | present | R O R | ORACLE_INVALID |
| REQ-0086 | -> REQ-0087 | present | R R R | ORACLE_INVALID |

REQ-0086's recorded ground is that instruction firing verbatim: "the sentence
that actually forbids the pulse belongs to REQ-0087." The block decides whether a
ground EXISTS; the flip rate below decides whether it fires in the round that
counts.

**A statistic is withdrawn here.** This write-up previously read "7 of 11 routed
requirements were rejected (64%) against 12 of 32 direct (38%)". That was
confounded by a defect in the driver, not a property of the pipeline:
`correspondence.review` builds its sibling map from the `requirements` dict it is
handed, and `docs/evidence/drive.py` filters that list to the 43 -- so a
`through_req` pointing outside the 43 resolved to nothing and `_through` omitted
the block silently. Seven of the eleven routed requirements lost it that way
(REQ-0008, 0042, 0043, 0044, 0046, 0082, 0089, all pointing at REQ-0051 / 0053 /
0047 / 0096, none of which is in the 43). This is the same class of error as the
filtered testplan above: an input the stage indexes by uid, filtered.

| | TRUSTED | ORACLE_INVALID | reject rate |
|---|---|---|---|
| route block reached the reviewer | 0 | 4 | **100%** |
| no route block | 24 | 15 | 38% |
| ... of which the driver suppressed | 4 | 3 | 43% |

The seven suppressed reject at 43%, indistinguishable from the 38% base rate,
which is consistent with the block being the active ingredient rather than the
routing itself.

**The fix is not a better author.** A definitional requirement cannot be repaired
into a check, and the gate is not permitted to ask about it. REQ-0020 and
REQ-0028 are TRUSTED and convicting golden because nothing in the reviewer's
remit could reject them; REQ-0025 and REQ-0086 were rejected only because
normalization happened to leave a sibling pointer. Both outcomes are wrong and
both come from the same hole: nothing between S1 and the frozen set asks whether
a requirement states a falsifiable obligation.

This classification reads each rejection's **stated ground** and checks it for
internal consistency against the requirement text and the port list. It does not
re-derive whether each alleged false path actually occurs in the golden trace;
that is a separate pass.

## The loop judges three times and repairs twice

`oracles_stage.py:1146` breaks before the re-ask on the final round:

```python
for rounds in range(1, verifications + 1):     # verifications = 3
    ...review -> verify -> reject...
    if rounds == verifications:
        break                                   # the last round JUDGES, never REPAIRS
    ...re-ask the author...
```

The IO record confirms it: 37 re-asks at round 1, 24 at round 2, and
**zero at round 3**. So the objection recorded against every one of the 19
rejections -- including the nine with a one-line repair -- is the one the author
was never given a chance to answer.

That would be defensible on its own; somebody has to judge last. This is not:
**the reviewer agrees with itself 67% of the time on a byte-identical prompt.**
Of 42 adjacent round-pairs whose prompt was unchanged, 14 changed verdict.

```
verdict pattern across the 3 rounds (O = passes correspondence, R = rejected)
  OOO  9    ORR  6    RRO  6    ROO  5
  RRR  5    OOR  5    ORO  4    ROR  3
```

* **8 of the 19 rejections passed correspondence at round 2 and died at round 3**
  -- REQ-0008, 0025, 0046, 0063, 0066, 0093, 0095, 0097. Seven of the eight on a
  byte-identical prompt. REQ-0093 flipped twice on the same prompt: R -> O -> R.
* It cuts both ways. REQ-0020 and REQ-0089 were rejected on an identical prompt
  at round 2 and rescued at round 3; they are TRUSTED because the coin landed the
  other way on the last throw. Ten TRUSTED checks were rejected in some round.
* Only the five `RRR` are unambiguous rejections.

The genuinely stuck ones look different: the objection RECURS. REQ-0021 (3
rounds, same ground), REQ-0080 (5 objections), REQ-0086 (4) -- all three in the
not-justified bucket. For all nine justified rejections the objection MOVED each
round, a different and narrower ground; REQ-0006 burned all three rounds on three
distinct grounds and was still descending when the loop stopped.

### 14 of the 19 rejections had ALREADY passed correspondence

Only five were never accepted in any round -- REQ-0006, 0022, 0043, 0080, 0086,
the `RRR` group. The other fourteen passed the reviewer and were then rejected by
a later round, and **six of them are frozen holding the byte-identical check that
had passed**: REQ-0008, 0021, 0025, 0046, 0063, 0093. Nothing about those checks
changed; only the draw did.

`correspondence.review(list(held.values()), ...)` re-reviews EVERY held oracle
every round. There is no "already accepted" filter, and the disposition is taken
from the last round's `rejected` alone.

### So what if it stopped at the first accepted attempt?

`docs/evidence/repair_policy.py` reconstructs the check as it stood at each round
-- the correspondence prompt carries `{"clause", "source"}` -- and decides four
policies against both held-out arms. It is validated by `last` reproducing the
frozen result exactly (15 / 6 / 22).

| policy | kept | calls | passes | CONVICTS golden | silent | disc | inv | sep |
|---|---|---|---|---|---|---|---|---|
| **last** (what the run did) | 24 | 129 | 15 | **6** | 22 | 3 | 3 | **+0** |
| majority of 3 | 23 | 129 | 11 | 9 | 23 | 2 | 3 | -1 |
| **latch on first pass** | 38 | **73** | 14 | **18** | 11 | 2 | 3 | -1 |
| unanimous (any R is fatal) | 9 | 129 | 4 | 3 | 36 | 0 | 1 | -1 |

Latching is 43% cheaper and nearly halves the silent count -- and **triples the
false convictions, 6 to 18**. Conviction rate among checks that decide: last 29%,
majority 45%, latch 56%. The reviewer never sees the control, so its later
rejections are independent evidence, and they correlate with over-strictness
strongly enough that re-reviewing an already-accepted check is doing real
filtering work rather than burning budget.

**A recommendation made earlier in this document is withdrawn.** It argued for
taking the verdict as a majority over the rounds, on the reasoning that a 67%
self-agreement rate makes the majority the better estimator. Measured, majority
is WORSE than the last-verdict rule it would replace -- 9 golden convictions
against 6, and separation -1 against +0. The reasoning ignored that the draws are
not independent samples of one truth: a later round sees a repaired check, so
later rejections carry more information than earlier ones, and averaging discards
that.

Separation differences of +-1 on 43 requirements are noise and none of these
policies is distinguishable on it. The 6-vs-18 conviction gap is not.

### The break is deliberate, and this write-up called it a defect

An earlier draft of this section proposed "fixing the round-3 asymmetry" by
moving the `break` past the re-ask. That was wrong twice over.

**It is not an oversight.** `repair_attempts`' own docstring diagnoses it, and
the parameter was renamed for exactly this reason:

> REPAIR ATTEMPTS an oracle gets, not verification rounds. It was
> `max_rounds: int = 2` and that name is why this sat wrong: the loop breaks at
> `rounds == max_rounds` BEFORE re-asking, **because the last round has nothing
> left to verify its answer**, so 2 rounds bought exactly ONE attempt.

`verifications = repair_attempts + 1`, so `repair_attempts=2` delivers two repair
attempts and a final unanswerable judgment BY DESIGN. Describing "three judgments,
two repairs" as a defect was describing the parameter working as documented.

**And the measurement above argues for the existing design, not against it.**
The alternative to a terminal final-round rejection is keeping the last version
that passed -- which selects the same set as `latch` (every requirement with an
`O` anywhere; the two policies differ only in which accepted version they freeze,
and only for the four `ORO` patterns). That is 18 golden convictions against 6.
The reason the break looks harsh and is not: **a later rejection carries more
information than an earlier acceptance, because the later round is judging a
repaired check.** Averaging the rounds, or trusting the first accept, both throw
that ordering away.

**What is genuinely untested** is the thing the docstring worries about --
accepting an unverified final-round repair. No round-3 repairs exist in this run,
so there is nothing to score. It is unmeasured, not refuted, and measuring it
means a run with `repair_attempts=3` to compare against this one at 2.

**Confirmed against production.** Neither `integration.py:621` nor
`refmodel/compose.py:456` passes `repair_attempts`, so both take the default of
2, and `drive.py`'s default matches. Everything measured in this section is the
pipeline's own behaviour at its own settings, not an artifact of the driver.

### A review clears a VERSION; the loop spends ROUNDS

The correspondence reviewer is STATELESS: its prompt carries `system`,
`specification`, `interface`, `requirement`, `normalized` and `oracle` and
nothing else -- no previous answer, no prior objection, unlike the author's,
which carries both `previous_answer` and `gate_failures`. Every round is an
independent look, and a look at a REPAIRED check bears no relation to the looks
before it.

**This does not contradict "three rounds" above, and the two are easy to read as
if it did.** Every requirement IS reviewed three times -- 129 responses, 43 x 3.
What moves is the denominator: a repair replaces the thing being reviewed, so a
check repaired at both rounds gets

    round 1   review version A  -> reject -> repair -> version B
    round 2   review version B  -> reject -> repair -> version C
    round 3   review version C  -> verdict, and no repair is possible

three reviews of the REQUIREMENT and exactly one of version C, which is what
ships. A check never repaired gets all three reviews of the version that ships.
The arithmetic ties out: 37 re-asked at round 1 of which 24 produced a genuinely
new source, 24 re-asked at round 2 of which 20 did, and 0 at round 3. The 4-check
gap at round 2 is replacements that were REJECTED -- "the replacement decided
nothing on any of its testpoint(s); the previous stands" -- so those kept their
round-2 source and got two looks at it.

The loop does not account for that. It spends rounds, so how many reviews a
check's FINAL form receives depends on how late it was last repaired:

| reviews of the final source | TRUSTED | ORACLE_INVALID |
|---|---|---|
| **1** | **12** | 8 |
| 2 | 6 | 5 |
| 3 | 6 | 6 |

**20 of 43 checks had their final form reviewed exactly once, and 12 of those
shipped TRUSTED on that single draw** -- against a reviewer measured at 67%
self-agreement.

**And that costs nothing measurable here; on this data it looks beneficial.**
Of the 24 checks that shipped, scored against golden by how often the shipping
version had been reviewed:

| looks at final form | n | passes | CONVICTS golden | convict rate |
|---|---|---|---|---|
| 1 | 12 | 10 | 1 | **8%** |
| 2 | 6 | 3 | 2 | 33% |
| 3 | 6 | 2 | 3 | **50%** |

The confound is exact rather than statistical: `looks = 3 - (accepted repairs)`,
by construction, so "reviewed three times" IS "never repaired". The variable is
repair count wearing review count's clothes, and what the table actually says is
that a check nothing ever objected to is likelier to convict a correct design --
which is the over-strictness the repair rounds exist to relax. It cannot be read
as evidence about reviewing.

So the argument for clearing a VERSION rather than a requirement is a COHERENCE
one and not a quality one: a clearance that refers to code which no longer exists
states nothing, whatever its effect on the outcome turns out to be. An earlier
draft of this section claimed the under-reviewed checks were the risky ones. That
claim is withdrawn -- it was an inference, the measurement contradicts it, and
n = 12 / 6 / 6 with one to three convictions per cell is too small to support the
reverse claim either.

Worked, on two requirements carrying the SAME defect -- normalization's
`until: [{cmd_ack: 1}, {al: 1}]`, where `al` is read as a level, so a stale or
unrelated pulse slams the window shut before the design has acted:

* **REQ-0063** was never repaired, so all three rounds reviewed the identical
  source `c58824ff`. Verdicts pass, pass, REJECT, and the objection names it
  exactly -- "it fires on any row where al happens to read 1 ... That lets the
  window close instantly, before the STOP sequence's own release phase can run".
  One catch in three looks.
* **REQ-0055** was repaired after round 1, so rounds 2 and 3 both reviewed
  `b0b7d242`, and both passed. Zero catches in two looks -- and it ships TRUSTED,
  convicting golden on TP-0133, where the window opens at edge 0, `al` pulses at
  edge 7, and the design's correct START lands at edges 28 and 38, outside the
  three-row window.

Round 1's objection on REQ-0055 was a different and entirely correct finding --
one undifferentiated window shared across START/STOP/READ/WRITE, which the author
fixed by branching per command. Nothing was masked or carried between rounds; the
revised check simply drew twice and lost twice.

**The rule this argues for:** a review clears a VERSION of a check, not the
requirement, so a rewritten check should not inherit its predecessor's
clearances, and the budget should spend reviews-of-the-current-source rather than
rounds. Not built -- it changes what `verifications` means and the
per-requirement call budget with it, and `docs/evidence/repair_policy.py` can
simulate it offline from the recorded rounds before anything is wired.

## The six that still convict golden are the same defect class

| req | subject of the requirement | |
|---|---|---|
| REQ-0007 | "holding the **timing counter**" | internal |
| REQ-0020 | "The ena input **is the** core enable signal that gates normal timing and input filtering" | definition; both mechanisms internal |
| REQ-0028 | "al **indicates that** the controller has detected an arbitration loss" | definition |
| REQ-0055 | "asserts the **internal sda_chk** arbitration-check signal" | the text says "internal" itself |
| REQ-0087 | "**slave_wait** ... pauses the **timing counter** ... prevents the FSM from advancing" | internal |
| REQ-0057 | "The START sequence releases the SDA open-drain output enable" | the only clean one |

Five of the six are the internal-mechanism / definition class -- identical in kind
to the ten rejected above. Same defect, opposite outcome: rejected means coverage
falls, survived means golden gets convicted, and which one happens is decided by
the routing pointer and the flip, not by the requirement.

Two independent instrument signals say the check is at fault rather than the
design. **The witness fails REQ-0020 and REQ-0057 too** (`instrument_notes`:
REQ-0020 "fails it at edge 25 -- scl_oen changed from 1 to 0 at edge 25") -- a
check that convicts golden RTL AND the known-executable Python witness is
convicting everything. And REQ-0057 carries an `idle_match` note: "judged at edge
2, before any of al, cmd_ack, sda_oen had moved off its reset value -- and
cmd_ack, sda_oen moves later in this same trace, so the scenario had not happened
yet." REQ-0028's complaint -- "al dropped before reset cleared it; the
arbitration-lost indication is not sticky" -- is an obligation its text never
states.

**So none of the six is a clean statement about the design.** "Over-strictness
43 -> 6" should be read as 43 -> 6 of which zero survive scrutiny, bought by 22 of
43 requirements ceasing to decide anything.

## How many of these requirements should have been asserted at all?

Given that no gate asks, the size of the question is worth measuring. **The bar:
a determinate CONDITION and a determinate EFFECT that lands on a port the
contract declares.** Four ways to miss it -- DEFINITION (copular, nothing to
falsify), INTERNAL (the effect named is not a declared port), SCOPE (a role or
capability summary with no determinate effect), HEDGED (the effect qualified into
indeterminacy: "at the appropriate timing phases").

Of the 43, **32 have no `through_req`** -- the population the route-block ground
cannot reach. Hand-labelled against that bar, **20 should be asserted and 12
should not**. A text-only rule set in `docs/evidence/assertable.py` reproduces
the hand labels on 29 of 32 (91%); its three misses are sentence conjunctions and
vocabulary, so it is a screen rather than an oracle.

What the split predicts, against golden:

| | passes | CONVICTS golden | silent |
|---|---|---|---|
| **should be asserted** (20) | 9 | **1** | 10 |
| **should NOT be asserted** (12) | 3 | **5** | 4 |

**42% against 5%, an eight-fold difference.** Five of the six requirements still
convicting golden -- REQ-0007, REQ-0020, REQ-0028, REQ-0055, REQ-0087 -- are
requirements that should never have become checks. Only REQ-0057 is a real
obligation convicting a correct design, and it carries the `idle_match` note.

And the cost of dropping the twelve is **nothing**:

| among the 32 | discriminating | inverted | separation |
|---|---|---|---|
| as frozen | REQ-0002, REQ-0117 | REQ-0007, REQ-0055, REQ-0087 | **-1** |
| dropping the 12 | REQ-0002, REQ-0117 | none | **+2** |

Every inverted check in this population -- golden convicted, candidate passed,
the actively misleading kind -- is one that should not have been asserted. Every
discriminating one is a real obligation. Dropping the twelve removes all three
inversions and five of the six false convictions, and loses no discriminating
power at all.

**Scaled to the design.** 89 of c1-i2c's 122 normalized requirements have no
`through_req`. The rules call **29 of the 89 (33%) non-assertable** -- 15
INTERNAL, 5 SCOPE, 5 with no obligation verb, 2 HEDGED, 2 DEFINITION -- and the
rules run slightly conservative against the hand labels, so the true figure is at
least that. Roughly a quarter of every requirement in the design is being turned
into a check that cannot be a fair test of it.

### The gate, built: correspondence asks the prior question

Assertability is now a rejection ground in the correspondence reviewer rather
than a measurement in this document. Section `3b. THE PRIOR QUESTION` asks it
before the fit question, because "for every False path there must be a sentence
condemning it" has nothing to run on when the requirement condemns nothing:

> CAN YOU DESCRIBE A DESIGN THAT THIS SENTENCE, IN ITS OWN WORDS, CALLS WRONG?

Four things make it a different gate from the five that were already there.

**It accuses the specification, not the check.** `Review.states_an_obligation`
is a separate field from `tests_the_requirement` and `rejects()` gives it
priority when a reply says both, because they route to different parties:
`not-assertable:` maps to a new **`NOT_ASSERTABLE`** verdict whose
`ROUTE` is *return to spec authoring*, beside `UNOBSERVABLE`. Folding it into
`off-target:` would have sent a repair round to the author.

**It never costs a repair round.** `verify_one` returns `may_quote=False` for
this rejection, so the requirement is recorded and not re-asked. Nothing an
author writes can add an obligation to a sentence that has none, and re-asking
buys the same invention back at the price of a call.

**The author's own check is the evidence, which is why this belongs here rather
than in a pre-gate on the text.** The author cannot decline: handed a definition
it produces the most plausible check in the neighbourhood -- usually an
obligation borrowed from a sibling -- and that check is well-formed, satisfiable
and confident. The reviewer is the only reader holding the sentence and the code
side by side, so it is the only one positioned to see the invention.

**The boundary is the whole risk, and it is pinned.** Section 7 forbids "it
would need to observe an internal signal" as a rejection, because normalization
once called 27 of 77 requirements unobservable by reading their mechanism. A
"states no obligation" ground could reintroduce that failure exactly, so the
prompt carries a contrast pair and a test asserts both survive: REQ-0093
("reloads the internal counter cnt ... and normal command-FSM bit timing does not
progress") names an invisible counter and IS an obligation, because a design
whose outputs advanced while `ena` was low is condemned by its words; REQ-0086
("the slave_wait condition indicates that another bus participant is holding
SCL low") names an invisible signal and is not, because it says only what the
condition means. The question is never "can this be observed" but "does this
sentence forbid anything".

`OracleSet.rates()` reports `NOT_ASSERTABLE: None` when correspondence is off,
under the rule the summary already applies to `VACUOUS` and `ORACLE_INVALID`: a
zero from a gate that did not run reads exactly like a clean bill.

### Measured live, on 20 requirements -- and it overturns the count above

The ground was put in front of a live reviewer on c1-i2c's own requirements,
with the real oracle each one got. `docs/evidence/gate3b-live.json` carries every
answer.

| | gate says NOT_ASSERTABLE | gate lets it through |
|---|---|---|
| copular definitions (4) -- **3 of them CONFOUNDED, see below** | 4 | 0 |
| requirements hand-labelled assertable (10) | **0** | 10 |
| requirements hand-labelled NOT assertable (6) | **0** | 6 |

**THE POSITIVE CONTROLS ARE MOSTLY CIRCULAR, and the worker that answered them
said so before I noticed.** REQ-0025, REQ-0028 and REQ-0086 appear VERBATIM in
section 3b as its worked examples of a definition and of a no-obligation
sentence. Asking the reviewer to classify sentences its own instructions quote as
canonical things to reject measures nothing. I mined the test set for the
prompt's examples and then tested on the test set.

**Only REQ-0020 is held out**, and it did fire, on reasoning that does not lean
on the examples -- "the sentence supplies neither a concrete trigger ... nor a
concrete effect ... no hold, no suppressed pulse, nothing a trace could
contradict". So the true-positive evidence is **1 of 1, not 4 of 4**, and c1-i2c
has no further held-out definition to offer: those four are the only copular,
obligation-verb-free sentences in all 127 of its requirements.

The false-positive result is unaffected -- none of the 10 assertable
requirements appears in the prompt, and none was rejected.

A real measurement needs definitions the prompt has never seen. Three exist in
other runs: `a2-i2c` REQ-0020 ("The output al is the arbitration-lost
indicator."), `a2-i2c` REQ-0038, and `d1-i2c` REQ-0006 ("The ena port is the core
enable signal.").

The third row below stands on its own -- it is a result against this document
rather than against the gate, and nothing in it is confounded.

**Two riders on the one held-out case, one weakening it and one worth keeping.**

REQ-0020's answer reasons by ANALOGY to the prompt's examples -- "closely
paralleling the briefing's own 'no obligation' examples". Its sentence is not in
the prompt, so this is not the circularity above; but it is generalisation from
given examples rather than an independent reading, which is a weaker thing to
have measured than the bare 1-of-1 suggests.

Against that: REQ-0020 was answered against the OLD section 3b -- no two-leg bar,
no borrowing rule, both added afterwards in the commit that followed -- and the
reviewer raised BOTH unprompted. It rejected for want of "a concrete trigger-value
or port-level effect", which is the second leg; and it flagged the check as
testing "obligations ... drawn from a different part of the spec (Implementation
Detail #2 / the processing-flow paragraph), not from REQ-0020's own words", which
is the borrowing rule. Those two additions codify what a careful reader already
does, which is the claim that commit made from the 15-of-16 port-naming count,
supported here on a second and independent line.

**And an observation about S1 rather than about the gate.** REQ-0020's
`spec_span` "stops just before the sentence that actually supplies the
trigger+effect". Compare REQ-0080, where the span DID reach the reset paragraph
and the reviewer recovered the antecedent from it. The same extraction step
decides, by where it cuts, whether a requirement is repairable from its own
provenance or not -- and nothing measures that.

**THE HAND LABELS WERE WRONG, and the reviewer's readings are better.** On all
six it named a specific design the sentence condemns, which is exactly the test
section 3b poses:

* REQ-0001 -- "a design that receives a supported command and never moves
  scl_oen/sda_oen from their released level, or that ever drives scl_o/sda_o
  non-zero, is condemned by these words". Called a SCOPE statement above; it is
  not.
* REQ-0055 -- "sda_chk is internal and outside the port list, so no check can
  speak to it, **but the enable-driving half of the sentence is a testable
  claim**". The boundary rule applied correctly to a mixed sentence, where this
  document had rejected the whole for one internal conjunct.
* REQ-0080 -- "the bare text has no trigger of its own, **but its spec_span sits
  squarely inside the reset paragraph**". It recovered the antecedent from
  evidence the hand pass did not use.
* REQ-0016, REQ-0026, REQ-0095 -- same shape.

So the bar in this document ("a determinate condition and a determinate effect
landing on a declared port") is stricter than 3b's ("can you describe a design
this sentence calls wrong"), and 3b's is the right one, because it is the test
that maps onto whether a check can exist at all.

**WITHDRAWN: "20 should be asserted and 12 should not", and the 33%-of-89
extrapolation drawn from it.** The defensible class is narrower and cleaner --
the copular definition, which states what something IS or MEANS:

```
REQ-0025  "The cmd[3:0] input is the bit-level command provided by the
           byte-level controller."
REQ-0028  "The arbitration-lost output al indicates that the controller has
           detected an arbitration loss."
REQ-0086  "The slave_wait condition indicates that another bus participant is
           holding the SCL line low."
REQ-0020  "The ena input is the core enable signal that gates normal timing and
           input filtering operation."
```

Four of the 43, and the reviewer's ground on each is the same sentence: "both
trigger and effect are absent". On REQ-0025 and REQ-0086 it goes further and
names the sibling whose obligation the check actually borrowed -- REQ-0104 /
REQ-0016, and REQ-0087.

**What it is worth, stated at the size the evidence supports.** REQ-0020 and
REQ-0028 are TRUSTED today and both convict golden, so the gate removes **2 of
the 6 remaining false convictions** -- not the five this document previously
projected. REQ-0025 and REQ-0086 were already ORACLE_INVALID; the gate re-routes
them from "the author's check is off-target" to "the specification states no
obligation", which ends them instead of spending a repair round on a party that
cannot act. Of the other four golden convictions, REQ-0055 was tested and let
through, and REQ-0007, REQ-0057 and REQ-0087 were not tested.

**Caveat on the instrument.** The reviewer here is the same model family as the
author whose work it judges, and the hand labels it overturned are the same
author's too. What this measures is whether the PROMPT elicits the judgement,
not whether an independent party agrees.

## The whole set, both arms

Splicing the re-authored 43 back into the frozen 110 -- a requirement whose check
was rejected contributes nothing, which is the honest representation of a lost
check:

| | CONFORMS | VIOLATES | UNDECIDED | coverage | pass rate |
|---|---|---|---|---|---|
| BEFORE golden | 44 | 43 | 23 | 79% | 61% |
| BEFORE candidate | 42 | 45 | 23 | 79% | 59% |
| **AFTER golden** | **59** | **6** | **45** | **59%** | **95%** |
| **AFTER candidate** | **48** | **17** | **45** | **59%** | **85%** |

**Over-strictness fell 43 -> 6. Coverage fell 79% -> 59%.** Those are the same
event seen from two sides, and it is #99 measured on a labelled set: over-
strictness and vacuity are one expressiveness defect with two signs, so pressing
on one moves the other.

## The number that decides whether this was worth doing

Passing golden is half a measurement -- a check that abstains everywhere passes
golden too. The instrument is better only if it still tells the two designs
apart.

| | discriminating | inverted | separation |
|---|---|---|---|
| BEFORE | 9 | 6 | **+3** |
| AFTER | 12 | 3 | **+9** |

**Separation tripled**, and it attributes cleanly:

* all 9 original discriminating checks were **retained**, none lost;
* the 3 gained -- REQ-0002, REQ-0042, REQ-0117 -- are **all from the re-authored
  43**;
* 5 of the 6 inverted were **fixed** (REQ-0016, 0073, 0080, 0093, 0107); REQ-0007
  remains;
* but re-authoring also **introduced 2 new inverted** checks, REQ-0055 and
  REQ-0087. The move is net +6, not monotone, and a report that hid the two
  regressions would be describing a different run.

The golden/candidate pass-rate gap also widened from **2 points to 10**, which
materially changes the §4 gate's prospects (see below).

**Provenance of the candidate arm.** The candidate traces were reused from
`rtl_cand2` and could not afterwards be regenerated: none of the five candidate
RTLs in the benchmark reproduces them, because `rtl_probe.py` rescales every
input step to `hold=60` and the edge counts do not match (`rtl_golden2` TP-0000
is 753 edges, `rtl_cand2` 498, a raw re-run 268). What the arm's identity IS
pinned by is its BEFORE row, which reproduces the project's standing baseline
exactly -- 42 / 45 / 23, against golden's 44 / 43 / 23. So both rows of the
separation table are measured on the same two trace sets and the delta is
apples-to-apples; what is not established is which source file `rtl_cand2` was
built from, and no conclusion here rests on that.

## What this does and does not license

**Does:** the [O] ordering plus correspondence is a real instrument improvement.
34 of 43 checks were rejected in round one and the gates caught genuine defects
-- an unlicensed `never(cmd_ack==1)` conjunct on a port its requirement never
mentions; a window opened on a raw `sda_i` edge rather than the spec's *filtered*
START, which would convict a design for correctly filtering a glitch.

**Does not:** it does not license shipping the coverage number. 22 of 43
requirements ended with nothing that decides. The pipeline got more precise by
becoming quieter, and on 19 of them by giving up entirely.

**§4's two-metric gate is vindicated as a design even as it fails this set.**
Pass rate alone would read 95% on golden and look excellent; coverage at 59%
is what stops that from being reported as success. Gating on both is what makes
the vacuous accept safe, and this run is the case that demonstrates it.

**§140 revisited.** The pass-rate gate previously had a 2-point window between
golden (61%) and candidate (59%) -- unusable. It is now 10 points (95% vs 85%).
Still not somewhere to put a fixed threshold without more designs, but a relative
ratchet is now viable where it was not.

## The defect re-authoring provably cannot fix

The specification never states `cmd`'s numeric encoding. It names START/STOP/
READ/WRITE, says the FSM "decodes `cmd`", and gives no value; `contract
["parameters"]` is empty; the design's `i2c_master_defines.v` (START=1, STOP=2,
WRITE=4, READ=8) is not part of the spec handed to the pipeline. Normalization
invented the numbers, inconsistently -- `cmd=1` is associated with all four
command names across different requirements, and six requirements gate on
`cmd=3`, which is not a legal one-hot code at all.

This run demonstrated that authoring cannot settle it. Three workers repairing
different checks reached three different conclusions about the same field: two
triangulated the correct encoding from sibling requirements, one "fixed" a check
by re-gating it to `cmd==3 (WRITE)`. The information needed to decide is not in
the material any of them was given.

Two requirements among the 43 have a pinned `cmd` that flatly contradicts their
own text -- REQ-0066 (text READ, `cmd=4` = WRITE) and REQ-0121 (text WRITE,
`cmd=1` = START) -- and both ended `ORACLE_INVALID`, with the correspondence
reviewer naming the encoding as the ground in each. Every other pinned `cmd` in
the 43 is self-consistent with its requirement's text (REQ-0063 STOP=2,
REQ-0067 READ=8, REQ-0071/0095 WRITE=4), so within this set the error is
sporadic rather than systematic. REQ-0006 and REQ-0030 pin `cmd=1` while their
text mentions STOP, but there the STOP is the *detected bus condition* during an
active command, not the issued command, so `cmd=1` is a legal narrowing and not
an encoding error; their rejections rest on other grounds. The gate catching the
two real ones is the right direction to fail in, and the price is the
requirement rather than a wrong verdict.

**The fix is upstream:** normalization must not mint a numeric code for a field
the specification does not enumerate -- express the activation symbolically, or
emit `UNOBSERVABLE` naming the omission. A cheap interim guard: reject any
non-one-hot literal for a one-hot command field. `cmd=3` dies to that alone.

## Reproduce

The scripts are committed beside this write-up, in `docs/evidence/`:

```
docs/evidence/drive.py --name full43 --workers 24 --resume   # the stage
docs/evidence/score.py full43                                # vs golden (uncorrected)
docs/evidence/separation.py                                  # both arms (uncorrected)

docs/evidence/restage.py     # re-render the 8 staged testpoints against golden
docs/evidence/rescore.py     # the 43, with the staged testpoints' REAL traces
docs/evidence/resep.py       # the whole-set fold, staged traces applied PER ORACLE
docs/evidence/gate_audit.py  # re-asks per round, reviewer self-agreement,
                             # and whether the route block reached the reviewer
docs/evidence/assertable.py  # the assertability bar, scored against hand labels
docs/evidence/repair_policy.py # last / majority / latch / unanimous, scored on
                             # both arms; `last` reproduces the frozen result
```

`score.py` and `separation.py` are kept as the record of the first pass;
`rescore.py` and `resep.py` produce the corrected numbers reported above.

Three data files carry the results:

```
docs/evidence/reauthor43-oracles.json           the re-authored checks
docs/evidence/reauthor43-score-corrected.json   per-requirement outcome, with
                                                first_pass_outcome for the diff
docs/evidence/reauthor43-invalid-triage.json    the 19 rejections, classified,
                                                each with the reviewer's ground
```

They carry absolute paths to the scratchpad they were written for and to
`/home/user/runs/c1-i2c`; re-running them elsewhere means repointing `S`, `RUN`
and the rendezvous directory. They are committed as the RECORD of what produced
the numbers above, not as a turnkey harness.

`drive.py --resume` replays every banked answer by `(stage, round_)` and pays
only for what is missing. This run survived four interruptions -- a wall-clock timeout, a
deliberate restart to widen the fan-out, a usage-limit kill of all 20 workers,
and a container restart -- without re-paying for a single answer.
