"""Assemble `ref_model.py`, and run the bounded gate loop around the agent.

Base selection (R0) is a script decision from contract fields, not a prompt: the
agent's own `base` answer is cross-checked against it rather than trusted.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from collections.abc import Callable
from typing import Protocol

import logging

from ..model_io import ModelPort
from ..ports import classify
from ..schema import Issue, has_errors
from ..stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_stage,
)
from . import freeze, ratchet, verdict
from .agent import SYSTEM, RefModelOutput, parse_response
from .oracles import decide_all
from .session import MODEL, DebugSession
from .validate import validate

logger = logging.getLogger(__name__)

STAGE = "refmodel"

_COMPLETION_WORDS = {"valid", "ready", "ack", "done", "busy", "complete"}


def choose_base(contract: dict) -> str:
    """R0. `step` for sequential designs, `evaluate` otherwise.

    Mirrors `contract_linter._has_completion_signal` (`:55-71`): a multi-cycle
    output or a handshake port means the model needs state, because a single
    input vector no longer determines the output on its own.
    """
    clocking = contract.get("clocking") or {}
    if not clocking.get("is_sequential"):
        return "evaluate"

    timing = contract.get("timing") or {}
    for spec in timing.values():
        if isinstance(spec, dict) and int(spec.get("latency_cycles") or 0) > 1:
            return "step"

    for port in contract.get("io") or []:
        name = str(port.get("name") or "").lower()
        if any(w in name.split("_") or w == name for w in _COMPLETION_WORDS):
            return "step"

    # Sequential but single-cycle and handshake-free: a registered output is
    # still a pure function of the previous input, so `evaluate` plus a latency
    # of 1 models it without state.
    return "evaluate"


def output_ports(contract: dict) -> list[str]:
    return [
        str(p.get("name"))
        for p in (contract.get("io") or [])
        if p.get("name") and p.get("dir") == "output"
    ]


def latency_cycles(contract: dict) -> int:
    timing = contract.get("timing") or {}
    best = 0
    for spec in timing.values():
        if isinstance(spec, dict):
            best = max(best, int(spec.get("latency_cycles") or 0))
    return best


def render(out: RefModelOutput, contract: dict) -> str:
    """Emit `ref_model.py`. The generator supplies the whole class body.

    The harness used to synthesise the dispatch by calling one method per
    requirement in declaration order. That was reasonable while the model was
    required to be one-method-per-requirement, and it was the wrong shape: it
    meant the generator could not express execution order at all, and execution
    order is where reset priority lives -- `nReset` dominating `rst` dominating
    normal operation is a statement about sequence, not about which sentence of
    the spec came first.

    So the generator now writes `evaluate`/`step` itself, and this only wraps its
    body in the class the contract determines. The one thing still script-owned
    is `OUTPUT_PORTS` and `LATENCY_CYCLES`, which come from the contract and are
    not the generator's to choose.
    """
    body = textwrap.indent(textwrap.dedent(out.source).strip(), "    ")
    return (
        '"""Generated reference model. Do not edit.\n\n'
        "Derived from the specification via specflow S1 + refmodel. Frozen once\n"
        "gate G4 passes: after the RTL exists, a wrong-RTL hypothesis and a\n"
        "wrong-model hypothesis compete for every failing check, and the model is\n"
        "the cheaper one to 'fix' -- which is how a reference model gets\n"
        "retrofitted to match broken RTL.\n"
        '"""\n\n'
        "from specflow.refmodel.base import RefModel\n\n\n"
        "class Model(RefModel):\n"
        f"    OUTPUT_PORTS = {output_ports(contract)!r}\n"
        f"    LATENCY_CYCLES = {latency_cycles(contract)}\n\n"
        + body
        + "\n"
    )


class RefModelDebugger(Protocol):
    """An agent that edits a reference model until its oracles pass.

    Injected rather than imported, exactly as `specflow/loop.py` injects
    `RtlRepair`: the implementation lives in `eda_agent` and needs AgentScope,
    and `specflow/` deliberately imports none of that. Absent one, the stage
    behaves as it always has.

    Returns `(best_source, attempts, note)` -- BEST, not last, so a turn that
    wandered downhill hands back where it was highest.
    """

    def debug(self, session: DebugSession) -> tuple[str, int, str]: ...


def generate_model(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    base: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 3,
    #: The name this generation is RECORDED under. Two callers produce a model
    #: from the same prompt -- the reference model and the held-out witness --
    #: and `model_io` keys every prompt/response pair by `{stage}_r{round}`. One
    #: name for both would have the witness overwrite the model's record, and a
    #: cache or replay would then serve one where the other was asked for.
    stage: str = STAGE,
    #: An extra gate, run only on a model that already passes the mechanical
    #: checks, receiving `(output, source, round_)`. The per-requirement judge
    #: is the only caller that supplies one; a witness supplies none.
    extra_gate: Callable[[RefModelOutput, str, int], list[Issue]] | None = None,
) -> tuple[StageResult[RefModelOutput], str]:
    """Produce ONE implementation of these requirements. Returns it and its source.

    Extracted so the two callers that need an implementation -- the reference
    model, and the held-out witness that bounds the oracles from above -- share
    one generator rather than one of them re-entering the other.
    `conform.conforming_implementation` used to call `run_refmodel`, from inside
    `_debug_turns`, which is inside `run_refmodel`: a stage re-entering itself
    from within its own repair loop. Nothing about that was deliberate, and it
    is what made the witness impossible to lift into a stage of its own.

    Knows nothing about oracles, judges or debugging. Its whole contract is
    "requirements in, gate-clean model out", which is what makes it safe to call
    twice for two different purposes.
    """
    rendered: dict[str, str] = {"src": ""}
    rounds = {"n": 0}

    def build_prompt(issues: list[Issue] | None, previous: str | None = None) -> str:
        parts = [
            SYSTEM,
            "<requirements>\n"
            + json.dumps(requirements, indent=2, ensure_ascii=False)
            + "\n</requirements>",
            "<contract_json>\n" + contract_json.rstrip() + "\n</contract_json>",
            f"The dispatch method for this design is `{base}` "
            f"(chosen from the contract, not negotiable). "
            f"Output ports that must all be written: {output_ports(contract)}.",
        ]
        if issues:
            # The artifact first: the defect list refers to it, so a reader
            # (or a model) meets what is being repaired before what is wrong
            # with it. S1-S3 order it the same way.
            if previous:
                parts.append(previous_answer_block(previous))
            parts.append(gate_failures_block(issues))
        return "\n\n".join(parts)

    def gate(out: RefModelOutput) -> list[Issue]:
        rendered["src"] = render(out, contract)
        issues = validate(
            out=out,
            source=rendered["src"],
            requirements=requirements,
            contract=contract,
            expected_base=base,
            workdir=workdir,
        )
        if extra_gate is not None and not has_errors(issues):
            issues = issues + extra_gate(out, rendered["src"], rounds["n"])
        rounds["n"] += 1
        return issues

    result = run_stage(
        stage=stage,
        port=port,
        build_prompt=build_prompt,
        parse=parse_response,
        gate=gate,
        max_repairs=max_repairs,
    )
    return result, rendered["src"]


def run_refmodel(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 3,
    item_port: ModelPort | None = None,
    run_dir: Path | None = None,
    testplan: list[dict] | None = None,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    debugger: RefModelDebugger | None = None,
    max_judge_turns: int = 3,
    control_source: str | None = None,
    normalized: dict[str, dict] | None = None,
    #: The verified, frozen oracle set, produced by `oracles_stage` BEFORE this
    #: stage ran. When supplied nothing here generates oracles -- which is the
    #: whole point: an oracle written after the model exists is written by
    #: something that could have read it.
    oracle_set=None,
    #: Strengthening rounds after the debug loop converges. See `_closed_loop`.
    adequacy_rounds: int = 0,
    reconsider_rounds: int = 0,
) -> tuple[StageResult[RefModelOutput], str]:
    """R2-R6. Returns the stage result and the rendered source.

    `item_port`, when supplied, adds the per-requirement judge to the gate: one
    small call per requirement over the composed model, whose blocking verdicts
    join the script issues and drive the same bounded repair round. It is a
    separate port because the judge runs a small model while the generator runs
    the configured one -- and because a run without it is still a valid run, just
    one gated on structure alone.
    """
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except Exception:  # noqa: BLE001
        contract = {}

    base = choose_base(contract)
    # Generation is gated on the MECHANICAL checks alone and repaired by
    # REGENERATING, which is the right tool for a missing quote or an unwritten
    # output -- a whole round was once lost to exactly that. Behavioural
    # failures go to the debug turns below, which EDIT instead.
    result, source = generate_model(
        requirements=requirements, contract_json=contract_json,
        contract=contract, base=base, port=port, workdir=workdir,
        max_repairs=max_repairs,
    )
    rendered: dict[str, str] = {"src": source}

    if debugger is not None and result.ok and oracle_set is None:
        # Nothing to repair against. Correct -- every blocking verdict is the
        # outcome of running an oracle, so with no oracles there is no finding
        # to act on -- but it must be SAID. A model that was never checked and a
        # model that passed look identical from here, and that ambiguity is the
        # one this pipeline exists to remove.
        result = StageResult(result.output, list(result.issues) + [Issue(
            "warning", "refmodel.unchecked",
            "no oracle set was produced, so this reference model was never "
            "decided against its requirements -- it is unrepaired, not "
            "verified")], result.rounds)

    if debugger is not None and result.ok and oracle_set is not None:
        source, issues = _closed_loop(
            source=rendered["src"], contract=contract,
            contract_json=contract_json, requirements=requirements,
            covers=result.output.covers, oracles=list(oracle_set.trusted),
            base=base, testplan=testplan or [],
            stimulus_by_tp=stimulus_by_tp or {}, run_dir=run_dir,
            debugger=debugger, max_turns=max_judge_turns,
            control_source=control_source, normalized=normalized,
            item_port=item_port,
            variants=list(oracle_set.variants),
            carried={u: v for u, v in oracle_set.dispositions.items()
                     if v != "TRUSTED"},
            oracle_rates=oracle_set.rates(),
            oracle_liveness=dict(oracle_set.liveness),
            witness_notes=dict(oracle_set.witness_notes),
            oracle_set=oracle_set, adequacy_rounds=adequacy_rounds,
            reconsider_rounds=reconsider_rounds,
        )
        rendered["src"] = source
        result = StageResult(result.output, issues, result.rounds)

    return result, rendered["src"]


def _closed_loop(
    *,
    source: str,
    contract: dict,
    contract_json: str,
    requirements: list[dict],
    covers: dict[str, list[str]],
    oracles: list,
    base: str,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    run_dir: Path | None,
    debugger: RefModelDebugger,
    max_turns: int,
    control_source: str | None,
    normalized: dict[str, dict] | None,
    item_port: ModelPort,
    variants: list | None,
    carried: dict[str, str],
    oracle_rates: dict,
    #: Optional so a caller predating the measurement still works; an empty map
    #: reports "not measured" downstream rather than "none dead".
    oracle_liveness: dict[str, str] | None = None,
    witness_notes: dict[str, str] | None = None,
    oracle_set=None,
    adequacy_rounds: int = 0,
    #: Rounds of the OTHER edge, counted separately from `adequacy_rounds` --
    #: and separate because running both in one round makes them fight.
    #:
    #: Measured on t-i2c, which ran both: `strengthen` tightened 5 oracles and
    #: `reconsider` relaxed 7, and the set's over-strictness did not move --
    #: 15 checks failed a known-good control before the round and 15 after,
    #: two fixed and two newly created. That is the oscillation the plan
    #: predicted, arriving as a net zero rather than a wobble, because both
    #: directions were applied to one set at once.
    #:
    #: `strengthen` is what MANUFACTURES over-strictness: it says tighten until
    #: you catch this mutant, and a check tightened past what the requirement
    #: states is exactly a check no correct design satisfies. So the two are
    #: separable and worth separating -- relaxing alone is the move that can
    #: unblock a gate, and it cannot be tested while something else is
    #: tightening underneath it.
    reconsider_rounds: int = 0,
) -> tuple[str, list[Issue]]:
    """Debug until the oracles are satisfied, then ask whether that meant anything.

    Satisfying every oracle is only evidence if the oracles could have failed
    the design they just passed -- `qualify.py:3-22`'s argument, one level down.
    So once the loop converges, the SHIPPED model is mutated and every trusted
    oracle is asked whether it would have noticed. A survivor is a finding about
    the ORACLE, and the counterexample is in hand, so it goes back to the stage
    that owns oracle generation.

    `adequacy_rounds=0` measures and acts on nothing, which is how this ships:
    the rate has to be known before it is allowed to spend calls.
    """
    from .adequacy import assess, discrimination, inadequate, write

    # Normalised once. Both are optional so a caller predating the measurement
    # still works, and both are read below in set operations where None is not
    # an empty map but a TypeError.
    oracle_liveness = dict(oracle_liveness or {})
    witness_notes = dict(witness_notes or {})
    issues: list[Issue] = []
    feedback_rounds = max(0, int(adequacy_rounds), int(reconsider_rounds))
    for round_ in range(feedback_rounds + 1):
        source, issues = _debug_turns(
            source=source, contract=contract, contract_json=contract_json,
            requirements=requirements, covers=covers, oracles=oracles,
            base=base, testplan=testplan, stimulus_by_tp=stimulus_by_tp,
            run_dir=run_dir, debugger=debugger, max_turns=max_turns,
            control_source=control_source, normalized=normalized,
            item_port=item_port, variants=variants,
            carried=carried, oracle_rates=oracle_rates,
            oracle_liveness=oracle_liveness, witness_notes=witness_notes,
        )
        if not oracles:
            break
        report = assess(oracles, source, contract, stimulus_by_tp, base=base)
        # The one number that says whether the set is an instrument at all.
        # Measured on n-i2c: 70 oracles separated a model failing 138 of 168
        # golden testpoints from one passing all 168 by THREE requirements, and
        # neither arm produced a single VIOLATES. Every other figure about that
        # run -- 46 CONFORMS, a converged loop, 70 verified oracles -- was true
        # and meant nothing without this beside it. Reported, never a gate: the
        # control is a proxy for the held-out grade.
        apart = (discrimination(oracles, source, control_source, contract,
                                stimulus_by_tp, base=base)
                 if control_source else None)
        if apart is not None:
            logger.info(
                "oracle set discriminates %d of %d requirement(s) between this "
                "model and a known-good one%s", apart["discriminating"],
                apart["oracles"],
                f"; it FAILS the known-good design on {len(apart['control_violates'])}"
                if apart["control_violates"] else "")
        if run_dir is not None:
            write(Path(run_dir), report, round_, discrimination=apart)
        weak = inadequate(report)
        logger.info("adequacy r%d: %d of %d oracle(s) a mutant got past",
                    round_, len(weak), len(report))

        # THE OTHER FEEDBACK EDGE. `weak` is a check something provably wrong
        # got past. This is a check nothing could satisfy: the loop above just
        # spent its whole turn budget on it and a second implementation of the
        # same requirement fails it too.
        #
        # Measured on s-i2c: the loop drove VIOLATES 15 -> 9 and 7 of the 9 it
        # could not clear are checks the known-good control ALSO fails. Those 7
        # block G4, which is why a reference model scoring its best separation
        # of the series -- 57/168 at +24, the first positive one -- still
        # produced no RTL. The residue was the checks, not the design, and
        # nothing sent them anywhere.
        #
        # Only oracles the loop actually failed to satisfy qualify. A check the
        # witness merely disagreed with, and the model then satisfied, has
        # answered the question and is left alone.
        # `Issue.path` is "refmodel.<uid>.<verdict>" -- see `verdict.to_issue`.
        # Only VIOLATES qualifies: a NOT_EXERCISED is the stimulus's and an
        # ORACLE_INVALID already went back through the stage's own repair loop.
        still_violating = {
            i.path.split(".")[1] for i in issues
            if i.path.startswith("refmodel.") and i.path.endswith(".violates")
        }
        stuck = {uid: witness_notes[uid]
                 for uid in sorted(still_violating & set(witness_notes))}
        if not int(reconsider_rounds) or round_ >= int(reconsider_rounds):
            stuck = {}
        if not int(adequacy_rounds) or round_ >= int(adequacy_rounds):
            weak = {}
        if stuck:
            logger.info(
                "%d oracle(s) survived the turn budget and a second "
                "implementation fails them too: %s", len(stuck),
                ", ".join(sorted(stuck)))

        if (not weak and not stuck) or oracle_set is None:
            break

        from ..oracles_stage import run_oracle_stage

        oracle_set = run_oracle_stage(
            requirements=requirements, contract_json=contract_json,
            contract=contract, testplan=testplan,
            stimulus_by_tp=stimulus_by_tp, port=item_port,
            workdir=(Path(run_dir) / "specflow" if run_dir is not None
                     else Path("/tmp/specflow-oracles")),
            base=base, normalized=normalized, control_source=control_source,
            run_dir=run_dir, strengthen=weak, reconsider=stuck,
            previous=oracle_set,
        )
        oracles = list(oracle_set.trusted)
        carried = {u: v for u, v in oracle_set.dispositions.items()
                   if v != "TRUSTED"}
        oracle_rates = oracle_set.rates()
        oracle_liveness = dict(oracle_set.liveness)
        witness_notes = dict(oracle_set.witness_notes)
    return source, issues


def _debug_turns(
    *,
    source: str,
    contract: dict,
    contract_json: str,
    requirements: list[dict],
    covers: dict[str, list[str]],
    oracles: list,
    base: str,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    run_dir: Path | None,
    debugger: RefModelDebugger,
    max_turns: int,
    control_source: str | None,
    normalized: dict[str, dict] | None,
    item_port: ModelPort,
    variants: list | None = None,
    #: Testpoints the loop may append, total. Caller-supplied like every other
    #: budget here (`loop.py:14-18` argues against hard-coded ones), and one of
    #: the two things that decide whether the loop still has a move to make.
    stimulus_budget: int = 12,
    #: What the oracle stage decided about the requirements whose oracle is NOT
    #: in `oracles` -- ORACLE_INVALID, VACUOUS, UNOBSERVABLE, UNDECIDED. Carried
    #: through for reporting and never recomputed here: they were settled
    #: against a witness that does not move, before this model existed.
    carried: dict[str, str] | None = None,
    oracle_rates: dict | None = None,
    oracle_liveness: dict[str, str] | None = None,
    witness_notes: dict[str, str] | None = None,
) -> tuple[str, list[Issue]]:
    """The debug loop. There is no other one, and no judge in this one.

    Every blocking verdict here is the outcome of RUNNING something. The judge's
    verdict was an opinion that its oracle was then asked to justify, which is
    the weakest available form of evidence -- a rationalisation of a conclusion
    already reached, by something that had read the model. An oracle written
    before any verdict exists, from the requirement alone, and then executed, is
    not a justification at all. It IS the verdict.

    What that removes, measured on f-i2c: 31 of 33 blocking findings went to the
    reference-model agent when the fix lay elsewhere. Here a verdict carries the
    party it accuses, so `NOT_EXERCISED` reaches the stimulus tool and
    `ORACLE_INVALID` is not handed to the model agent at all.

    The oracle set is FROZEN across turns. It does not depend on the model, so
    re-deriving it would cost a fan-out to receive the same answer -- and it
    would let the measure drift under the thing being measured, which is the one
    property that makes "N failing oracles going to zero" mean anything.

    Decided TRANSACTIONALLY, the way `trace_compare.transactional` compares:
    over the sequence of distinct states rather than raw edges. Screening and
    the session must agree on this, or a gate passes an oracle the loop then
    fails for a reason the gate never saw.
    """
    issues: list[Issue] = []
    turns = max(1, int(max_turns))
    carried = dict(carried or {})
    oracle_rates = dict(oracle_rates or {})
    oracle_liveness = dict(oracle_liveness or {})
    witness_notes = dict(witness_notes or {})
    _, reset_names, _ = classify(contract)

    # The set this loop promised to measure against, recorded at entry so each
    # turn can PROVE it is still deciding with it. Nothing here reassigns
    # `oracles`, so a mismatch is not a drift the loop tolerates -- it is a
    # defect in the loop, and reporting "N failing went to zero" against a set
    # that moved is the exact failure freezing exists to stop.
    at_entry = {
        o.req_uid: o.hash or freeze.content_hash(
            o, (normalized or {}).get(o.req_uid))
        for o in oracles
    }
    #: What each oracle was PROVED against, recorded at entry. `add_stimulus`
    #: appends to an oracle's evidence set on purpose, so this changing is not
    #: drift -- it is I7's trigger: what the must-pass and must-fail legs ran
    #: against is no longer what the oracle is decided against.
    proofs = {o.req_uid: freeze.evidence_hash(o) for o in oracles}
    #: Cumulative across turns: a testpoint appended in turn 1 is still evidence
    #: in turn 2, because nothing is ever removed.
    added: list[str] = []
    #: Failing count the last MODEL turn started from, so the next turn can ask
    #: whether that route is still producing anything.
    last_failing: int | None = None
    stalled = False
    #: Turns that moved nothing. Not a stop condition -- see the tail of the
    #: loop -- but worth reporting, because "took three turns and moved nothing"
    #: and "took one turn" look identical in a verdict count.
    idle_turns = 0
    #: Why the loop stopped short of every oracle conforming, if it did.
    stop = ""
    #: The last turn artifact written, so the stop reason can be recorded on it.
    #: The reason is only known after that turn has been judged, and a reader
    #: needs it on the turn it describes rather than in a log line.
    last_artifact: Path | None = None

    def _restimulate(req: dict, hint: str) -> list[dict]:
        from ..testcase_agent import stimulus_for_scenario

        return stimulus_for_scenario(
            requirement=req, what_the_scenario_needs=hint,
            contract=contract, port=item_port)

    for turn in range(turns + 1):
        # `model_copy` rather than reconstructing field by field: a
        # reconstruction is a list of fields that has to be kept in step with
        # the model, and the first field added without a default would break the
        # guard at runtime, inside the loop, on the path that exists to catch
        # things breaking quietly.
        moved = freeze.drift(oracles, [
            o.model_copy(update={"hash": at_entry[o.req_uid]}) for o in oracles
        ], normalized)
        if moved:
            raise RuntimeError(
                "the frozen oracle set changed under the loop measuring "
                f"against it: {sorted(moved)}")
        # NO SCREENING HERE. The set arrived verified by the oracle stage,
        # against a witness and variants that do not move, so re-asking those
        # questions each turn could only re-ask them against a design the agent
        # is editing. Two measured failures came from exactly that: VACUOUS
        # wandered 16 -> 18 -> 16 under a frozen oracle set, and four of five
        # apparent closures were the agent editing the model toward checks a
        # known-good design also fails -- invisible until turn 2 because the
        # gates ran in an order that hid them while they were still failing.
        #
        # What a turn may conclude is three things, and `of_result` is all of
        # it: the design honoured the clause, broke it, or never met it.
        results = decide_all(oracles, source, contract, stimulus_by_tp,
                             base=base, transactional=True)
        by_uid = {r.req_uid: r for r in results}
        mechanical = {**carried,
                      **{u: verdict.of_result(r) for u, r in by_uid.items()}}
        for req in requirements:
            uid = str(req.get("uid") or "")
            if uid and uid not in mechanical:
                mechanical[uid] = "UNDECIDED"

        # I6, on the only path that can lose an activation. Appending stimulus
        # cannot -- nothing existing is edited -- but whether a scenario occurs
        # is a joint property of the stimulus and the design, so an edit that
        # stops the model entering a state un-fires an activation the stimulus
        # still drives, and the failing count DROPS.
        regressed = (ratchet.note(
            Path(run_dir) / "specflow" / "exercised.json", mechanical)
            if run_dir is not None else [])
        issues = verdict.issues(
            mechanical,
            {u: (r.detail or r.broken) for u, r in by_uid.items()},
        ) + ratchet.issues(regressed)

        if run_dir is not None:
            out = Path(run_dir) / "specflow" / "judge" / f"r{turn}"
            out.mkdir(parents=True, exist_ok=True)
            last_artifact = out / "trust.json"
            (out / "trust.json").write_text(
                json.dumps({
                    "driver": "requirement-oracles",
                    "rates": oracle_rates,
                    # WHAT A CONFORMS IS WORTH. "46 CONFORMS" was reported as
                    # the loop converging on a model that fails 138 of 168
                    # testpoints against golden RTL; 11 of those 46 came from
                    # checks no legal value of any port they read could move.
                    # Carried in from [O] rather than recomputed -- the verdict
                    # does not depend on the design being debugged (identical on
                    # all 70 against a 30/168 model and a 168/168 control), and
                    # recomputing would put a gate back inside the loop.
                    "conforms_by_liveness": _conforms_by_liveness(
                        mechanical, oracle_liveness),
                    # WHO A VIOLATES MAY BE ABOUT. A failing oracle is
                    # evidence about the model -- unless a SECOND
                    # implementation of the same requirement fails it too, in
                    # which case it may be the check.
                    #
                    # Attribution, not suppression, and the distinction is the
                    # whole of it: these still count as VIOLATES, still block,
                    # and the oracle is not rejected. The witness is a second
                    # reading by the same author and has no authority to
                    # overrule the requirement. What it can do is say where a
                    # turn is unlikely to be repaid.
                    #
                    # Measured on r-i2c: the loop drove VIOLATES 9 -> 5 and
                    # spent its last three turns on the 5 that remained, every
                    # one of which a known-good control also fails. The witness
                    # had flagged exactly those five before the reference model
                    # existed, and the note sat unread in the oracle artifact.
                    "violates_the_witness_also_fails": sorted(
                        u for u, v in mechanical.items()
                        if v == "VIOLATES" and u in witness_notes),
                    "mechanical_verdicts": {
                        "counts": verdict.counts(mechanical),
                        "blocking": verdict.blocking(mechanical),
                        "by_requirement": mechanical,
                        "routes": {u: verdict.ROUTE[v]
                                   for u, v in sorted(mechanical.items())},
                    },
                    "carried_from_the_oracle_stage": carried,
                    # What earlier turns appended. Reported per turn so a reader
                    # can tell "NOT_EXERCISED fell" from "NOT_EXERCISED fell
                    # BECAUSE stimulus was added", which are different claims.
                    "stimulus_added": list(added),
                    "oracle_set": {
                        "count": len(oracles),
                        "frozen": at_entry,
                        "evidence_changed": freeze.stale_proofs(oracles, proofs),
                        "variants": len(variants or []),
                    },
                    "regressed": regressed,
                    "idle_turns": idle_turns,
                    "stopped_because": stop,
                }, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")

        if not has_errors(issues):
            return source, issues
        if turn == turns:
            short = [u for u, r in by_uid.items() if not r.ok]
            # Attribute the residue rather than reporting a bare count. On
            # r-i2c the loop stopped "with 13 oracle(s) short of CONFORMS" and
            # every one of the 5 still FAILING was a check a known-good design
            # also fails -- so the turns it spent on them could not have been
            # repaid, and the number as printed read as 13 unfixed model bugs.
            doubted = sorted(u for u in short if u in witness_notes)
            stop = (f"turn budget of {turns} spent with {len(short)} oracle(s) "
                    f"short of CONFORMS")
            if doubted:
                stop += (f"; a second implementation of the same requirement "
                         f"also fails {len(doubted)} of them "
                         f"({', '.join(doubted[:6])}), so those may be the "
                         f"check rather than the model")
            break
        if not oracles:
            stop = "no trusted oracle to drive the loop"
            break

        session = DebugSession(
            source, contract, stimulus_by_tp, oracles, base=base,
            requirements=requirements,
            verdicts={u: v for u, v in mechanical.items()},
            reasons={u: {"reason": r.detail, "evidence": "", "remedy": ""}
                     for u, r in by_uid.items()},
            covers=covers,
            workdir=Path(run_dir) / "specflow" / "_refmodel_debug"
            if run_dir is not None else None,
            stimulus_gen=_restimulate, normalized=normalized,
            testplan=testplan, reset_ports=frozenset(reset_names),
            transactional=True, model_route_stalled=stalled,
            # WHAT IS LEFT OF THE BUDGET, not the whole of it again.
            #
            # A fresh `DebugSession` is built every turn and counts its own
            # `added` from zero, so passing the full figure made the budget
            # PER TURN. Measured on t-i2c, the first run in which the tool was
            # reachable at all: exactly 12 testpoints added on each of four
            # turns, 48 against a stated budget of 12, and not one of them
            # changed a single verdict -- CONFORMS held at 45 and VIOLATES at 9
            # from the first turn to the last.
            #
            # The defect predates the fix that exposed it. `add_stimulus` had
            # never once fired in six runs, so nothing had ever spent this
            # budget twice.
            stimulus_budget=max(0, stimulus_budget - len(added)),
        )
        before = source
        # Whether the model route is still producing anything. Compared
        # pre-debug against pre-debug, so it asks exactly "did the last model
        # turn move the count", and recorded only for model turns -- a stimulus
        # turn is not evidence about the model route either way.
        if session.route == MODEL:
            failing_now = sum(1 for r in by_uid.values() if r.failed())
            stalled = (last_failing is not None and failing_now >= last_failing)
            last_failing = failing_now
        source, _attempts, _note = debugger.debug(session)
        if session.added:
            # Write the grown testplan back into the CALLER's list, in place.
            #
            # `stimulus_by_tp` already reaches the caller, because the session
            # never copies that dict -- so without this the two halves of one
            # appended testpoint separate: `render_suite` gets stimulus for a
            # testpoint it is not rendering, and the scenario the loop paid a
            # model call to stage is silently dropped from the suite. The plan
            # claimed this flowed through "with no special plumbing, because
            # nothing was edited"; the session copies the list, so it did not.
            #
            # One explicit line at the boundary where growth leaves the loop,
            # rather than aliasing the caller's list deep inside the session.
            testplan[:] = session.testplan
            added.extend(session.added)
            # I7, and the whole of what append-only leaves of it: an oracle
            # that GAINED a testpoint was verified against an evidence set that
            # no longer exists. Existing stimulus is never edited, so no other
            # verification can have gone stale. RECORDED, not re-decided here --
            # re-verifying belongs to the stage that owns the witness and the
            # variants, and doing it inline would put a gate back inside the
            # loop, which is the thing this rework removed.
            stale_now = freeze.stale_proofs(oracles, proofs)
            if stale_now:
                logger.info(
                    "turn %d: %d oracle(s) gained evidence and are due "
                    "re-verification: %s", turn, len(stale_now),
                    ", ".join(stale_now))
            logger.info("turn %d added %d testpoint(s): %s", turn,
                        len(session.added), ", ".join(session.added))
        elif source == before:
            # A TURN THAT CHANGED NOTHING DOES NOT END THE LOOP.
            #
            # It used to: "the next turn would re-derive the verdicts already
            # in hand". That is true only if the next turn would be the SAME
            # turn, and it is not -- a model turn that moved nothing sets
            # `stalled`, which hands the next one the stimulus route. Returning
            # here spent one turn of three and quit with the stimulus budget
            # untouched, which is exactly what n-i2c did: 24 oracles never
            # exercised, `add_stimulus` never called once, and a blocking
            # verdict reported as though the loop had tried.
            #
            # The reference model does not get to skip or give up while any
            # oracle is short of CONFORMS and there is any budget left to spend.
            # It stops on success, on exhaustion, or on both routes being
            # provably dry -- and the reason is recorded either way.
            dry = _both_routes_dry(session, by_uid)
            if dry:
                stop = dry
                break
            idle_turns += 1

    if stop and last_artifact is not None and last_artifact.is_file():
        try:
            blob = json.loads(last_artifact.read_text(encoding="utf-8"))
            blob["stopped_because"] = stop
            blob["idle_turns"] = idle_turns
            last_artifact.write_text(
                json.dumps(blob, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        except (OSError, ValueError) as exc:  # noqa: BLE001
            logger.warning("stop reason not recorded (%r)", exc)
    if stop:
        logger.info("loop stopped: %s", stop)

    return source, issues


def _conforms_by_liveness(
    mechanical: dict[str, str], liveness: dict[str, str],
) -> dict[str, int | None]:
    """How many CONFORMS came from a check that could have said otherwise.

    `None` where the measurement did not run, never 0: a set frozen before
    liveness existed reports "not measured" rather than "none dead", which is
    the same distinction `OracleSet.rates` keeps and the same one whose absence
    once read `over_strict: 0` as "no oracle is over-strict" when it meant "no
    control was supplied".
    """
    conforming = [u for u, v in mechanical.items() if v == "CONFORMS"]
    if not liveness:
        return {"conforms": len(conforming), "from_a_check_that_can_fail": None,
                "from_a_check_that_cannot": None,
                "from_a_check_undecided": None, "not_measured": None}
    counted = [u for u in conforming if u in liveness]
    dead = [u for u in counted if liveness[u].startswith("dead")]
    # `unknown` gets its own bucket rather than joining "can fail". It means the
    # instrument could not decide -- no replayable testpoint, no declared output
    # port, a model that would not run -- and folding that into the reassuring
    # side makes the reassuring side the default for everything unmeasurable.
    undecided = [u for u in counted
                 if not liveness[u].startswith("dead") and liveness[u] != "live"]
    return {
        "conforms": len(conforming),
        "from_a_check_that_can_fail": len(counted) - len(dead) - len(undecided),
        "from_a_check_that_cannot": len(dead),
        "from_a_check_undecided": len(undecided),
        "not_measured": len(conforming) - len(counted),
    }


def _both_routes_dry(session: DebugSession, by_uid: dict) -> str:
    """Why there is nothing left to try, or empty if there is.

    The only honest reason to stop short of every oracle conforming. Both are
    facts about the loop's remaining moves, not about whether the last turn
    happened to help:

    * nothing is failing AND nothing is unexercised -- so neither route has an
      input, and whatever is left is `broken`, which is a finding about the
      oracle that editing the model cannot discharge;
    * something is unexercised but the stimulus budget is spent, so the route
      that could reach it has no moves left.
    """
    failing = [r for r in by_uid.values() if r.failed()]
    unexercised = [r for r in by_uid.values() if r.unexercised()]
    if not failing and not unexercised:
        return ("neither route has an input: nothing is failing and nothing is "
                "unexercised, so what remains is broken oracles, which editing "
                "the model cannot discharge")
    if not failing and unexercised and len(session.added) >= session.stimulus_budget:
        return (f"{len(unexercised)} oracle(s) still unexercised and the "
                f"stimulus budget of {session.stimulus_budget} testpoint(s) is "
                f"spent; the remaining scenarios need a testplan fix")
    return ""


def write_artifacts(
    run_dir: Path, result: StageResult[RefModelOutput], source: str
) -> Path:
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "ref_model.py"
    path.write_text(source, encoding="utf-8")

    (out_dir / "refmodel_gate.json").write_text(
        json.dumps(
            {
                "ok": result.ok,
                "rounds": result.rounds,
                # The generator's own claim about where each requirement is
                # implemented. Recorded because it is what the judge is checking
                # and what a reader needs to follow a requirement into the code.
                "covers": result.output.covers,
                "underdetermined": result.output.underdetermined,
                "issues": [
                    {"severity": i.severity, "path": i.path, "message": i.message,
                     "kind": i.kind}
                    for i in result.issues
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


# ------------------------------------------------------------------- fan-out
