"""WHERE the refutation term belongs in the chooser's key. Zero model calls.

    e6_refutation_placement.py <cache.pkl> [cache.pkl ...]

The term has been in three places on this branch and each is a different rule:

  tier      `tier = spared or per_req[uid]` -- a refuted body loses to ANY
            body the population spares, whatever either one separates.
  guard     beside `dissent_weighted <= maxdw`, ABOVE marginal separation --
            "separation first, then the guards, then more separation", the
            ordering this tree already moved the dissent guard to.
  tiebreak  below `placement` -- it only decides between bodies that separate
            identically.
  none      absent.

Blindness only. Every quantity comes from the spec-derived population; the
control is not read here and the placement must not be chosen by it.
"""
import pickle
import sys
from pathlib import Path

RULES = ("tier", "guard", "tiebreak", "none")


def load(tag):
    C = pickle.load(Path(tag).open("rb"))
    per = {}
    alive, closes, owner = set(C["alive"]), C["closes"], C["owner"]
    for k in closes:
        if k in alive and owner[k] in C["frozen_src"]:
            per.setdefault(owner[k], []).append(k)
    for u in per:
        per[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))
    return C, per


def choose(C, per, rule, maxdw):
    covered, picks = set(), {}
    order = sorted(per, key=lambda u: (-max(len(C["closes"][k]) for k in per[u]), u))
    for uid in order:
        pool = per[uid]
        if rule == "tier":
            pool = [k for k in pool if k not in C["refuted"]] or pool

        def key(k, uid=uid):
            new = C["closes"][k] - covered
            spared = k not in C["refuted"]
            guard = C["dw"][k] <= maxdw
            head = (bool(new), spared, guard) if rule == "guard" else (bool(new), guard)
            tail = (C["pl"][k], spared) if rule == "tiebreak" else (C["pl"][k],)
            return head + (len(new),) + tail + (C["src"][k] == C["frozen_src"].get(uid),)

        pick = max(pool, key=key)
        covered |= C["closes"][pick]
        picks[uid] = pick
    return picks, C["cells"] - len(covered)


for tag in sys.argv[1:]:
    C, per = load(tag)
    print(f"=== {Path(tag).stem}  {len(per)} requirements, {C['cells']} cells ===")
    print(f"  {'rule':>9}  {'blind':>7}  {'rate':>7}  {'refuted kept':>12}")
    for rule in RULES:
        picks, blind = choose(C, per, rule, 2.0)
        ref = sum(1 for k in picks.values() if k in C["refuted"])
        print(f"  {rule:>9}  {blind:7d}  {100*blind/C['cells']:6.2f}%  {ref:12d}",
              flush=True)
