"""Testpoints where a candidate's RECORDED BEHAVIOUR differs from golden's.

    e6_golden_diff.py <run-dir> <rtl> [<rtl> ...]

An independent yardstick for the RTL editor, and deliberately not the check
set's: it asks whether the design MOVED TOWARD the reference, where the
testbench only asks whether the checks are satisfied. A repair loop can satisfy
more checks while drifting further from correct behaviour, and nothing in the
suite can see that.

**GOLDEN IS RUN AND NEVER READ.** Its path is handed to the simulator; no line
of it is opened here, printed, or shown to any agent. What comes back is a
recording, which is the same thing any other design produces.

**COMPARED ON DECLARED OUTPUTS ONLY.** Golden predates the probe table and
exposes none of it, so comparing on probes would report every testpoint as
differing and say nothing. The honest comparison is the module boundary both
designs actually have.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.rtl_trace import load_traces, rows_from  # noqa: E402
from specflow.run import run_suite  # noqa: E402

GOLDEN = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
              "i2c_master_bit_ctrl.v")
#: Golden `include`s `timescale.v` and `i2c_master_defines.v` from its parent.
#: The candidates are self-contained and need neither; passing the directory
#: for every design keeps the two elaborations otherwise identical.
INCLUDES = (Path("benchmarks/chipverilog/Des/i2c"),)
RUN = Path(sys.argv[1])
CANDIDATES = [Path(p) for p in sys.argv[2:]]
TOP = "i2c_master_bit_ctrl"

contract = json.loads((RUN / "contract.json").read_text())
outputs = sorted(str(p["name"]) for p in (contract.get("io") or [])
                 if p.get("dir") == "output" and p.get("name"))
print(f"comparing on {len(outputs)} declared output(s): {', '.join(outputs)}\n")
results = RUN / "suite" / "results"


def record(rtl: Path) -> dict[str, list[dict]]:
    """Run the suite with `rtl` as the DUT and keep the traces."""
    if results.is_dir():
        for f in results.iterdir():
            if f.is_file():
                f.unlink()
    out = run_suite(rtl_path=rtl, hdl_toplevel=TOP, suite_dir=RUN / "suite",
                    refmodel_path=RUN / "ref_model.py", coverage=False,
                    trace=False, include_dirs=INCLUDES)
    if not getattr(out, "ok", True):
        print(f"  (suite reported not-ok for {rtl.name}; traces still read)")
    return {tp: rows_from(t, side="dut")
            for tp, t in load_traces(results).items()}


def cells(a: list[dict], b: list[dict]) -> tuple[int, int, int]:
    """`(differing cells, compared cells, row-count delta)`.

    **A PER-TESTPOINT FLAG SATURATES AND CANNOT SHOW MOVEMENT.** One differing
    edge anywhere in a several-hundred-edge recording sets it, so two designs
    at wildly different distances from golden both read ~98%. The cell -- one
    (edge, declared output) pair -- is the resolution at which a repair that
    fixed half a testpoint is visible.

    Rows are compared over the common prefix and the length difference is
    reported separately rather than folded in: a recording that ends early is a
    different fact from one that disagrees, and adding them would let a design
    that stops responding score as closer.
    """
    n = min(len(a), len(b))
    bad = 0
    for ra, rb in zip(a[:n], b[:n]):
        oa, ob = ra.get("outputs") or {}, rb.get("outputs") or {}
        bad += sum(1 for p in outputs if oa.get(p) != ob.get(p))
    return bad, n * len(outputs), abs(len(a) - len(b))


def differs(a: list[dict], b: list[dict]) -> bool:
    """Any edge where the two recordings disagree on a declared output."""
    bad, _total, delta = cells(a, b)
    return bool(bad or delta)


print(f"running GOLDEN ({GOLDEN.name}) -- path only, never read", flush=True)
gold = record(GOLDEN)
print(f"  {len(gold)} testpoint(s) recorded\n", flush=True)

for cand in CANDIDATES:
    print(f"running {cand.name}", flush=True)
    got = record(cand)
    shared = sorted(set(gold) & set(got))
    diff = [tp for tp in shared if differs(gold[tp], got[tp])]
    missing = sorted(set(gold) - set(got))
    bad = tot = delta = 0
    for tp in shared:
        b, t, d = cells(gold[tp], got[tp])
        bad += b
        tot += t
        delta += d
    print(f"  {len(diff)} of {len(shared)} shared testpoint(s) DIFFER from "
          f"golden = {100 * len(diff) / max(1, len(shared)):.1f}%")
    print(f"  {bad} of {tot} (edge, output) cell(s) differ = "
          f"{100 * bad / max(1, tot):.2f}%   row-count delta {delta}")
    if missing:
        print(f"  {len(missing)} testpoint(s) golden recorded and this did not")
    print(flush=True)
