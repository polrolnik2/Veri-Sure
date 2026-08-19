"""The reference-model base. Hand-written, never generated.

One class with two entry points rather than a `TransactionModel` /`CycleModel`
hierarchy: the hierarchy is premature until the two shapes need divergent
helpers, and `compose.py` decides which entry point the testbench calls from the
contract's `clocking.is_sequential`.

**This module imports nothing from cocotb and knows nothing about simulation.**
The model is an ordinary Python object that can be driven from a REPL. cocotb
appears only where `tb/runtime.py` calls `evaluate()`/`step()` to obtain an
expected value. That independence is what lets G4 run under plain pytest with no
simulator, and lets the model be debugged in isolation from the RTL.
"""

from __future__ import annotations


class RefModel:
    """Expected-value oracle derived from the specification alone.

    The subclass is generated whole and shaped like the DESIGN -- a synchroniser,
    a filter, a divider, an FSM -- not like the requirement list. It writes its
    own dispatch, because execution order is where reset priority lives, and
    declares a coverage map from requirement uid to the methods implementing it.
    (It used to be one method per requirement named `_req_NNNN`; that produced a
    262-line `_req_0000` holding 85% of the design and 23 stubs around it.)

    The generated subclass never sees the RTL -- `compose.py` does not put it in
    the agent's input bundle, and at the point S1-S5 run there is no `rtl.sv` in
    existence to see.
    """

    #: Output port names, from the contract. `evaluate`/`step` must write every
    #: one of them; a port left unwritten means the model does not determine it,
    #: which G4 rejects.
    OUTPUT_PORTS: list[str] = []

    #: Cycles between a stimulus and the output that answers it. 0 is
    #: combinational. Used by the testbench to align sampling, not by the model.
    LATENCY_CYCLES: int = 0

    def reset(self) -> None:
        """Return to the post-reset state. Sequential models override."""

    def evaluate(self, inputs: dict) -> dict:
        """Combinational: inputs -> outputs, no state."""
        raise NotImplementedError

    def step(self, inputs: dict) -> dict:
        """Sequential: advance ONE clock edge and return the outputs.

        One call, one edge. The testbench calls this once per rising edge of the
        DUT's clock and compares the result against the DUT at that same edge,
        so a model that advances a whole transaction per call is a different
        machine from the design and will fail a correct DUT.

        `tb/runtime.py` used to call it once per stimulus VECTOR while clocking
        the DUT `LATENCY_CYCLES + 1` edges, which on a design whose contract
        reported `latency_cycles: 3` ran the DUT at 4x the model's rate. Both
        sides now advance together in `Env.settle`.

        Default delegates to `evaluate` so a combinational model can be driven
        through either entry point without the caller special-casing it.
        """
        return self.evaluate(inputs)

    # -- helpers available to generated fragments -------------------------

    @staticmethod
    def mask(value: int, width: int) -> int:
        """Truncate to `width` bits, matching hardware wraparound.

        Provided because the single most common reference-model error is
        modelling an unbounded Python int where the hardware has a fixed width,
        which shows up as a mismatch only at the boundary the spec cared about.
        """
        return int(value) & ((1 << int(width)) - 1)

    @staticmethod
    def sign_extend(value: int, width: int) -> int:
        """Interpret a `width`-bit pattern as two's complement."""
        value = int(value) & ((1 << int(width)) - 1)
        sign = 1 << (int(width) - 1)
        return (value ^ sign) - sign
