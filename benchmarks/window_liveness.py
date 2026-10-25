#!/usr/bin/env python3
"""Did the rewritten checks get BETTER, or only better-looking?

`window_probe.py` measures uptake -- does the check author call `after` instead
of writing its own index arithmetic. That is necessary and it is not the
question. A check can call every operator in the module and still decide
nothing, or decide everything the wrong way.

So this replays them. Pure computation, no model calls: it reads a probe's
`oracles.json`, runs each check against the WITNESS over the stimulus that
already exists, and asks the three questions the uptake number cannot:

  DOES IT DECIDE?        `decide` returning None means the activation never
                         occurred. A check that abstains on every testpoint it
                         names is not evidence, whatever it is made of -- and
                         it is the failure mode a nicer window makes MORE
                         likely, since a narrower window is easier to miss.

  DOES IT STILL PASS?    Against the same witness the old set was measured on.
                         A new check that a spec-faithful implementation fails
                         is over-strict, and the whole argument for this change
                         was that over-strictness comes from inexpressiveness --
                         so if the count does not fall, that argument is wrong
                         and it should be reported as wrong.

  WHAT MOVED?            Per requirement, old disposition against new verdict.
                         The aggregate hides the case that matters: a check
                         that went from over-strict to abstaining has not been
                         fixed, it has been broken in the other direction.

Against the witness rather than the control, for the reason `_liveness` gives:
the same 70 frozen oracles gave identical verdicts against a model scoring
30/168 and against the known-good control at 168/168, on all 70. The witness is
sufficient here and carries no golden-RTL information.

    python benchmarks/window_liveness.py --run /home/user/runs/a2-i2c \\
        --probe /tmp/window_probe
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from specflow.refmodel import liveness as L  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=pathlib.Path)
    ap.add_argument("--probe", required=True, type=pathlib.Path,
                    help="a window_probe.py --out directory")
    ap.add_argument("--base", default="step")
    args = ap.parse_args(argv)

    src = args.run / "specflow"
    contract = json.loads((args.run / "contract.json").read_text(encoding="utf-8"))
    witness = (src / "witness.py").read_text(encoding="utf-8")
    stim = json.loads((src / "stimulus.json").read_text(encoding="utf-8"))
    stim_by_tp = {t["tp_uid"]: t.get("stimulus_steps") or []
                  for t in (stim.get("testpoints") or [])}

    old = json.loads((src / "oracles.json").read_text(encoding="utf-8"))
    old_disp = old.get("dispositions") or {}
    old_over = set(old.get("unsatisfiable_by_the_control") or [])
    # The tp_uids each requirement's OLD oracle named. Reused rather than
    # re-derived: the point is to replay the new check over the same evidence,
    # so a difference is the check and not a different testpoint set.
    old_tps = {(o.get("req_uid") or o.get("uid")): o.get("tp_uids") or []
               for o in (old.get("oracles") or [])}

    rows = json.loads((args.probe / "oracles.json").read_text(encoding="utf-8"))
    built, skipped = [], []
    for r in rows:
        uid = r["req_uid"]
        tps = old_tps.get(uid) or []
        if not tps:
            skipped.append(uid)
            continue
        built.append(RequirementOracle(
            req_uid=uid, clause=r.get("clause", ""), source=r["source"],
            tp_uids=list(tps)))
    if skipped:
        # NEVER SILENT. A requirement dropped here is one this comparison
        # cannot speak about, and a rate that quietly excluded it would read
        # as a result over the whole population.
        print(f"skipped {len(skipped)} with no testpoints in the old set: "
              f"{sorted(skipped)}")

    report = L.assess(built, witness, contract, stim_by_tp, base=args.base)

    print(f"\nLIVENESS against the witness, {len(built)} rewritten checks")
    for verdict, n in sorted(L.counts(report).items()):
        print(f"  {verdict:14} {n:3}")

    # Decide-rate is the headline: a check that abstains everywhere is not a
    # check, and a narrower window makes abstention MORE likely, not less.
    decided = [u for u, rec in report.items()
               if rec.get("verdict") in (L.LIVE, L.DEAD_ORACLE)]
    print(f"\n  decides on at least one testpoint: {len(decided)}/{len(built)}")

    def dv(v):
        return v.get("disposition") if isinstance(v, dict) else v

    moved = collections.Counter()
    for u in sorted(report):
        was = ("over-strict" if u in old_over
               else str(dv(old_disp.get(u)) or "?").lower())
        moved[(was, report[u].get("verdict", L.UNKNOWN))] += 1
    print("\n  old disposition -> new liveness verdict")
    for (was, now), n in sorted(moved.items(), key=lambda kv: -kv[1]):
        print(f"    {was:12} -> {now:14} {n:3}")

    out = args.probe / "liveness.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
