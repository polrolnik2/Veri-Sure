"""Testpoints where a candidate's RECORDED BEHAVIOUR differs from golden's.

    e6_golden_diff.py <run-dir> <rtl> [<rtl> ...] [--population <dir>]

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

**AND A RAW COUNT OF DIFFERENCES IS THE WRONG NUMBER, WHICH IS WHY
`--population` EXISTS.** A spec-admissible design SHOULD differ from golden
wherever the specification leaves the behaviour open; counting those measures
conformance to golden's arbitrary choices, not correctness. Earlier work here
quoted the raw form -- "261 of 348 testpoints differing" -- and this module
already records why that is weak: "on a 32-bit port two spec-derived designs
differ almost everywhere ... stratify set blindness by port width, or do not
quote it".

The seven independently written spec-derived designs are the instrument for
it. Where they ALL agree on a `(testpoint, port)`, seven readings of the spec
pin that behaviour and a candidate differing from golden there is a defect.
Where they disagree, `variety.cells` already calls that a cell -- the spec is
under-determined and differing is not evidence of anything.

One caveat, stated rather than hidden: the mask comes from Python replays of
the population and the difference from RTL-to-RTL recordings. The mask answers
"do independent readings of the spec agree here", which does not depend on the
substrate; the measurement is like-for-like.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.rtl_trace import (load_traces,  # noqa: E402
                                        rows_from, unknown_ports)
from specflow.run import run_suite  # noqa: E402

GOLDEN = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
              "i2c_master_bit_ctrl.v")
#: Golden `include`s `timescale.v` and `i2c_master_defines.v` from its parent.
#: The candidates are self-contained and need neither; passing the directory
#: for every design keeps the two elaborations otherwise identical.
INCLUDES = (Path("benchmarks/chipverilog/Des/i2c"),)
#: **FLAGS AND THEIR VALUES ARE NOT CANDIDATES.** Taking every remaining
#: argument as an RTL path put `--population` and its directory into the
#: candidate list, and each was dutifully "run" -- producing a row of zeroes
#: and "422 testpoint(s) golden recorded and this did not", which reads as a
#: design that recorded nothing rather than as an argument that is not a design.
_FLAGS_WITH_VALUES = ("--population",)
_argv, _skip = [], False
for _i, _a in enumerate(sys.argv[1:]):
    if _skip:
        _skip = False
        continue
    if _a in _FLAGS_WITH_VALUES:
        _skip = True
        continue
    if _a.startswith("--"):
        continue
    _argv.append(_a)
RUN = Path(_argv[0])
CANDIDATES = [Path(q) for q in _argv[1:]]
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
    rows = {tp: rows_from(t, side="dut")
            for tp, t in load_traces(results).items()}
    #: **AN UNRESOLVED PORT READS AS 100% DIFFERING AND IS NOT A DIFFERENCE.**
    #: `Env.sample` returns None for a port the design does not expose, so a
    #: naming mismatch between golden and the rendered suite would silently
    #: inflate every count here -- the whole measurement, reported as a
    #: behavioural gap. Named per design, not summed away.
    bad: dict[str, int] = {}
    for tp_rows in rows.values():
        for port, n in unknown_ports(tp_rows).items():
            if port in outputs:
                bad[port] = bad.get(port, 0) + n
    if bad:
        named = ", ".join(f"{k} on {v} row(s)" for k, v in sorted(bad.items()))
        print(f"  UNRESOLVED on this design: {named} -- every cell on those "
              f"ports counts as differing and is NOT evidence", flush=True)
    else:
        print(f"  all {len(outputs)} declared output(s) resolved", flush=True)
    return rows


def step(rows: list[dict], port: str) -> list[tuple[int, object]]:
    """`(edge, value)` for `port`, as a step function over the recording.

    ROWS ARE NOT COMPARABLE BY INDEX. `transactional_view` collapses runs of
    identical samples, so two designs that behave identically can still have
    different row counts and row 7 is not the same instant in both. The `edge`
    number is the instant; this indexes by it and the reader holds the last
    value at or before the edge it asks about.
    """
    return [(int(r.get("edge", 0)), (r.get("outputs") or {}).get(port))
            for r in rows]


def at(steps: list[tuple[int, object]], edge: int) -> object:
    """The value in force at `edge`; None before the recording starts."""
    lo, hi, out = 0, len(steps) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if steps[mid][0] <= edge:
            out = steps[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return out


def cells(a: list[dict], b: list[dict]) -> tuple[int, int, int]:
    """`(differing cells, compared cells, row-count delta)`, EDGE-ALIGNED.

    **A PER-TESTPOINT FLAG SATURATES AND CANNOT SHOW MOVEMENT.** One differing
    edge anywhere in a several-hundred-edge recording sets it, so two designs
    at wildly different distances from golden both read ~98%. The cell -- one
    (edge, declared output) pair -- is the resolution at which a repair that
    fixed half a testpoint is visible.

    **AND IT IS ALIGNED BY `edge`, NOT BY ROW INDEX, WHICH THIS GOT WRONG.**
    `transactional_view` collapses runs of identical samples, so two designs
    that behave identically can still have different row counts and row 7 is
    not the same instant in both. Zipping them compared unrelated instants and
    disagreed with the constrained/under-determined split computed beside it --
    17969 against 19034 on the same pair, which is how the defect was found.

    The length difference is reported separately rather than folded in: a
    recording that ends early is a different fact from one that disagrees, and
    adding them would let a design that stops responding score as closer.
    """
    asteps = {p: step(a, p) for p in outputs}
    bsteps = {p: step(b, p) for p in outputs}
    bad = 0
    for r in a:
        e = int(r.get("edge", 0))
        bad += sum(1 for p in outputs
                   if at(asteps[p], e) != at(bsteps[p], e))
    return bad, len(a) * len(outputs), abs(len(a) - len(b))


def differs(a: list[dict], b: list[dict]) -> bool:
    """Any edge where the two recordings disagree on a declared output."""
    bad, _total, delta = cells(a, b)
    return bool(bad or delta)


POP_DIR = None
if "--population" in sys.argv:
    POP_DIR = Path(sys.argv[sys.argv.index("--population") + 1])
pop_rows: dict[str, dict[str, list[dict]]] = {}
if POP_DIR is not None:
    from specflow import oracles_stage as _OS
    from specflow.refmodel.compose import choose_base as _base
    sources = [q.read_text() for q in sorted(POP_DIR.glob("*.py"))]
    stim = json.loads((RUN / "stimulus.json").read_text())
    sbt = {t["tp_uid"]: t["stimulus_steps"] for t in stim["testpoints"]}
    print(f"replaying {len(sources)} spec-derived design(s) for the "
          f"constrained/under-determined mask", flush=True)
    pop_rows = _OS._population_rows(sources, contract, sbt,
                                    base=_base(contract), transactional=True)
    print(f"  {len(pop_rows)} design(s) replayed\n", flush=True)


def per_port_and_onset(g: list[dict], c: list[dict], tp: str
                       ) -> tuple[dict[str, int], int | None, int | None]:
    """`(defect cells per port, first constrained-differing edge, last edge)`.

    **A CELL COUNT CANNOT TELL ONE STRUCTURAL CHANGE FROM THOUSANDS OF
    INDEPENDENT ERRORS, AND THEY MEAN OPPOSITE THINGS.** A state machine that
    shifts by a cycle mismatches every sample after the shift, so one defect
    bills as thousands of cells; a genuinely scattered regression bills the
    same total across many ports and many onsets. The onset edge separates
    them: if the repaired design diverges EARLIER in a testpoint than the one
    it replaced, it changed when the machine does something, not what it does
    at one instant.
    """
    gsteps = {q: step(g, q) for q in outputs}
    csteps = {q: step(c, q) for q in outputs}
    psteps = {d: {q: step(rows.get(tp) or [], q) for q in outputs}
              for d, rows in pop_rows.items()}
    by_port: dict[str, int] = {}
    onset = last = None
    for r in g:
        e = int(r.get("edge", 0))
        for q in outputs:
            if at(gsteps[q], e) == at(csteps[q], e):
                continue
            vals = {at(psteps[d][q], e) for d in psteps if psteps[d][q]}
            if len(vals) != 1:
                continue            # under-determined: not a defect
            by_port[q] = by_port.get(q, 0) + 1
            onset = e if onset is None else min(onset, e)
            last = e if last is None else max(last, e)
    return by_port, onset, last


def split_by_constraint(g: list[dict], c: list[dict], tp: str) -> tuple[int, int]:
    """`(defect cells, slack cells)` over the edges golden recorded.

    CONSTRAINED means every spec-derived design agrees on that port at that
    edge -- seven independent readings of the specification pin the value, so a
    candidate differing from golden there is a defect. Where they disagree the
    specification is under-determined and differing is not evidence of
    anything, which is the whole reason a raw difference count is the wrong
    number.
    """
    defect = slack = 0
    gsteps = {p: step(g, p) for p in outputs}
    csteps = {p: step(c, p) for p in outputs}
    psteps = {d: {p: step(rows.get(tp) or [], p) for p in outputs}
              for d, rows in pop_rows.items()}
    for r in g:
        e = int(r.get("edge", 0))
        for p in outputs:
            gv, cv = at(gsteps[p], e), at(csteps[p], e)
            if gv == cv:
                continue
            vals = {at(psteps[d][p], e) for d in psteps if psteps[d][p]}
            if len(vals) == 1:
                defect += 1
            else:
                slack += 1
    return defect, slack


#: `candidate -> {testpoint: first constrained-differing edge}`, so the two
#: candidates can be compared on WHEN they leave golden rather than only on
#: how much.
ONSETS: dict[str, dict[str, int]] = {}

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
    if pop_rows:
        d_sum = s_sum = 0
        for tp in shared:
            d, sl = split_by_constraint(gold[tp], got[tp], tp)
            d_sum += d
            s_sum += sl
        tot2 = d_sum + s_sum
        print(f"  of the differences, {d_sum} sit where ALL spec-derived "
              f"designs agree (DEFECT) and {s_sum} where they do not "
              f"(under-determined) = {100 * d_sum / max(1, tot2):.1f}% defect")
        ports: dict[str, int] = {}
        onsets: dict[str, int] = {}
        touched = 0
        for tp in shared:
            bp, on, _last = per_port_and_onset(gold[tp], got[tp], tp)
            for q, n in bp.items():
                ports[q] = ports.get(q, 0) + n
            if on is not None:
                onsets[tp] = on
                touched += 1
        print("  defect cells by port: " + ", ".join(
            f"{q}={ports.get(q, 0)}" for q in outputs))
        med = (sorted(onsets.values())[len(onsets) // 2] if onsets else "-")
        print(f"  {touched} testpoint(s) carry a defect; median onset edge {med}")
        ONSETS[cand.name] = onsets
    if missing:
        print(f"  {len(missing)} testpoint(s) golden recorded and this did not")
    print(flush=True)


#: **EARLIER ONSET IS A TIMING CHANGE; SAME ONSET WITH MORE CELLS IS NOT.**
if len(ONSETS) == 2:
    (n1, a), (n2, b) = ONSETS.items()
    both = sorted(set(a) & set(b))
    earlier = sum(1 for tp in both if b[tp] < a[tp])
    later = sum(1 for tp in both if b[tp] > a[tp])
    same = len(both) - earlier - later
    print(f"\nONSET, {n2} against {n1}, over {len(both)} testpoint(s) both "
          f"fail:\n  diverges EARLIER {earlier}   later {later}   same {same}")
    only2 = sorted(set(b) - set(a))
    only1 = sorted(set(a) - set(b))
    print(f"  testpoints newly carrying a defect: {len(only2)}   "
          f"no longer carrying one: {len(only1)}")
