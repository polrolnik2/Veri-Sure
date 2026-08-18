"""One place that decides what a port name means.

Three modules used to answer "is this the clock?" and "is this the reset?"
independently, with three different name sets:

    render.default_stimulus     {"clk", "rst", "reset"}
    runtime.Env.reset           ("rst", "reset", "rst_n", "resetn")
    validate._random_inputs     {"clk", "clock", "rst", "reset", "rst_n", "resetn"}

On `i2c_master_bit_ctrl`, whose reset is named `nReset`, all three missed it and
each one broke differently: the stimulus randomised a reset, G4 fed the model a
randomised reset, and the runtime asserted no reset at all. Meanwhile `rst` --
which that design *also* declares -- was dropped from the bundle by all three, so
the generated model raised `KeyError('rst')` on its first call and the whole node
failed before a single testpoint ran.

Two rules follow, and both are load-bearing:

1. **Classification is shared.** Exactly one function decides, and everyone asks
   it. Three sets cannot agree by accident.
2. **Excluding a port from stimulus does not remove it from the bundle.** The
   runtime owns the clock and the reset, so neither is *randomised* -- but both
   are still declared inputs, so the reference model is entitled to read them.
   They are pinned to their inactive value, not deleted.

`clk_cnt` is why clock matching is exact rather than by token: it is a real
functional input on the I2C design and a substring rule would silently drop it.
"""

from __future__ import annotations

# Exact names only. A token rule would swallow `clk_cnt`, `clk_div`, `clken`.
CLOCK_NAMES = frozenset({
    "clk", "clock", "clk_i", "i_clk", "clki", "sysclk", "sys_clk", "aclk",
})

RESET_NAMES = frozenset({
    "rst", "reset", "rst_n", "rstn", "reset_n", "resetn",
    "nrst", "nreset", "n_rst", "n_reset",
    "arst", "areset", "arst_n", "aresetn", "arstn",
    "srst", "sreset", "rst_i", "reset_i", "rst_ni",
})


def is_clock(name: str) -> bool:
    return str(name).strip().lower() in CLOCK_NAMES


def is_reset(name: str) -> bool:
    return str(name).strip().lower() in RESET_NAMES


def reset_is_active_low(name: str) -> bool:
    """`nReset`, `rst_n`, `resetn`, `aresetn` are asserted low; `rst` is not."""
    low = str(name).strip().lower()
    return low.startswith(("n", "n_")) or low.endswith(("n", "_n", "_ni", "ni"))


def inactive_value(name: str) -> int:
    """The value a runtime-owned port holds while the testcase is driving.

    The clock's level is meaningless to a `step()` model -- `step` *is* the edge
    -- so 0 is a placeholder, present so the key exists. The reset's value is not
    a placeholder: pinning it to deasserted is what lets the model exercise
    functional behaviour instead of sitting in reset for the whole sweep.
    """
    if is_reset(name):
        return 1 if reset_is_active_low(name) else 0
    return 0


def classify(contract: dict) -> tuple[list[str], list[str], list[str]]:
    """(clocks, resets, functional) over the contract's declared inputs, in order."""
    clocks: list[str] = []
    resets: list[str] = []
    functional: list[str] = []
    for port in contract.get("io") or []:
        if port.get("dir") != "input":
            continue
        name = str(port.get("name") or "")
        if not name:
            continue
        if is_clock(name):
            clocks.append(name)
        elif is_reset(name):
            resets.append(name)
        else:
            functional.append(name)
    return clocks, resets, functional


def input_names(contract: dict) -> list[str]:
    """Every declared input, in declaration order. The reference model's bundle."""
    return [
        str(p.get("name"))
        for p in (contract.get("io") or [])
        if p.get("dir") == "input" and p.get("name")
    ]


def pinned_inputs(contract: dict) -> dict[str, int]:
    """The runtime-owned inputs and the values they hold during stimulus."""
    clocks, resets, _ = classify(contract)
    return {name: inactive_value(name) for name in (*clocks, *resets)}
