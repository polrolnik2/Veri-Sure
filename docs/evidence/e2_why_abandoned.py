"""Why half the E2 sample was ABANDONED. Zero model calls.

The unbiased E2 run abandoned 20 of 40 gated and 19 of 40 demoted -- half the
sample, and a larger loss than the faithfulness gates it was measuring. The run
froze only `rates()`, so the reasons are not on disk; but both normalize-side
grounds are decided at the site in `_dispositions` where "the normalized form
and the dispositions meet", from the shape alone, so they replay exactly.

Reproduces the driver's own seeded sample so the denominator matches, and
runs over BOTH normalizations so the recovery is visible in one output:
`normalized-direct-only.json` is the pass my driver called, and
`normalized-all.json` is what `resolve_indirect` leaves behind.
"""
import json
import random
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.oracles_stage import _route_declines  # noqa: E402

E3 = "docs/evidence/e3"
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


for norm, label in (("normalized-direct-only.json", "DIRECT PASS ONLY -- what the run actually had"),
                    ("normalized-all.json", "AFTER `resolve_indirect` -- what the pipeline does")):
    have = json.load(open(f"{E3}/{norm}"))
    pool = [r for r in reqs if r["uid"] in have]
    random.Random(20260917).shuffle(pool)
    print(f"\n\n########  {label}")
    for scope, rows in (("THE SAMPLE", pool[:40]), ("THE WHOLE MODULE", pool)):
        counts, conceded = {}, 0
        for r in rows:
            shape = have[r["uid"]]
            g = ground(shape)
            counts[g] = counts.get(g, 0) + 1
            if g == "no observation route found" and (
                    shape.get("unobservable_reason") or "").strip():
                conceded += 1
        print(f"\n{scope} -- {len(rows)} requirements")
        for k in sorted(counts, key=lambda k: -counts[k]):
            print(f"  {counts[k]:4d}  {k}")
        #: THE POINT OF THE WHOLE SCRIPT. `resolve_indirect` consumes exactly
        #: this field. Direct-only leaves 52 of 115 unroutable and every one of
        #: them states a reason; the indirect pass takes that to 5.
        print(f"  of the unroutable, {conceded} STATE a reason in "
              f"`unobservable_reason` -- the indirect pass's input")

    #: WHAT SURVIVES THE INDIRECT PASS IS NOT A FAITHFULNESS ERROR. Four of the
    #: five residual units say in their OWN TEXT that they impose no
    #: requirement -- two bare list-item markers, two headings -- and the fifth
    #: is the port-declaration list. `s1_classify` routes them downstream on
    #: purpose: `unit_kind` is "ADVISORY AND NEVER A FILTER", because the
    #: previous design dropped them at S1 and silently lost 49 of 168 units.
    #: The oracle-stage abandonment IS the intended destination.
    resid = [u for u, n in have.items()
             if ground(n) == "no observation route found"]
    if len(resid) <= 8:
        by = {r["uid"]: r for r in reqs}
        print("\n  the residual, with S1's advisory unit_kind:")
        for u in sorted(resid):
            r = by[u]
            print(f"    {u}  unit_kind={r.get('unit_kind')!r:14} "
                  f"{(r.get('text') or '').strip()[:74]}")
