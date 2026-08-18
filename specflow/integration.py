"""Bridge between `eda_agent`'s node-level run and the specflow pipeline.

Kept in `specflow/` rather than threaded through `top_agent.py` so the two can be
tested apart: everything here is a pure function of a run directory plus a model
port, and none of it needs the orchestrator.

The one thing this genuinely fixes on the `eda_agent` side is the spec. `spec:
str` is already a required parameter of `TopAgent.run` (`:963-973`) and both
entry points supply it, but only `cli.py:74` writes it to disk. specflow reads
`prompt.txt`, so `ensure_prompt_file` makes the benchmark path carry it too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .coverage import build_report, freeze_denominator
from .gate import evaluate
from .model_io import make_port
from .refmodel.compose import run_refmodel
from .refmodel.compose import write_artifacts as write_refmodel
from .run import reconcile, run_suite
from .s1_requirements import renumber as renumber_reqs
from .s1_requirements import run_s1
from .s1_requirements import write_artifacts as write_s1
from .s2_testplan import renumber as renumber_tps
from .s2_testplan import run_s2
from .s2_testplan import write_artifacts as write_s2
from .s3_coverage import renumber as renumber_cov
from .s3_coverage import run_s3
from .s3_coverage import write_artifacts as write_s3
from .schema import GateVerdict, Issue
from .tb.render import gate_g5, render_suite


def ensure_prompt_file(run_dir: Path, spec: str) -> Path:
    """Persist the spec so specflow (and any offline replay) can read it.

    `cli.py` does this for the `run` subcommand; the benchmark path builds its
    prompt separately and never writes it, so a benchmark node had no spec on
    disk at all.
    """
    path = Path(run_dir) / "prompt.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(spec.rstrip() + "\n", encoding="utf-8")
    return path


@dataclass
class BuildResult:
    ok: bool
    stage: str = ""
    issues: list[Issue] | None = None
    suite_dir: Path | None = None
    refmodel_path: Path | None = None
    bins: list[dict] | None = None

    @property
    def reason(self) -> str:
        if self.ok:
            return "artifacts built"
        n = len(self.issues or ())
        return f"{self.stage} gate failed with {n} issue(s)"


def build_artifacts(
    *,
    run_dir: Path,
    spec: str,
    contract_json: str,
    model_port: str = "replay",
    max_repairs: int = 3,
) -> BuildResult:
    """S1 -> S2 -> S3 -> reference model -> rendered suite, gate by gate.

    Stops at the first gate that fails, and says which. Exhaustion is a hard
    failure everywhere: a stage that could not be certified never propagates a
    partial artifact downstream.
    """
    run_dir = Path(run_dir)
    ensure_prompt_file(run_dir, spec)
    port = make_port(model_port, run_dir / "agent_io")
    contract = json.loads(contract_json) if contract_json.strip() else {}

    s1 = run_s1(spec=spec, contract_json=contract_json, port=port,
                max_repairs=max_repairs)
    renumber_reqs(s1.output)
    write_s1(run_dir, s1)
    if not s1.ok:
        return BuildResult(False, "S1", s1.issues)

    reqs = [r.model_dump() for r in s1.output.requirements]

    s2 = run_s2(requirements=reqs, contract_json=contract_json, port=port,
                max_repairs=max_repairs)
    renumber_tps(s2.output)
    write_s2(run_dir, s2)
    if not s2.ok:
        return BuildResult(False, "S2", s2.issues)

    tps = [e.model_dump() for e in s2.output.elements]

    s3 = run_s3(testplan=tps, contract_json=contract_json, port=port,
                max_repairs=max_repairs)
    renumber_cov(s3.output)
    write_s3(run_dir, s3)
    if not s3.ok:
        return BuildResult(False, "S3", s3.issues)

    bins = [b.model_dump() for b in s3.output.bins]
    checks = [c.model_dump() for c in s3.output.checks]

    rm, source = run_refmodel(
        requirements=reqs, contract_json=contract_json, port=port,
        workdir=run_dir / "specflow" / "_refmodel_check", max_repairs=max_repairs,
    )
    refmodel_path = write_refmodel(run_dir, rm, source)
    if not rm.ok:
        return BuildResult(False, "refmodel", rm.issues)

    suite_dir = run_dir / "specflow" / "suite"
    manifest = render_suite(
        testplan=tps, bins=bins, checks=checks, contract=contract, out_dir=suite_dir
    )
    g5 = gate_g5(out_dir=suite_dir, manifest=manifest, bins=bins, checks=checks)
    if any(i.severity == "error" for i in g5):
        return BuildResult(False, "G5", g5)

    return BuildResult(
        True, suite_dir=suite_dir, refmodel_path=refmodel_path, bins=bins
    )


def judge(
    *,
    rtl_path: Path,
    hdl_toplevel: str,
    suite_dir: Path,
    refmodel_path: Path,
    bins: list[dict],
    iteration: int = 0,
    extra_sources: Sequence[Path | str] = (),
    include_dirs: Sequence[Path | str] = (),
) -> tuple[GateVerdict, dict]:
    """One evaluation: run the suite and return the three-valued verdict.

    This is the replacement for `sim_reviewer.sim_review`'s two-valued answer.
    That function decides pass or fail from log markers, so `is_pass=True,
    mismatch_cnt=0` means both "everything was checked and passed" and "nothing
    ran". Here the verdict is data written by the runtime, per testpoint, and
    an unexercised testpoint is its own outcome rather than a silent success.
    """
    suite_dir = Path(suite_dir)
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))

    outcome = run_suite(
        rtl_path=rtl_path, hdl_toplevel=hdl_toplevel, suite_dir=suite_dir,
        refmodel_path=refmodel_path, iteration=iteration,
        extra_sources=extra_sources, include_dirs=include_dirs,
    )
    denominator = freeze_denominator(bins, suite_dir / "denominator.json")
    report = build_report(denominator=denominator, results=outcome.results)

    verdict = evaluate(
        results=outcome.results,
        report=report,
        missing_records=reconcile(outcome, manifest),
        build_ok=outcome.build_ok,
        build_log=outcome.build_log,
    )
    return verdict, {
        "results": {u: r.status for u, r in outcome.results.items()},
        "uncovered": report.undisposed,
        "build_ok": outcome.build_ok,
    }


def failure_payload(suite_dir: Path) -> list[dict]:
    """Every failing check across every testpoint, with values and stimulus.

    The replacement for a scraped simulation log. `rtl_editor` currently gets a
    log excerpt filtered by keyword, and the recorded failure of that approach
    was 210 MISMATCH lines carrying two actual values. Here each entry already
    carries the check, the expected and actual values, and the stimulus that
    produced them -- and every failing testpoint is present, not just the first.
    """
    payload: list[dict] = []
    for path in sorted((Path(suite_dir) / "results").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "FAIL":
            continue
        payload.append(
            {
                "testpoint": data["tp_uid"],
                "failed_checks": data.get("checks_failed") or [],
                "mismatches": data.get("mismatches") or [],
            }
        )
    return payload
