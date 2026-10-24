"""The 23 the fixes can reach, re-authored with `aborts_on` and NOT_ASSERTABLE
in place -- against the SAME normalization the baseline got.

Three arms over c1-i2c's frozen 110, so each column isolates one thing:

  FROZEN        the original 110.
  FULL43        the 43 over-strict replaced by the earlier re-authoring, which
                ran BEFORE any of the three additions existed.
  +TOOLS        FULL43 with only the 23 reachable requirements overwritten by
                the new run. Everything else is byte-identical to FULL43, so a
                difference between these two columns is the tools and nothing
                else.

A requirement whose check was REJECTED contributes NOTHING -- the honest
representation of a lost check, and the reason coverage is reported beside the
pass rate rather than under it.
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle      # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
contract = json.load(open(A / "full43/run/contract.json"))
frozen = {o["req_uid"]: o for o in
          json.load(open("/home/user/runs/c1-i2c/specflow/oracles.json"))["oracles"]}
full43 = {o["req_uid"]: o for o in
          json.load(open(A / "full43/run/specflow/oracles.json"))["oracles"]}
new = {o["req_uid"]: o for o in
       json.load(open(A / "affected23/run/specflow/oracles.json"))["oracles"]}
over = set(json.load(open(A / "over_strict.json"))["over_strict"])
aff = json.load(open(A / "affected.json"))
sub, movable, controls = set(aff["over_strict"]), set(aff["movable"]), set(aff["controls"])

disp43 = json.load(open(A / "full43/run/specflow/oracles.json")).get("dispositions") or {}
dispN = json.load(open(A / "affected23/run/specflow/oracles.json")).get("dispositions") or {}


def build(mix):
    return [RequirementOracle(**{k: o[k] for k in
            ("req_uid", "clause", "source", "tp_uids") if k in o})
            for _, o in sorted(mix.items())]


arms = {}
arms["FROZEN"] = dict(frozen)
arms["FULL43"] = {**{u: o for u, o in frozen.items() if u not in over},
                  **{u: o for u, o in full43.items() if u in over}}
arms["+TOOLS"] = {**arms["FULL43"], **{u: o for u, o in new.items() if u in sub}}
# A requirement rejected in the new run must DROP OUT of +TOOLS, not silently
# keep FULL43's check -- that would score a lost check as if it survived.
for u in sub:
    if u not in new:
        arms["+TOOLS"].pop(u, None)

traces = {arm: load_traces(S / d / "suite/results")
          for arm, d in (("golden", "rtl_golden2"), ("candidate", "rtl_cand2"))}

res = {}
print(f"{'':16}{'CONFORMS':>9}{'VIOLATES':>9}{'UNDECIDED':>10}{'cover':>8}{'pass':>7}")
for label, mix in arms.items():
    for rtl in ("golden", "candidate"):
        d = {x.req_uid: x.ok for x in decide_rtl(build(mix), traces[rtl], contract)}
        for u in frozen:
            d.setdefault(u, None)
        res[(label, rtl)] = d
        c, n = collections.Counter(d.values()), len(frozen)
        tag = f"{label:16}" if rtl == "golden" else " " * 16
        print(f"{tag}{c[True]:>9}{c[False]:>9}{c[None]:>10}"
              f"{100*(n-c[None])/n:>7.0f}%{100*(n-c[False])/n:>6.0f}%   {rtl}")
    print()

print(f"{'set':<16}{'discriminating':>15}{'inverted':>10}{'separation':>12}")
for label in arms:
    g, c = res[(label, "golden")], res[(label, "candidate")]
    disc = sorted(u for u in g if g[u] is True and c[u] is False)
    inv = sorted(u for u in g if g[u] is False and c[u] is True)
    print(f"{label:<16}{len(disc):>15}{len(inv):>10}{len(disc)-len(inv):>+12}")

print("\nTHE 23, on GOLDEN.  convicting golden is the defect under test.")
print(f"{'req':<10}{'':2}{'FULL43':<9}{'+TOOLS':<9}{'class':<10}"
      f"{'disposition (full43 -> new)'}")
moved = []
for u in sorted(sub):
    a = res[("FULL43", "golden")].get(u)
    b = res[("+TOOLS", "golden")].get(u)
    cls = "movable" if u in movable else ("control" if u in controls else "not-assertable?")
    mark = "  " if a == b else "->"
    if a != b:
        moved.append((u, a, b, cls))
    print(f"{u:<10}{mark}{str(a):<9}{str(b):<9}{cls:<10}"
          f"{disp43.get(u,'-')} -> {dispN.get(u,'REJECTED')}")

print(f"\nmoved on golden: {len(moved)} of {len(sub)}")
for u, a, b, cls in moved:
    print(f"  {u}  {a} -> {b}   ({cls})")
json.dump({"arms": {k: {r: res[(k, r)] for r in ("golden", "candidate")} for k in arms},
           "moved": moved, "dispositions_new": dispN},
          open(A / "sep23.json", "w"), indent=1, default=str)
