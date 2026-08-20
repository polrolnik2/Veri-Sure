"""Assemble `ref_model.py`, and run the bounded gate loop around the agent.

Base selection (R0) is a script decision from contract fields, not a prompt: the
agent's own `base` answer is cross-checked against it rather than trusted.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from ..model_io import ModelPort
from ..schema import Issue, has_errors
from ..stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_stage,
)
from .agent import SYSTEM, RefModelOutput, parse_response
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
        if judge_port is not None and not has_errors(issues):
            from .judge import run_judge, write_report

            result = run_judge(
                source=rendered["src"], contract_json=contract_json,
                requirements=requirements, covers=out.covers,
                port=judge_port, round_=rounds["n"],
                contract=contract, base=base, testplan=testplan,
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
    return result, rendered["src"]


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
