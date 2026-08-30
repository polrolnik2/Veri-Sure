"""What if the loop had STOPPED at the first accepted attempt?

The loop re-reviews EVERY held oracle every round -- `oracles_stage.py`'s
`correspondence.review(list(held.values()), ...)` has no "already passed" filter
-- and the disposition is taken from the LAST round's `rejected`. With a reviewer
that flips on 33% of byte-identical prompts, every extra review of a check that
already passed is a fresh chance to lose it.

The correspondence PROMPT carries `{"clause": ..., "source": ...}`, so the exact
check that passed at round r can be reconstructed and decided against the
held-out arms. `tp_uids` are taken from the frozen artifact (staging only ever
ADDED ids, so this is the generous reading for every policy alike).
"""
import json, re, sys, collections
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.rtl_trace import decide_rtl, load_traces

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"; IO = A / "full43/io"
art = json.load(open(A / "full43/run/specflow/oracles.json"))
contract = json.load(open(A / "full43/run/contract.json"))
disp = art["dispositions"]
final = {o["req_uid"]: o for o in art["oracles"]}
# tp_uids for a REJECTED uid are not in the frozen set, so take c1's originals
# and add whatever staging minted for that requirement.
c1 = {o["req_uid"]: o for o in json.load(
    open("/home/user/runs/c1-i2c/specflow/oracles.json"))["oracles"]}
added = art.get("stimulus_added") or {}
def tps(u):
    if u in final:
        return final[u].get("tp_uids") or []
    return sorted(set(c1.get(u, {}).get("tp_uids") or []) | set(added.get(u) or []))

def verdict(u, r):
    p = IO / f"correspond_{u}_r{r}_response.txt"
    return json.loads(p.read_text()).get("tests_the_requirement") if p.exists() else None

def source_at(u, r):
    p = IO / f"correspond_{u}_r{r}_prompt.txt"
    if not p.exists():
        return None
    m = re.search(r"<oracle>\n(.*?)\n</oracle>", p.read_text(), re.S)
    return json.loads(m.group(1)) if m else None

pat = {u: "".join("O" if verdict(u, r) is True else "R" for r in (0, 1, 2)) for u in disp}

def build(policy: str):
    """Return the oracle set a policy would have frozen."""
    out = []
    for u, p in pat.items():
        if policy == "last":            keep = p[2] == "O"; at = 2
        elif policy == "majority":      keep = p.count("O") >= 2; at = p.rfind("O")
        elif policy == "latch":         keep = "O" in p; at = p.find("O")
        elif policy == "unanimous":     keep = "R" not in p; at = 2
        if not keep:
            continue
        # The FROZEN artifact is ground truth for what round 3 reviewed. Two of
        # the 43 have a round-3 prompt that disagrees with it (REQ-0042,
        # REQ-0055), because the resumed run re-derived prompts; prefer the
        # artifact whenever the policy selects the final round.
        blob = (final[u] if at == 2 and u in final else source_at(u, at))
        if not blob:
            continue
        out.append(RequirementOracle(req_uid=u, clause=blob.get("clause", ""),
                                     source=blob["source"],
                                     tp_uids=tps(u)))
    return out

traces = {"golden": load_traces(S / "rtl_golden2/suite/results"),
          "candidate": load_traces(S / "rtl_cand2/suite/results")}
traces["golden"].update(load_traces(A / "staged_golden/suite/results"))

print(f"{'policy':<12}{'kept':>6}{'calls':>7}{'passes':>8}{'CONVICTS':>10}"
      f"{'silent':>8}{'disc':>6}{'inv':>5}{'sep':>6}")
for policy in ("last", "majority", "latch", "unanimous"):
    orc = build(policy)
    d = {a: {x.req_uid: x.ok for x in decide_rtl(orc, t, contract)}
         for a, t in traces.items()}
    g, c = d["golden"], d["candidate"]
    for u in disp:
        g.setdefault(u, None); c.setdefault(u, None)
    n = collections.Counter(g.values())
    disc = sum(1 for u in g if g[u] is True and c[u] is False)
    inv = sum(1 for u in g if g[u] is False and c[u] is True)
    # calls a policy would have spent: round 1 reviews all; later rounds review
    # only what that policy has not yet settled.
    # Round 1 reviews everything. A later round reviews only what the policy
    # has not yet settled -- which is everything, except under `latch`, where a
    # check that has passed is never re-asked again.
    calls = len(pat)
    for r in (1, 2):
        calls += (sum(1 for p in pat.values() if "O" not in p[:r])
                  if policy == "latch" else len(pat))
    print(f"{policy:<12}{len(orc):>6}{calls:>7}{n[True]:>8}{n[False]:>10}"
          f"{n[None]:>8}{disc:>6}{inv:>5}{disc-inv:>+6}")
cens = collections.Counter(pat.values())
print("\n  pattern census:", dict(sorted(cens.items())), "n =", sum(cens.values()))
print("  latch calls =", len(pat), "+",
      sum(1 for p in pat.values() if "O" not in p[:1]), "+",
      sum(1 for p in pat.values() if "O" not in p[:2]))
print("\n  last     = what the run did: the final round's verdict decides")
print("  majority = 2 of 3 rounds accepted")
print("  latch    = STOP AT THE FIRST ACCEPTED ATTEMPT, and never re-ask")
print("  unanimous= every round must accept; one rejection anywhere is fatal")
