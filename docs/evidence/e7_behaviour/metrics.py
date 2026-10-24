"""metrics.py -- behaviour metrics for every design, from out/<module>/<design>.json.

GOLDEN-GRADED (scoring only; never available in a run), on the UNION of the module's
corpora's input sequences:
  edge      share of edges where every spec output equals golden's
  tp        share of testpoints whose whole output trace equals golden's
  cell      share of (testpoint, output port) traces equal to golden's
  order     share of testpoints whose sequence of distinct output states equals golden's
            (durations and latency ignored -- what an order-only check can see)
  class     the design's behaviour on the stimulus, as a hash of every output at every edge

GOLDEN-FREE (what a run could compute), on the design's OWN corpus's input sequences only:
  ship      share of the run's shipped requirements the design passes (the editor's review)
  ref       edge agreement with the run's own reference model (the model that realized the stimulus)
  peer      mean edge agreement with the other generated designs of the same corpus
"""

import hashlib
import json
import statistics as st
import os
from pathlib import Path

#: Working tree (stimulus, traces, metrics): large and regenerable, so outside the repo.
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path("/home/user/Veri-Sure/docs/evidence/e7")
MODS = [
    "fpu_exceptions",
    "i2c_master_bit_ctrl",
    "i2c_master_byte_ctrl",
    "or1200_dc_fsm",
    "or1200_sb",
]
abl = {
    (r["run"], r["module"], r["sample"]): r
    for r in json.loads((E / "ABLATION.json").read_text())
}
edj = {(r["run"], r["module"]): r for r in json.loads((E / "EDITOR.json").read_text())}
#: The checks-only feedback rerun's kinds -> editor tag, and the arm each is reported under. Arms of
#: their own, so the generated/repaired figures of `BEHAVIOUR.md` are unchanged by their presence.
CF = {"cfg": "cf-gen", "cfc": "cf-checks", "cfm": "cf-model",
      "acg1": "abl-child-gen1", "acg2": "abl-child-gen2", "acg3": "abl-child-gen3", "vc": "val-cons"}
ARM = {"final": "repaired", "cfg": "generated-child", "cfc": "checks-repaired",
       "cfm": "model-repaired-rerun", "acg1": "generated-child", "acg2": "generated-child",
       "acg3": "generated-child", "vc": "consensus-repaired"}


def _cf(run, mod, kind, name):
    f = E / run / f"editor-{CF[kind]}" / mod / name
    return json.loads(f.read_text()) if f.is_file() else None


def verdict(run, mod, kind):
    if kind in CF:
        return (_cf(run, mod, kind, "chipverilog.json") or {}).get("status")
    if kind.startswith("gen"):
        return abl[(run, mod, kind)]["verdict"]
    if kind == "final":
        return edj[(run, mod)]["verdict"]
    f = E / run / "editor" / mod / "chipverilog_generated.json"
    return json.loads(f.read_text()).get("status") if f.is_file() else None


def ship(run, mod, kind):
    if kind in CF:
        h = _cf(run, mod, kind, "editor_summary.json")["final"]
        return h["pass"] / h["requirements"]
    if kind.startswith("gen"):
        r = abl[(run, mod, kind)]
    elif kind == "final":
        r = edj[(run, mod)]
    else:
        h = json.loads((E / run / "editor" / mod / "editor_summary.json").read_text())[
            "history"
        ][0]
        r = {"pass": h["pass"], "requirements": h["requirements"]}
    return r["pass"] / r["requirements"]


def num(s):
    try:
        return int(s, 16)
    except ValueError:
        return s  # x / z


def dedup(rows):
    out = []
    for r in rows:
        if not out or out[-1] != r:
            out.append(r)
    return out


def _dc(row):
    """A golden X/Z sample is DON'T-CARE: an unreset register golden itself leaves undefined."""
    return [None if any(ch in v for ch in "xXzZ") else v for v in row]


def _eq(x, y, dc):
    if not dc:
        return x == y
    return len(x) == len(y) and all(g is None or g == v for v, g in zip(x, _dc(y)))


def agree(a, b, runs, tps_of, dc=False):
    """(edge, tp, cell, order) agreement of traces a and b over `runs`; `dc`: b is golden."""
    e = et = t = tt = c = ct = o = 0
    for r in runs:
        for tp in tps_of[r]:
            x, y = a[r][tp], b[r][tp]
            n = min(len(x), len(y))
            e += sum(1 for i in range(n) if _eq(x[i], y[i], dc))
            et += max(len(x), len(y))
            t += len(x) == len(y) and all(_eq(p, q, dc) for p, q in zip(x, y))
            tt += 1
            dx, dy = dedup(x), dedup([_dc(r) if dc else r for r in y])
            o += len(dx) == len(dy) and all(
                _eq(p, q, False)
                if not dc
                else all(g is None or g == v for v, g in zip(p, q))
                for p, q in zip(dx, dy)
            )
            for k in range(len(x[0]) if x else 0):
                c += all(_eq([p[k]], [q[k]], dc) for p, q in zip(x, y)) and len(
                    x
                ) == len(y)
                ct += 1
    return {
        "edge": e / et if et else None,
        "tp": t / tt if tt else None,
        "cell": c / ct if ct else None,
        "order": o / tt if tt else None,
    }


rows, classes = [], {}
for mod in MODS:
    d = EQ / "out" / mod
    if not (d / "golden.json").is_file():
        continue
    G = json.loads((d / "golden.json").read_text())
    runs = sorted(G)
    tps_of = {r: sorted(G[r]) for r in runs}
    def fp(D):
        return hashlib.sha256(
            json.dumps([D[r][tp] for r in runs for tp in tps_of[r]]).encode()
        ).hexdigest()[:12]
    gfp = fp(G)
    stims = {r: json.loads((EQ / "stim" / r / f"{mod}.json").read_text()) for r in runs}
    D = {}
    for f in sorted(d.glob("*.json")):
        if f.stem == "golden":
            continue
        x = json.loads(f.read_text())
        if "compile_error" in x or any("run_error" in x.get(r, {}) for r in runs):
            print("SKIP", mod, f.stem, "compile/run error")
            continue
        D[f.stem] = x
    for name, x in D.items():
        run, kind = name.split(".")
        own = [run]
        g = agree(x, G, runs, tps_of, dc=True)  # union stimulus, golden-graded
        g_own = agree(x, G, own, tps_of, dc=True)
        ref = stims[run]
        re_ = rt = 0
        for tp in tps_of[run]:
            for i, row in enumerate(x[run][tp]):
                exp = (
                    ref["tps"][tp]["ref"][i] if i < len(ref["tps"][tp]["ref"]) else None
                )
                rt += 1
                re_ += exp is not None and all(
                    num(s) == (int(v) if v is not None else None)
                    for s, v in zip(row, exp)
                )
        #: byte_ctrl's real-child designs are compared with the real-child samples only: the
        #: gen1..3 of ABLATION.json had a stand-in child.
        group = (("cfg", "acg1", "acg2", "acg3") if mod == "i2c_master_byte_ctrl" and kind in CF
                 else ("gen1", "gen2", "gen3", "r0"))
        peers = [
            p
            for p in D
            if p.split(".")[0] == run
            and p.split(".")[1] in group
            and p != name
        ]
        peer = (
            st.mean(agree(x, D[p], own, tps_of)["edge"] for p in peers)
            if peers
            else None
        )
        cls = fp(x)
        if (
            g["tp"] == 1.0
        ):  # equal to golden everywhere golden is defined: golden's class
            cls = gfp
        rows.append(
            {
                "module": mod,
                "run": run,
                "kind": kind,
                "arm": ARM.get(kind, "generated"),
                "verdict": verdict(run, mod, kind),
                "class": cls,
                "golden_class": cls == gfp,
                **{f"g_{k}": v for k, v in g.items()},
                **{f"own_{k}": v for k, v in g_own.items()},
                "ship": ship(run, mod, kind),
                "ref": re_ / rt if rt else None,
                "peer": peer,
            }
        )
(EQ / "metrics.json").write_text(json.dumps(rows, indent=1))
print(len(rows), "designs scored")
