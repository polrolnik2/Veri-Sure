"""End-to-end replay against a recorded fixture.

The fixture is a real VerilogEval-v2-EXT problem (Prob024_hadd) whose S1
response was produced once by a Claude subagent through `FilePort`. Replaying it
needs no model, so this runs in CI and is the regression net for the whole S1
path -- prompt composition, parsing, G1 and the loop -- against real spec text
rather than a hand-built fixture.

A Claude subagent is not the production model, so this records *a* model's
behaviour, not *the* model's. It pins the machinery, not prompt quality.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from specflow.model_io import ReplayPort
from specflow.s1_requirements import run_s1

FIXTURE = Path(__file__).parent / "fixtures" / "specflow" / "hadd"


def _run(tmp_path: Path):
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract = (run_dir / "contract.json").read_text(encoding="utf-8")
    return run_s1(
        spec=spec,
        contract_json=contract,
        port=ReplayPort(root=run_dir / "agent_io"),
    )


def test_recorded_response_passes_g1_on_the_first_round(tmp_path):
    res = _run(tmp_path)
    assert res.ok, [i.message for i in res.issues]
    # One round: the gate accepted it outright, so no repair prompt was needed.
    assert res.rounds == 1


def test_decomposition_is_atomic_and_traceable(tmp_path):
    res = _run(tmp_path)
    reqs = res.output.requirements

    # A half adder has exactly two independent output behaviours. One
    # requirement would not be atomic; three would mean the spec was
    # over-decomposed.
    assert len(reqs) == 2

    # Each requirement must own its output port, which is what makes the
    # later requirement -> reference-model-method mapping mechanical.
    owned = {p for r in reqs for p in r.ports}
    assert {"sum", "cout"} <= owned

    for r in reqs:
        assert r.spec_spans, f"{r.uid} quotes no spec text"
        assert "testplan" in r.needs and "refmodel" in r.needs


def test_every_span_is_verbatim_spec_text(tmp_path):
    from specflow.s1_requirements import normalize_spec

    spec = normalize_spec((FIXTURE / "prompt.txt").read_text(encoding="utf-8"))
    res = _run(tmp_path)

    for r in res.output.requirements:
        for sp in r.spec_spans:
            assert spec[sp.start : sp.end] == sp.quote, f"{r.uid} span not verbatim"


def test_replay_is_deterministic(tmp_path):
    a = _run(tmp_path / "a")
    b = _run(tmp_path / "b")
    assert a.output.model_dump() == b.output.model_dump()
