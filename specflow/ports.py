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


#: Suffixes that mark a FUNCTIONAL input as asserted-low. Deliberately narrow:
#: `reset_is_active_low` accepts a bare trailing "n", which is right for reset
#: names but catastrophic here -- `din`, `en`, `sda_in` and `token` all end in
#: "n" and none of them is active-low. An explicit contract field is the real
#: answer; this only catches the unambiguous `_n` convention.
_ACTIVE_LOW_SUFFIXES = ("_n", "_ni", "_l", "_b")


def idle_value(name: str, spec: dict | None = None) -> int:
    """The value an input holds when nothing is asking the design to do anything.

    Order: the contract's own `idle_value` for the port, then the reset rule,
    then the `_n` convention, then 0.

    `inactive_value` returned 0 for every non-reset port, and 0 is simply wrong
    for an active-low or open-drain input. On `i2c_master_bit_ctrl` that put
    `scl_i` and `sda_i` LOW during reset -- a bus stuck low -- while the DUT saw
    X on the same pins, so the two started from different states. It also made
    the comparison actively perverse: `dout` accounted for 996 of 2016 diverging
    edges, and because golden leaves `dout` unreset while a wrong candidate
    zeroes it exactly as the model does, the harness scored the WRONG RTL above
    golden. A harness that rewards disagreeing with the reference is worse than
    no harness.
    """
    if spec is not None:
        declared = spec.get("idle_value")
        if isinstance(declared, bool):
            return int(declared)
        if isinstance(declared, int):
            return int(declared)
    if is_reset(name):
        return 1 if reset_is_active_low(name) else 0
    if is_clock(name):
        return 0
    return 1 if str(name).strip().lower().endswith(_ACTIVE_LOW_SUFFIXES) else 0


def idle_values(contract: dict) -> dict[str, int]:
    """Every declared input mapped to its idle value, in declaration order."""
    return {
        str(p.get("name")): idle_value(str(p.get("name")), p)
        for p in (contract.get("io") or [])
        if p.get("dir") == "input" and p.get("name")
    }


def asserted_resets(contract: dict, only: list[str] | None = None) -> dict[str, int]:
    """Each reset port mapped to its ACTIVE value -- the mirror of `pinned_inputs`.

    `idle_value` gives the level a reset holds when it is NOT asserting; for a
    one-bit reset the assertion is its complement, whether that came from the
    contract's own `idle_value`, the active-low convention, or the name rule.
    Deriving it rather than re-reading the convention keeps a design that
    declares an explicit `idle_value` honoured in both directions.
    """
    _, resets, _ = classify(contract)
    # A SUBSET, WHEN THE STEP NAMES ONE. A design with two reset ports cannot
    # otherwise be asked about either: asserting all of them together makes
    # "rst asserted while nReset is released" a state the runtime never
    # produces, and a requirement about which reset is which is then
    # unjudgeable. Measured on a2-i2c: 204 replayed edges, one row with rst==1,
    # nReset==0 on that same row, and zero rows with rst==1 and nReset==1 --
    # so REQ-0006 and REQ-0007 abstained by construction.
    if only is not None:
        wanted = {str(n) for n in only}
        resets = [n for n in resets if n in wanted]
    by_name = {
        str(port.get("name")): port
        for port in (contract.get("io") or []) if port.get("name")
    }
    return {name: 0 if idle_value(name, by_name.get(name)) else 1 for name in resets}


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
    """The runtime-owned inputs and the values they hold during stimulus.

    Contract-aware now, so a design that declares an explicit `idle_value` for
    its reset is honoured rather than second-guessed by the name rule.
    """
    clocks, resets, _ = classify(contract)
    by_name = {
        str(p.get("name")): p
        for p in (contract.get("io") or []) if p.get("name")
    }
    return {
        name: idle_value(name, by_name.get(name))
        for name in (*clocks, *resets)
    }
