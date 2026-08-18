"""Assemble `ref_model.py`, and run the bounded gate loop around the agent.

Base selection (R0) is a script decision from contract fields, not a prompt: the
agent's own `base` answer is cross-checked against it rather than trusted.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

from ..ids import method_name
from ..model_io import ModelPort
from ..schema import Issue
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


def _defines(source: str, name: str) -> bool:
    """Does `source` already define a method called `name` at any indentation?"""
    return re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", source, re.M) is not None


def synthesise_dispatch(out: RefModelOutput, base: str) -> str:
    """Build the `evaluate`/`step` that calls each fragment in order.

    This is a script rather than a prompt because it is fully determined: the
    call order is the order the fragments were declared, and the entry-point
    name is `choose_base`'s decision from the contract, which the prompt already
    describes as "not negotiable". Asking an agent for something already known
    only adds a way to not get it.

    That is not hypothetical. The prompt asked for the dispatch while the
    response schema had nowhere to put it -- `helpers` was shown empty in the
    template -- so a model that followed the schema literally returned fragments
    and no dispatch, `Model.evaluate` fell through to the base class, and G4
    failed with `NotImplementedError` for four rounds without the issue text
    ever naming the real defect. One model happened to infer that the dispatch
    belonged in `helpers`; that convention was never stated anywhere.

    Outputs are seeded to `None` rather than left absent so that a port no
    fragment writes survives as `None` for G4 to report as an undetermined
    output, instead of raising `KeyError` from whichever caller reads it first.
    """
    calls = "\n".join(
        f"        self.{frag.method_name or method_name(frag.req_uid)}(i, o)"
        for frag in out.fragments
    )
    return (
        f"    def {base}(self, i):\n"
        "        o = {p: None for p in self.OUTPUT_PORTS}\n"
        f"{calls}\n"
        "        return o"
    )


def render(out: RefModelOutput, contract: dict) -> str:
    """Emit `ref_model.py`. Deterministic; the agent supplies only method bodies."""
    body: list[str] = []
    if out.helpers.strip():
        body.append(textwrap.indent(textwrap.dedent(out.helpers).strip(), "    "))
    for frag in out.fragments:
        body.append(textwrap.indent(textwrap.dedent(frag.code).strip(), "    "))

    # Only when the agent did not supply one itself: a second definition would
    # shadow the first, and which one wins depends on emission order rather than
    # on anything the author decided.
    base = choose_base(contract)
    if not _defines(out.helpers, base) and not any(
        _defines(f.code, base) for f in out.fragments
    ):
        body.append(synthesise_dispatch(out, base))

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
        + "\n\n".join(body)
        + "\n"
    )


def run_refmodel(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 3,
) -> tuple[StageResult[RefModelOutput], str]:
    """R2-R6. Returns the stage result and the rendered source."""
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
            parts.append(gate_failures_block(issues))
        if previous:
            parts.append(previous_answer_block(previous))
        return "\n\n".join(parts)

    def gate(out: RefModelOutput) -> list[Issue]:
        rendered["src"] = render(out, contract)
        return validate(
            out=out,
            source=rendered["src"],
            requirements=requirements,
            contract=contract,
            expected_base=base,
            workdir=workdir,
        )

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
                "fragments": [
                    {"req_uid": f.req_uid, "method_name": method_name(f.req_uid)}
                    for f in result.output.fragments
                ],
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
