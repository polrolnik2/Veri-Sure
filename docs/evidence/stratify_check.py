"""Could a fleet have untangled this by ITERATING, and did the material exist?

The classic answer to "in what order do I resolve mutually dependent things"
is that you do not need the order: stratified bottom-up evaluation (Datalog's
semi-naive iteration, or chaotic iteration in dataflow analysis) runs everything
each round, keeps what could be discharged from the vocabulary currently
available, publishes those results into the vocabulary, and repeats to fixpoint.
The dependency graph is the OUTPUT, not the input -- which is exactly what makes
it applicable here, where deriving the graph from the RTL is circular.

This asks two questions of h3's own artifacts:

  1. Does the specification actually SUPPLY a definition at each level of the
     filter chain? Without one, there is nothing for a round to discharge and
     the iteration has no bottom to start from.
  2. What did the pipeline do with those definitions?

and checks whether either dependency field already in the requirement schema
could order the rounds.
"""
import collections
import json
import re
from pathlib import Path

RUN = Path("/home/user/runs/h3-i2c/specflow")
DEPTH = {"cSCL": 0, "cSDA": 0, "filter_cnt": 0, "fSCL": 1, "fSDA": 1,
         "sSCL": 2, "sSDA": 2, "dSCL": 3, "dSDA": 3,
         "sta_condition": 4, "sto_condition": 4,
         "slave_wait": 5, "clk_en": 5, "cnt": 5, "scl_sync": 5}
# "<sig> IS <expr>" defines; "when <sig> ..." only uses. Only a definition can
# be discharged into the next round's vocabulary.
DEFN = re.compile(r"\b(is|are|shall be|equals?|becomes|is set to|is the|is defined|derived)\b",
                  re.I)

items = json.loads((RUN / "requirements.json").read_text())
items = items if isinstance(items, list) else (items.get("requirements") or items["elements"])
o = json.loads((RUN / "oracles.json").read_text())
disp = {k: (v.get("disposition") if isinstance(v, dict) else v)
        for k, v in (o.get("dispositions") or {}).items()}

defines = collections.defaultdict(list)
for it in items:
    uid = it["uid"]
    txt = it.get("text") or (it.get("obligation") or {}).get("quote") or ""
    for sig in DEPTH:
        for sent in re.split(r"(?<=[.;])\s+", txt):
            if re.search(rf"\b{sig}\b", sent) and DEFN.search(sent):
                defines[sig].append(uid)
                break

print("does the SPEC define each level of the chain, and what became of it?")
print(f"{'signal':<15}{'depth':>6}  defining requirement -> disposition")
for sig, dep in sorted(DEPTH.items(), key=lambda x: x[1]):
    ds = defines.get(sig) or []
    shown = "  ".join(f"{u}={disp.get(u, '-')}" for u in ds[:3]) or "NONE"
    print(f"{sig:<15}{dep:>6}  {shown}")

print("\ncould either dependency field in the schema order the rounds?")
n = collections.Counter(tuple(sorted(i.get("needs") or [])) for i in items)
print(f"  `needs`    : {len(items)} requirements, {len(n)} distinct value(s) -> {list(n)[:2]}")
print("               a STAGE LIST, identical everywhere. Not an edge.")

uids = {i["uid"] for i in items}
sup = {i["uid"]: [x for x in (i.get("supports") or []) if x in uids] for i in items}
dep_of = collections.defaultdict(set)
for a, bs in sup.items():
    for b in bs:
        dep_of[b].add(a)                 # A supports B -> settle A first
layer = {}


def d(u, stack=frozenset()):
    if u in layer:
        return layer[u]
    if u in stack:
        return 0
    layer[u] = 1 + max((d(x, stack | {u}) for x in dep_of.get(u, ())), default=-1)
    return layer[u]


for u in uids:
    d(u)
print(f"  `supports` : a real requirement-to-requirement edge on "
      f"{sum(1 for v in sup.values() if v)} of {len(items)}")
for r, what in (("REQ-0076", "DEFINES cSCL, the chain's root"),
                ("REQ-0051", "DEFINES sSCL/sSDA/sta/sto"),
                ("REQ-0057", "CONSUMES the filtered bus"),
                ("REQ-0052", "CONSUMES the filtered bus")):
    print(f"      layer {layer.get(r)}  {r}  {what}")
print("               the consumers sort BEFORE the producers, so this edge is"
      "\n               rhetorical (which paragraph elaborates which), not"
      "\n               derivational. Ordering by it is worse than not ordering.")
