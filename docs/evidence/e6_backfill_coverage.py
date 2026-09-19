"""Give a pre-fix run directory the bins its staged testpoints never got.

    python docs/evidence/e6_backfill_coverage.py <src_run> <dst_run>

A run that staged testpoints before `_staged_coverage` existed wrote a
coverage model that disagrees with its own testplan, so it fails its own
`gate_s3` and `--reuse` re-buys S3 and everything below it. New runs mint the
bins as they stage; this is the migration for the ones already on disk.

**IT CALLS THE PRODUCTION MINTER.** `_staged_coverage` and nothing else, so a
backfilled artifact is the artifact the pipeline would have written, and the
gate it then passes is the same gate. Anything hand-rolled here would be a fact
about this script.

Testpoints whose requirement `normalize` says states no observable obligation
are DROPPED rather than given a bin: staging them was the defect, they carry no
check, and minting a bin with no signal to compare would only move the gate
failure. On the run this was written for that is 60 of 111.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

from specflow import probes as P  # noqa: E402
from specflow.oracles_stage import _staged_coverage  # noqa: E402
from specflow.s2_testplan import TestplanOutput  # noqa: E402
from specflow.s3_coverage import CoverageOutput, gate  # noqa: E402

SRC, DST = Path(sys.argv[1]), Path(sys.argv[2])
if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, symlinks=True,
                ignore=shutil.ignore_patterns("agent_io", "results", "sim_build"))

sf = DST / "specflow"
base = json.loads(Path("benchmarks/baselines/i2c_master_bit_ctrl/arm_a/"
                       "contract.json").read_text())
contract = P.in_force(DST, base)
P.write_contract(DST, contract)

els = [e.model_dump() for e in TestplanOutput.model_validate(
    json.loads((sf / "testplan.json").read_text())).elements]
cov = json.loads((sf / "coverage_model.json").read_text())
bins, checks = list(cov.get("bins") or []), list(cov.get("checks") or [])
norm = {n["req_uid"]: n for n in
        json.loads((sf / "normalized.json").read_text())["normalized"]}
reqs = {r["uid"]: r for r in
        json.loads((sf / "requirements.json").read_text())["requirements"]}
stim = {s["tp_uid"]: s["stimulus_steps"] for s in
        json.loads((sf / "stimulus.json").read_text())["testpoints"]}


def unobservable(req_uid: str) -> bool:
    sh = norm.get(req_uid) or {}
    return bool(str(sh.get("unobservable_reason") or "").strip()
                and not (sh.get("observable") or ()))


def errors(elements, b, c):
    return [i for i in gate(elements, CoverageOutput.model_validate(
        {"reasoning": "", "bins": b, "checks": c}), contract)
        if i.severity == "error"]


print(f"gate errors before: {len(errors(els, bins, checks))}", flush=True)
covered = {b["covers"][0].split("@")[0] for b in bins if b.get("covers")}
keep, dropped, minted = [], [], 0
for e in els:
    req_uid = (e.get("covers") or ["@"])[0].split("@")[0]
    if e["uid"] not in covered and unobservable(req_uid):
        dropped.append(e["uid"])
        continue
    keep.append(e)
    if e["uid"] not in covered:
        _staged_coverage(e["uid"], req_uid, reqs.get(req_uid, {}),
                         norm.get(req_uid, {}), contract=contract,
                         bins=bins, checks=checks,
                         stimulus=str(e.get("stimulus") or ""))
        minted += 1

left = errors(keep, bins, checks)
print(f"minted {minted} bin/check pair(s); dropped {len(dropped)} testpoint(s) "
      f"whose requirement states no observable obligation")
print(f"gate errors after:  {len(left)}")
for i in left[:5]:
    print("  ", i.path, i.message[:160])
if left:
    print("NOT written: the backfilled artifact does not pass its own gate")
    raise SystemExit(1)

(sf / "testplan.json").write_text(
    json.dumps({"elements": keep}, indent=2, ensure_ascii=False) + "\n")
cov["bins"], cov["checks"] = bins, checks
(sf / "coverage_model.json").write_text(
    json.dumps(cov, indent=2, ensure_ascii=False) + "\n")
(sf / "stimulus.json").write_text(json.dumps({"testpoints": [
    {"tp_uid": u, "stimulus_steps": s} for u, s in stim.items()
    if u not in set(dropped)]}, indent=2, ensure_ascii=False) + "\n")

#: **AND THE RENDERED SUITE, WHICH IS WHAT ACTUALLY RUNS.** Trimming the
#: testplan and leaving `suite/` alone leaves a run whose simulation and whose
#: plan disagree: the first pass of this dropped 60 testpoints and then
#: executed 482 of them anyway, because every one still had a rendered module.
#: Not unsound -- the scoping rule is that a check is replayed where the
#: stimulus goes -- but it is the same artifacts-disagree defect this whole
#: file exists to repair, one directory over.
gone = {u.replace("-", "") for u in dropped}
suite = sf / "suite"
removed = 0
for f in sorted((suite / "tests").glob("test_TP*.py")):
    if f.stem.replace("test_", "") in gone:
        f.unlink()
        removed += 1
man = suite / "manifest.json"
if man.is_file():
    doc = json.loads(man.read_text())
    doc["modules"] = [m for m in doc.get("modules") or []
                      if m.replace("test_", "") not in gone]
    man.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"pruned {removed} rendered test module(s); manifest now "
          f"{len(doc['modules'])}")
print(f"wrote {DST}  ({len(keep)} testpoints, {len(bins)} bins)")
