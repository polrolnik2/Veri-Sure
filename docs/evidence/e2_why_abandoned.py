"""Why half the E2 sample was ABANDONED. Zero model calls.

The unbiased E2 run abandoned 20 of 40 gated and 19 of 40 demoted -- half the
sample, and a larger loss than the faithfulness gates it was measuring. The run
froze only `rates()`, so the reasons are not on disk; but both normalize-side
grounds are decided at the site in `_dispositions` where "the normalized form
and the dispositions meet", from the shape alone, so they replay exactly.

Reproduces the driver's own seeded sample so the denominator matches.
"""
import json
import random
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.oracles_stage import _route_declines  # noqa: E402

E3 = "docs/evidence/e3"
have = json.load(open(f"{E3}/normalized-all.json"))
reqs = json.load(open(f"{E3}/requirements.json"))
reqs = reqs["requirements"] if isinstance(reqs, dict) else reqs


def ground(shape):
    """The two normalize-side abandonment grounds, in `_dispositions` order."""
    if "observed_via" not in shape:
        #: A form predating the resolution pass. Treating its absence as a
        #: failed attempt would abandon requirements nothing ever asked about.
        return "no observed_via key (pass never ran)"
    if not (shape.get("observable") or []) and not shape.get("observed_via"):
        return "no observation route found"
    routes = shape.get("observed_via") or []
    if routes and all(_route_declines(r) for r in routes):
        return "no discrimination stated"
    return "survives normalize-side"


pool = [r for r in reqs if r["uid"] in have]
random.Random(20260917).shuffle(pool)
sample = pool[:40]

for label, rows in (("THE SAMPLE", sample), ("THE WHOLE MODULE", pool)):
    counts, conceded = {}, 0
    for r in rows:
        shape = have[r["uid"]]
        g = ground(shape)
        counts[g] = counts.get(g, 0) + 1
        if g == "no observation route found" and (
                shape.get("unobservable_reason") or "").strip():
            conceded += 1
    print(f"\n{label} -- {len(rows)} requirements")
    for k in sorted(counts, key=lambda k: -counts[k]):
        print(f"  {counts[k]:4d}  {k}")
    #: THE POINT OF THE WHOLE SCRIPT. `resolve_indirect` consumes exactly this
    #: field, and is recorded recovering 15 of 18 conceding requirements (83%)
    #: with a real port AND route. The run that produced these numbers never
    #: called it.
    print(f"  of the unroutable, {conceded} STATE a reason in "
          f"`unobservable_reason` -- the indirect pass's input")
