"""Is the blindness residue reachable by ADMITTING MORE of the corpus?

    python docs/evidence/e6_residue_reach.py <cache.pkl>

Asked once before, under the tier-first chooser, and answered +0. Re-asked here
because the separation-first rule leaves a DIFFERENT residue, so a body that
closed nothing against the old chosen set might close something against the new
one. It does not:

    corpus   admissible bodies not chosen   reach of the residue   supplementary
    run 2                            109                   0.0%   0, blind 9.2%
    run 1                            165                   4.1%   6, blind 5.7 -> 5.5%

On the corpus that sits at the target's edge, not ONE remaining body that is
alive, unrefuted and inside the dissent guard closes a single uncovered cell.
On the other it buys two tenths of a point.

So admission is closed as a blindness lever, and a second check per requirement
is not worth the schema change it needs -- `oracles` is keyed by `req_uid`
throughout, and a supplementary check would have to be carried into the audit
denominator too or it would be a check exempt from the grade.

What is left is a better corpus, and authoring at cells is already at its
pre-registered null: 40 bodies authored at blind cells, `_adopt_cell_bodies`
took 0 and the chooser took 4.
"""
import pickle
import sys
from pathlib import Path

C = pickle.load(Path(sys.argv[1]).open("rb"))
cells, closes, owner = C["cells"], C["closes"], C["owner"]
alive, refuted, dw, pl = set(C["alive"]), C["refuted"], C["dw"], C["pl"]
src, frozen_src, arm = C["src"], C["frozen_src"], C["arm"]
MAXDW = 2.0

per_req = {}
for k in closes:
    if k in alive and owner[k] in frozen_src:
        per_req.setdefault(owner[k], []).append(k)
for u in per_req:
    per_req[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))


def choose():
    covered, out = set(), {}
    order = sorted(per_req, key=lambda u: (-max(len(closes[k]) for k in per_req[u]), u))
    for uid in order:
        spared = [k for k in per_req[uid] if k not in refuted]
        tier = spared or per_req[uid]
        standing = frozen_src.get(uid)
        pick = max(tier, key=lambda k: (bool(closes[k] - covered),
                                        dw[k] <= MAXDW,
                                        len(closes[k] - covered),
                                        pl[k], src[k] == standing))
        covered |= closes[pick]
        out[uid] = pick
    return out, covered


chosen, covered = choose()
residue = cells - len(covered)
print(f"separation-first: {len(chosen)} checks, blind {residue}/{cells} = "
      f"{100*residue/cells:.1f}%")

uncovered = set(range(cells)) - covered
#: Every body not chosen, under the SAME guards the chooser honours.
cand = [k for k in alive if k not in set(chosen.values())
        and k not in refuted and dw[k] <= MAXDW]
reach = set().union(*[closes[k] & uncovered for k in cand]) if cand else set()
print(f"{len(cand)} admissible bodies not chosen; they reach "
      f"{len(reach)}/{residue} = {100*len(reach)/max(1,residue):.1f}% of the residue")

#: And a greedy over them, as supplementary checks.
extra, cov2 = [], set(covered)
pool = list(cand)
while True:
    best, gain = None, 0
    for k in pool:
        g = len(closes[k] - cov2)
        if g > gain:
            best, gain = k, g
    if best is None:
        break
    extra.append(best)
    cov2 |= closes[best]
    pool.remove(best)
print(f"supplementary greedy admits {len(extra)}; blind "
      f"{cells-len(cov2)}/{cells} = {100*(cells-len(cov2))/cells:.1f}%")
if extra:
    from collections import Counter
    print("  by arm:", dict(Counter(arm[k] for k in extra)))
    print("  requirements:", len({owner[k] for k in extra}))
