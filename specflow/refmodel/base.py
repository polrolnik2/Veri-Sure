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

    #: Probe names, from the contract's `dir: "probe"` entries. A probe is a
    #: SPECIFICATION TERM made observable -- `in_lrefill3` is true exactly when
    #: the model is in the state the spec calls LREFILL3 -- so that a check can
    #: name the moment its requirement is about instead of proxying it through a
    #: combination of outputs.
    #:
    #: DELIBERATELY A SEPARATE LIST, and that is the whole design. Putting probes
    #: in `OUTPUT_PORTS` would be free plumbing and would drag in every gate
    #: keyed on it at once: `validate`'s every-output-written-every-call rule
    #: (wrong for a state that is False most of the time), the bidirectional
    #: OUTPUT_PORTS check, `_ports_agree`, `compose.output_ports`,
    #: `variants._widths` and `liveness._widths`. Kept separate, all of those are
    #: untouched, and the obligation on a probe is only that it is READABLE --
    #: presence, not determination.
    PROBE_PORTS: list[str] = []

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


def probe_names(contract: dict) -> list[str]:
    """The contract's `dir: "probe"` names, in declaration order."""
    return [
        str(p.get("name"))
        for p in ((contract or {}).get("io") or [])
        if p.get("name") and p.get("dir") == "probe"
    ]


def probe_values(ref: object, names: list[str] | tuple[str, ...]) -> dict:
    """Sample probes off a model instance, as 0/1.

    ONE helper for both runtimes. Probes are sampled in two places -- the cocotb
    suite (`tb/runtime.Env._record`) and the oracle stage's own replay
    (`refmodel/oracles.replay`) -- and those two drive the SAME frozen checks.
    Any difference between them is a place where a check can pass its gate
    meaning one thing and be judged meaning another, which is the reason
    `replay` already imports the testbench's own step decoder rather than
    reimplementing it.

    A missing attribute on a model that DECLARES the probe samples as 0, not
    None. `None` in a row is what a check reads when it silently never fires,
    and an absent attribute on a model that claims the probe is far more likely
    to mean "this model is not in that state" than to mean anything a check
    should reason about. `validate`'s check 3c catches that case LOUDLY, at
    generation, so nothing has to be inferred from it here.

    **A PROBE THE MODEL DOES NOT DECLARE IS UNAVAILABLE, AND UNAVAILABLE IS NOT
    FALSE.** That distinction is the whole of this function's second half, and
    omitting it put a number on the board that measured nothing. The i2c
    control declares no `PROBE_PORTS` -- it predates probes, as do the nine
    standing yardstick designs and every benchmark RTL -- so all sixteen of a
    run's probes sampled 0 against it: never idle, never in a start sequence,
    never holding an active command. Of 19 checks that convicted the control,
    **18 read a probe**; of the 14 that read none, **1** convicted. The audit
    column was reporting "this design predates this run's probe table".

    `_ports_agree` already refuses to reuse a witness whose `PROBE_PORTS`
    disagree with the contract, for exactly this reason: "a witness reused
    across a contract change in its probe set would decide against a different
    row list than the one its checks were authored against, silently." This is
    that rule applied where the disagreement cannot be repaired by regenerating
    -- a foreign design is not the pipeline's to rewrite.

    A model declaring no probes at all is the common case of the same rule, not
    a separate one: it declares none of them, so none of them is available.
    """
    declared = set(getattr(ref, "PROBE_PORTS", None) or ())
    out: dict = {}
    for name in names or ():
        if str(name) not in declared:
            #: Unavailable. `decide` turns a check that READS one of these into
            #: an abstention, so the check is not judged against a fiction.
            out[str(name)] = None
            continue
        value = getattr(ref, name, None)
        out[str(name)] = 1 if value else 0
    return out
