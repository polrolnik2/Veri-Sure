"""Drive the differential check under cocotb + Verilator.

Kept separate from `differential.py` because that module runs *inside* the
simulator process and this one launches it. Uses cocotb's programmatic runner
(`cocotb_tools.runner`), so there is no Makefile anywhere in specflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiffResult:
    ok: bool
    samples: int
    disagreements: list[dict]

    @property
    def summary(self) -> str:
        if self.ok:
            return f"model agrees with the reference RTL on all {self.samples} samples"
        first = self.disagreements[0]
        return (
            f"{len(self.disagreements)} of {self.samples} samples disagree; "
            f"first: {first['signal']} dut={first['dut']} model={first['model']} "
            f"on {first['stimulus']}"
        )


def run_differential(
    *,
    rtl_path: Path,
    hdl_toplevel: str,
    contract: dict,
    refmodel_path: Path,
    build_dir: Path,
    timeout_s: int = 300,
) -> DiffResult:
    from cocotb_tools.runner import get_runner

    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    ports = contract.get("io") or []
    inputs = [
        {"name": str(p["name"]), "width": int(p.get("width") or 1)}
        for p in ports
        if p.get("dir") == "input" and p.get("name") not in {"clk", "rst"}
    ]
    outputs = [str(p["name"]) for p in ports if p.get("dir") == "output"]
    report = build_dir / "differential.json"

    runner = get_runner("verilator")
    runner.build(
        sources=[str(rtl_path)],
        hdl_toplevel=hdl_toplevel,
        build_args=["--coverage-line", "--coverage-toggle"],
        build_dir=str(build_dir / "sim_build"),
        always=True,
    )
    try:
        runner.test(
            test_module=["specflow.tb.differential"],
            hdl_toplevel=hdl_toplevel,
            test_dir=str(build_dir),
            results_xml=str(build_dir / "results.xml"),
            plusargs=["+verilator+coverage+file+cov_diff.dat"],
            extra_env={
                "SPECFLOW_REFMODEL": str(refmodel_path),
                "SPECFLOW_INPUTS": json.dumps(inputs),
                "SPECFLOW_OUTPUTS": json.dumps(outputs),
                "SPECFLOW_DIFF_REPORT": str(report),
            },
        )
    except SystemExit:
        # cocotb's runner raises when any test fails. A disagreeing model is a
        # *verdict*, not a harness error -- the report on disk is the answer and
        # is read below either way. Letting this propagate would turn "the model
        # is wrong" into "the differential crashed", which is exactly the
        # blame-misattribution this pipeline exists to remove.
        pass

    if not report.exists():
        return DiffResult(False, 0, [{"error": "differential produced no report"}])

    data = json.loads(report.read_text(encoding="utf-8"))
    dis = data.get("disagreements") or []
    return DiffResult(not dis, int(data.get("samples") or 0), dis)
