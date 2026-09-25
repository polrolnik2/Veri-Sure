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

    # -- the sampled-edge form: what an assertion sees, then the edge ------
    #
    # **A ROW IS ONE CLOCK EDGE AS AN ASSERTION SAMPLES IT.** The inputs
    # present at the edge, and every output and probe as it stands at that
    # edge BEFORE the edge takes effect -- the value SVA reads in the preponed
    # region. A registered output or a state therefore changes in the row
    # AFTER the edge that updates it; a combinational output answers the
    # inputs of its own row.
    #
    # WHY IT IS TWO METHODS. `step` used to be one call that advanced and
    # returned "the outputs", and nothing said which side of the edge those
    # were. Seven models written from one prompt answered it three ways --
    # outputs from the pre-edge state and probes from the post-edge one; both
    # post-edge; and one OR-ing a before and an after value of each ack "so
    # the ack is visible" -- while the simulator sampled a fourth: the
    # post-edge state beside the inputs that caused it, where a
    # combinational ack that coincides with leaving a state is never
    # recorded at all. Measured on or1200_dc_fsm, that pairing is the
    # largest single cause of checks convicting the known-good design. Split,
    # the question cannot be answered two ways: `outputs` cannot see the
    # edge it precedes.

    def outputs(self, inputs: dict) -> dict:
        """Everything a row shows at this edge, before it takes effect.

        Registered outputs as they stand; combinational outputs computed from
        that state and `inputs`. Sets every probe attribute the same way. Must
        not change any state -- `advance` does that.
        """
        raise NotImplementedError

    def advance(self, inputs: dict) -> None:
        """Take the edge: update state from the current state and `inputs`."""
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

        A model written in the sampled-edge form (`outputs` + `advance`) is
        driven here, so every caller of `step` -- the simulator runtime, the
        replay, the generation gate -- gets the same row without knowing which
        form the model took. The probes are captured between the two calls,
        because an attribute read after `step` returns shows the state AFTER
        the edge, which is the next row's.
        """
        if samples_before_edge(self):
            out = self.outputs(inputs)
            self._sampled_probes = {
                str(n): getattr(self, str(n), None)
                for n in (getattr(self, "PROBE_PORTS", None) or ())}
            self.advance(inputs)
            return out
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


def samples_before_edge(ref: object) -> bool:
    """Is `ref` written in the sampled-edge form (`outputs` + `advance`)?

    Decided by what the class implements, the way the runtime already decides
    `step` against `evaluate`, so an artifact written before the form existed
    keeps the convention it was written and checked under.
    """
    cls = type(ref)
    return (getattr(cls, "outputs", RefModel.outputs) is not RefModel.outputs
            and getattr(cls, "advance", RefModel.advance) is not RefModel.advance
            and getattr(cls, "step", RefModel.step) is RefModel.step)


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
    #: THE VALUE AT THE EDGE, for a model in the sampled-edge form: `step`
    #: captured it between `outputs` and `advance`. The attribute itself
    #: already shows the state after the edge.
    sampled = getattr(ref, "_sampled_probes", None)
    sampled = sampled if isinstance(sampled, dict) else None
    #: **A WIDE PROBE IS A VALUE.** This collapsed every probe to 0/1, so a
    #: 3-bit filter history read 1 in every replay row while the simulator
    #: recorded 0..7 for the same quantity -- two recordings of one design
    #: disagreeing on every check that reads it.
    widths = getattr(ref, "PROBE_WIDTHS", None) or {}
    out: dict = {}
    for name in names or ():
        if str(name) not in declared:
            #: Unavailable. `decide` turns a check that READS one of these into
            #: an abstention, so the check is not judged against a fiction.
            out[str(name)] = None
            continue
        value = (sampled.get(str(name)) if sampled is not None
                 else getattr(ref, name, None))
        width = int(widths.get(str(name), 1) or 1) if isinstance(widths, dict) else 1
        if width > 1 and isinstance(value, (int, bool)):
            out[str(name)] = int(value) & ((1 << width) - 1)
        else:
            out[str(name)] = 1 if value else 0
    return out
