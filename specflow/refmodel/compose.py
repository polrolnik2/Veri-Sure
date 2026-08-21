"""Assemble `ref_model.py`, and run the bounded gate loop around the agent.

Base selection (R0) is a script decision from contract fields, not a prompt: the
agent's own `base` answer is cross-checked against it rather than trusted.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Protocol

from ..model_io import ModelPort
from ..schema import Issue, has_errors
from ..stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_stage,
)
from . import trust
from .agent import SYSTEM, RefModelOutput, parse_response
from .session import DebugSession
from .validate import validate

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
            control_source=control_source,
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
) -> tuple[str, list[Issue]]:
    """Judge, screen, debug; repeat. Returns the final source and its issues.

    One turn is one expensive judging pass (~77 model calls) and several cheap
    debug attempts (milliseconds each, pure Python). The judge re-runs only when
    the session stops, which is what makes "a few attempts against one frozen
    oracle set" the unit of work.
    """
    from .judge import oracles_of, run_judge, verdict_map, write_round

    # `max_turns + 1` passes, and the extra one is not slack. The judge must
    # have seen the model that is actually returned: satisfying every trusted
    # oracle is NOT the same as the requirements being met -- oracles are a
    # subset (screening discards some) and each is a necessary condition the
    # judge wrote down, never its whole verdict. Only the judge closes that gap.
    #
    # Without the final pass the stage reports verdicts about a model that no
    # longer exists: a turn that fixed everything still looks blocked, and one
    # that broke something the oracles do not cover still looks clean.
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
        if run_dir is not None:
            (Path(run_dir) / "specflow" / "judge" / f"r{turn}" / "trust.json"
             ).write_text(
                json.dumps({"rates": screened.rates(),
                            "discarded": screened.discarded,
                            "sensitivity": screened.sensitivity},
                           indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if not screened.trusted:
            # Nothing usable this turn. The verdicts still block, and the
            # caller sees them as prose -- which is exactly today's behaviour,
            # so a judge that cannot write oracles costs nothing beyond the
            # screening.
            return source, issues

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
        )
        before = source
        source, _attempts, _note = debugger.debug(session)
        if source == before:
            # The turn changed nothing, so re-judging would return the verdicts
            # already in hand. Spending ~77 model calls to rediscover them is
            # the expensive way to learn nothing.
            return source, issues

    return source, issues


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
