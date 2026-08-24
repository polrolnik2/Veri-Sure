"""Assemble `ref_model.py`, and run the bounded gate loop around the agent.

Base selection (R0) is a script decision from contract fields, not a prompt: the
agent's own `base` answer is cross-checked against it rather than trusted.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
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
from . import freeze, trust, verdict
from .agent import SYSTEM, RefModelOutput, parse_response
from .oracles import decide_all, replay, stimulus_liveness
from .session import DebugSession
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


def run_refmodel(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 3,
    judge_port: ModelPort | None = None,
    run_dir: Path | None = None,
    testplan: list[dict] | None = None,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    debugger: RefModelDebugger | None = None,
    max_judge_turns: int = 3,
    control_source: str | None = None,
    normalized: dict[str, dict] | None = None,
    #: Generate a SECOND oracle set from the requirements alone, screen it
    #: beside the judge's, and report both. Read-only: the judge's oracles still
    #: drive the loop, so this changes nothing about the run except what is
    #: written down. Off by default because it costs one call per requirement.
    compare_oracles: bool = False,
    #: Requirement-only oracles drive the loop and the judge stops deciding.
    #: Implies `compare_oracles`, which is what generates them.
    oracle_driven: bool = False,
) -> tuple[StageResult[RefModelOutput], str]:
    """R2-R6. Returns the stage result and the rendered source.

    `judge_port`, when supplied, adds the per-requirement judge to the gate: one
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
    rendered: dict[str, str] = {"src": ""}

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

    rounds = {"n": 0}
    judged: dict[str, object] = {"result": None}

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
        # The judge runs only on a model that already passes the mechanical
        # checks. Asking ~70 questions about a model that does not import, or
        # leaves an output undetermined, spends a fan-out to rediscover what a
        # script already said -- and the verdicts would be about code that is
        # going to be regenerated anyway.
        # With a debugger, the judge does NOT run inside the gate. Generation
        # is gated on the mechanical checks alone and repaired by regenerating,
        # which is the right tool for a missing quote or an unwritten output --
        # a whole round was lost to exactly that. Behavioural failures go to the
        # debug turns below, which EDIT rather than regenerate.
        if judge_port is not None and debugger is None and not has_errors(issues):
            from .judge import run_judge, write_report

            result = run_judge(
                source=rendered["src"], contract_json=contract_json,
                requirements=requirements, covers=out.covers,
                port=judge_port, round_=rounds["n"],
                contract=contract, base=base, testplan=testplan,
                stimulus_by_tp=stimulus_by_tp,
            )
            judged["result"] = result
            if run_dir is not None:
                write_report(run_dir, result)
            issues = issues + result.issues
        rounds["n"] += 1
        return issues

    result = run_stage(
        stage=STAGE,
        port=port,
        build_prompt=build_prompt,
        parse=parse_response,
        gate=gate,
        max_repairs=max_repairs,
    )

    if debugger is not None and judge_port is not None and result.ok:
        source, issues = _debug_turns(
            source=rendered["src"], contract=contract, contract_json=contract_json,
            requirements=requirements, covers=result.output.covers,
            judge_port=judge_port, base=base, testplan=testplan or [],
            stimulus_by_tp=stimulus_by_tp or {}, run_dir=run_dir,
            debugger=debugger, max_turns=max_judge_turns,
            control_source=control_source, normalized=normalized,
            compare_oracles=compare_oracles or oracle_driven,
            oracle_driven=oracle_driven,
        )
        rendered["src"] = source
        result = StageResult(result.output, issues, result.rounds)

    return result, rendered["src"]


def _debug_turns(
    *,
    source: str,
    contract: dict,
    contract_json: str,
    requirements: list[dict],
    covers: dict[str, list[str]],
    judge_port: ModelPort,
    base: str,
    testplan: list[dict],
    stimulus_by_tp: dict[str, list[dict]],
    run_dir: Path | None,
    debugger: RefModelDebugger,
    max_turns: int,
    control_source: str | None,
    normalized: dict[str, dict] | None = None,
    compare_oracles: bool = False,
    #: Let the requirement-only oracles DRIVE, and derive the blocking verdicts
    #: from screening them instead of from the judge's opinion. The judge still
    #: runs when `compare_oracles` is on, for the record, but nothing routes off
    #: it. See `_oracle_driven_turns`.
    oracle_driven: bool = False,
) -> tuple[str, list[Issue]]:
    """Judge, screen, debug; repeat. Returns the final source and its issues.

    One turn is one expensive judging pass (~77 model calls) and several cheap
    debug attempts (milliseconds each, pure Python). The judge re-runs only when
    the session stops, which is what makes "a few attempts against one frozen
    oracle set" the unit of work.
    """
    from .judge import (
        oracles_of,
        reconcile,
        run_judge,
        verdict_map,
        write_round,
    )

    # `max_turns + 1` passes, and the extra one is not slack. The judge must
    # have seen the model that is actually returned: satisfying every trusted
    # oracle is NOT the same as the requirements being met -- oracles are a
    # subset (screening discards some) and each is a necessary condition the
    # judge wrote down, never its whole verdict. Only the judge closes that gap.
    #
    # Without the final pass the stage reports verdicts about a model that no
    # longer exists: a turn that fixed everything still looks blocked, and one
    # that broke something the oracles do not cover still looks clean.
    # Generated ONCE, not per turn. An oracle written from the requirement
    # alone does not depend on the model, which is the entire reason it can be
    # frozen -- so re-asking each turn would pay 77 calls to receive the same
    # answer. The judge's oracles cannot do this, and that asymmetry is the
    # clearest practical argument for the split.
    isolated: list = []
    frozen_path = (Path(run_dir) / "specflow" / "oracles.json"
                   if run_dir is not None else None)
    if compare_oracles:
        try:
            from .conform import conforming_implementation
            from .oracle_gen import run_oracle_gen

            # Read forever. A run re-entered with `--reuse` regenerating its
            # oracles would hand the loop a different measure for the same
            # requirements -- which is the disease measured on the judge-driven
            # loop, where no oracle source was identical between rounds and
            # CONFORMS random-walked 30, 33, 30. Loading also skips the
            # conforming implementation, because nothing left needs it.
            if frozen_path is not None:
                isolated = freeze.load(frozen_path)
                if isolated:
                    logger.info("oracles: %d frozen, read from %s",
                                len(isolated), frozen_path)

            if not isolated:
                # An implementation of the same requirements, generated once,
                # for the must-pass leg. Never the golden control: its
                # behaviour must not reach oracle generation (I1), and it has
                # to stay held out to grade the result. A design where this
                # cannot be produced still gets oracles -- the leg goes quiet
                # rather than failing them all.
                conforming, conform_issues = conforming_implementation(
                    requirements=requirements, contract_json=contract_json,
                    port=judge_port,
                    workdir=(Path(run_dir) / "specflow" / "_conform"
                             if run_dir is not None
                             else Path("/tmp/specflow-conform")),
                )
                if not conforming:
                    logger.warning(
                        "conforming implementation: not produced (%d issue(s)); "
                        "the must-pass leg is off for this run",
                        len(conform_issues))

                isolated, _ = run_oracle_gen(
                    requirements=requirements, contract_json=contract_json,
                    contract=contract, testplan=testplan, port=judge_port,
                    normalized=normalized,
                    conforming_source=conforming,
                    stimulus_by_tp=stimulus_by_tp, base=base,
                )
                if frozen_path is not None:
                    isolated, drifted = freeze.freeze(
                        isolated, frozen_path, normalized)
                    for uid, why in sorted(drifted.items()):
                        logger.warning("oracle drift %s: %s", uid, why)
                else:
                    isolated = freeze.stamp(isolated, normalized)
        except Exception as exc:  # noqa: BLE001
            # Never let the reporting path fail a run. It informs a decision
            # about a future design; it does not gate this one.
            logger.warning("isolated oracles: not generated (%r)", exc)

    if oracle_driven and isolated:
        return _oracle_driven_turns(
            source=source, contract=contract, contract_json=contract_json,
            requirements=requirements, covers=covers, oracles=isolated,
            base=base, testplan=testplan, stimulus_by_tp=stimulus_by_tp,
            run_dir=run_dir, debugger=debugger, max_turns=max_turns,
            control_source=control_source, normalized=normalized,
            judge_port=judge_port,
        )

    issues: list[Issue] = []
    turns = max(1, int(max_turns))
    for turn in range(turns + 1):
        result = run_judge(
            source=source, contract_json=contract_json,
            requirements=requirements, covers=covers,
            port=judge_port, round_=turn,
            contract=contract, base=base, testplan=testplan,
            stimulus_by_tp=stimulus_by_tp,
        )
        issues = result.issues
        if run_dir is not None:
            write_round(run_dir, turn, result)
        if not has_errors(issues):
            return source, issues
        if turn == turns:
            # Budget spent. `issues` describes `source`, which is the invariant
            # this loop owes its caller.
            break

        screened = trust.screen(
            oracles_of(result), verdict_map(result), source, contract,
            stimulus_by_tp, testplan, base=base, control_source=control_source,
        )

        # A verdict its own oracle contradicts is a TRANSLATION failure, not an
        # untrustworthy oracle: the oracle is the verdict written executably, so
        # the judge is the authority and the two must be made to agree. One
        # focused call per conflict -- 18 against 77 for a full pass -- recovers
        # oracles that would otherwise be discarded over a bad translation.
        #
        # The judge may resolve it either way, and the second way is the one
        # worth having: changing the VERDICT because writing the check made the
        # claim concrete enough to fail. Rewriting the oracle to match the
        # verdict here instead would fabricate the agreement and lose that.
        if screened.conflicts:
            fixed = reconcile(
                conflicts=screened.conflicts,
                verdicts={v.req_uid: v for v in result.verdicts},
                requirements=requirements, source=source,
                contract_json=contract_json, contract=contract,
                port=judge_port, base=base, round_=turn,
                known_tps={str(t.get("uid")) for t in (testplan or [])
                           if t.get("uid")},
            )
            if fixed:
                merged = [fixed.get(v.req_uid, v) for v in result.verdicts]
                result = type(result)(verdicts=merged)
                issues = result.issues
                if not has_errors(issues):
                    return source, issues
                screened = trust.screen(
                    oracles_of(result), verdict_map(result), source, contract,
                    stimulus_by_tp, testplan, base=base,
                    control_source=control_source,
                )
                if run_dir is not None:
                    write_round(run_dir, turn, result)

        if run_dir is not None:
            # Measured beside the trust rates because it is what most often
            # explains them. An inert testpoint makes every oracle naming it
            # unjudgeable, and the resulting UNKNOWNs and "never observed"
            # failures otherwise read as findings about the judge.
            live = stimulus_liveness(source, contract, stimulus_by_tp, base=base)
            # The MECHANICAL verdict, beside the judge's opinion rather than
            # instead of it. Nothing routes off this yet -- it is written so the
            # two can be compared on real runs before anything depends on it.
            mechanical = verdict.classify(
                discarded=screened.discarded,
                passing={u for u, ok in screened.decisions.items() if ok},
                failing={u for u, ok in screened.decisions.items() if not ok},
                had_oracle={o.req_uid for o in oracles_of(result)},
                requirements=requirements,
            )
            (Path(run_dir) / "specflow" / "judge" / f"r{turn}" / "trust.json"
             ).write_text(
                json.dumps({"rates": screened.rates(),
                            **_comparison(
                                isolated=isolated, judge_rates=screened.rates(),
                                source=source, contract=contract,
                                stimulus_by_tp=stimulus_by_tp, testplan=testplan,
                                base=base, control_source=control_source,
                                normalized=normalized, live=live),
                            "mechanical_verdicts": {
                                "counts": verdict.counts(mechanical),
                                "blocking": verdict.blocking(mechanical),
                                "by_requirement": mechanical,
                                "routes": {
                                    uid: verdict.ROUTE[v]
                                    for uid, v in sorted(mechanical.items())
                                },
                            },
                            "discarded": screened.discarded,
                            "sensitivity": screened.sensitivity,
                            "unresolved_conflicts": screened.conflicts,
                            "control_unexercised": screened.unexercised,
                            "stimulus": {
                                **live.summary(),
                                "inert_testpoints": live.inert,
                                "requirements_left_unjudgeable": sorted(
                                    o.req_uid for o in oracles_of(result)
                                    if o.tp_uids
                                    and all(t in live.inert for t in o.tp_uids)
                                ),
                            }},
                           indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if not screened.trusted:
            # Nothing usable this turn. The verdicts still block, and the
            # caller sees them as prose -- which is exactly today's behaviour,
            # so a judge that cannot write oracles costs nothing beyond the
            # screening.
            return source, issues

        # The stimulus generator, bound to the judge's port. Injected rather
        # than imported by the session for the reason `RefModelDebugger` is:
        # everything decidable about a debug turn must stay runnable with no
        # model at all, and a generator is the one part that cannot be.
        def _restimulate(req: dict, hint: str) -> list[dict]:
            from ..testcase_agent import stimulus_for_scenario

            return stimulus_for_scenario(
                requirement=req, what_the_scenario_needs=hint,
                contract=contract, port=judge_port,
            )

        _, reset_names, _ = classify(contract)
        session = DebugSession(
            source, contract, stimulus_by_tp, screened.trusted, base=base,
            requirements=requirements,
            verdicts=verdict_map(result),
            reasons={v.req_uid: {"reason": v.reason, "evidence": v.evidence,
                                 "remedy": v.remedy}
                     for v in result.verdicts},
            covers=covers,
            workdir=Path(run_dir) / "specflow" / "_refmodel_debug"
            if run_dir is not None else None,
            stimulus_gen=_restimulate,
            normalized=normalized,
            testplan=testplan,
            reset_ports=frozenset(reset_names),
        )
        before = source
        source, _attempts, _note = debugger.debug(session)
        if session.added:
            # The testpoints this turn minted outlive it. `stimulus_by_tp` is
            # mutated in place, so the next judging pass replays the grown suite
            # -- which is the whole point: a scenario staged once should not have
            # to be re-staged, and the testplan grows so the rendered suite gets
            # it too.
            testplan = session.testplan
            logger.info("turn %d added %d testpoint(s): %s",
                        turn, len(session.added), ", ".join(session.added))
        if source == before:
            # The turn changed nothing, so re-judging would return the verdicts
            # already in hand. Spending ~77 model calls to rediscover them is
            # the expensive way to learn nothing.
            return source, issues

    return source, issues


def _oracle_driven_turns(
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
    judge_port: ModelPort,
) -> tuple[str, list[Issue]]:
    """The loop with no judge in it.

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

    def _restimulate(req: dict, hint: str) -> list[dict]:
        from ..testcase_agent import stimulus_for_scenario

        return stimulus_for_scenario(
            requirement=req, what_the_scenario_needs=hint,
            contract=contract, port=judge_port)

    for turn in range(turns + 1):
        moved = freeze.drift(oracles, [
            type(o)(req_uid=o.req_uid, clause=o.clause, source=o.source,
                    tp_uids=o.tp_uids, hash=at_entry[o.req_uid])
            for o in oracles
        ], normalized)
        if moved:
            raise RuntimeError(
                "the frozen oracle set changed under the loop measuring "
                f"against it: {sorted(moved)}")
        screened = trust.screen(
            oracles, {o.req_uid: "met" for o in oracles}, source, contract,
            stimulus_by_tp, testplan, base=base, control_source=control_source,
            transactional=True,
        )
        # Gate 1 asks an oracle to agree with a verdict it never had. With no
        # judge there is none, so it is neutralised by construction: the
        # `"met"` above makes it discard exactly the oracles that FAIL the
        # model, which are the findings this loop exists to act on. Recover
        # them -- a disagreement with a verdict that does not exist is not a
        # defect in the oracle.
        failing_uids = {
            uid for uid, why in screened.discarded.items()
            if why.startswith("disagreed:")
        }
        trusted = list(screened.trusted) + [
            o for o in oracles if o.req_uid in failing_uids
        ]
        discarded = {uid: why for uid, why in screened.discarded.items()
                     if uid not in failing_uids}

        results = decide_all(trusted, source, contract, stimulus_by_tp,
                             base=base, transactional=True)
        by_uid = {r.req_uid: r for r in results}
        mechanical = verdict.classify(
            discarded=discarded,
            passing={u for u, r in by_uid.items() if r.ok is True},
            failing={u for u, r in by_uid.items() if r.failed()},
            had_oracle={o.req_uid for o in oracles},
            requirements=requirements,
        )
        issues = verdict.issues(
            mechanical,
            {u: (r.detail or r.broken) for u, r in by_uid.items()},
        )

        if run_dir is not None:
            out = Path(run_dir) / "specflow" / "judge" / f"r{turn}"
            out.mkdir(parents=True, exist_ok=True)
            (out / "trust.json").write_text(
                json.dumps({
                    "driver": "requirement-oracles",
                    "rates": screened.rates(),
                    "mechanical_verdicts": {
                        "counts": verdict.counts(mechanical),
                        "blocking": verdict.blocking(mechanical),
                        "by_requirement": mechanical,
                        "routes": {u: verdict.ROUTE[v]
                                   for u, v in sorted(mechanical.items())},
                    },
                    "discarded": discarded,
                    "recovered_from_gate1": sorted(failing_uids),
                    # What earlier turns appended. Reported per turn so a reader
                    # can tell "NOT_EXERCISED fell" from "NOT_EXERCISED fell
                    # BECAUSE stimulus was added", which are different claims.
                    "stimulus_added": list(added),
                    "oracle_set": {
                        "count": len(oracles),
                        "frozen": at_entry,
                        "evidence_changed": freeze.stale_proofs(oracles, proofs),
                    },
                }, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")

        if not has_errors(issues):
            return source, issues
        if turn == turns or not trusted:
            break

        session = DebugSession(
            source, contract, stimulus_by_tp, trusted, base=base,
            requirements=requirements,
            verdicts={u: v for u, v in mechanical.items()},
            reasons={u: {"reason": r.detail, "evidence": "", "remedy": ""}
                     for u, r in by_uid.items()},
            covers=covers,
            workdir=Path(run_dir) / "specflow" / "_refmodel_debug"
            if run_dir is not None else None,
            stimulus_gen=_restimulate, normalized=normalized,
            testplan=testplan, reset_ports=frozenset(reset_names),
            transactional=True,
        )
        before = source
        source, _attempts, _note = debugger.debug(session)
        if session.added:
            testplan = session.testplan
            added.extend(session.added)
            logger.info("turn %d added %d testpoint(s): %s", turn,
                        len(session.added), ", ".join(session.added))
        elif source == before:
            # Nothing changed and no scenario was staged, so the next turn
            # would re-derive the verdicts already in hand.
            return source, issues

    return source, issues


def _comparison(
    *,
    isolated: list,
    judge_rates: dict,
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    testplan: list[dict],
    base: str,
    control_source: str | None,
    normalized: dict[str, dict] | None,
    live,
) -> dict:
    """Everything measured beside the loop but not driving it.

    Two questions, both read-only:

    * **Does an oracle written WITHOUT the model screen better than one written
      with it?** Same gates, same model, same stimulus, same control -- the only
      difference is what was in context when the oracle was written. That is the
      cleanest available test of whether the split is worth making, and it costs
      one screening pass because both oracle sets already exist.
    * **Did the stimulus stage each requirement's activation?** Asked of the
      normalized requirements rather than of the oracles, so it does not inherit
      the suspicion it is meant to check.

    Never raises. This informs a decision about a future design; a defect in it
    must not fail the run it is observing.
    """
    out: dict = {}
    try:
        if isolated:
            # Gate 1 asks whether an oracle reproduces THE VERDICT IT SHIPPED
            # WITH, and an isolated oracle ships with none. Feeding it a blanket
            # "met" does not skip the gate -- it makes the gate DISCARD every
            # isolated oracle that fails the model, before gates 3 and 2 ever
            # see it, so over-strictness and vacuity would be measured over a
            # population filtered to the passing ones. That flatters the
            # isolated set on exactly the two columns the comparison turns on.
            #
            # Pre-deciding and handing gate 1 the matching verdict makes it a
            # no-op instead, so the later gates run on all of them.
            said = {}
            for o in isolated:
                d = trust._decide_over(  # noqa: SLF001
                    o, source, contract, stimulus_by_tp, base=base)
                said[o.req_uid] = "met" if d.ok else "not_met"
            other = trust.screen(
                isolated, said, source, contract,
                stimulus_by_tp, testplan, base=base, control_source=control_source,
            )
            # Gate 1 is deliberately excluded from the comparison: it asks
            # whether an oracle agrees with the VERDICT it shipped with, and an
            # isolated oracle ships with no verdict. Comparing the two on it
            # would score the isolated set against a question it was never
            # asked. The gates that do transfer are over-strictness (does a
            # known-good design satisfy it) and vacuity (can anything falsify
            # it) -- which are the two that actually say whether a check is any
            # good.
            rates = other.rates()
            out["isolated_oracles"] = {
                "generated": len(isolated),
                "rates": rates,
                "comparable": {
                    "over_strict": rates.get("over_strict"),
                    "convicted": rates.get("convicted"),
                    "unknown": rates.get("unknown"),
                    "unexercised": rates.get("unexercised"),
                    "malformed": rates.get("malformed"),
                },
                "judge_comparable": {
                    k: judge_rates.get(k) for k in
                    ("over_strict", "convicted", "unknown", "unexercised",
                     "malformed")
                },
                "note": "gate 1 (agreement with its own verdict) is excluded: "
                        "an isolated oracle ships with no verdict to agree with",
            }
    except Exception as exc:  # noqa: BLE001
        out["isolated_oracles"] = {"error": repr(exc)}

    try:
        if normalized:
            from ..normalize import NormalizedRequirement
            from ..obligation import obligations, report
            from ..ports import classify

            norms = [NormalizedRequirement.model_validate(n)
                     for n in normalized.values()]
            _, resets, _ = classify(contract)
            rows = {
                tp: replay(source, contract, steps, base=base).rows
                for tp, steps in stimulus_by_tp.items()
            }
            out["obligations"] = report(
                obligations_=obligations(norms), testplan=testplan,
                stimulus_by_tp=stimulus_by_tp, replay_rows=rows,
                reset_ports=frozenset(resets),
            )
            out["obligations"]["unobservable"] = sorted(
                n.req_uid for n in norms if n.unobservable)
    except Exception as exc:  # noqa: BLE001
        out["obligations"] = {"error": repr(exc)}
    return out


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
