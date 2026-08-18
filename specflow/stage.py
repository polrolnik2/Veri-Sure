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

import concurrent.futures as _cf
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, TypeVar

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
    build_prompt: Callable[[list[Issue] | None, str | None], str],
    parse: Callable[[str], T],
    gate: Callable[[T], list[Issue]],
    max_repairs: int = 3,
) -> StageResult[T]:
    """Generate, gate, repair; bounded.

    `build_prompt` receives the current issue list and the *immediately
    previous* raw answer -- one version, replaced each round, never accumulated.

    Passing the previous answer is not history-keeping, and the distinction
    matters because the two were conflated here before. The lesson from
    `TBGenerator`/`RTLGenerator` (and LLM4DV's ablation) is that a growing pile
    of failed attempts makes models repeat mistakes; what got dropped alongside
    it was the artifact currently under repair, which is the working document.

    Without it the repair instruction is unexecutable. The prompt says "fix
    exactly these defects" and "do not renumber items the gate did not complain
    about", while the model cannot see what it wrote -- so it must regenerate
    everything and hope the UIDs line up. Measured on or1200_ctrl: requirement
    counts churned 55 -> 61 -> 51 -> 31 across four rounds, which means an issue
    list keyed by UID was being applied to an artifact that no longer existed.
    The feedback was not merely noisy, it was misaddressed.
    """
    issues: list[Issue] = []
    output: T | None = None
    previous: str | None = None

    for round_ in range(max_repairs + 1):
        prompt = build_prompt(issues or None, previous)
        raw = port.complete(stage=stage, round_=round_, prompt=prompt)
        previous = raw
        output = parse(raw)
        issues = gate(output)
        if not has_errors(issues):
            return StageResult(output, issues, round_ + 1)

    assert output is not None  # the loop body always runs at least once
    return StageResult(output, issues, max_repairs + 1)


def previous_answer_block(previous: str | None) -> str:
    """The artifact under repair, verbatim, or nothing on the first round.

    Truncated defensively: a stage whose previous answer is enormous would
    otherwise push the prompt toward the gateway's request ceiling, and a
    repair round that cannot complete is worse than one that sees a little
    less.
    """
    if not previous:
        return ""
    body = previous.strip()
    limit = 60000
    if len(body) > limit:
        body = body[:limit] + "\n... [truncated]"
    return "<previous_answer>\n" + body + "\n</previous_answer>"


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


# ------------------------------------------------------------------- fan-out

#: How many items run at once. Chosen by measurement, not by "more is faster":
#: concurrency buys wall clock and costs cache hits, because parallel calls race
#: the cache write. 24 real units of `i2c_master_bit_ctrl` through the classifier
#: on `gpt-5-mini`:
#:
#:     workers  warmup   wall    hit%   billed input
#:           8       2    72s   88.6%         13,592
#:           4       2    76s   96.8%          3,864
#:           4       6    67s   93.1%          8,216
#:           2       2    85s   92.9%          8,472
#:
#: 8 workers costs **3.5x the input tokens** for 5% less wall clock. The hit-rate
#: ordering among the lower rows is within run-to-run noise -- 2 workers is not
#: better than 4 -- but 8's token cost is well outside it. So: 4.
FANOUT_WORKERS = 4

#: Items run one at a time before the pool opens. A cold prefix is not cached
#: until a response has been written, and concurrent calls race that write:
#: measured, 3 of 8 parallel calls on a cold prefix reported `cached=0`, while
#: the same prefix warmed serially reported 97% from the third call onward. This
#: is the entire reason the fan-out is not just a thread pool.
#:
#: Two, not more. Warm-up calls are serial *and* the first of them is a
#: guaranteed full-price miss, so a longer warm-up costs more than it recovers:
#: 6 warm-up items measured worse on both hit rate and billed tokens than 2.
WARMUP_ITEMS = 2


def run_fanout(
    items: Iterable,
    run_one: Callable[[object], object],
    *,
    workers: int = FANOUT_WORKERS,
    warmup: int = WARMUP_ITEMS,
) -> list:
    """Run `run_one` over `items`, warming the prompt cache before parallelising.

    Results come back in the order of `items`, not completion order, so a caller
    can zip them against their inputs without threading an index through.

    The first `warmup` items run **strictly serially**. They are not a
    throughput sacrifice worth optimising away: without them the pool's first
    wave all miss the cache, which on a 5,000-token shared prefix is the
    difference between paying 3% of it and paying all of it, on every call in
    that wave.

    An exception in one item is raised to the caller rather than swallowed,
    because a stage that silently dropped an item would produce an artifact with
    a hole in it and a gate that reports the hole as the model's fault.
    """
    items = list(items)
    if not items:
        return []

    results: list = [None] * len(items)
    head = items[:max(0, warmup)]
    tail = items[len(head):]

    for i, item in enumerate(head):
        results[i] = run_one(item)

    if tail:
        with _cf.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(run_one, item): len(head) + i
                for i, item in enumerate(tail)
            }
            for fut in _cf.as_completed(futures):
                results[futures[fut]] = fut.result()

    return results
