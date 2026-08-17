"""The one bounded agent-plus-gate loop that S1, S2, S3 and the reference model
all run.

Factored out because the loop's *properties* are the design, and each of them is
a defect observed in the existing system:

* **The gate never softens.** GoGoTB's Soft Gate downgrades testpoint
  completeness to a warning as attempts rise, which defeats a completeness gate
  entirely. Here the same verdict is returned on round 4 as on round 0.
* **Exhaustion is a hard failure, never a pass.** `top_agent.py` builds a
  `tb_lint_lesson` (`:679-688`) and a `compile_lesson` (`:879-886`) and drops
  both on the floor, returning `finish(False, "")`. Here the unresolved issue
  list is persisted and the caller is told plainly that nothing was certified.
* **Feedback is the current defect list, not accumulated history.**
  `TBGenerator` and `RTLGenerator` both append to a `failed_trial` list that is
  re-splatted into every later prompt and never truncated
  (`tb_generator.py:597-602` with `:642`). LLM4DV's ablation found that
  accumulating a poisoned history makes models repeat prior mistakes.

Implementing these once means a new stage cannot quietly acquire a softer gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .model_io import ModelPort
from .schema import Issue, has_errors

T = TypeVar("T")


@dataclass(frozen=True)
class StageResult(Generic[T]):
    output: T
    issues: list[Issue]
    rounds: int

    @property
    def ok(self) -> bool:
        return not has_errors(self.issues)


def run_stage(
    *,
    stage: str,
    port: ModelPort,
    build_prompt: Callable[[list[Issue] | None], str],
    parse: Callable[[str], T],
    gate: Callable[[T], list[Issue]],
    max_repairs: int = 3,
) -> StageResult[T]:
    """Generate, gate, repair; bounded.

    `build_prompt` receives the *current* issue list only. It is deliberately
    not given the history: see the module docstring.
    """
    issues: list[Issue] = []
    output: T | None = None

    for round_ in range(max_repairs + 1):
        prompt = build_prompt(issues or None)
        raw = port.complete(stage=stage, round_=round_, prompt=prompt)
        output = parse(raw)
        issues = gate(output)
        if not has_errors(issues):
            return StageResult(output, issues, round_ + 1)

    assert output is not None  # the loop body always runs at least once
    return StageResult(output, issues, max_repairs + 1)


def gate_failures_block(issues: list[Issue]) -> str:
    """The repair instruction appended to a retry prompt.

    Says "fix exactly these" rather than "try again": a scoped repair keeps
    unaffected items stable, and stability is what makes the `@rev` discipline
    meaningful -- wholesale regeneration churns every UID and marks every
    downstream cover outdated.
    """
    from .schema import render_issues

    return (
        "<gate_failures>\n"
        "Your previous answer did not pass the gate. Fix exactly these defects "
        "and reply with the full corrected JSON object. Do not renumber or "
        "restructure items the gate did not complain about.\n\n"
        + render_issues(issues)
        + "</gate_failures>"
    )
