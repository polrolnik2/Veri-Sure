"""Does re-normalization change which VARIANT KINDS a requirement needs?

The must-fail leg reuses c1-i2c's 335 variants rather than redrawing them, and
`run_oracle_stage` gives the reason: "A variant is a wrong implementation of ONE
requirement, and the requirement does not change" -- redrawing makes an oracle
convictable as vacuous one round and clear the next.

But the normalized form DOES reach variant generation, in one place that
matters: `kinds_for(requirement, normalized)` decides which kinds exist, by
regex over the requirement text joined with `activation.text` and
`expectation`. If a new normalized form changes that join enough to add or drop
a kind, the reused set is missing a variant that requirement now needs, and its
must-fail leg is quietly weaker.

This checks that empirically instead of trusting the reading. Any requirement
whose kind set moved is named, and those -- and only those -- should be
redrawn.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

SRC = Path("/home/user/runs/c1-i2c")


def _forms(path: Path) -> dict[str, dict]:
    return {n["req_uid"]: n
            for n in json.loads(path.read_text()).get("normalized", [])
            if n.get("req_uid")}


def main() -> int:
    from specflow.refmodel.variants import kinds_for

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n1-i2c")
    a = ap.parse_args()

    reqs = json.loads((SRC / "specflow/requirements.json").read_text())["requirements"]
    old = _forms(SRC / "specflow/normalized.json")
    new = _forms(Path(a.run_dir) / "specflow/normalized.json")
    have = {v.get("req_uid") for v in
            json.loads((SRC / "specflow/variants.json").read_text())}

    moved, gained, same = [], [], 0
    for r in reqs:
        uid = r.get("uid")
        ko = kinds_for(r, old.get(uid))
        kn = kinds_for(r, new.get(uid))
        if ko == kn:
            same += 1
            continue
        (gained if uid not in have else moved).append(
            (uid, sorted(set(kn) - set(ko)), sorted(set(ko) - set(kn))))

    print(f"{len(reqs)} requirements: {same} unchanged, "
          f"{len(moved)} moved, {len(gained)} moved and had no variants anyway")
    for uid, plus, minus in sorted(moved):
        print(f"  {uid}  +{plus or '[]'}  -{minus or '[]'}")
    if not moved:
        print("\nNothing to redraw: every requirement that HAS variants still "
              "needs exactly the kinds it has. Reuse is sound.")
    else:
        json.dump({"redraw": sorted(u for u, _, _ in moved)},
                  open(Path(__file__).parent / "kinds_delta.json", "w"), indent=1)
        print(f"\nredraw these {len(moved)}: "
              + " ".join(sorted(u for u, _, _ in moved)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
