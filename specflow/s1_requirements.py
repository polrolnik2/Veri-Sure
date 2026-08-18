"""S1: spec text -> atomic requirements, certified by G1.

The agent decomposes; a script decides whether the decomposition covered the
spec. That split is the whole design: an LLM must never certify that its own
output was complete, because the failure it would have to notice is the one it
just made.

S1 reads the spec from the `spec` parameter that `TopAgent.run` already receives
(`eda_agent/top_agent.py:963-973`), not from the truncated contract. That matters
because `contract_only=True` reduces the contract to at most six
`functional_summary` bullets before it reaches any downstream agent -- so the
spec text exists at the node and is thrown away, which is precisely why a
completeness argument is impossible today.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .assure import check_spec_attribution
from .ids import PREFIX_REQUIREMENT, mint
from .model_io import ModelPort
from .stage import previous_answer_block
from .schema import Issue, RequirementsOutput, has_errors, render_issues

STAGE = "s1"

SYSTEM = """\
You decompose a hardware specification into atomic requirements.

A requirement is ONE testable statement about observable behaviour -- one thing
that could be independently right or wrong, and that will become exactly one
method in a Python reference model. "The output is the sum of the inputs" is one
requirement; "the output is the sum, saturating on overflow" is two.

For each requirement you MUST supply:
  uid          REQ-0000, REQ-0001, ... in order, no gaps
  text         the requirement, one sentence, in your own words
  spec_spans   one or more VERBATIM quotations of the specification, each with
               the exact character offsets it occupies in the spec. The quote
               must be character-identical to spec[start:end]. This is checked.
  ports        the port names this requirement constrains, exactly as the
               contract declares them
  needs        ["testplan", "refmodel"] unless the requirement is untestable

EVERY meaningful sentence of the specification must be claimed by at least one
requirement's spec_spans. Unclaimed spec text is a hard error -- it means a
behaviour nobody will ever verify. Interface declarations and port lists count
as claimable text: attribute them to the requirements they constrain.

If the specification does not determine some behaviour -- it is silent or
ambiguous about a corner -- do NOT invent an answer. Record it in
`underdetermined` with the question you would ask. An honest "the spec does not
say" is worth more than a confident guess, and the pipeline has somewhere to put
it; a guess becomes a wrong oracle that fails correct designs.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "requirements": [
    {"uid": "REQ-0000", "text": "...", "rev": 1,
     "spec_spans": [{"start": 0, "end": 41, "quote": "..."}],
     "ports": ["a", "b", "sum"], "needs": ["testplan", "refmodel"]}
  ],
  "underdetermined": [{"req_uid": "REQ-0003", "question": "..."}]
}
"""


def normalize_spec(spec: str) -> str:
    """The single definition of "the specification text".

    The prompt and the gate MUST see byte-identical text, because G1 checks
    character offsets into it. The first version of this module put
    `spec.rstrip()` in the prompt while checking offsets against the raw `spec`,
    and stated `len(spec)` as the length -- so for every VerilogEval prompt,
    which begins with a blank line, all offsets were shifted by one and the
    stated length disagreed with the text supplied. Every span failed
    verification for a reason that had nothing to do with the decomposition.

    Normalising once, here, and using the result for the prompt, the stated
    length and the gate is what makes that class of bug impossible rather than
    merely fixed.
    """
    return spec.replace("\r\n", "\n").strip()


def build_prompt(spec: str, contract_json: str, issues: list[Issue] | None = None,
                 previous: str | None = None) -> str:
    """Compose the S1 prompt.

    On a repair round the *current* defect list is appended -- not an
    accumulated history. `TBGenerator` and `RTLGenerator` both append to a
    `failed_trial` list that is re-splatted into every later prompt and never
    truncated (`tb_generator.py:597-602` with `:642`); LLM4DV's ablation found
    that accumulating a poisoned history makes models repeat prior mistakes.
    """
    spec = normalize_spec(spec)
    parts = [
        SYSTEM,
        "<specification>\n" + spec + "\n</specification>",
        "<contract_json>\n" + contract_json.rstrip() + "\n</contract_json>",
        # Offsets are what G1 verifies, so state the convention explicitly and
        # name the exact boundaries: the text begins immediately after the
        # newline following <specification> and ends immediately before the
        # newline preceding </specification>.
        f"The specification is exactly {len(spec)} characters: it starts at "
        f"{spec[:24]!r} and ends at {spec[-24:]!r}. Offsets are 0-based into "
        "that exact text, including newlines, excluding the tags.",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(
            "<gate_failures>\n"
            "Your previous answer did not pass the completeness gate. Fix exactly "
            "these defects and reply with the full corrected JSON object.\n\n"
            + render_issues(issues)
            + "</gate_failures>"
        )
    return "\n\n".join(parts)


def parse_response(text: str) -> RequirementsOutput:
    """Never raises. A parse failure returns a shaped object whose `reasoning`
    starts with "Parse Error: ", matching the house convention
    (`eda_agent/asserter_agent.py:149-155`)."""
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return RequirementsOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return RequirementsOutput(reasoning=f"Parse Error: {exc}")


def gate(spec: str, out: RequirementsOutput, contract: dict | None) -> list[Issue]:
    """G1. Pure code; no model involvement.

    Normalises the spec by the same rule `build_prompt` uses, so the offsets
    checked here are offsets into the text the model was actually shown.
    """
    spec = normalize_spec(spec)
    reqs = [r.model_dump() for r in out.requirements]
    issues: list[Issue] = []

    if out.reasoning.startswith("Parse Error: "):
        issues.append(Issue("error", "s1.response", out.reasoning))
        return issues

    if not reqs:
        issues.append(Issue("error", "s1.requirements", "no requirements produced"))
        return issues

    seen: set[str] = set()
    for i, r in enumerate(reqs):
        uid = r.get("uid") or ""
        path = f"requirement[{i}]"
        if not uid:
            issues.append(Issue("error", path, "missing uid"))
        elif uid in seen:
            issues.append(Issue("error", f"requirement.{uid}", "duplicate uid"))
        seen.add(uid)
        if not (r.get("text") or "").strip():
            issues.append(Issue("error", f"requirement.{uid}", "empty text"))

    issues.extend(check_spec_attribution(spec, reqs))

    # Contract cross-check. A requirement naming a port the contract does not
    # declare means one of the two artifacts is wrong, and it is far cheaper to
    # learn that here than from a testbench that will not elaborate.
    if contract:
        declared = {
            str(p.get("name")) for p in (contract.get("io") or []) if p.get("name")
        }
        if declared:
            for r in reqs:
                for port in r.get("ports") or []:
                    if port not in declared:
                        issues.append(
                            Issue(
                                "error",
                                f"requirement.{r.get('uid')}.ports",
                                f"{port!r} is not a port in the contract "
                                f"(declared: {sorted(declared)})",
                            )
                        )

    return issues


@dataclass(frozen=True)
class S1Result:
    output: RequirementsOutput
    issues: list[Issue]
    rounds: int

    @property
    def ok(self) -> bool:
        return not has_errors(self.issues)


def run_s1(
    *,
    spec: str,
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 3,
) -> S1Result:
    """Agent, gate, bounded repair. Exhaustion is a hard failure, never a pass.

    The gate does not soften on retry. GoGoTB's Soft Gate downgrades testpoint
    completeness to a warning as attempts rise, which defeats a completeness
    gate entirely.
    """
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except Exception:  # noqa: BLE001
        contract = {}

    issues: list[Issue] = []
    out = RequirementsOutput()
    # One previous answer, replaced each round -- never an accumulated history.
    previous: str | None = None

    for round_ in range(max_repairs + 1):
        prompt = build_prompt(spec, contract_json, issues or None, previous)
        raw = port.complete(stage=STAGE, round_=round_, prompt=prompt)
        previous = raw
        out = parse_response(raw)
        issues = gate(spec, out, contract)
        if not has_errors(issues):
            return S1Result(out, issues, round_ + 1)

    return S1Result(out, issues, max_repairs + 1)


def renumber(out: RequirementsOutput) -> RequirementsOutput:
    """Force contiguous, canonical UIDs.

    The agent is asked for `REQ-0000` upward with no gaps and will sometimes
    drift. Renumbering here rather than rejecting keeps a good decomposition
    from being thrown away over clerical numbering -- and it happens before
    anything downstream pins a reference, so no `@rev` link is invalidated.
    """
    remap = {
        r.uid: mint(PREFIX_REQUIREMENT, i) for i, r in enumerate(out.requirements)
    }
    for r in out.requirements:
        r.uid = remap[r.uid]
    for u in out.underdetermined:
        u.req_uid = remap.get(u.req_uid, u.req_uid)
    return out


def write_artifacts(run_dir: Path, result: S1Result) -> Path:
    """Persist under the house report envelope."""
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "requirements.json"
    path.write_text(
        json.dumps(result.output.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "s1_gate.json").write_text(
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
