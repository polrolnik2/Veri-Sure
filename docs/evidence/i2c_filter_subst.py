"""Two assumptions, separated: the filtered VALUE and the registered-output LAG.

Offset 0 substitutes row i's raw pins with row i's derived filtered values --
the pure "the author never had the filter" counterfactual. Offset 1 substitutes
row i's pins with row i-1's derived values, which is what a check comparing a
REGISTERED output against its input needs, because `dout <= #1 sSDA` makes the
new value visible one edge later. If a conviction clears only at offset 1, the
filter was never its cause: the one-cycle latency of a registered output was.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, str(Path(__file__).parent))
from i2c_filter_derive import derive                                        # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide   # noqa: E402
from specflow.refmodel.rtl_trace import rows_from, transactional_view  # noqa: E402

RUN = Path("/home/user/runs/h3-i2c/specflow")
RES = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a"
           "/scratchpad/h3_own2/suite/results")

els = json.loads((RUN / "testplan.json").read_text())["elements"]
by_req = collections.defaultdict(list)
for e in els:
    for c in e.get("covers") or []:
        by_req[c.split("@")[0]].append(e["uid"])

raw = {}
for f in sorted(RES.glob("*.trace.json")):
    t = json.loads(f.read_text())
    raw[t["tp_uid"]] = t


def view(offset):
    out = {}
    for u, t in raw.items():
        if offset is None:
            out[u] = transactional_view(rows_from(t, side="dut"))
            continue
        der = derive(t["edges"])
        sub = json.loads(json.dumps(t))
        for i, row in enumerate(sub["edges"]):
            d = der[max(0, i - offset)]
            row["inputs"]["scl_i"] = d["sSCL"]
            row["inputs"]["sda_i"] = d["sSDA"]
        out[u] = transactional_view(rows_from(sub, side="dut"))
    return out


VIEWS = {"as-written": view(None), "filtered": view(0), "filtered+lag1": view(1)}


def verdict(o, cache):
    worst = None
    for tp in o.tp_uids:
        if tp not in cache:
            continue
        r = decide(o, cache[tp])
        if r.broken:
            continue
        if r.ok is False:
            return "CONVICTS"
        if r.ok is True:
            worst = True
    return "passes" if worst else "silent"


oracles = json.loads((RUN / "oracles.json").read_text())["oracles"]
res = {}
for spec in oracles:
    req = spec["req_uid"]
    o = RequirementOracle(req_uid=req, clause=spec.get("clause", ""),
                          source=spec["source"], tp_uids=by_req.get(req) or [])
    res[req] = {k: verdict(o, v) for k, v in VIEWS.items()}

for name in VIEWS:
    c = sum(1 for v in res.values() if v[name] == "CONVICTS")
    s = sum(1 for v in res.values() if v[name] == "silent")
    print(f"{name:<16} convicts {c:>3}/{len(res)}   silent {s}")

base = [r for r, v in res.items() if v["as-written"] == "CONVICTS"]
print(f"\nof the {len(base)} convictions as written:")
for r in sorted(base):
    print(f"  {r}  filtered={res[r]['filtered']:<9} filtered+lag1={res[r]['filtered+lag1']}")
