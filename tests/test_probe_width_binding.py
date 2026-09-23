"""A probe must not bind a signal wider than the contract declares.

**A BINDING THAT READS A DIFFERENT QUANTITY IS WORSE THAN NO BINDING.** Probe
rule 4 reuses the specification's own identifier lower-cased (`cSCL` ->
`cscl`), while `probe_block` obliges every probe to be a BOOLEAN. So the stage
mints a one-bit predicate named after whatever the specification called the
state -- and a design that carries that state, under that name, at its real
width binds successfully and is then sampled as if it were the predicate.

Measured on the known-good i2c design: `fscl` is declared `width: 1` beside a
span, in the same contract entry, reading "the three-sample histories `fSCL`
and `fSDA`". It bound a three-bit register reading 0..7 where the check expects
0 or 1, and three of the fifteen checks convicting that design convict it on
such a read.
"""

from specflow.refmodel.compose import probe_widths


class _Handle:
    """A DUT signal of a fixed width."""

    def __init__(self, width, value):
        self._width, self.value = width, value

    def __len__(self):
        return self._width


class _Dut:
    pass


class _Ref:
    PROBE_WIDTHS = {"fscl": 1, "idle": 1}


class _Ref2:
    PROBE_WIDTHS = {"cscl": 1}


def _env(dut, ref):
    """An `Env` with only the two attributes `sample` reads."""
    from specflow.tb import runtime

    env = object.__new__(runtime.Env)
    env.dut, env.ref = dut, ref
    return env


def _clear():
    from specflow.tb import runtime

    runtime._WIDTH_REFUSED.clear()
    runtime._CASE_BOUND.clear()
    runtime._SAMPLED_WIDTH.clear()


def test_a_wider_signal_is_refused_not_sampled():
    from specflow.tb import runtime

    _clear()
    dut = _Dut()
    dut.fscl = _Handle(3, 7)      # the three-sample history, not the predicate
    dut.idle = _Handle(1, 1)      # a genuine one-bit probe
    env = _env(dut, _Ref())

    assert env.sample("fscl") is None, (
        "a 3-bit signal bound to a probe declared 1-bit must NOT be sampled: "
        "the value read is a different quantity from the one the check means")
    assert runtime._WIDTH_REFUSED["fscl"] == (1, 3), (
        "the refusal has to be RECORDED, or an abstention with a cause is "
        "indistinguishable from a design that simply lacks the signal")
    assert env.sample("idle") == 1, "a conforming probe must still bind"


def test_one_bit_too_wide_is_already_a_different_quantity():
    """The boundary is `wider at all`, not `much wider`.

    `cscl` on the known-good i2c design is a TWO-bit synchroniser reading 0..3
    against a probe declared one bit -- one bit too wide, and already a
    different quantity. A guard that only caught the three-bit `fscl` case
    would pass this straight through, and REQ-0061 and REQ-0102 convict that
    design on exactly `cscl`/`csda`.
    """
    from specflow.tb import runtime

    _clear()
    dut = _Dut()
    dut.cscl = _Handle(2, 3)
    env = _env(dut, _Ref2())

    assert env.sample("cscl") is None
    assert runtime._WIDTH_REFUSED["cscl"] == (1, 2)


def test_the_case_fallback_does_not_smuggle_a_wider_signal_in():
    """The fallback found the name; the width still has to hold."""
    from specflow.tb import runtime

    _clear()
    dut = _Dut()
    dut.fSCL = _Handle(3, 7)      # spelled as the specification spells it
    env = _env(dut, _Ref())

    assert env.sample("fscl") is None
    assert runtime._WIDTH_REFUSED["fscl"] == (1, 3)
    assert "fscl" not in runtime._CASE_BOUND, (
        "a refused binding must not be reported as a successful case-insensitive "
        "one -- the run would then name a binding that did not happen")


def test_an_absent_declaration_changes_nothing():
    """Artifacts frozen before `PROBE_WIDTHS` existed keep their behaviour."""
    from specflow.tb import runtime

    _clear()
    dut = _Dut()
    dut.fscl = _Handle(3, 7)

    class _Old:
        pass

    assert _env(dut, _Old()).sample("fscl") == 7
    assert not runtime._WIDTH_REFUSED


def test_a_narrower_or_equal_signal_binds():
    from specflow.tb import runtime

    _clear()
    dut = _Dut()
    dut.idle = _Handle(1, 0)
    assert _env(dut, _Ref()).sample("idle") == 0
    assert not runtime._WIDTH_REFUSED


def test_widths_come_from_the_contract_probe_entries():
    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
        {"name": "fscl", "dir": "probe", "width": 1},
        {"name": "wide", "dir": "probe", "width": 3},
    ]}
    assert probe_widths(contract) == {"fscl": 1, "wide": 3}, (
        "only probe entries, and the declared width rather than a default")


def test_the_generated_model_carries_the_widths():
    """`render` must EMIT the map, not merely be able to compute it.

    Pinned at the call site because a stage-level constant that is computed and
    never written is invisible to every behavioural test: the runtime would read
    `PROBE_WIDTHS` off a model that does not define it, `getattr` would return
    None, and the guard would silently stop guarding.
    """
    from specflow.refmodel.compose import RefModelOutput, render

    contract = {"io": [
        {"name": "fscl", "dir": "probe", "width": 1},
        {"name": "wide", "dir": "probe", "width": 3},
    ]}
    out = RefModelOutput(reasoning="", source="    def evaluate(self):\n        pass\n")
    src = render(out, contract)
    assert "PROBE_WIDTHS = {'fscl': 1, 'wide': 3}" in src, (
        "the generated model must define PROBE_WIDTHS; without it the runtime "
        "guard reads None and every wider signal binds again")


def test_the_sampled_width_is_recorded_even_when_the_refusal_is_INERT():
    """**AND THAT IS THE CASE THAT MATTERS**, because it is the one on disk.

    The refusal above needs `PROBE_WIDTHS` on the reference model. An artifact
    frozen before that existed has none -- `full2`'s `ref_model.py` does not
    define it, and its 482-testpoint golden replay recorded `width_refused: {}`
    -- so the refusal is inert and the TRACE is the only place the width can
    survive to reach `rtl_trace.declared_width_gap`.

    Recorded for every sampled signal, not only refused ones, because the
    consumer decides by declaration and needs the fact rather than this module's
    verdict about it.
    """
    from specflow.tb import runtime

    _clear()

    class _NoWidths:
        pass

    dut = _Dut()
    dut.idle = _Handle(18, 0)
    env = _env(dut, _NoWidths())
    assert env.sample("idle") == 0, (
        "with no PROBE_WIDTHS the refusal must stay inert and sample as before")
    assert runtime._WIDTH_REFUSED == {}
    assert runtime._SAMPLED_WIDTH["idle"] == 18, (
        "without this the 18-bit register reading 0 is indistinguishable from a "
        "flag that is low, and REQ-0100 convicts the known-good design for it")
    _clear()


def test_a_signal_with_no_length_records_no_width():
    """`len()` is not defined on every handle, and inventing a width for one
    that cannot report it would be this module guessing."""
    from specflow.tb import runtime

    _clear()

    class _Bare:
        value = 1

    dut = _Dut()
    dut.flag = _Bare()
    assert _env(dut, _Ref()).sample("flag") == 1
    assert "flag" not in runtime._SAMPLED_WIDTH
    _clear()
