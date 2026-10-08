"""The lexical window screen against a mechanical, design-anchored one.

`_names_a_window` compares the requirement's PROSE to the normalized FORM and
warns when they disagree about a span. It ships as a warning and gates nothing,
but it is a faithfulness instrument and nothing had ever checked it against
anything outside itself. `variety.flattened_a_span` asks the same question of
the DESIGNS: run the activation's own `inputs` predicate along the population's
traces and see whether the behaviour occupies more than the one row the form
kept.

Zero model calls -- normalization is read off `e3/normalized-all.json` and the
designs are replayed. The replay harness is deliberately a copy of the one in
`e4b_constriction.py` rather than a shared import, so each evidence driver runs
standalone from a bare checkout.
"""
import glob
import importlib.util
import json
import os
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V  # noqa: E402
from specflow.normalize import _names_a_window  # noqa: E402

CMD = {"NOP": 0, "START": 1, "STOP": 2, "WRITE": 4, "READ": 8}


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Model


def stim(seq, *, clk_cnt=4, sda=1, scl=1, hold=6):
    out = [{"nReset": 0, "rst": 1, "ena": 0, "cmd": 0, "din": 0,
            "clk_cnt": clk_cnt, "scl_i": scl, "sda_i": sda}] * 2
    out = list(out)
    for name, din in seq:
        for _ in range(hold):
            out.append({"nReset": 1, "rst": 0, "ena": 1, "cmd": CMD[name],
                        "din": din, "clk_cnt": clk_cnt,
                        "scl_i": scl, "sda_i": sda})
    return out


TESTPOINTS = {
    "TP-start":   stim([("START", 0), ("NOP", 0)]),
    "TP-write":   stim([("START", 0), ("WRITE", 1), ("NOP", 0)]),
    "TP-read":    stim([("START", 0), ("READ", 0), ("NOP", 0)]),
    "TP-stop":    stim([("START", 0), ("WRITE", 1), ("STOP", 0)]),
    "TP-arb":     stim([("START", 0), ("WRITE", 1)], sda=0),
    "TP-slow":    stim([("START", 0), ("WRITE", 0)], clk_cnt=9, hold=10),
    "TP-nostart": stim([("WRITE", 1), ("NOP", 0)]),
}


def replay(Model, steps):
    m = Model()
    m.reset()
    rows = []
    for i, inp in enumerate(steps):
        try:
            outs = m.step(dict(inp))
        except Exception:
            return None
        rows.append({"inputs": dict(inp), "outputs": dict(outs), "edge": i})
    return rows


designs = {}
for p in sorted(glob.glob("docs/evidence/*-i2c.ref_model.py")):
    name = os.path.basename(p).split("-")[0]
    try:
        M = load(p)
    except Exception as e:
        print(f"  skip {name}: {e}")
        continue
    rows = {tp: r for tp, s in TESTPOINTS.items() if (r := replay(M, s))}
    if len(rows) == len(TESTPOINTS):
        designs[name] = rows
    else:
        print(f"  skip {name}: ran {len(rows)}/{len(TESTPOINTS)} testpoints")

print(f"\ndesigns replayed: {len(designs)} -> {sorted(designs)}")
have = json.load(open("docs/evidence/e3/normalized-all.json"))
print(f"forms: {len(have)}")

#: THE SHIPPING PREDICATE, COPIED EXACTLY from `normalize.py:1888` -- it reads
#: the NORMALIZED activation text plus the expectation, not the raw requirement,
#: and it is guarded on `windowed` alone. Re-deriving it from the prose here
#: would measure a different screen than the one that ships.
warned, flattened, judgeable = set(), set(), set()
for uid, n in have.items():
    act = n.get("activation") or {}
    if not act.get("windowed") and _names_a_window(
            f"{act.get('text', '')} {n.get('expectation', '')}"):
        warned.add(uid)
    if not act.get("windowed") and not act.get("until") and (act.get("inputs") or {}):
        judgeable.add(uid)
        if V.flattened_a_span(act, designs):
            flattened.add(uid)

N = len(have)
both = warned & judgeable
print(f"\nLEXICAL    warns                     {len(warned):3d} of {N}"
      f"   {100 * len(warned) / N:.1f}%")
print(f"MECHANICAL can judge at all          {len(judgeable):3d} of {N}"
      f"   {100 * len(judgeable) / N:.1f}%")
print(f"           flattened a real span     {len(flattened):3d} of "
      f"{len(judgeable)}   {100 * len(flattened) / max(1, len(judgeable)):.1f}%")
print(f"\n  agree (warned AND flattened)       {len(warned & flattened):3d}")
print(f"  warned but NOT flattened           {len(warned - flattened):3d}"
      f"   of which {len(warned - judgeable)} are not judgeable at all")
print(f"  flattened but NOT warned            {len(flattened - warned):3d}")
print(f"\n  on the {len(both)} forms BOTH can judge: agree on "
      f"{len(both & flattened)} = {100 * len(both & flattened) / max(1, len(both)):.0f}%")
print(f"  recall against flattening: {len(both & flattened)} of {len(flattened)}"
      f" = {100 * len(both & flattened) / max(1, len(flattened)):.0f}%")

json.dump({"forms": N, "designs": sorted(designs),
           "warned": sorted(warned), "judgeable": sorted(judgeable),
           "flattened": sorted(flattened)},
          open("docs/evidence/window-lexical-vs-mechanical.json", "w"), indent=1)
