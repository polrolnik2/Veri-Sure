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
            # The artifact first: the defect list refers to it, so a reader
            # (or a model) meets what is being repaired before what is wrong
            # with it. S1-S3 order it the same way.
            if previous:
                parts.append(previous_answer_block(previous))
            parts.append(gate_failures_block(issues))
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


# ------------------------------------------------------------------- fan-out


def run_refmodel_fanout(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 3,
    fanout: bool = True,
) -> tuple[StageResult[RefModelOutput], str]:
    """One small call per requirement, composed into one reference model.

    The batched call this replaces asked for every fragment at once, which put a
    200-300s reasoning request against a gateway that cuts at ~300s -- and made
    a single unparseable response cost the whole model. Here a requirement that
    fails is one requirement's problem.

    **G4 still runs on the composed whole, not per fragment.** Its load-bearing
    checks -- output determination, determinism, no-RTL-import -- are properties
    of the assembled model, and a per-fragment gate could pass every fragment
    while the class they compose into leaves an output free. So the fan-out
    gates each fragment on what is decidable locally (it parses, it names its
    requirement, it writes an output port) and the composed model on the rest.
    """
    from ..fanout import compose as compose_prompt
    from ..fanout import json_block, shared_block
    from ..stage import run_fanout
    from .validate import validate_source

    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except Exception:  # noqa: BLE001
        contract = {}

    base = choose_base(contract)
    shared = shared_block(
        ("system", SYSTEM),
        ("contract_json", contract_json),
        ("dispatch", f"The dispatch method for this design is `{base}` (chosen "
                     f"from the contract, not negotiable). Output ports that "
                     f"must all be written across the whole model: "
                     f"{output_ports(contract)}."),
    )

    def one(req: dict) -> StageResult[RefModelOutput]:
        uid = req.get("uid", "unknown")
        return run_stage(
            stage=f"{STAGE}_{uid}",
            port=port,
            build_prompt=lambda issues, previous: compose_prompt(
                shared, json_block("requirement", req),
                issues=issues, previous=previous),
            parse=parse_response,
            gate=lambda out: _gate_one_fragment(out, req),
            max_repairs=max_repairs,
        )

    results = run_fanout(requirements, one) if fanout else [one(r) for r in requirements]

    merged = RefModelOutput(
        reasoning="; ".join(r.output.reasoning for r in results if r.output.reasoning)[:2000],
        base=base,
        helpers=_merge_helpers(results),
        fragments=[f for r in results for f in r.output.fragments],
        underdetermined=[u for r in results for u in (r.output.underdetermined or [])],
    )
    source = render(merged, contract)
    issues = [i for r in results for i in r.issues]
    issues += validate_source(
        source=source, requirements=requirements, contract=contract,
        expected_base=base, workdir=workdir,
    )
    return StageResult(merged, issues, max(r.rounds for r in results) if results else 0), source


def _merge_helpers(results: list) -> str:
    """Concatenate helper blocks, dropping duplicate definitions.

    Naive concatenation is wrong here in a way the batched call never had. Under
    fan-out, N independent calls each write `helpers` without seeing each other,
    and shared state is exactly what none of them owns individually -- a
    synchroniser, a majority filter, a clock divider. Every call that needs one
    emits it, so a plain join produces the same `def` several times.

    Python tolerates that (last definition wins) which is precisely the problem:
    it is silent, and the surviving definition is whichever call happened to be
    ordered last. Dedupe by the name being bound, keeping the first, and report
    the collisions so a genuine disagreement between two calls is visible rather
    than resolved by ordering.
    """
    import ast as _ast

    seen: set[str] = set()
    kept: list[str] = []
    collisions: list[str] = []
    for r in results:
        block = (getattr(r.output, "helpers", "") or "").strip()
        if not block:
            continue
        try:
            tree = _ast.parse(textwrap.dedent(block))
        except SyntaxError:
            # Not parseable on its own -- keep it and let G4 reject the whole.
            kept.append(block)
            continue
        for node in tree.body:
            name = getattr(node, "name", None)
            if name is None and isinstance(node, _ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, _ast.Name)]
                name = targets[0] if targets else None
            if name is not None and name in seen:
                collisions.append(name)
                continue
            if name is not None:
                seen.add(name)
            kept.append(_ast.get_source_segment(textwrap.dedent(block), node) or "")
    if collisions:
        kept.insert(0, "# helper(s) defined by more than one fragment call, first "
                       f"kept: {sorted(set(collisions))}")
    return "\n\n".join(x for x in kept if x.strip())


def _gate_one_fragment(out: RefModelOutput, req: dict) -> list[Issue]:
    """What is decidable about one fragment on its own.

    Everything else -- determinism, output determination over the whole port
    set, the sandbox check -- is a property of the composed class and is left to
    `validate_source` afterwards. Asserting them per fragment would reject a
    correct fragment for its neighbours' omissions.
    """
    uid = req.get("uid") or ""
    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", f"refmodel.{uid}", out.reasoning)]
    frags = [f for f in out.fragments if f.req_uid == uid]
    if not frags:
        return [
            Issue("error", f"refmodel.{uid}",
                  f"returned no fragment for {uid}", "uncovered")
        ]
    if len(out.fragments) > len(frags):
        extra = sorted({f.req_uid for f in out.fragments} - {uid})
        return [
            Issue("error", f"refmodel.{uid}",
                  f"returned fragments for other requirements too: {extra}",
                  "unwanted")
        ]
    return []
