"""Sweep the dissent guard on GOLDEN-FREE quantities only.

    sweep.py <cache.pkl> [out.json]

`max_dissent_weighted` is `_choose_bodies`'s over-strictness guard: the summed
1 - dissent of every design a body convicts, so at seven designs 2.0 means
"convicts about two of seven". It was measured once, at one value, and never
swept -- and it is what holds the blindness residue: with it off the same
corpus goes 14.6% -> 9.0%.

Blindness and span are computed from the spec-derived population and from
nothing else. The audit column is NOT swept here and must not be: choosing a
threshold by the grade is gating on the control in slow motion.
"""
import json
import pickle
import sys
from pathlib import Path

C = pickle.load(Path(sys.argv[1]).open("rb"))
cells, closes, owner = C["cells"], C["closes"], C["owner"]
alive, refuted, dw, pl = set(C["alive"]), C["refuted"], C["dw"], C["pl"]
src, frozen_src = C["src"], C["frozen_src"]

#: **ONLY THE REQUIREMENTS THE RUN ACTUALLY FROZE.** `_choose_bodies` returns a
#: body for every requirement with a live one, and the stage then drops the
#: rejected and abandoned. A variant that keeps them is scoring a set the
#: pipeline would never ship.
per_req = {}
for k in closes:
    if k in alive and owner[k] in frozen_src:
        per_req.setdefault(owner[k], []).append(k)
for u in per_req:
    per_req[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))


def choose(maxdw):
    covered, out = set(), {}
    order = sorted(per_req,
                   key=lambda u: (-max(len(closes[k]) for k in per_req[u]), u))
    for uid in order:
        spared = [k for k in per_req[uid] if k not in refuted]
        tier = spared or per_req[uid]
        inside = [k for k in tier if dw[k] <= maxdw]
        pool = inside or tier
        standing = frozen_src.get(uid)
        pick = max(pool, key=lambda k: (len(closes[k] - covered), pl[k],
                                        src[k] == standing))
        covered |= closes[pick]
        out[uid] = pick
    return out, cells - len(covered)


print(f"{len(per_req)} requirements with a live body, {cells} cells")
print(f"{'maxdw':>7}  {'checks':>6}  {'blind':>7}  {'rate':>6}  "
      f"{'convicts>2':>10}  {'refuted kept':>12}")
out = {}
for maxdw in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 99.0):
    picks, blind = choose(maxdw)
    over = sum(1 for k in picks.values() if dw[k] > 2.0)
    ref = sum(1 for k in picks.values() if k in refuted)
    print(f"{maxdw:7.1f}  {len(picks):6d}  {blind:7d}  "
          f"{100*blind/cells:5.1f}%  {over:10d}  {ref:12d}")
    out[f"dw{maxdw}"] = {owner[k]: src[k] for k in picks.values()}
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
    print(f"wrote {sys.argv[2]}")


#: **THE GUARD MAY NOT PREFER AN INERT CHECK.** `dissent_weighted` is applied
#: as a TIER: a body inside it beats a body outside it whatever either does.
#: On this corpus four requirements therefore froze a body separating NOTHING
#: over a sibling separating thousands of cells -- REQ-0001 at 0 against 7863.
#: A guard against over-strictness buying its safety with vacuity is the same
#: defect wearing its other sign. Separation first, then the guard, then how
#: much.
def choose_2(maxdw):
    covered, out = set(), {}
    order = sorted(per_req,
                   key=lambda u: (-max(len(closes[k]) for k in per_req[u]), u))
    for uid in order:
        spared = [k for k in per_req[uid] if k not in refuted]
        tier = spared or per_req[uid]
        standing = frozen_src.get(uid)
        pick = max(tier, key=lambda k: (bool(closes[k] - covered),
                                        dw[k] <= maxdw,
                                        len(closes[k] - covered),
                                        pl[k], src[k] == standing))
        covered |= closes[pick]
        out[uid] = pick
    return out, cells - len(covered)


print()
for maxdw in (1.0, 2.0, 3.0, 3.5):
    picks, blind = choose_2(maxdw)
    over = sum(1 for k in picks.values() if dw[k] > 2.0)
    print(f"separates-first, maxdw {maxdw:4.1f}  blind {blind:7d}  "
          f"{100*blind/cells:5.1f}%   convicts>2 {over}")
    out[f"sep_dw{maxdw}"] = {owner[k]: src[k] for k in picks.values()}
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
