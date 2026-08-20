"""The harness itself, against known-correct (RTL, model) pairs.

Every other simulator-backed test in this repo drives ONE fixture: a
combinational half-adder. With `LATENCY_CYCLES = 0`, `Env.settle`'s
`max(1, latency + 1)` is 1 and the design has no reset port at all, so the
multi-edge branch of `settle` and the whole of `Env.reset` were never executed by
the test suite. Three alignment bugs lived there undetected, and were found only
by transliterating a golden RTL by hand and noticing that a *faithful* oracle
scored 77 of 168.

These pairs are written to agree by construction. Any failure is a defect in the
harness -- in how it clocks, resets, samples, or bundles inputs -- never in the
fixture. That is what makes this the precondition for the rest of the timing
work: without it, a change to `runtime.py` can only be evaluated against a live
design whose own correctness is unknown.

Deliberately repo assets rather than per-design golden RTL, because production
has no golden to compare against and a conformance suite that only works on a
benchmark is not a conformance suite.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.run import run_suite
from specflow.tb.render import render_suite

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "harness"

needs_verilator = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)

#: What each fixture is here to pin. A name alone does not say why it exists.
CASES = {
    "comb_adder": "the shape already covered -- the control, not the point",
    "reg1": "one registered output; the simplest sequential path",
    "pipe3": "three registers in series; latency_cycles 3, where settle's "
             "multi-edge branch first matters",
    "prescaled_fsm": "a 5-phase FSM advancing one phase per clk_en tick, two of "
                     "whose phases drive identical outputs -- the i2c shape in "
                     "miniature",
    "activelow_io": "an active-low input and an open-drain output, for which 0 "
                    "is not idle",
    "clock_named_clock": "reg1 with the clock port named `clock`; runtime.py "
                         "hardcodes getattr(dut, 'clk') at three sites",
}


def _plan(contract: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """One testpoint, one bin, one check over every declared output.

    Hand-written rather than run through S1-S3: the agent chain is not what is
    under test here, and replaying it would make a harness failure look like a
    generation failure.
    """
    outs = [p["name"] for p in contract["io"] if p.get("dir") == "output"]
    tp = {
        "uid": "TP-0000", "rev": 1, "covers": ["REQ-0000@1"],
        "dimension": "D2_control_flow",
        "stimulus": "exercise every declared input",
        "expected_response": "outputs match the reference model",
        "check_method": "compare against the reference model",
    }
    return (
        [tp],
        [{"uid": "BIN-0000", "rev": 1, "covers": ["TP-0000@1"], "condition": "any"}],
        [{"uid": "CHK-0000", "rev": 1, "covers": ["TP-0000@1"],
          "expr": "outputs match the reference model", "signals": outs}],
    )


def _build(name: str, tmp_path: Path):
    src = FIXTURES / name
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    manifest = render_suite(testplan=testplan, bins=bins, checks=checks,
                            contract=contract, out_dir=suite)
    return src, contract, suite, manifest


@needs_verilator
@pytest.mark.parametrize("name", sorted(CASES))
def test_harness_agrees_with_a_correct_pair(name, tmp_path):
    """A hand-matched RTL and model must agree at every checked point."""
    src, contract, suite, manifest = _build(name, tmp_path)
    outcome = run_suite(
        rtl_path=src / "dut.sv",
        hdl_toplevel=contract["module_name"],
        suite_dir=suite,
        refmodel_path=src / "ref_model.py",
        coverage=False,
        trace=False,
    )
    assert outcome.build_ok, f"{name}: {outcome.build_log}"
    assert len(outcome.results) == len(manifest.testpoints), (
        f"{name}: a testpoint produced no record"
    )
    failing = [
        (u, r.mismatches) for u, r in outcome.results.items() if r.status != "PASS"
    ]
    assert not failing, (
        f"{name} ({CASES[name]}) disagreed. The pair is correct by construction, "
        f"so this is a harness defect: {failing}"
    )


@needs_verilator
@pytest.mark.parametrize("name", sorted(CASES))
def test_every_case_rejects_a_tied_off_dut(name, tmp_path):
    """Agreement is only evidence if disagreement was possible.

    This is the half that matters. `clock_named_clock` passed the test above
    while proving nothing: `runtime.py` looks up the clock as
    `getattr(dut, "clk")`, finds nothing on a port named `clock`, and therefore
    `Env.start` never calls `reset()`. Nothing drives `rst_n`, it reads 0, the
    DUT sits in reset at q=0 -- and `_bundle` reads that same `rst_n=0` off the
    DUT, so the model resets too. Both sides say 0 for the whole run and agree
    for entirely the wrong reason.

    A tied-off DUT catches exactly that: if the harness cannot tell a correct
    design from a constant one, the case is vacuous no matter what it scored.
    """
    src, contract, suite, _ = _build(name, tmp_path)
    outs = [
        (p["name"], int(p.get("width") or 1))
        for p in contract["io"] if p.get("dir") == "output"
    ]
    text = (src / "dut.sv").read_text(encoding="utf-8")
    head = text.split(");", 1)[0].replace("output reg", "output")
    body = "\n".join(f"  assign {n} = {w}'d0;" for n, w in outs)
    broken = tmp_path / "broken.sv"
    broken.write_text(f"{head});\n{body}\nendmodule\n", encoding="utf-8")

    outcome = run_suite(
        rtl_path=broken, hdl_toplevel=contract["module_name"], suite_dir=suite,
        refmodel_path=src / "ref_model.py", coverage=False, trace=False,
    )
    assert outcome.build_ok, f"{name}: {outcome.build_log}"
    assert outcome.failing, (
        f"{name} ({CASES[name]}): a tied-off DUT passed. The harness cannot "
        f"distinguish this design from a constant, so the case above proves "
        f"nothing."
    )
