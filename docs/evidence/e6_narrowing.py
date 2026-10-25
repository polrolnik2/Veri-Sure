"""The SLOPE the repair guard records and does not gate. Zero model calls.

    e6_narrowing.py <evidence-dir> [<evidence-dir> ...]

`oracles_stage` blocks a repair that stops deciding ENTIRELY -- `was and not
now` -- and says so in its own comment:

    THE SLOPE, RECORDED BECAUSE THE GUARD BELOW ONLY SEES THE CLIFF. A
    replacement that goes from ten testpoints to one passes silently ...
    REPORTED, NOT GATED. The cliff is measured at nine checks on d1-i2c; the
    slope is unmeasured, and a threshold picked before its distribution is
    seen is the error this branch keeps paying for. This is what makes the
    distribution visible.

It has been visible in `repair_narrowing` for three completed runs and nobody
read it. This reads it.
"""
import json
import sys
from pathlib import Path

for tag in sys.argv[1:]:
    d = Path(tag)
    nar = (json.loads((d / "oracles.json").read_text())
           .get("repair_narrowing") or {})
    if not nar:
        print(f"{d.name}: no repair_narrowing recorded")
        continue
    cliff = kept = wider = 0
    worst: list[tuple[int, str, int, int]] = []
    for uid, events in nar.items():
        for e in events:
            was, now = int(e.get("was", 0)), int(e.get("now", 0))
            if was and not now:
                cliff += 1
            elif now > was:
                wider += 1
            elif was > now:
                kept += 1
                worst.append((was - now, uid, was, now))
    worst.sort(reverse=True)
    print(f"\n=== {d.name}: {len(nar)} requirement(s) changed reach ===")
    print(f"  cliff (BLOCKED)        {cliff}")
    print(f"  narrowed but KEPT      {kept}")
    print(f"  widened                {wider}")
    for delta, uid, was, now in worst[:8]:
        pct = 100 * delta / max(1, was)
        print(f"    {uid}: {was} -> {now} testpoint(s)  (-{delta}, "
              f"{pct:.0f}% of its reach) and was KEPT")
