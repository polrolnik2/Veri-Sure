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

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .model_io import ModelPort
from .refmodel import freeze, trust
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
    variants: list = field(default_factory=list)
    witness_kind: str = NO_BOUND
    rounds: int = 0

    def rates(self) -> dict[str, int]:
        counts = Counter(self.dispositions.values())
        return {"trusted": len(self.trusted),
                **{k: counts[k] for k in sorted(counts) if k != TRUSTED}}

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
) -> tuple[str, bool]:
    """`(why, quotable)` -- why this oracle is unusable, and whether an author
    may be told the details.

    `quotable` is False for anything the CONTROL decided. The rejection stands
    and is recorded, but its reason never reaches a prompt: see the note on
    `CONTROL` above. A witness-derived rejection is quotable and drives repair.

    Cheapest first, and every check here is independent of the design under
    repair -- which is what makes one pass enough.
    """
    why = well_formed(oracle, contract, testplan)
    if why:
        return f"malformed: {why}", True

    if witness:
        held = trust._decide_over(  # noqa: SLF001
            oracle, witness, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        if held.broken and not held.model_broke:
            return f"malformed: {held.broken}", True
        # A witness that raises says nothing about the oracle. Quiet, not guilty.
        if held.failed():
            where = f" at edge {held.edge}" if held.edge is not None else ""
            return (f"over-strict: an independent implementation of this same "
                    f"requirement fails it{where} -- "
                    f"{held.detail or '(no detail)'}"), True
        # `held.unexercised()` is deliberately NOT a rejection -- see the module
        # docstring. The scenario not being staged is the stimulus's business.

    if variants:
        level, detail = variants_mod.must_fail(
            oracle, variants, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        if level == trust.CONVICTED:
            return f"vacuous: {detail}", True

    if control:
        # Last, because it is the only check whose finding cannot be acted on.
        # Running it earlier would spend the strongest instrument producing the
        # least usable answer.
        known = trust._decide_over(  # noqa: SLF001
            oracle, control, contract, stimulus_by_tp, base=base,
            transactional=transactional)
        if known.failed():
            return ("over-strict: a known-good design fails it; the detail is "
                    "withheld from the author on purpose so the oracle cannot "
                    "be tuned against a held-out grade"), False
    return "", True


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

    rejected: dict[str, str] = {}
    rounds = 0
    for rounds in range(1, max_rounds + 1):
        rejected = {}
        quotable: dict[str, str] = {}
        for uid, oracle in held.items():
            why, may_quote = verify_one(
                oracle, contract=contract, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, witness=witness,
                control=control, variants=variants, base=base,
                transactional=transactional)
            if why:
                rejected[uid] = why
                if may_quote:
                    quotable[uid] = why
        if not quotable or rounds == max_rounds:
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
            only=set(quotable),
            feedback={uid: [_repair_issue(uid, why)]
                      for uid, why in quotable.items()},
        )
        # Only a replacement that actually arrived replaces anything. A round
        # that produced nothing leaves the previous oracle standing to be
        # rejected again, which is the honest outcome rather than a hole.
        for o in again:
            held[o.req_uid] = o

    trusted = [o for uid, o in held.items() if uid not in rejected]
    dispositions, reasons = _dispositions(
        requirements=requirements, trusted=trusted, rejected=rejected,
        had_source=set(held), normalized=normalized)

    if run_dir is not None:
        trusted, drift = freeze.freeze(
            trusted, Path(run_dir) / "specflow" / ARTIFACT, normalized,
            extra={"dispositions": dispositions, "reasons": reasons,
                   "witness": witness_kind, "rounds": rounds,
                   "variants": len(variants)})
        for uid, what in sorted(drift.items()):
            logger.warning("oracle drift %s: %s", uid, what)
        if variants:
            variants_mod.save(variants,
                              Path(run_dir) / "specflow" / "variants.json")
    else:
        trusted = freeze.stamp(trusted, normalized)

    logger.info("oracles: %s (bound: %s)", _summary(dispositions), witness_kind)
    return OracleSet(trusted=trusted, dispositions=dispositions,
                     reasons=reasons, variants=variants,
                     witness_kind=witness_kind, rounds=rounds)


def _witness(
    *, requirements: list[dict], contract_json: str, port: ModelPort,
    workdir: Path, run_dir: Path | None,
) -> tuple[str, str]:
    """The design the repair loop is allowed to quote, and whether there is one.

    Generated even where a control exists, because the two do different jobs: a
    control REJECTS and a witness REPAIRS, and collapsing them would let the
    control's behaviour reach an oracle author.
    """
    from .refmodel.conform import conforming_implementation

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
    return source, WITNESS


def _dispositions(
    *, requirements: list[dict], trusted: list[RequirementOracle],
    rejected: dict[str, str], had_source: set[str],
    normalized: dict[str, dict] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """One verdict per requirement, and never fewer.

    `UNOBSERVABLE` is settled at normalization and passes straight through --
    a requirement with no boundary observable is a hole in the specification,
    not a defect in a check that was never written for it.
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
        if shape and not (shape.get("observable") or []):
            out[uid] = "UNOBSERVABLE"
            why[uid] = shape.get("unobservable_reason") or "no declared output"
        elif uid in ok:
            out[uid] = TRUSTED
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
        why, _quotable = verify_one(
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
                     witness_kind=witness_kind, rounds=previous.rounds + 1)
