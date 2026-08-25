"""Did adding stimulus actually discharge anything?

`add_stimulus` reports success per call and the run reports `stimulus_added` per
turn, so the route looks busy from every angle except the one that matters. It
was busy and inert for three consecutive runs and nobody noticed, because no
view put the two series side by side:

    t-i2c  added 12 -> 24 -> 36 -> 48 across its turns
    w-i2c  added the full 12-testpoint budget
    v-i2c  added the full 12-testpoint budget
    NOT_EXERCISED in all three, every turn r0..r6:  4, 4, 4, 4, 4, 4, 4

48 testpoints of generated stimulus moved nothing. The cause was `_attach`
requiring `activation.inputs`, which skipped the very requirement the testpoint
had been minted for; fixed, but the class of mistake is the reason this exists.

    python3 benchmarks/stimulus_progress.py <run>/specflow [<run2>/specflow ...]

Reads only per-turn artifacts, so it costs nothing and works on any completed
run. A FLAT NOT_EXERCISED column beside a rising `added` column is the finding.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path


def turns(run: Path) -> list[tuple[int, int, dict]]:
    """`(turn, stimulus_added, verdict counts)` per debug turn, in order."""
    out = []
    for f in sorted(glob.glob(str(run / "judge/r*/trust.json")),
                    key=lambda p: int(re.search(r"/r(\d+)/", p).group(1))):
        blob = json.load(open(f))
        out.append((
            int(re.search(r"/r(\d+)/", f).group(1)),
            len(blob.get("stimulus_added") or []),
            (blob.get("mechanical_verdicts") or {}).get("counts") or {},
        ))
    return out


def report(run: Path) -> str:
    rows = turns(run)
    if not rows:
        return f"{run}: no turn artifacts under judge/r*/trust.json"

    name = run.parent.name or str(run)
    lines = [f"=== {name} ==="]
    lines.append(f"  {'turn':<5} {'added':>6} {'NOT_EXERCISED':>14} "
                 f"{'VIOLATES':>9} {'CONFORMS':>9}")
    for t, added, c in rows:
        lines.append(f"  r{t:<4} {added:>6} {c.get('NOT_EXERCISED', 0):>14} "
                     f"{c.get('VIOLATES', 0):>9} {c.get('CONFORMS', 0):>9}")

    added_series = [a for _t, a, _c in rows]
    ne_series = [c.get("NOT_EXERCISED", 0) for _t, _a, c in rows]
    grew = added_series[-1] - added_series[0]
    moved = ne_series[0] - ne_series[-1]

    lines.append("")
    if grew <= 0:
        lines.append(f"  the route never fired: {added_series[-1]} testpoint(s) added in total")
    elif moved > 0:
        lines.append(f"  ROUTE WORKED: +{grew} testpoint(s) and NOT_EXERCISED "
                     f"{ne_series[0]} -> {ne_series[-1]} ({moved} discharged)")
    elif len(set(ne_series)) == 1:
        lines.append(f"  INERT: +{grew} testpoint(s) added and NOT_EXERCISED never "
                     f"moved off {ne_series[0]}. Stimulus was generated and "
                     f"discarded -- check `_attach`.")
    else:
        lines.append(f"  +{grew} testpoint(s) added; NOT_EXERCISED {ne_series[0]} -> "
                     f"{ne_series[-1]}, which is not an improvement")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path, help="one or more specflow/ dirs")
    args = ap.parse_args()
    print("\n\n".join(report(r) for r in args.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
