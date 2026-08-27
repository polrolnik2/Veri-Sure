#!/usr/bin/env python3
"""What does the STAGE produce, where `window_probe` only asked the generator?

`window_probe.py` calls `run_oracle_gen`. That skips the whole of [O]'s
verify-repair cycle: executability against the witness, over-strictness,
vacuity against the variants, liveness, and -- the one that matters -- the
repair round that seeds the rejection reason back into the prompt.

So every figure that probe produced sits UPSTREAM of the feedback these checks
were designed around, and is an upper bound on the defect rate. Pessimistic,
not optimistic, but not the number the pipeline would report. This takes the
same requirements and the SAME normalized forms through `run_oracle_stage`, so
the only difference between the two runs is the stage.

Two repair loops were already running and should not be confused with the
missing one. `run_stage`'s per-item loop fires at both stages -- on wp-v3 it
re-asked 30 of 41 normalisations once and 11 twice. That is `gate_one`'s
STRUCTURAL gate. What was absent is the stage's own loop, which is the only one
that can see a check fail against evidence.

EVERYTHING EXPENSIVE IS REUSED, and the reuse is the reason this is affordable:
`variants.json` (571 calls already paid) and `witness.py` are both read from
`--run/specflow/` by the stage itself. What is paid for here is generation,
correspondence, staging and repair.

    python benchmarks/stage_probe.py --run /tmp/a2-copy \\
        --normalized /tmp/wp-v3/normalized.json --baseline /home/user/runs/a2-i2c
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from specflow.model_io import PortSettings, make_port, resumable  # noqa: E402
from specflow.oracles_stage import CONTROL, run_oracle_stage  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=pathlib.Path,
                    help="a COPY of a completed run dir. The stage writes "
                         "oracles.json into it, so pointing at the original "
                         "destroys the baseline this is measured against.")
    ap.add_argument("--baseline", required=True, type=pathlib.Path,
                    help="the untouched run whose dispositions are compared")
    ap.add_argument("--normalized", required=True, type=pathlib.Path,
                    help="a window_probe --out normalized.json. Passing the "
                         "SAME forms the generator saw is what isolates the "
                         "stage as the only difference.")
    ap.add_argument("--out", required=True, type=pathlib.Path,
                    help="where agent_io lands; kept out of the run copy so a "
                         "resume does not have to distinguish them")
    ap.add_argument("--model", default="gpt-5-mini",
                    help="the fan-out model. NOT Luna: this is a fan-out.")
    ap.add_argument("--effort", default="medium")
    # WITHOUT THIS THE RUN IS BOUNDED BY THE WITNESS ALONE, and the witness
    # shares an author with the checks -- so a misreading they agree on passes.
    # `integration.py` passes `control_source` on all three of its call sites;
    # this probe did not, and the first run was scored against a strictly
    # weaker bound than the baseline it was compared to (`witness+control`).
    # Measured on that run: 7 of 17 replayable TRUSTED checks are failed by the
    # control, and 3 of them PASS the witness -- invisible to a witness-only
    # bound by construction.
    ap.add_argument("--control", type=pathlib.Path,
                    help="a known-good ref_model.py, e.g. "
                         "benchmarks/controls/<top>/ref_model.py. Omitting it "
                         "is legitimate only when no control exists for the "
                         "design; the run then reports `witness` and its "
                         "TRUSTED count is NOT comparable to a witness+control "
                         "baseline.")
    args = ap.parse_args(argv)

    src = args.run / "specflow"
    contract = json.loads((args.run / "contract.json").read_text(encoding="utf-8"))
    contract_json = json.dumps(contract, indent=2, sort_keys=True)
    reqs = json.loads((src / "requirements.json").read_text(encoding="utf-8"))
    reqs = reqs.get("requirements") or reqs
    by_uid = {r["uid"]: r for r in reqs}
    testplan = json.loads((src / "testplan.json").read_text(encoding="utf-8"))
    testplan = testplan.get("elements") or testplan.get("testplan") or testplan
    stim = json.loads((src / "stimulus.json").read_text(encoding="utf-8"))
    stim_by_tp = {t["tp_uid"]: t.get("stimulus_steps") or []
                  for t in (stim.get("testpoints") or [])}
    spec = (args.run / "prompt.txt").read_text(encoding="utf-8")

    norm = json.loads(args.normalized.read_text(encoding="utf-8"))
    target = sorted(u for u in norm if u in by_uid)

    # The baseline disposition for each, from the UNTOUCHED run.
    base = json.loads((args.baseline / "specflow" / "oracles.json")
                      .read_text(encoding="utf-8"))
    base_disp = base.get("dispositions") or {}
    over = set(base.get("unsatisfiable_by_the_control") or [])
    base_bound = str(base.get("over_strictness_bounded_by")
                     or base.get("witness") or "?")

    def dv(v):
        return v.get("disposition") if isinstance(v, dict) else v

    def label(uid):
        d = str(dv(base_disp.get(uid)) or "?")
        return "over-strict" if d == "TRUSTED" and uid in over else d.lower()

    was = collections.Counter(label(u) for u in target)
    print(f"target: {len(target)} requirements -- {dict(was)}")

    control_source = (args.control.read_text(encoding="utf-8")
                      if args.control else "")
    # LOUD, because a bound mismatch makes every disposition below
    # incomparable to the baseline in the direction that flatters this run.
    print(f"baseline bound: {base_bound}")
    if not control_source:
        print("!! no --control: this run is bounded by the WITNESS ALONE. Its "
              "TRUSTED count is an UPPER BOUND and is not comparable to a "
              f"baseline bounded by {base_bound!r}.")
    elif CONTROL not in base_bound:
        print(f"!! --control given but the baseline was bounded by "
              f"{base_bound!r}; this run is bounded MORE tightly, so a fall "
              f"in TRUSTED may be the bound rather than the checks")

    # VARIANTS AND WITNESS MUST SURVIVE. The stage unlinks both when `rewrite`
    # is set, and regenerating variants is 571 calls of the same evidence in a
    # DIFFERENT draw -- which would make a vacuity verdict incomparable to the
    # baseline for a reason nobody could name.
    vpath, wpath = src / "variants.json", src / "witness.py"
    before = (vpath.stat().st_size if vpath.exists() else 0,
              wpath.stat().st_size if wpath.exists() else 0)
    print(f"reusing variants.json ({before[0]:,}B) and witness.py ({before[1]:,}B)")

    args.out.mkdir(parents=True, exist_ok=True)
    port = resumable(
        make_port("api", args.out,
                  settings=PortSettings(model=args.model, effort=args.effort)),
        args.out)

    got = run_oracle_stage(
        requirements=[by_uid[u] for u in target],
        contract_json=contract_json, contract=contract, testplan=testplan,
        stimulus_by_tp=stim_by_tp, port=port, workdir=src,
        base=choose_base(contract), normalized=norm, spec=spec,
        want_variants=True, want_correspondence=True,
        control_source=control_source,
        run_dir=args.run, rewrite=False,
    )

    after = (vpath.stat().st_size if vpath.exists() else 0,
             wpath.stat().st_size if wpath.exists() else 0)
    if after != before:
        # Loud, because a silent regeneration makes every vacuity number below
        # incomparable to the baseline.
        print(f"!! variants/witness CHANGED {before} -> {after}; vacuity "
              f"verdicts are no longer comparable to the baseline")

    disp = dict(got.dispositions or {})
    print(f"\nSTAGE OUTPUT -- {got.rounds} verify/repair round(s), "
          f"bounded by {got.witness_kind}")
    # `rewrite=False` keeps the stage from unlinking variants/witness ABOVE --
    # and the same flag reaches `freeze.freeze`, which then returns the prior
    # set and writes nothing. So `got.trusted` is the BASELINE's oracles while
    # `got.dispositions` describes the ones just generated. Reading the run
    # dir's `oracles.json` as this run's output is then reading the baseline,
    # which is exactly what happened the first time. The sources live only in
    # `--out`'s `oracle_*_response.txt`.
    print("note: rewrite=False, so oracles.json was NOT written and "
          "got.trusted holds the BASELINE oracles; dispositions below are "
          f"this run's. Sources are in {args.out}/oracle_*_response.txt")
    for k, n in sorted(collections.Counter(disp.values()).items()):
        print(f"  {k:16} {n:3}")

    print("\nWHAT MOVED  (baseline -> stage)")
    moved = collections.Counter((label(u), disp.get(u, "?")) for u in target)
    for (a, b), n in sorted(moved.items(), key=lambda kv: -kv[1]):
        print(f"  {a:14} -> {b:16} {n:3}")

    # The field that has to be read beside any gain claimed here: tightening is
    # what makes checks over-strict, and on s-i2c 46% of repaired-and-kept
    # oracles were failed by the control against 6% of never-repaired.
    osar = base.get("over_strict_after_repair")
    print(f"\nover_strict_after_repair: baseline {len(osar or [])}")
    out = args.out / "stage.json"
    out.write_text(json.dumps({
        "target": target, "was": {u: label(u) for u in target},
        "now": disp, "rounds": got.rounds, "witness_kind": got.witness_kind,
        "repairs": {u: v for u, v in (got.repairs or {}).items()},
    }, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
