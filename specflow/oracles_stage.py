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

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .model_io import ModelPort
from .refmodel import correspondence, freeze
from .refmodel import liveness as _L
from .refmodel import trust
from .refmodel import variants as variants_mod
from .refmodel import verdict as V
from .refmodel.oracle_gen import run_oracle_gen
from .refmodel.oracles import RequirementOracle, well_formed
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


@dataclass(frozen=True)
class OracleSet:
    """What the stage decided, for every requirement it was given."""

    trusted: list[RequirementOracle] = field(default_factory=list)
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
            **{k: counts[k] for k in sorted(counts) if k != TRUSTED},
        }
        if not self.variants:
            out["VACUOUS"] = None
        if self.witness_kind == NO_BOUND:
            out["ORACLE_INVALID"] = out.get("ORACLE_INVALID")
        return out

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
        off = correspondence.rejects(review)
        if off:
            return off, True, notes

    if variants and replayable:
        level, detail = variants_mod.must_fail(
            oracle, variants, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        if level == trust.CONVICTED:
            return f"vacuous: {detail}", True, notes
    return "", True, notes


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


def _is_live(oracle, witness: str, contract: dict, stimulus_by_tp: dict,
             *, base: str) -> bool:
    """Whether ONE replacement can fail. Unknown counts as live.

    An oracle this cannot decide about must not be discarded on that account --
    the same asymmetry `verify_one` uses, where an instrument that could not
    answer never convicts.
    """
    record = _liveness({oracle.req_uid: oracle}, witness, contract,
                       stimulus_by_tp, base=base).get(oracle.req_uid)
    return not record or record.get("verdict") != _L.DEAD_ORACLE


def _dead_advisory(req_uid: str, detail: str) -> Issue:
    """The check cannot fail. Unlike gate 1, this is not one reader's opinion.

    Gate 1's note is a disagreement between two same-author readings, so
    declining it is a real answer. This is a fact about the check itself,
    established mechanically: every declared output it names was set to every
    other legal value, near and far, everywhere and at single points, and the
    verdict never moved. There is no design that this check distinguishes from
    any other.

    It is still an ADVISORY and not a rejection, and the reason is the rate
    rather than the reasoning. Its false-positive rate is known on one design.
    This stage has twice turned a number into a refusal before knowing what it
    rejected -- gate 1's blanket "met" discarded 30 requirements, and the
    correspondence gate rejected 56 of 70 on a miscalibration -- and both times
    the damage was invisible until a later gate could not see past it. So: one
    attempt, and the previous check stands if the attempt is not better.

    What the author is NOT told is which design was used. The counterexample is
    the perturbation, which is derived from the trace's own declared widths, not
    from any implementation's behaviour.
    """
    return Issue(
        "warning", f"oracle.{req_uid}.cannot_fail",
        f"This check cannot fail. {detail}. Every declared output it names was "
        f"driven to every other legal value -- one step away and at both ends "
        f"of the range, across the whole trace and at single edges -- and the "
        f"verdict did not change once.\n\n"
        f"That usually means one of three things. The check reads a port to "
        f"find its activation window but never ASSERTS on any port. Its "
        f"comparison is true for every value the port can carry, so it restates "
        f"the port's width rather than the requirement. Or its trigger cannot "
        f"fire, so the body it guards never runs.\n\n"
        f"Rewrite it so there is some legal output value it rejects, and name "
        f"that value in `reasoning`. If the requirement genuinely constrains "
        f"nothing observable at the boundary, say THAT instead and keep the "
        f"check as it is -- a requirement with no observable is a finding about "
        f"the specification, not something to invent an assertion for.")


def _repair_issue(req_uid: str, why: str) -> Issue:
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
    workdir: Path,
    base: str = "step",
    normalized: dict[str, dict] | None = None,
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
    run_dir: Path | None = None,
    max_repairs: int = 2,
    #: Verify-repair-verify rounds over the whole set, on top of the per-oracle
    #: repairs `run_stage` already does inside generation.
    max_rounds: int = 2,
    transactional: bool = True,
    fanout: bool = True,
    #: `{req_uid: why}` for oracles a LATER stage found inadequate -- a mutation
    #: of the shipped model they could not catch. Only these are regenerated,
    #: and `previous` supplies everything else unchanged. This is the feedback
    #: edge: without it an oracle that proves nothing stays in the set forever,
    #: because the only thing that could have told us was downstream of it.
    strengthen: dict[str, str] | None = None,
    previous: OracleSet | None = None,
    #: Something upstream regenerated, so the frozen artifacts are about
    #: requirements that no longer exist. Written once means once PER REQUIREMENT
    #: SET, not once per directory -- without this the stage would spend its
    #: fan-out generating oracles and then silently keep the stale file, and the
    #: loop would measure the new model against the old requirements' checks.
    rewrite: bool = False,
) -> OracleSet:
    """Generate, verify, repair, freeze. Returns a disposition for every requirement."""
    if strengthen and previous is not None:
        return _strengthen(
            strengthen, previous, requirements=requirements,
            contract_json=contract_json, contract=contract, testplan=testplan,
            stimulus_by_tp=stimulus_by_tp, port=port, workdir=workdir,
            base=base, normalized=normalized, control_source=control_source,
            witness_port=witness_port, run_dir=run_dir,
            max_repairs=max_repairs, transactional=transactional,
            fanout=fanout)

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

    variants: list = []
    if want_variants and witness:
        from .obligation import by_requirement

        variants, _ = variants_mod.run_variant_gen(
            requirements=requirements, contract_json=contract_json,
            contract=contract, conforming_source=witness,
            stimulus_by_tp=stimulus_by_tp,
            tp_by_req=by_requirement(testplan), port=port,
            normalized=normalized, base=base, fanout=fanout,
        )
        logger.info("oracles: %d variant(s) for %d requirement(s)",
                    len(variants), len({v.req_uid for v in variants}))

    oracles, _results = run_oracle_gen(
        requirements=requirements, contract_json=contract_json,
        contract=contract, testplan=testplan, port=port,
        normalized=normalized, conforming_source=witness,
        stimulus_by_tp=stimulus_by_tp, base=base,
        max_repairs=max_repairs, fanout=fanout,
    )
    held: dict[str, RequirementOracle] = {o.req_uid: o for o in oracles}
    by_uid = {str(r.get("uid") or ""): r for r in requirements}

    rejected: dict[str, str] = {}
    repairs: dict[str, list[str]] = {}
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
    for rounds in range(1, max_rounds + 1):
        rejected = {}
        disagreements = {}
        quotable: dict[str, str] = {}
        reviews = (
            correspondence.review(
                list(held.values()), by_uid, port=port, normalized=normalized,
                round_=rounds - 1, fanout=fanout)
            if want_correspondence else {})
        for uid, oracle in held.items():
            why, may_quote, notes = verify_one(
                oracle, contract=contract, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, witness=witness,
                control=control, variants=variants, base=base,
                transactional=transactional, review=reviews.get(uid))
            if notes:
                disagreements[uid] = notes
            if why:
                rejected[uid] = why
                if may_quote:
                    quotable[uid] = why
        for uid, why in quotable.items():
            repairs.setdefault(uid, []).append(why)
        # Can each surviving check fail at all? Recomputed per round because a
        # repaired oracle is a different check, and kept for the artifact so the
        # stage reports what it last saw rather than a stale first look.
        alive = _liveness(held, witness, contract, stimulus_by_tp, base=base)
        dead_now = {
            uid: record.get("detail", "")
            for uid, record in alive.items()
            if record.get("verdict") == _L.DEAD_ORACLE
        }
        # Gate 1 and the liveness note each earn an attempt -- "try to make it
        # pass" -- but only one each, and only where nothing else is already
        # re-asking. Both are advisory: see `_advisory` and `_dead_advisory`.
        advisory_only = {
            uid for uid, note in disagreements.items()
            if "witness" in note and uid not in quotable and uid not in advised
        } | {
            uid for uid in dead_now if uid not in quotable and uid not in advised
        }
        ask = set(quotable) | advisory_only
        if not ask or rounds == max_rounds:
            # Nothing left that an author could be told about. A control-only
            # rejection is terminal by design, so re-asking would spend a call
            # on a prompt carrying no information.
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
                uid: ([_advisory(uid, disagreements[uid]["witness"])]
                      if "witness" in disagreements.get(uid, {}) else [])
                     + ([_dead_advisory(uid, dead_now[uid])]
                        if uid in dead_now else [])
                     + ([_repair_issue(uid, quotable[uid])]
                        if uid in quotable else [])
                for uid in ask
            },
            label=f"_fix{rounds}",
        )
        advised |= advisory_only
        # Only a replacement that actually arrived replaces anything. A round
        # that produced nothing leaves the previous oracle standing to be
        # rejected again, which is the honest outcome rather than a hole.
        for o in again:
            if o.req_uid in advisory_only:
                # This oracle was not rejected -- it was asked to TRY. A reply
                # that comes back worse must not be promoted over the one that
                # was already fine, or advice becomes a way to lose a good
                # check. Same rule `_strengthen` applies for the same reason.
                worse, _q, _n = verify_one(
                    o, contract=contract, testplan=testplan,
                    stimulus_by_tp=stimulus_by_tp, witness=witness,
                    control=control, variants=variants, base=base,
                    transactional=transactional)
                if worse:
                    logger.info("oracles: %s declined the advisory and its "
                                "attempt was worse (%s); the previous check "
                                "stands", o.req_uid, worse.split(":")[0])
                    continue
                if o.req_uid in dead_now and not _is_live(
                        o, witness, contract, stimulus_by_tp, base=base):
                    # A replacement that still cannot fail is not an
                    # improvement, and swapping one inert check for another
                    # loses the reasoning already recorded against this uid.
                    logger.info("oracles: %s was re-asked because it cannot "
                                "fail and the replacement cannot either; the "
                                "previous check stands", o.req_uid)
                    continue
            held[o.req_uid] = o

    trusted = [o for uid, o in held.items() if uid not in rejected]
    dispositions, reasons = _dispositions(
        requirements=requirements, trusted=trusted, rejected=rejected,
        had_source=set(held), normalized=normalized)
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

    if run_dir is not None:
        trusted, drift = freeze.freeze(
            trusted, Path(run_dir) / "specflow" / ARTIFACT, normalized,
            extra={"dispositions": dispositions, "reasons": reasons,
                   "witness": witness_kind, "rounds": rounds,
                   "variants": len(variants),
                   # Legibility, not decoration: a reader has to be able to
                   # tell a check that found nothing from one that never ran.
                   "vacuity_checked": bool(variants),
                   "correspondence_checked": want_correspondence,
                   "over_strictness_bounded_by": witness_kind,
                   "repairs": repairs,
                   # What the designs said without being allowed to decide.
                   "instrument_notes": disagreements,
                   "unsatisfiable_by_the_control": sorted(
                       u for u, d in disagreements.items() if "control" in d),
                   "testpoints_no_oracle_names": idle,
                   "stimulus_liveness": live,
                   "oracle_liveness": dead})
        for uid, what in sorted(drift.items()):
            logger.warning("oracle drift %s: %s", uid, what)
        if variants:
            variants_mod.save(variants,
                              Path(run_dir) / "specflow" / "variants.json")
    else:
        trusted = freeze.stamp(trusted, normalized)

    logger.info("oracles: %s (bound: %s)", _summary(dispositions), witness_kind)
    return OracleSet(trusted=trusted, dispositions=dispositions,
                     reasons=reasons, repairs=repairs, variants=variants,
                     witness_kind=witness_kind, rounds=rounds,
                     testpoints_no_oracle_names=idle,
                     liveness={u: r.get("verdict", _L.UNKNOWN)
                               for u, r in report.items()})


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
        if held.strip():
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


def _dispositions(
    *, requirements: list[dict], trusted: list[RequirementOracle],
    rejected: dict[str, str], had_source: set[str],
    normalized: dict[str, dict] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """One verdict per requirement, and never fewer.

    `UNOBSERVABLE` is settled at normalization, EXCEPT that a working oracle
    refutes it -- see below.
    """
    norm = normalized or {}
    ok = {o.req_uid for o in trusted}
    out: dict[str, str] = {}
    why: dict[str, str] = {}
    for req in requirements:
        uid = str(req.get("uid") or "")
        if not uid:
            continue
        shape = norm.get(uid) or {}
        blind = bool(shape) and not (shape.get("observable") or [])
        if uid in ok:
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
            out[uid] = TRUSTED
            if blind:
                why[uid] = ("normalization called this UNOBSERVABLE and its "
                            "oracle decides it at a declared port, so the "
                            "normalization is wrong")
        elif blind:
            out[uid] = "UNOBSERVABLE"
            why[uid] = shape.get("unobservable_reason") or "no declared output"
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


def _strengthen(
    inadequate: dict[str, str],
    previous: OracleSet,
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    port: ModelPort,
    workdir: Path,
    base: str,
    normalized: dict[str, dict] | None,
    control_source: str | None,
    witness_port: ModelPort | None,
    run_dir: Path | None,
    max_repairs: int,
    transactional: bool,
    fanout: bool,
) -> OracleSet:
    """Re-ask only the oracles a mutant got past, and verify the replacements.

    A replacement is kept only if it VERIFIES. An oracle strengthened to catch a
    mutant very easily becomes over-strict -- that is the oscillation the plan
    names -- and the honest handling is that the round simply fails to improve
    it, not that a check no correct design satisfies gets promoted because it
    was eager.
    """
    witness, witness_kind = _witness(
        requirements=requirements, contract_json=contract_json,
        port=witness_port or port, workdir=workdir, run_dir=run_dir)
    control = control_source or ""
    if control:
        witness_kind = (f"{WITNESS}+{CONTROL}" if witness else CONTROL)

    again, _ = run_oracle_gen(
        requirements=requirements, contract_json=contract_json,
        contract=contract, testplan=testplan, port=port,
        normalized=normalized, conforming_source=witness,
        stimulus_by_tp=stimulus_by_tp, base=base,
        max_repairs=max_repairs, fanout=fanout,
        only=set(inadequate),
        label=f"_strengthen{previous.rounds}",
        feedback={uid: [Issue(
            "error", f"oracle.{uid}.inadequate",
            f"A design that VIOLATES this requirement passes your check: it "
            f"{why}. The check is therefore satisfied by something provably "
            f"wrong, so a design agreeing with it proves nothing. Tighten it to "
            f"the behaviour the clause actually states -- and only to that: a "
            f"check no correct design satisfies is rejected outright.")]
            for uid, why in inadequate.items()},
    )

    kept = {o.req_uid: o for o in previous.trusted}
    dispositions = dict(previous.dispositions)
    reasons = dict(previous.reasons)
    for oracle in again:
        why, _quotable, _notes = verify_one(
            oracle, contract=contract, testplan=testplan,
            stimulus_by_tp=stimulus_by_tp, witness=witness, control=control,
            variants=previous.variants, base=base, transactional=transactional)
        if why:
            # The replacement is worse than what it replaced. Keep the old one
            # and record that the round did not help: reporting an oscillation
            # is worth more than promoting whichever attempt happened to be last.
            reasons[oracle.req_uid] = (
                f"strengthening rejected -- {why}; the previous oracle stands")
            continue
        kept[oracle.req_uid] = oracle
        dispositions[oracle.req_uid] = TRUSTED
        reasons[oracle.req_uid] = "strengthened after a mutant got past it"

    trusted = list(kept.values())
    if run_dir is not None:
        trusted, _drift = freeze.freeze(
            trusted, Path(run_dir) / "specflow" / ARTIFACT, normalized,
            extra={"dispositions": dispositions, "reasons": reasons,
                   "witness": witness_kind, "rounds": previous.rounds + 1,
                   "variants": len(previous.variants)},
            rewrite=True)
    else:
        trusted = freeze.stamp(trusted, normalized)

    logger.info("oracles: strengthened %d of %d inadequate",
                sum(1 for u in inadequate if dispositions.get(u) == TRUSTED
                    and reasons.get(u, "").startswith("strengthened")),
                len(inadequate))
    return OracleSet(trusted=trusted, dispositions=dispositions,
                     reasons=reasons, variants=list(previous.variants),
                     witness_kind=witness_kind, rounds=previous.rounds + 1,
                     testpoints_no_oracle_names=_decides_nothing(
                         testplan, trusted))


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
    )
