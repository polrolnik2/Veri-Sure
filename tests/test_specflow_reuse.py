"""Reusing certified artifacts, and the two rules that keep it honest.

A full node is ~18 minutes of model calls, almost all of it in S1-S3 and the
reference model. Re-running those to reach a fix in a later stage is waste --
but a cache that is merely trusted is worse than no cache, so:

1. **The gate is always re-run**, never read from the recorded verdict. The G1
   whitespace fix is the live example: the same `requirements.json` scored 2
   errors before it and 0 after.
2. **Once a stage regenerates, everything after it does too.** A cached testplan
   is only valid against the requirements that produced it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from specflow.integration import build_artifacts
from specflow.model_io import ReplayPort
from specflow.refmodel.compose import run_refmodel, write_artifacts as write_refmodel
from specflow.s1_requirements import run_s1, write_artifacts as write_s1
from specflow.s2_testplan import run_s2, write_artifacts as write_s2
from specflow.s3_coverage import run_s3, write_artifacts as write_s3

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "specflow" / "hadd"


class _CountingPort:
    """A port that records every stage it is asked to serve."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[str] = []

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.calls.append(stage)
        return self.inner.complete(stage=stage, round_=round_, prompt=prompt)


def _certified(tmp_path: Path) -> Path:
    """A run directory whose four stages are already on disk and certified."""
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract_json = (run_dir / "contract.json").read_text(encoding="utf-8")
    port = ReplayPort(root=run_dir / "agent_io")

    s1 = run_s1(spec=spec, contract_json=contract_json, port=port)
    write_s1(run_dir, s1)
    reqs = [r.model_dump() for r in s1.output.requirements]
    s2 = run_s2(requirements=reqs, contract_json=contract_json, port=port)
    write_s2(run_dir, s2)
    tps = [e.model_dump() for e in s2.output.elements]
    s3 = run_s3(testplan=tps, contract_json=contract_json, port=port)
    write_s3(run_dir, s3)
    rm, source = run_refmodel(
        requirements=reqs, contract_json=contract_json, port=port,
        workdir=run_dir / "specflow" / "_refmodel_check",
    )
    write_refmodel(run_dir, rm, source)
    return run_dir


def _build(run_dir: Path, *, reuse: bool):
    port = _CountingPort(ReplayPort(root=run_dir / "agent_io"))
    import specflow.integration as integration

    real_make_port = integration.make_port
    integration.make_port = lambda kind, root, stats=None: port
    try:
        res = build_artifacts(
            run_dir=run_dir,
            spec=(run_dir / "prompt.txt").read_text(encoding="utf-8"),
            contract_json=(run_dir / "contract.json").read_text(encoding="utf-8"),
            reuse=reuse, stimulus_agent=False,
        )
    finally:
        integration.make_port = real_make_port
    return res, port.calls


def test_reuse_makes_no_model_calls_when_every_gate_still_passes(tmp_path):
    run_dir = _certified(tmp_path)
    res, calls = _build(run_dir, reuse=True)
    assert res.ok, res.reason
    assert calls == [], f"reuse still called the model for {calls}"
    assert (run_dir / "specflow" / "suite" / "manifest.json").exists()


def test_without_reuse_every_stage_is_regenerated(tmp_path):
    run_dir = _certified(tmp_path)
    res, calls = _build(run_dir, reuse=False)
    assert res.ok, res.reason
    assert {"s1", "s2", "s3", "refmodel"} <= set(calls)


def test_a_stale_artifact_is_regenerated_not_trusted(tmp_path):
    """The recorded verdict says ok; the gate says otherwise. The gate wins."""
    run_dir = _certified(tmp_path)
    path = run_dir / "specflow" / "requirements.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # A quote that is not spec text at all: G1 must reject it on re-gate.
    data["requirements"][0]["spec_spans"] = [
        {"start": 0, "end": 10, "quote": "this sentence is not in the spec"}
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    # `s1_gate.json` still records ok=true, untouched.
    assert json.loads((run_dir / "specflow" / "s1_gate.json").read_text())["ok"]

    res, calls = _build(run_dir, reuse=True)
    assert res.ok, res.reason
    assert "s1" in calls, "a corrupt artifact was reused on the recorded verdict"


def test_regenerating_a_stage_invalidates_everything_after_it(tmp_path):
    """A cached testplan is only valid against the requirements that made it."""
    run_dir = _certified(tmp_path)
    (run_dir / "specflow" / "requirements.json").unlink()

    res, calls = _build(run_dir, reuse=True)
    assert res.ok, res.reason
    assert calls[0] == "s1"
    assert {"s2", "s3", "refmodel"} <= set(calls), (
        f"downstream stages were reused against regenerated requirements: {calls}"
    )


def test_a_broken_reference_model_is_regenerated(tmp_path):
    """G4 is re-run by executing the model, so a model that no longer runs
    cannot be reused on its recorded verdict."""
    run_dir = _certified(tmp_path)
    (run_dir / "specflow" / "ref_model.py").write_text(
        "class Model:\n    def evaluate(self, i):\n        raise RuntimeError('nope')\n",
        encoding="utf-8",
    )
    res, calls = _build(run_dir, reuse=True)
    assert res.ok, res.reason
    assert "refmodel" in calls
    assert "s1" not in calls, "an unrelated stage was invalidated"
