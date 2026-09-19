"""Every input has a defined quiescent value, and the harness starts there.

`inactive_value` returned 0 for every non-reset port. That is right for an
ordinary active-high input and wrong for an active-low or open-drain one, and
the consequence was not a rounding error: on `i2c_master_bit_ctrl` it held
`scl_i`/`sda_i` LOW -- a stuck bus -- during reset while the DUT saw X on the
same pins, so the two started from different states.

Worse than merely wrong, it was wrong in the rewarding direction. `dout` alone
was 996 of 2016 diverging edges, and because golden leaves `dout` unreset while
a wrong candidate zeroes it exactly as the model does, the harness scored the
WRONG RTL above golden: 16 vs 4 passing. A harness that pays you for disagreeing
with the reference is worse than no harness. With idle values declared, that
inverts back to golden 58 vs 35 with no output excluded.
"""

from __future__ import annotations

import json

import pytest

from eda_agent.contract_linter import lint_contract_json
from specflow.ports import idle_value, idle_values, pinned_inputs

CONTRACT = {
    "module_name": "M",
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "rst", "dir": "input", "width": 1},
        {"name": "din", "dir": "input", "width": 4},
        {"name": "req_n", "dir": "input", "width": 1},
        {"name": "scl_i", "dir": "input", "width": 1, "idle_value": 1},
        {"name": "q", "dir": "output", "width": 4},
    ],
    "clocking": {"is_sequential": True},
    "timing": {"q": {"latency_cycles": 1}},
}


def test_the_contract_wins_over_every_name_rule():
    """An open-drain bus is not guessable from its name. `scl_i` looks like an
    ordinary input and idles high; only the contract can say so."""
    assert idle_value("scl_i", {"idle_value": 1}) == 1
    assert idle_values(CONTRACT)["scl_i"] == 1


def test_resets_keep_their_polarity():
    assert idle_value("nReset") == 1      # active low: idle is deasserted = 1
    assert idle_value("rst") == 0


@pytest.mark.parametrize("name", ["din", "en", "token", "sda_in", "green"])
def test_a_trailing_n_does_not_make_a_port_active_low(name):
    """The trap that would have made this worse than the bug it replaces.

    `reset_is_active_low` accepts a bare trailing "n", which is correct for
    reset names. Reusing it for functional inputs would idle `din`, `en` and
    `token` at 1 -- silently feeding the model a different stimulus from the
    DUT on ports that are perfectly ordinary.
    """
    assert idle_value(name) == 0, f"{name} must idle at 0"


@pytest.mark.parametrize("name", ["req_n", "cs_n", "oe_b", "wr_ni"])
def test_the_underscore_convention_is_honoured(name):
    assert idle_value(name) == 1


def test_pinned_inputs_is_contract_aware():
    """It used to call `inactive_value(name)`, so a declared reset idle_value
    was ignored in favour of the name rule."""
    weird = {"io": [{"name": "rst", "dir": "input", "width": 1, "idle_value": 1}]}
    assert pinned_inputs(weird)["rst"] == 1


def test_idle_values_covers_every_declared_input():
    got = idle_values(CONTRACT)
    assert set(got) == {"clk", "nReset", "rst", "din", "req_n", "scl_i"}
    assert "q" not in got, "outputs are not driven"


# ------------------------------------------------------------------ linting


def _issues(contract):
    issues, _ = lint_contract_json(json.dumps(contract))
    return {i.path: i for i in issues if "idle_value" in i.path}


def test_a_non_integer_idle_value_is_an_error():
    c = json.loads(json.dumps(CONTRACT))
    c["io"].append({"name": "z", "dir": "input", "width": 1, "idle_value": "x"})
    found = _issues(c)["io.z.idle_value"]
    assert found.severity == "error"


def test_an_undeclared_active_low_input_is_warned_not_blocked():
    """A warning, not an error: the `_n` convention is strong but not universal,
    and a false error would block a contract that is merely unconventional."""
    found = _issues(CONTRACT)
    assert "io.req_n.idle_value" in found
    assert found["io.req_n.idle_value"].severity == "warning"


def test_a_declared_port_is_not_warned_about():
    assert "io.scl_i.idle_value" not in _issues(CONTRACT)


def test_resets_are_not_warned_about():
    """`nReset` is active-low and already handled by the reset rule; warning
    about it would be noise on every sequential contract in the suite."""
    assert not [p for p in _issues(CONTRACT) if "nReset" in p or "rst" in p]
