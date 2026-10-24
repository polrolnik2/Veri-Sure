"""Write the choice map each refutation placement produces, for scoring.

    e6_placement_maps.py <cache.pkl> <out.json>

Pairs with `e6_score_map.py`, which puts the run's own scorecard over the map
and is the only place the control is read.
"""
import json
import pickle
import sys
from pathlib import Path

C = pickle.load(Path(sys.argv[1]).open("rb"))
per: dict[str, list[str]] = {}
for k in C["closes"]:
    if k in set(C["alive"]) and C["owner"][k] in C["frozen_src"]:
        per.setdefault(C["owner"][k], []).append(k)
for u in per:
    per[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))


def choose(rule: str, maxdw: float = 2.0) -> dict:
    covered, picks = set(), {}
    order = sorted(per, key=lambda u: (-max(len(C["closes"][k]) for k in per[u]), u))
    for uid in order:
        pool = [k for k in per[uid] if k not in C["refuted"]] or per[uid] \
            if rule == "tier" else per[uid]

        def key(k, uid=uid):
            new = C["closes"][k] - covered
            spared, guard = k not in C["refuted"], C["dw"][k] <= maxdw
            head = (bool(new), spared, guard) if rule == "guard" else (bool(new), guard)
            tail = (C["pl"][k], spared) if rule == "tiebreak" else (C["pl"][k],)
            return head + (len(new),) + tail + (C["src"][k] == C["frozen_src"].get(uid),)

        pick = max(pool, key=key)
        covered |= C["closes"][pick]
        picks[uid] = C["src"][pick]
    return picks


out = {r: choose(r) for r in ("tier", "guard", "tiebreak", "none")}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
print(f"wrote {sys.argv[2]}: " + ", ".join(f"{r} {len(m)}" for r, m in out.items()))
