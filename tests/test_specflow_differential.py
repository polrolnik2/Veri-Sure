"""M4's real test: the reference model against golden RTL, both directions.

Golden RTL is a validation instrument used at test time only. It never enters
the model's input bundle -- the model is frozen before this runs -- which is what
keeps this an independent check rather than a circular one.

Both directions are tested because a differential that cannot fail is worthless:
it would certify any model at all.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.tb.diffrun import run_differential

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "specflow" / "hadd"
GOLDEN = (
    REPO
    / "benchmarks"
    / "verilogeval-v2-ext"
    / "dataset_spec-to-rtl"
    / "Prob024_hadd_ref.sv"
)

pytestmark = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)


def _refmodel(tmp_path: Path) -> Path:
    """Rebuild the model from the recorded fixture, so this test exercises the
    generated artifact rather than a hand-written stand-in."""
    from specflow.model_io import ReplayPort
    from specflow.refmodel.compose import run_refmodel, write_artifacts
    from specflow.s1_requirements import run_s1

    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract = (run_dir / "contract.json").read_text(encoding="utf-8")
    port = ReplayPort(root=run_dir / "agent_io")

    s1 = run_s1(spec=spec, contract_json=contract, port=port)
    assert s1.ok
    result, source = run_refmodel(
        requirements=[r.model_dump() for r in s1.output.requirements],
        contract_json=contract,
        port=port,
        workdir=run_dir / "check",
    )
    assert result.ok, [i.message for i in result.issues]
    return write_artifacts(run_dir, result, source)


def _contract() -> dict:
    return json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))


def test_generated_model_agrees_with_golden_rtl(tmp_path):
    res = run_differential(
        rtl_path=GOLDEN,
        hdl_toplevel="RefModule",
        contract=_contract(),
        refmodel_path=_refmodel(tmp_path),
        build_dir=tmp_path / "diff",
    )
    assert res.ok, res.summary
    # Four one-bit input combinations: the sweep must be exhaustive, not
    # sampled. A handful of random samples can agree by luck on exactly the
    # corner the specification cared about.
    assert res.samples == 4


def test_differential_detects_a_wrong_model(tmp_path):
    """The gate must fail when it should, or it certifies anything."""
    path = _refmodel(tmp_path)
    # Break the carry only. The fixture factors both outputs into one helper --
    # they are two sentences about one piece of hardware -- so the substitution
    # targets the returned carry expression rather than a per-requirement method.
    broken = path.read_text(encoding="utf-8").replace(
        "self.mask(a & b, 1)", "self.mask(a | b, 1)"
    )
    assert "a | b" in broken, "the substitution did not apply"
    wrong = path.parent / "wrong_model.py"
    wrong.write_text(broken, encoding="utf-8")

    res = run_differential(
        rtl_path=GOLDEN,
        hdl_toplevel="RefModule",
        contract=_contract(),
        refmodel_path=wrong,
        build_dir=tmp_path / "diff_bad",
    )
    assert not res.ok
    # AND and OR differ on exactly the two one-hot inputs.
    assert len(res.disagreements) == 2
    assert all(d["signal"] == "cout" for d in res.disagreements)
