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

Indirect routing predicts rejection without determining it: **7 of 11 routed
requirements were rejected (64%) against 12 of 32 direct (38%)**. REQ-0042,
REQ-0044, REQ-0082 and REQ-0089 are routed and trusted, so the route is a
handicap rather than a wall.

This classification reads each rejection's **stated ground** and checks it for
internal consistency against the requirement text and the port list. It does not
re-derive whether each alleged false path actually occurs in the golden trace;
that is a separate pass.

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
