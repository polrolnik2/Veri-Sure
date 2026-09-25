"""The triple of a run's shipped set as soon as its ORACLE STAGE has finished.

    e7_after_oracles.py <runs-root> <module>

`build_artifacts` ships the cover (`shipped.json`) and scores it only after the
reference-model stage, the longest one in the pipeline, and the figures do not
depend on it. This computes the same set with the pipeline's own functions --
`admitted_pool` exactly as `build_artifacts` admits (the latency finding is
advisory, so nothing is dropped for it), then `_ship_cover` -- so it is the
set the run will ship, not a re-derivation, and
then scores it against golden exactly as `e7_module.py` does:

    1  a corpus directory from the run's specflow/ artifacts, with the run's
       WITNESS standing in as the lock-step model the testbench runtime needs
       to record a trace (it advances beside the DUT and never reaches a
       verdict -- `decide_rtl` reads the DUT side)
    2  shipped.json, by `admitted_pool(...)` and
       `integration._ship_cover`
    3  golden replayed through a suite regenerated from this run's own
       testplan, stimulus and contract (`e6_replay_corpus.py`)
    4  span / blindness / audit of the shipped set (`e7_score_run.py`)

Writes `<runs-root>/results/<module>/after_oracles.json`. Golden is RUN, never
read.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks"))

from run_chipverilog import child_sources, find_task, submodules  # noqa: E402

from specflow.integration import _ship_cover  # noqa: E402
from specflow.oracles_stage import admitted_pool  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402

COPY = ("contract.json", "requirements.json", "normalized.json", "testplan.json",
        "stimulus.json", "coverage_model.json", "probes.json", "oracles.json")


class _Set:
    def __init__(self, trusted, corpus):
        self.trusted, self.corpus = trusted, corpus


class _Body:
    def __init__(self, uid, source):
        self.req_uid, self.source = uid, source


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    runs, module = Path(args[0]).resolve(), args[1]
    sf = runs / module / "specflow"
    if not (sf / "oracles.json").is_file():
        print(f"{module}: no oracles.json yet")
        return 1
    corpus = runs / "after_oracles" / module
    if corpus.exists():
        shutil.rmtree(corpus)
    (corpus / "population").mkdir(parents=True)
    for name in COPY:
        if (sf / name).is_file():
            shutil.copy(sf / name, corpus / name)
    for p in sorted((sf / "population").glob("*.py")):
        shutil.copy(p, corpus / "population" / p.name)
    witness = sf / "witness.py"
    shutil.copy(witness, corpus / "ref_model.py")

    contract = _load(corpus / "contract.json")
    reqs = _load(corpus / "requirements.json")
    reqs = reqs["requirements"] if isinstance(reqs, dict) else reqs
    _t = _load(corpus / "testplan.json")
    plan = _t if isinstance(_t, list) else (_t.get("elements") or [])
    _s = _load(corpus / "stimulus.json")
    stim = _s["testpoints"] if isinstance(_s, dict) else _s
    by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
    blob = _load(corpus / "oracles.json")
    trusted = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                                 clause=x.get("clause", ""), source=x["source"])
               for x in blob.get("oracles") or []]
    cmap = {u: [_Body(u, m.get("source") or "") for m in ms]
            for u, ms in (blob.get("corpus") or {}).items()}
    #: As `build_artifacts` admits: the latency finding is advisory, so no
    #: corpus body is dropped for it.
    pool = admitted_pool(_Set(trusted, cmap), contract, plan)
    population = [p.read_text() for p in sorted((corpus / "population").glob("*.py"))]
    #: `_ship_cover` writes `<run_dir>/specflow/shipped.json`; give it that
    #: layout inside the corpus and move the file beside the rest.
    (corpus / "specflow").mkdir(exist_ok=True)
    shipped = _ship_cover(corpus, pool, population, contract, by_tp)
    written = corpus / "specflow" / "shipped.json"
    if written.is_file():
        shutil.move(str(written), corpus / "shipped.json")
    #: And drop the scaffold: a corpus with a `specflow/` inside it reads to
    #: `e7_score_run.py` as a RUN directory, and it would look in there.
    shutil.rmtree(corpus / "specflow", ignore_errors=True)
    print(f"{module}: {len(trusted)} accepted, pool {len(pool)}, shipped "
          f"{len(shipped) if shipped else 'NONE (no population)'}", flush=True)

    task = find_task(module)
    extras = [str(p) for p in child_sources(submodules(task, module))]
    gold = runs / "gold_after_oracles" / module
    res = runs / "results" / module
    res.mkdir(parents=True, exist_ok=True)
    rc = subprocess.run(
        [sys.executable, str(HERE / "e6_replay_corpus.py"), str(corpus),
         str(task / f"{module}.v"), str(gold)]
        + [a for e in extras for a in ("--extra", e)],
        cwd=str(ROOT), stdout=open(res / "after_oracles_replay.log", "w"),
        stderr=subprocess.STDOUT).returncode
    if rc != 0:
        print(f"golden replay failed; see {res / 'after_oracles_replay.log'}")
        return 1
    return subprocess.run(
        [sys.executable, str(HERE / "e7_score_run.py"), str(corpus), str(gold),
         "--json", str(res / "after_oracles.json")], cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
