"""realize.py RUN MODULE -- fix one corpus's stimulus as concrete per-edge input vectors.

Each testpoint's `stimulus_steps` are replayed through THE RUN'S OWN reference model
(`ref_model.py`, golden-free): `until` waits resolve against that model, exactly as the
run's own screening did. The result is one fixed input sequence per testpoint, which every
RTL design (golden included) is then driven through open-loop. The model's outputs are kept
too: they are the run's own expectation, available in-run without golden.
-> stim/<run>/<module>.json
"""

import json
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import replay  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402

#: Working tree (stimulus, traces, metrics): large and regenerable, so outside the repo.
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
run, mod = sys.argv[1], sys.argv[2]
C = EQ / "corpora" / run / mod
if not C.is_dir():  #: unpack the committed corpus
    import tarfile

    C.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(
        f"/home/user/Veri-Sure/docs/evidence/e7/{run}/corpora/{mod}-ok.tar.gz"
    ) as t:
        t.extractall(C.parent, filter="data")
    (C.parent / f"{mod}-ok").rename(C)
contract = json.loads((C / "contract.json").read_text())
src = (C / "ref_model.py").read_text()
s = json.loads((C / "stimulus.json").read_text())
stim = s["testpoints"] if isinstance(s, dict) else s
ins = [p["name"] for p in contract["io"] if p["dir"] == "input"]
outs = [p["name"] for p in contract["io"] if p["dir"] == "output"]
width = {p["name"]: int(p.get("width") or 1) for p in contract["io"]}
base = choose_base(contract)
t0 = time.time()
tps = {}
for t in stim:
    steps = t.get("stimulus_steps") or []
    if not steps:
        continue
    rep = replay(src, contract, steps, base=base)
    rows = [[r["inputs"].get(n) for n in ins] for r in rep.rows]
    ref = [[r["outputs"].get(n) for n in outs] for r in rep.rows]
    tps[t["tp_uid"]] = {
        "rows": rows,
        "ref": ref,
        "err": rep.error if hasattr(rep, "error") else "",
        "notes": list(getattr(rep, "notes", []) or [])[:3],
    }
out = EQ / "stim" / run
out.mkdir(parents=True, exist_ok=True)
(out / f"{mod}.json").write_text(
    json.dumps(
        {
            "inputs": ins,
            "outputs": outs,
            "width": width,
            "clock": (contract.get("clocking") or {}).get("clock", {}).get("name"),
            "tps": tps,
        }
    )
)
edges = sum(len(v["rows"]) for v in tps.values())
none_in = sum(1 for v in tps.values() for r in v["rows"] for x in r if x is None)
print(
    f"{run} {mod}: {len(tps)} tps, {edges} edges, {none_in} None inputs, {time.time() - t0:.0f}s, "
    f"errors {sum(1 for v in tps.values() if v['err'])}"
)
