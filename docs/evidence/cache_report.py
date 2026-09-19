"""Cache hit rate per stage family, from a run's recorded metas.

The run-scale measurement `PortSettings.developer_role_prefix` says is owed. The
probe behind that switch was four filler calls against a nonce prefix; this is
real prompts, real fan-out concurrency, and however many calls the stage took.

Read it per family, never pooled: families have different shared prefixes and a
warm one hides a cold one -- the same reason `cache_stats.family` exists.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dirs", nargs="+")
    a = ap.parse_args()

    for run_dir in a.run_dirs:
        rows: dict[str, list] = collections.defaultdict(list)
        for p in glob.glob(str(Path(run_dir) / "agent_io" / "*_meta.json")):
            m = json.loads(Path(p).read_text())
            u = m.get("usage") or {}
            name = re.sub(r"_r\d+_meta\.json$", "", Path(p).name)
            fam = re.sub(r"_REQ-\d+.*$|_TP-\d+.*$", "", name)
            rows[fam].append((u.get("input_tokens") or 0,
                              (u.get("input_tokens_details") or {}).get(
                                  "cached_tokens") or 0,
                              m.get("served_model") or "?"))
        print(f"\n=== {run_dir} ===")
        print(f"{'stage family':<22}{'model':<16}{'calls':>6}{'input':>11}"
              f"{'cached':>11}{'hit':>7}")
        ti = tc = 0
        for fam, v in sorted(rows.items()):
            i = sum(x[0] for x in v)
            c = sum(x[1] for x in v)
            ti += i
            tc += c
            models = sorted({x[2] for x in v})
            print(f"{fam:<22}{','.join(models)[:15]:<16}{len(v):>6}{i:>11}"
                  f"{c:>11}{100*c/max(i,1):>6.0f}%")
        n = sum(len(v) for v in rows.values())
        print(f"{'TOTAL':<22}{'':<16}{n:>6}{ti:>11}{tc:>11}"
              f"{100*tc/max(ti,1):>6.0f}%")
        print(f"  full-price input tokens: {ti - tc:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
