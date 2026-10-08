#!/usr/bin/env python3
"""Per-stage prompt-cache accounting for a live or finished run.

Reads the call records a run already writes (`agent_io/*_meta.json`) rather than
instrumenting anything, so it can be pointed at a run in progress and at one
that finished months ago.

WHY THE WARM-UP SPLIT IS SHOWN SEPARATELY. A fanned-out stage misses on its
first calls by construction -- the prefix is cold -- so folding those into one
rate makes a healthy stage look broken and, worse, hides the difference between
"still warming" and "never warmed". `cache_stats` excludes them from its gate for
the same reason; this prints both numbers so the reader can see which case they
are in rather than being told.

THE KEY IS NESTED. `usage.input_tokens_details.cached_tokens`, not a top-level
`cached_tokens`. Reading the top level returns nothing and reports 0% on a run
that was in fact 74% cached -- a mistake already made once on this project, and
the reason `_cached` below is written as a lookup that fails loudly rather than
a `.get` chain that returns a plausible zero.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from specflow.cache_stats import family  # noqa: E402


def _cached(usage: dict) -> tuple[int, int]:
    """`(cached, cache_write)`. Raises if the shape is not what it should be."""
    details = usage["input_tokens_details"]
    return int(details.get("cached_tokens") or 0), int(
        details.get("cache_write_tokens") or 0)


def collect(run_dir: Path) -> dict:
    by_family: dict[tuple[str, str], list[dict]] = defaultdict(list)
    bad = 0
    for meta in sorted((run_dir / "agent_io").glob("*_meta.json")):
        try:
            blob = json.loads(meta.read_text(encoding="utf-8"))
            usage = blob["usage"]
            cached, written = _cached(usage)
        except Exception:  # noqa: BLE001 -- a malformed record is counted, not fatal
            bad += 1
            continue
        # `<family>_<item>_r<round>_meta.json` -- drop the round and the suffix.
        stem = meta.name[: -len("_meta.json")]
        stage = stem.rsplit("_r", 1)[0]
        by_family[(family(stage), blob.get("served_model") or "?")].append({
            "input": int(usage.get("input_tokens") or 0),
            "cached": cached, "written": written,
            "output": int(usage.get("output_tokens") or 0),
        })
    return {"by_family": by_family, "unreadable": bad}


def report(run_dir: Path) -> str:
    got = collect(run_dir)
    rows = []
    tot_in = tot_cached = tot_out = 0
    for (fam, model), calls in sorted(got["by_family"].items()):
        # First call of a family is cold by construction; report the rest apart.
        warm = calls[1:]
        w_in = sum(c["input"] for c in warm)
        w_cached = sum(c["cached"] for c in warm)
        a_in = sum(c["input"] for c in calls)
        a_cached = sum(c["cached"] for c in calls)
        tot_in += a_in
        tot_cached += a_cached
        tot_out += sum(c["output"] for c in calls)
        rows.append((
            fam, model, len(calls),
            f"{a_cached / a_in * 100:5.1f}%" if a_in else "    -",
            f"{w_cached / w_in * 100:5.1f}%" if w_in else "    -",
            f"{a_in / 1000:8.1f}k", f"{a_cached / 1000:8.1f}k",
        ))
    width = max([len(r[0]) for r in rows] + [6])
    out = [f"{'stage':<{width}}  {'model':<12} {'calls':>5} {'cached':>7} "
           f"{'warm':>7} {'input':>9} {'of which':>9}"]
    out.append("-" * (width + 55))
    for fam, model, n, rate, warm, tin, tcached in rows:
        out.append(f"{fam:<{width}}  {model:<12} {n:>5} {rate:>7} {warm:>7} "
                   f"{tin:>9} {tcached:>9}")
    out.append("-" * (width + 55))
    rate = (tot_cached / tot_in * 100) if tot_in else 0.0
    out.append(f"{'TOTAL':<{width}}  {'':<12} {sum(r[2] for r in rows):>5} "
               f"{rate:6.1f}% {'':>7} {tot_in / 1000:8.1f}k "
               f"{tot_cached / 1000:8.1f}k")
    out.append(f"output tokens: {tot_out / 1000:.1f}k")
    if got["unreadable"]:
        out.append(f"WARNING: {got['unreadable']} unreadable call record(s) -- "
                   f"not counted, and a silent drop here would understate cost")
    return "\n".join(out)


if __name__ == "__main__":
    print(report(Path(sys.argv[1] if len(sys.argv) > 1 else ".")))
