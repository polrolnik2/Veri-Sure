"""Run the pipeline unattended, and PACK THE RESULT BEFORE ANYTHING CAN EAT IT.

    e6_autorun.py <run-dir> --spec <spec.txt> --contract <contract.json>
                  [--control <ref_model.py>] [--reuse] [--resume]
                  [--population N] [--no-preflight] [--admit-pool] [--cover]
                  [--transport-retries N]

**FOUR RUNS' ARTIFACTS WENT WITH A CONTAINER RECLAIM ON THIS BRANCH, AND EVERY
NUMBER TAKEN FROM THEM HAD TO BE RECOMPUTED OR WITHDRAWN.** Three more --
`o1`..`o3` -- survived and still cannot be re-scored, because their CONTRACT was
never written down: they declare 17 probes where `full2` declares 24, so
replaying one's population under the other's contract reports every probe
unavailable and blindness reaches 99.7% by construction.

Both failures are the same failure. A run that finishes and is not packed is a
run whose evidence depends on a directory surviving, and directories here do
not. So this packs on completion, unconditionally, before it prints anything --
and it packs on FAILURE too, because a run that died at the oracle stage still
spent whatever it spent and its earlier stages are still worth freezing.

## Preflight, which exists because of how this session went

The gateway returned `429 BUDGET_EXCEEDED` on every probe of a long session.
Discovering that after S1 has run is discovering it having paid for S1. The
preflight spends ONE four-token call and refuses to start if it fails, and it
corrects the two environment mistakes this project keeps making: the base URL
needs its `/v1` suffix and the model name must drop its `openai/` prefix.

Pass `--no-preflight` to skip it -- for a `--reuse` run that will make no calls
at all, where a budget failure is irrelevant.

## Running only from the stage you changed

`--reuse` reads each stage's artifact from the run directory and re-runs only
what is missing or invalidated. `--resume` additionally replays recorded model
responses. **`--resume` COLLAPSED A POPULATION ONCE**: `ResumePort` keys on
`(stage, round_)` and every population member shares `WITNESS_STAGE`, so one
recorded witness was replayed seven times and `full10`'s seven "designs" were
one design with seven names -- cells 0, blindness n/a. The fix is in
`oracles_stage._population`, which now bypasses call-level resume; the warning
stays because the shape of that bug outlived its instance.
"""
import json
import logging
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

HERE = Path(__file__).resolve().parent
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}
POSITIONAL = [a for a in sys.argv[1:] if not a.startswith("--")]


def _opt(name: str, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def preflight() -> str | None:
    """`None` when the gateway answers, else why it did not."""
    base = (os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    if not base:
        return "OPENAI_BASE_URL is unset"
    if not base.endswith("/v1"):
        base += "/v1"
    #: **THE MODEL AND THE EXTRA BODY EXACTLY AS THE PIPELINE SENDS THEM.**
    #: This used to strip an `openai/` prefix, which one gateway needed -- and
    #: which OpenRouter REQUIRES, so the preflight answered 400 for a model the
    #: pipeline would have reached, or 200 for one it would not. A preflight
    #: that tests a different request from the run's tests nothing. The extra
    #: body carries the provider routing (e.g. the flex endpoint), which is the
    #: other half of "does this gateway answer the request we are about to pay
    #: for".
    model = os.environ.get("OPENAI_MODEL") or ""
    try:
        extra = json.loads(os.environ.get("OPENAI_EXTRA_BODY") or "{}")
    except ValueError:
        return "OPENAI_EXTRA_BODY is not valid JSON"
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps({**(extra if isinstance(extra, dict) else {}),
                         "model": model, "max_tokens": 64,
                         "messages": [{"role": "user", "content": "ping"}]}).encode(),
        headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90):
            return None
    except Exception as exc:  # noqa: BLE001
        body = ""
        try:
            body = exc.read().decode()[:160]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        return f"{getattr(exc, 'code', type(exc).__name__)} {' '.join(body.split())}"


def pack(run_dir: Path, tag: str) -> None:
    """Freeze whatever exists. Never raises: packing must not lose a run."""
    src = run_dir / "specflow"
    if not src.is_dir():
        print(f"pack: nothing at {src}", flush=True)
        return
    out = run_dir.parent / "corpora"
    name = f"{run_dir.name}-{tag}"
    try:
        subprocess.run(
            [sys.executable, str(HERE / "e6_pack_corpus.py"), str(src),
             str(out), "--name", name], check=True)
        subprocess.run(
            ["tar", "-C", str(out), "-czf", str(out / f"{name}.tar.gz"), name],
            check=True)
        print(f"pack: {out / f'{name}.tar.gz'}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"pack: FAILED ({exc!r}) -- the run directory is still at "
              f"{run_dir}, freeze it by hand before this container goes",
              flush=True)


def main() -> int:
    if not POSITIONAL:
        print(__doc__.strip().splitlines()[2])
        return 2
    run_dir = Path(POSITIONAL[0]).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    if "--no-preflight" not in FLAGS:
        why = preflight()
        if why:
            print(f"PREFLIGHT FAILED: {why}\n\nNothing has been spent. Fix the "
                  f"gateway, or pass --no-preflight for a --reuse run that "
                  f"makes no calls.")
            return 1
        print("preflight: gateway answers", flush=True)

    logging.basicConfig(level=logging.WARNING, format="%(message)s",
                        stream=sys.stdout)
    for name in ("specflow.oracles_stage", "specflow.scorecard",
                 "specflow.integration", "specflow.probes",
                 "specflow.refmodel.liveness"):
        logging.getLogger(name).setLevel(logging.INFO)

    started = datetime.now(timezone.utc)
    print(f"start {started.isoformat(timespec='seconds')}  run_dir={run_dir}",
          flush=True)
    rc = 0
    try:
        from specflow.integration import build_artifacts
        from specflow.model_io import PortSettings

        spec_path = _opt("--spec", None)
        contract_path = _opt("--contract", None)
        if not spec_path or not contract_path:
            print("need --spec and --contract; see the docstring")
            return 2
        #: **THE CONTROL GOES IN AS `audit_control` AND NOWHERE ELSE.** That
        #: parameter reaches `scorecard.score`, a module with no author, no
        #: prompt and no repair path. `refmodel_control` reaches the oracle
        #: stage, which CAN reject on it. A control may reject an oracle and
        #: may never repair one; passing it here it does not even reject, it
        #: only scores.
        control = _opt("--control", None)
        control_source = (Path(control).read_text(encoding="utf-8")
                          if control and Path(control).is_file() else None)

        import time as _time

        from specflow.integration import _transport_failure

        def _build(reuse: bool, resume: bool):
            return build_artifacts(
            run_dir=run_dir,
            spec=Path(spec_path).read_text(encoding="utf-8"),
            contract_json=Path(contract_path).read_text(encoding="utf-8"),
            model_port="api",
            port_settings=PortSettings(),
            max_repairs=5,
            refmodel_max_repairs=2,
            enable_probes=True,
            stimulus_agent=True,
            demote_faithfulness=True,
            #: **`--admit-pool` SCORES THE POOL AND NOT ONE BODY PER
            #: REQUIREMENT.** Without it the stage freezes one body each and
            #: blindness reads 0.1416; with it, 0.0526 at the same span, because
            #: a cell is separated by a CHECK and a second body is a second
            #: chance to separate it. Off unless asked, because every recorded
            #: figure on this branch was computed the other way and switching it
            #: silently would change what `blindness` NAMES in all of them.
            admit_pool="--admit-pool" in FLAGS,
            #: **`--cover` SHIPS THE COVER OF THE POOL** -- `specflow/cover.py`.
            #: Population-only and model-free, so a finished run gets it by
            #: re-entering with `--reuse --no-preflight`: blindness and span
            #: held exactly, audit free only to fall.
            ship_cover="--cover" in FLAGS,
            population_size=int(_opt("--population", 7)),
            audit_control=control_source,
            reuse=reuse,
            resume_calls=resume,
        )

        #: **A TRANSPORT FAILURE IS RESUMED, NOT REPORTED.** The pipeline now
        #: stops on one rather than degrading the run, and resuming it is the
        #: same run over the same inputs -- exactly what `reuse` + `resume`
        #: exist for -- so an operator re-typing the command adds nothing but
        #: latency. Bounded, and backing off, so a gateway that is down stays a
        #: failure this reports instead of a loop.
        retries = int(_opt("--transport-retries", 6))
        reuse, resume = "--reuse" in FLAGS, "--resume" in FLAGS
        for attempt in range(retries + 1):
            try:
                result = _build(reuse, resume)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == retries or not _transport_failure(exc):
                    raise
                wait = min(600, 60 * 2 ** attempt)
                print(f"\ntransport failure ({exc!r:.200}); resuming in {wait}s "
                      f"(attempt {attempt + 1} of {retries})", flush=True)
                _time.sleep(wait)
                reuse = resume = True
        print(f"\nbuild ok={getattr(result, 'ok', None)} "
              f"stage={getattr(result, 'stage', None)}", flush=True)
        rc = 0 if getattr(result, "ok", False) else 1
    except Exception as exc:  # noqa: BLE001
        print(f"\nBUILD RAISED: {exc!r}", flush=True)
        rc = 1
    finally:
        #: **PACK BEFORE REPORTING, AND PACK ON FAILURE.** A run that died at
        #: the oracle stage still spent what it spent, and its S1, probe, S2
        #: and S3 artifacts are worth freezing -- that is exactly the material
        #: the four lost runs would have left behind.
        pack(run_dir, "ok" if rc == 0 else "failed")
        took = datetime.now(timezone.utc) - started
        print(f"took {took}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
