"""Audit with the contract's probes BOUND to the known-good design by hand.

    e7_bind_golden.py <corpus-dir> <golden.v> <binding.py> <out-dir> [--extra CHILD.v]

**THIS READS GOLDEN, AND IT IS THE ONLY THING HERE THAT DOES.** Every other
driver only runs the known-good design. A probe is a name and a width in the
contract; a design built without that contract -- golden -- implements the same
quantity under its own name, registered or not, and binding by name leaves most
checks reading a probe unjudgeable on it (`idle` is a state constant there,
`cSCL` two bits, `in_start_sequence` exists nowhere). So a human writes, per
module, which of golden's internals each probe IS:

    docs/evidence/e7/golden_bind/<module>.py
        INTERNALS  golden signals to record per edge (dotted for a child)
        PROBES     probe -> function(recorded internals) -> value
        UNBOUND    probe -> why it has no counterpart in golden

The binding is AUDIT-ONLY. It is read here and nowhere else: no pipeline stage,
prompt, model or selection rule sees it, and golden's RTL is not modified --
its internals are recorded by the testbench (`trace_internals`) and the probe
columns of its traces are rewritten from them after simulation. A probe with no
binding reads `None`, so a check reading it abstains rather than pass or fail.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def _load_binding(path: Path):
    spec = importlib.util.spec_from_file_location("golden_binding", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return (list(getattr(mod, "INTERNALS", [])), dict(getattr(mod, "PROBES", {})),
            dict(getattr(mod, "UNBOUND", {})))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")
            and sys.argv[sys.argv.index(a) - 1] != "--extra"]
    if len(args) < 4:
        print(__doc__.strip().splitlines()[2])
        return 2
    corpus, golden, binding, out = (Path(a).resolve() for a in args[:4])
    extras = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--extra"]
    internals, probes, unbound = _load_binding(binding)
    contract = json.loads((corpus / "contract.json").read_text())
    declared = {p["name"]: int(p.get("width") or 1) for p in contract.get("io") or []
                if p.get("dir") == "probe"}
    missing = sorted(set(declared) - set(probes) - set(unbound))
    if missing:
        print(f"binding does not account for probe(s): {missing}")
        return 2

    raw = out / "raw"
    rc = subprocess.run(
        [sys.executable, str(HERE / "e6_replay_corpus.py"), str(corpus), str(golden),
         str(raw), "--internals", ",".join(internals)]
        + [a for e in extras for a in ("--extra", e)],
        cwd=str(ROOT), stdout=open(out.parent / f"{out.name}.replay.log", "w")
        if out.parent.is_dir() else None, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        print("golden replay failed")
        return 1

    bound = out / "bound"
    if bound.exists():
        shutil.rmtree(bound)
    shutil.copytree(raw, bound)
    seen: dict[str, set] = {p: set() for p in probes}
    errors: dict[str, int] = {}
    for f in sorted((bound / "suite" / "results").glob("*.trace.json")):
        t = json.loads(f.read_text())
        for e in t.get("edges") or []:
            s = e.get("dut_internal") or {}
            dut = dict(e.get("dut") or {})
            for name, fn in probes.items():
                try:
                    v = fn(s)
                except Exception:  # noqa: BLE001 -- an internal read None
                    v = None
                    errors[name] = errors.get(name, 0) + 1
                dut[name] = None if v is None else int(v)
                if v is not None and len(seen[name]) < 9:
                    seen[name].add(int(v))
            for name in unbound:
                dut[name] = None
            e["dut"] = dut
        widths = dict(t.get("widths") or {})
        for name in probes:
            widths[name] = declared[name]
        t["widths"] = widths
        if isinstance(t.get("width_refused"), dict):
            for name in probes:
                t["width_refused"].pop(name, None)
        f.write_text(json.dumps(t))

    print(f"bound {len(probes)} probe(s), {len(unbound)} left unbound:")
    for name in sorted(probes):
        vals = sorted(seen[name])
        flag = "" if vals else "   <-- NEVER READ A VALUE"
        flag += f"   ({errors[name]} edge(s) could not be computed)" if name in errors else ""
        print(f"   {name:28} w={declared[name]}  values seen {vals}{flag}")
    for name, why in sorted(unbound.items()):
        print(f"   {name:28} UNBOUND: {why}")
    print(flush=True)
    return subprocess.run(
        [sys.executable, str(HERE / "e7_score_run.py"), str(corpus), str(bound),
         "--json", str(out / "score_bound.json")], cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
