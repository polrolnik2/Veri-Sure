"""Per-stage entry points.

Every stage is runnable and inspectable on its own, so a milestone can be driven
and judged without the surrounding loop. With `--model-port file` a stage emits
its prompt and exits; a Claude subagent (or anything else) writes the response
file and the same command is re-run to ingest it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import s2_testplan, s3_coverage
from .model_io import PendingResponse, make_port
from .s1_requirements import renumber, run_s1, write_artifacts
from .schema import render_issues


def _read(path: Path, what: str) -> str:
    if not path.exists():
        raise SystemExit(f"missing {what}: {path}")
    return path.read_text(encoding="utf-8")


def _contract(run_dir: Path) -> str:
    p = run_dir / "contract.json"
    return p.read_text(encoding="utf-8") if p.exists() else "{}"


def _artifact(run_dir: Path, name: str) -> dict:
    path = run_dir / "specflow" / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"missing upstream artifact {path}; run the earlier stage first")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_s1(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    spec = _read(run_dir / "prompt.txt", "spec")
    contract_path = run_dir / "contract.json"
    contract_json = contract_path.read_text(encoding="utf-8") if contract_path.exists() else "{}"

    port = make_port(args.model_port, run_dir / "agent_io")
    try:
        result = run_s1(
            spec=spec,
            contract_json=contract_json,
            port=port,
            max_repairs=args.max_repairs,
        )
    except PendingResponse as pending:
        # The expected outcome of an emit, not an error. Exit 3 so a caller can
        # distinguish "waiting for a response" from "the gate failed" (exit 1).
        print(pending, file=sys.stderr)
        return 3

    renumber(result.output)
    path = write_artifacts(run_dir, result)

    n = len(result.output.requirements)
    if result.ok:
        print(f"S1 ok: {n} requirements in {result.rounds} round(s) -> {path}")
        if result.output.underdetermined:
            print(f"  {len(result.output.underdetermined)} underdetermined:")
            for u in result.output.underdetermined:
                print(f"    {u.req_uid}: {u.question}")
        return 0

    print(f"S1 FAILED after {result.rounds} round(s); {n} requirements", file=sys.stderr)
    print(render_issues(result.issues), file=sys.stderr, end="")
    return 1


def cmd_s2(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    reqs = _artifact(run_dir, "requirements")["requirements"]
    port = make_port(args.model_port, run_dir / "agent_io")
    try:
        result = s2_testplan.run_s2(
            requirements=reqs,
            contract_json=_contract(run_dir),
            port=port,
            max_repairs=args.max_repairs,
        )
    except PendingResponse as pending:
        print(pending, file=sys.stderr)
        return 3

    s2_testplan.renumber(result.output)
    path = s2_testplan.write_artifacts(run_dir, result)
    n = len(result.output.elements)
    if result.ok:
        print(f"S2 ok: {n} testplan elements in {result.rounds} round(s) -> {path}")
        return 0
    print(f"S2 FAILED after {result.rounds} round(s); {n} elements", file=sys.stderr)
    print(render_issues(result.issues), file=sys.stderr, end="")
    return 1


def cmd_s3(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    tps = _artifact(run_dir, "testplan")["elements"]
    port = make_port(args.model_port, run_dir / "agent_io")
    try:
        result = s3_coverage.run_s3(
            testplan=tps,
            contract_json=_contract(run_dir),
            port=port,
            max_repairs=args.max_repairs,
        )
    except PendingResponse as pending:
        print(pending, file=sys.stderr)
        return 3

    s3_coverage.renumber(result.output)
    path = s3_coverage.write_artifacts(run_dir, result)
    nb, nc = len(result.output.bins), len(result.output.checks)
    if result.ok:
        print(f"S3 ok: {nb} bins, {nc} checks in {result.rounds} round(s) -> {path}")
        return 0
    print(f"S3 FAILED after {result.rounds} round(s); {nb} bins, {nc} checks",
          file=sys.stderr)
    print(render_issues(result.issues), file=sys.stderr, end="")
    return 1


def cmd_refmodel(args: argparse.Namespace) -> int:
    from .refmodel import compose

    run_dir = Path(args.run_dir)
    reqs = _artifact(run_dir, "requirements")["requirements"]
    port = make_port(args.model_port, run_dir / "agent_io")
    try:
        result, source = compose.run_refmodel(
            requirements=reqs,
            contract_json=_contract(run_dir),
            port=port,
            workdir=run_dir / "specflow" / "_refmodel_check",
            max_repairs=args.max_repairs,
        )
    except PendingResponse as pending:
        print(pending, file=sys.stderr)
        return 3

    path = compose.write_artifacts(run_dir, result, source)
    n = len(result.output.fragments)
    if result.ok:
        print(f"refmodel ok: {n} fragments in {result.rounds} round(s) -> {path}")
        for u in result.output.underdetermined:
            print(f"  underdetermined: {u}")
        return 0
    print(f"refmodel FAILED after {result.rounds} round(s); {n} fragments",
          file=sys.stderr)
    print(render_issues(result.issues), file=sys.stderr, end="")
    return 1


def cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.run_dir) / "specflow" / f"{args.artifact}.json"
    if not path.exists():
        raise SystemExit(f"no such artifact: {path}")
    print(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="specflow")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("s1", help="decompose the spec into requirements (G1)")
    s1.add_argument("--run-dir", required=True)
    s1.add_argument("--model-port", default="file", choices=["file", "replay", "api"])
    s1.add_argument("--max-repairs", type=int, default=3)
    s1.set_defaults(func=cmd_s1)

    s2 = sub.add_parser("s2", help="requirements -> testplan (G2)")
    s2.add_argument("--run-dir", required=True)
    s2.add_argument("--model-port", default="file", choices=["file", "replay", "api"])
    s2.add_argument("--max-repairs", type=int, default=3)
    s2.set_defaults(func=cmd_s2)

    s3 = sub.add_parser("s3", help="testplan -> bins and checks (G3)")
    s3.add_argument("--run-dir", required=True)
    s3.add_argument("--model-port", default="file", choices=["file", "replay", "api"])
    s3.add_argument("--max-repairs", type=int, default=3)
    s3.set_defaults(func=cmd_s3)

    rm = sub.add_parser("refmodel", help="requirements -> Python reference model (G4)")
    rm.add_argument("--run-dir", required=True)
    rm.add_argument("--model-port", default="file", choices=["file", "replay", "api"])
    rm.add_argument("--max-repairs", type=int, default=3)
    rm.set_defaults(func=cmd_refmodel)

    show = sub.add_parser("show", help="pretty-print a specflow artifact")
    show.add_argument("--run-dir", required=True)
    show.add_argument("artifact")
    show.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
