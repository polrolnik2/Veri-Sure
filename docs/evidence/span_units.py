"""Do S1's spans respect the units `divide()` cut, or do they subdivide them?

`divide.py` cuts only at blank lines, list items, headings and table rows --
"boundaries a human put there deliberately" -- and holds itself to
`splits_a_sentence`. Its docstring then grants the classifier three powers:
divide a unit further, chain adjacent units, never merge distant ones.

BUT NOTHING CARRIES THAT CONTRACT TO THE MODEL OR CHECKS IT. S1's system prompt
never says the word "unit". `assure.py` validates that a quote is verbatim and
locatable, and states outright that offsets are "a HINT, not the check". So the
one direction the model is free to move in -- downward, below the floor -- is
the one direction nothing measures.

This measures it. A span is CLEAN if it is exactly a union of whole units;
SUBDIVIDES if it starts or ends strictly inside one. Reported per requirement,
with the two failure shapes separated, because they have different fixes: a
span cutting a sentence is a defect, while one covering a whole paragraph plus
half the next may be a chaining error instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")


def main() -> int:
    from specflow.divide import divide, normalize_spec, splits_a_sentence

    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="/home/user/Veri-Sure/benchmarks/chipverilog/"
                                      "Des/i2c/i2c_master_bit_ctrl/description.txt")
    ap.add_argument("--reqs", default="/home/user/runs/c1-i2c/specflow/requirements.json")
    a = ap.parse_args()

    spec = Path(a.spec).read_text()
    text = normalize_spec(spec)
    units = divide(spec)
    starts = {u.start for u in units}
    ends = {u.end for u in units}
    reqs = json.loads(Path(a.reqs).read_text())["requirements"]

    clean, bad_start, bad_end, offenders = 0, 0, 0, []
    for r in reqs:
        spans = r.get("spec_spans") or []
        ok = True
        for s in spans:
            st, en = int(s.get("start", -1)), int(s.get("end", -1))
            s_ok, e_ok = st in starts, en in ends
            if not s_ok:
                bad_start += 1
            if not e_ok:
                bad_end += 1
            if not (s_ok and e_ok):
                ok = False
        if ok:
            clean += 1
        else:
            offenders.append(r)

    print(f"spec: {len(text)} chars, {len(units)} units from divide()")
    print(f"requirements: {len(reqs)}")
    print(f"  spans that are a union of WHOLE units : {clean}")
    print(f"  spans that SUBDIVIDE a unit           : {len(offenders)}")
    print(f"     (starts inside a unit: {bad_start}, ends inside a unit: {bad_end})")

    # The sharper subset: a span that also cuts a sentence. `divide()` can never
    # produce one, so every hit here is the model going below the floor.
    from specflow.divide import Unit
    as_units = [Unit(start=int(s["start"]), end=int(s["end"]), kind="span")
                for r in reqs for s in (r.get("spec_spans") or [])]
    cut = splits_a_sentence(spec, as_units)
    print(f"  spans that BEGIN MID-SENTENCE         : {len(cut)}"
          f"   <- divide() holds itself to zero here")

    print("\nfirst offenders:")
    for r in offenders[:12]:
        s = (r.get("spec_spans") or [{}])[0]
        print(f"  {r['uid']}  {s.get('start')}-{s.get('end')}  "
              f"{(s.get('quote') or '')[:64]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
