"""Generate a testcase for an uncovered bin.

**The agent chooses stimulus; it does not write test code.** This is the single
most important constraint in the design, and it is what makes it safe to hand
this tool to the RTL-repair agent -- whose objective is making things pass.

What the tool cannot express is the guarantee:

* checks come from the coverage model, so none can be weakened or omitted;
* expected values come from the frozen reference model, so none can be bent
  toward the current RTL;
* the agent supplies a bounded stimulus list, never Python;
* the bin must already be uncovered in the gate's own report, so targets cannot
  be invented.

Together these make adding a testcase **monotone**: it can add obligations, never
remove one. An agent reaching for this to escape a failing check can only make
its own job harder. The safety is a property of the interface, not a policy the
agent is asked to respect.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .ids import PREFIX_TESTCASE, mint, next_index
from .model_io import ModelPort
from .schema import Issue
from .stage import StageResult, gate_failures_block, run_stage

STAGE = "testcase"


class TestcaseSpec(BaseModel):
    # Not a pytest test class despite the name.
    __test__ = False

    reasoning: str = ""
    targets: list[str] = Field(default_factory=list)
    #: Bounded choice list: one dict of port -> value per step.
    stimulus_steps: list[dict] = Field(default_factory=list)
    notes: str = ""


SYSTEM = """\
You choose stimulus for a coverage bin the testbench has not yet reached.

You do NOT write test code. You do NOT state expected values. You supply input
values only; the harness drives them, records the bin, and compares the outputs
against the reference model on your behalf.

Supply:
  targets         the bin uid(s) this stimulus is meant to reach
  stimulus_steps  a list of steps, each a dict of input port name -> integer
                  value. Every input port must appear in every step.
  notes           one line on why this stimulus should reach the bin

Rules the gate enforces mechanically:
  * every port you name must be an input port in the contract
  * every value must fit its port width
  * at least one step
  * targets must be bins currently reported uncovered

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "targets": ["BIN-0007"],
  "stimulus_steps": [{"a": 1, "b": 1}],
  "notes": "..."
}
"""


def build_prompt(
    *,
    bin_uid: str,
    condition: str,
    testplan_element: dict,
    contract: dict,
    gap_category: str,
    already_reached: list[dict],
    issues: list[Issue] | None = None,
) -> str:
    inputs = [
        {"name": str(p["name"]), "width": int(p.get("width") or 1)}
        for p in (contract.get("io") or [])
        if p.get("dir") == "input"
    ]
    parts = [
        SYSTEM,
        f"<bin uid=\"{bin_uid}\" category=\"{gap_category}\">\n{condition}\n</bin>",
        "<testplan_element>\n"
        + json.dumps(testplan_element, indent=2, ensure_ascii=False)
        + "\n</testplan_element>",
        "<input_ports>\n" + json.dumps(inputs, indent=2) + "\n</input_ports>",
        # What existing testcases already drove. "These were reached, this one
        # was not" is a far more tractable prompt than "write a test for this".
        "<already_driven>\n"
        + json.dumps(already_reached[:32], indent=2)
        + "\n</already_driven>",
    ]
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_response(text: str) -> TestcaseSpec:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return TestcaseSpec.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return TestcaseSpec(reasoning=f"Parse Error: {exc}")


def gate(
    spec: TestcaseSpec, *, bin_uid: str, contract: dict, uncovered: set[str]
) -> list[Issue]:
    if spec.reasoning.startswith("Parse Error: "):
        return [Issue("error", "testcase.response", spec.reasoning)]

    issues: list[Issue] = []
    inputs = {
        str(p["name"]): int(p.get("width") or 1)
        for p in (contract.get("io") or [])
        if p.get("dir") == "input"
    }

    if not spec.stimulus_steps:
        issues.append(Issue("error", "testcase.stimulus_steps", "no steps supplied"))

    for i, step in enumerate(spec.stimulus_steps):
        path = f"testcase.stimulus_steps[{i}]"
        for name, value in step.items():
            if name not in inputs:
                issues.append(
                    Issue("error", path, f"{name!r} is not an input port in the contract")
                )
                continue
            try:
                as_int = int(value)
            except Exception:  # noqa: BLE001
                issues.append(Issue("error", path, f"{name}={value!r} is not an integer"))
                continue
            if not (0 <= as_int < (1 << inputs[name])):
                issues.append(
                    Issue("error", path,
                          f"{name}={as_int} does not fit {inputs[name]} bit(s)")
                )
        missing = set(inputs) - set(step)
        if missing:
            issues.append(
                Issue("error", path, f"does not drive {sorted(missing)}")
            )

    # The tool cannot invent targets: the bin must already be uncovered in the
    # gate's own report. This is what keeps the addition monotone.
    for target in spec.targets or [bin_uid]:
        if target not in uncovered:
            issues.append(
                Issue("error", "testcase.targets",
                      f"{target} is not currently reported uncovered")
            )

    return issues


def run_testcase_agent(
    *,
    bin_uid: str,
    condition: str,
    testplan_element: dict,
    contract: dict,
    gap_category: str,
    already_reached: list[dict],
    uncovered: set[str],
    port: ModelPort,
    max_repairs: int = 2,
) -> StageResult[TestcaseSpec]:
    return run_stage(
        stage=f"{STAGE}_{bin_uid.replace('-', '')}",
        port=port,
        build_prompt=lambda issues: build_prompt(
            bin_uid=bin_uid, condition=condition, testplan_element=testplan_element,
            contract=contract, gap_category=gap_category,
            already_reached=already_reached, issues=issues,
        ),
        parse=parse_response,
        gate=lambda spec: gate(
            spec, bin_uid=bin_uid, contract=contract, uncovered=uncovered
        ),
        max_repairs=max_repairs,
    )


def next_testcase_uid(existing: list[dict]) -> str:
    return mint(PREFIX_TESTCASE, next_index([t.get("uid", "") for t in existing],
                                            PREFIX_TESTCASE))


def append_testcase(
    *, testcases_path: Path, uid: str, targets: list[str], module: str
) -> list[dict]:
    """Record the testcase. Existing entries are never rewritten.

    `frozen` makes the append-only discipline enforceable: an accepted testcase
    is not a thing a later round may quietly amend.
    """
    path = Path(testcases_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing.append({"uid": uid, "targets": targets, "module": module, "frozen": True})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return existing
