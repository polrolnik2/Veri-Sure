"""Distil a run directory into the numbers `docs/convergence-plan.md` cites.

Every measurement in that document was taken in a scratch directory under
`/tmp`, on a container that is reclaimed after a period of inactivity. 3.3 GB of
run artifacts is not worth committing and the numbers derived from them are:
without this, a reader can check the plan's arithmetic against nothing, and a
container restart takes the evidence with it.

What it keeps, per run: the oracle dispositions, the per-turn verdict counts,
the stop reason, liveness, discrimination against the control, and the gate.
What it drops: `agent_io` (prompts and responses, 3-27 MB per run), the
stimulus, and every intermediate artifact -- none of which any claim rests on.

The reference models are copied separately and deliberately. They are ~12 KB
each and they are the only artifact `golden_check` needs, so keeping them is
what makes the separation table reproducible rather than merely reported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

#: Verdict keys worth carrying. Zeroes are kept for `verdict.counts`'s reason:
#: a key that appears only when non-zero reads as "none found" when it means
#: "never looked".
VERDICTS = ("CONFORMS", "VIOLATES", "NOT_EXERCISED", "UNOBSERVABLE",
            "ORACLE_INVALID", "VACUOUS", "UNDECIDED")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return None


def turns(run: Path) -> list[dict]:
    """Per-turn verdicts, in turn order, with what each turn actually did."""
    out = []
    judge = run / "specflow" / "judge"
    if not judge.is_dir():
        return out
    for d in sorted(judge.glob("r*"), key=lambda p: int(p.name[1:] or 0)):
        body = _load(d / "trust.json")
        if not body:
            continue
        counts = (body.get("mechanical_verdicts") or {}).get("counts") or {}
        out.append({
            "turn": d.name,
            "counts": {k: counts.get(k, 0) for k in VERDICTS},
            "stimulus_added": len(body.get("stimulus_added") or []),
            "idle_turns": body.get("idle_turns"),
            "stopped_because": body.get("stopped_because") or "",
            # The split that made "46 CONFORMS" readable: a pass from a check
            # that could not have failed is not the same result as one from a
            # check that could.
            "conforms_by_liveness": body.get("conforms_by_liveness"),
            "violates_the_witness_also_fails":
                body.get("violates_the_witness_also_fails") or [],
        })
    return out


def oracles(run: Path) -> dict:
    body = _load(run / "specflow" / "oracles.json") or {}
    disp = body.get("dispositions") or {}
    tally: dict[str, int] = {}
    for value in disp.values():
        tally[value] = tally.get(value, 0) + 1
    return {
        "frozen": len(body.get("oracles") or []),
        "dispositions": tally,
        "by_requirement": disp,
        "rounds": body.get("rounds"),
        "repaired": len(body.get("repairs") or {}),
        "correspondence_checked": body.get("correspondence_checked"),
        "vacuity_checked": body.get("vacuity_checked"),
    }


def gate(run: Path) -> dict:
    body = _load(run / "specflow" / "refmodel_gate.json")
    if not body:
        return {"present": False}
    issues = body.get("issues") or []
    by_severity: dict[str, int] = {}
    for issue in issues:
        key = str(issue.get("severity", "?"))
        by_severity[key] = by_severity.get(key, 0) + 1
    return {"present": True, "ok": body.get("ok"),
            "issues": len(issues), "by_severity": by_severity}


def distil(run: Path) -> dict:
    return {
        "run": run.name,
        "oracles": oracles(run),
        "turns": turns(run),
        "adequacy": (_load(run / "specflow" / "adequacy_r0.json") or {}
                     ).get("counts"),
        "gate": gate(run),
        "rtl_produced": (run / "rtl.sv").exists(),
        "model_present": (run / "specflow" / "ref_model.py").exists(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+", help="run directories to distil")
    ap.add_argument("--out", required=True, help="directory to write into")
    ap.add_argument("--copy-models", action="store_true",
                    help="also copy each ref_model.py, which is what makes the "
                         "golden_check table reproducible")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for name in args.runs:
        run = Path(name)
        if not (run / "specflow").is_dir():
            continue
        record = distil(run)
        summary.append(record)
        (out / f"{run.name}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        model = run / "specflow" / "ref_model.py"
        if args.copy_models and model.is_file():
            (out / f"{run.name}.ref_model.py").write_text(
                model.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"distilled {len(summary)} run(s) into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
