"""Does moving `al` from until= to aborts= flip REQ-0055 on golden RTL?

Two candidate defects were on the table for this check and only one of them is
what `aborts_on` fixes. Measure, do not assert.
"""
import collections
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.rtl_trace import load_traces, rows_from
from specflow.refmodel.oracles import transactional_view
from specflow.refmodel.temporal import after, eventually, worst

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
tr = load_traces(S/"rtl_golden2/suite/results")
tr.update(load_traces(A/"staged_golden/suite/results"))

def _holds(cond):
    def p(row):
        return all(row["outputs"].get(k, row["inputs"].get(k)) == v
                   for k, v in cond.items())
    return p

def _any(alts):
    preds = [_holds(a) for a in alts]
    return lambda row: any(p(row) for p in preds)

def decide(trace, *, split):
    """split=False reproduces the frozen check; split=True moves `al` to aborts."""
    if split:
        closes, voids = _holds({"cmd_ack": 1}), _holds({"al": 1})
    else:
        closes, voids = _any([{"cmd_ack": 1}, {"al": 1}]), None
    def _w(cmd_value):
        return after(trace, _holds({"cmd": cmd_value, "ena": 1, "nReset": 1, "rst": 0}),
                     until=closes, aborts=voids)
    v = []
    for w in _w(1):
        v.append(eventually(w, lambda r: r["outputs"]["scl_oen"] == 0,
                            after_activation=True, strong=True))
        v.append(eventually(w, lambda r: r["outputs"]["sda_oen"] == 0,
                            after_activation=True, strong=True))
    for w in _w(2):
        v.append(eventually(w, lambda r: r["outputs"]["sda_oen"] == 0,
                            after_activation=True, strong=True))
    for w in _w(8):
        v.append(eventually(w, lambda r: r["outputs"]["scl_oen"] == 0,
                            after_activation=True, strong=True))
    for w in _w(4):
        v.append(eventually(w, lambda r: r["outputs"]["scl_oen"] == 0,
                            after_activation=True, strong=True))
        if w.value("din") == 0:
            v.append(eventually(w, lambda r: r["outputs"]["sda_oen"] == 0,
                                after_activation=True, strong=True))
    return worst(v)

for tp in ("TP-0132", "TP-0133"):
    raw = tr.get(tp)
    rows = transactional_view(rows_from(raw, side="dut")) if raw else None
    if rows is None:
        print(f"{tp}: NO TRACE")
        continue
    print(f"{tp}  ({len(rows)} rows)")
    for split in (False, True):
        ok, edge, detail = decide(rows, split=split)
        tag = "aborts=al " if split else "until=al|ack"
        print(f"   {tag}  ok={str(ok):<5} edge={edge}  {detail[:90]}")

# And across the WHOLE suite, since the plan's model is suite-wide evidence.
for split in (False, True):
    t = collections.Counter()
    for tp, raw in tr.items():
        t[decide(transactional_view(rows_from(raw, side="dut")), split=split)[0]] += 1
    print(("aborts=al " if split else "until=al|ack"), dict(t))
