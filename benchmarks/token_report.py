#!/usr/bin/env python3
"""Token and prompt-cache accounting for a run, readable WHILE IT IS RUNNING.

`specflow.cache_stats` writes `cache_report.json` at the end of a run. That is
the right place for the gate, and the wrong place for the question "what is
this costing me right now" -- a run that dies at hour three leaves no report at
all, which is exactly when the number is wanted. This reads the same counts
back out of `agent_io/*_meta.json`, which every call writes as it completes, so
a partial run reports its partial cost instead of nothing.

**Rows are keyed on `prompt_cache_key`, not on the stage name**, and that is
deliberate. The key IS the cache partition the provider matched against, so a
key that accidentally varies per item shows up here as a row of one call rather
than averaging invisibly into a healthy-looking stage family. Keying on the
stage name would report the shape the code intended; keying on the key sent
reports the shape the gateway actually saw.

Warm-up is excluded from the rate and the exclusion is printed per row, the
same discipline `cache_stats` states: a cold prefix misses its first calls by
construction, and folding those in makes a healthy stage look broken.

Usage:  python benchmarks/token_report.py RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

#: Matches `cache_stats.WARMUP_CALLS`. Measured: the first two calls of a cold
#: prefix report cached=0, the third onward 97%.
WARMUP_CALLS = 2

#: Below this, after warm-up, a stage is called out. Matches the stage gate.
MIN_HIT_RATE = 0.5

#: Fewer calls than this and a rate is noise, so no verdict is offered.
MIN_CALLS_FOR_VERDICT = 5


def _usage(meta: dict) -> tuple[int, int, int, int] | None:
    """(input, cached, output, reasoning) from either API shape, or None.

    Chat completions report `prompt_tokens` / `prompt_tokens_details`; the
    Responses API reports `input_tokens` / `input_tokens_details`. Both are
    handled because specflow runs on whichever the gateway routes, and silently
    recording zeros for one of them would look exactly like a dead cache.
    """
    u = meta.get("usage") or {}
    if not u:
        return None
    inp = u.get("input_tokens") or u.get("prompt_tokens") or 0
    det = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
    cached = det.get("cached_tokens") or 0
    out = u.get("output_tokens") or u.get("completion_tokens") or 0
    reasoning = (u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
    return int(inp), int(cached), int(out), int(reasoning)


def collect(run_dir: Path) -> dict[tuple[str, str], list[tuple[int, int, int, int]]]:
    """Group every recorded call by `(prompt_cache_key, served model)`.

    Ordered by mtime so `[:WARMUP_CALLS]` really is the head of the stage and
    not whatever the filesystem happened to list first.
    """
    metas = sorted((run_dir / "agent_io").glob("*_meta.json"),
                   key=lambda p: p.stat().st_mtime)
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for path in metas:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue          # a call still being written is not a defect
        counts = _usage(meta)
        if counts is None:
            continue
        kwargs = meta.get("generate_kwargs") or {}
        key = kwargs.get("prompt_cache_key") or "(no cache key)"
        model = meta.get("served_model") or meta.get("requested_model") or "?"
        groups[(key, model)].append(counts)
    return groups


def render(run_dir: Path) -> str:
    groups = collect(run_dir)
    if not groups:
        return f"{run_dir}: no completed calls recorded yet"

    head = (f"{'prompt_cache_key':<40} {'calls':>6} {'input':>11} {'cached':>11} "
            f"{'hit%':>6} {'output':>10} {'reason':>10}  verdict")
    rows = [str(run_dir), head]
    tot_in = tot_cached = tot_out = tot_reason = tot_calls = 0

    for (key, model), calls in sorted(groups.items()):
        steady = calls[WARMUP_CALLS:]
        steady_in = sum(c[0] for c in steady)
        steady_cached = sum(c[1] for c in steady)
        hit = steady_cached / steady_in if steady_in else 0.0
        n_in = sum(c[0] for c in calls)
        n_cached = sum(c[1] for c in calls)
        n_out = sum(c[2] for c in calls)
        n_reason = sum(c[3] for c in calls)
        verdict = ("too_few_calls" if len(calls) < MIN_CALLS_FOR_VERDICT
                   else "ok" if hit >= MIN_HIT_RATE else "BELOW_THRESHOLD")
        excluded = min(WARMUP_CALLS, len(calls))
        rows.append(
            f"{key:<40} {len(calls):>6} {n_in:>11,} {n_cached:>11,} "
            f"{100 * hit:>5.1f} {n_out:>10,} {n_reason:>10,}  {verdict}"
            f"  (first {excluded} excluded as warm-up)"
        )
        tot_calls += len(calls)
        tot_in += n_in
        tot_cached += n_cached
        tot_out += n_out
        tot_reason += n_reason

    rows.append(
        f"{'TOTAL':<40} {tot_calls:>6} {tot_in:>11,} {tot_cached:>11,} "
        f"{100 * tot_cached / tot_in if tot_in else 0:>5.1f} "
        f"{tot_out:>10,} {tot_reason:>10,}"
    )
    # Billed input is the number that pays the bill, and it is not the input
    # column -- quoting `input` alone overstates the cost by 4x on a warm run.
    rows.append(
        f"\nbilled input (uncached) {tot_in - tot_cached:,}"
        f" · cached {tot_cached:,}"
        f" · output {tot_out:,}"
        f" (reasoning {tot_reason:,} = "
        f"{100 * tot_reason / tot_out if tot_out else 0:.0f}%)"
    )
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    for i, arg in enumerate(argv[1:]):
        if i:
            print()
        print(render(Path(arg)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
