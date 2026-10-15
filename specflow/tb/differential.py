"""Differential check: reference model vs a known-good RTL.

This is the strongest validation available for a generated oracle, and it is
available because the benchmark ships golden references. It is spent here, at
M4, before anything depends on the model.

Note carefully what it is *not*: golden RTL is a **validation instrument, used at
test time only**. It never enters the reference model's input bundle -- the model
is already frozen by the time this runs. The same posture is already precedented
in the repo, where `benchmarks/run_verilog_eval_v2.py:416-433` discards
`is_sim_pass` and re-judges against the golden testbench independently.

Configured entirely through the environment because cocotb imports this module
inside the simulator process, where nothing can be passed to it directly.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.triggers import Timer


def _load_model(path: str):
    spec = importlib.util.spec_from_file_location("_specflow_ref_model", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.Model()


def _stimulus(inputs: list[dict], limit: int = 256):
    """Exhaustive when the space is small enough, random otherwise.

    Exhaustive matters here: a differential run over a handful of samples can
    agree by luck on exactly the corner the specification cared about.
    """
    widths = [int(p["width"]) for p in inputs]
    total = 1
    for w in widths:
        total *= 1 << w
        if total > limit:
            break

    if total <= limit:
        for combo in itertools.product(*[range(1 << w) for w in widths]):
            yield dict(zip([p["name"] for p in inputs], combo))
    else:
        rng = random.Random(1337)  # noqa: S311 -- reproducibility over entropy
        for _ in range(limit):
            yield {
                p["name"]: rng.getrandbits(int(p["width"])) for p in inputs
            }


@cocotb.test()
async def differential(dut):
    """Drive DUT and model identically; every disagreement is reported."""
    model = _load_model(os.environ["SPECFLOW_REFMODEL"])
    inputs = json.loads(os.environ["SPECFLOW_INPUTS"])
    outputs = json.loads(os.environ["SPECFLOW_OUTPUTS"])
    report_path = Path(os.environ.get("SPECFLOW_DIFF_REPORT", "differential.json"))

    disagreements: list[dict] = []
    samples = 0

    for stim in _stimulus(inputs):
        for name, value in stim.items():
            getattr(dut, name).value = int(value)
        await Timer(1, unit="ns")

        expected = model.evaluate(dict(stim))
        samples += 1

        for out in outputs:
            got = int(getattr(dut, out).value)
            want = expected.get(out)
            if got != want:
                # Accumulate rather than assert: one disagreement usually means
                # a whole region disagrees, and the shape of that region is what
                # identifies which requirement is wrong.
                disagreements.append(
                    {"stimulus": stim, "signal": out, "dut": got, "model": want}
                )

    report_path.write_text(
        json.dumps(
            {"samples": samples, "disagreements": disagreements}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    assert not disagreements, (
        f"{len(disagreements)} of {samples} samples disagree; "
        f"first: {disagreements[0]}"
    )
