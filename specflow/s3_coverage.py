"""S3: testplan elements -> cover bins and checks, certified by G3.

A bin and a check answer different questions and both are required. The bin asks
*was this scenario reached*; the check asks *did the DUT behave correctly there*.
A testplan element with a bin and no check is coverable and unverifiable --
reached, and proving nothing -- which is the vacuity failure in its purest form.

Note what this stage does NOT decide: the expected value. Checks name a signal
and a comparison; what the signal *should* be always comes from the frozen
reference model. That is what stops a generated check from smuggling in an
oracle that mirrors the design.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .assure import assure_testplan_to_bins, assure_testplan_to_checks
from .ids import PREFIX_BIN, PREFIX_CHECK, mint
from .fanout import compose, json_block, shared_block
from .model_io import ModelPort
from .s2_testplan import borrowed
from .schema import CoverageOutput, Issue
from .stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_fanout,
    run_stage,
)

STAGE = "s3"

SYSTEM = """\
You turn testplan elements into a functional coverage model.

For each testplan element produce BOTH:

  a cover bin  -- was this scenario actually reached?
     uid        BIN-0000, BIN-0001, ... in order, no gaps
     covers     ["TP-0000@1"], pinned by revision
     condition  a plain-language condition over the DUT's ports naming when the
                bin is considered hit, e.g. "a and b both equal 1"

  a check      -- did the DUT behave correctly there?
     uid        CHK-0000, CHK-0001, ... in order, no gaps
     covers     ["TP-0000@1"], pinned by revision
     signals    the output port names this check compares
     expr       what is compared, e.g. "sum matches the reference model"

Rules the gate enforces mechanically:
  * EVERY testplan element must have at least one bin AND at least one check.
    An element with a bin and no check is coverable and unverifiable.
  * Only reference port names the contract declares.
  * Pin every reference to the element's current revision.
  * Do not cover an element that does not declare the need.

Do NOT state expected values. A check names the signal and the comparison; what
the value should be comes from the reference model, never from you. A check that
hard-codes an expected number is an oracle that cannot notice a design change.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "bins":   [{"uid": "BIN-0000", "rev": 1, "covers": ["TP-0000@1"],
              "condition": "..."}],
  "checks": [{"uid": "CHK-0000", "rev": 1, "covers": ["TP-0000@1"],
              "signals": ["sum"], "expr": "..."}]
}
"""

_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

# Words that appear in a natural-language bin condition and are not signals.
# Kept deliberately generous: this check only *warns*, because a false positive
# on prose would block the pipeline over an English word.
_PROSE = {
    "a", "an", "and", "or", "not", "the", "is", "are", "be", "to", "of", "in",
    "on", "at", "all", "any", "both", "each", "equal", "equals", "when", "if",
    "then", "with", "for", "from", "high", "low", "true", "false", "set",
    "cleared", "asserted", "deasserted", "zero", "one", "ones", "value",
    "values", "input", "inputs", "output", "outputs", "bit", "bits", "cycle",
    "cycles", "after", "before", "during", "while", "reset", "clock", "clk",
    "rst", "same", "different", "than", "greater", "less", "maximum", "minimum",
    "max", "min", "overflow", "underflow", "carry", "sum", "result", "state",
    "transition", "signal", "port", "toggles", "changes", "remains", "stays",
    "no", "its", "it", "this", "that", "as", "by", "into", "over", "up", "down",
}


def build_prompt(
    testplan: list[dict], contract_json: str, issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    parts = [
        SYSTEM,
        "<testplan>\n"
        + json.dumps(testplan, indent=2, ensure_ascii=False)
        + "\n</testplan>",
        "<contract_json>\n" + contract_json.rstrip() + "\n</contract_json>",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_response(text: str) -> CoverageOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return CoverageOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return CoverageOutput(reasoning=f"Parse Error: {exc}")


def gate(testplan: list[dict], out: CoverageOutput, contract: dict | None) -> list[Issue]:
    """G3. Both halves of the link, plus signal grounding."""
    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", "s3.response", out.reasoning)]

    bins = [b.model_dump() for b in out.bins]
    checks = [c.model_dump() for c in out.checks]

    if not bins and not checks:
        return [Issue("error", "s3", "no bins and no checks produced")]

    issues = assure_testplan_to_bins(testplan, bins)
    issues += assure_testplan_to_checks(testplan, checks)

    ports = {str(p.get("name")) for p in ((contract or {}).get("io") or []) if p.get("name")}
    outputs = {
        str(p.get("name"))
        for p in ((contract or {}).get("io") or [])
        if p.get("name") and p.get("dir") == "output"
    }

    for c in checks:
        uid = c.get("uid") or "<no-uid>"
        signals = c.get("signals") or []
        if not signals:
            issues.append(
                Issue("error", f"check.{uid}.signals", "names no signal to compare")
            )
        for s in signals:
            if ports and s not in ports:
                issues.append(
                    Issue(
                        "error",
                        f"check.{uid}.signals",
                        f"{s!r} is not a port in the contract (declared: {sorted(ports)})",
                    )
                )
            elif outputs and s not in outputs:
                # Checking an input compares the stimulus against itself.
                issues.append(
                    Issue(
                        "error",
                        f"check.{uid}.signals",
                        f"{s!r} is an input; a check must compare an output",
                    )
                )
        if not (c.get("expr") or "").strip():
            issues.append(Issue("error", f"check.{uid}.expr", "empty"))

    for b in bins:
        uid = b.get("uid") or "<no-uid>"
        cond = (b.get("condition") or "").strip()
        if not cond:
            issues.append(Issue("error", f"bin.{uid}.condition", "empty"))
            continue
        if ports:
            # Warning, not error: the condition is prose, so an unrecognised
            # word is far more likely to be English than a hallucinated signal.
            # Blocking here would stall a node over a synonym.
            unknown = {
                t for t in _IDENT_RE.findall(cond)
                if t not in ports and t.lower() not in _PROSE and not t.isdigit()
            }
            if unknown:
                issues.append(
                    Issue(
                        "warning",
                        f"bin.{uid}.condition",
                        f"mentions {sorted(unknown)}, which are not contract ports",
                    )
                )

    return issues


def run_s3(
    *,
    testplan: list[dict],
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 3,
) -> StageResult[CoverageOutput]:
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except Exception:  # noqa: BLE001
        contract = {}

    return run_stage(
        stage=STAGE,
        port=port,
        build_prompt=lambda issues, previous: build_prompt(
            testplan, contract_json, issues, previous),
        parse=parse_response,
        gate=lambda out: gate(testplan, out, contract),
        max_repairs=max_repairs,
    )


def renumber(out: CoverageOutput) -> CoverageOutput:
    for i, b in enumerate(out.bins):
        b.uid = mint(PREFIX_BIN, i)
    for i, c in enumerate(out.checks):
        c.uid = mint(PREFIX_CHECK, i)
    return out


def write_artifacts(run_dir: Path, result: StageResult[CoverageOutput]) -> Path:
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "coverage_model.json"
    path.write_text(
        json.dumps(result.output.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "s3_gate.json").write_text(
        json.dumps(
            {
                "ok": result.ok,
                "rounds": result.rounds,
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


def shared_prefix(contract_json: str) -> str:
    return shared_block(("system", SYSTEM), ("contract_json", contract_json))


#: Appended to an INDIRECT element's item block, for the same reason S2's is not
#: in the shared prefix: it applies to a minority and would misdirect the rest.
INDIRECT_NOTE = """\
THE REQUIREMENT THIS ELEMENT COVERS IS OBSERVED AT ANOTHER REQUIREMENT'S PORT.

That is what makes a bin writable here at all. A requirement whose own text
names no port can otherwise only produce a bin condition over something
internal -- coverable and unverifiable, which is the vacuity failure in its
purest form. `observed_via` gives you the port; `when` gives you the condition
under which it carries THIS requirement's effect.

BIN. Write the condition over the route's port AND qualified by this
requirement's own activation. The port alone is the other requirement's bin.

CHECK. Name the route's port in `signals`. But if your check's signals and its
`expr` would both be exactly what you would write for `through_req`, you have
duplicated that requirement's check under a different uid and this one verifies
nothing -- qualify it by the activation, the way the bin is qualified.
"""


def build_prompt_one(
    element: dict,
    contract_json: str,
    issues: list[Issue] | None = None,
    previous: str | None = None,
    normalized: dict | None = None,
) -> str:
    item = json_block("testplan_element", element)
    if normalized:
        item += "\n\n" + json_block("normalized", normalized)
        if borrowed(normalized):
            item += "\n\n" + INDIRECT_NOTE
    return compose(
        shared_prefix(contract_json),
        item,
        issues=issues,
        previous=previous,
    )


def indirect_issues(element: dict, out: CoverageOutput,
                    normalized: dict | None) -> list[Issue]:
    """An indirect check has to be qualified, or it is the sibling's check.

    The one failure mode indirection introduces: the element borrows a port, and
    the easiest thing to write about that port is what its OWNER already says
    about it. Such a check passes and fails with the other requirement, so this
    requirement is covered on paper and verified by nothing.

    Detected structurally rather than semantically -- an `expr` naming only the
    route's port, with nothing from this requirement's activation in it. That
    over-approximates toward silence: a check qualified in words the activation
    does not use passes here, which is the right way to be wrong for a gate
    whose alternative is rejecting correct checks.
    """
    routes = borrowed(normalized)
    if not routes:
        return []
    act = ((normalized or {}).get("activation") or {})
    words = {w for w in str(act.get("text") or "").lower().split() if len(w) > 3}
    words |= {str(k).lower() for k in (act.get("inputs") or {})}
    ports = {str(r.get("port")) for r in routes}
    issues: list[Issue] = []
    for check in out.checks:
        expr = str(getattr(check, "expr", "") or "").lower()
        named = {str(x) for x in (getattr(check, "signals", None) or [])}
        if not named or not named <= ports:
            continue
        if words and not any(w in expr for w in words):
            issues.append(Issue(
                "error", f"s3.{element.get('uid')}.{check.uid}.expr",
                f"this check names only {sorted(named)}, which belongs to "
                f"another requirement, and says nothing about when "
                f"{element.get('uid')}'s own activation holds. As written it "
                f"passes and fails with that other requirement, so this "
                f"element is covered on paper and verified by nothing. "
                f"Qualify it by the activation: {act.get('text')!r}"))
    return issues


def run_s3_fanout(
    *,
    testplan: list[dict],
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 3,
    fanout: bool = True,
    #: `req_uid -> normalized form`, looked up through the element's `covers`.
    #: Without it an indirect element's bin can only be written over something
    #: internal -- coverable and unverifiable.
    normalized: dict[str, dict] | None = None,
) -> tuple[CoverageOutput, list[StageResult[CoverageOutput]]]:
    """One small call per testplan element, merged into one coverage model.

    Renumbered once at the end. A uid minted inside the fan-out would depend on
    completion order, and a rerun of identical inputs producing different uids is
    exactly what `--reuse` and the recorded fixtures rely on not happening.
    """
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except json.JSONDecodeError:
        contract = {}

    def _shape(element: dict) -> dict | None:
        from .ids import parse_ref

        for ref in element.get("covers") or []:
            shape = (normalized or {}).get(parse_ref(str(ref)).uid)
            if shape:
                return shape
        return None

    def one(element: dict) -> StageResult[CoverageOutput]:
        shape = _shape(element)
        return run_stage(
            stage=f"{STAGE}_{element.get('uid', 'unknown')}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt_one(
                element, contract_json, issues, previous, normalized=shape),
            parse=parse_response,
            gate=lambda out: gate([element], out, contract)
            + indirect_issues(element, out, shape),
            max_repairs=max_repairs,
        )

    results = run_fanout(testplan, one) if fanout else [one(e) for e in testplan]
    merged = CoverageOutput(
        reasoning="; ".join(r.output.reasoning for r in results if r.output.reasoning)[:2000],
        bins=[b for r in results for b in r.output.bins],
        checks=[c for r in results for c in r.output.checks],
    )
    return renumber(merged), results
