"""Does a TRUE greedy beat the fixed order the chooser picks bodies in?

    e6_greedy_order.py <cache.pkl> [cache.pkl ...]

`_choose_bodies` serves every requirement, so the order does not decide WHICH
requirements get a check -- it decides which BODY each one gets, through the
`covered` set the marginal-gain term is read against. The order is computed
once, from each requirement's best body in ABSOLUTE terms:

    order = sorted(per_req, key=lambda u: (-max(len(closes[k]) ...), u))

A greedy max-coverage picks, at every step, the pair whose MARGINAL gain is
largest -- which is the form the (1 - 1/e) guarantee is stated for. This
measures the difference on real corpora. Blindness only: every quantity here
comes from the spec-derived population and the control is not read.
"""
import pickle
import sys
from pathlib import Path


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


def key(k, covered, C, uid, maxdw):
    return (bool(C["closes"][k] - covered), C["dw"][k] <= maxdw,
            len(C["closes"][k] - covered), C["pl"][k],
            k not in C["refuted"], C["src"][k] == C["frozen_src"].get(uid))


def fixed(C, per, maxdw):
    """The shipped order: by each requirement's best body, absolutely."""
    covered = set()
    order = sorted(per, key=lambda u: (-max(len(C["closes"][k]) for k in per[u]), u))
    for uid in order:
        covered |= C["closes"][max(per[uid], key=lambda k: key(k, covered, C, uid, maxdw))]
    return C["cells"] - len(covered)


def greedy(C, per, maxdw):
    """True greedy: at each step the requirement whose best body adds most."""
    covered, left = set(), dict(per)
    while left:
        best = {u: max(ks, key=lambda k: key(k, covered, C, u, maxdw))
                for u, ks in left.items()}
        uid = max(sorted(best), key=lambda u: len(C["closes"][best[u]] - covered))
        covered |= C["closes"][best[uid]]
        del left[uid]
    return C["cells"] - len(covered)


for tag in sys.argv[1:]:
    C, per = load(tag)
    print(f"=== {Path(tag).stem}  {len(per)} requirements, {C['cells']} cells ===")
    for maxdw in (1.0, 2.0, 3.0, 99.0):
        f, g = fixed(C, per, maxdw), greedy(C, per, maxdw)
        print(f"  maxdw {maxdw:5.1f}   fixed order {f:6d} = {100*f/C['cells']:5.2f}%"
              f"   greedy {g:6d} = {100*g/C['cells']:5.2f}%", flush=True)
