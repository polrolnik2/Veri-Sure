"""Everything after a run is packed, for one module, in one command.

    e7_module.py <runs-root> <module> [--trials N] [--rounds R] [--skip-editor]

Reads `<runs-root>/<module>` (the run) and `<runs-root>/corpora/<module>-ok`
(the corpus `e6_autorun.py` packed), writes `<runs-root>/results/<module>/`:

    1  GOLDEN REPLAY   `e6_replay_corpus.py` -- the known-good design simulated
                       through a suite regenerated from this corpus's own
                       stimulus. Children (`i2c_master_byte_ctrl` instantiates
                       `i2c_master_bit_ctrl`) and headers are supplied to the
                       simulator only. Golden is RUN, never read.
    2  THE TRIPLE      `e7_score_run.py` -- span, blindness and audit of the set
                       the run SHIPPED, with the pipeline's own rules and no
                       others. -> score.json
    3  RTL EDITOR      `e7_rtl_editor.py` -- RTLGenerator writes rtl.sv from the
                       specification and contract, then RTLEditor repairs it
                       against the shipped set, iterating on the testbench's
                       failures. Golden is not in this path. -> editor_summary.json
    4  VERDICT         `benchmarks/score_chipverilog.py` -- ChipVerilog's own
                       compile gate + equivalence/simulation flow on the final
                       rtl.sv. -> chipverilog.json

Each step logs to its own file beside the JSON; a failed step is reported and
the later steps that do not depend on it still run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DES = ROOT / "benchmarks" / "chipverilog" / "Des"


def _opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def _task(module: str) -> Path:
    hits = [p.parent for p in DES.rglob("description.txt") if p.parent.name == module]
    if not hits:
        raise SystemExit(f"no ChipVerilog task named {module!r}")
    return hits[0]


def _step(name: str, argv: list[str], log: Path) -> bool:
    print(f"== {name}", flush=True)
    with log.open("w") as fh:
        rc = subprocess.run(argv, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT).returncode
    tail = log.read_text(errors="replace").strip().splitlines()[-6:]
    for line in tail:
        print(f"   {line[:200]}", flush=True)
    print(f"   -> exit {rc} (log {log})", flush=True)
    return rc == 0


def main() -> int:
    pos = [a for a in sys.argv[1:] if not a.startswith("--")
           and sys.argv[sys.argv.index(a) - 1] not in ("--trials", "--rounds")]
    if len(pos) < 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    runs, module = Path(pos[0]).resolve(), pos[1]
    run, corpus = runs / module, runs / "corpora" / f"{module}-ok"
    gold, res = runs / "gold" / module, runs / "results" / module
    editor = runs / "editor" / module
    res.mkdir(parents=True, exist_ok=True)
    task = _task(module)
    golden = task / f"{module}.v"
    sys.path.insert(0, str(ROOT / "benchmarks"))
    from run_chipverilog import child_sources, submodules  # noqa: E402
    extras = [str(p) for p in child_sources(submodules(task, module))]

    py = sys.executable
    ok_gold = _step("golden replay", [py, str(HERE / "e6_replay_corpus.py"), str(corpus),
                                      str(golden), str(gold)]
                    + [a for e in extras for a in ("--extra", e)],
                    res / "replay.log")
    if ok_gold:
        _step("the triple of the shipped set", [py, str(HERE / "e7_score_run.py"),
                                                str(corpus), str(gold), "--json",
                                                str(res / "score.json")],
              res / "score.log")
    if "--skip-editor" in sys.argv:
        return 0
    ok_ed = _step("RTL editor", [py, str(HERE / "e7_rtl_editor.py"), str(run), str(editor),
                                 "--spec", str(task / "description.txt"),
                                 "--trials", _opt("--trials", "20"),
                                 "--rounds", _opt("--rounds", "3"),
                                 "--summary", str(res / "editor_summary.json")],
                  res / "editor.log")
    if ok_ed or (editor / "rtl.sv").is_file():
        import shutil

        from score_chipverilog import score  # noqa: E402 -- benchmarks/ is on the path
        #: Graded on the DELIVERABLE -- the reference interface, probes
        #: unconnected -- which the scorer expects to find as `rtl.sv`.
        ship = runs / "deliverable" / module
        ship.mkdir(parents=True, exist_ok=True)
        src = editor / "rtl_deliverable.sv"
        shutil.copy(src if src.is_file() else editor / "rtl.sv", ship / "rtl.sv")
        verdict = score(ship, module)
        (res / "chipverilog.json").write_text(json.dumps(verdict, indent=2) + "\n")
        print(f"== ChipVerilog verdict: {verdict.get('status')} "
              f"({verdict.get('flow')}, {verdict.get('proof_type')})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
