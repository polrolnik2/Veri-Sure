"""S2: requirements -> testplan elements, certified by G2.

A testplan element is GoGoTB's testpoint tuple made explicit: stimulus, expected
response, check method, dimension. The seven dimensions are theirs; the UID and
`covers` link are not, and they are what makes the completeness question
decidable. GoGoTB anchors each bin to a *named* specification behaviour, which
is bin -> clause; nothing there establishes clause -> bin, so its coverage
denominator is the model's own testpoint list.
"""

from __future__ import annotations

import json
from pathlib import Path

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .assure import assure_requirements_to_testplan
from .ids import PREFIX_TESTPLAN, mint
from .fanout import compose, json_block, shared_block
from .model_io import ModelPort
from .schema import Issue, TestplanOutput
from .stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_fanout,
    run_stage,
)

STAGE = "s2"

DIMENSIONS = """\
  D1_data_boundary   min/max/zero/all-ones, width edges, overflow points
  D2_control_flow    mode selection, enables, muxing, priority
  D3_timing          latency, throughput, back-to-back, stalls
  D4_fsm_transition  each state entered, each legal edge taken
  D5_protocol        handshake sequences, ordering, framing
  D6_error_injection illegal or out-of-range input, reset mid-operation
  D7_microarch       pipelining, forwarding, internal resource contention"""

SYSTEM = f"""\
You turn requirements into a verification testplan.

A testplan element describes ONE scenario that exercises a requirement, as a
tuple: stimulus, expected response, check method, dimension.

For each element supply:
  uid                TP-0000, TP-0001, ... in order, no gaps
  covers             the requirement(s) it exercises, pinned by revision, e.g.
                     ["REQ-0003@1"]. Pin every reference.
  dimension          one of the seven below
  stimulus           what to drive, concretely
  expected_response  what the DUT must then do, in terms of observable outputs
  check_method       how the comparison is made
  needs              ["bin", "check"]

The seven dimensions:
{DIMENSIONS}

Rules the gate enforces mechanically:
  * EVERY requirement that declares needs=["testplan"] must be covered by at
    least one element. An uncovered requirement is a hard error.
  * Do NOT cover a requirement that does not declare needs=["testplan"]. That is
    unrequested coverage and is also a hard error -- it inflates the denominator
    without verifying anything.
  * Pin every reference to the requirement's current revision.

Prefer several small elements over one broad one. A requirement with a corner
case usually needs at least two: the ordinary path and the corner.

Reply with ONE JSON object and nothing else:

{{
  "reasoning": "...",
  "elements": [
    {{"uid": "TP-0000", "rev": 1, "covers": ["REQ-0000@1"],
      "dimension": "D1_data_boundary", "stimulus": "...",
      "expected_response": "...", "check_method": "...",
      "needs": ["bin", "check"]}}
  ]
}}
"""

_VALID_DIMENSIONS = {
    "D1_data_boundary", "D2_control_flow", "D3_timing", "D4_fsm_transition",
    "D5_protocol", "D6_error_injection", "D7_microarch",
}


def build_prompt(
    requirements: list[dict], contract_json: str, issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    parts = [
        SYSTEM,
        "<requirements>\n"
        + json.dumps(requirements, indent=2, ensure_ascii=False)
        + "\n</requirements>",
        "<contract_json>\n" + contract_json.rstrip() + "\n</contract_json>",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_response(text: str) -> TestplanOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return TestplanOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return TestplanOutput(reasoning=f"Parse Error: {exc}")


def gate(requirements: list[dict], out: TestplanOutput) -> list[Issue]:
    """G2: the link, plus the structural fields a testpoint needs to be usable."""
    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", "s2.response", out.reasoning)]

    elements = [e.model_dump() for e in out.elements]
    if not elements:
        return [Issue("error", "s2.elements", "no testplan elements produced")]

    issues = assure_requirements_to_testplan(requirements, elements)

    for e in elements:
        uid = e.get("uid") or "<no-uid>"
        if e.get("dimension") not in _VALID_DIMENSIONS:
            issues.append(
                Issue(
                    "error",
                    f"testplan.{uid}.dimension",
                    f"{e.get('dimension')!r} is not one of {sorted(_VALID_DIMENSIONS)}",
                )
            )
        # An element missing any of these is not a testpoint; it is a wish.
        # Each corresponds to a component the renderer must emit, so an empty
        # field becomes a testcase that drives nothing or checks nothing.
        for field in ("stimulus", "expected_response", "check_method"):
            if not (e.get(field) or "").strip():
                issues.append(
                    Issue("error", f"testplan.{uid}.{field}", "empty")
                )

    return issues


def run_s2(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 3,
) -> StageResult[TestplanOutput]:
    return run_stage(
        stage=STAGE,
        port=port,
        build_prompt=lambda issues, previous: build_prompt(
            requirements, contract_json, issues, previous),
        parse=parse_response,
        gate=lambda out: gate(requirements, out),
        max_repairs=max_repairs,
    )


def renumber(out: TestplanOutput) -> TestplanOutput:
    for i, e in enumerate(out.elements):
        e.uid = mint(PREFIX_TESTPLAN, i)
    return out


def write_artifacts(run_dir: Path, result: StageResult[TestplanOutput]) -> Path:
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "testplan.json"
    path.write_text(
        json.dumps(result.output.model_dump(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "s2_gate.json").write_text(
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

#: Ends the shared block for the per-requirement path. Everything before it is
#: byte-identical across every requirement of one node; see `specflow/fanout.py`.
_SHARED_SECTIONS = "system", "contract_json"


def shared_prefix(contract_json: str) -> str:
    return shared_block(("system", SYSTEM), ("contract_json", contract_json))


#: Appended to an INDIRECT requirement's item block. Not in the shared prefix:
#: it applies to a minority of requirements and putting it there would tell
#: every other one to plan a contrast it has no `shows` for.
INDIRECT_NOTE = """\
THIS REQUIREMENT IS OBSERVED AT ANOTHER REQUIREMENT'S PORT.

`observed_via` says which port, through which requirement, and -- in `shows` --
what that port does when this requirement holds AND when it does not.

PLAN BOTH CASES. The observation is a DIFFERENCE at a port this requirement does
not own, so a single scenario at that port is satisfied by the port's ordinary
behaviour: an element covering only the holding case would be discharged by a
design with none of this requirement's behaviour in it. Give the contrasting
scenario as well, as its own element, and say in `expected_response` which side
of `shows` each one is.

`activated_via`, when present, is the sequence that reaches the state this
requirement applies in. `stimulus` has to drive that sequence, not the state:
"issue START, then hold" is drivable, "be in START_B" is not.
"""


def build_prompt_one(
    requirement: dict,
    contract_json: str,
    issues: list[Issue] | None = None,
    previous: str | None = None,
    normalized: dict | None = None,
) -> str:
    item = json_block("requirement", requirement)
    if normalized:
        item += "\n\n" + json_block("normalized", normalized)
        if normalized.get("observed_via") or normalized.get("activated_via"):
            item += "\n\n" + INDIRECT_NOTE
    return compose(
        shared_prefix(contract_json),
        item,
        issues=issues,
        previous=previous,
    )


def gate_one(requirement: dict, out: TestplanOutput) -> list[Issue]:
    """G2, scoped to the one requirement this call was given.

    The call is 1:1 on the way in -- one requirement, nothing else -- and 1:N on
    the way out, because one requirement legitimately needs several testpoints: a
    boundary case, a timing case, an error-injection case. Measured on
    `i2c_master_bit_ctrl`, 72 requirements produced 164 elements.

    **The uncovered-requirement check still fires**, contrary to an earlier
    version of this docstring which claimed the fan-out made it vacuous. It does
    not: a call that returns nothing fails on "no testplan elements produced",
    and a call that answers for some other requirement fails as both `orphaned`
    and `uncovered`. What the fan-out changes is narrower and runs the other way
    -- "requirement 47 was silently dropped from a batch of 72" is no longer a
    thing that can happen quietly, because it becomes a call that fails its own
    gate rather than an item missing from a list.

    The rest still bites too: an element with no dimension, no stimulus, no
    expected response or no check method is not a testpoint. Over-splitting
    upstream shows up as exactly that -- a requirement too small to have an
    expected response cannot be given one -- which is half of the opposing
    pressure that replaces a span-length threshold. The other half is G4's
    writes-no-output-port check.
    """
    return gate([requirement], out)


def run_s2_fanout(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 3,
    fanout: bool = True,
    #: `req_uid -> normalized form`. Carries `observed_via` / `activated_via`,
    #: without which an indirect requirement is planned as though its own text
    #: named the port -- one scenario, no contrast, and nothing to discriminate.
    normalized: dict[str, dict] | None = None,
) -> tuple[TestplanOutput, list[StageResult[TestplanOutput]]]:
    """One small call per requirement, merged into one testplan.

    Elements are renumbered once at the end rather than per call: a uid minted
    inside a fan-out would depend on completion order, and results that look
    different on a rerun of identical inputs are the thing `--reuse` and the
    fixtures both depend on not happening.
    """
    def one(req: dict) -> StageResult[TestplanOutput]:
        return run_stage(
            stage=f"{STAGE}_{req.get('uid', 'unknown')}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt_one(
                req, contract_json, issues, previous,
                normalized=(normalized or {}).get(str(req.get("uid") or ""))),
            parse=parse_response,
            gate=lambda out: gate_one(req, out),
            max_repairs=max_repairs,
        )

    results = run_fanout(requirements, one) if fanout else [one(r) for r in requirements]
    merged = TestplanOutput(
        reasoning="; ".join(r.output.reasoning for r in results if r.output.reasoning)[:2000],
        elements=[e for r in results for e in r.output.elements],
    )
    return renumber(merged), results
