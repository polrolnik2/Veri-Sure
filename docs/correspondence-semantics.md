# Semantic checks the correspondence gate could ask, and what it would cost

**Status: plan, unbuilt except where noted.** Written against `c1-i2c`
(127 requirements, 110 TRUSTED, 43 refuted by the known-good control, 5
VACUOUS). Every number here is from that run or from the repair experiment
over it; none is projected.

---

## 0. Two corrections this document rests on

**REQ-0015 is not a direction error.** It was recorded as one on the strength
of the live correspondence gate's own r2 prose -- *"It does not sample the
external line levels (scl_i/sda_i), but partial checks ... are considered ON
TARGET"* -- which is wrong about the code it was reviewing. The final check
asserts `eventually(w, scl_i == 1)` and `eventually(w, sda_i == 1)`: the
consequent, correctly. The direction reviewer named the antecedent and the
consequent accurately and passed it, and passing was right.

It is VACUOUS for a different reason, and the reason is a problem class in its
own right: the run drives `--idle-high scl_i --idle-high sda_i`, so *"eventually
the released line is high"* is true by construction. **The right consequent,
trivially satisfied by the stimulus's idle values.** No reader of two texts can
see that -- it is a fact about the stimulus configuration, and it belongs to
vacuity.

**Consequence for the direction question (`--question direction`, `dc9a3c9`):
it is untested, not refuted.** It flagged 0 of 10 on the smoke, but c1-i2c's
VACUOUS set may contain no direction errors at all, so the 0/5 recall measures
the label set rather than the detector. It needs a set with confirmed positives
before any claim is made about it -- see §3.

**The repair experiment completed** and is the evidence base for §4:
`benchmarks/repair_overstrict.py` on `gpt-5-mini` rewrote 40 of the 43
control-refuted checks from their requirements alone (2 unparseable, 1 rejected
for naming no declared port), then re-decided each against the control and the
model:

| | |
|---|---|
| control still refutes | 22 of 40 |
| control now satisfies | 18 |
| ...of which went quiet (stopped failing the model too) | 2 -- **not** wins |
| **genuine repairs** | **16** |

So a reader holding only the requirement and the check repaired **16 of 43**,
about 37%. That is the measured ceiling for text-only detection on this
population, and it is a floor on what a text-only *detector* could find, since
repairing is strictly harder than flagging.

---

## 1. D, E and F, as long-run items

Recorded verbatim from where they were proposed, with what changes once the
check declares its rejections. A and B (witness-as-gate, implementation panel)
and C (two independent authors) were rejected as circular: if an implementation
or a second same-author reading decides whether a check is valid, the check has
no independent authority and differential testing replaces the whole pipeline.
D, E and F all stay inside the specification.

**They are gated on one enabling change**, which is why they are long-run:
`OracleOutput` is `{reasoning, clause, source}` -- free Python, with nothing
declaring what the check asserts -- while `expectation` is free prose. A
`rejects` field, one entry per failing path, carrying
`{ports, when, condition, licensed_by}`, is what turns each of these from a
separate instrument into a query over structure.

### D. Anchor each failing condition to a spec span

Requirements already carry `spec_spans` with quoted source text. Require every
failing path to name the span licensing it, then verify the cited words are
actually in that span. Attacks the defect at authoring rather than detecting it
afterwards. Weak alone -- a span can be cited loosely -- but it makes the
licence visible. *With `rejects`:* `licensed_by` becomes the span reference,
checkable mechanically against the quoted text, no model call.

### E. Recover the requirement from the check

Show a reader only the check, never the requirement, and ask what requirement it
enforces. Compare the recovered text against the real one; surplus appears as
clauses in the recovery that are absent from the original. Purely textual, and
it cannot be gamed by topic-matching because the reader never sees the topic to
match to. *With `rejects`:* reading the declared rejections back as prose **is**
the recovered requirement, so there is no separate pass.

### F. Make the check generate its own counterexample, and let the spec adjudicate

A check's failing paths *define* the traces it rejects. Synthesise one, then ask
a spec-only reader: *"the requirement says X; this trace does Y; does X forbid
Y?"* If it does not, the rejection is surplus. **The one to back hardest**,
because the counterexample comes from the check itself rather than from any
design -- the property A and B lack -- and it produces the actionable artifact a
repair prompt needs: the specific behaviour being wrongly rejected. REQ-0094
makes it concrete: the check rejects *"`al` asserted with `scl_oen` = 0"*; ask
whether *"arbitration checking is performed during WRITE operations"* forbids
that. It plainly does not. *With `rejects`:* each entry already **is** the
counterexample description -- the `condition` field is the thing that would
otherwise need synthesising.

**Sequencing.** The `rejects` field and its two gates (mechanical AST
consistency between declaration and code; per-rejection correspondence against
the requirement) land first, in one change -- the consistency gate cannot lag,
or the declaration is decoration that drifts from the code. D, E and F then
follow as uses of it. It invalidates existing `oracles.json` for the new gates,
so it needs a fresh oracle stage to measure, not a `--reuse` run.

---

## 2. Finishing the normalization error: making it blocking

**Today it blocks nothing, at three separate points**, and only the second is
load-bearing:

1. `normalize.py:984` emits `Issue("error", …)` for *"observable at [...] but no
   route given"*, which drives `run_stage`'s repair loop at `max_repairs=2`.
2. **`run_normalize_fanout` then merges `result.output.normalized[:1]` without
   consulting `result.ok`** (`normalize.py:1141-1147`). A requirement whose
   normalized form never passed its own gate ships identically to one that did.
3. `unsupported_observable()` has exactly one caller -- `write_artifacts`
   (`:1506`) -- and no reader.

On c1-i2c it fired on 15 requirements and checks were written for all 15.

### The argument for blocking, and the argument it does not need

The quality argument is **not** supported by the one measurement available: 39%
of checks from flagged requirements are refuted by the control against 39% from
clean ones. Carrying this error does not predict a worse check, and any plan
that promises it will is promising something already measured false.

The argument that does hold is the one framed as *schema normalization*: **a
stage's own gate rejected the artifact, and the artifact shipped anyway.** That
is a consistency defect independent of whether it predicts downstream quality.
A route with no `shows` is a licence with no claim attached, and the check
author is then handed a port it may assert anything about -- which is what
REQ-0094 did, requiring both lines released on arbitration loss, a thing correct
hardware does not do.

Both should be stated whenever this is reported. The prediction to record now,
so the measurement can refute it: **blocking will not move per-requirement check
quality; it will remove a class of check written with nothing to assert.**

### What blocking means, concretely

* `run_normalize_fanout` merges only items whose `StageResult.ok` holds. The
  rest go to a `malformed` list on `normalized.json`, each with its unresolved
  issues.
* S2 does not plan testpoints for them; [O] attempts no oracle; they never enter
  the frozen set.
* **§8.0's denominator rule applies without exception**: they leave the
  numerator *and* the denominator, and the count is printed beside every rate.
  A build that passes with N requirements carrying no check has to say N.
* They are counted, named and reasoned **on the face of the gate artifact**,
  with their unresolved issues.

### The disposition is NOT `ABANDONED`, and the distinction routes differently

`ABANDONED` means *"we attempted this and the attempt was exhausted"* -- a
finding about the specification or the stimulus. A requirement whose normalized
form is malformed is a finding about **the normalizer**: the model returned a
structure its own gate rejects. Those route to different readers, and collapsing
them would hide a prompt defect inside a spec-quality count. So: a separate
`MALFORMED` disposition with the unresolved issue list attached, routed to
whoever owns the normalization prompt.

### One thing to settle before landing it

`max_repairs=2` at normalize was chosen when the error was advisory. If it is to
block, measure the round-2 residue first -- how many of the 15 were still
failing after both repair rounds, and on what. Blocking on a schema error the
loop would have fixed on round 3 discards a requirement for a prompt's sake.
Raise the bound if the residue is dominated by near-misses; leave it if the
residue is requirements with genuinely nothing to observe.

### Verification

* a requirement whose normalize gate still errors after the repair rounds is
  **absent from `merged`**, absent from the testplan, gets no oracle, and is
  **present, named and reasoned in `normalized.json` and on the gate face** --
  both halves, or the change is half-made;
* it is excluded from every reported rate's denominator, and the count appears
  beside that rate;
* `MALFORMED` is distinguishable from `ABANDONED` in the artifact;
* re-run c1-i2c's normalization and report how many of the 15 survive both
  repair rounds, before the block is switched on;
* `golden_check` at `--hold 60`, pass rate **and** separation -- removing
  requirements changes the denominator and could flatter the rate, so the pair
  is the only honest report.

---

## 3. A calibration test for the calibration

### The confound, restated

`benchmarks/correspondence_calibrate.py` scores its reviewer against a label no
reviewer sees: whether the known-good control satisfies the check. But the 43
refuted and 49 satisfied are checks for **different requirements**, and
requirement difficulty correlates with both check quality and the label. A
reviewer could score well by detecting *"this requirement is hard"* rather than
*"this check overreaches"*, and precision/recall cannot separate those.

The controlled design was always: **hold the requirement fixed and vary only the
check.** It was recorded as unavailable, because the run's own repair rounds do
not supply such pairs (12 at r1, 1 at r2, mostly crash fixes).

### The corpus now exists, as a by-product

`repair_overstrict.py` wrote 40 rewrites of control-refuted checks, keeping
`before` and `after` for each on the **same requirement**. That is the paired
set:

| stratum | n | before | after | what it tests |
|---|---|---|---|---|
| **repaired** | 16 | control refutes | control satisfies | the reviewer should flag `before` and clear `after` |
| **unrepaired** | 22 | control refutes | control refutes | it should flag **both** -- clearing `after` here means it responds to *change*, not to overreach |
| **went quiet** | 2 | control refutes | control satisfies, model too | it should still flag `after`, or the metric rewards vacuity |

The unrepaired stratum is the load-bearing one: it is the negative control that
the unpaired design has no way to construct. A reviewer scoring 16/16 on the
repaired pairs and also clearing 22 of 22 unrepaired `after`s has learned
"something changed", not "this overreaches".

### What to report

**Paired agreement, not precision and recall.** Per stratum: how often the
reviewer's verdict on `before` and `after` matches what the control did. Three
numbers, and the middle stratum reported first, because it is the one that can
falsify the instrument.

Cheap, and it needs no new labels: 40 pairs, 80 calls on `gpt-5-mini`.

### The direction question needs its own set, and c1-i2c does not supply one

Per §0, c1-i2c's 5 VACUOUS contain no confirmed direction error, so the
direction reviewer currently has a label set with no positives. Two ways to give
it one, in preference order:

1. **Injected pairs, the same paired design.** Take checks the control
   satisfies and mechanically invert them -- assert the activation predicate in
   place of the expectation predicate, which is the antecedent form and the
   common one. The requirement is held fixed, the injection is known, and the
   reviewer should flag the injected member and clear the original. This is the
   only design that produces positives whose ground truth is not a judgement
   call.
2. **Hand-label a wider run's VACUOUS set.** Slower, smaller, and it inherits
   whatever reading the labeller brings.

Until one of those exists, the direction question must be reported as **built
and unmeasured**, never as low-yield.

---

## 4. The problem classes in c1-i2c, and which a text-only check could catch

Taxonomy of the 40 rewrites, by the surplus the repairer named. **This is a
reading of 40 free-text descriptions, not a mechanical label** -- the class
boundaries are mine and another reader would move some. The repair outcome
beside each is mechanical and is not.

| class | n | repaired | what the check did |
|---|---|---|---|
| **absence mapped to failure** | 7 | **5** | convicted when evidence was merely missing -- `eventually(...)` with no match returning False. REQ-0008, 0016, 0042, 0043, 0067 |
| **quantifier inflation** | 6 | **3** | `throughout` a whole window, or over every output, where the requirement names one signal at one moment. REQ-0018, 0020, 0107 |
| **invented timing** | 4 | **2** | cycle counts, pulse widths, equal spacings the requirement never states. REQ-0044, 0089 |
| **invented conjunction** | 4 | 1 | "X happens" became "X happens AND Y". REQ-0118 repaired; REQ-0094 not |
| **edge demanded for a level** | 8 | 1 (+2 quiet) | the requirement states a state (*"is observed low"*, *"is high"*); the check demands a **transition into** it. REQ-0002, 0006, 0027, 0030, 0060, 0095, 0097, 0124 |
| **activation over-gating** | 3 | 0 | the check's window adds conditions the activation does not name (`ena==1, nReset==1, rst==0` onto a `cmd==1` activation), so it rarely opens |
| **trace-schema navigation** | 5 | 1 | reading a port from `row['outputs']` when it is in `row['inputs']`, or vice versa. REQ-0057, 0071, 0073, 0093, 0117 |
| **no observable content** | 2 | 0 | the requirement offers nothing to assert on. REQ-0017, REQ-0126 |

### The split that matters

**Text-only detection works on defects of LOGICAL FORM and fails on defects of
TEMPORAL SEMANTICS.** Absence-as-failure 5/7, quantifier inflation 3/6, invented
timing 2/4 -- against edge-for-level 1/8 and activation over-gating 0/3. The
first three are answerable by comparing what the check asserts to what the
requirement says. The last two require knowing what the design *does*: whether a
signal that is high was ever low, whether an activation's extra conjuncts are
ever jointly true. Two texts cannot say.

**And two classes must not be routed to a semantic reader at all:**

* **trace-schema navigation** (5) is a harness defect -- the check mis-navigates
  the replay row shape. It has no semantic content, a reader asked about it will
  confabulate one, and the fix is a schema the author cannot get wrong.
* **the trivially-true consequent** (§0, REQ-0015) needs the stimulus's idle
  values. Its instrument is vacuity.

### The checks worth adding, and what each can see

Each is a narrower predicate than the surplus question, and the value of
splitting them is not novelty -- three are re-cuts -- but that **each gets its
own label and its own repair instruction**, which a single question cannot.

| check | question | label | can it see it? |
|---|---|---|---|
| **level vs edge** | the requirement states a LEVEL; does the check demand a TRANSITION? | control | yes, purely textual -- and it is the **largest unrepaired class**, 8, so it is the first to build |
| **absence as failure** | does any path convict when the evidence is merely missing? | control | yes, and it needs **only the check** -- no requirement. Overlaps §15's `must_pass` and should be built as one thing, not two |
| **quantifier inflation** | does the check quantify over more ports, or more time, than the requirement? | control | yes, textual |
| **activation gating** | does the window require conditions the activation does not name? | **vacuity** -- it narrows, so it causes abstention, not conviction | partly: the conditions are textual, whether they co-occur is not |
| **direction** (built, `dc9a3c9`) | does the check assert the antecedent, the converse, the inverse, or swapped roles? | **vacuity** | unmeasured -- §3 |

Two of the five carry the vacuity label rather than the control label, which is
the same split that made direction a separate call: **a check that narrows
cannot fail, so the control satisfies it and it lands in the over-strictness
label's negative class.** Any of these scored against the wrong label would
count its correct catches as false positives.

### What this does not fix

None of these breaks the symmetry §4b item 4 named. Requirement, check and
reviewer are all text by the same author reading the same specification, so a
misreading they share passes every one of them. `--variants` remains the only
leg that does not share that reading. These checks reduce a measured 43-of-110
defect rate; they do not make the set independent of its author.

---

## 5. Where these two classes actually come from, and what correspondence is missing

Read after §4, and it revises part of it.

### 5.1 The author does what it was told, three times, each with a count behind it

**An earlier draft of this section blamed `effect_follows` and normalization.
That was confounded and is retracted.** The class was selected by reading 40
free-text repair descriptions and then one variable was measured on it (8 of 8
carry `effect_follows=True` against a base rate of 75 of 122). Two checks kill
it: the mechanism does not reproduce -- a stable-correct level under
`after_activation=True, strong=True` PASSES, because the window's closing row
keeps `body` non-empty -- and the 8 checks fail through at least four different
mechanisms (`sequence`, `throughout`, `eventually`, and hand-rolled edge tests),
so one cause was never available to find.

**The real answer is in the prompt, and it is not an omission. It is an
instruction.** `oracle_gen.py:140`, in capitals:

> `WHEN THE REQUIREMENT DESCRIBES AN ACTION, LOOK FOR THE TRANSITION, NOT THE
> LEVEL.` On an open-drain or active-low line the RESTING value and the
> "released"/"inactive" value are the SAME NUMBER, so a scan for
> `outputs[p] == released` matches the very first state, before anything has
> happened [...] it was a level read where a transition was meant.

That reasoning is correct and the measurement behind it is real. What is absent
is its boundary: **nothing anywhere says that requiring the transition convicts
a design whose signal is correctly already at the value and stays there.**

Three instructions push the same direction, each with a measured count, none
carrying its converse:

| where | says | measured on |
|---|---|---|
| `oracle_gen:140` | look for the TRANSITION, not the level | a level scan matching index 0, idle == released |
| `oracle_gen:425` | pass `strong=True`, or the check can never be violated | 5 of 14 abstaining checks |
| `temporal:228` | a consequent already true at the activation satisfies the default -- **the vacuity this module exists to remove** | 6 of 14 vacuous checks |

And the asymmetry is total: **every occurrence of "already" in `oracle_gen.py`
and `temporal.py` is on the vacuity side.** There is no sentence in either file
describing a legitimately already-correct signal.

So the answer to "why can't the author figure it out" is that it is not failing
to figure anything out. It is following three explicit rules, each justified by
evidence, whose joint effect on a requirement stating a STATE is to convict a
correct design. The vacuity-side rules are unconditional imperatives with
counts; the over-strictness-side boundaries are absent. An author would have to
override a capitalised instruction on its own reading of the requirement.

**What the prompt is missing is one sentence, and it is the converse of the one
it has:**

> A requirement can describe a STATE rather than an ACTION -- *"is high while
> X"*, *"is observed low"*, *"remains released"*. There the correct design may
> already hold the value when the window opens and never change it, so a check
> requiring a transition, an edge, or `strong=True` reports a failure against a
> design that is right. Require the transition when the requirement names an
> ACTION; require the level when it names a STATE; and when the resting value
> and the asserted value are the same number, say which one the requirement
> means before you choose.

**Absence-as-failure is the same defect and the same shape**, which is why the
two classes group together. The prompt states its rule twice and both statements
cover NO WINDOW -- *"Return ok=None when THE ACTIVATION NEVER OCCURS"*, *"Do NOT
turn an empty window list into False"* -- while all five defects are a window
that OPENED and did not contain the evidence (REQ-0043: *"the code path that let
`eventually(...)` produce a False verdict for an activation (i.e. 'no indicator
observed')"*). Uncovered by the rule, and covered by `strong=True` pointing the
other way.

**This is #99 from the prompt side**, and it sets the measurement obligation:
every one of these three instructions exists because vacuity was the previous
complaint, so any change to them must be scored on over-strictness AND vacuity
together, or the classes trade back.

### 5.2 Correspondence never sees the interface

`correspondence.build_prompt` takes `requirement`, `normalized`,
`oracle{clause, source}` and `spec`. **It does not take the contract.**
`oracle_gen.build_prompt` takes `contract_json` and `contract` (`:514-522`).

So the check author knows every port's direction and the reviewer does not.
There is no principled defence for that asymmetry: the contract is upstream of
every artifact the pipeline produces, which is exactly the argument that already
admits `spec` to this prompt, and it is an interface, not a design. It carries
nothing back from the model, the witness or the trace.

What it unlocks, in the order the classes matter:

* **quantifier inflation** -- *"more ports than the requirement names"* is not
  answerable without knowing what the ports are;
* **#95 directly** -- REQ-0028's check asserts on an INPUT the design cannot
  drive. A reviewer holding port directions sees *"this convicts on a value the
  DUT does not drive"* in one line; without them it cannot see it at all;
* **invented conjunction** -- whether the added conjunct is even an observable
  of this design.

**And it partly revises §4's "route away" call on trace-schema navigation.**
Those 5 checks read a port from `row['outputs']` when it is in `row['inputs']`
or the reverse. With port directions the reviewer can distinguish *the check
read the wrong dict* (a check defect, repairable) from *the trace put an output
in the inputs dict* (a harness defect, and a different owner). That does not
make it a semantic check -- it stays a mechanical one -- but it converts an
undiagnosable class into a routable one, which §4 said was out of reach.

### 5.3 What to do, in order

1. **Add the contract to `correspondence.build_prompt`**, ahead of the
   requirement so the shared prefix stays cacheable across the fan-out -- the
   same placement and the same reason as `spec`. Smallest change here, and it is
   a precondition for three of §4's five checks rather than one of them.
2. **Give `normalize` the state-versus-event distinction** that `effect_follows`
   is currently answering by accident, and re-measure the 8. This is the larger
   half of level-vs-edge and it lands with §2, not with the detectors.
3. **Rewrite the `strong=True` guidance** to carry the obligation-versus-state
   rule, and measure over-strictness AND vacuity together, since the instruction
   exists because vacuity was the previous complaint.
4. Only then the detectors in §4, against a population these three have already
   changed.
