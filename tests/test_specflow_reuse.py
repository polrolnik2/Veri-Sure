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
    # `*_, **__`: this stands in for a real function whose signature grows.
    # A double pinned to today's arity turns an added parameter into a
    # test failure that says nothing about behaviour.
    integration.make_port = lambda *_, **__: port
    try:
        res = build_artifacts(
            run_dir=run_dir,
            spec=(run_dir / "prompt.txt").read_text(encoding="utf-8"),
            contract_json=(run_dir / "contract.json").read_text(encoding="utf-8"),
            reuse=reuse, stimulus_agent=False,
            # The generative arm, explicitly: division is the default now,
            # and these fixtures record the generative stage names. This
            # module is about `reuse`, which both arms share.
            divide_s1=False, fanout=False,
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


def test_the_divided_arm_reuses_downstream_stages_too(tmp_path):
    """A stage that was *reused* does not invalidate the stages after it.

    `_run_divided_s1` used to report itself as regenerated unconditionally, so
    the divided arm could never benefit from `--reuse` downstream: the
    requirements came back from disk in milliseconds and then S2, S3 and the
    reference model all re-ran anyway. Measured on one live run before the fix --
    72 + 200 calls and about ten minutes rebuilding artifacts that were already
    on disk and still passing their gates.
    """
    import specflow.integration as integration

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "specflow").mkdir()
    spec = "The sum output is a xor b.\n\nThe cout output is a and b.\n"
    (run_dir / "prompt.txt").write_text(spec, encoding="utf-8")
    contract = json.dumps({
        "io": [
            {"name": "a", "dir": "input", "width": 1},
            {"name": "b", "dir": "input", "width": 1},
            {"name": "sum", "dir": "output", "width": 1},
        ],
        "clocking": {"is_sequential": False},
        "timing": {"sum": {"latency_cycles": 0}},
    })
    # Requirements already on disk, in the shape the divided arm writes.
    (run_dir / "specflow" / "requirements.json").write_text(json.dumps({
        "requirements": [{
            "uid": "REQ-0000", "rev": 1, "text": "The sum output is a xor b.",
            "kind": "function",
            "spec_spans": [{"start": 0, "end": 26, "quote": spec[:26]}],
            "ports": ["sum"], "needs": ["testplan", "refmodel"],
        }]
    }), encoding="utf-8")

    reqs, issues, regenerated = integration._run_divided_s1(
        run_dir=run_dir, spec=spec, contract_json=contract,
        port=None, max_repairs=0, reuse=True,
    )
    assert issues == [] and len(reqs) == 1
    assert regenerated is False, (
        "a reused S1 reported itself as regenerated, which invalidates every "
        "stage after it"
    )


def test_a_regenerated_divided_s1_does_invalidate_downstream(tmp_path):
    """The other direction: a genuinely new S1 must not leave a stale S2."""
    import specflow.integration as integration

    run_dir = tmp_path / "run"
    (run_dir / "specflow").mkdir(parents=True)
    spec = "The sum output is a xor b.\n"
    (run_dir / "prompt.txt").write_text(spec, encoding="utf-8")

    class _Port:
        def complete(self, *, stage, round_, prompt):
            return json.dumps({"kind": "scaffolding", "obligations": []})

    _, _, regenerated = integration._run_divided_s1(
        run_dir=run_dir, spec=spec, contract_json="{}",
        port=_Port(), max_repairs=0, reuse=True,   # nothing on disk to reuse
    )
    assert regenerated is True


def test_a_regenerated_model_is_judged_like_a_freshly_generated_one(tmp_path,
                                                                    monkeypatch):
    """The stale-artifact branch must not hold a model to a weaker standard.

    `--reuse` re-gates a recorded model and regenerates it when the gate now
    fails. That branch called `run_refmodel` with no `judge_port`, no testplan
    and no stimulus, so the replacement was accepted on the mechanical checks
    alone -- while an identical fresh run would have put it through ~77
    per-requirement judgements against its own execution trace. Two standards
    for the same artifact, chosen by whether a previous run happened to exist.
    """
    import specflow.integration as integration

    seen: dict = {}
    real = integration.run_refmodel

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(integration, "run_refmodel", spy)

    run_dir = _certified(tmp_path)
    # Break the recorded model so re-validation fails and the branch fires.
    (run_dir / "specflow" / "ref_model.py").write_text(
        "class Model:\n    pass\n", encoding="utf-8"
    )
    _build(run_dir, reuse=True)

    assert seen, "the regeneration branch never ran; the test proves nothing"
    assert seen.get("judge_port") is not None, (
        "a regenerated model was accepted without the judge that a fresh one faces"
    )
    assert seen.get("testplan"), "regeneration lost the testplan the judge needs"
