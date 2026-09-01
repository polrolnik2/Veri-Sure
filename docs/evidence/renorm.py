"""Re-run c1-i2c's NORMALIZATION stage live, with everything that has landed.

The question this run exists to answer is the untested one: `gate_one` now
rejects a route with an empty `when`, and replaying c1-i2c's recorded responses
says 78 of 127 requirements fail ONLY on that check. Prior evidence cuts against
convergence -- all 15 of that run's gate-failures spent their whole repair budget
and still failed -- so the blast radius has to be measured, not assumed.

Three things are being read off one run:

  1. do the 78 recover, and in how many rounds
  2. do the five requirements lost to the `observed_via` shape come back
     (REQ-0010, 0017, 0048, 0078, 0100)
  3. what the malformed count is against c1-i2c's 15

SAME MODEL AND EFFORT AS THE ORIGINAL, pinned explicitly rather than inherited:
c1-i2c's own meta records `gpt-5-mini` at medium on the responses surface. A
different model would make the comparison a comparison of models.

NOTHING HERE SEES THE GOLDEN RTL. Normalization is upstream of every design.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

SRC = Path("/home/user/runs/c1-i2c")
LOST = ["REQ-0010", "REQ-0017", "REQ-0048", "REQ-0078", "REQ-0100"]


def main() -> int:
    from specflow.model_io import PortSettings, make_port, resumable
    from specflow.normalize import (
        resolve_indirect,
        run_normalize_fanout,
        write_artifacts,
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n1-i2c")
    ap.add_argument("--limit", type=int, default=0, help="0 = every requirement")
    ap.add_argument("--max-repairs", type=int, default=3,
                    help="3 gives r0..r3, the four rounds c1-i2c recorded")
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--no-indirect", action="store_true",
                    help="skip the second pass; the gate question is in the first")
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    if run_dir.exists() and not a.resume:
        shutil.rmtree(run_dir)
    (run_dir / "specflow").mkdir(parents=True, exist_ok=True)

    reqs = json.loads((SRC / "specflow/requirements.json").read_text())["requirements"]
    if a.limit:
        keep = {u for u in LOST}
        reqs = [r for r in reqs if r.get("uid") in keep][:a.limit] or reqs[:a.limit]
    contract_json = (SRC / "contract.json").read_text()
    contract = json.loads(contract_json)

    # The small-model path is what the fanned-out stages take; pinning both
    # halves means neither an inherited OPENAI_MODEL nor an inherited effort
    # can silently change what this measures.
    settings = PortSettings(model=a.model, effort=a.effort,
                            small_model=a.model, small_effort=a.effort)
    port = resumable(make_port("api", run_dir / "agent_io", settings=settings),
                     run_dir / "agent_io")

    t0 = time.time()
    print(f"normalizing {len(reqs)} requirements on {a.model}/{a.effort}, "
          f"max_repairs={a.max_repairs}", flush=True)
    normalized, results = run_normalize_fanout(
        requirements=reqs, contract_json=contract_json, contract=contract,
        port=port, max_repairs=a.max_repairs)
    print(f"  direct pass: {len(normalized)}/{len(reqs)} normalized "
          f"in {time.time()-t0:.0f}s", flush=True)

    if not a.no_indirect:
        normalized, _ = resolve_indirect(
            normalized=normalized, requirements=reqs,
            contract_json=contract_json, contract=contract,
            port=port, max_repairs=a.max_repairs)
        print(f"  after indirect: {len(normalized)}", flush=True)

    write_artifacts(run_dir, normalized, results, requirements=reqs)

    # --- what the run was launched to measure -------------------------------
    by_uid = {n.req_uid: n for n in normalized}
    rounds = {}
    for req, res in zip(reqs, results):
        rounds[req.get("uid")] = len(getattr(res, "attempts", None) or []) or None

    empty_when = sum(1 for n in normalized for r in n.observed_via
                     if not (r.when or "").strip())
    total_routes = sum(len(n.observed_via) for n in normalized)
    still_failing = [r.get("uid") for r, res in zip(reqs, results) if not res.ok]

    print()
    print(f"normalized      {len(normalized)}/{len(reqs)}")
    print(f"gate-failed     {len(still_failing)}  (c1-i2c: 15)")
    print(f"routes          {total_routes}, empty `when`: {empty_when} "
          f"(c1-i2c frozen: 180 of 238)")
    print("the five lost   " + "  ".join(
        f"{u}={'OK' if u in by_uid else 'FAIL'}" for u in LOST))
    if still_failing:
        print(f"\nstill failing: {' '.join(sorted(x for x in still_failing if x))}")
    json.dump({"normalized": sorted(by_uid), "gate_failed": sorted(
        x for x in still_failing if x), "empty_when": empty_when,
        "total_routes": total_routes, "rounds": rounds, "seconds": time.time() - t0},
        open(Path(__file__).parent / "renorm.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
