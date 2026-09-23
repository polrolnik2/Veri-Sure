"""Pack a run's artifacts into a self-contained corpus that re-runs anywhere.

    e6_pack_corpus.py <run>/specflow <out-dir> [--name NAME]

**A CORPUS IS WORTH MORE THAN THE RUN THAT MADE IT, AND THIS BRANCH HAS ALREADY
LOST ONE.** Four runs' artifacts went with a container reclaim; every number
taken from them had to be recomputed or withdrawn. The artifacts that survived
did so because they were committed, and the ones that could not be re-scored --
`o1`..`o3` -- could not because their CONTRACT was never written down, so a
17-probe run looked compatible with a 24-probe one by uid and was not.

So a packed corpus carries everything a re-score needs and a digest of each
piece, and it states the one fact that made `o1`..`o3` unusable: how many
probes its contract declares.

## What goes in

    contract.json           the interface, probes included -- the thing whose
                            absence made three runs unusable
    requirements.json       S1's output, the span denominator
    normalized.json         the windows the checks were authored against
    testplan.json           testpoints
    stimulus.json           what drove them
    coverage_model.json     bins and checks
    probes.json             the probe stage's own output
    oracles.json            the frozen set AND the corpus of superseded bodies
    population/*.py         the spec-derived designs, which is what makes
                            blindness computable at all
    ref_model.py            the reference model
    scorecard.json          the triple this run recorded, to compare against

## What stays out, and why it is not a loss

`suite/` is rendered from the testplan, the stimulus and the contract, and its
`results/` are simulator output. Both regenerate from what is packed, and
together they are 90% of a run directory. `agent_io/` is prompts and responses:
large, and model traces are gitignored on this branch.

## What this does NOT do

It does not upload anywhere. See `CORPORA.md` for the Hugging Face pathway,
which needs a token this environment does not have.
"""
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

FILES = ("contract.json", "requirements.json", "normalized.json",
         "testplan.json", "stimulus.json", "coverage_model.json",
         "probes.json", "oracles.json", "ref_model.py", "scorecard.json")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe_count(contract: dict) -> int:
    return sum(1 for p in (contract.get("io") or []) if p.get("dir") == "probe")


def pack(src: Path, out: Path, name: str) -> dict:
    root = out / name
    if root.exists():
        shutil.rmtree(root)
    (root / "population").mkdir(parents=True)

    manifest: dict = {
        "name": name,
        "packed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(src),
        "files": {},
        "missing": [],
    }
    for fname in FILES:
        s = src / fname
        if not s.is_file():
            manifest["missing"].append(fname)
            continue
        shutil.copy2(s, root / fname)
        manifest["files"][fname] = {"sha256": sha256(s), "bytes": s.stat().st_size}

    members = sorted((src / "population").glob("*.py"))
    for m in members:
        shutil.copy2(m, root / "population" / m.name)
        manifest["files"][f"population/{m.name}"] = {
            "sha256": sha256(m), "bytes": m.stat().st_size}
    distinct = len({sha256(m) for m in members})
    #: **THE POPULATION'S OWN PROBE LIST, CROSS-CHECKED AGAINST THE CONTRACT.**
    #: A corpus whose designs expose a different set from the one its checks
    #: were authored against cannot be re-scored, and the failure is silent:
    #: every probe reads unavailable and blindness reaches ~100% by
    #: construction. Counting is not enough -- `full2` and `full7` both declare
    #: 24 and two of the names differ, so `full7`'s population under `full2`'s
    #: contract would lose `read_sample_window` and `write_stable_high_phase`
    #: and gain two it does not implement.
    declared: list[frozenset] = []
    for m in members:
        hit = re.search(r"PROBE_PORTS\s*=\s*(\[[^\]]*\])",
                        m.read_text(encoding="utf-8"))
        declared.append(frozenset(eval(hit.group(1))) if hit else frozenset())
    manifest["population"] = {
        "members": len(members), "distinct": distinct,
        "probe_ports_identical_across_members": len(set(declared)) <= 1,
        "probe_ports": sorted(declared[0]) if declared else [],
    }

    #: **THE FACT THAT MADE THREE RUNS UNUSABLE.** `o1`..`o3` share every
    #: req_uid and tp_uid with `full2` and are NOT the same instrument: they
    #: declare 17 probes where full2 declares 24, so replaying one's population
    #: under the other's contract reports every probe unavailable and blindness
    #: reaches 99.7% by construction. Recorded here so the mismatch is visible
    #: before a re-score rather than after it.
    contract_path = root / "contract.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        manifest["contract"] = {
            "module": contract.get("module_name"),
            "declared_probes": _probe_count(contract),
            "probe_names": sorted(
                str(p.get("name")) for p in (contract.get("io") or [])
                if p.get("dir") == "probe" and p.get("name")),
            "ports": sum(1 for p in (contract.get("io") or [])
                         if p.get("dir") in ("input", "output")),
        }

    pp = set(manifest.get("population", {}).get("probe_ports") or ())
    cp = set(manifest.get("contract", {}).get("probe_names") or ())
    if pp or cp:
        manifest["probe_agreement"] = {
            "population_matches_contract": pp == cp,
            "only_in_population": sorted(pp - cp),
            "only_in_contract": sorted(cp - pp),
        }

    blob_path = root / "oracles.json"
    if blob_path.is_file():
        blob = json.loads(blob_path.read_text(encoding="utf-8"))
        corpus = blob.get("corpus") or {}
        manifest["checks"] = {
            "accepted": len(blob.get("oracles") or []),
            "corpus_bodies": sum(len(v) for v in corpus.values()),
            "corpus_requirements": len(corpus),
        }

    card_path = root / "scorecard.json"
    if card_path.is_file():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        #: The triple AS THE RUN RECORDED IT. A re-score under later code will
        #: differ -- the boundary fix alone moved full7's blindness from 0.2450
        #: to 0.2896 -- so this is the baseline to compare against, not a claim
        #: about today's code.
        manifest["recorded_scorecard"] = {
            k: card.get(k) for k in
            ("span", "blindness", "audit", "trusted", "cells", "population",
             "control_judges", "control_convicted_by", "effective_size")}

    (root / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    src, out = Path(args[0]), Path(args[1])
    name = (sys.argv[sys.argv.index("--name") + 1]
            if "--name" in sys.argv else src.parent.name)
    m = pack(src, out, name)
    print(f"packed {name} -> {out / name}")
    print(f"  files       {len(m['files'])}"
          + (f"   MISSING {m['missing']}" if m["missing"] else ""))
    c = m.get("contract") or {}
    print(f"  contract    {c.get('module')} | {c.get('declared_probes')} probes"
          f" | {c.get('ports')} ports")
    p = m.get("population") or {}
    print(f"  population  {p.get('members')} member(s), "
          f"{p.get('distinct')} distinct, probe lists agree across them: "
          f"{p.get('probe_ports_identical_across_members')}")
    a = m.get("probe_agreement")
    if a is not None:
        ok = a["population_matches_contract"]
        print(f"  probes      population matches contract: {ok}"
              + ("" if ok else
                 f"   ONLY IN POPULATION {a['only_in_population']}"
                 f"   ONLY IN CONTRACT {a['only_in_contract']}"))
    k = m.get("checks") or {}
    print(f"  checks      {k.get('accepted')} accepted of "
          f"{k.get('corpus_bodies')} corpus bodies over "
          f"{k.get('corpus_requirements')} requirement(s)")
    r = m.get("recorded_scorecard") or {}
    if r.get("span") is not None:
        print(f"  recorded    span {r['span']:.4f}  blindness "
              f"{r['blindness']:.4f}  audit {r['audit']} "
              f"({r.get('control_convicted_by')}/{r.get('control_judges')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
