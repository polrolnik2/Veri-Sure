"""Whole-set fold with the STAGED testpoints decided against their REAL traces.

The staged ids collided with c1's existing TP-0318..TP-0330, so a global trace
override would hand the wrong evidence to REQ-0109, the one FROZEN oracle that
also names a colliding id. So the override is applied PER ORACLE: only the four
requirements that minted stimulus see the staged traces.
"""
import json, collections, sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.rtl_trace import decide_rtl, load_traces

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
contract = json.load(open(A / "full43/run/contract.json"))
frozen = {o["req_uid"]: o for o in json.load(open("/home/user/runs/c1-i2c/specflow/oracles.json"))["oracles"]}
art = json.load(open(A / "full43/run/specflow/oracles.json"))
reauth = {o["req_uid"]: o for o in art["oracles"]}
over = set(json.load(open(A / "over_strict.json"))["over_strict"])
staged_by_req = {u: set(ids) for u, ids in art["stimulus_added"].items() if ids}

def build(mix): return [RequirementOracle(**{k: o[k] for k in
        ("req_uid", "clause", "source", "tp_uids") if k in o}) for u, o in sorted(mix.items())]

before = dict(frozen)
after = {u: o for u, o in frozen.items() if u not in over}
after.update({u: o for u, o in reauth.items() if u in over})

traces = {a: load_traces(S / d / "suite/results") for a, d in
          (("golden", "rtl_golden2"), ("candidate", "rtl_cand2"))}
staged = load_traces(A / "staged_golden/suite/results")
missing = sorted({t for v in staged_by_req.values() for t in v} - set(staged))

print(f"staged traces recovered: {len(staged)}   never recovered: {missing}")
print("REQ-0124 names TP-0324/TP-0325, so its golden verdict is UNRELIABLE.\n")

print(f"{'':24}{'CONFORMS':>9}{'VIOLATES':>9}{'UNDECIDED':>10}{'coverage':>10}{'pass':>7}")
res = {}
for label, mix in (("BEFORE (frozen 110)", before), ("AFTER  (43 re-authored)", after)):
    for arm in ("golden", "candidate"):
        base = traces[arm]
        d = {x.req_uid: x.ok for x in decide_rtl(build(mix), base, contract)}
        if label.startswith("AFTER") and arm == "golden":
            # per-oracle override: ONLY the requirements that minted stimulus
            fixed = dict(base); fixed.update(staged)
            only = {u: mix[u] for u in staged_by_req if u in mix}
            for x in decide_rtl(build(only), fixed, contract):
                d[x.req_uid] = x.ok
        for u in frozen: d.setdefault(u, None)
        res[(label, arm)] = d
        c = collections.Counter(d.values()); n = len(frozen)
        tag = f"{label:24}" if arm == "golden" else " " * 24
        print(f"{tag}{c[True]:>9}{c[False]:>9}{c[None]:>10}"
              f"{100*(n-c[None])/n:>9.0f}%{100*(n-c[False])/n:>6.0f}%   {arm}")
    print()

print(f"{'set':<24}{'discriminating':>15}{'inverted':>10}{'separation':>12}")
for label in ("BEFORE (frozen 110)", "AFTER  (43 re-authored)"):
    g, c = res[(label, "golden")], res[(label, "candidate")]
    disc = sorted(u for u in g if g[u] is True and c[u] is False)
    inv = sorted(u for u in g if g[u] is False and c[u] is True)
    tainted = sorted(set(disc + inv) & set(staged_by_req))
    print(f"{label:<24}{len(disc):>15}{len(inv):>10}{len(disc)-len(inv):>+12}"
          + (f"   (tainted: {tainted})" if tainted and label.startswith('AFTER') else ""))
