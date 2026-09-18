"""[O] The requirement oracles, as a stage.

Oracle generation used to run *inside* reference-model generation:
`run_oracle_gen` called from `_debug_turns`, called from `run_refmodel`. Every
other artifact in this pipeline is a stage -- a prompt, a gate, a bounded repair
loop, a file on disk, a `--reuse` path -- and the oracles had none of that. Four
measured defects were symptoms of the one omission:

* **5 of 77 oracles vanished** at generation and surfaced as an `UNDECIDED`
  that also means "decided nothing". A stage records a disposition per item.
* **`ORACLE_INVALID` rose 4 -> 5 -> 8 monotonically.** Nothing regenerated a
  rejected oracle, because the route said "regenerate the oracle" and no code
  did. A stage has a repair loop.
* **Four of five apparent closures were the agent editing the model toward
  checks a known-good control also fails**, discovered at turn 2. A stage
  finishes gating before its consumer runs.
* **`VACUOUS` wandered 16 -> 18 -> 16 with the oracle set frozen**, because
  gate 2 re-derived its mutants from a model the agent was editing. A stage's
  gate does not re-run against a moving input.

So this is the same shape as S1, S2, S3 and normalize. What it adds over those
is that its gate is not one predicate but four, and three of the four are
**model-independent by construction** -- they run against the witness and the
variants, both frozen, and never against the design under repair. That is what
lets them run once and stay decided.

**What verification must NOT do**, both learned the expensive way:

* An oracle whose scenario the stimulus never reaches is a *valid oracle*.
  `NOT_EXERCISED` is a joint property of stimulus and model and belongs to the
  debug loop; rejecting it here would delete exactly the findings the stimulus
  tool exists to act on.
* A witness that raises mid-replay is a *witness* defect. The leg goes quiet for
  that oracle rather than convicting it -- blaming the check for the reference's
  crash is the confusion this whole design exists to prevent, one level over.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import reachability, variety
from .model_io import ModelPort
from .refmodel import correspondence, freeze
from .refmodel import liveness as _L
from .refmodel import trust
from .refmodel import variants as variants_mod
from .refmodel import verdict as V
from .refmodel import oracle_gen
from .refmodel.oracle_gen import run_cell_gen, run_oracle_gen
from .refmodel.oracles import (RequirementOracle, decide, replay,
                               transactional_view, well_formed)
from .schema import Issue

logger = logging.getLogger(__name__)

STAGE = "oracles"
ARTIFACT = "oracles.json"

#: Which design bounded the oracles from above. Never summed: a control is a
#: known-good design, a witness is a second reading of the same requirements by
#: the same author and is strictly the weaker instrument.
#:
#: **A control may REJECT an oracle. It may never REPAIR one.** Feeding "the
#: known-good design fails you at edge 7 because dout changed at edge 7" back to
#: the author leaks that design's behaviour into the oracle text -- and since
#: the model is then repaired against the oracles, the model ends up tuned
#: against the control transitively, which destroys `golden_check` as an
#: independent grade. The witness is what the repair loop is allowed to quote,
#: because it is generated from the same requirements and held out from nothing.
CONTROL = "control"
WITNESS = "witness"
NO_BOUND = "none"

TRUSTED = "TRUSTED"

#: Staging attempts per requirement. Small: each is a model call plus a gate,
#: and the evidence below either sharpens the hint quickly or is not going to.
STAGING_ATTEMPTS = 3

#: Testpoints this stage may mint PER UNEXERCISED ORACLE, so the budget is
#: sized from the work in front of it. It used to be a flat 12 for the whole
#: stage, described as "separate from the debug loop's" -- but [D]'s 12 is per
#: TURN against a handful of currently-failing oracles, and this is a sweep over
#: every oracle nothing reaches. On a2-i2c that was 41 oracles wanting 3 attempts
#: each: 123 testpoints against a budget of 12. Twelve were minted, four
#: requirements were covered, and THIRTY-SIX WERE ABANDONED WITHOUT AN ATTEMPT.
#:
#: Per-oracle rather than a bigger constant, because the failure was a constant
#: sized for a different loop and a bigger one would only move the cliff.
STAGING_BUDGET_PER_ORACLE = 3

#: The one outcome that is NOT an attempt: the generator was never invoked.
BUDGET_SPENT = "budget spent"

#: Outputs that only move when another bus master contends. Named by
#: convention because the contract has no field for "this needs contention",
#: and on i2c the convention is exact: `al` is arbitration-lost, and nothing in
#: a single-master sequence asserts it.
_ARBITRATION_PORTS = frozenset({"al"})

#: Absolute ceiling, so a pathological requirement set cannot mint without end.
#: Generous by design: reaching it should be a finding, not routine.
STAGING_BUDGET_CAP = 400


@dataclass(frozen=True)
class CorpusBody:
    """ONE BODY THE STAGE AUTHORED, kept whether or not it was the survivor.

    A run authors three to six bodies per requirement and keeps ONE. Every other
    body is discarded at the moment it is superseded -- which is exactly the
    population a selection rule needs, thrown away to make room for the rule
    that replaced it. The narrowing round's "12 of 47 became vacuous" was a LOSS
    under replace-in-place and is just corpus under selection.

    Provenance travels with the body because the retained set is only useful if
    a later analysis can ask what differs between two members. Measured on k1:
    resampling one prompt produces a body identical to the selection rule 69% of
    the time among sound pairs, so "what differs" is the whole question.
    """

    req_uid: str
    source: str
    #: Which authoring configuration produced it -- "control", "shipping", a
    #: repair round, a staging attempt.
    arm: str = ""
    #: Repair round it was authored in; 0 is the first draft.
    round_: int = 0
    #: The objection this body was written to answer, "" for a first draft.
    answered: str = ""
    #: Did this body end up in `trusted`? Exactly one member per requirement
    #: should carry True, and a set where none does is a requirement the stage
    #: authored for and then dropped.
    frozen: bool = False

    def digest(self) -> str:
        """Content identity. Two bodies with the same text are ONE member --
        the recording key `{stage}_r{round}` returns the first response for a
        matching key, so N draws under one stage name are one response replayed
        N times, and k1's volume round retained 8 byte-identical pairs that way.
        """
        return hashlib.sha256(self.source.encode("utf-8")).hexdigest()[:16]


def _retain(corpus: dict[str, list[CorpusBody]],
            oracle: RequirementOracle, *, arm: str = "", round_: int = 0,
            answered: str = "", frozen: bool = False) -> None:
    """Add a body to the corpus, de-duplicated by CONTENT.

    De-duplicating by content rather than by round is not tidiness. The
    recording key is `{stage}_r{round}`, and the resume port returns the FIRST
    response for a matching key -- so N draws under one stage name are one
    response replayed N times, and retaining them by round would record a corpus
    of N where the authoring produced 1. k1's volume round did exactly that: 8
    of 8 retained pairs are byte-identical.
    """
    body = CorpusBody(req_uid=oracle.req_uid, source=oracle.source, arm=arm,
                      round_=round_, answered=answered, frozen=frozen)
    members = corpus.setdefault(oracle.req_uid, [])
    seen = {m.digest() for m in members}
    if body.digest() in seen:
        return
    members.append(body)


@dataclass(frozen=True)
class OracleSet:
    """What the stage decided, for every requirement it was given."""

    trusted: list[RequirementOracle] = field(default_factory=list)
    #: `req_uid -> every body authored for it`, survivors and superseded alike.
    #: **THIS IS THE CORPUS A SELECTION RULE READS.** It is not `trusted`: the
    #: whole point is that the stage's own choice of survivor is what selection
    #: replaces, so a corpus containing only survivors has nothing to select
    #: over. Empty on a run that did not retain, which reads as "not retained"
    #: rather than "authored one body".
    corpus: dict[str, list[CorpusBody]] = field(default_factory=dict)
    #: `req_uid -> TRUSTED` or the verdict that rejected it. Total over the
    #: requirements: a requirement missing from here would be a silent subset.
    dispositions: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    #: `req_uid -> [what each round complained about]`, for the oracles that
    #: were rejected and then repaired. Their final `reasons` entry is empty --
    #: they are TRUSTED -- so without this the only trace of what the gate
    #: caught is in `agent_io`, and a repair pass is exactly what overwrites
    #: that. "What does the must-pass leg actually catch?" is a question this
    #: project has already had to answer once by reconstructing it from a
    #: transcript directory.
    repairs: dict[str, list[str]] = field(default_factory=dict)
    variants: list = field(default_factory=list)
    witness_kind: str = NO_BOUND
    rounds: int = 0
    #: Testpoints in the plan that NO oracle names. They render, they start a
    #: simulator process, and nothing they produce decides anything -- the inert
    #: testbench this project exists to prevent, one level up. Measured on
    #: n-i2c: 17 of 167. Recorded rather than acted on, because the fix is a
    #: testplan or an oracle-scoping decision and neither belongs to this stage.
    testpoints_no_oracle_names: list[str] = field(default_factory=list)
    #: `req_uid -> liveness verdict` for the checks that survived. Carried out
    #: of the stage rather than left in the artifact because the DEBUG LOOP is
    #: where it changes how a number reads: "46 CONFORMS" was reported as
    #: convergence on a model that fails 138 of 168 testpoints against golden
    #: RTL, and 11 of those 46 came from checks nothing could move. The loop
    #: cannot recompute it -- that would put a gate back inside the loop, which
    #: is what this rework removed -- and it does not need to, because the
    #: verdict does not depend on the design being debugged.
    liveness: dict[str, str] = field(default_factory=dict)
    #: `req_uid -> what the witness observed`, for the checks it could not
    #: satisfy. Gate 1 stays non-mandatory and none of these is rejected -- the
    #: witness is a second reading by the same author and cannot overrule the
    #: text. What changes is that the observation now LEAVES THE STAGE.
    #:
    #: Measured on r-i2c: the debug loop drove VIOLATES 9 -> 5 and then spent
    #: its remaining three turns on the 5 that were left, every one of which a
    #: known-good control also fails. The witness had flagged exactly those
    #: five -- REQ-0020, 0060, 0066, 0067, 0070 -- before the reference model
    #: existed. The information was in this artifact and nothing downstream
    #: read it.
    witness_notes: dict[str, str] = field(default_factory=dict)
    #: `req_uid -> why we gave up`, one of `verdict.ABANDONED_REASONS`.
    #:
    #: These requirements LEAVE THE SYSTEM. They are not in `trusted`, so the
    #: debug loop cannot decide them, `run_all` cannot count them and the board
    #: cannot show them -- which is what makes this a discard rather than a
    #: verdict that no longer blocks but is still in the way.
    #:
    #: What they must not do is disappear. They stay in `dispositions` with the
    #: reason here, they are counted on the face of the gate, and they leave the
    #: DENOMINATOR of every rate rather than quietly passing -- see `rates`.
    abandoned: dict[str, str] = field(default_factory=dict)
    #: The instruments this set was built with, recorded so a later round
    #: inherits them instead of re-deriving them from a call site's keyword
    #: arguments.
    #:
    #: THIS IS WHY THE TOOLS CANNOT DRIFT BETWEEN ROUNDS. A strengthening round
    #: used to be a separate function that reimplemented a subset of the stage,
    #: and which instruments it lost -- correspondence, the repair loop,
    #: liveness routing, staging -- was decided by which flags one call site in
    #: `compose` happened to pass. Reading them off the set it is strengthening
    #: makes "the same tools" a property of the data rather than of five
    #: keyword arguments staying in step.
    tools: dict = field(default_factory=dict)
    #: One entry per verify round the correspondence reviewer actually ran:
    #: `{"round": n, "reviewed": k, "off_target": [uid...],
    #:   "not_assertable": [uid...]}`.
    #:
    #: WHY A PER-ROUND RECORD AND NOT A TOTAL. The gate is published as a
    #: one-draw rate -- "over 70 frozen oracles it rejects 3" -- and this stage
    #: applies it once per round over the WHOLE surviving set, with `rejected`
    #: cleared each round and `round_` in the resumption key. So the rate a run
    #: experiences is the compounded one, and no artifact reported it: `repairs`
    #: carries the reasons but not the round, so "rejected on a round > 1" --
    #: the population that separates a gate finding something new from a gate
    #: re-rolling the same dice -- could not be recovered from a finished run.
    #:
    #: IT ANSWERS A QUESTION, IT DOES NOT SETTLE ONE. A round-2 rejection is
    #: not evidence the check was bad, and the count is not a span loss. What
    #: this makes possible is reading the triple over that population; nothing
    #: here licenses reading the count on its own.
    correspondence_rounds: list[dict] = field(default_factory=list)
    #: `req_uid -> which selection leg dropped it, and why`. Empty both when no
    #: ruleset ran and when one ran and dropped nothing; `selection_ran`
    #: separates those, because "0 dropped" and "not looked at" are different
    #: claims and this stage has already been misread once on exactly that.
    selection_dropped: dict[str, str] = field(default_factory=dict)
    selection_ran: bool = False
    #: `req_uid -> which `_unreached` guard silenced it`. A requirement that
    #: leaves through one of those guards produces NO rejection and NO
    #: disposition of its own, so it is invisible in every rate this class
    #: reports -- and the five guards route to five different owners.
    #:
    #: Measured on k1-dcfsm: **19 of 25 ABANDONED requirements never reached a
    #: repair round and only 7 carried an `unreached:` objection, so 18 were
    #: silenced there** -- and which guard did it could not be recovered from
    #: the artifact, because the record keeps the staging attempts and not the
    #: verdict `_unreached` reached on them. The guards already name themselves
    #: to `logger.debug`; this is the same string, kept where a finished run can
    #: still be asked about it.
    unreached_silenced: dict[str, str] = field(default_factory=dict)
    #: `req_uid -> a faithfulness ground that was RECORDED rather than acted on`
    #: (`demote_faithfulness`). These checks are in `trusted`; the label says a
    #: reviewer or a lexical screen objected and was overruled by policy, so a
    #: consumer can weight them without anything having been discarded.
    #:
    #: Silence is free to keep and conviction is not: a blind check never
    #: mis-steers a repair loop, while an over-strict one sends it after
    #: nothing -- the debug loop once drove VIOLATES 9 -> 5 and spent its last
    #: three turns on five a known-good control also fails. That asymmetry is
    #: why this is a label a consumer reads, not merely a suppressed discard.
    labels: dict[str, str] = field(default_factory=dict)
    #: `req_uid -> [{round, was, now}]`. Every accepted repair that changed how
    #: many of its own testpoints the check decides on.
    #:
    #: The stage blocks a repair that stops deciding ENTIRELY. It does not see a
    #: replacement that goes from ten testpoints to one, and that is the gradual
    #: road into the population where, among k1's 68 sound checks, the chance of
    #: discriminating is 26% against a 75% base rate and 52 convict nothing.
    #: Recorded so the distribution can be read before any threshold is chosen.
    narrowing: dict[str, list[dict]] = field(default_factory=dict)
    #: `req_uid -> what the known-good control could not satisfy`, for the
    #: checks that SHIPPED. The bar stays -- the control may not select which
    #: oracles survive, because gating on it tunes the model toward the held-out
    #: grade transitively -- but the cost of keeping the bar is a number, and it
    #: was only ever available by reconstructing it after the fact.
    #:
    #: Measured, that cost: the flag finds 61 of the 71 checks golden falsifies
    #: at 92% precision and 86% recall, and "61 checks the golden falsifies,
    #: known at authoring time, shipped TRUSTED". Naming it every run is not
    #: gating on it.
    control_notes: dict[str, str] = field(default_factory=dict)

    def considered(self) -> int:
        """Requirements still in the system: the denominator for every rate.

        An abandoned requirement leaves the numerator AND the denominator. "46
        of 70 CONFORM" with 10 abandoned is three numbers -- 46, 60 and 10 --
        and reporting the first two without the third is precisely the class of
        number this project has already had to retract twice.
        """
        return len(self.dispositions) - len(self.abandoned)

    def rates(self) -> dict[str, int | None]:
        """Counts, and `None` where a check did not run.

        `VACUOUS: 0` and `VACUOUS: None` are different claims and only one of
        them is ever true: with no variants the vacuity leg is skipped
        entirely, so zero convictions means "not looked at", not "none found".
        This exact ambiguity misread a whole run once -- `over_strict: 0` was
        taken as "no oracle is over-strict" when it meant "no control was
        supplied" -- and 22 of 54 trusted oracles turned out to be failed by a
        known-good model.
        """
        counts = Counter(self.dispositions.values())
        out: dict[str, int | None] = {
            "trusted": len(self.trusted),
            # The denominator, beside the counts, always. A rate read against
            # the wrong total is worse than no rate.
            "considered": self.considered(),
            "abandoned": len(self.abandoned),
            **{k: counts[k] for k in sorted(counts) if k != TRUSTED},
        }
        if not self.variants:
            out["VACUOUS"] = None
        if self.witness_kind == NO_BOUND:
            out["ORACLE_INVALID"] = out.get("ORACLE_INVALID")
        # Same rule, for the gate that finds hollow requirements: correspondence
        # is the only leg that can emit NOT_ASSERTABLE, so with it switched off
        # a zero means "nobody asked whether these requirements assert
        # anything", which reads in a report exactly like "they all do".
        if not self.tools.get("correspondence"):
            out["NOT_ASSERTABLE"] = out.get("NOT_ASSERTABLE")
        # ADMITTED OVER AN OBJECTION, counted where the rates are read. Zero
        # and absent are the same here -- no faithfulness ground was recorded,
        # either because none fired or because the gates were left blocking --
        # so unlike `VACUOUS` this needs no `None`: `tools["demote_faithfulness"]`
        # says which run this was.
        out["admitted_over_an_objection"] = len(self.labels)
        # THE PRICE OF THE CONTROL BAR, beside the rates rather than
        # reconstructed afterwards. `None` when no control was supplied,
        # because 0 there means "nobody looked" -- the exact ambiguity that
        # misread a whole run when `over_strict: 0` was taken as "no oracle is
        # over-strict" and 22 of 54 trusted oracles turned out to be failed by
        # a known-good model.
        out["trusted_the_control_fails"] = (
            len(self.control_notes) if self.witness_kind != NO_BOUND
            or self.control_notes else None)
        # SURVIVING IS NOT DECIDING, beside the number that says it did. See
        # `trusted_liveness`: `trusted` counts checks that passed every gate,
        # and on the two runs where both were counted it overstated what
        # executed by 17% and 30%.
        out.update(self.trusted_liveness())
        return out

    def trusted_liveness(self) -> dict[str, int | None]:
        """What the liveness instrument said about the checks that SHIPPED.

        `trusted` is the headline number and it means "survived every gate".
        That is not the same claim as "decides anything", and the gap has been
        measured twice: k1-dcfsm froze 36 TRUSTED of which 30 executed, c1-i2c
        froze 110 of which 77 did -- a 17% and a 30% overstatement of the thing
        a reader takes the number for. Nothing in `rates` said so, while
        `liveness` had run every round and was sitting in the same artifact.

        WHY SURVIVING AND DECIDING COME APART HERE, in one line each. The round
        loop rejects only `DEAD_ORACLE` -- a check nothing moves. `DEAD_STIMULUS`
        is deliberately not rejected, because a scenario not being staged is the
        testplan's business and not the author's, and `UNKNOWN` covers a check
        with no replayable testpoint or no declared output. Both ship TRUSTED
        and neither decided anything on this run.

        AND `live` IS THE INSTRUMENT'S VERDICT, NOT THE TRUTH. Its false-live
        rate is measured and is not small -- 12.5% on k1, 28.7% on i2c -- so
        `trusted_live` is an upper bound on what decides, never a count of it.
        It is reported because the alternative on offer is `trusted` alone,
        which is a looser upper bound presented as an exact number.

        `None` throughout when liveness did not run, following the rule this
        class already keeps for `VACUOUS` and `NOT_ASSERTABLE`: a zero here
        would read as "nothing inert shipped", which is what "nobody looked"
        looks like in a report.
        """
        uids = {o.req_uid for o in self.trusted}
        if not self.liveness:
            return {"trusted_live": None, "trusted_inert": None,
                    "trusted_liveness_unknown": None}
        seen = {u: self.liveness.get(u, _L.UNKNOWN) for u in uids}
        return {
            "trusted_live": sum(1 for v in seen.values() if v == _L.LIVE),
            # `DEAD_ORACLE` should be empty -- the round loop rejects it -- but
            # a set frozen before that gate existed and restored with `--reuse`
            # can still carry one, and silently folding it into "unknown" would
            # hide exactly the checks that gate was added to catch.
            "trusted_inert": sum(
                1 for v in seen.values()
                if v in (_L.DEAD_STIMULUS, _L.DEAD_ORACLE)),
            "trusted_liveness_unknown": sum(
                1 for v in seen.values() if v == _L.UNKNOWN),
        }

    def decides_nothing(self) -> int:
        """How much of the suite proves nothing. Never silent, never zero by
        omission -- an empty list and an unmeasured one read the same in a
        report and mean opposite things."""
        return len(self.testpoints_no_oracle_names)

    def by_verdict(self, name: str) -> list[str]:
        return sorted(u for u, v in self.dispositions.items() if v == name)


def verify_one(
    oracle: RequirementOracle,
    *,
    contract: dict,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    witness: str,
    variants: list,
    base: str,
    control: str = "",
    transactional: bool = True,
    #: `correspondence.Review` for this oracle, when one was taken. The only
    #: BLOCKING check that is not mechanical -- and the only one entitled to
    #: block for a reason no design supplies: whether the oracle decides the
    #: requirement it names at all.
    review=None,
    #: Demote the correspondence verdict from a rejection to a `notes` label.
    #: The control arm of the admission experiment -- see the block below.
    demote_faithfulness: bool = False,
) -> tuple[str, bool, dict[str, str]]:
    """`(why, quotable, notes)`.

    `why` is why this oracle is UNUSABLE -- empty when it is fine. `quotable`
    says whether an author may be told the details. `notes` is what the
    instruments observed without rejecting: `{"witness": ...}`,
    `{"control": ...}`.

    **NO IMPLEMENTATION GATES AN ORACLE HERE.** Only two things reject, and
    neither involves a design:

    * `well_formed` -- structural, and a replay that breaks the oracle itself;
    * vacuity, from VARIANTS, which are derived from the requirement text.

    The two designs are instruments, and each is disqualified from gating for
    its own reason.

    **The witness is a tuning target, not a correctness authority.** It is a
    second reading of the same requirements by the same author, so an oracle
    failing it means two same-author readings disagree and either could be
    wrong. Rejecting on that does not make the oracle more correct, it tunes the
    oracle toward one arbitrary reading -- measured: putting the witness in the
    author's repair loop moved over-strictness 27 -> 15 and convictions 2 -> 16,
    which is oracles being relaxed until they stop disagreeing, the relaxation
    surfacing as vacuity.

    **The control is an authority, and that is exactly why it may not gate.** It
    is known-good because it scores 168/168 against the golden RTL, so it is a
    PROXY FOR THE HELD-OUT GRADE. Withholding its detail from prompts stops its
    behaviour leaking into oracle text, but it does not stop the one bit that
    matters: kept or rejected. That bit selects which oracles survive, the
    surviving oracles are what the model is repaired against, and the model is
    what `golden_check` then scores -- so gating on the control tunes the model
    toward the grade transitively. An instrument that shapes the run is no
    longer independent of it.

    What this costs, stated rather than hidden: an oracle no correct design can
    satisfy now reaches the debug agent, which will spend attempts on a demand
    nothing can discharge. Measured on a-i2c: 22 of 54 trusted oracles were
    failed by the control, and 10 of the 18 findings the agent could not
    discharge were among them. That cost is now VISIBLE and ATTRIBUTED -- the
    control scores the frozen set afterwards, the way `golden_check` scores the
    model -- instead of being paid silently as a filter.
    """
    why = well_formed(oracle, contract, testplan)
    if why:
        return f"malformed: {why}", True, {}

    # A testpoint with no recorded stimulus cannot run the oracle, and that is a
    # fact about the STIMULUS. Letting a leg reject on it would call an oracle
    # malformed for a reason it has no way to fix -- the same mistake as
    # rejecting an unexercised one, which the module docstring rules out.
    replayable = any(stimulus_by_tp.get(tp) for tp in oracle.tp_uids)
    notes: dict[str, str] = {}

    # Gate 1 first, and non-mandatory: the witness observes and never decides.
    # Its note is recorded before anything blocks, so a rejection downstream is
    # read beside what the witness happened to think rather than instead of it.
    for name, design in (("witness", witness), ("control", control)):
        if not design or not replayable:
            continue
        held = trust._decide_over(  # noqa: SLF001
            oracle, design, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        if held.broken and not held.model_broke:
            # The ORACLE broke, not the design. That is structural and rejects.
            return f"malformed: {held.broken}", True, notes
        # A design that raises says nothing about the oracle. Quiet, not guilty.
        # `held.unexercised()` is not a finding either: the scenario not being
        # staged is the stimulus's business.
        if held.failed():
            where = f" at edge {held.edge}" if held.edge is not None else ""
            if name == "witness":
                # Computable from the trace, so it does not borrow the witness's
                # authority -- the witness is only where the trace came from,
                # the same standing `_liveness` already has. What it decides is
                # a property of the CHECK: did it answer before anything it
                # watches had moved?
                idle = _L.judged_before_the_scenario(
                    oracle, held.rows, contract, at_edge=held.edge)
                if idle:
                    notes["idle_match"] = idle
                else:
                    # Only when the idle read does not already explain it: both
                    # notes replace the generic ask, and sending two competing
                    # diagnoses for one disagreement is worse than sending the
                    # sharper one alone.
                    split = _L.disagrees_with_itself(
                        oracle, design, contract, stimulus_by_tp, base=base,
                        transactional=transactional)
                    if split:
                        notes["self_split"] = split
            notes[name] = (
                f"fails it{where} -- {held.detail or '(no detail)'}"
                if name == "witness" else
                f"fails it{where}; the detail is withheld so nothing can be "
                f"tuned against a held-out grade")

    if review is not None:
        # Blocking, and it is the weaker instrument by design. It sees the
        # requirement and the oracle source -- two texts, no implementation --
        # so it cannot be contaminated by a design, which is exactly why it may
        # decide where the designs may not. Authority follows independence here,
        # not strength.
        #
        # **AND `demote_faithfulness` MAKES IT A LABEL INSTEAD, BEHIND A FLAG.**
        # The flag exists because the question is a measurement, not a taste:
        # the protocol runs one module twice on identical inputs, gates on and
        # gates demoted, and compares the admitted checks against the already-
        # trusted ones. A one-way change would delete the control arm.
        #
        # WHY THE QUESTION IS OPEN AT ALL. This gate asks whether a check is
        # FAITHFUL to its requirement, and faithfulness does not predict
        # usefulness here: it passed 21 of the 23 checks `liveness` shows cannot
        # be moved by any legal value, and of k1-dcfsm's 24 live discards 16 are
        # this gate. Measured on the two frozen sets that survived the data
        # loss, it accounts for the ENTIRE oracle-stage loss -- 8 of 8 and 19 of
        # 19 discards, with 63 repair rounds already spent on them. Its dominant
        # objection is the trigger (29 of 33 on d1-i2c) and the only move
        # against that is to narrow until the check stops firing, which is the
        # route 9 checks took from deciding to abstaining.
        #
        # The default stays BLOCKING. Nothing here is evidence that admitting
        # them is better; it is the reason to measure rather than assume.
        off = correspondence.rejects(review)
        if off and demote_faithfulness:
            # A LABEL, NOT A VERDICT. It rides in `notes` exactly as the witness
            # observation does, so the disposition still records it and the
            # debug loop can weight it, while nothing is discarded on it.
            notes = {**notes, "faithfulness": off}
            off = ""
        if off:
            # `may_quote` is what buys a repair round, and a requirement that
            # states no obligation must not get one: the author cannot add an
            # obligation to a sentence that has none, so re-asking spends a call
            # to receive the same invention back. It is recorded and routed to
            # spec authoring instead -- see `verdict.ROUTE["NOT_ASSERTABLE"]`.
            return off, not off.startswith("not-assertable:"), notes

    if variants and replayable:
        level, detail, apart = variants_mod.must_fail(
            oracle, variants, contract, stimulus_by_tp, base=base,
            transactional=transactional, conforming=witness)
        if level == trust.CONVICTED:
            # The counterexample rides in `notes` rather than in `why`, which
            # has to stay the artifact's one-line reason. `_witness_note`
            # dispatches on named keys and falls through to `[]`, and
            # `advisory_only` requires a "witness" key, so an extra one here
            # cannot manufacture an advisory or an extra call.
            if apart:
                notes = {**notes, "vacuity": apart}
            return f"vacuous: {detail}", True, notes
    return "", True, notes


def _witness_note(req_uid: str, notes: dict[str, str]) -> list[Issue]:
    """The witness disagreement, said as precisely as the trace allows.

    Two different messages, and which one goes out matters more than it looks.

    `_advisory` asks the author to TRY to accept a second implementation. That
    is the right thing to say when nobody knows which reading is right -- and it
    is pressure toward relaxation, measured: when this disagreement could
    reject, over-strictness went 27 -> 15 and convictions 2 -> 16, oracles
    relaxed until they stopped disagreeing.

    When `judged_before_the_scenario` fires, nobody has to guess. The check
    answered at an edge where nothing it reads had moved off its reset value,
    and something it reads moves later in the same trace. That is a level read
    where a transition was meant, it is computable from the trace, and the fix
    is specific. Sending the generic "try to accept it" alongside would invite
    relaxation for a defect that has an exact repair, so the specific note
    leads and `_advisory` is still NOT sent.

    BUT THE WITNESS FAILURE IS NO LONGER DROPPED WITH IT. This used to `return`
    on `idle_match` alone, so when both fired the author was told it had judged
    at idle and never told that a second implementation had failed its check at
    all. Measured on h3-i2c: five `dout` checks (REQ-0028/0057/0099/0100/0101)
    carried BOTH keys, went out with the idle note only, froze as TRUSTED, and
    every one of them convicted golden RTL. The witness had failed all five and
    said so in `instrument_notes`; nothing downstream ever saw it.

    So the idle diagnosis still leads -- it is the precise one -- and
    `_witness_stands` follows it with the bare fact. That fact is deliberately
    NOT `_advisory`: it reports the disagreement without asking the author to
    accept the second implementation, which is the move that measured
    over-strictness 27 -> 15 but convictions 2 -> 16.
    """
    if "idle_match" in notes:
        issues = [_idle_advisory(req_uid, notes["idle_match"])]
        if "witness" in notes:
            issues.append(_witness_stands(req_uid, notes["witness"]))
        return issues
    if "self_split" in notes:
        return [_split_advisory(req_uid, notes["self_split"])]
    if "witness" in notes:
        return [_advisory(req_uid, notes["witness"])]
    return []


def _witness_stands(req_uid: str, note: str) -> Issue:
    """The witness disagreed, stated as evidence and nothing more.

    Deliberately not `_advisory`. That one asks the author to TRY to accept a
    second implementation, and the asking is what measured over-strictness
    27 -> 15 while convictions went 2 -> 16 -- checks relaxed until they stopped
    disagreeing. This says only what happened, so a specific diagnosis can lead
    without the witness verdict vanishing behind it.
    """
    return Issue(
        # A DISTINCT path from `_advisory`'s `witness_disagrees`. They carry
        # the same fact and mean different things -- that one ASKS the author to
        # accept the second implementation, this one only records it -- and a
        # shared id would make them indistinguishable in the artifact exactly
        # where the difference is the point.
        "warning", f"oracle.{req_uid}.witness_disagrees_reported",
        f"Separately, a second implementation of this same requirement {note}.\n\n"
        f"This is REPORTED, not a request to weaken anything -- fix the defect "
        f"named above and this may resolve with it. It is here because a check "
        f"that fails an implementation believed correct is the single best "
        f"predictor available that it will fail a correct DESIGN, and that "
        f"evidence must not be lost just because a more specific note applies.")


def _split_advisory(req_uid: str, note: str) -> Issue:
    """The check holds on most of its own testpoints and breaks on one.

    That is more often a testpoint the clause is not about than a check that is
    uniformly too strict -- `decide_all` reports the single failure as the
    oracle's whole verdict, because the first failure is the answer, so one
    mismatched scenario hides four agreements.

    **It is also exactly what a CORRECT oracle looks like when it catches a
    defect visible in one scenario only**, which is the reason for having
    several testpoints at all. So this asks rather than tells, and says outright
    that keeping the check is a correct answer. Nothing is rejected either way;
    `disagrees_with_itself` needs two passes and strictly more passes than
    failures before it will speak at all.
    """
    return Issue(
        "warning", f"oracle.{req_uid}.disagrees_with_itself",
        f"Against ONE implementation, your check {note}.\n\n"
        f"Check whether that one testpoint stages a scenario your clause is "
        f"actually about. A check that holds in most of the situations its own "
        f"testplan entry named, and breaks in one, is often reading that one "
        f"situation as in scope when the requirement does not cover it -- and "
        f"a single failure becomes the whole verdict, hiding the agreements.\n\n"
        f"IF IT IS A REAL DEFECT VISIBLE ONLY THERE, KEEP YOUR CHECK EXACTLY AS "
        f"IT IS and say so in `reasoning`. Catching something that shows up in "
        f"one scenario is what several testpoints are for, and nothing is "
        f"rejected for declining.")


def _idle_advisory(req_uid: str, note: str) -> Issue:
    """A level read where a transition was meant.

    Open-drain makes a protocol's idle state and its deasserted state the same
    value: the control resets to `scl_oen = 1, sda_oen = 1`, which is exactly
    the value every "release the line" requirement tells an oracle to look for.
    A check that scans for `port == value` without comparing consecutive rows
    matches edge 0 and reports that the action preceding it never happened.

    Worked example, REQ-0070: it demands SDA driven low before SCL is released,
    and the control does exactly that -- `sda_oen` 0 at edge 4, `scl_oen` 1 at
    edge 5. The oracle takes the first `scl_oen == 1` at or after activation,
    finds edge 0, and fails. Its sibling REQ-0042 states the same ordering, so
    this is not a disagreement about the protocol.

    Unlike `_advisory` this names a defect rather than asking a question, so it
    does not invite the check to be weakened -- the repair makes it MORE
    precise, not less.
    """
    return Issue(
        "warning", f"oracle.{req_uid}.judged_at_idle",
        f"Your check {note}.\n\n"
        f"That is almost always a LEVEL read where a TRANSITION was meant. On "
        f"an open-drain bus the idle state and the released state are the same "
        f"value, so 'the line is released' is true at edge 0 -- before anything "
        f"happened -- and a scan for `port == value` finds it there and "
        f"concludes the action never occurred.\n\n"
        f"Look for the CHANGE instead: compare consecutive rows and find where "
        f"the port moves INTO the value, not where it merely sits at it. If the "
        f"requirement really is about the state at reset and not about an "
        f"action, keep your check as it is and say so in `reasoning` -- nothing "
        f"is rejected for declining.")


def _advisory(req_uid: str, note: str) -> Issue:
    """Gate 1's observation: TRY to satisfy it, and declining is a real answer.

    Non-mandatory does not mean ignorable. The author is asked to make the check
    pass a second implementation of the same requirement, because a check no
    implementation satisfies is usually pinning a detail the specification
    leaves open -- and that is worth one attempt.

    What makes it non-mandatory is the exit: if satisfying the witness is
    impossible, or would contradict what the requirement says, KEEPING THE CHECK
    IS THE CORRECT ANSWER and nothing is rejected for it. The witness is a
    second reading by the same author and has no authority to overrule the text.

    That exit is the whole safety property. Measured when this disagreement
    could REJECT -- when declining meant the oracle was discarded --
    over-strictness went 27 -> 15 and convictions 2 -> 16: oracles relaxed until
    they stopped disagreeing, because compliance was the only way to survive.

    Asked once per oracle, and a replacement is kept only if it still verifies
    (see the repair round). An attempt that makes the check worse leaves the
    previous one standing.
    """
    return Issue(
        "warning", f"oracle.{req_uid}.witness_disagrees",
        f"A second implementation of this same requirement {note}. TRY to make "
        f"your check accept it: a check no implementation satisfies is usually "
        f"pinning a detail the specification leaves open -- an exact edge, a "
        f"count the text does not state, an ordering it does not fix. Relax "
        f"that detail if you find one.\n\n"
        f"THIS IS NOT A DEFECT AND YOU MAY DECLINE. That implementation was "
        f"written from the same text by no better authority than you, so it "
        f"cannot overrule the requirement. If accepting it is impossible, or "
        f"would mean checking something the requirement does not say, KEEP YOUR "
        f"CHECK EXACTLY AS IT IS and say why in `reasoning`. Nothing is "
        f"rejected for declining, and a check contorted to agree is worse than "
        f"a disagreement.")


#: A `live` LIVENESS VERDICT REFUTES A REACHABILITY CLAIM, AND NOTHING ELSE.
#:
#: `liveness` decided the check on a real replay and then moved its verdict by
#: perturbing a port it reads. That is a direct counter-example to "never
#: reached": the check DID decide, so the claim that nothing reaches it was
#: measured false. Keeping it is not a softening -- it is declining to believe a
#: refuted claim.
#:
#: EVERY OTHER GROUND IS OUT OF SCOPE, and the exclusions are the whole of this
#: predicate:
#:
#:   `off-target`      -- correspondence asks whether the oracle tests the
#:       requirement it CLAIMS to. Liveness cannot see that; a check can be
#:       perfectly live and test the wrong thing. Of k1-dcfsm's 24 live discards,
#:       16 are this. Admitting them would launder what this stage has twice been
#:       burned by: turning a number into a verdict it does not support.
#:
#:   `not-assertable` -- the REQUIREMENT states no obligation ("the sentence
#:       lacks an actionable effect"). That is a claim about the spec, not about
#:       the check, and a live check attached to a hollow requirement is testing
#:       something nothing asked for -- off-target wearing another hat. Both of
#:       k1's NOT_ASSERTABLE checks are this, and an earlier draft of this
#:       predicate wrongly matched the string; `test_correspondence` caught it.
#:
#: MEASURED. Of k1-dcfsm's 53 discarded checks 24 are `live`, and 6 of those were
#: held on the reachability ground alone -- so this takes TRUSTED 36 -> 42, not
#: the 36 -> 60 that reprieving every live check would have claimed.
_REACHABILITY_CLAIMS = ("never reached", "unreached")


def _reprieved(reason: str, verdict: str | None) -> bool:
    """True when `verdict` is evidence against the stated `reason`."""
    if verdict != _L.LIVE:
        return False
    text = str(reason or "").lower()
    if "off-target" in text or "not-assertable" in text:
        return False
    return any(claim in text for claim in _REACHABILITY_CLAIMS)


def _liveness(held: dict, witness: str, contract: dict,
              stimulus_by_tp: dict, *, base: str) -> dict:
    """`req_uid -> record` over the checks still standing. `{}` if it cannot run.

    Against the WITNESS, and that costs nothing: the same 70 frozen oracles gave
    identical verdicts against a model scoring 30/168 against golden RTL and
    against the known-good control at 168/168, on all 70. Never raises -- a
    measurement that cannot be taken must not take the stage down with it, which
    is the rule every other instrument here follows.
    """
    if not witness or not held:
        return {}
    try:
        return _L.assess(list(held.values()), witness, contract,
                         stimulus_by_tp, base=base)
    except Exception as exc:  # noqa: BLE001
        logger.info("oracle liveness not measured (%r)", exc)
        return {}


def _decides(oracle, witness: str, contract: dict, stimulus_by_tp: dict,
             *, base: str, transactional: bool = True) -> int:
    """How many of this oracle's own testpoints it reaches a verdict on.

    `decide` returns None exactly when the activation never occurred, so this
    counts the testpoints where the check actually saw its case. Zero means it
    decided nothing anywhere -- which is not a defect on its own (the stimulus
    may simply not stage it) and IS a defect in a replacement, if the check it
    replaces decided something.

    WHY THIS EXISTS. The correspondence gate rejects overwhelmingly on the
    TRIGGER -- 29 of 33 rejections on d1-i2c named it as the thing to fix, 20
    calling a False path "unlicensed by the requirement". The author's only
    move against that instruction is to narrow the activation, and a narrow
    enough activation never fires. Measured on the same run: of the rejected
    checks whose verdict moved across repair, six went from convicting to
    ABSTAINING and three from passing to abstaining -- nine checks that stopped
    deciding under an instruction to be more precise.

    Nothing caught it. `verify_one` rejects for `malformed` and `vacuous` and
    nothing else mechanical, and the post-repair call does not pass a
    `review`, so correspondence -- the one leg that would notice -- sees a
    replacement only at the TOP OF THE NEXT ROUND, which on the last round
    never comes.
    """
    #: **WHEREVER THE STIMULUS GOES, for the same reason everything else that
    #: asks a question about a check does.** This counts testpoints a check
    #: DECIDES on -- a liveness question -- and answering it over `tp_uids`
    #: alone, median 2 of 499, reports a check as deciding nothing whenever its
    #: two attached testpoints happen not to trigger it. That costs span in the
    #: one direction the stage cannot recover from: a check called dead is not
    #: re-asked about, it is discarded.
    n = 0
    for tp in _population_scope(stimulus_by_tp, oracle):
        steps = stimulus_by_tp.get(tp)
        if not steps:
            continue
        rep = replay(witness, contract, steps, base=base)
        rows = transactional_view(rep.rows) if transactional else rep.rows
        result = decide(oracle, rows, unavailable=rep.unavailable)
        if not result.broken and result.ok is not None:
            n += 1
    return n


def _unreached(oracle, record: dict | None, witness: str, contract: dict,
               stimulus_by_tp: dict, *, base: str, transactional: bool,
               silenced: dict[str, str] | None = None) -> str:
    """The check decides nothing AND the stimulus loop already failed to reach it.

    WHY THIS MAY GATE, WHEN "UNEXERCISED IS NOT A FINDING" IS THE MODULE'S OWN
    RULE. That rule is right while the gate runs BEFORE staging: an abstention
    is then ambiguous between a bad check and an unstaged scenario, and
    convicting the check deletes exactly the findings the stimulus tool exists
    to act on. Once staging runs first, every round, the ambiguity has been
    settled by an experiment -- an independent generator was handed this
    activation, retried on evidence, and could not make it occur. "Still decides
    nothing" then means something it could not mean before.

    Measured on d1-i2c, which is what this is for: 16 of 48 frozen checks
    decided nothing at generation and at every repair round, were rejected up to
    twice for a trigger defect no reader could diagnose, and were frozen TRUSTED.

    FIVE GUARDS, each one a scar. A discard must be EARNED by an attempt that
    ran, or the gate rewards not trying. A check whose testpoints carry no
    stimulus at all is a testplan defect, not a check defect. Deciding on SOME
    testpoints is fine and must not fire this. A route whose ports never moved
    is a finding against normalisation and `_diagnose` already says so. And this
    returns a REJECTION, not a disposition: the author is re-asked, and only an
    exhausted repair budget turns it into `ABANDONED`, with the record to prove
    it.
    """
    # EACH GUARD SAYS WHICH ONE FIRED, because returning "" five different ways
    # is indistinguishable in the artifact and the difference is the whole
    # diagnosis. Measured on k1-dcfsm: 19 of 25 ABANDONED requirements never
    # reached a repair round and only 7 carried an `unreached:` objection, so 18
    # were silenced HERE -- and which guard did it could not be recovered from
    # `oracles.json`, because the record keeps the staging attempts but not the
    # verdict this function reached on them. Naming the guard is what makes the
    # next measurement possible; it changes no behaviour.
    def _silent(guard: str) -> str:
        logger.debug("oracles: %s not routed as unreached (%s)",
                     oracle.req_uid, guard)
        if silenced is not None:
            silenced[oracle.req_uid] = guard
        return ""

    if not record:
        return _silent("nothing was attempted")
    attempted = int(record.get("attempted") or 0)
    if not attempted:
        return _silent("attempted == 0")
    if record.get("reached_at_attempt"):
        return _silent("the scenario WAS reached")
    if not any(stimulus_by_tp.get(tp) for tp in oracle.tp_uids):
        return _silent("no stimulus on any testpoint it names")
    if _decides(oracle, witness, contract, stimulus_by_tp,
                base=base, transactional=transactional):
        return _silent("it decides on some testpoint; partial is not silence")
    evidence = [t.get("evidence") or {} for t in (record.get("attempts") or [])
                if t.get("evidence")]
    last = evidence[-1] if evidence else {}
    if last.get("route_never_moved"):
        # The ports this requirement is observed on never moved at all. That is
        # a defect in the observation route, and re-asking the check author for
        # it sends the finding to the one party who cannot act on it.
        return _silent("route_never_moved -- a normalisation defect, not the "
                       "author's")
    said = _diagnose(last) if last else "the scenario was never made to occur"
    return (
        f"unreached: an independent stimulus author was given this check's "
        f"activation and could not make it occur in {attempted} attempt(s) -- "
        f"{said}. The check decided nothing on any of the "
        f"{len(oracle.tp_uids)} testpoint(s) it names, so this is no longer a "
        f"gap in the stimulus. What the last attempt actually produced: "
        f"{json.dumps(last, default=str, sort_keys=True)}. Widen the trigger to "
        f"the condition the requirement states, rather than a narrower one that "
        f"nothing reaches."
    )


def _population_scope(stimulus_by_tp: dict, oracle) -> list[str]:
    """**EVERY TESTPOINT THE STIMULUS HAS, NOT THE TWO THE TESTPLAN ATTACHED.**

    A check is a `decide(trace)` function that says for itself when it applies:
    `decide` returns None exactly when the clause's scenario never occurred.
    Restricting it to `oracle.tp_uids` -- median **2 of 499** on the probe run
    -- is a second, cruder gate on top of that one, and it silently caps what
    any set-level instrument can see. A cell at TP-0400 can only be separated
    by a check that is replayed at TP-0400, so a suite whose checks are each
    pinned to two testpoints is blind almost everywhere BY CONSTRUCTION.

    Measured on the probe run's own three designs and 3,530 cells, at
    `(testpoint, pair)` resolution:

        set                 on own tp_uids   replayed everywhere
        TRUSTED 96                   96.9%                 22.3%
        all 151 first drafts         97.0%                 12.8%

    It is also the honest scope for over-strictness, and the two are the same
    measurement read twice: a check that fires where it should not is exactly a
    check that convicts a design somewhere its requirement does not govern.
    Narrowing the replay hides that instead of fixing it -- and this tree
    already names over-strictness and vacuity as one defect with two signs.

    `oracle` is taken and deliberately unused apart from the assertion below:
    the parameter is what makes the change visible at every call site rather
    than a silent widening, and a future caller wanting the narrow scope has to
    say so by not calling this.
    """
    del oracle  # the scope is a property of the stimulus, not of the check
    return [tp for tp, steps in (stimulus_by_tp or {}).items() if steps]


def _population_tables(held: dict, population: Sequence[str], contract: dict,
                       stimulus_by_tp: dict, *, base: str,
                       transactional: bool) -> tuple[dict, dict, dict]:
    """`(verdicts, by_testpoint, objections)` from ONE set of replays.

    The three instruments -- refutation, cell blindness and `placement` -- want
    three shapes of the same evidence, and each used to replay the population
    for itself. With the scope widened to every testpoint that is 3 x 499
    replays per instrument per round; done once it is 3 x 499 for all of them.

      verdicts       `uid -> design -> bool | None`, testpoints folded away.
                     What the refutation leg wants: does this check convict
                     this design AT ALL.
      by_testpoint   `uid -> testpoint -> design -> bool | None`, one entry per
                     replay performed. What a CELL wants, whose first
                     coordinate is a testpoint -- see `variety.separates_at`.
      objections     `uid -> design -> frozenset(testpoints)`. What `placement`
                     wants: not whether it objected but WHERE.
    """
    rows_by_design = _population_rows(
        population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    absent = _population_unavailable(population, contract, base=base)

    verdicts: dict[str, dict[str, bool | None]] = {}
    by_tp: dict[str, dict[str, dict[str, bool | None]]] = {}
    objections: dict[str, dict[str, frozenset]] = {}
    for uid, oracle in held.items():
        scope = _population_scope(stimulus_by_tp, oracle)
        per: dict[str, bool | None] = {}
        table: dict[str, dict[str, bool | None]] = {}
        obj: dict[str, frozenset] = {}
        for name, rows in rows_by_design.items():
            hits, saw = [], False
            for tp in scope:
                r = rows.get(tp)
                if not r:
                    continue
                try:
                    v = decide(oracle, r, unavailable=absent.get(name, ()))
                except Exception as exc:  # noqa: BLE001
                    logger.info("population decide failed (%r)", exc)
                    continue
                if v.broken or v.ok is None:
                    continue
                saw = True
                table.setdefault(tp, {})[name] = v.ok
                if v.ok is False:
                    hits.append(tp)
            obj[name] = frozenset(hits)
            per[name] = (False if hits else (True if saw else None))
        verdicts[uid] = per
        by_tp[uid] = table
        objections[uid] = obj
    return verdicts, by_tp, objections


def _population_unavailable(population: Sequence[str], contract: dict, *,
                            base: str) -> dict[str, tuple[str, ...]]:
    """`design -> the probes the contract declares and that design does not`.

    Empty for every member of a population this pipeline generated, because it
    generates them from the contract in force. Not empty for a control, a
    standing yardstick design or a benchmark RTL, which is exactly when it
    matters -- see `refmodel.base.probe_values`.
    """
    out: dict[str, tuple[str, ...]] = {}
    for i, src in enumerate(population):
        try:
            rep = replay(src, contract, [{}], base=base)
        except Exception:  # noqa: BLE001
            out[str(i)] = ()
            continue
        out[str(i)] = tuple(rep.unavailable)
    return out


def _population_verdicts(held: dict, population: Sequence[str], contract: dict,
                         stimulus_by_tp: dict, *, base: str,
                         transactional: bool) -> dict:
    """`req_uid -> design index -> verdict` over spec-derived designs.

    Testpoints folded away: what the refutation leg wants. See
    `_population_tables`, and `_population_verdicts_by_tp` for the shape a cell
    needs. Never raises: a measurement that cannot be taken must not take the
    stage down, which is the rule every other instrument here follows.
    """
    return _population_tables(
        held, population, contract, stimulus_by_tp, base=base,
        transactional=transactional)[0]


def _population_verdicts_by_tp(held: dict, population: Sequence[str],
                               contract: dict, stimulus_by_tp: dict, *,
                               base: str, transactional: bool) -> dict:
    """`req_uid -> testpoint -> design index -> verdict`, one entry per replay.

    **THE SAME REPLAYS `_population_verdicts` RUNS, NOT COLLAPSED.** That
    function folds a check's testpoints into one bool per design, which is what
    the refutation leg wants -- "does this check convict this design at all" --
    and is exactly wrong for a cell, whose first coordinate is a testpoint.
    Handing the collapsed table to `variety.blind` made ONE separation stand in
    for every testpoint of the pair: on the probe run, one check separating
    designs 0 and 1 somewhere marked all 966 of that pair's cells adjudicated,
    and blindness read 0.0% of 3,530 cells. At this resolution: 97.0%.

    A testpoint with no stimulus, a replay that raises, and a `None` or broken
    verdict all leave the entry out rather than recording a false one. An
    absent entry separates nothing, which is the rule `separates` already
    applies to an abstention.
    """
    return _population_tables(
        held, population, contract, stimulus_by_tp, base=base,
        transactional=transactional)[1]


def _population_rows(population: Sequence[str], contract: dict,
                     stimulus_by_tp: dict, *, base: str,
                     transactional: bool) -> dict:
    """`design -> testpoint -> rows`, the input `variety.cells` takes."""
    out: dict[str, dict[str, list]] = {}
    for i, src in enumerate(population):
        per: dict[str, list] = {}
        for tp, steps in (stimulus_by_tp or {}).items():
            if not steps:
                continue
            try:
                rep = replay(src, contract, steps, base=base)
                per[tp] = list(transactional_view(rep.rows) if transactional
                               else rep.rows)
            except Exception as exc:  # noqa: BLE001
                logger.info("population replay failed at %s (%r)", tp, exc)
        if per:
            out[str(i)] = per
    return out


def _cell_targets(*, population: Sequence[str], held: dict, contract: dict,
                  stimulus_by_tp: dict, testplan: list[dict],
                  by_uid: dict, normalized: dict | None, budget: int,
                  base: str, transactional: bool) -> list[dict]:
    """The blind cells worth authoring at, heaviest port first.

    A CELL IS A LOCATION. `(testpoint, port, two design names)` where readings
    of the specification come apart and no held check separates them --
    `variety.blind` with the polarity correction on, so a check convicting BOTH
    sides does not count as closing anything. That correction is the whole
    difference between this and the recorded `placement` rule, which kept 24
    checks convicting all seven designs because they scored ~0 by objecting to
    everything.

    **RANKED BY DISAGREEMENT MASS, WHICH READS ONLY THE DESIGNS.** An earlier
    ranking scored cells by whether closing them could change the ACCEPTED set,
    and that was withdrawn: it filters evidence about the suite using the
    suite's own verdicts, and it is non-monotone -- removing a bad check
    re-values cells it had zeroed. Mass is a fact about the population.
    """
    #: THE CONTRACT KEYS ITS PORTS UNDER `io`, WITH A `dir`. An earlier
    #: version of this line read `contract["outputs"]`, which no contract has,
    #: so `outputs` was always empty and the whole lever returned [] on every
    #: run without saying anything -- the silent form of building a lever and
    #: not connecting it. `normalize`, `s3_coverage` and `testcase_agent` all
    #: use the filter below; this is the fourth copy and matches them.
    outputs = [str(p.get("name")) for p in (contract.get("io") or [])
               if p.get("dir") == "output" and p.get("name")]
    if not outputs or len(population) < 2:
        return []
    rows_by_design = _population_rows(
        population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    if len(rows_by_design) < 2:
        return []
    all_cells = variety.cells(rows_by_design, outputs)
    #: **AT `(TESTPOINT, PAIR)`, NOT AT `PAIR`.** See `variety.separates_at`:
    #: the collapsed table this used to read let one separation anywhere close
    #: every cell of a pair, so the probe run -- 12 budget, 3 designs, 3,530
    #: cells -- authored NOTHING because blindness read 0.0%. It reads 97.0%
    #: at the resolution the replays actually have.
    verdicts = _population_verdicts_by_tp(
        held, population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    blind = variety.blind_at(all_cells, verdicts)
    if not blind:
        return []
    weight = dict(variety.ranked(blind))
    #: WHICH REQUIREMENT OWNS A TESTPOINT. `covers` is the testplan's own
    #: attachment and the only non-model route from a testpoint back to a
    #: requirement -- the same source `run_oracle_gen` takes `tp_uids` from.
    covers: dict[str, list[str]] = {}
    for tp in testplan or []:
        uid = str(tp.get("uid") or "")
        for c in (tp.get("covers") or []):
            covers.setdefault(uid, []).append(str(c).split("@")[0])

    #: **ONE TARGET PER REQUIREMENT, AND THAT IS FORCED BY THE DATA MODEL.**
    #: A `RequirementOracle` is keyed by `req_uid`, so two checks authored for
    #: one requirement cannot both be held -- the second overwrites the first.
    #: Deduping per `(testpoint, port)` instead spent a whole budget on three
    #: requirements, nine targets of twelve landing on REQ-0002 alone, and at
    #: most one of those nine could survive. Twelve calls, near-zero possible
    #: yield, by construction.
    #:
    #: **AND THE BUDGET IS SPREAD ACROSS PORTS, NOT POURED INTO THE HEAVIEST.**
    #: `ranked` collapses cells to `(port, count)`, so sorting by that weight
    #: alone put all twelve targets on `sda_oen` -- one port, which is the
    #: opposite of a variety lever. Ports are visited round-robin in weight
    #: order, so the first pass takes the heaviest cell of each port before any
    #: port gets a second.
    by_port: dict[str, list] = {}
    for cell in blind:
        by_port.setdefault(cell.port, []).append(cell)
    for port in by_port:
        by_port[port].sort(key=lambda c: (c.testpoint, c.left, c.right))
    order = sorted(by_port, key=lambda p: (-weight.get(p, 0), p))

    claimed: set[str] = set()
    targets: list[dict] = []
    depth = 0
    while len(targets) < budget and any(len(by_port[p]) > depth for p in order):
        for port in order:
            if len(targets) >= budget:
                break
            if len(by_port[port]) <= depth:
                continue
            cell = by_port[port][depth]
            for uid in covers.get(cell.testpoint, []):
                if uid in claimed:
                    continue
                req = by_uid.get(uid)
                if not req:
                    continue
                shape = (normalized or {}).get(uid) or {}
                act = (shape.get("activation") or {})
                targets.append({
                    "cell": cell,
                    "requirement": req,
                    "tp_uids": [cell.testpoint],
                    "brief": oracle_gen.CellBrief.at(
                        cell,
                        requirement=str(req.get("text") or ""),
                        activation=str(act.get("text") or "")
                        or "whenever the requirement's condition holds",
                        driven=dict(act.get("inputs") or {})),
                })
                claimed.add(uid)
                break
        depth += 1
    return targets


def _population_objections(held: dict, population: Sequence[str], contract: dict,
                           stimulus_by_tp: dict, *, base: str,
                           transactional: bool) -> tuple[dict, dict]:
    """`(verdicts, objections)` -- the second is per TESTPOINT, which placement needs.

    `_population_verdicts` collapses a check to one bool per design. `placement`
    asks WHERE it objected, so it needs the testpoints themselves. Both come
    from `_population_tables`, over every testpoint the stimulus has rather
    than the two `oracle.tp_uids` happens to carry -- see `_population_scope`.
    `placement` scores "how much more often a check speaks where the population
    disagrees than where it agrees", and a check replayed at two testpoints of
    499 has almost no places to speak at.
    """
    v, _by_tp, obj = _population_tables(
        held, population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    return v, obj


#: Discard grounds a corpus body may answer, because they are claims about the
#: BODY that the rescue's own two tests re-decide. Everything else -- a
#: faithfulness label, a control-only rejection, a hollow-requirement route --
#: is a claim about the REQUIREMENT or about evidence this function does not
#: hold, and is terminal here.
#:
#: `vacuous:` is NOT here, and a first draft that included it was wrong: the
#: stage's vacuity instrument is `_cannot_fail` -- "every declared output it
#: names was driven to every other legal value, at both ends of the range, and
#: the verdict did not change once" -- and "decides somewhere on the witness"
#: is strictly weaker. A check can decide on every testpoint and still be
#: unfalsifiable. `test_a_still_inert_replacement_is_KEPT_because_liveness_is_
#: not_the_only_axis` is the test that says so.
#:
#: `malformed:` is not here either: it means there is no normalized form to
#: write a check against, which no other body of the same requirement fixes.
_RESCUABLE = ("over-strict:", "unreached:")


def _rescue_from_corpus(*, corpus: dict, held: dict, blocked: set,
                        reasons_for: dict, witness: str,
                        population: Sequence[str],
                        contract: dict, stimulus_by_tp: dict, base: str,
                        transactional: bool) -> dict:
    """The best body a discarded requirement already has, or nothing.

    **A DISCARD IS ABOUT A BODY, AND A DISPOSITION IS ABOUT A REQUIREMENT.**
    Conflating them is what made a requirement fail because its LAST draft did,
    while an earlier one in the same corpus passes every blocking rule. The
    corpus has existed for exactly this since `_retain` landed -- "a corpus
    containing only survivors has nothing to select from" -- and nothing chose
    from it.

    Two tests, both the stage's own, both golden-free:

      decides    it returns a verdict somewhere on the witness. This is the
                 liveness rule, and a body that decides nothing is vacuous
                 whichever draft it came from.
      not        the whole spec-derived population does not convict it. The
      refuted    specification admits several behaviours here; a check that
                 rejects all of them has rejected the correct one too.

    Ordered NEWEST FIRST, so a repair that fixed something is preferred to the
    draft it replaced, and the first admissible body wins.

    **IT REPLACES A BODY. IT NEVER OVERTURNS A VERDICT.** Two restrictions make
    that true, and the first draft of this had neither -- it re-admitted the
    standing body of every discarded requirement, which silently repealed the
    correspondence gate, the hollow-requirement route and the control-only
    rejection at once. Nine tests said so.

      the ground   only `over-strict:` and `unreached:`, which are exactly the
                   two the tests below ARE the instrument for -- the
                   population refutation is the stage's own over-strictness
                   rule, and a verdict on the witness is the counter-example
                   that overturns "never reached", which is the same evidence
                   `_reprieved` already acts on. `vacuous:` is excluded
                   because "decides somewhere" is strictly weaker than
                   `_cannot_fail`; a faithfulness label is excluded because
                   demoting it is `demote_faithfulness`'s decision and not
                   this function's to make behind its back.
      a different  a candidate whose source is byte-identical to the standing
      body         body is skipped. Re-admitting the very body that was
                   rejected is not a rescue, it is ignoring the verdict, and
                   the two tests here are a SUBSET of the rules that produced
                   it -- so it would pass by construction.
    """
    eligible = {uid for uid in blocked
                if str(reasons_for.get(uid) or "").startswith(_RESCUABLE)}
    standing = {uid: (held[uid].source if uid in held else "") for uid in eligible}
    candidates = {
        uid: [b for b in reversed(corpus.get(uid) or [])
              if b.source != standing.get(uid)]
        for uid in sorted(eligible) if corpus.get(uid)}
    candidates = {uid: bodies for uid, bodies in candidates.items() if bodies}
    if not candidates:
        return {}
    flat: dict[str, RequirementOracle] = {}
    owner: dict[str, str] = {}
    for uid, bodies in candidates.items():
        standing = held.get(uid)
        tps = list(standing.tp_uids) if standing else []
        clause = standing.clause if standing else ""
        for i, body in enumerate(bodies):
            key = f"{uid}#{i}"
            flat[key] = RequirementOracle(
                req_uid=key, tp_uids=tps, clause=clause, source=body.source)
            owner[key] = uid

    #: One pass for the witness and one for the population, rather than one per
    #: candidate: at the wide replay scope that is the difference between a
    #: rescue that runs and one that doubles the stage.
    live, _by_tp, _obj = _population_tables(
        flat, (witness,) if witness else (), contract, stimulus_by_tp,
        base=base, transactional=transactional)
    refuted: set[str] = set()
    #: `> 1` rather than `>= 2`, which is the same number: the refutation leg's
    #: own guard is pinned at the source by a test that finds the FIRST
    #: `>= 2` in this module, and a second spelling of it here would shadow it.
    if len(population) > 1:
        pop_v, _b, _o = _population_tables(
            flat, population, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        refuted = set(variety.refuted_by_the_population(pop_v))

    out: dict[str, RequirementOracle] = {}
    for key, oracle in flat.items():
        uid = owner[key]
        if uid in out:
            continue
        if key in refuted:
            continue
        if not any(v is not None for v in (live.get(key) or {}).values()):
            continue
        out[uid] = RequirementOracle(
            req_uid=uid, tp_uids=list(oracle.tp_uids),
            clause=oracle.clause, source=oracle.source)
    return out


def _select_frozen(trusted: dict, population: Sequence[str], contract: dict,
                   stimulus_by_tp: dict, *, rules, base: str,
                   transactional: bool):
    """Apply a `population.Ruleset` to the set about to be frozen.

    **THE VERDICTS ARE COMPUTED PER TESTPOINT AND HANDED TO `select`, WHICH IS
    USED FOR ITS RULES AND NOT ITS SCORING.** `select` drives a check over a
    population member's rows, and a caller that flattens a design's testpoints
    into one trace gets different answers: measured, per-testpoint scoring and
    a concatenated trace agreed on ONE check of 16 and 27 at `t = 0`. A check
    authored for one testpoint has no business being run over a trace that
    concatenates six others. So each population member is passed as a marker
    row and the closure returns the verdict already computed on the testpoints
    the check NAMES.

    Returns `(selection, shape)`, or `(None, None)` when the rules cannot be
    applied -- a refusal is reported, never silently skipped.
    """
    from . import population as _pop

    outputs = [str(p.get("name")) for p in (contract.get("io") or [])
               if p.get("dir") == "output" and p.get("name")]
    rows_by_design = _population_rows(
        population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    if len(rows_by_design) < 2 or not outputs:
        logger.warning("oracles: selection needs >=2 replayable designs and "
                       "declared outputs; leaving the frozen set unselected")
        return None, None
    verdicts, objections = _population_objections(
        trusted, population, contract, stimulus_by_tp, base=base,
        transactional=transactional)
    shape = _pop.characterise(rows_by_design, outputs)
    names = sorted(rows_by_design)
    #: A MARKER ROW PER DESIGN. `convictions` passes each member to the
    #: closure; the closure reads the marker and returns the precomputed
    #: verdict rather than re-deciding on a trace shape the check never saw.
    members = [[{"__design__": d}] for d in names]

    def decider(uid: str):
        def f(rows):
            d = str((rows or [{}])[0].get("__design__"))
            return verdicts.get(uid, {}).get(d)
        return f

    corpus = {uid: decider(uid) for uid in trusted}
    obj_by_name = {uid: {d: objections[uid].get(str(i), frozenset())
                         for i, d in enumerate(names)}
                   for uid in trusted if uid in objections}
    try:
        sel = _pop.select(corpus, members, ruleset=rules, shape=shape,
                          objections=obj_by_name)
    except ValueError as exc:
        #: REFUSED, NOT SKIPPED. `min_population` defaults to 5 and a run with
        #: three designs will land here -- which is the rule protecting itself,
        #: and it has to be visible rather than read as "selection found
        #: nothing to drop".
        logger.warning("oracles: selection REFUSED and the frozen set is "
                       "unselected: %s", exc)
        return None, shape
    return sel, shape


def _refuted_everywhere(n: int, where: list[tuple[str, str]] | None = None) -> str:
    """The rejection for a check the whole admissible population contradicts.

    **THE DUAL OF `_cannot_fail`, AND THE STAGE BLOCKED ONLY ONE SIGN.** A
    check nothing can move is `DEAD_ORACLE`. A check that convicts every
    spec-derived design is the same defect with the other sign -- the tree's
    own "over-strictness and vacuity as one defect with two signs" -- and
    nothing stopped it.

    Mechanical, and golden-free: the population is spec-derived designs, the
    control is never among them, and the argument is not statistical. The
    specification admits at least seven equivalence classes; a check rejecting
    all of them has rejected the class the correct design is in, unless the
    specification is unsatisfiable.

    `over-strict:` because `_repair_issue` already routes that prefix to the
    relax-it instruction, which is exactly the right ask here.
    """
    return (
        f"over-strict: this check convicts every one of the {n} independently "
        f"written spec-derived designs it was replayed against. They are not "
        f"all wrong in the same way -- the specification admits several "
        f"behaviours here and this rejects all of them, so it has rejected the "
        f"correct one too. No reference was read to determine this.\n\n"
        f"Relax it to what the requirement actually says. If it pins a detail "
        f"the specification leaves open -- which edge a response lands on, an "
        f"exact count the text does not state, an ordering it does not fix -- "
        f"that detail is where the over-strictness is."
        + _fired_at_block(where)
    )


def _fired_at_block(where: list[tuple[str, str]] | None) -> str:
    """The testpoints every reading was convicted at, and what they drive.

    **THE FIRST VERSION OF THIS MESSAGE GAVE NO LOCATION AT ALL**, and an
    author told only "you convict all of them" has to guess which of its
    clauses is wrong and which scenario made it wrong. Your check runs on every
    testpoint the suite drives -- see SYSTEM -- so the commonest cause is not a
    detail pinned too tightly inside the window but a window that opened
    somewhere the requirement does not govern, and only the location
    distinguishes the two.
    """
    if not where:
        return ""
    lines = "\n".join(f"  {tp}  {said}" if said else f"  {tp}"
                       for tp, said in where)
    return (
        f"\n\nIT FIRED, AND EVERY READING WAS CONVICTED, AT THESE TESTPOINTS:\n\n"
        f"{lines}\n\n"
        f"These are scenarios this suite drives, with the stimulus written for "
        f"them -- not any design's behaviour. Read them and ask whether your "
        f"requirement governs them at all. If it does not, the defect is the "
        f"window rather than the assertion: make the activation FALSE there, "
        f"using `aborts_on`, `until` or the conditions that cannot hold outside "
        f"the requirement's situation, and keep the assertion exactly as strong "
        f"as the obligation states. If it does govern them, then the assertion "
        f"pins something the specification leaves open in that scenario, and "
        f"that is what to relax."
    )


def _where_it_fired(objections: dict, testplan: list[dict], *,
                    limit: int = 3) -> list[tuple[str, str]]:
    """`[(testpoint, its own scenario prose)]` where EVERY design was convicted.

    **A LOCATION AND THE PIPELINE'S OWN STIMULUS -- NEVER A DESIGN'S
    BEHAVIOUR.** The population may only refute; the witness is the one that
    may repair. So what travels to the author is the testpoint id and the
    scenario S2 wrote for it, both of which are this pipeline's own inputs and
    were already in the author's prompt for its own testpoints. No design's
    source, no design's values, and no claim that any of them is correct.

    That distinction is the same one `CellBrief` makes, and it is made for the
    same measured reason: presenting behaviours and asking which is meant makes
    them the answer set, and it reproduces the pathology the witness gate was
    deleted for -- "it does not make the check more correct, it makes the check
    agree with the witness", h-i2c over-strictness 27 -> 15, convictions
    2 -> 16.

    The INTERSECTION across designs, not the union: a testpoint where only some
    were convicted is an ordinary disagreement, and the refutation is about the
    places every reading was rejected. Three of them, because a list of forty
    testpoint ids is not a location, it is a wall.
    """
    sets = [set(v) for v in objections.values()]
    if not sets:
        return []
    everywhere = set.intersection(*sets) if len(sets) > 1 else sets[0]
    prose = {str(t.get("uid")): str(t.get("stimulus") or "") for t in testplan or []}
    out = []
    for tp in sorted(everywhere)[:limit]:
        said = prose.get(tp, "")
        out.append((tp, said[:240] + (" ..." if len(said) > 240 else "")))
    return out


def _cannot_fail(detail: str) -> str:
    """The rejection reason for a check no legal value can move.

    A REASON STRING, not an `Issue`, because this is now blocking: it flows
    through `rejected`/`quotable` like `malformed:` and `off-target:`, buys a
    repair round on the same terms, and leaves the check VACUOUS if it stays
    dead. It was an advisory `Issue` until the loop was measured losing work to
    it -- see the note at the `dead_now` fold.

    The text is the old advisory's, minus its offer to decline. A blocking gate
    cannot invite the author to keep the check as-is. What survives is the one
    escape that is not a decline: if the requirement constrains nothing
    observable, saying so is the right answer, and it routes to spec authoring
    rather than back to the author.
    """
    lead = f"{detail}. " if detail else ""
    return (
        f"vacuous: this check cannot fail. {lead}Every declared output it names "
        f"was driven to every other legal value -- one step away and at both "
        f"ends of the range, across the whole trace and at single edges -- and "
        f"the verdict did not change once.\n\n"
        f"That usually means one of three things. The check reads a port to "
        f"find its activation window but never ASSERTS on any port. Its "
        f"comparison is true for every value the port can carry, so it restates "
        f"the port's width rather than the requirement. Or its trigger cannot "
        f"fire, so the body it guards never runs.\n\n"
        f"Rewrite it so there is some legal output value it rejects, and name "
        f"that value in `reasoning`. If the requirement genuinely constrains "
        f"nothing observable at the boundary, say THAT instead -- a requirement "
        f"with no observable is a finding about the specification, not "
        f"something to invent an assertion for.")


def _reconsider_issue(req_uid: str, why: str) -> Issue:
    """Evidence that has been earned, unlike gate 1's, and still not authority.

    Gate 1 asks this question once, before any reference model exists, on the
    strength of one second reading. This asks it again after a debug loop has
    spent its whole budget failing to satisfy the check -- so the claim is no
    longer "another author disagrees" but "two independent implementations and
    every edit a repair loop could think of, and none of them satisfied it".

    That is a much stronger case and it is still not a verdict, because the
    thing it cannot distinguish is the one that matters: a check pinning a
    detail the specification leaves open looks exactly like a check pinning a
    detail two implementations both got wrong. Only the requirement decides,
    and the author is the one reading it.

    So the exit stays open, for the reason it stayed open in `_advisory`: when
    this disagreement could REJECT, over-strictness fell 27 -> 15 and
    convictions rose 2 -> 16 -- checks relaxed until they stopped disagreeing,
    because compliance was the only way to survive. A relaxation that goes too
    far fails `verify_one` as vacuous and the previous check stands.
    """
    return Issue(
        "warning", f"oracle.{req_uid}.unsatisfied_by_two_implementations",
        f"Nothing has been able to satisfy this check. A second implementation "
        f"of this same requirement {why}, and a repair loop then spent its "
        f"entire turn budget editing a third and still could not make it "
        f"pass.\n\n"
        f"The usual cause is a detail the requirement does not actually state: "
        f"an exact edge, a count the text leaves open, an ordering it does not "
        f"fix, a value it does not name. Read the clause again and check "
        f"whether your check demands more than it says. If it does, decide "
        f"only what the clause decides.\n\n"
        f"THE OTHER POSSIBILITY IS REAL AND YOU MAY CHOOSE IT. Two "
        f"implementations can be wrong in the same way, especially where the "
        f"requirement is subtle -- that is exactly the case a check like yours "
        f"exists to catch, and relaxing it would delete the finding. If you "
        f"read the clause and your check decides what it says, KEEP IT AS IT "
        f"IS and say why in `reasoning`. Nothing is rejected for that, and a "
        f"check contorted until it stops disagreeing is worth less than a "
        f"disagreement.")


def _standing(held: dict, uids) -> dict[str, str]:
    """The check each author is being asked to revise, shaped like a reply.

    `run_stage` fills `previous` with the model's own prior attempt inside one
    call's repair loop, so on the FIRST attempt of a repair round it is empty --
    and both repair rounds were therefore saying "tighten your check" and
    "fix your check" to an author holding no copy of it. Rendered as the same
    JSON object the author is asked to return, because the instruction that
    follows says "reply with the full corrected JSON object".
    """
    out = {}
    for uid in uids:
        o = held.get(uid)
        if o is not None and getattr(o, "source", ""):
            out[uid] = json.dumps({"clause": o.clause, "source": o.source},
                                  indent=2, ensure_ascii=False)
    return out


def _repair_issue(req_uid: str, why: str, apart: str = "") -> Issue:
    """The rejection, phrased as something an author can act on.

    Not "your oracle was discarded": that names an outcome, not a defect. The
    text `trust.screen` already writes for these cases said what was wrong and
    was thrown away, because nothing downstream re-asked.
    """
    if why.startswith("over-strict:"):
        return Issue(
            "error", f"oracle.{req_uid}.over_strict",
            f"{why}. One of the two readings is wrong and it may be either -- "
            f"but a check no reading of the requirement satisfies can never be "
            f"discharged by anyone. If your check pins a detail the "
            f"specification leaves open -- which edge the response lands on, an "
            f"exact count the requirement does not state, an ordering the text "
            f"does not fix -- relax it to what the requirement actually says.")
    if why.startswith("vacuous:"):
        if apart:
            # The counterexample REPLACES the generic ask, for the reason
            # `_witness_note` gives about the idle-match note: sending "check
            # the specific behaviour the clause states" alongside an exact
            # disagreement invites a rewrite when there is a repair.
            return Issue("error", f"oracle.{req_uid}.vacuous",
                         f"Your check {apart}")
        return Issue(
            "error", f"oracle.{req_uid}.vacuous",
            f"{why}. It passes designs that provably violate this requirement, "
            f"so it cannot tell a correct design from a broken one and proves "
            f"nothing. Check the specific behaviour the clause states.")
    return Issue("error", f"oracle.{req_uid}.malformed", why)


def run_oracle_stage(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    port: ModelPort,
    #: The variant author, when it should not be the oracle author. Variants are
    #: WRONG implementations of a requirement -- the must-fail leg of the vacuity
    #: check -- so the job is breadth, not the care an oracle needs, and paying
    #: oracle-grade inference for ~700 of them is the largest avoidable cost in
    #: this stage. Defaults to `port`, which is what every caller did implicitly
    #: before this existed.
    variant_port: ModelPort | None = None,
    workdir: Path,
    base: str = "step",
    normalized: dict[str, dict] | None = None,
    #: The source document S1 read. Passed to `correspondence.review`, whose
    #: `build_prompt` puts it AHEAD of the requirement expressly "so the shared
    #: prefix stays cacheable across the fan-out" -- and which never received it,
    #: so that prefix was `SYSTEM` alone at ~471 tokens, under the provider's
    #: 1024-token cache floor. Measured on a2-i2c: correspondence came back at
    #: 12% cached over 315 calls, against 65-83% for every other fan-out.
    #:
    #: Strictly upstream of every artifact here -- it is what S1 read -- so it
    #: cannot carry anything the pipeline produced back into the gate.
    spec: str = "",
    #: A known-good implementation, where the design has one. Preferred over a
    #: generated witness and recorded as such.
    control_source: str | None = None,
    #: Separate port for the witness, so it can be a DIFFERENT model from the
    #: one writing the oracles. Same author for both is the shared-misreading
    #: confound this stage cannot otherwise touch.
    witness_port: ModelPort | None = None,
    want_variants: bool = False,
    #: Ask a reviewer, per oracle, whether it decides the requirement it names.
    #: One call each. The only blocking gate that is not mechanical, and the
    #: only check of any kind that connects an oracle to ITS requirement --
    #: without it nothing does, on a run with no variants.
    want_correspondence: bool = False,
    #: Stage the scenarios nothing reaches, before anything is frozen.
    #:
    #: ON, because the alternative is measured and it is worse. z-i2c ended with
    #: 33 unexercised oracles and `stimulus_added: 0` on all three debug turns:
    #: a third of the set decided nothing, and the only route to stage one was a
    #: tool inside a turn that never called it. Off by default meant the
    #: pipeline's answer to "nothing reaches this requirement" was to report it.
    #:
    #: It costs a model call per attempt, bounded by `staging_attempts` and by
    #: `staging_budget` -- and it is cheaper than the alternative it replaces,
    #: which is a debug loop spending turns on findings no edit can discharge.
    want_staging: bool = True,
    staging_attempts: int = STAGING_ATTEMPTS,
    #: [O]'s own budget, separate from the debug loop's. A scenario found before
    #: the model exists is not competing with one found after it.
    staging_budget: int | None = None,
    run_dir: Path | None = None,
    max_repairs: int = 2,
    #: Verify-repair-verify rounds over the whole set, on top of the per-oracle
    #: repairs `run_stage` already does inside generation.
    #: REPAIR ATTEMPTS an oracle gets, not verification rounds. It was
    #: `max_rounds: int = 2` and that name is why this sat wrong: the loop
    #: breaks at `rounds == max_rounds` BEFORE re-asking, because the last round
    #: has nothing left to verify its answer, so 2 rounds bought exactly ONE
    #: attempt.
    #:
    #: Measured on z-i2c with one attempt each: 16 oracles were rejected as
    #: vacuous and 8 were rescued -- 50%. s-i2c, with one attempt and no
    #: counterexample, rescued 13 of 24 -- 54%. So the counterexample did not
    #: move the conversion rate, and the surviving 8 audit CLEAN: 20 variant
    #: replays, 0 never-triggered, 0 indistinguishable at the oracle's own
    #: ports. They are genuine vacuity, correctly convicted, on one attempt.
    #:
    #: A second attempt is therefore the cheap untested lever -- roughly one
    #: call per still-rejected oracle, ~28 on a 116-requirement draw.
    #:
    #: IT ALSO PUSHES TIGHTER, and tightening is what makes checks over-strict:
    #: on s-i2c, 46% of repaired-and-kept oracles were failed by the known-good
    #: control against 6% of never-repaired. Nothing rejects for strictness, so
    #: this cannot be guarded -- only reported, via `over_strict_after_repair`,
    #: which is why that field has to be read beside any gain claimed here.
    repair_attempts: int = 2,
    #: **THE ADMISSION ARM.** Demote every FAITHFULNESS ground from a discard to
    #: a label: correspondence's verdict, the prose "no discrimination stated"
    #: abandonment, and the "normalization produced no form" abandonment. What
    #: still blocks is mechanical and asks only whether the check RUNS --
    #: `well_formed`, a replay break, and `DEAD_ORACLE` -> `vacuous:`.
    #:
    #: Default False, so nothing changes until the experiment says it should.
    #: Measured on the two surviving frozen sets, this is 8 of 8 and 19 of 19
    #: discards: TRUSTED 15 -> 23 and 24 -> 43 with nothing left blocked.
    demote_faithfulness: bool = False,
    #: INDEPENDENTLY WRITTEN SPEC-DERIVED DESIGNS, as rendered sources. A check
    #: convicting every one of them is rejected -- see `_refuted_everywhere`.
    #:
    #: **WHY IT IS AN INPUT AND NOT SOMETHING THIS STAGE BUILDS.** The pipeline
    #: runs oracles BEFORE `run_refmodel`, on purpose: "an oracle written after
    #: the model exists is written by something that could have read it." So at
    #: authoring time a run has ZERO designs, and a population can only come
    #: from runs that already finished -- which is exactly the provenance of
    #: the nine `*-i2c.ref_model.py` designs the evidence drivers use. Passing
    #: them in keeps that ordering guarantee intact.
    #:
    #: **NOT THE CONTROL, AND STRUCTURALLY SO.** `control_source` is a separate
    #: parameter and is never added here. These are spec-derived; the rule
    #: reads no reference and no grade.
    #:
    #: Fewer than two is not a population -- one design convicting a check is
    #: an ordinary disagreement -- so the leg stays off below that.
    population: Sequence[str] = (),
    #: GENERATE the population here instead of being handed one. k calls to the
    #: same generator that writes the witness, each in its own workdir so the
    #: cache returns independent readings rather than one reading k times.
    #:
    #: **THIS DOES NOT BREAK THE ORDERING GUARANTEE.** What that guarantee
    #: forbids is an oracle written by something that could have read THE
    #: SHIPPED DESIGN, which `run_refmodel` produces after this stage. These are
    #: throwaway readings of the requirements, like the witness, and the shipped
    #: model is still written later and independently.
    #:
    #: Off at 0. Costs k conforming-implementation calls, paid once and held on
    #: disk. Ignored when `population` is supplied directly.
    population_size: int = 0,
    #: HOW MANY DISAGREEMENT CELLS TO AUTHOR A CHECK AT, after the per
    #: requirement pass. This is the generation-stage variety lever: the author
    #: is handed a LOCATION the suite is silent on rather than a requirement it
    #: already has a check for, so the anchor differs per call.
    #:
    #: Needs a population -- a cell is a place two spec-derived designs come
    #: apart -- so 0 unless `population`/`population_size` gives it one.
    #:
    #: **PRE-REGISTERED, AND IT CAN CLOSE THIS LINE.** Varying the stimulus
    #: ROUTE to a scenario was pre-registered at >=40% = lever, <15% = closed,
    #: and delivered 1 of 20 = 5% fully caught. This varies the check that
    #: ADJUDICATES one, which is the untried half. If it also returns <=15%,
    #: generation cannot reach the residual blindness and the honest output is
    #: the irreducible equivalence classes as a specification finding.
    cell_budget: int = 0,
    #: A `population.Ruleset` applied to the frozen set, so a run FREEZES THE
    #: SELECTED SET rather than leaving selection an afterthought nobody runs.
    #: `population` was imported by `scoring` alone -- no pipeline module
    #: touched it -- so every selection figure on this branch was post-hoc.
    #:
    #: Needs a population, for the same reason the refutation leg does. `None`
    #: leaves the frozen set unselected, which is what every run so far did.
    #:
    #: **A REFUSAL IS REPORTED, NEVER SKIPPED.** `Ruleset.min_population`
    #: defaults to 5, so a three-design run is refused by design; that has to
    #: read as "the rule declined" and not as "the rule found nothing".
    selection: "object | None" = None,
    transactional: bool = True,
    fanout: bool = True,
    #: THE FEEDBACK EDGE. A check a debug loop spent its whole budget on and
    #: could not satisfy, while a second implementation of the same requirement
    #: fails it too.
    #:
    #: Measured on s-i2c: the loop drove VIOLATES 15 -> 9, and 7 of the 9 left
    #: are checks the known-good control also fails. Those 7 block the gate,
    #: which is why no RTL is produced from a reference model that scores its
    #: best separation yet -- the residue is the checks, not the design. The
    #: witness had flagged 8 of the 9, catching 7 of 7 with one false alarm and
    #: no misses.
    #:
    #: Regeneration, never rejection, and the prompt says so: two
    #: implementations failing the same check usually means it pins a detail
    #: the text leaves open, and sometimes means both got the same thing wrong.
    #: Only the author can tell, and keeping the check is a valid answer.
    reconsider: dict[str, str] | None = None,
    previous: OracleSet | None = None,
    #: Something upstream regenerated, so the frozen artifacts are about
    #: requirements that no longer exist. Written once means once PER REQUIREMENT
    #: SET, not once per directory -- without this the stage would spend its
    #: fan-out generating oracles and then silently keep the stale file, and the
    #: loop would measure the new model against the old requirements' checks.
    rewrite: bool = False,
) -> OracleSet:
    """Generate, verify, repair, freeze. Returns a disposition for every requirement.

    A STRENGTHENING ROUND IS THIS STAGE, SCOPED -- not a smaller copy of it.

    It used to dispatch to `_strengthen`, which reimplemented a subset: one
    generation, one `verify_one`, keep-or-revert. No repair loop, no
    correspondence, no liveness routing, and later no stimulus loop either --
    so the second iteration of the refmodel/oracle loop ran on strictly weaker
    instruments than the first, and which instruments it lost was decided by
    which keyword arguments a call site in `compose` happened to pass.

    Scoping with `only` gives every round the same tools by construction. What
    a scoped round skips is only what cannot have changed: variants are per
    requirement and are inherited, and the witness is read back from disk
    exactly as `_witness` already does for the same reason.
    """
    scoped = set(reconsider or {})
    if scoped and previous is not None:
        # INHERITED, not re-specified. A caller that forgets one of these does
        # not get a quieter round, it gets the same round.
        inherited = dict(previous.tools or {})
        want_correspondence = inherited.get("correspondence", want_correspondence)
        want_variants = inherited.get("variants", want_variants)
        want_staging = inherited.get("staging", want_staging)
        max_repairs = inherited.get("max_repairs", max_repairs)
        repair_attempts = inherited.get("repair_attempts", repair_attempts)
        only = scoped
        feedback = {
            **{uid: [_reconsider_issue(uid, why)]
               for uid, why in (reconsider or {}).items()},
        }
        standing = _standing({o.req_uid: o for o in previous.trusted}, scoped)
        label = f"_reconsider{previous.rounds}"
    else:
        only, feedback, standing, label = None, None, None, ""

    if rewrite and run_dir is not None:
        for name in (ARTIFACT, "variants.json", "witness.py",
                     # The ratchet records which REQUIREMENT UIDS have been
                     # exercised, and uids are re-minted contiguously per run --
                     # so against a new requirement set REQ-0005 may name a
                     # different requirement, and a "stopped being exercised"
                     # finding would accuse the model of losing a scenario that
                     # was never its.
                     "exercised.json"):
            (Path(run_dir) / "specflow" / name).unlink(missing_ok=True)

    witness, witness_kind = _witness(
        requirements=requirements, contract_json=contract_json,
        port=witness_port or port, workdir=workdir, run_dir=run_dir)
    control = control_source or ""
    if control:
        witness_kind = (f"{WITNESS}+{CONTROL}" if witness else CONTROL)

    # THE POPULATION, ALONGSIDE THE WITNESS AND FOR THE SAME REASONS. Both are
    # spec-derived readings written from the requirements alone, both are held
    # on disk so they hold still across rounds, and neither is ever shown to an
    # oracle author. They differ in what they are ALLOWED to do: a witness may
    # repair, a population may only refute.
    if not population and population_size:
        population = _population(
            size=population_size, requirements=requirements,
            contract_json=contract_json, port=port, workdir=workdir,
            run_dir=run_dir)

    # GENERATED ONCE, FROM THE WITNESS, AND THEN NEVER AGAIN.
    #
    # A variant is a wrong implementation of ONE requirement, and the
    # requirement does not change. Regenerating spends a call per requirement to
    # rebuild the same evidence -- and worse, a DIFFERENT DRAW of it, so an
    # oracle can be convicted vacuous this round and cleared the next for no
    # reason anyone could name. `variants_mod.save` already refuses to overwrite
    # for exactly that reason: "the must-fail leg is only evidence if the thing
    # it fails to catch holds still."
    #
    # Three things had to be true for "once" to mean once, and only the first
    # was. In-process inheritance (`previous.variants`) covers a scoped round;
    # it does NOT survive the process, and the stage is long enough that it
    # routinely does not get to finish in one. So the artifact is consulted
    # before generating, and written the moment they exist rather than at the
    # end of the stage. Measured cost of the gap on a2-i2c: a restart during [O]
    # discarded 159 variant calls -- about 1.3M input tokens -- to rebuild a
    # file whose own writer would have refused to overwrite it.
    #
    # Reusing the artifact is safe because `rewrite` above unlinks it: when the
    # requirement set changes, these variants are about requirements that no
    # longer exist, and they are deleted before this point rather than reused.
    variants_path = (Path(run_dir) / "specflow" / "variants.json"
                     if run_dir is not None else None)
    variants: list = list(previous.variants) if only and previous else []
    if not variants and variants_path is not None:
        variants = variants_mod.load(variants_path)
        if variants:
            logger.info("oracles: %d variant(s) reused from %s -- generated "
                        "once, from the witness", len(variants),
                        variants_path.name)
    if want_variants and witness and not only and not variants:
        from .obligation import by_requirement

        variants, _ = variants_mod.run_variant_gen(
            requirements=requirements, contract_json=contract_json,
            contract=contract, conforming_source=witness,
            stimulus_by_tp=stimulus_by_tp,
            tp_by_req=by_requirement(testplan), port=variant_port or port,
            normalized=normalized, base=base, fanout=fanout,
        )
        logger.info("oracles: %d variant(s) for %d requirement(s)",
                    len(variants), len({v.req_uid for v in variants}))
        # PERSISTED HERE, not at the end of the stage. Everything after this
        # point -- oracle generation, verification, repair, the stimulus loop --
        # can fail or be interrupted, and none of it changes what a variant is.
        if variants_path is not None:
            variants_mod.save(variants, variants_path)

    oracles, _results = run_oracle_gen(
        requirements=requirements, contract_json=contract_json,
        contract=contract, testplan=testplan, port=port,
        normalized=normalized, conforming_source=witness,
        stimulus_by_tp=stimulus_by_tp, base=base,
        max_repairs=max_repairs, fanout=fanout,
        only=only, feedback=feedback, standing=standing,
        label=label,
    )
    held: dict[str, RequirementOracle] = {o.req_uid: o for o in oracles}
    by_uid = {str(r.get("uid") or ""): r for r in requirements}

    # AUTHORING AT DISAGREEMENT CELLS -- the generation-stage variety lever,
    # in the same place as the per-requirement pass because it is the same
    # author and the same gate with a different ANCHOR.
    #
    # Resampling one prompt returns 69% identical bodies among sound pairs: it
    # samples one interpretation rather than producing another. A cell differs
    # per target, which is the untried half of the variety question.
    #
    # ADDITIVE, NOT A REPLACEMENT. A cell check is keyed by the requirement it
    # comes from, so it can only supersede that requirement's draft when the
    # draft decided nothing -- otherwise the per-requirement pass would be
    # silently overwritten by a check written for one port.
    cell_authored: list[str] = []
    cell_bodies: list[RequirementOracle] = []
    #: **THE LEG REPORTS WHY IT DID NOTHING, BECAUSE SILENCE COST A WHOLE RUN.**
    #: A run configured with `cell_budget=12` and a population of three
    #: produced zero cell bodies and zero prompts, and the artifact recorded
    #: nothing about it -- so "the budget never arrived", "no cell was blind"
    #: and "the author declined" were indistinguishable after the fact. Offline
    #: on that run's own artifacts `_cell_targets` returns 12, and a stubbed
    #: stage reaches it with the budget intact, so the cause is in-run state
    #: that nothing preserved. `logger.info` is not enough: it does not survive
    #: into the artifact a reader has.
    cell_report: dict[str, object] = {
        "budget": int(cell_budget or 0),
        "population": len(population),
        "targets": None,
        "authored": None,
        "adopted": None,
    }
    if cell_budget and len(population) >= 2:
        targets = _cell_targets(
            population=population, held=held, contract=contract,
            stimulus_by_tp=stimulus_by_tp, testplan=testplan, by_uid=by_uid,
            normalized=normalized, budget=cell_budget, base=base,
            transactional=transactional)
        cell_report["targets"] = len(targets)
        logger.info("oracles: %d blind cell(s) to author at", len(targets))
        for extra in run_cell_gen(
                targets=targets, contract_json=contract_json, contract=contract,
                port=port, testplan=testplan, normalized=normalized, spec=spec,
                siblings=by_uid, conforming_source=witness,
                stimulus_by_tp=stimulus_by_tp, base=base,
                max_repairs=max_repairs, fanout=fanout, label=f"{label}_cell"):
            standing_body = held.get(extra.req_uid)
            if standing_body is not None and _decides(
                    standing_body, witness, contract, stimulus_by_tp,
                    base=base, transactional=transactional):
                #: The requirement already has a check that decides something.
                #: Keeping the cell check would cost that one its place, so it
                #: goes to the corpus for selection and not to `held`.
                cell_bodies.append(extra)
                continue
            held[extra.req_uid] = extra
            cell_bodies.append(extra)
            cell_authored.append(extra.req_uid)
        cell_report["authored"] = len(cell_bodies)
        cell_report["adopted"] = len(cell_authored)
        logger.info("oracles: %d cell check(s) adopted of %d authored",
                    len(cell_authored), len(cell_bodies))

    #: **A1: THE CORPUS STARTS AT GENERATION, NOT AT REPAIR.** Retaining only
    #: superseded bodies records nothing at all for a run that never repairs --
    #: which is most requirements -- so the first draft is a member too. This
    #: was a real defect: the first wiring hooked only the repair-accept path
    #: and a stage-level test found the corpus empty.
    corpus: dict[str, list[CorpusBody]] = {}
    for _first in oracles:
        _retain(corpus, _first, arm="generate", round_=0)
    #: CELL BODIES ARE CORPUS MEMBERS WHETHER OR NOT THEY WERE ADOPTED. One
    #: that lost its place to a deciding draft is exactly what selection exists
    #: to choose between, and dropping it here would make the lever look like
    #: it produced nothing. `arm` says where it came from.
    for _extra in cell_bodies:
        _retain(corpus, _extra, arm="cell", round_=0)

    rejected: dict[str, str] = {}
    repairs: dict[str, list[str]] = {}
    #: Per-round correspondence outcomes -- see `OracleSet.correspondence_rounds`
    #: for why the round index is the field that matters.
    correspondence_rounds: list[dict] = []
    #: `req_uid -> which `_unreached` guard silenced it`. Last write wins: a
    #: check re-examined each round should be attributed to the guard that
    #: silenced it on the round whose verdict actually shipped.
    unreached_silenced: dict[str, str] = {}
    #: `req_uid -> the oracle body last put to correspondence`, and the verdicts
    #: it returned. Together they make the gate one draw per DISTINCT check
    #: rather than one per round -- see the review call site.
    #: `req_uid -> [{round, was, now}]` for every accepted repair that changed
    #: how many testpoints the check decides on. See the accept site.
    narrowing: dict[str, list[dict]] = {}
    _reviewed: dict[str, str] = {}
    _carried: dict[str, object] = {}
    #: `req_uid -> the faithfulness ground that no longer discards it`. Recorded
    #: so the disposition still carries the observation and the debug loop can
    #: weight it; never consulted by anything that decides.
    labels: dict[str, str] = {}
    #: `req_uid -> why we gave up`, one of `verdict.ABANDONED_REASONS`. These
    #: leave the frozen set entirely -- see the exclusion below. Populated only
    #: by a stage that RAN a bounded attempt and exhausted it; empty here means
    #: nothing has been attempted yet, and nothing may be discarded on that
    #: basis. Step 2 of the plan fills it from the stimulus loop.
    abandoned: dict[str, str] = {}

    # NO NORMALIZED FORM, NO ORACLE.
    #
    # Normalization already refuses to ship a requirement whose form failed its
    # own gate: `gate_one` raises an Issue on a Parse Error, `run_stage` spends
    # the whole repair budget on it, and the merge loop drops it under "A
    # REQUIREMENT WHOSE NORMALIZED FORM NEVER PASSED ITS OWN GATE DOES NOT
    # SHIP." That is right, and it fired.
    #
    # THIS STAGE THEN AUTHORED A CHECK ANYWAY. It iterates `requirements` and
    # reads the shape as `(normalized or {}).get(uid) or {}`, so a requirement
    # with NO record is silently an empty activation and nothing says so. It is
    # the mirror of the bug normalization already closed: stopping "a REJECTED
    # form ships" left "NO form ships" open.
    #
    # MEASURED on c1-i2c: five requirements -- REQ-0010, REQ-0017, REQ-0048,
    # REQ-0078, REQ-0100 -- reached the author with no activation and no
    # observation route, and every one got a check. REQ-0010's is the naive "no
    # output may change on any input edge", which is what authoring from the
    # text alone looks like; it later INVERTED, passing a design that had
    # deleted its input filter and convicting the golden one.
    #
    # They leave as MALFORMED rather than quietly absent, because the
    # denominator has to show them: a requirement nobody could write a check
    # for is a finding, and dropping it silently is how coverage comes to look
    # better than it is.
    if normalized is not None:
        for _uid in sorted(by_uid):
            if _uid and _uid not in normalized and demote_faithfulness:
                # The form failed a FAITHFULNESS gate. Whether the check that
                # was authored anyway can run is a separate question, and the
                # structural gate below already asks it.
                labels[_uid] = "malformed: normalization produced no form"
            elif _uid and _uid not in normalized:
                rejected[_uid] = abandoned[_uid] = (
                    "malformed: normalization produced no form for this "
                    "requirement -- it failed its own gate and exhausted its "
                    "repair budget -- so there is no activation, no observable "
                    "and no observation route to write a check from. The one "
                    "measured case convicted the known-good design while "
                    "passing a candidate that had deleted the behaviour")
    #: What the stimulus loop staged, per requirement. Declared here because the
    #: loop that fills it now runs inside the verify rounds.
    staging: dict[str, dict] = {}
    #: What is LEFT of the stage's one staging budget. Sized on first use and
    #: spent down across rounds, because the loop that spends it now runs once
    #: per round and a per-round budget would triple the stimulus calls.
    staging_left: int | None = None
    #: Oracles a repair round made newly unsatisfiable to the known-good
    #: control. REPORTED, never acted on -- see the round body for why the
    #: control may not select which oracles survive.
    newly_over_strict: set[str] = set()
    #: `req_uid -> {instrument: what it observed}`. Never rejections: no
    #: implementation gates an oracle here. Recorded so the cost of not gating
    #: is visible -- an oracle a known-good design fails still reaches the debug
    #: agent, and the artifact must say so rather than let the attempts look
    #: unexplained.
    disagreements: dict[str, dict[str, str]] = {}
    #: Oracles already given gate 1's note. Asked ONCE: a disagreement that
    #: recurs every round would spend a call per round on an author who has
    #: already answered, which is pressure by repetition.
    advised: set[str] = set()
    #: The last liveness measurement any round took, reused for the artifact.
    #: Recomputing it afterwards would replay every named testpoint a second
    #: time to answer a question already answered about the same checks.
    alive: dict = {}
    rounds = 0
    # One verification pass per attempt, plus a final one to judge the last
    # answer -- an attempt whose reply nothing checks is not an attempt.
    verifications = max(0, int(repair_attempts)) + 1
    for rounds in range(1, verifications + 1):
        rejected = {}
        disagreements = {}
        quotable: dict[str, str] = {}
        # STAGE BEFORE THE GATES, AND EVERY ROUND. The order is the fix.
        #
        # It used to run AFTER the gates and only at `rounds == 1`, over
        # `survivors = held - rejected`. Two filters, and together they made the
        # routes one-way: a check rejected in round 1 was excluded from staging
        # and staging never ran again, so it could be rewritten twice and never
        # once be given stimulus. Measured on d1-i2c: 16 of 48 frozen checks
        # decided nothing at generation and at every repair round, 15 of them
        # rejected for a trigger defect, and NOT ONE was staged -- while 17 of
        # the 23 staging slots went to checks nobody had flagged.
        #
        # Here `rejected` is empty, because the gate has not run yet. So the
        # `survivors` filter does not need removing: it cannot be expressed.
        # Eligibility is one predicate -- this check decides nothing.
        #
        # And it makes `_unreached` legitimate below. A gate may only convict an
        # abstaining check once the stimulus route has actually been tried.
        if want_staging and witness:
            from .normalize import Activation

            unexer = unexercised_against(
                held, witness, contract, stimulus_by_tp, base=base,
                transactional=transactional)
            # AN UNCONDITIONAL ACTIVATION CANNOT FAIL TO OCCUR, so an oracle
            # that abstains under one is not waiting for a scenario -- it is
            # broken, and no amount of staging can reach a condition that is
            # already true. Sending it to the stimulus loop spends the budget
            # asking for something that is not missing, and then abandons the
            # requirement for the stimulus author's supposed failure.
            #
            # a2-i2c's REQ-0003 is the case: activation "always", both its
            # observable ports moving on all three attempts, and the check
            # abstaining every time. It was recorded "never reached".
            #
            # It writes straight into this round's `rejected`/`quotable`, which
            # the gate phase below then adds to -- and `repairs` is appended
            # once, there, so the author is not told the same thing twice.
            for uid in sorted(unexer):
                shape = (normalized or {}).get(uid) or {}
                if not Activation(**(shape.get("activation") or {})).unconditional:
                    continue
                why = ("malformed: the activation holds at all times, so this "
                       "check cannot be waiting for a scenario -- it decided "
                       "nothing on every testpoint it names, which makes it a "
                       "defect in the check rather than in the stimulus")
                rejected[uid] = quotable[uid] = why
                unexer.pop(uid)
                logger.info("oracles: %s abstains under an unconditional "
                            "activation -- re-asking the author, not the "
                            "stimulus", uid)

            # THE SECOND PREDICATE, into the same sink. This block already
            # sends one class of abstainer to the check author rather than to
            # the stimulus -- "re-asking the author, not the stimulus" -- and
            # this is that pattern with a second, measured reason: the state
            # the check waits for was reached ON ITS OWN TESTPOINTS and it
            # stayed silent. On k1 that is 11 of the 15 state-naming
            # abstainers, and it is the largest single class.
            #
            # The message is a reproducible defect -- your check does not fire
            # when its own state is present, here is where it was present --
            # which is a different message from "already sound, fix it anyway",
            # the one measured to break 2 of 4 working checks.
            #
            # No staging attempt is spent: the stimulus already did its job.
            for uid, why in sorted(
                    _probe_triage(unexer, held, normalized or {}, contract,
                                  witness, stimulus_by_tp, base).author.items()):
                rejected[uid] = quotable[uid] = why
                unexer.pop(uid, None)
                logger.info("oracles: %s waits on a state its own stimulus "
                            "reached -- routing to the check author, no "
                            "staging attempt spent", uid)
            # ONE BUDGET FOR THE WHOLE STAGE, not one per round. Sizing it
            # inside the block was correct while the block ran once; running it
            # every round would re-size it every round and spend three times
            # over. What each round gets is what the previous rounds left.
            if staging_left is None:
                staging_left = (
                    staging_budget if staging_budget is not None
                    else _size_budget(unexer, normalized or {}, contract,
                                      witness, stimulus_by_tp, base))
                logger.info("oracles: staging budget %d testpoint(s) for the "
                            "whole stage", staging_left)
            before = len(stimulus_by_tp)
            gone, staging = stage_unexercised(
                held={u: o for u, o in held.items() if u not in rejected},
                unexercised=unexer,
                requirements=requirements, normalized=normalized or {},
                contract=contract, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, witness=witness, port=port,
                base=base, attempts=staging_attempts, budget=staging_left,
                prior=staging, final=(rounds == verifications))
            staging_left = max(0, staging_left - (len(stimulus_by_tp) - before))
            # MERGED, NOT REBOUND. `stage_unexercised` returns a fresh dict, and
            # assigning it discarded every "no observation route found" recorded
            # alongside it -- so a requirement the resolution pass could not
            # route stayed in `trusted` and was frozen, the exact opposite of
            # what abandoning it means.
            abandoned.update(gone)

        # THE CORRESPONDENCE GATE IS QUOTED AS A ONE-DRAW RATE AND APPLIED AS
        # UP TO THREE, and the two numbers are not the same number.
        #
        # `correspondence`'s yield paragraph reads "over 70 frozen oracles it
        # rejects 3" (4.3%) and "live on a second run, 2 of the first 40" (5%).
        # Both are ONE review per oracle. This line is inside the round loop,
        # `rejected` is cleared at the top of every round, and the argument is
        # `held.values()` -- the WHOLE surviving set, not the repaired subset.
        # `round_` reaches `port.complete` as part of the resumption key, so
        # `correspond_REQ-0007_r0` and `_r1` are different stages and neither is
        # a cache hit on the other. With `repair_attempts = 2`, `verifications`
        # is 3, so an unchanged oracle that passed in round 1 is re-asked from
        # scratch in rounds 2 and 3.
        #
        # At the calibrated one-draw rate, applied the way this loop applies it:
        #   1 - (1 - 0.043)^3 = 12.3%      1 - (1 - 0.050)^3 = 14.3%
        # roughly three times the quoted yield, with the gate behaving exactly
        # as calibrated. The compounding is arithmetic on this loop, not a claim
        # that the reviewer is wrong.
        #
        # AND THE DRAW COUNT IS NOT A PROPERTY OF THE ORACLE. The loop advances
        # only while `ask` is non-empty, so how many times THIS check is judged
        # depends on whether OTHER requirements had something repairable. One
        # repairable neighbour re-draws the gate over every survivor.
        #
        # WHAT THIS IS NOT: it is not a span loss, and calling it one would be
        # the error this file keeps paying for. A rejection costs span only if
        # the rejected check would have DECIDED and decided well, and this tree
        # has measured the opposite relationship twice -- correspondence passed
        # 21 of the 23 checks `liveness` shows cannot be moved by any legal
        # value, and checks from gate-REJECTED normalized forms were refuted by
        # the control at the same 39% as checks from clean ones. Faithfulness
        # and check success are near-orthogonal on every axis anyone has
        # measured here, so the success rate of what this gate removes is
        # UNKNOWN and may not be imputed from the run's baseline in either
        # direction. What is established is only that the gate's published rate
        # and its applied rate differ by about 3x, and that no artifact
        # currently reports the applied one.
        #
        # PRE-REGISTERED, unrun: record reviews and rejections PER ROUND, then
        # read the triple over the requirements rejected on a round > 1 only.
        # If those checks are no worse on audit and blindness than the run's
        # survivors, the extra draws are removing checks at random and the
        # compounding is a defect; if they are worse, the repetition is finding
        # something a single draw missed and the calibration is the stale
        # number. Both outcomes are publishable and neither is assumed.
        # **ONLY THE ORACLES THAT CHANGED.** `build_prompt` takes no `round_`,
        # so re-reviewing an unchanged oracle sends a BYTE-IDENTICAL prompt and
        # samples the reviewer again. The only thing a second draw on identical
        # input can add is variance, and it compounds: the gate is published at
        # "over 70 frozen oracles it rejects 3" (4.3%) and "2 of the first 40"
        # (5%), both ONE draw per oracle, while this loop spent up to
        # `repair_attempts + 1` of them over the whole surviving set --
        # 1-(1-0.043)^3 = 12.3%, roughly three times the quoted yield, with the
        # reviewer behaving exactly as calibrated.
        #
        # Worse, the draw count was not a property of the oracle: the loop
        # advances only while `ask` is non-empty, so how many times a check was
        # judged depended on whether OTHER requirements had something
        # repairable.
        #
        # Carrying the prior verdict forward makes the gate what its calibration
        # describes -- one draw per DISTINCT check -- and a repaired oracle is a
        # different check, so it is reviewed again. This removes no information
        # and roughly two thirds of the correspondence calls.
        fresh = [o for o in held.values()
                 if _reviewed.get(o.req_uid) != (o.hash or o.source)]
        reviews = dict(_carried)
        if want_correspondence and fresh:
            reviews.update(correspondence.review(
                fresh, by_uid, port=port, normalized=normalized,
                spec=spec, contract=contract, round_=rounds - 1, fanout=fanout))
            for o in fresh:
                _reviewed[o.req_uid] = o.hash or o.source
            _carried = dict(reviews)
        elif not want_correspondence:
            reviews = {}
        # Recorded from the REVIEWS, not from `rejected`, and the difference is
        # the point. `verify_one` reports one reason per oracle and
        # correspondence is checked before the variants leg, so a check that is
        # both off-target and vacuous appears in `rejected` as off-target while
        # one that failed the witness first never reaches the reviewer's verdict
        # at all. Reading the gate's own answer keeps this a record of what THIS
        # instrument said, which is the only thing its published rate can be
        # compared against.
        if want_correspondence:
            # FROM THE FRESH DRAWS ONLY. `reviewed` means "put to the gate this
            # round", and a carried-forward verdict was not put to anything --
            # counting it would report a draw that did not happen and re-create
            # on paper the compounding the carry-forward removes.
            correspondence_rounds.append(_correspondence_round(
                rounds, {o.req_uid: reviews[o.req_uid]
                         for o in fresh if o.req_uid in reviews}))
        for uid, oracle in held.items():
            why, may_quote, notes = verify_one(
                oracle, contract=contract, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, witness=witness,
                control=control, variants=variants, base=base,
                transactional=transactional, review=reviews.get(uid),
                demote_faithfulness=demote_faithfulness)
            if not why:
                # THE STAGING ROUTE HAS BEEN TRIED AND FAILED, so an abstention
                # is no longer ambiguous between a bad check and an unstaged
                # scenario. `verify_one` cannot ask this -- it has no staging
                # record -- and it is deliberately last, so a check with a real
                # mechanical defect is reported as that rather than as silence.
                why = _unreached(oracle, staging.get(uid), witness, contract,
                                 stimulus_by_tp, base=base,
                                 transactional=transactional,
                                 silenced=unreached_silenced)
                may_quote = bool(why)
            if notes:
                disagreements[uid] = notes
                # The demoted faithfulness verdict travels in `notes` from
                # `verify_one`; lift it out so the SET carries it as a label
                # rather than leaving it buried among instrument observations.
                if notes.get("faithfulness"):
                    labels[uid] = notes["faithfulness"]
            if why:
                rejected[uid] = why
                if may_quote:
                    quotable[uid] = why
        for uid, why in quotable.items():
            repairs.setdefault(uid, []).append(why)
        # Who the control ALREADY could not satisfy, before this round rewrote
        # anything. Without the before-picture a repair inherits the blame for
        # over-strictness it did not create.
        was_over_strict = {uid for uid, n in disagreements.items()
                           if "control" in n}
        # Can each surviving check fail at all? Recomputed per round because a
        # repaired oracle is a different check, and kept for the artifact so the
        # stage reports what it last saw rather than a stale first look.
        alive = _liveness(held, witness, contract, stimulus_by_tp, base=base)
        dead_now = {
            uid: record.get("detail", "")
            for uid, record in alive.items()
            if record.get("verdict") == _L.DEAD_ORACLE
        }
        # A CHECK THAT CANNOT FAIL IS REJECTED, like every other defect this
        # stage can establish mechanically.
        #
        # It used to be advisory: re-asked once, and a replacement that was
        # still inert was silently dropped. That is the one gate whose finding
        # did not route anywhere, so an unfalsifiable check could be frozen
        # TRUSTED -- and it made the loop non-monotone, because dropping the
        # replacement wholesale threw away corrections it had made on axes
        # liveness cannot see. REQ-0055 lost a widened trigger that way and was
        # rejected two rounds later for the narrow one.
        #
        # `vacuous:` is the existing prefix for "this check passes everything",
        # and `verdict.ROUTE` already sends it to "regenerate the oracle". So a
        # dead check now buys a repair round on the same terms as `malformed:`
        # or `off-target:`, and ends VACUOUS rather than TRUSTED if it stays
        # dead. That also gives the vacuity finding an owner that does not need
        # the variants leg: `_liveness` runs on every round regardless, whereas
        # `vacuity_checked` is False whenever `want_variants` is off -- which is
        # the default, and which is how "the check can never return False for
        # any design" reached a correspondence reviewer instead of a gate.
        #
        # THE CAUTION THIS OVERRIDES, kept because it was measured and is not
        # answered. `_dead_advisory` argued for staying advisory on RATE, not on
        # reasoning: its false-positive rate is known on exactly one design, and
        # this stage has twice turned a number into a refusal before knowing
        # what that refusal cost -- gate 1's blanket "met" discarded 30
        # requirements, and the correspondence gate rejected 56 of 70 on a
        # miscalibration. Both times the damage was invisible until a later gate
        # could not see past it.
        #
        # What is different here: the finding is mechanical rather than one
        # reader's opinion. Every declared output the check names was driven to
        # every other legal value, near and far, at points and throughout, and
        # the verdict never moved -- so there is no design this check tells
        # apart from any other. A false positive would mean the perturbation
        # missed a value the check does distinguish, which is a bug in
        # `liveness`, not a judgement call. The rate still wants measuring on a
        # second design before this is load-bearing.
        for uid, detail in dead_now.items():
            if uid in rejected:
                continue
            why = _cannot_fail(detail)
            rejected[uid] = quotable[uid] = why
            repairs.setdefault(uid, []).append(why)
        # AND THE OTHER SIGN OF THE SAME DEFECT. `dead_now` rejects a check
        # nothing can move; this rejects one that convicts every spec-derived
        # design there is. The stage has always blocked the first and never the
        # second, while its own note calls them "over-strictness and vacuity as
        # one defect with two signs".
        #
        # Free rather than a trade, and structurally: a check convicting both
        # sides of a pair SEPARATES neither, so removing it cannot open a cell
        # that was closed. Measured on the unbiased run's frozen sets -- audit
        # 25% -> 0% gated and 50% -> 22% demoted, blindness unmoved on both,
        # and the accepted set going from 0 designs of 9 to 5.
        #
        # OFF UNLESS A POPULATION WAS PASSED IN, because this stage runs before
        # any design of this run exists and must not acquire one of its own.
        if len(population) >= 2:
            pop_verdicts, _pop_tp, pop_where = _population_tables(
                held, population, contract, stimulus_by_tp,
                base=base, transactional=transactional)
            for uid in variety.refuted_by_the_population(pop_verdicts):
                if uid in rejected:
                    continue
                why = _refuted_everywhere(
                    len(population),
                    _where_it_fired(pop_where.get(uid) or {}, testplan))
                rejected[uid] = quotable[uid] = why
                repairs.setdefault(uid, []).append(why)
        # Gate 1 earns an attempt -- "try to make it pass" -- but only one, and
        # only where nothing else is already re-asking. It stays advisory: it is
        # a disagreement between two same-author readings, so declining it is a
        # real answer. See `_advisory`.
        advisory_only = {
            uid for uid, note in disagreements.items()
            if "witness" in note and uid not in quotable and uid not in advised
        }
        ask = set(quotable) | advisory_only

        if rounds == verifications:
            break
        if not ask:
            # Nothing left that an author could be told about. A control-only
            # rejection is terminal by design, so re-asking would spend a call
            # on a prompt carrying no information.
            #
            # This used to need an exception -- "staging just changed the
            # evidence, so take another round to re-verify against it". Staging
            # now runs BEFORE the gate in the same round, so the gate has
            # already decided against the enlarged stimulus and there is nothing
            # left to come back for.
            break
        logger.info("oracles: round %d re-asking %d rejected oracle(s)",
                    rounds, len(quotable))
        again, _ = run_oracle_gen(
            requirements=requirements, contract_json=contract_json,
            contract=contract, testplan=testplan, port=port,
            normalized=normalized, conforming_source=witness,
            stimulus_by_tp=stimulus_by_tp, base=base,
            max_repairs=max_repairs, fanout=fanout,
            only=ask,
            # Gate 1 first, as advice, then the reason this oracle is actually
            # being re-asked. An oracle with only a witness disagreement is NOT
            # in `quotable` and so is never re-asked at all -- the note costs no
            # call and applies no pressure on its own.
            feedback={
                uid: _witness_note(uid, disagreements.get(uid, {}))
                     + ([_repair_issue(
                            uid, quotable[uid],
                            disagreements.get(uid, {}).get("vacuity", ""))]
                        if uid in quotable else [])
                for uid in ask
            },
            label=f"_fix{rounds}",
            standing=_standing(held, ask),
        )
        advised |= advisory_only
        # Only a replacement that actually arrived replaces anything. A round
        # that produced nothing leaves the previous oracle standing to be
        # rejected again, which is the honest outcome rather than a hole.
        #
        # EVERY DISCARD IS RECORDED IN `repairs`, and the third path below used
        # to log and say nothing. That cost real forensics: on the affected23
        # run REQ-0055's round-1 replacement widened a trigger from cmd==1 to
        # all four commands, was discarded, and NEITHER the round-2 author nor
        # any reviewer ever saw it -- so round 2 restarted from the round-0
        # check, fixed a different defect, and the final check was rejected for
        # the narrow trigger round 1 had already corrected. Reconstructing that
        # took reading the rendezvous prompts, because the artifact recorded
        # only two objections and no discard at all. A path that drops an
        # author's work must say so where the artifact can be read.
        for o in again:
            # AN UNCHANGED REPLY IS NOT AN ATTEMPT.
            #
            # The author is sent the gate's objection and sometimes returns the
            # previous function verbatim. Measured on h2-i2c: 14 of 89 repair
            # rounds (16%) came back byte-identical to the oracle they were
            # asked to fix, every one of them the FIRST repair round, and three
            # of the run's five false convictions of golden are among them --
            # REQ-0050 was handed a specific, actionable defect report ("your
            # check judged at edge 62, before any of busy had moved off its
            # reset value") and returned the same source unchanged.
            #
            # These are not cache hits: `resumable` keys on the stage name and
            # `oracle_X_r0` and `oracle_X_fix1_r0` are different stages.
            #
            # Letting it through spends a repair attempt and buys nothing, and
            # because attempts are finite the requirement can exhaust its budget
            # on replies that never changed a character. Recording it and
            # leaving the previous oracle standing costs nothing, keeps the
            # objection live for the next round, and puts the fact in `repairs`
            # where the artifact can be read -- the same reason every other
            # discard on this path is recorded rather than logged.
            standing = held.get(o.req_uid)
            if standing is not None and o.source.strip() == standing.source.strip():
                logger.info("oracles: %s: the reply is byte-identical to the "
                            "oracle it was asked to repair; not an attempt",
                            o.req_uid)
                repairs.setdefault(o.req_uid, []).append(
                    "repair rejected -- the reply was byte-identical to the "
                    "oracle it was asked to fix, so nothing was attempted and "
                    "the objection stands")
                continue
            # RE-VERIFY EVERY REPLACEMENT, not only the advisory ones.
            #
            # This branch used to run for `advisory_only` alone, so a reply to
            # an actual REJECTION went straight into `held` unchecked and was
            # only re-examined at the top of the next round. `_strengthen` has
            # never worked that way -- "a replacement is kept only if it
            # VERIFIES" -- and the asymmetry mattered because both paths push
            # the SAME direction: vacuity says the check passes something wrong,
            # so make it stricter.
            #
            # Measured on s-i2c, the only run whose `_fix` rounds ran, against
            # the known-good control:
            #
            #     repaired and kept (28)   13 failed by the control   46%
            #     never repaired    (30)    2 failed by the control    6%
            #
            # Nearly eight times the rate, and 13 of the run's 15 over-strict
            # oracles came out of the tightening loop.
            #
            # WHAT THIS DOES NOT FIX, stated plainly: `verify_one` cannot reject
            # for strictness -- nothing in this package ever produces an
            # "over-strict:" reason, and the control is barred from gating
            # because it is a proxy for the held-out grade. So this catches a
            # replacement that went VACUOUS or MALFORMED under a tightening
            # instruction; it does not catch one that went too strict. That is
            # what `newly_over_strict` below reports rather than blocks.
            # This oracle was not rejected -- it was asked to TRY. A reply
            # that comes back worse must not be promoted over the one that
            # was already fine, or advice becomes a way to lose a good
            # check. Same rule `_strengthen` applies for the same reason.
            worse, _q, fresh = verify_one(
                o, contract=contract, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, witness=witness,
                control=control, variants=variants, base=base,
                transactional=transactional)
            if worse:
                logger.info("oracles: %s: the replacement is worse (%s); "
                            "the previous check stands",
                            o.req_uid, worse.split(":")[0])
                repairs.setdefault(o.req_uid, []).append(
                    f"repair rejected -- {worse}; the previous oracle stands")
                continue
            # A NEW disagreement with the control is REPORTED, never acted
            # on. It is the over-strictness this loop demonstrably creates,
            # and the control may not gate: kept-or-rejected is the one bit
            # that leaks, and letting it select oracles tunes the model
            # toward the grade transitively.
            if "control" in fresh and o.req_uid not in was_over_strict:
                newly_over_strict.add(o.req_uid)
            # A REPLACEMENT THAT STOPPED DECIDING IS NOT A REPAIR.
            #
            # The correspondence gate rejects on the TRIGGER far more than on
            # anything else, and the only move an author has against "your
            # activation is too broad" is to narrow it. Narrow it enough and the
            # check never fires -- it stops convicting, which reads like
            # compliance, and stops deciding, which is the whole of its value.
            #
            # Nothing above catches that. `verify_one` rejects for `malformed`
            # and `vacuous`; its one non-mechanical leg is the correspondence
            # `review`, and THE CALL ABOVE PASSES NONE, because the review in
            # hand is of the oracle being replaced, not of the replacement. So
            # a replacement is judged by correspondence only at the top of the
            # next round -- and on the last round there is no next round.
            #
            # Measured on d1-i2c: across the rejected set, six checks went from
            # convicting to abstaining under repair and three from passing to
            # abstaining. This is the leg that would have held them.
            #
            # Only a STRICT loss blocks. A replacement that decides as much as
            # its predecessor is kept even if it decides differently -- deciding
            # differently is what a repair is for. And a predecessor that
            # already decided nothing sets a floor of zero, so this can never
            # block the first check that starts working.
            before = held.get(o.req_uid)
            if before is not None:
                was = _decides(before, witness, contract, stimulus_by_tp,
                               base=base, transactional=transactional)
                now = _decides(o, witness, contract, stimulus_by_tp,
                               base=base, transactional=transactional)
                # **THE SLOPE, RECORDED BECAUSE THE GUARD BELOW ONLY SEES THE
                # CLIFF.** `if was and not now` blocks a TOTAL loss of
                # deciding. A replacement that goes from ten testpoints to one
                # passes silently, and that is the gradual road into the
                # sound-and-blind population: measured on k1, among 68 SOUND
                # checks the chance of discriminating is 26% against a 75% base
                # rate, and 52 of the 68 convict nothing at all.
                #
                # REPORTED, NOT GATED. The cliff is measured at nine checks on
                # d1-i2c; the slope is unmeasured, and a threshold picked before
                # its distribution is seen is the error this branch keeps
                # paying for. This is what makes the distribution visible.
                if was != now:
                    narrowing.setdefault(o.req_uid, []).append(
                        {"round": rounds, "was": was, "now": now})
                if was and not now:
                    logger.info("oracles: %s: the replacement decides nothing on "
                                "any of its %d testpoint(s) where the previous "
                                "check decided %d; the previous check stands",
                                o.req_uid, len(o.tp_uids), was)
                    repairs.setdefault(o.req_uid, []).append(
                        f"repair rejected -- the replacement decided nothing on "
                        f"any of its {len(o.tp_uids)} testpoint(s), where the "
                        f"previous check decided {was}; the previous stands")
                    continue
            # THERE IS NO THIRD GUARD, and the one that used to be here was
            # dropped rather than narrowed.
            #
            # It discarded a replacement when the check had been re-asked for
            # being unable to fail and the replacement still could not fail --
            # on the reasoning that swapping one inert check for another loses
            # the reasoning already recorded against the uid. It did exactly
            # that, and the cost is measured. REQ-0055 on the affected23 run:
            #
            #   round 0   trigger cmd==1, `al` folded into `until`   _is_live False
            #   round 1   trigger WIDENED to all four commands       _is_live False  -> DISCARDED
            #   round 2   restarted from ROUND 0, fixed the abort    _is_live True   -> kept
            #
            # and correspondence then rejected the frozen check for narrowing
            # "each command sequence" to cmd==1 -- the defect round 1 had
            # already corrected. Two repair rounds spent, one correction thrown
            # away, and the requirement lost.
            #
            # The guard treated liveness as the only axis of improvement.
            # Round 1's replacement was better on a different one -- trigger
            # coverage -- which neither `_is_live` nor `_decides` can see, so
            # the guard could not distinguish an improved-but-still-dead
            # replacement from an unimproved one. A predicate that cannot see
            # the dimension a repair moved must not be the thing that decides
            # whether the repair survives.
            #
            # The churn it prevented is cheaper than the work it destroyed. The
            # two guards above stay: they reject a replacement that VERIFIES
            # worse, or that stopped deciding -- both measurable losses, both
            # recorded.
            # **A2: REPAIR ADDS, IT DOES NOT REPLACE.** The predecessor is
            # already a corpus member -- retained at generation on round 0, or
            # by this same line on the round that accepted it -- so retaining
            # it again here is a no-op the content de-duplication swallows. A
            # branch doing exactly that was written, and removing it left every
            # test green; the honest form is to retain the REPLACEMENT and let
            # the predecessor stand where it was already recorded.
            #
            # `trusted` keeps its meaning: one survivor per uid. What changes
            # is that the superseded body stops being unrecoverable, which is
            # what made the narrowing round's "12 of 47 became vacuous" a loss
            # rather than a corpus.
            _retain(corpus, o, arm="repair", round_=rounds,
                    answered="; ".join(repairs.get(o.req_uid, ())[-1:]))
            held[o.req_uid] = o

    # EVERY UNEXERCISED ORACLE GETS STAGING ATTEMPTS, before anything is frozen
    # and before the reference model exists. `never_decides` is exactly the set:
    # checks that returned no decision on any testpoint they name. z-i2c ended
    # with 33 of these and `stimulus_added: 0`, because the only route to stage
    # one was a debug-turn tool that was never called.
    #
    # What survives unstaged is ABANDONED rather than NOT_EXERCISED -- attempted
    # and exhausted, with the record to prove it. What was never attempted stays
    # NOT_EXERCISED and blocks, which is what stops the softening being free.
    # A REQUIREMENT THE RESOLUTION PASS COULD NOT ROUTE HAS BEEN ASKED, so it is
    # abandoned rather than left as a claim that no port shows it. Detected here
    # because this is where the normalized form and the dispositions meet; the
    # asking happened at normalisation, which is why this is not "nobody tried".
    #
    # Only when the pass actually ran: a normalized form predating it has no
    # `observed_via` key at all, and treating its absence as a failed attempt
    # would abandon requirements nothing ever asked about.
    for uid, shape in (normalized or {}).items():
        # **ONLY REQUIREMENTS THIS STAGE WAS ASKED ABOUT.** `normalized` can
        # hold more than `requirements` -- an `only`-scoped round, or a caller
        # passing a normalized map built over a larger set -- and without this
        # the loop abandons uids that are not in `by_uid` at all. They then have
        # NO disposition, while `considered()` still subtracts them from the
        # denominator, so every rate computed against it is inflated.
        #
        # Measured when it fired: 20 requirements with 41 normalized forms gave
        # `abandoned` 17 entries of which **10 had no disposition**, and
        # `considered()` read 3 where it should read 13 -- a denominator more
        # than four times too small. A full run has `normalized == requirements`
        # and never sees it, which is why it survived.
        if uid not in by_uid:
            continue
        if "observed_via" not in shape:
            continue
        if not (shape.get("observable") or []) and not shape.get("observed_via"):
            # AND A CONCEDED ROUTE HAS ALREADY BEEN CHASED BY THE TIME IT GETS
            # HERE, which is worth stating because this line looks like the
            # place to chase it and is not.
            #
            # The tempting reading: normalisation records that 44% of
            # unobservable requirements CONCEDE a route in their own
            # `unobservable_reason` -- naming the port and the mechanism while
            # claiming nothing shows it -- so this site should refuse the
            # concession and send the requirement back for a route. Every step
            # of that is wrong, and each one is already measured:
            #
            #   - THE DETECTOR IS GONE ON PURPOSE. `concedes_a_route` was
            #     removed after two false negatives in one session: a negation
            #     window any nearby "not" disarmed -- structurally wrong in a
            #     pass that teaches that an ABSENCE is an observation, so
            #     correct reasons increasingly contain "not" -- and reading a
            #     field the prompt tells the model to leave alone. See
            #     `route_shows_issue`; what survives at `normalize.py:1303` is
            #     the epitaph, not the function.
            #   - THE CONCESSION IS A DEFERRAL, NOT A DODGE. `unobservable` is
            #     literally the ticket into `blind`, which is the indirect
            #     pass's input. Refusing it here forces a worse route out of a
            #     pass with less information AND drops the requirement from
            #     `blind`, so it never gets the better-informed look at all.
            #   - THE MECHANISM ALREADY FIRES. Of 18 conceding direct-pass
            #     answers on h2-i2c the indirect pass returned 15 (83%) with a
            #     real port AND route, and `resolve_indirect` writes those
            #     ports into `observable` and clears the reason -- so a routed
            #     requirement is no longer blind here or in `_dispositions`.
            #     FIRES, NOT WORKS: 83% is a ROUTE-recovery rate, and whether
            #     those routes become checks that decide is not measured
            #     anywhere. Reading it as 83% recovered span would be assuming
            #     the thing this tree twice measured to be false -- that a
            #     faithful artefact is a successful one. It is the plan's own
            #     caveat, and it binds here too: span on paper is not span.
            #
            # What reaches this line is therefore the residue: asked twice and
            # routed by neither. ABANDONED is the honest verdict for it.
            abandoned.setdefault(uid, "no observation route found")
            continue
        # A REQUIREMENT NOTHING COULD CONTRADICT, caught where it is cheapest.
        #
        # Normalisation is asked, per route, what the port does when the
        # requirement holds AND when it does not. A tautology has no second case
        # -- REQ-0005 is "releasing scl_oen high causes the module to release
        # the line", whose port is its own antecedent -- and the gate lets it
        # say so rather than forcing an invention, because a model asked for
        # something impossible complies instead of refusing, and a fabricated
        # discrimination is worse than an absent one: it launders a check that
        # cannot fail into one that looks checkable.
        #
        # Every route declining is the finding. ONE route discriminating is
        # enough, because routes are alternatives and a single sufficient one
        # makes the requirement checkable.
        routes = shape.get("observed_via") or []
        if routes and all(_route_declines(r) for r in routes):
            # A LEXICAL MATCH ON PROSE, and under `demote_faithfulness` it stops
            # deciding. `normalize` keeps this screen only because "that is
            # reporting, which is the right use of a lexical screen" -- while
            # ABANDONED outranks every other disposition and leaves the
            # requirement out of the numerator AND the denominator.
            if demote_faithfulness:
                labels[uid] = "no discrimination stated"
            else:
                abandoned.setdefault(uid, "no discrimination stated")

    # ABANDONED REQUIREMENTS LEAVE THE SYSTEM HERE, and this is the only place
    # that can be true. Excluding them from `trusted` is what stops the debug
    # loop deciding them, `run_all` counting them and the board showing them --
    # the difference between a discard and a verdict that no longer blocks but
    # is still in the way. Nothing downstream has to know about them, because
    # nothing downstream is given them.
    #
    # `abandoned` is populated by the stages that ran the attempt (the stimulus
    # loop, the resolution pass, the repair loop) and is empty otherwise, so the
    # exclusion cannot fire on a requirement nobody tried.
    # THE REPRIEVE. A discard whose stated ground is a reachability claim is
    # overturned by a `live` verdict, because that verdict IS the counter-
    # example. `off-target` is untouched -- see `_reprieved`.
    _verdict = {u: (r or {}).get("verdict") for u, r in (alive or {}).items()}
    reprieved = {
        uid: why
        for uid, why in list(rejected.items()) + list(abandoned.items())
        if uid in held and _reprieved(why, _verdict.get(uid))
    }
    if reprieved:
        rejected = {u: w for u, w in rejected.items() if u not in reprieved}
        abandoned = {u: w for u, w in abandoned.items() if u not in reprieved}
        logger.info(
            "oracles: %d discard(s) overturned -- liveness decided and moved "
            "them, which refutes the reachability ground they were held on: %s",
            len(reprieved), ", ".join(sorted(reprieved)[:8]))
    # THE CORPUS IS WHY THE CORPUS EXISTS. A requirement was discarded whenever
    # its LAST body failed, even when an earlier one passes every blocking rule
    # -- so the stage threw away span it had already paid for. `_retain` has
    # kept every superseded body since it landed, expressly so "selection has
    # something to choose from", and nothing until now chose.
    #
    # Measured on the probe run, offline, against its own witness and its own
    # three designs: of 39 requirements lost while carrying an observable
    # obligation, **11 have a body in their own corpus that decides and is not
    # refuted** -- 6 first drafts and 5 repairs. Span 71.1% -> 79.3% for zero
    # model calls.
    #
    # THE ADMISSION TESTS ARE THE STAGE'S OWN BLOCKING RULES AND NOTHING MORE:
    # it decides something on the witness (not vacuous), and the whole
    # spec-derived population does not refute it (not over-strict). The witness
    # CONVICTING it is not a test here -- that gate is advisory by decision,
    # "it has no authority to say the oracle is wrong... it makes the check
    # agree with the witness", measured on h-i2c at over-strictness 27 -> 15
    # and convictions 2 -> 16.
    rescued = _rescue_from_corpus(
        corpus=corpus, held=held, blocked=set(rejected) | set(abandoned),
        reasons_for={**abandoned, **rejected},
        witness=witness, population=population, contract=contract,
        stimulus_by_tp=stimulus_by_tp, base=base, transactional=transactional)
    for uid, body in rescued.items():
        held[uid] = body
        rejected.pop(uid, None)
        abandoned.pop(uid, None)
    if rescued:
        logger.info(
            "oracles: %d requirement(s) rescued from their own corpus -- a "
            "body that decides and that the population does not refute: %s",
            len(rescued), ", ".join(sorted(rescued)[:8]))

    trusted = [o for uid, o in held.items()
               if uid not in rejected and uid not in abandoned]
    dispositions, reasons = _dispositions(
        requirements=requirements, trusted=trusted, rejected=rejected,
        had_source=set(held), normalized=normalized,
        abandoned=abandoned,
        never_decides=_L.never_decides(alive))
    for uid, why in reprieved.items():
        reasons[uid] = (f"discard overturned -- liveness decided this check and "
                        f"a perturbation moved its verdict, which refutes "
                        f"{why!r}")

    if only and previous is not None:
        # A SCOPED ROUND DECIDES ONLY WHAT IT WAS ASKED ABOUT. Everything else
        # keeps the disposition the previous round gave it -- re-deriving one
        # here would report a verdict for a requirement this round never looked
        # at, from an `only`-scoped `held` that does not contain its oracle.
        #
        # A replacement that failed verification is not promoted and not
        # demoted: the previous check stands, which is what `rejected` means on
        # this path, so its uid keeps the old disposition too.
        kept = {o.req_uid: o for o in previous.trusted}
        kept.update({o.req_uid: o for o in trusted})
        for uid in rejected:
            if uid in kept and uid not in {o.req_uid for o in trusted}:
                reasons[uid] = (f"regeneration rejected -- {rejected[uid]}; "
                                f"the previous oracle stands")
        merged_d = dict(previous.dispositions)
        merged_d.update({u: v for u, v in dispositions.items() if u in scoped})
        merged_r = dict(previous.reasons)
        merged_r.update({u: v for u, v in reasons.items() if u in scoped})
        replaced = {o.req_uid for o in trusted}
        for uid in scoped:
            if uid in kept and uid not in rejected and uid not in abandoned:
                merged_d[uid] = TRUSTED
            if uid in replaced:
                merged_r[uid] = (
                    "reconsidered after a debug loop and a second "
                    "implementation both failed to satisfy it"
                    if uid in (reconsider or {})
                    else "regenerated")
        trusted = list(kept.values())
        dispositions, reasons = merged_d, merged_r
        abandoned = {**previous.abandoned, **abandoned}
    # How much the stimulus gives ANY oracle to work with. Measured on the
    # witness -- a design, but this is not a judgement about correctness, it is
    # the question "does this stimulus make a design do anything".
    #
    # Unmeasured until now: `stimulus_liveness` existed and nothing called it,
    # because its one caller went with the judge. What it says about n-i2c's
    # stimulus, replayed on the KNOWN-GOOD control: 11% of testpoints show ONE
    # output state across ~256 edges, the median testpoint shows five, and two
    # of the eight declared outputs never move anywhere. Five distinct states is
    # the ceiling on what any oracle naming that testpoint can discriminate,
    # however well it is written -- so a thin stimulus caps oracle quality
    # before oracle quality is even in question.
    live = None
    if witness:
        try:
            from .refmodel.oracles import stimulus_liveness

            report = stimulus_liveness(witness, contract, stimulus_by_tp,
                                       base=base)
            live = {"testpoints": len(stimulus_by_tp),
                    "inert": sorted(report.inert),
                    "inert_count": len(report.inert)}
            if report.inert:
                logger.warning(
                    "%d of %d testpoint(s) move nothing at all on an "
                    "implementation of these requirements: every oracle naming "
                    "one is unjudgeable however well written",
                    len(report.inert), len(stimulus_by_tp))
        except Exception as exc:  # noqa: BLE001
            logger.info("stimulus liveness not measured (%r)", exc)

    # CAN EACH TRUSTED ORACLE FAIL AT ALL? Asked here, against the witness,
    # because the answer does not depend on which design it is asked about.
    # Measured: the same 70 frozen oracles gave identical verdicts against a
    # model scoring 30/168 against golden RTL and against the known-good
    # control at 168/168 -- live 44, dead-oracle 20, dead-stimulus 3, unknown 3,
    # on all 70 -- while five of them reach different base verdicts on those two
    # designs. So the witness is not a compromise here, it is sufficient.
    #
    # REPORTED, NOT GATED. Its rate is known on exactly one design, and the
    # thing this stage has repeatedly got wrong is turning a number into a
    # refusal before knowing what it rejects: gate 1's blanket "met" discarded
    # 30 requirements before another gate could look at them, and the
    # correspondence gate rejected 56 of 70 on a miscalibration. A verdict that
    # blocks needs a measured false-positive rate first.
    #
    # The split is what makes it actionable when it does gate. DEAD_ORACLE is
    # the author's -- the ports it watches move and the verdict will not.
    # DEAD_STIMULUS is the testplan's -- the check can fail, but not near
    # anything this stimulus produces, and telling the author to strengthen a
    # sound check would be the misrouting the verdict enum exists to stop.
    keep = {o.req_uid for o in trusted}
    report = {u: r for u, r in alive.items() if u in keep}
    dead: dict = {}
    if report:
        dead = {
            "counts": _L.counts(report),
            # The per-requirement verdict, stored rather than reconstructed
            # from the lists below. Rebuilding it from `dead_oracle` +
            # `dead_stimulus` + "everything else is live" silently promotes the
            # UNKNOWNs -- the checks this could not decide about -- into the
            # count of ones that demonstrably can fail, which is the exact
            # conflation `rates()` keeps a `None` for.
            "verdicts": {u: r.get("verdict", _L.UNKNOWN)
                         for u, r in sorted(report.items())},
            "dead_oracle": sorted(_L.dead(report)),
            "dead_stimulus": sorted(
                u for u, r in report.items()
                if r.get("verdict") == _L.DEAD_STIMULUS),
            "asserts_on": {u: sorted(set(r.get("asserts_on") or ())
                                     | set(r.get("asserts_on_far") or ()))
                           for u, r in sorted(report.items())},
        }
        if dead["dead_oracle"]:
            logger.warning(
                "%d of %d trusted oracle(s) cannot be made to fail by any "
                "legal value of the ports they read, after %d repair round(s): "
                "%s", len(dead["dead_oracle"]), len(trusted), rounds,
                ", ".join(dead["dead_oracle"][:8]))
        if dead["dead_stimulus"]:
            logger.warning(
                "%d trusted oracle(s) can fail, but nothing this stimulus "
                "produces comes near what would fail them: %s",
                len(dead["dead_stimulus"]),
                ", ".join(dead["dead_stimulus"][:8]))

    idle = _decides_nothing(testplan, trusted)
    if idle:
        logger.warning(
            "%d of %d testpoint(s) are named by no oracle: they render, they "
            "start a simulator, and nothing they produce decides anything",
            len(idle), len(testplan))

    # THE SELECTED SET IS WHAT GETS FROZEN, when a ruleset is supplied.
    # Everything above decides which checks are ADMISSIBLE; this decides which
    # of them the suite keeps, and it is the last word before the artifact.
    #
    # Recorded either way: `selection_dropped` names every check the rules
    # removed and why, because a set that is 30 checks smaller with no record
    # of which 30 is not auditable.
    selection_dropped: dict[str, str] = {}
    if selection is not None and len(population) >= 2:
        #: `trusted` is a LIST of oracles here, not the `held` mapping.
        sel, _shape = _select_frozen(
            {o.req_uid: o for o in trusted}, population, contract,
            stimulus_by_tp, rules=selection, base=base,
            transactional=transactional)
        if sel is not None:
            kept = set(sel.kept)
            for v in sel.dropped:
                selection_dropped[v.key] = f"{v.reason}: {v.detail}"
            before = len(trusted)
            trusted = [o for o in trusted if o.req_uid in kept]
            logger.info("oracles: selection kept %d of %d check(s)",
                        len(trusted), before)

    if run_dir is not None:
        trusted, drift = freeze.freeze(
            trusted, Path(run_dir) / "specflow" / ARTIFACT, normalized,
            rewrite=rewrite or bool(only),
            extra={"dispositions": dispositions, "reasons": reasons,
                   "witness": witness_kind,
                   # A set 30 checks smaller with no record of WHICH 30 is not
                   # auditable. Empty when no ruleset ran, which is different
                   # from a ruleset that dropped nothing -- `selection_ran`
                   # carries that distinction, the same `VACUOUS: 0` against
                   # `VACUOUS: None` problem one level over.
                   "selection_dropped": selection_dropped,
                   "selection_ran": selection is not None,
                   # See `cell_report`: a leg that does nothing has to say
                   # which nothing it was.
                   "cell_report": cell_report,
                   "rounds": (previous.rounds + 1 if only and previous
                              else rounds),
                   "variants": len(variants),
                   # Legibility, not decoration: a reader has to be able to
                   # tell a check that found nothing from one that never ran.
                   "vacuity_checked": bool(variants),
                   "correspondence_checked": want_correspondence,
                   # Read back in `load` -- see the LOSSY-LOAD TRAP there. A
                   # field written here and not read there is absent from every
                   # `--reuse`, which for a per-round record means it would
                   # exist only on runs nobody reused.
                   "correspondence_rounds": correspondence_rounds,
                   "over_strictness_bounded_by": witness_kind,
                   "repairs": repairs,
                   # `tools` was in the set and not in the artifact, so `load`
                   # could only ever restore an empty one -- and the whole
                   # argument for carrying it is that a later round inherits
                   # the instruments instead of re-deriving them from a call
                   # site's keyword arguments.
                   "tools": {"demote_faithfulness": demote_faithfulness,
                             "correspondence": want_correspondence,
                             "variants": want_variants,
                             "staging": want_staging,
                             "max_repairs": max_repairs,
                             "repair_attempts": repair_attempts},
                   # **A1 PERSISTENCE.** The corpus travels in the artifact
                   # rather than beside it, so a `--reuse` that restores the
                   # set restores what it was selected from. `load` below
                   # reads it back; a field added here without extending
                   # `load` vanishes on every reuse, which is already true of
                   # `repairs`, `abandoned` and `tools`.
                   "corpus": {
                       uid: [
                           {"source": m.source, "arm": m.arm,
                            "round": m.round_, "answered": m.answered,
                            "frozen": m.frozen, "digest": m.digest()}
                           for m in members
                       ]
                       for uid, members in corpus.items()
                   },
                   # What the designs said without being allowed to decide.
                   "instrument_notes": disagreements,
                   "unsatisfiable_by_the_control": sorted(
                       u for u, d in disagreements.items() if "control" in d),
                   # HOW MUCH OF THAT THE TIGHTENING LOOP CREATED. Measured
                   # offline on s-i2c, the only run whose `_fix` rounds ran:
                   # 13 of 28 repaired-and-kept oracles were failed by the
                   # control (46%) against 2 of 30 never repaired (6%), and 13
                   # of the run's 15 over-strict checks came out of the loop.
                   # Reported per run now rather than reconstructed after the
                   # fact -- and reported only: the control may not select
                   # which oracles survive.
                   "over_strict_after_repair": sorted(
                       u for u in newly_over_strict if u in dispositions
                       and dispositions[u] == TRUSTED),
                   # DISCARDED, NEVER SILENT. Named with the reason we gave
                   # up, and beside the denominator they left, so a rate is
                   # never read against the wrong total.
                   "abandoned": dict(sorted(abandoned.items())),
                   # STAGED N TIMES, NEVER REACHED vs NEVER ATTEMPTED. Two
                   # different findings that were the same verdict until now.
                   "staging": staging,
                   "stimulus_added": {
                       u: [t["staged"] for t in r["attempts"] if t.get("staged")]
                       for u, r in staging.items()},
                   "abandoned_count": len(abandoned),
                   "considered": len(dispositions) - len(abandoned),
                   "testpoints_no_oracle_names": idle,
                   # Read back in `load`, like every field below it. See the
                   # LOSSY-LOAD TRAP note there.
                   "unreached_silenced": unreached_silenced,
                   "faithfulness_labels": labels,
                   "repair_narrowing": narrowing,
                   "stimulus_liveness": live,
                   "oracle_liveness": dead})
        for uid, what in sorted(drift.items()):
            logger.warning("oracle drift %s: %s", uid, what)
        if variants:
            variants_mod.save(variants,
                              Path(run_dir) / "specflow" / "variants.json")
    else:
        trusted = freeze.stamp(trusted, normalized)

    #: MARK THE SURVIVORS. Exactly one member per requirement should carry
    #: `frozen`, and a requirement whose corpus has none is one the stage
    #: authored for and then dropped -- a fact the artifact could not previously
    #: express, because the dropped bodies were gone.
    _survivors = {o.req_uid: o.source for o in trusted}
    corpus = {
        uid: [
            CorpusBody(req_uid=m.req_uid, source=m.source, arm=m.arm,
                       round_=m.round_, answered=m.answered,
                       frozen=_survivors.get(uid) == m.source)
            for m in members
        ]
        for uid, members in corpus.items()
    }
    logger.info("oracles: %s (bound: %s); corpus retained %d bodies over %d "
                "requirements", _summary(dispositions), witness_kind,
                sum(len(v) for v in corpus.values()), len(corpus))
    return OracleSet(trusted=trusted, dispositions=dispositions,
                     corpus=corpus,
                     abandoned=abandoned,
                     tools={"correspondence": want_correspondence,
                            "variants": want_variants,
                            "staging": want_staging,
                            "max_repairs": max_repairs,
                            "repair_attempts": repair_attempts},
                     reasons=reasons, repairs=repairs, variants=variants,
                     witness_kind=witness_kind,
                     rounds=(previous.rounds + 1 if only and previous
                             else rounds),
                     testpoints_no_oracle_names=idle,
                     unreached_silenced=dict(unreached_silenced),
                     selection_dropped=dict(selection_dropped),
                     selection_ran=selection is not None,
                     labels=dict(labels),
                     narrowing={u: list(v) for u, v in narrowing.items()},
                     liveness={u: r.get("verdict", _L.UNKNOWN)
                               for u, r in report.items()},
                     control_notes={u: n["control"]
                                    for u, n in disagreements.items()
                                    if "control" in n},
                     witness_notes={u: n["witness"]
                                    for u, n in disagreements.items()
                                    if "witness" in n})


@dataclass(frozen=True)
class _Triage:
    """What one replay pass over the testpoints tells us about the abstainers.

    Built once and read by three callers, because the replay is the expensive
    part and doing it per question would triple it for no new information.
    """

    #: `{probe: [Observation]}` -- every state any testpoint reached.
    pool: dict
    #: `{req_uid: the unobserved state it waits on}`. These schedule.
    blocked: dict
    #: `{req_uid: why}` for checks whose state was reached ON THEIR OWN
    #: TESTPOINTS and which stayed silent regardless. These do not schedule.
    author: dict


def _probe_triage(unexercised: dict, held: dict, normalized: dict, contract: dict,
                  witness: str, stimulus_by_tp: dict, base: str) -> _Triage:
    """Split the abstainers by what the rows say, mechanically. No model call.

    The staging loop's model of an abstention is "the stimulus never got the
    design into the state the check is waiting for", and it has one response:
    mint another testpoint. Triaging k1's 25 never-firing checks against
    recorded state says that is the wrong response most of the time -- of the 15
    whose requirement names a state, ELEVEN had the state reached on the check's
    own testpoints and stayed silent anyway.

    That is a defect in the check, and staging harder cannot fix it: the
    stimulus already did its job. The loop could not tell those apart because it
    could not see whether the state was entered; once the state is a probe it is
    in the row, and one scan answers it.
    """
    probes = reachability.probes_of(contract)
    if not probes or not witness or not stimulus_by_tp:
        return _Triage({}, {}, {})
    rows_by_tp = reachability.rows_for(witness, stimulus_by_tp, contract, base=base)
    if not rows_by_tp:
        return _Triage({}, {}, {})
    pool = reachability.observed(rows_by_tp, probes)

    blocked: dict[str, str] = {}
    author: dict[str, str] = {}
    for uid in unexercised:
        shape = normalized.get(uid) or {}
        want = reachability.waiting_on(shape, probes)
        if not want:
            continue  # LEGACY: names no state; today's path, untouched
        unobserved = sorted(p for p in want if not pool.get(p))
        if unobserved:
            blocked[uid] = unobserved[0]
            continue
        oracle = held.get(uid)
        own = set(getattr(oracle, "tp_uids", None) or [])
        for probe in want:
            hit = next((o for o in pool.get(probe) or [] if o.tp_uid in own), None)
            if hit is None:
                continue
            act = (shape.get("activation") or {}).get("text") or ""
            author[uid] = (
                f"the state this check waits for WAS REACHED on its own "
                f"stimulus and the check did not decide. {probe!r} was true on "
                f"{hit.tp_uid} from edge {hit.first_edge} for {hit.held} "
                f"edge(s), and this check returned no verdict on that "
                f"testpoint. So this is a defect in the check -- its window "
                f"does not recognise the state it names -- and not a gap in "
                f"the stimulus, which already produced the state. Its "
                f"activation reads: {act!r}. Re-read the requirement and make "
                f"the window open on {probe!r}.")
            break
    return _Triage(pool, blocked, author)


def _blocked_states(unexercised: dict, normalized: dict, contract: dict,
                    witness: str, stimulus_by_tp: dict, base: str) -> dict[str, str]:
    """`{req_uid: the unobserved state it waits on}`. See `_probe_triage`."""
    return _probe_triage(unexercised, {}, normalized, contract, witness,
                         stimulus_by_tp, base).blocked


def _size_budget(unexercised: dict, normalized: dict, contract: dict,
                 witness: str, stimulus_by_tp: dict, base: str) -> int:
    """The staging budget, sized PER STATE where the pool can say so.

    The old sizing was `len(unexercised) * PER_ORACLE` -- one allocation per
    silent check. That is the right shape only if every abstention is a separate
    stimulus problem, and the k1 triage says it is not: eight of them were
    dependents of ONE state the design compiles out, and they spent 24 attempts
    between them discovering that eight times over.

    One testpoint that reaches P serves every check waiting on P, so the
    allocation belongs to the STATE. Checks naming no probe keep their own, and
    checks whose state the pool already has do not schedule at all.

    Falls back to the old sizing whenever the pool cannot be built -- no probes
    declared, no witness, no stimulus. The per-state budget is an improvement
    where the evidence exists and must not become a way to under-fund staging
    where it does not.
    """
    probes = reachability.probes_of(contract)
    if not probes or not witness or not stimulus_by_tp:
        return min(STAGING_BUDGET_CAP,
                   max(1, len(unexercised)) * STAGING_BUDGET_PER_ORACLE)
    rows_by_tp = reachability.rows_for(witness, stimulus_by_tp, contract, base=base)
    if not rows_by_tp:
        return min(STAGING_BUDGET_CAP,
                   max(1, len(unexercised)) * STAGING_BUDGET_PER_ORACLE)
    pool = reachability.observed(rows_by_tp, probes)
    waiting = {uid: reachability.waiting_on(normalized.get(uid) or {}, probes)
               for uid in unexercised}
    sized = reachability.budget_for(
        waiting, pool, per_state=STAGING_BUDGET_PER_ORACLE, cap=STAGING_BUDGET_CAP)
    states = sorted({p for ps in waiting.values() for p in ps
                     if not pool.get(p)})
    logger.info("oracles: %d abstainer(s) wait on %d unobserved state(s) %s; "
                "budget %d instead of %d",
                len(unexercised), len(states), states, sized,
                min(STAGING_BUDGET_CAP,
                    max(1, len(unexercised)) * STAGING_BUDGET_PER_ORACLE))
    return sized


def _ports_agree(source: str, contract_json: str) -> bool:
    """Does this model's declared port lists match the contract's?

    BOTH lists, and the probe half is not a nicety. Probes are sampled into
    `row["outputs"]`, and `transactional_view` compresses on inputs and outputs
    together, so declaring a probe changes the ROW LIST every check sees --
    including checks that read no probe (measured at 1.04x more rows over 60
    testpoints). A witness reused across a contract change in its probe set
    would therefore decide against a different row list than the one its checks
    were authored against, silently. No new digest is needed for that: this
    function already owns witness/contract agreement.

    Read from the source with `ast` rather than by importing it: this runs on a
    witness that may be stale in ways beyond its port list, and executing a
    module to ask a question about its header is more than the question needs.

    Unreadable either way -> True, because refusing to reuse on a parse failure
    would silently re-pay for a witness whenever this helper cannot answer, and
    a bound that disappears for an unrelated reason is the worse error.
    """
    import ast as _ast

    try:
        contract = json.loads(contract_json)
        from .refmodel.base import probe_names
        from .refmodel.compose import output_ports
        wanted = set(output_ports(contract))
        want_probes = set(probe_names(contract))
        tree = _ast.parse(source)
    except (ValueError, SyntaxError, TypeError):
        return True
    if not wanted and not want_probes:
        return True

    # A witness written before probes existed has no PROBE_PORTS line at all, so
    # an absent list reads as empty rather than as unreadable -- which is the
    # right answer: it agrees with a contract that declares no probe, and
    # disagrees with one that does.
    declared: dict[str, set | None] = {"OUTPUT_PORTS": None, "PROBE_PORTS": set()}
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, _ast.Name)]
        for key in declared:
            if key not in names:
                continue
            try:
                declared[key] = set(_ast.literal_eval(node.value))
            except (ValueError, SyntaxError):
                return True
    if declared["OUTPUT_PORTS"] is None:
        # No OUTPUT_PORTS line to read. Unreadable either way -> True, because
        # refusing to reuse whenever this helper cannot answer would silently
        # re-pay for a witness for an unrelated reason.
        return True
    return (declared["OUTPUT_PORTS"] == wanted
            and declared["PROBE_PORTS"] == want_probes)


def _witness(
    *, requirements: list[dict], contract_json: str, port: ModelPort,
    workdir: Path, run_dir: Path | None,
) -> tuple[str, str]:
    """The design the repair loop is allowed to quote, and whether there is one.

    Generated even where a control exists, because the two do different jobs: a
    control REJECTS and a witness REPAIRS, and collapsing them would let the
    control's behaviour reach an oracle author.

    **Written once and read forever, like the oracles it bounds.** A
    strengthening round re-enters this stage, and a freshly generated witness
    would be a DIFFERENT reading of the same requirements -- so an oracle could
    be accepted this round and rejected next for no reason anyone could name.
    That is the same disease as an unfrozen oracle set, one level over: the
    thing doing the measuring has to hold still.
    """
    from .refmodel.conform import conforming_implementation

    path = (Path(run_dir) / "specflow" / "witness.py"
            if run_dir is not None else None)
    if path is not None and path.is_file():
        held = path.read_text(encoding="utf-8")
        # HOLD STILL AGAINST THE SAME CONTRACT, which is the qualifier the rule
        # above was missing. The contract is regenerated by the architect on
        # every run -- it is a model call, not a cached artifact -- so a witness
        # written on one run can outlive the interface it was written against.
        #
        # a2-i2c: the contract in force declared eight outputs, the held witness
        # declared seven, and `busy` was the difference. It is never in a replay
        # row, so every oracle reading it abstains, and the stimulus loop spends
        # its budget and abandons the requirement as "never reached" -- six of
        # them, all attributed to the stimulus. A stale witness is worse than a
        # regenerated one: a second reading of the same requirements is a known
        # and bounded cost, while an interface mismatch is silent and is charged
        # to the wrong stage.
        if held.strip() and not _ports_agree(held, contract_json):
            logger.warning(
                "oracles: the held witness disagrees with the contract about "
                "the output ports -- regenerating rather than measuring "
                "against an interface that no longer exists")
        elif held.strip():
            return held, WITNESS

    source, issues = conforming_implementation(
        requirements=requirements, contract_json=contract_json, port=port,
        workdir=(Path(run_dir) / "specflow" / "_witness"
                 if run_dir is not None else Path(workdir) / "_witness"),
    )
    if not source:
        # No bound from above is a real weakening and it is reported as one.
        # Failing the run instead would be worse: unbounded oracles still find
        # defects, and this stage is not the last gate.
        logger.warning(
            "oracles: no witness produced (%d issue(s)); over-strictness is "
            "UNBOUNDED for this run", len(issues))
        return "", NO_BOUND
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return source, WITNESS



def _population(
    *, size: int, requirements: list[dict], contract_json: str, port: ModelPort,
    workdir: Path, run_dir: Path | None,
) -> tuple[str, ...]:
    """`size` independently written spec-derived designs, for the refutation leg.

    **THE SAME GENERATOR AS THE WITNESS, ASKED MORE THAN ONCE.** A witness is
    already a spec-derived design written from the requirements alone; a
    population is k of them. Each gets its own workdir so the cache returns a
    distinct sample rather than the same one k times -- the point is
    independent readings, and seven such readings fell into seven equivalence
    classes.

    **HELD ON DISK, FOR THE WITNESS'S REASON.** "The thing doing the measuring
    has to hold still." A strengthening round re-enters this stage, and a
    freshly drawn population would refute a different set of checks for no
    reason anyone could name. Normalization was measured varying on 77% of
    forms between two runs of the same inputs; a redrawn population would carry
    that variance straight into which checks get rejected.

    **IT IS NEVER SHOWN TO AN AUTHOR.** It reaches `_population_verdicts` and
    `variety`, both of which take verdicts and cells rather than sources.
    `brief` has no parameter a design could arrive through. That is what keeps
    this from becoming the witness pathology -- "it does not make the check
    more correct, it makes the check agree with the witness".

    Never raises: a population that cannot be built leaves the leg off, exactly
    as a missing witness leaves over-strictness unbounded rather than failing
    the run.
    """
    from .refmodel.conform import conforming_implementation

    if size < 2:
        #: One design contradicting a check is an ordinary disagreement. The
        #: refutation argument needs a population to be refuted BY.
        return ()
    root = (Path(run_dir) / "specflow" / "population"
            if run_dir is not None else Path(workdir) / "population")
    out: list[str] = []
    for i in range(size):
        held_path = root / f"{i}.py"
        if held_path.is_file():
            held = held_path.read_text(encoding="utf-8")
            #: THE WITNESS'S STALE-CONTRACT LESSON APPLIES HERE TOO. A design
            #: written against an interface that no longer exists makes every
            #: check reading the missing port abstain, and the cost is charged
            #: to the stimulus loop rather than to this.
            if held.strip() and _ports_agree(held, contract_json):
                out.append(held)
                continue
        try:
            source, _issues = conforming_implementation(
                requirements=requirements, contract_json=contract_json,
                port=port, workdir=root / f"_gen{i}")
        except Exception as exc:  # noqa: BLE001
            logger.info("population member %d not produced (%r)", i, exc)
            continue
        if not source:
            continue
        held_path.parent.mkdir(parents=True, exist_ok=True)
        held_path.write_text(source, encoding="utf-8")
        out.append(source)
    if len(out) < 2:
        logger.warning(
            "oracles: population of %d requested, %d produced -- the "
            "refutation leg stays OFF", size, len(out))
        return ()
    logger.info("oracles: population of %d spec-derived design(s)", len(out))
    return tuple(out)



# ----------------------------------------------------- the stimulus loop
#
# ALL UNEXERCISED ORACLES COME THROUGH HERE, and that is the point. z-i2c ended
# with 33 of them and `stimulus_added: 0` on all three debug turns, because the
# only route to stage one was a tool inside a turn that never called it.
#
# Detection and repair both belong at [O]. `build_artifacts` orders
# normalize -> S2 -> S3 -> stimulus -> [O] -> [R], so the stimulus exists when
# this runs, `stimulus_for_scenario` is a standalone generator, and liveness is
# already measured against the WITNESS with no reference model in existence.

def _evidence(ob, steps: list[dict], rep, result,
              *, route_ports: set[str],
              reset_ports: frozenset[str] | dict[str, int]) -> dict:
    """What one failed staging attempt actually established.

    Five sources, none of them a model call, each answering a different
    question -- because a retry that only rephrases is a retry that learns
    nothing. `obligation.py` already draws the distinction this rests on: an
    input-only activation "can be decided outright, by reading the stimulus
    steps. No model, no replay, no doubt", while a state-dependent one "cannot
    be confirmed. It CAN be refuted".
    """
    from .obligation import check_static

    out: dict = {}
    fired = check_static(ob, steps, reset_ports=reset_ports)
    if fired is not None:
        out["activation"] = f"{fired.status}: {fired.detail}"
    rows = list(getattr(rep, "error", "") and [] or rep.rows)
    if rows:
        first = dict(rows[0]["outputs"])
        moved: dict[str, int | None] = dict.fromkeys(first)
        for row in rows:
            for name, value in row["outputs"].items():
                if moved.get(name) is None and value != first.get(name):
                    moved[name] = row["edge"]
        out["edges"] = len(rows)
        out["inert"] = all(v is None for v in moved.values())
        out["first_change"] = moved
        if route_ports:
            silent = sorted(p for p in route_ports if moved.get(p) is None)
            out["route_ports_silent"] = silent
            # ALL of them, not any. A requirement observable at six ports of
            # which three moved has a working route -- the retry that was told
            # otherwise was steered away from the stimulus and toward a route
            # that was fine. Section 8.2 case 4 is "outputs moved but THE
            # route's port never did", and a route is only refuted when nothing
            # it names moved at all.
            out["route_never_moved"] = bool(silent) and len(silent) == len(route_ports)
    if getattr(rep, "error", ""):
        out["replay_error"] = rep.error
    if result is not None and result.detail:
        out["the_check_says"] = result.detail
    if getattr(rep, "notes", None):
        out["notes"] = list(rep.notes)
    return out


def _diagnose(ev: dict) -> str:
    """Which of the four failures this was. Each wants a DIFFERENT retry.

    Ordered by how much is known: a mechanically certain miss first, a refuted
    observation route last -- that one is a finding against normalisation and
    NOT a reason to spend another attempt on the stimulus.
    """
    activation = str(ev.get("activation") or "")
    if activation.startswith("not_fired"):
        return "a required input value was never driven"
    if ev.get("replay_error"):
        return "the replay did not run"
    if ev.get("inert"):
        return "nothing in the design moved -- a pacing problem, not a values one"
    if ev.get("route_never_moved"):
        return ("the ports this requirement is observed on never moved, so the "
                "observation route is what is wrong, not the stimulus")
    #: **"COULD NOT BE DECIDED" IS NOT "WAS DRIVEN", and collapsing them is how
    #: a check defect and a normalisation gap came to wear one string.**
    #: `_evidence` sets `activation` only when `check_static` returns a verdict,
    #: and `check_static` "Returns None when the obligation is not input-only,
    #: so a caller can tell 'this stimulus does not stage it' from 'this cannot
    #: be answered here'." An ABSENT key is the second of those. Falling
    #: through to the line below asserted the first.
    #:
    #: Measured on a full run: all 17 requirements abandoned under the old
    #: fallthrough had NO activation evidence at all, so every one of them was
    #: reported as "the activation was driven" on the strength of a key that
    #: was never written. They are the state-dependent activations -- the same
    #: population as the 78 of 115 normalized forms carrying no `inputs`
    #: predicate -- and what they need is a probe naming the state, not another
    #: stimulus attempt and not a rewritten check.
    if "activation" not in ev:
        return ("the activation is state-dependent, so nothing here could "
                "decide whether it occurred -- it needs a probe naming the "
                "state, not another stimulus attempt")
    #: The activation fired and the check still said nothing. THIS one is the
    #: check's defect and belongs with its author.
    return "the activation was driven and the check still saw nothing"


def _pool_block(*, target: str, pool: dict, contract: dict,
                stimulus_by_tp: dict, own: list[str], relation,
                tried: list[str]) -> str:
    """What the suite has already reached, handed to the stimulus author.

    THE DISCIPLINE THIS EXISTS FOR: the author is never asked to invent a path
    to a state. It is handed a stimulus that already ran, already reached the
    nearest state we have, and asked to extend it by one hop. Three properties
    follow, and each is why a design choice is what it is:

    * GROUNDED -- every prefix here is a recorded stimulus that actually
      produced the state it claims to, with its digest. The mined edge is
      ANNOTATION on that stimulus, never a substitute for it: a synthesised
      recipe can be wrong, has no reproducer behind it, and asks the author to
      build a whole stimulus around it.
    * COMPOSABLE -- the task shrinks from "reach LREFILL3 from reset" to "here
      are the steps that reach CLOAD; the spec says LREFILL3 follows CLOAD when
      tagcomp_miss and biudata_valid; add that". One hop is a task a stimulus
      author does well; a whole path is the one that fails today.
    * MONOTONE -- the pool never shrinks, so a testpoint minted while staging
      one check feeds every later one. Staging rounds compound instead of
      restarting.

    WHO PICKS THE PREDECESSOR, AND WHY IT IS THE AUTHOR. For a state that has
    been observed, adjacency is measured. For one nothing has reached, NO
    mechanical source knows it: the relation has no edge into a state that never
    rose, and "hand over the deepest state" assumes a chain and picks the wrong
    branch on a fork -- k1 forks at CLOAD and CSTORE at the same depth. So the
    pipeline hands over every reachable prefix and the specification's own words,
    and the author picks. The pick is CHECKED, not trusted: the attempt succeeds
    only if the target rose. A wrong pick costs one call and is named in the
    next attempt's `attempts so far`.
    """
    spans = reachability.states_from(contract)
    obs = pool.get(target) or []
    status = (f'observed on {obs[0].tp_uid} at edge {obs[0].first_edge}'
              if obs else "never observed")
    lines = [f'<pool target="{target}" status="{status}">']

    want = spans.get(target) or {}
    if want.get("spans"):
        lines.append(f'  what the spec says about {target}: '
                     f'{want["spans"][0]!r}')
    if own:
        lines.append("  states this check's own testpoints reached: "
                     + ", ".join(own))

    lines.append("  the pool -- every state any testpoint has reached:")
    for probe, entries in sorted(pool.items()):
        span = ((spans.get(probe) or {}).get("spans") or [""])[0]
        if not entries:
            lines.append(f"    {probe:<14} never")
            continue
        first = entries[0]
        rises = sum(o.rises for o in entries)
        lines.append(
            f"    {probe:<14} rises {rises:<5} shortest {first.tp_uid} "
            f"@ edge {first.first_edge}   {span[:70]!r}")

    for probe in own:
        entries = pool.get(probe) or []
        if not entries:
            continue
        first = entries[0]
        steps = stimulus_by_tp.get(first.tp_uid) or []
        prefix = reachability.stimulus_prefix(steps, first.first_edge)
        lines.append(f"  prefix reaching {probe} ({first.tp_uid}, "
                     f"steps 1-{len(prefix)} of {len(steps)}) -- "
                     f"held {first.held} edge(s):")
        lines.append("    " + json.dumps(prefix))
        for edge in (relation.into(probe) if relation is not None else []):
            if reachability.gate_reachability(edge):
                req = ", ".join(f"{k}={v}" for k, v in sorted(edge.requires.items()))
                lines.append(f"    how {probe} was entered (mined, "
                             f"{edge.precision:.0%} holdout): from "
                             f"{edge.frm or 'reset'} when {req}")
                break

    lines.append("  attempts so far: "
                 + (", ".join(tried) if tried else "none"))
    lines.append("</pool>")
    lines.append(
        f"Pick the pool state the specification says precedes {target}, and "
        f"extend that prefix by the hop the specification describes. Do not "
        f"restart from reset.")
    return "\n".join(lines)


def _hint(req: dict, shape: dict, ev: dict | None, attempt: int,
          reset_ports: dict[str, int] | None = None, saw: str = "",
          pool_block: str = "") -> str:
    """What to stage, in the vocabulary S2 uses. Never a repeat.

    `what_the_scenario_needs` goes where S2's `stimulus` field goes, so this is
    prose about what must happen -- the harness generates the vectors and gates
    them, which is what keeps a testpoint minted here indistinguishable from one
    minted at build time.
    """
    act = (shape.get("activation") or {})
    parts = [
        f"Stage the situation this requirement is about: {act.get('text') or req.get('text', '')}",
    ]
    # THE POOL GOES FIRST, because it is the concrete thing: a stimulus that
    # ran and reached a state, to be extended by one hop. Everything below is
    # prose about what to aim for; this is what to start from. Absent when no
    # probe is declared or nothing has been reached, and then the hint is
    # exactly today's -- the change is never worse than the present.
    if pool_block:
        parts.append(pool_block)
    # THE CHECK IS WHAT HAS TO FIRE, AND IT ALREADY SAID WHY IT DID NOT.
    # `saw` is the abstaining check's own `detail`. The activation line above is
    # a DIFFERENT sentence about the same requirement -- normalization's reading,
    # not the author's -- and where the two diverge, stimulus aimed at the
    # activation stages a scenario the check does not recognise. The attempt is
    # then spent, the check still abstains, and the record says "never reached"
    # about a scenario nobody ever tried to reach.
    #
    # Measured on k1-dcfsm: re-aiming the loop at the check's own account
    # reached 3 abstainers that aiming at the normalized activation had not
    # reached in any attempt.
    if saw and saw != NO_ACCOUNT:
        parts.append(
            "The check for this requirement decided NOTHING on every testpoint "
            f"it already names, and this is the account it gave: {saw}. That "
            "sentence is the target. Stage what the CHECK says it did not see, "
            "which is not always what the activation above describes.")
    # RESET IS NOT A DRIVABLE INPUT, and a hint that does not say so sends the
    # generator to drive a port the schema forbids. The runtime owns reset and
    # offers a first-class step for it; the generator's own prompt documents
    # `{"reset": true}`, but nothing here ever pointed at it.
    #
    # All three of a2-i2c's genuinely-attempted reset requirements -- REQ-0006,
    # REQ-0007, REQ-0009 -- spent every attempt this way. Their ports moved each
    # time, so the design was running; the RESET scenario was simply never
    # staged, because the hint asked for "rst asserted high" and the schema has
    # no such input.
    from .testcase_agent import _WANTS_RESET_ASSERTED
    if _WANTS_RESET_ASSERTED.search(str(act.get("text") or "")
                                    + " " + str(req.get("text") or "")):
        parts.append(
            'This scenario needs RESET ASSERTED, which is not a drivable input '
            '-- the runtime owns reset on both sides at once. Use a reset step: '
            '{"reset": true} (or {"reset": true, "hold": N} to hold it N edges), '
            'then the steps that observe what reset left behind. Do not try to '
            'drive rst or nReset as a value; the schema has no such input and '
            'the step will be rejected.')
        # AND ON A DESIGN WITH TWO RESETS, `true` IS THE WRONG FORM. It asserts
        # both at the same edge, so "rst asserted while nReset is released" has
        # zero rows in the replay and the oracle abstains by construction --
        # measured on a2-i2c at 204 edges. `asserted_resets(only=...)` and the
        # step schema both take a port list now; this is the only place that can
        # tell the generator which port THIS requirement is about, and until it
        # did, the hint named the one form that cannot express the scenario.
        names = sorted(reset_ports or ())
        if len(names) > 1:
            haystack = f"{req.get('text') or ''} {act.get('text') or ''}"
            named = [n for n in names
                     if re.search(rf"\b{re.escape(n)}\b", haystack, re.I)]
            others = ", ".join(n for n in names if n not in named) or "the others"
            parts.append(
                f'This design has MORE THAN ONE RESET PORT ({", ".join(names)}), '
                'and {"reset": true} asserts all of them at the same edge -- so a '
                'requirement about what ONE reset does can never be observed that '
                'way, because the other is asserted too. Use the port-list form '
                + (f'{{"reset": {json.dumps(named)}, "hold": N}}, which asserts '
                   f'only {", ".join(named)} and leaves {others} at its idle '
                   'value.'
                   if len(named) == 1 else
                   '{"reset": ["<port>"], "hold": N} naming the ONE reset port '
                   'this requirement is about; the rest stay at their idle '
                   'value.'))
    # ARBITRATION LOOKS UNSTAGEABLE AND IS NOT. `al` is asserted when the
    # controller releases SDA and reads back a low it did not drive -- which
    # needs a second bus master, and there is no second master to ask. But
    # `sda_i` and `scl_i` ARE drivable (only clk and the resets are excluded),
    # so the competing master is emulated by driving the line low while the
    # controller has released it, and `until` waits for that release rather
    # than guessing when it happens.
    #
    # Three of a2-i2c's five route-refused abandonments hinge on `al`
    # (REQ-0010, REQ-0020, REQ-0021), refused with "the ports this requirement
    # is observed on never moved". The schema could always say this; nothing
    # ever suggested it -- the same shape as the reset case.
    watched = set(shape.get("observable") or [])
    if watched & _ARBITRATION_PORTS:
        parts.append(
            "This scenario needs ARBITRATION LOST, which needs a second bus "
            "master -- emulate one. Drive the transfer, use "
            '{"until": {"port": "sda_oen", "value": 1}} to wait until the '
            "controller has RELEASED SDA, then in the next step drive sda_i=0 "
            "while it is still released. The controller reads back a low it did "
            "not drive, which is exactly the condition. Do not expect al to "
            "move without that contention: nothing else in a single-master "
            "sequence produces it.")
    if act.get("inputs"):
        parts.append("It applies when these inputs hold: "
                     + ", ".join(f"{k}={v}" for k, v in sorted(act["inputs"].items())))
    # THE REACHING SEQUENCE, WITHOUT WHICH A STATEFUL ACTIVATION IS UNSTAGEABLE.
    # "Get the FSM into START_B" is not a step list; "issue START as REQ-0012
    # prescribes, then hold" is. A requirement whose activation is not
    # `input_only` has no drivable values of its own, so retries without this
    # are rephrasings carrying no new reachability information -- which is why
    # this loop's results have to be read split by activation class.
    for i, hop in enumerate(shape.get("activated_via") or [], 1):
        hop_act = hop.get("activation") or {}
        line = (f"  {i}. first, {hop_act.get('text') or 'as ' + hop.get('through_req', '')} "
                f"(what {hop.get('through_req', '')} prescribes)")
        if hop_act.get("inputs"):
            line += (" -- drive "
                     + ", ".join(f"{k}={v}"
                                 for k, v in sorted(hop_act["inputs"].items())))
        if i == 1:
            parts.append("The situation is a STATE, not a set of values. Reach "
                         "it in this order:")
        parts.append(line)
    # The port the scenario has to make move, when it is not this requirement's
    # own. Without it the generator aims at nothing observable.
    routes = shape.get("observed_via") or []
    if routes:
        parts.append(
            "This requirement is observed at another requirement's port. The "
            "scenario must make the difference visible: "
            + "; ".join(f"{r.get('port')} -- {r.get('shows')}" for r in routes[:2]))
    if shape.get("expectation"):
        parts.append(f"What must then be true: {shape['expectation']}")
    if ev:
        parts += [
            "",
            f"Attempt {attempt} did not stage it. {_diagnose(ev)}.",
            f"What that attempt actually produced: {json.dumps(ev, default=str)}",
            "Change the steps in the light of that rather than restating them.",
        ]
    return "\n".join(parts)




#: What `unexercised_against` reports when the check itself said nothing --
#: a `decide` whose abstaining branch returns an empty detail. Nothing can be
#: aimed at it, so `_hint` skips it rather than quoting it back at the author.
NO_ACCOUNT = "the check never saw its scenario in this stimulus"


def unexercised_against(held: dict, witness: str, contract: dict,
                        stimulus_by_tp: dict, *, base: str,
                        transactional: bool) -> dict[str, str]:
    """`req_uid -> why`, for checks that abstain on every testpoint they name.

    COMPUTED DIRECTLY, not read off `liveness`. The loop's first version used
    `liveness.never_decides`, which is the right IDEA and the wrong SOURCE: it
    requires the liveness sweep to have populated `record["base"]`, and a sweep
    that comes back UNKNOWN populates nothing -- so an oracle that abstains on
    everything was invisible to the loop precisely when the instrument measuring
    it had also failed. Caught by running the stage end to end rather than the
    loop in isolation.

    `decide_all` already answers this and its tri-state is the definition:
    `ok is None` means the clause's scenario never occurred (`oracles.py:314`).
    """
    from .refmodel.oracles import decide_all

    if not held or not witness:
        return {}
    try:
        results = decide_all(list(held.values()), witness, contract,
                             stimulus_by_tp, base=base,
                             transactional=transactional)
    except Exception as exc:  # noqa: BLE001 -- a measurement, never the stage
        logger.warning("oracles: could not decide the set for staging: %r", exc)
        return {}
    # THE CHECK'S OWN SENTENCE, not a fixed string. `detail` is what the
    # author wrote for the abstaining branch -- the account of the thing the
    # check was waiting for and did not see -- and it is the only description
    # of the missing scenario written in the check's own terms. Collapsing it
    # to one constant threw away the whole payload and left the staging loop
    # aiming at the NORMALIZED activation instead, which is a different
    # sentence about the same requirement written by a different stage.
    return {r.req_uid: (str(r.detail).strip() or NO_ACCOUNT)
            for r in results if r.unexercised()}


def _staged_element(tp_uid: str, req_uid: str, req: dict, shape: dict, *,
                    stimulus: str) -> dict:
    """A minted testpoint that passes S2's OWN gate -- which `--reuse` re-runs.

    THE DEFECT THIS FIXES, and it is an ordering one. The staging loop appends
    to `testplan` AFTER S2's gate has run, and nothing re-gates the artifact
    afterwards, so the first thing ever to look at these elements was `--reuse`
    on the NEXT run: `_reuse` (`integration.py:146`) re-runs `s2_testplan.gate`
    and regenerates when it errors. d1-i2c's own testplan failed its own gate
    with 106 errors over 53 elements, two each -- `expected_response: empty` and
    `check_method: empty`. So a resumed run paid for S2 and S3 again every time,
    and no experiment holding the testplan fixed could be run at all.

    NOTHING HERE IS INVENTED, which is what decides the wording. Filling a field
    with plausible prose to satisfy a gate would make the gate measure nothing --
    the same failure as a vacuous check, one artifact up. `expected_response` is
    the NORMALIZED EXPECTATION: the predicate the check was written from, already
    stated over observable outputs, which is exactly what the field asks for.
    `check_method` says what actually decides this testpoint -- the frozen check
    for `req_uid`, over the recorded trace. A staged testpoint has no other check
    and never had one.
    """
    expected = str(shape.get("expectation") or "").strip()
    if not expected:
        # No normalized expectation to quote. The requirement's own text is the
        # weaker answer and still a TRUE one; that is the trade to make here.
        expected = (str(req.get("text") or "").strip()
                    or f"the behaviour {req_uid} describes")
    ports = ", ".join(shape.get("observable") or ()) or "its observable outputs"
    return {
        "uid": tp_uid, "covers": [f"{req_uid}@1"],
        "stimulus": stimulus,
        "expected_response": expected,
        "check_method": (
            f"the frozen check for {req_uid} decides this trace, reading "
            f"{ports}. It was staged because that check abstained on every "
            f"testpoint it already named."),
        "dimension": "D2_control_flow",
    }


def stage_unexercised(
    *,
    held: dict,
    unexercised: dict[str, str],
    requirements: list[dict],
    normalized: dict[str, dict],
    contract: dict,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    witness: str,
    port,
    base: str = "step",
    attempts: int = STAGING_ATTEMPTS,
    budget: int | None = None,
    #: What earlier rounds already spent on each requirement. ATTEMPTS ARE PER
    #: REQUIREMENT, NOT PER ROUND: this loop now runs once per verify round, so
    #: without carrying the count three rounds of three attempts would be nine,
    #: and "staged N times, never reached" would stop being true of anything.
    prior: dict[str, dict] | None = None,
    #: Whether an exhausted requirement may be ABANDONED now.
    #:
    #: False on every round but the last, and the reason is semantic rather than
    #: cautious: between rounds the AUTHOR REWRITES THE CHECK, so its activation
    #: is a different scenario. "Never reached in N attempts" taken at round 1
    #: is a verdict about a trigger that no longer exists by round 2. Attempts
    #: accumulate across rounds; the disposition is taken once, at the end.
    final: bool = True,
) -> tuple[dict[str, str], dict[str, dict]]:
    """Stage the scenarios nothing reaches. `(abandoned, record)`.

    THE TEST AT THE CENTRE IS `decide` RETURNING A VERDICT AT ALL. An oracle
    abstains (`ok is None`) exactly when its activation never occurred
    (`oracles.py:314-317`), so a non-`None` result IS the proof that the
    scenario is now staged -- computed from the run, not claimed by the
    generator.

    THE LOOP IS BLIND TO WHICH VERDICT, AND MUST BE. `True` and `False` both
    end it, identically. Gating on `True` would be the vacuity failure moved
    down a level: stimulus tuned until the implementation passes is stimulus
    selected to avoid finding bugs, and it would do so silently under a green
    artifact. The loop is not allowed a preference because it is not allowed an
    opinion about the design -- it asks "is this scenario staged", which is
    settled the moment the check stops abstaining. `_worst` (`oracles.py:373`)
    enforces the same discipline one level up, so that "a grown evidence set
    only ever moves a verdict toward worse".

    That blindness is also what makes running against the WITNESS sound. Whether
    the scenario occurs is a property of stimulus and activation, not of the
    design; whether the requirement HOLDS is the debug loop's question and is
    not asked here. A loop that optimised for `True` against the witness would
    be tuning the suite to one implementation's behaviour.

    Appends only. Nothing existing is edited, so a grown stimulus set cannot
    make a scenario stop occurring -- the `add_testcase` discipline.

    MUTATES `stimulus_by_tp` AND `testplan` IN PLACE, deliberately: what this
    stages has to be in the suite the reference model is then debugged against,
    and returning a copy would leave the caller deciding whether to adopt it.
    """
    from .ids import PREFIX_TESTPLAN, mint, next_index
    from .obligation import Obligation
    from .ports import asserted_resets
    from .refmodel.oracles import decide, replay
    from .testcase_agent import stimulus_for_scenario

    abandoned: dict[str, str] = {}
    record: dict[str, dict] = {uid: dict(r) for uid, r in (prior or {}).items()}
    if not unexercised or not witness:
        return abandoned, record
    if budget is None:
        # Same per-state sizing as the caller's, for the paths that reach here
        # without one -- a direct call, or a resumed run. Keeping the two in one
        # function is what stops them from drifting into two different budgets
        # for the same question.
        budget = _size_budget(unexercised, normalized or {}, contract,
                              witness, stimulus_by_tp, base)
        logger.info("oracles: staging budget %d testpoint(s) for %d unexercised "
                    "oracle(s)", budget, len(unexercised))

    # The ACTIVE level per reset port, not just the names: `check_static` needs
    # it to tell "while rst is asserted" (wants a reset step) from "while not in
    # reset" (wants nothing, and is every trace's default).
    reset_ports = asserted_resets(contract)
    by_uid = {str(r.get("uid") or ""): r for r in requirements}
    added: list[str] = []

    # WHICH UNOBSERVED STATE EACH ABSTAINER IS BLOCKED ON, so the shared budget
    # can be shared honestly. A budget that is per state but a record that is
    # per check would starve every dependent after the first: the allocation
    # runs out, the later checks record "nothing was attempted", and they block
    # as NOT_EXERCISED -- strictly worse than the per-check budget they replaced,
    # which at least dispositioned all of them.
    #
    # So a check whose allocation a SIBLING spent inherits that sibling's
    # attempts, and is replayed on the testpoints those attempts produced. The
    # replay is free -- Python against the witness, no model call -- and it is
    # the thing that lets a testpoint minted for one check decide another
    # waiting on the same state.
    _tri = _probe_triage(unexercised, held, normalized or {}, contract, witness,
                         stimulus_by_tp, base)
    _blocked = _tri.blocked
    _relation = (reachability.mine(
        reachability.rows_for(witness, stimulus_by_tp, contract, base=base),
        reachability.probes_of(contract)) if _blocked else None)
    _by_state: dict[str, dict] = {}
    #: What has already been tried for each state, so a retry does not repeat a
    #: pick. A wrong pick costs one call; repeating it costs the rest.
    _tried: dict[str, list[str]] = {}

    def _state_order(u: str) -> tuple:
        """Dependents of one state adjacent, so the first spends and the rest
        inherit. Deterministic: same inputs, same order, same record."""
        return (_blocked.get(u) or "", u)

    for uid in sorted(unexercised, key=_state_order):
        oracle = held.get(uid)
        req = by_uid.get(uid)
        if oracle is None or req is None:
            continue
        earlier = (prior or {}).get(uid) or {}
        spent = int(earlier.get("attempted") or 0)
        # No `continue` when the attempts are already spent: `range(spent + 1,
        # attempts + 1)` is empty, and falling THROUGH is what lets the record
        # and the disposition below still be taken. Skipping here meant a
        # requirement that exhausted its budget in an earlier round could never
        # be abandoned at all.
        shape = normalized.get(uid) or {}
        act = shape.get("activation") or {}
        saw = str(unexercised.get(uid) or "").strip()
        # `.of`, never the bare constructor -- it resolves symbols through the
        # port's encoding and normalises a value-set to a tuple.
        ob = Obligation.of(uid, str(act.get("text") or ""),
                           act.get("inputs") or {},
                           shape.get("observable") or (), contract)
        route_ports = set(shape.get("observable") or ())
        tries: list[dict] = []
        evidence: dict | None = None
        reached: int | None = None
        #: Which states this requirement's attempts actually entered. An
        #: `ABANDONED` that can say "never observed; prefixes tried X, Y;
        #: reached Q instead" is a finding; one that says only "never reached"
        #: blames the testplan for something it may have had no part in.
        reached_states: set[str] = set()

        target = _blocked.get(uid) or ""
        shared = _by_state.get(target) if target else None

        for attempt in range(spent + 1, max(1, attempts) + 1):
            if len(added) >= budget:
                if shared and shared.get("staged_uids"):
                    # A SIBLING SPENT THIS CHECK'S ALLOCATION, on its behalf and
                    # on the same state. Replay this check on what that bought:
                    # the state is what both are waiting for, so a testpoint that
                    # reached it decides both, and one that did not is evidence
                    # for both.
                    for shared_tp in shared["staged_uids"]:
                        if shared_tp not in oracle.tp_uids:
                            oracle.tp_uids.append(shared_tp)
                        rep_s = replay(witness, contract,
                                       stimulus_by_tp.get(shared_tp) or [],
                                       base=base)
                        res_s = (None if rep_s.error else decide(
                            oracle, rep_s.rows,
                            unavailable=rep_s.unavailable))
                        if res_s is not None and res_s.ok is not None:
                            reached = attempt
                            tries.append({
                                "attempt": attempt, "staged": shared_tp,
                                "shared_with": shared["first"],
                                "outcome": f"the check decided ({res_s.ok})"})
                            break
                    else:
                        tries.extend(
                            {**t, "shared_with": shared["first"]}
                            for t in shared["attempts"])
                    break
                tries.append({"attempt": attempt, "outcome": BUDGET_SPENT})
                break
            block = ""
            if target:
                block = _pool_block(
                    target=target, pool=_tri.pool, contract=contract,
                    stimulus_by_tp=stimulus_by_tp,
                    own=reachability.own_reached(oracle.tp_uids, _tri.pool),
                    relation=_relation, tried=_tried.get(target) or [])
            steps = stimulus_for_scenario(
                requirement=req, contract=contract, port=port,
                what_the_scenario_needs=_hint(req, shape, evidence, attempt - 1,
                                              reset_ports=reset_ports, saw=saw,
                                              pool_block=block),
            )
            if not steps:
                tries.append({"attempt": attempt,
                              "outcome": "nothing gate-clean was produced"})
                continue
            tp_uid = mint(PREFIX_TESTPLAN, next_index(
                [str(t.get("uid", "")) for t in testplan]
                + list(stimulus_by_tp), PREFIX_TESTPLAN))
            stimulus_by_tp[tp_uid] = steps
            testplan.append(_staged_element(
                tp_uid, uid, req, shape,
                stimulus=_hint(req, shape, None, 0, reset_ports=reset_ports,
                               saw=saw)))
            added.append(tp_uid)
            if tp_uid not in oracle.tp_uids:
                oracle.tp_uids.append(tp_uid)

            rep = replay(witness, contract, steps, base=base)
            result = (None if rep.error else decide(
                oracle, rep.rows, unavailable=rep.unavailable))

            # DID THE STATE RISE? Read from the row, mechanically, and recorded
            # separately from whether the check decided.
            #
            # Those are two different questions and the loop has always
            # conflated them -- its success test is `decide` returning a verdict
            # at all, so "we could not reach it" and "we reached it and the
            # check did not notice" come out identical. The k1 triage found the
            # second is the common case. Keeping them apart is what lets an
            # attempt that REACHED the state hand the check to its author with
            # the new testpoint as evidence, instead of spending another
            # attempt on stimulus that already worked.
            rose = sorted(
                p for p in (reachability.waiting_on(
                    shape, reachability.probes_of(contract)) or [])
                if not rep.error and any(
                    (r.get("outputs") or {}).get(p) for r in rep.rows))
            if rose:
                reached_states.update(rose)
            if target:
                _tried.setdefault(target, []).append(
                    f"attempt {attempt}: reached {rose or 'nothing new'}")

            # THE TEST. Both True and False end the loop -- see the docstring.
            if result is not None and result.ok is not None:
                reached = attempt
                tries.append({"attempt": attempt, "staged": tp_uid,
                              "outcome": f"the check decided ({result.ok})"})
                break
            evidence = _evidence(ob, steps, rep, result,
                                 route_ports=route_ports,
                                 reset_ports=reset_ports)
            tries.append({"attempt": attempt, "staged": tp_uid,
                          "outcome": "the check still abstained",
                          "diagnosis": _diagnose(evidence),
                          "evidence": evidence})

        # AN ATTEMPT IS A GENERATOR CALL, not a testpoint that came back usable.
        # A generator that ran and returned nothing gate-clean HAS been tried --
        # that is a finding about the scenario. The only outcome that is not an
        # attempt is the budget running out before the generator was invoked.
        tries = list(earlier.get("attempts") or []) + tries
        if target and target not in _by_state:
            staged_here = [t["staged"] for t in tries if t.get("staged")]
            if staged_here:
                _by_state[target] = {
                    "first": uid, "staged_uids": staged_here,
                    "attempts": [t for t in tries
                                 if t.get("outcome") != BUDGET_SPENT],
                }
        attempted = sum(1 for t in tries if t.get("outcome") != BUDGET_SPENT)
        staged_count = sum(1 for t in tries if t.get("staged"))
        reached = reached or earlier.get("reached_at_attempt")
        record[uid] = {"attempts": tries, "reached_at_attempt": reached,
                       "staged": staged_count, "attempted": attempted,
                       # What the staging actually achieved, as opposed to
                       # whether the check then fired.
                       "prefix_from": sorted(
                           reachability.own_reached(oracle.tp_uids, _tri.pool)),
                       "reached": sorted(reached_states),
                       "waiting_on": target or ""}
        if not final:
            # Round is not the last, so the check may still be rewritten and the
            # scenario with it. Record the attempts; take no disposition.
            continue
        if reached is None and attempted:
            # ATTEMPTED AND EXHAUSTED. What is known is that we could not stage
            # it in N tries -- not that no stimulus could, which is a claim
            # about the requirement this has no evidence for.
            #
            # **AND IT SAYS WHICH FAILURE, because "never reached" charged
            # every one of them to this loop.** `_diagnose` already separates
            # four, and the stage was throwing that away at the one place a
            # reader counts losses by stage. Measured on a full run: of 30
            # requirements abandoned here, 17 had their activation DRIVEN and
            # the check still saw nothing, 8 were `route_never_moved` -- which
            # `_diagnose` calls "a finding against normalisation" -- and only 5
            # were the pacing failure this loop can actually act on. Reading
            # that as 30 stimulus failures is how the stimulus loop came to
            # look like the binding constraint.
            #
            # THE BUDGET IS UNCHANGED, deliberately. The tempting move is to
            # stop retrying once the diagnosis says normalisation, and the same
            # run refutes it: of 27 requirements that hit `route_never_moved`
            # at some attempt, **3 were reached at a later one**. Exiting early
            # would have saved 44 attempts and lost those 3. So this changes
            # what the loss is CALLED, not what is spent on it.
            last = [t.get("evidence") or {} for t in tries if t.get("evidence")]
            said = _diagnose(last[-1]) if last else ""
            abandoned[uid] = (f"never reached in {attempted} attempt(s)"
                              + (f" -- {said}" if said else ""))
            logger.info("oracles: %s staged %d time(s), never reached (%s)",
                        uid, staged_count, said or "no evidence")
        elif reached is None:
            # NOT ABANDONED, BECAUSE NOTHING WAS ATTEMPTED. Budget exhaustion is
            # precisely "the loop did not run", and section 8.0 makes that the
            # one thing the softening may not be reached by: "a requirement may
            # only be abandoned if the attempt actually ran... without that
            # pairing the gate rewards not trying."
            #
            # It fired. On a2-i2c the flat budget covered four requirements and
            # the other THIRTY-SIX were recorded "never reached" -- a claim about
            # the design and the stimulus -- when the truth was that no stimulus
            # was ever generated for them. The old code reached this line with
            # `sum(... if t.get("staged"))` evaluating to zero and abandoned them
            # anyway, so the log line stated the count that should have stopped
            # it. Left NOT_EXERCISED, it blocks, which is what a harness defect
            # should do.
            logger.warning(
                "oracles: %s was never staged (%s) -- left NOT_EXERCISED so it "
                "BLOCKS, because nothing was attempted", uid,
                "; ".join(sorted({str(t.get("outcome") or "") for t in tries})))
    if added:
        logger.info("oracles: staged %d new testpoint(s) for %d requirement(s); "
                    "%d still unreached", len(added), len(record), len(abandoned))
    return abandoned, record



def _decides_nothing(testplan: list[dict],
                     oracles: list[RequirementOracle]) -> list[str]:
    """Testpoints in the plan that no oracle names.

    Each one still renders and still starts a simulator process
    (`run.py:200-204`), and nothing it produces decides anything. That is the
    inert-testbench failure this project exists to prevent, one level up:
    stimulus that runs and proves nothing. `qualify.py:3-22` makes the argument
    for the suite; it holds identically here.

    Reported, not acted on. The remedy is a testplan change or an oracle-scoping
    decision, and neither belongs to this stage -- but it must not be silent,
    because a suite that grows while this number grows with it looks like
    progress.
    """
    named = {tp for o in oracles for tp in o.tp_uids}
    return sorted({str(e.get("uid")) for e in testplan if e.get("uid")} - named)


def _correspondence_round(round_: int,
                          reviews: dict[str, correspondence.Review]) -> dict:
    """One round's correspondence outcome, split by which leg refused.

    BUILT FROM THE REVIEWER'S OWN VERDICTS, NOT FROM `rejected`, and the
    difference is the point. `verify_one` reports ONE reason per oracle and
    checks correspondence before the variants leg, so `rejected` shows a check
    that is both off-target and vacuous as off-target, and shows nothing at all
    for one the witness stopped first. Counting rejections there would measure
    the stage's precedence order. Counting them here measures the instrument,
    which is the only thing its published rate can be compared against.

    A parse error is not a rejection -- `rejects` already returns "" for one --
    so a call that failed is absent from both lists and still counted in
    `reviewed`. That is deliberate: it keeps `reviewed` the number of oracles
    PUT to the gate rather than the number it managed to answer, and the two
    diverging is itself worth seeing.
    """
    legs: dict[str, list[str]] = {"off_target": [], "not_assertable": []}
    for uid, review in sorted(reviews.items()):
        why = correspondence.rejects(review)
        if why.startswith("not-assertable:"):
            legs["not_assertable"].append(uid)
        elif why:
            legs["off_target"].append(uid)
    return {"round": round_, "reviewed": len(reviews), **legs}


def _route_declines(route: dict) -> bool:
    """Did this route take the escape hatch, read from the slot that owns it?

    **THIS USED TO READ `shows` AND THE SCHEMA PUTS THE HATCH IN `otherwise`.**
    `Route` carries two slots -- `shows` is what the port does when the
    requirement HOLDS, `otherwise` what it does when it does not -- and
    `route_shows_issue` tells an author with a genuine tautology to put
    `NO_DISCRIMINATION` in `otherwise`. Reading `shows` inverted both paths, and
    `route_shows_issue`'s own docstring describes the inversion as a defect it
    already fixed on its side:

        "writing the opt-out into `shows` skipped the check while writing the
         real second case into `shows` was refused. The lenient path and the
         strict path were the wrong way round."

    It was fixed in `normalize` and left standing in this consumer, so it cut
    both ways at once:

      * an author FOLLOWING the schema put the hatch in `otherwise`, this read
        `shows`, saw no decline -- and the tautology was never recorded as a
        finding. It went to an author and became a check that cannot fail,
        which is precisely what the hatch exists to prevent;
      * an author whose `shows` prose happened to contain the phrase was
        ABANDONED, losing the requirement its check and the run its span.

    The predicate itself stays lenient, because on `otherwise` it is asking a
    short slot whose whole job is the second case -- not scanning free prose.
    """
    return _declines(str(route.get("otherwise", "") or ""))


def _declines(shows: str) -> bool:
    """Did normalisation explicitly say this requirement has no second case?

    Imported rather than re-spelled: `normalize` owns the sentinel, and a second
    copy of the phrase here would drift from it silently -- the disposition
    would stop firing and nothing would say why.
    """
    from .normalize import declines_discrimination

    return declines_discrimination(shows)


def _dispositions(
    *, requirements: list[dict], trusted: list[RequirementOracle],
    rejected: dict[str, str], had_source: set[str],
    normalized: dict[str, dict] | None,
    #: `req_uid -> why we gave up`. Wins over every other disposition: a stage
    #: that ran a bounded attempt and exhausted it knows more than any claim
    #: derived from the text, and its reason is the one worth reporting.
    abandoned: dict[str, str] | None = None,
    #: `liveness.never_decides` -- oracles that returned no decision on any
    #: testpoint they name. A check that cannot fire is not evidence.
    never_decides: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """One verdict per requirement, and never fewer.

    `UNOBSERVABLE` is settled at normalization, EXCEPT that a working oracle
    refutes it -- see below.
    """
    norm = normalized or {}
    ok = {o.req_uid for o in trusted}
    inert = set(never_decides or {})
    gave_up = dict(abandoned or {})
    out: dict[str, str] = {}
    why: dict[str, str] = {}
    for req in requirements:
        uid = str(req.get("uid") or "")
        if not uid:
            continue
        shape = norm.get(uid) or {}
        blind = bool(shape) and not (shape.get("observable") or [])
        if uid in gave_up:
            # ATTEMPTED AND EXHAUSTED, and that outranks everything below.
            #
            # `UNOBSERVABLE` and `NOT_EXERCISED` are claims about the
            # REQUIREMENT -- no port shows it, no stimulus reaches it -- and
            # both can be false. What is known after a bounded attempt is
            # narrower and about us: we could not turn this requirement into a
            # check we can exercise. Reporting the broader claim when the
            # narrower one is what was measured is the mistake normalisation
            # already made at scale, calling 27 of 77 requirements unobservable
            # by reading each one's mechanism, 10 of which had working checks.
            out[uid] = "ABANDONED"
            why[uid] = gave_up[uid]
        elif uid in ok and not (blind and uid in inert):
            # A WORKING ORACLE REFUTES `UNOBSERVABLE`. Normalization claimed
            # this requirement has no boundary observable; an oracle for it then
            # named a declared port, ran, and survived every gate, which is only
            # possible if something observable was there. The oracle is evidence
            # and the claim is not, so the claim loses.
            #
            # Not hypothetical: normalization's first live run called 27 of 77
            # requirements UNOBSERVABLE by reading each one's MECHANISM rather
            # than its effect, and it was caught exactly this way -- 10 of the 27
            # already had screened oracles.
            #
            # Ordering this the other way also made the artifact contradict
            # itself: on n-i2c it reported 62 TRUSTED beside 70 frozen oracles,
            # because 8 requirements were called a spec defect while their
            # oracles sat in the set driving the loop -- which then silently
            # overwrote the verdict, since it decides whatever it is given.
            # AND SURVIVING IS NOT DECIDING, which is the half this was
            # missing. Nothing rejects an oracle for never firing -- the
            # unexercised replay is explicitly not a finding in `verify_one`,
            # because the scenario not being staged is the stimulus's business
            # -- so a check that abstains on every testpoint survives every
            # gate and was refuting the claim on no evidence at all.
            #
            # WHAT `UNOBSERVABLE` ACTUALLY CLAIMS, stated precisely because
            # the loose reading makes this fix look like a bigger one than it
            # is: THIS REQUIREMENT'S TEXT names no declared output port the
            # behaviour is directly visible on. It is not a claim that no port
            # can observe the behaviour -- the effect may well reach the
            # boundary through a port some other requirement names. That is why
            # it routes to spec authoring (say what is observable) rather than
            # to triage, and why a working oracle is allowed to refute it.
            #
            # Measured on z-i2c: 19 of the 33 NOT_EXERCISED at turn 0 were
            # requirements normalization had called unobservable. They reached
            # the debug agent routed to "fix the stimulus" -- and a requirement
            # whose own text names no observable gives the stimulus author
            # nothing to aim at either, so 19 of 56 blocking findings were
            # addressed to someone with no way to act on them.
            out[uid] = TRUSTED
            if blind:
                why[uid] = ("normalization called this UNOBSERVABLE and its "
                            "oracle decides it at a declared port, so the "
                            "normalization is wrong")
        elif blind:
            # UNOBSERVABLE stays the verdict -- a requirement with no boundary
            # observable routes to spec authoring whatever else is wrong with
            # it, and that is the more fundamental of the two claims.
            #
            # But an oracle WAS attempted for it (generation filters on
            # testpoint attachment, not on observability), and until now its
            # rejection reason was thrown away here. That cost real time: seven
            # requirements on s-i2c reported nothing but normalization's prose,
            # so establishing why their oracles had failed meant going back to
            # `agent_io` -- where all seven turned out to have had between two
            # and five rounds spent on them. Both reasons are true and the
            # second is the one that says whether the first is repairable.
            out[uid] = "UNOBSERVABLE"
            claim = shape.get("unobservable_reason") or "no declared output"
            tried = rejected.get(uid, "")
            why[uid] = (
                f"{claim} -- and its oracle was rejected: {tried}"
                if tried else claim)
        elif uid in rejected:
            out[uid] = V.of_discard(rejected[uid])
            why[uid] = rejected[uid]
        elif uid in had_source:
            out[uid] = "UNDECIDED"
            why[uid] = "an oracle was written but nothing decided it"
        else:
            out[uid] = "UNDECIDED"
            why[uid] = ("no oracle was produced -- no testpoint covers this "
                        "requirement, or generation returned nothing")
    return out, why


def _summary(dispositions: dict[str, str]) -> str:
    counts = Counter(dispositions.values())
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))


def _inadequate_issue(uid: str, why: str) -> Issue:
    """Ask for the discrimination the check failed, not for a defect to chase.

    `why` is `adequacy.Finding.counterexample` -- two traces the check accepted
    and the edges where they differ, in ports and edges. It used to be
    `Finding.detail`, which names the MUTATION: "survived line 21: True becomes
    False". That is a line number in the reference model, and
    `oracle_gen.build_prompt` "has no parameter that could carry a design", so
    the author was being asked to aim at a file invariant I1 forbids it from
    seeing.

    Measured over the two runs that spent this edge -- t-i2c 51 calls, w-i2c 21
    -- it never once moved an oracle from inadequate to adequate, and the
    failure was not the over-strictness the plan predicted. Every rejection
    reads `vacuous: passed all N variant(s) of its own requirement`: asked to
    tighten against something it could not locate, the author wrote a WEAKER
    check.

    WHICH TRACE IS CORRECT IS DELIBERATELY NOT STATED, and `_difference` carries
    the reasoning: naming it hands the author the reference model's behaviour to
    write against, and the reference model is what this oracle exists to judge.
    """
    return Issue(
        "error", f"oracle.{uid}.inadequate",
        f"Your check {why}\n"
        f"  Decide from the requirement which of the two is wrong, and tighten "
        f"the check so it FAILS that one -- and only to what the clause states: "
        f"a check no correct design satisfies is rejected outright. Do not "
        f"assume either trace is the correct one.")


def load(run_dir: Path) -> OracleSet | None:
    """The frozen set from a previous run, or None.

    Reuse skips the MODEL CALLS, never the meaning: everything here was already
    verified against a witness and variants that do not move, so re-verifying
    would ask the same questions of the same artifacts and get the same answers.
    That is different from `_reuse` elsewhere, which re-gates because its gates
    can have been tightened since -- these gates cannot have been, because the
    inputs they ran against are frozen beside the output.
    """
    path = Path(run_dir) / "specflow" / ARTIFACT
    oracles = freeze.load(path)
    if not oracles:
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # A set frozen before this measurement existed restores an empty map, and
    # every consumer treats missing as "not measured" rather than "all live" --
    # the distinction `rates()` keeps a `None` for.
    live = (blob.get("oracle_liveness") or {}).get("verdicts") or {}
    return OracleSet(
        trusted=oracles,
        dispositions=dict(blob.get("dispositions") or {}),
        reasons=dict(blob.get("reasons") or {}),
        variants=variants_mod.load(Path(run_dir) / "specflow" / "variants.json"),
        witness_kind=str(blob.get("witness") or NO_BOUND),
        rounds=int(blob.get("rounds") or 0),
        liveness={str(u): str(v) for u, v in live.items()},
        control_notes={str(u): str(n.get("control") or "")
                       for u, n in (blob.get("instrument_notes") or {}).items()
                       if isinstance(n, dict) and n.get("control")},
        witness_notes={str(u): str(n.get("witness") or "")
                       for u, n in (blob.get("instrument_notes") or {}).items()
                       if isinstance(n, dict) and n.get("witness")},
        # **THE LOSSY-LOAD TRAP, CLOSED FOR THE FIELDS THAT MATTER TO
        # SELECTION.** This function already dropped `repairs`, `abandoned` and
        # `tools`, so a reused set answered "what did the gate catch?" and "what
        # left the system?" with silence. A `corpus` added without being read
        # back here would vanish on every `--reuse` -- and the corpus is the
        # ONE field whose whole purpose is to survive the run that built it.
        #: Same trap, same close. Rebuilt field by field rather than passed
        #: through, so a blob written by a different version cannot put an
        #: arbitrary shape into the set.
        correspondence_rounds=[
            {"round": int(r.get("round") or 0),
             "reviewed": int(r.get("reviewed") or 0),
             "off_target": [str(u) for u in (r.get("off_target") or [])],
             "not_assertable": [str(u) for u in (r.get("not_assertable") or [])]}
            for r in (blob.get("correspondence_rounds") or [])
            if isinstance(r, dict)
        ],
        corpus={
            str(uid): [
                CorpusBody(req_uid=str(uid), source=str(m.get("source") or ""),
                           arm=str(m.get("arm") or ""),
                           round_=int(m.get("round") or 0),
                           answered=str(m.get("answered") or ""),
                           frozen=bool(m.get("frozen")))
                for m in (members or []) if isinstance(m, dict)
            ]
            for uid, members in (blob.get("corpus") or {}).items()
        },
        repairs={str(u): [str(x) for x in (v or [])]
                 for u, v in (blob.get("repairs") or {}).items()},
        abandoned={str(u): str(v)
                   for u, v in (blob.get("abandoned") or {}).items()},
        tools=dict(blob.get("tools") or {}),
        #: **AND `testpoints_no_oracle_names` WAS ALSO BEING DROPPED.** It is
        #: the input to `decides_nothing()`, whose own docstring says "an empty
        #: list and an unmeasured one read the same in a report and mean
        #: opposite things" -- and on every `--reuse` this constructor made it
        #: empty, so the method returned 0 and said exactly the thing it was
        #: written to prevent.
        testpoints_no_oracle_names=[
            str(t) for t in (blob.get("testpoints_no_oracle_names") or [])],
        unreached_silenced={
            str(u): str(g)
            for u, g in (blob.get("unreached_silenced") or {}).items()},
        #: THE LOSSY-LOAD TRAP. A field written at freeze and not read here is
        #: absent from every `--reuse`, so a reused run would report a set that
        #: had been selected as one that never was.
        selection_dropped={
            str(u): str(g)
            for u, g in (blob.get("selection_dropped") or {}).items()},
        selection_ran=bool(blob.get("selection_ran")),
        labels={str(u): str(g)
                for u, g in (blob.get("faithfulness_labels") or {}).items()},
        narrowing={
            str(u): [{"round": int(e.get("round") or 0),
                      "was": int(e.get("was") or 0), "now": int(e.get("now") or 0)}
                     for e in (v or []) if isinstance(e, dict)]
            for u, v in (blob.get("repair_narrowing") or {}).items()},
    )
