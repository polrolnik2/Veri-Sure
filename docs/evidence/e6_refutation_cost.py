"""Ceiling WITHOUT the refutation preference.

"Convicting all of them is an okay check" -- no spec-derived design is
guaranteed correct, so a check convicting every one of them may simply be
right where they are all wrong. The chooser nonetheless prefers away from such
a body at every tier, and on one corpus that is 53% of it.

Every ceiling measured so far kept that preference on. This drops it.
"""
import pickle
import sys
from pathlib import Path

for tag in sys.argv[1:]:
    C = pickle.load((Path(tag)).open("rb"))
    cells, closes, owner = C["cells"], C["closes"], C["owner"]
    alive, refuted, dw, pl = set(C["alive"]), C["refuted"], C["dw"], C["pl"]
    src, frozen = C["src"], C["frozen_src"]
    per = {}
    for k in closes:
        if k in alive and owner[k] in frozen:
            per.setdefault(owner[k], []).append(k)
    for u in per:
        per[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))

    def run(use_ref, maxdw):
        cov, n = set(), 0
        order = sorted(per, key=lambda u: (-max(len(closes[k]) for k in per[u]), u))
        for uid in order:
            tier = ([k for k in per[uid] if k not in refuted] or per[uid]) \
                if use_ref else per[uid]
            pick = max(tier, key=lambda k: (bool(closes[k] - cov),
                                            dw[k] <= maxdw,
                                            len(closes[k] - cov), pl[k],
                                            src[k] == frozen.get(uid)))
            cov |= closes[pick]
            n += 1 if pick in refuted else 0
        return cells - len(cov), n

    name = Path(tag).stem
    print(f"=== {name}  ({cells} cells) ===")
    for use_ref in (True, False):
        best = min((run(use_ref, m) + (m,) for m in (1.0, 2.0, 3.0, 3.5, 99.0)),
                   key=lambda t: t[0])
        b, nref, m = best
        print(f"  refutation preference {'ON ' if use_ref else 'OFF'}: "
              f"best blind {b}/{cells} = {100*b/cells:5.1f}%  "
              f"(maxdw {m}, {nref} refuted bodies chosen)")
