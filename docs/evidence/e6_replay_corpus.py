"""Regenerate a suite from a packed corpus and RUN AN RTL THROUGH IT.

    e6_replay_corpus.py <corpus-dir> <rtl.v> <out-dir> [--toplevel NAME]

`e6_verify_corpus.py` re-scores span and blindness from a corpus alone, because
both are Python replays of the stored population. **THE AUDIT COLUMN IS NOT**:
it needs traces, and traces need a simulator, a design and a rendered suite.
`CORPORA.md` claims `suite/` regenerates from the testplan, the stimulus and
the contract, and that claim is why `suite/` is left out of a corpus at all.
This is the driver that tests it.

## The switch a corpus did not record

`render_suite` takes `trace_internals` and `bus_lines`, and `integration.py`'s
call site passes NEITHER. Only one of them turns out to matter, and MEASURING
that is what settled it -- the first draft of this file asserted both did.

  * **`trace_internals` does not gate the probes.** It adds the
    `dut_internal` / `model_internal` debug columns. The probe values
    `decide_rtl` reads live in `"dut"`, which `Env.finish` writes
    unconditionally and says so: "it used to be written only when
    `SPECFLOW_TRACE_INTERNALS` named something, which made the recording that
    DECIDES the design a side effect of asking for debug signals." Rendering
    this suite with `trace_internals=[]` (`--no-probes`) leaves the same 24
    probe keys in `"dut"` with the same 16 bound, and re-scores to the same
    0.3556 over 45. That switch is not a corpus problem.

  * **`bus_lines` does.** Unset, the stimulus drives `scl_i`, the DUT drives
    `scl_oen` and nothing connects them. `--unwired` against the same corpus
    and the same golden gives audit 14/45 = 0.3111 where the wired testbench
    gives 16/45 = 0.3556. Two convictions, and the denominator does not move.
    Derived here from the contract by `bus_lines_from`, which is what it should
    have been.

## And the stimulus the control was run under is part of the measurement

`stimulus_digest` exists because "every run of the pipeline mints the SAME uids
-- TP-0069 exists in every i2c run there has ever been -- while regenerating
the stimulus behind them." A digest computed over this corpus's own
`stimulus_steps` reproduces the digest its traces carry, 482 of 482, so a
verifier can tell offline whether a golden suite belongs to a corpus. It now
does; see `e6_verify_corpus.py`.

Golden is RUN and never read.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.run import run_suite  # noqa: E402
from specflow.tb.render import render_suite  # noqa: E402
from specflow.tb.runtime import bus_lines_from  # noqa: E402


def _opt(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    corpus, rtl, out = Path(args[0]), Path(args[1]), Path(args[2])
    out.mkdir(parents=True, exist_ok=True)

    contract = json.loads((corpus / "contract.json").read_text(encoding="utf-8"))
    _t = json.loads((corpus / "testplan.json").read_text())
    #: S2 writes `{"elements": [...]}`; older drivers wrote a bare list and
    #: one wrote `{"testpoints": [...]}`. Accepting all three here rather
    #: than in the packer, because the packer copies bytes and a corpus must
    #: stay byte-identical to the run that made it.
    testplan = (_t if isinstance(_t, list) else
                _t.get("elements") or _t.get("testpoints") or [])
    cov = json.loads((corpus / "coverage_model.json").read_text())
    bins = cov.get("bins") or []
    checks = cov.get("checks") or []
    _s = json.loads((corpus / "stimulus.json").read_text())
    stim = _s["testpoints"] if isinstance(_s, dict) else _s
    by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}

    #: **DERIVED FROM THE CONTRACT, BECAUSE THE CORPUS COULD NOT RECORD THEM.**
    #: Both are functions of the contract and nothing else, which is what makes
    #: deriving them legitimate rather than a guess. `bus_lines` is the one that
    #: moves the answer -- two convictions, measured with `--unwired`.
    #: `--no-probes` renders the suite recording no internal DEBUG columns,
    #: which is what an unset `SPECFLOW_TRACE_INTERNALS` gives. Kept because
    #: the measurement it settles is worth being able to repeat: it changes
    #: NOTHING -- same 24 probe keys in `"dut"`, same 16 bound, same audit.
    probes = [] if "--no-probes" in sys.argv else list(declared_probes(contract))
    #: `--unwired` renders the testbench the way `integration.py`'s own call
    #: site does -- passing no `bus_lines` at all -- so the two configurations
    #: can be MEASURED against each other instead of argued about. It is not a
    #: setting to ship: an unwired testbench is one where the DUT cannot
    #: observe the bus it drives.
    lines = [] if "--unwired" in sys.argv else bus_lines_from(contract)
    print(f"contract    {contract.get('module_name')} | {len(probes)} probes")
    print(f"testplan    {len(testplan)} testpoint(s), "
          f"{sum(1 for t in testplan if by_tp.get(t.get('uid')))} with stimulus")
    print(f"switches    trace_internals={len(probes)} derived from the contract; "
          f"bus_lines={[b.get('input') for b in lines]}")

    suite = out / "suite"
    manifest = render_suite(
        testplan=testplan, bins=bins, checks=checks, contract=contract,
        out_dir=suite, stimulus_by_tp=by_tp or None,
        trace_internals=probes, bus_lines=lines)
    n_cases = len(getattr(manifest, "testcases", None) or
                  getattr(manifest, "cases", None) or [])
    print(f"rendered    {n_cases or '?'} testcase(s) -> {suite}")

    refmodel = out / "ref_model.py"
    shutil.copy2(corpus / "ref_model.py", refmodel)
    shutil.copy2(corpus / "contract.json", out / "contract.json")

    toplevel = _opt("--toplevel") or str(contract.get("module_name"))
    #: **A HEADER IS NOT AN ORACLE.** The OpenCores i2c design ``\`include``s
    #: `i2c_master_defines.v` and will not elaborate without it, and a build
    #: error reads exactly like a defect in the design. Supplying the include
    #: path makes it simulable; it says nothing about what the design should
    #: do. Defaults to the RTL's own directory and its parent, which is where
    #: the header sits for this benchmark; `--include` adds more.
    includes = [rtl.parent, rtl.parent.parent, *(
        Path(a) for a in sys.argv[1:] if a.startswith("+incdir+"))]
    for i, a in enumerate(sys.argv):
        if a == "--include" and i + 1 < len(sys.argv):
            includes.append(Path(sys.argv[i + 1]))
    print(f"running     {rtl.name} as {toplevel} ... (this takes a while)",
          flush=True)
    outcome = run_suite(rtl_path=rtl, hdl_toplevel=toplevel, suite_dir=suite,
                        refmodel_path=refmodel, trace=False,
                        include_dirs=[str(d) for d in includes])
    #: `results/` holds TWO files per testpoint -- `{tp}.json`, the verdict
    #: record, and `{tp}.trace.json`, the recording. Globbing `*.json` counts
    #: both, and an earlier version of this line reported 964 "trace files" for
    #: 482 traces.
    results = sorted((suite / "results").glob("*.trace.json"))
    records = sorted(f for f in (suite / "results").glob("*.json")
                     if not f.name.endswith(".trace.json"))
    print(f"\nbuild_ok    {outcome.build_ok}")
    print(f"results     {len(results)} trace(s), {len(records)} record(s)")
    if not outcome.build_ok:
        print((outcome.build_log or "")[-1500:])
        return 1

    #: **THE ONE QUESTION THAT DECIDES WHETHER THIS WORKED.** A suite that runs
    #: and records no probe values is a suite whose audit column is a rate over
    #: the checks that need no probe -- which is the 14-of-111 denominator this
    #: branch spent a session correcting.
    seen: set = set()
    for f in results:
        t = json.loads(f.read_text())
        for e in (t.get("edges") or []):
            for n, v in (e.get("dut") or {}).items():
                if v is not None:
                    seen.add(n)
    bound = [p for p in probes if p in seen]
    print(f"probes      {len(bound)} of {len(probes)} bound in the traces")
    if len(bound) < len(probes):
        print(f"  unbound   {sorted(set(probes) - seen)}")
    print(f"\nnow: e6_verify_corpus.py {corpus} {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
