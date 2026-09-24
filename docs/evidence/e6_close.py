"""ONE COMMAND that closes the goal when the gateway answers. Refuses when it does not.

    e6_close.py <run-dir> --spec <spec.txt> --contract <contract.json>
                --rtl <golden.v> [--control <ref_model.py>] [--editor-trials N]

**THE GOAL IS TWO THINGS AND ONE OF THEM IS BLOCKED.** span > 90% and blindness
< 10% are met and the pipeline produces them -- `build_artifacts(admit_pool=True)`
ships the pool, `scorecard.score` carries a set of bodies, and `COVER.md`'s greedy
cover holds both while taking audit to 1 of 38. `audit = 0` is not met, and the
remaining conviction is REQ-0055, whose accepted body and both corpus alternatives
all convict the known-good design. No grade-blind rule drops it without dropping
~50 equally redundant requirements (measured: span 0.5351).

So closing it needs ONE non-convicting body for REQ-0055, and that needs the stage
that got it wrong to be re-run. `NORMALIZE-COLLAPSE.md` is the evidence that it IS
`normalize`, from inside the stage rather than from what its output convicts:

    REQ-0051   observable ['clk_en']    -- the port the requirement is about
    REQ-0055   observable ['cmd_ack']   -- not a timing counter

on two near-identical sentences about holding the timing counter during a slave
wait. Plus 21 groups of requirements share an exactly identical normalized form,
71 of 152.

## Why this file exists rather than a paragraph of instructions

Every figure this branch published before today was measured against a golden suite
whose stimulus provenance was never checked, and withdrawn. The lesson was not "be
careful"; it was that a pathway nobody can run in one command is a pathway that
gets re-derived differently each time. So the four steps are here, in order, with
the switches that the frontier measured baked in rather than remembered:

    1  PREFLIGHT       one four-token call; refuse if the gateway does not answer,
                       because discovering 429 after S1 is discovering it having
                       paid for S1
    2  RE-RUN          `build_artifacts(admit_pool=True, ...)` from the stage that
                       changed. normalize and the oracle stage re-run, so REQ-0055
                       gets a form and a body authored under today's gates:
                       `well_formed` now refuses an unbounded TO_END invariant AND
                       a property asserted under both temporal readings, which is
                       the shape REQ-0055's accepted body has.
    3  SCORE           replay golden through a suite regenerated from the packed
                       corpus, then the greedy cover. `e6_replay_corpus.py` and
                       `e6_cover.py`, both of which run today with zero model calls
                       and are the only steps here that are already verified.
    4  RTL EDITOR      `edit_drive.py`, the real `_EditSession`. Golden is withheld
                       from the agent: it sees the requirement text, the check's
                       complaint, the boundary trace, the VCD internals and the
                       candidate's source, and never the reference.

**STEP 3 IS VERIFIED AND STEPS 2 AND 4 ARE NOT.** Both are thin wrappers over
functions this branch tests, but neither has been executed end to end here, because
the gateway has answered `429 BUDGET_EXCEEDED` on every probe of this session. That
is stated rather than papered over: this file is a pathway, not a result, and it
prints so at the end.
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def _opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def preflight() -> str | None:
    """`None` when the gateway answers, else why not. See `e6_autorun.py`."""
    base = (os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    if not base:
        return "OPENAI_BASE_URL is unset"
    if not base.endswith("/v1"):
        base += "/v1"
    model = (os.environ.get("OPENAI_MODEL") or "").split("/", 1)[-1]
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({"model": model, "max_tokens": 4,
                         "messages": [{"role": "user", "content": "ping"}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90):
            return None
    except Exception as exc:  # noqa: BLE001
        body = ""
        try:
            body = exc.read().decode()[:200]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        return f"{getattr(exc, 'code', type(exc).__name__)} {' '.join(body.split())}"


def step(n, what, argv, *, cwd=ROOT) -> bool:
    print(f"\n=== {n}  {what} ===\n  $ {' '.join(argv[:6])}"
          f"{' ...' if len(argv) > 6 else ''}", flush=True)
    rc = subprocess.run(argv, cwd=str(cwd)).returncode
    print(f"  -> exit {rc}", flush=True)
    return rc == 0


def main() -> int:
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not pos:
        print(__doc__.strip().splitlines()[2])
        return 2
    run_dir = Path(pos[0]).resolve()
    spec, contract = _opt("--spec"), _opt("--contract")
    rtl, control = _opt("--rtl"), _opt("--control")
    if not (spec and contract and rtl):
        print("need --spec, --contract and --rtl; see the docstring")
        return 2

    started = datetime.now(timezone.utc)
    why = preflight()
    if why:
        print(f"PREFLIGHT FAILED: {why}\n")
        print("Nothing has been spent. Steps 2 and 4 need model access and cannot")
        print("run; step 3 can, on a frozen corpus:\n")
        print(f"  python3 {HERE}/e6_replay_corpus.py <corpus> {rtl} <out>")
        print(f"  python3 {HERE}/e6_cover.py <corpus> <out> --limit 2\n")
        print("That reproduces span 0.9737 / blindness 0.0595 / audit 1 of 38 --")
        print("two of the three targets, and the audit column that REQ-0055 holds")
        print("open. See COVER.md and DEPTH-RESIDUE.md.")
        return 1
    print("preflight: gateway answers", flush=True)

    ok = True
    #: **STEP 2. `admit_pool=True` IS THE WHOLE POINT OF RE-RUNNING.** Without it
    #: the stage freezes one body per requirement and blindness returns to 0.1416.
    #: The control goes in as `audit_control` and nowhere else -- it reaches
    #: `scorecard.score`, which has no author and no repair path. A control may
    #: REJECT an oracle and may never REPAIR one.
    argv = [sys.executable, str(HERE / "e6_autorun.py"), str(run_dir),
            "--spec", spec, "--contract", contract, "--admit-pool"]
    if control:
        argv += ["--control", control]
    ok = step(2, "re-run normalize + the oracle stage, scoring the POOL",
              argv) and ok

    corpus = run_dir.parent / "corpora" / f"{run_dir.name}-ok"
    gold = run_dir.parent / f"{run_dir.name}-gold"
    ok = step(3, "replay golden through a regenerated suite",
              [sys.executable, str(HERE / "e6_replay_corpus.py"), str(corpus),
               rtl, str(gold)]) and ok
    ok = step(3, "the greedy cover, and the triple",
              [sys.executable, str(HERE / "e6_cover.py"), str(corpus),
               str(gold), "--limit", "2"]) and ok

    trials = _opt("--editor-trials", "6")
    ok = step(4, "the RTL Editor testbench -- golden is WITHHELD from the agent",
              [sys.executable, str(HERE / "edit_drive.py"), "--run",
               str(run_dir), "--name", "close", "--trials", str(trials)]) and ok

    print(f"\ntook {datetime.now(timezone.utc) - started}")
    print("\n**WHAT TO CHECK, AND WHAT WOULD MAKE THIS A RESULT RATHER THAN A RUN**")
    print("  1. does REQ-0055's new normalized form observe a TIMING COUNTER")
    print("     (`clk_en`, `cnt_zero`, `filter_cnt`) rather than `cmd_ack`?")
    print("     NORMALIZE-COLLAPSE.md is the evidence that the old one was wrong.")
    print("  2. does its authored body SPARE golden? If not, the residue has a")
    print("     cause this branch has not found, and saying so is the result.")
    print("  3. is span still > 0.90 and blindness still < 0.10 on the cover?")
    print("     Both were met before this ran; a normalize change can move them.")
    print("  4. the editor's pass count against the frozen set, beside the 95 / 91")
    print("     / 86 on record -- which were measured against the SUPERSEDED set")
    print("     and are not comparable until this step re-runs.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
