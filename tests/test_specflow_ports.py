"""The port-classification fix, tested against the design that exposed it.

`i2c_master_bit_ctrl` declares nine inputs including *both* `rst` and `nReset`.
Three modules classified port names independently and all three got it wrong in
a different direction, so each assertion below names the failure it prevents.
"""

from __future__ import annotations

import pytest

from specflow.ports import (
    classify,
    inactive_value,
    input_names,
    is_clock,
    is_reset,
    pinned_inputs,
    reset_is_active_low,
)
from specflow.refmodel.validate import _random_inputs
from specflow.tb.render import default_stimulus, render_testcase

# The real contract shape from benchmarks/chipverilog: nine inputs, two of which
# are resets under different naming conventions, plus `clk_cnt` -- a functional
# input whose name begins with `clk`.
I2C_CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "rst", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "clk_cnt", "dir": "input", "width": 16},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "din", "dir": "input", "width": 1},
        {"name": "scl_i", "dir": "input", "width": 1},
        {"name": "sda_i", "dir": "input", "width": 1},
        {"name": "dout", "dir": "output", "width": 1},
    ]
}


def test_reset_naming_conventions_are_all_recognised():
    for name in ("rst", "reset", "rst_n", "resetn", "nReset", "aresetn", "n_rst"):
        assert is_reset(name), name


def test_clk_cnt_is_functional_not_a_clock():
    """The reason clock matching is exact: `clk_cnt` is a clock-divider count."""
    assert not is_clock("clk_cnt")
    assert is_clock("clk")
    _, _, functional = classify(I2C_CONTRACT)
    assert "clk_cnt" in functional


def test_reset_polarity_follows_the_name():
    assert reset_is_active_low("nReset")
    assert reset_is_active_low("rst_n")
    assert not reset_is_active_low("rst")
    assert not reset_is_active_low("reset")
    # deasserted: 1 for active-low, 0 for active-high
    assert inactive_value("nReset") == 1
    assert inactive_value("rst") == 0


def test_stimulus_excludes_clock_and_both_resets():
    """`nReset` used to be randomised because the exclusion set was {clk,rst,reset}."""
    stim = default_stimulus(I2C_CONTRACT)
    driven = set(stim[0])
    assert driven == {"ena", "clk_cnt", "cmd", "din", "scl_i", "sda_i"}


def test_g4_bundle_is_complete_even_though_stimulus_is_not():
    """The KeyError('rst') regression.

    G4 dropped every runtime-owned port from the bundle, so a model that read
    `rst` -- a port the contract declares -- raised on the first call and the
    node aborted before any real defect could surface.
    """
    import random

    inputs = _random_inputs(I2C_CONTRACT, random.Random(1))
    assert set(inputs) == set(input_names(I2C_CONTRACT))
    # pinned, not randomised: an asserted reset would make determination vacuous
    assert inputs["rst"] == 0
    assert inputs["nReset"] == 1
    assert inputs["clk"] == 0


def test_pinned_inputs_covers_exactly_the_runtime_owned_ports():
    assert pinned_inputs(I2C_CONTRACT) == {"clk": 0, "rst": 0, "nReset": 1}


def test_rendered_testcase_hands_the_runtime_the_full_input_set():
    source = render_testcase(
        tp={"uid": "TP-0001", "dimension": "D1"},
        bins=[{"uid": "BIN-0001"}],
        checks=[{"uid": "CHK-0001", "signals": ["dout"]}],
        stimulus=[{"ena": 1}],
        input_ports=input_names(I2C_CONTRACT),
        pinned=pinned_inputs(I2C_CONTRACT),
    )
    assert "INPUT_PORTS = " in source
    assert "'nReset'" in source and "'rst'" in source
    assert "input_ports=INPUT_PORTS" in source
    compile(source, "<rendered>", "exec")


class _Handle:
    def __init__(self, value):
        self.value = value


class _Dut:
    def __init__(self, **ports):
        for name, value in ports.items():
            setattr(self, name, _Handle(value))


class _ReadsReset:
    """A model written against the contract, which declares `rst`."""

    OUTPUT_PORTS = ["dout"]

    def step(self, inputs):
        return {"dout": 0 if inputs["rst"] else inputs["din"] & inputs["nReset"]}


def test_runtime_completes_the_bundle_from_the_dut():
    from specflow.tb.runtime import Env

    dut = _Dut(clk=0, rst=0, nReset=1, ena=1, clk_cnt=4, cmd=0, din=1, scl_i=1, sda_i=1)
    env = Env(
        dut, "TP-0001", _ReadsReset(), "results",
        input_ports=input_names(I2C_CONTRACT),
        pinned=pinned_inputs(I2C_CONTRACT),
    )
    # The stimulus drives six ports; the model reads a seventh.
    assert env.expect({"ena": 1, "din": 1, "cmd": 0, "clk_cnt": 4, "scl_i": 1, "sda_i": 1}) == {"dout": 1}


def test_runtime_without_input_ports_still_raises_the_old_way():
    """Guard the guard: with no declared inputs there is nothing to complete."""
    from specflow.tb.runtime import Env

    env = Env(_Dut(), "TP-0001", _ReadsReset(), "results")
    with pytest.raises(KeyError):
        env.expect({"din": 1, "nReset": 1})
