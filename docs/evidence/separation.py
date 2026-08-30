"""Did the instrument get BETTER, or only quieter?

Passing golden is half a measurement. A check that abstains everywhere passes
golden too. The question that decides whether this was worth doing is whether
the set still tells the KNOWN-GOOD design apart from a CANDIDATE one -- which
is what `discriminating` minus `inverted` measures, and what every previous run
has been scored on.

Splices the re-authored 43 into c1-i2c's frozen 110 and re-decides both arms.
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
reauth = {o["req_uid"]: o for o in json.load(open(A / "full43/run/specflow/oracles.json"))["oracles"]}
over = set(json.load(open(A / "over_strict.json"))["over_strict"])

def build(mix: dict) -> list:
    out = []
    for u, o in sorted(mix.items()):
        kw = {k: o[k] for k in ("req_uid", "clause", "source", "tp_uids") if k in o}
        out.append(RequirementOracle(**kw))
    return out

# ARM 1: the frozen 110 as they were.  ARM 2: the same 110 with the 43 replaced
# by whatever survived re-authoring -- a requirement whose check was REJECTED
# contributes NOTHING, which is the honest representation of a lost check.
before = dict(frozen)
after = {u: o for u, o in frozen.items() if u not in over}
after.update({u: o for u, o in reauth.items() if u in over})

traces = {arm: load_traces(S / d / "suite/results")
          for arm, d in (("golden", "rtl_golden2"), ("candidate", "rtl_cand2"))}

print(f"{'':22}{'CONFORMS':>9}{'VIOLATES':>9}{'UNDECIDED':>10}{'coverage':>10}{'pass rate':>11}")
res = {}
for label, mix in (("BEFORE (frozen 110)", before), ("AFTER  (43 re-authored)", after)):
    for arm in ("golden", "candidate"):
        d = {x.req_uid: x.ok for x in decide_rtl(build(mix), traces[arm], contract)}
        # A requirement with no surviving check decides nothing, by definition.
        for u in frozen:
            d.setdefault(u, None)
        res[(label, arm)] = d
        c = collections.Counter(d.values())
        n = len(frozen)
        cov = 100 * (n - c[None]) / n
        pr = 100 * (n - c[False]) / n
        tag = f"{label if arm=='golden' else '':22}" if arm == "golden" else " " * 22
        print(f"{tag}{c[True]:>9}{c[False]:>9}{c[None]:>10}{cov:>9.0f}%{pr:>10.0f}%   {arm}")
    print()

print(f"{'set':<24}{'discriminating':>15}{'inverted':>10}{'separation':>12}")
for label in ("BEFORE (frozen 110)", "AFTER  (43 re-authored)"):
    g, c = res[(label, "golden")], res[(label, "candidate")]
    disc = sorted(u for u in g if g[u] is True and c[u] is False)
    inv = sorted(u for u in g if g[u] is False and c[u] is True)
    print(f"{label:<24}{len(disc):>15}{len(inv):>10}{len(disc)-len(inv):>+12}")
    if label.startswith("AFTER") and disc:
        print(f"{'':24}discriminating: {' '.join(disc)}")
