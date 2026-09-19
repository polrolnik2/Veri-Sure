"""A check is a question about the whole run, not about one sampled instant.

The comparison used to be `env.check(uid, signal, expected, stim)` inside the
stimulus loop: one signal, at one moment, once per vector. On
`i2c_master_bit_ctrl` that looked at 3 of 12 cycles and a median of 4 of the 8
outputs, so a faithful line-by-line transliteration of the golden design scored
77 of 168 -- not because it was misaligned, but because most of the divergence
was never examined.

Registering the check and resolving it over the recorded trace asks instead
whether the DUT produced the model's ordered sequence of output states. These
cases pin what that does and does not judge, and -- the part that matters most
-- that it cannot pass by comparing nothing.
"""

from __future__ import annotations

from specflow.tb.runtime import Env


class _Handle:
    def __init__(self, value):
        self.value = value


class _Dut:
    def __init__(self, **ports):
        for name, value in ports.items():
            setattr(self, name, _Handle(value))


class _Model:
    OUTPUT_PORTS = ["y", "z"]

    def step(self, inputs):  # pragma: no cover -- never advanced here
        return {"y": 0, "z": 0}


def _env(tmp_path, trace, *, inputs=None):
    """An Env with a hand-written trace, so no simulator is involved."""
    env = Env(_Dut(y=0, z=0), "TP-0001", _Model(), tmp_path, input_ports=["a"])
    env._inputs = dict(inputs or {"a": 1})
    for i, (dut, model) in enumerate(trace):
        env._trace.append((dut, model, i // 2, env._inputs))
    return env


def _rows(env, uid="CHK-0001", signals=("y",)):
    env.check(uid, *signals)
    env._resolve()
    return env.sb


# ------------------------------------------------------- what is ignored


def test_a_state_held_longer_than_the_model_still_passes(tmp_path):
    """The decision, in one case: content is compared, duration is not.

    `contract.timing.cmd_ack.latency_cycles` was 3 in one run of the same spec
    and 1 in the next, while golden takes 5 `clk_en` phases -- so a cycle-exact
    comparison was being enforced against a number nothing could settle. It paid
    the full price of strictness, rejecting correct RTL, and still did not match
    golden.
    """
    trace = [({"y": 0}, {"y": 0}), ({"y": 1}, {"y": 1}),
             ({"y": 1}, {"y": 0}), ({"y": 0}, {"y": 0})]
    sb = _rows(_env(tmp_path, trace))
    assert sb.failed == [], sb.mismatches
    assert sb.invoked == ["CHK-0001"]


# ------------------------------------------------------- what is not


def test_a_skipped_state_fails(tmp_path):
    """Ignoring durations must not become ignoring states."""
    # The model passes through 1 on its way to 2; the DUT jumps straight there.
    trace = [({"y": 0}, {"y": 0}), ({"y": 2}, {"y": 1}), ({"y": 2}, {"y": 2})]
    sb = _rows(_env(tmp_path, trace))
    assert sb.failed == ["CHK-0001"]
    assert sb.mismatches[0]["step"] == 1
    assert sb.mismatches[0]["got"] == 2 and sb.mismatches[0]["expected"] == 1


def test_a_run_that_stops_early_has_not_agreed(tmp_path):
    """Two states where the model expects three is a failure, not a prefix."""
    trace = [({"y": 0}, {"y": 0}), ({"y": 1}, {"y": 1}), ({"y": 1}, {"y": 0})]
    sb = _rows(_env(tmp_path, trace))
    assert sb.failed == ["CHK-0001"]
    m = sb.mismatches[0]
    assert m["got"] is None and m["signal"] is None
    assert "stopped after 2 output state" in m["reason"]


def test_every_diverging_output_is_named_not_only_the_first(tmp_path):
    """A state is the tuple of the check's signals, so several can diverge.

    `signal` keeps naming the first so an older reader sees what it always saw;
    `signals` carries the rest, and `trace_summary` ranks by the full set --
    otherwise "which output is wrong most often" under-reports every output but
    one, which is the only question that summary exists to answer.
    """
    trace = [({"y": 0, "z": 0}, {"y": 0, "z": 0}),
             ({"y": 1, "z": 1}, {"y": 2, "z": 2}),
             ({"y": 1, "z": 1}, {"y": 2, "z": 2})]
    sb = _rows(_env(tmp_path, trace), signals=("y", "z"))
    m = sb.mismatches[0]
    assert m["signals"] == ["y", "z"] and m["signal"] == "y"
    assert m["got"] == {"y": 1, "z": 1} and m["expected"] == {"y": 2, "z": 2}


def test_the_context_is_the_vector_in_force_when_the_state_began(tmp_path):
    """`@state4` is unactionable without knowing what was being driven.

    The divergence index is an index into the run-length-encoded state sequence,
    so it is neither a cycle nor a stimulus vector. The stimulus travels with
    each recorded edge precisely so the failure can name the vector that
    produced it rather than whichever vector happened to be last.
    """
    env = Env(_Dut(y=0), "TP-0001", _Model(), tmp_path, input_ports=["a"])
    for i, (d, m) in enumerate([(0, 0), (0, 0), (1, 1), (1, 1), (0, 1), (1, 1)]):
        env._trace.append(({"y": d}, {"y": m}, i // 2, {"a": i // 2}))
    env._inputs = {"a": 99}
    sb = _rows(env)
    assert sb.failed == ["CHK-0001"]
    # Divergence is the third DUT state, which began on the third vector.
    assert sb.mismatches[0]["ctx"] == {"vector": 2, "a": 2}


# ------------------------------------------------------- vacuity


def test_a_check_that_compared_nothing_fails(tmp_path):
    """The guarantee that moving the comparison off the sample could have lost.

    `transactional([], [])` is trivially equal, so a testpoint whose trace is
    empty -- no clock and therefore no recorded edge, or a model declaring no
    outputs -- would report every check as PASSED having looked at nothing. That
    is exactly the vacuity `render.py` and G5 exist to make impossible.
    """
    sb = _rows(_env(tmp_path, []))
    assert sb.failed == ["CHK-0001"]
    assert "compared no cycles" in sb.mismatches[0]["reason"]


def test_a_clockless_design_records_its_evaluation(tmp_path):
    """The combinational path must record too, or every check on it is vacuous.

    A design with no clock takes the `Timer` branch of `settle` and never
    reached `_record`. Left alone that is 20 of the 64 ChipVerilog task modules
    passing every check with an empty trace -- the exact failure the
    `clock_named_clock` fixture already caught once, where both sides agreed
    because neither side did anything.

    Driven here with a stub trigger rather than a simulator; the same path runs
    for real in `tests/test_harness_conformance.py`, whose `comb_adder` case
    must reject a tied-off DUT and could not if the trace stayed empty.
    """
    import asyncio
    import sys
    import types

    from specflow.refmodel.base import RefModel

    class _Comb(RefModel):
        OUTPUT_PORTS = ["y"]

        def evaluate(self, inputs):
            return {"y": inputs["a"] & 1}

    async def _noop():
        return None

    stub = types.ModuleType("cocotb.triggers")
    stub.Timer = lambda *a, **k: _noop()
    saved = sys.modules.get("cocotb.triggers")
    sys.modules["cocotb.triggers"] = stub
    try:
        dut = _Dut(a=0, y=0)
        env = Env(dut, "TP-0001", _Comb(), tmp_path, input_ports=["a"])

        async def run():
            for value in (0, 1, 1, 0):
                dut.a.value = value
                dut.y.value = value
                await env.drive({"a": value})

        asyncio.run(run())
    finally:
        if saved is None:
            sys.modules.pop("cocotb.triggers", None)
        else:
            sys.modules["cocotb.triggers"] = saved

    assert len(env._trace) == 4
    sb = _rows(env)
    assert sb.failed == [], sb.mismatches


# ------------------------------------------------- a crash is not a verdict


class _Immutable:
    """A handle the simulator refuses to write, as Verilator's do for a signal
    it has optimised into a constant."""

    def __init__(self):
        self._value = 0

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, _):
        raise TypeError("Attempted setting an immutable object")


def test_a_port_the_design_does_not_have_is_a_verdict_not_a_crash(tmp_path):
    """A crash before `finish()` costs the evidence, not just the testpoint.

    `drive()` raised `AttributeError` on a missing port and `sample()` raised it
    on a missing output, so a candidate that simply omitted a declared port
    produced NO record at all -- and the suite lost the verdict for exactly the
    defect it had found. Measured across the 64 ChipVerilog references, this
    accounted for 7 designs reporting no record.
    """
    env = Env(_Dut(y=0), "TP-0001", _Model(), tmp_path, input_ports=["a", "gone"])
    env._drive("gone", 1)
    env.check("CHK-0001", "y")
    env._resolve()
    assert env.sb.failed == ["CHK-0001"]
    assert "gone" in env.sb.mismatches[0]["reason"]


def test_a_value_the_port_cannot_hold_is_a_verdict_not_a_crash(tmp_path):
    """2 on a 1-bit input. `gate_suite` rejects it in a generated suite, but the
    runtime must not lose the record when one reaches it anyway."""
    class _OneBit:
        def __init__(self):
            self._v = 0

        @property
        def value(self):
            return self._v

        @value.setter
        def value(self, v):
            if v > 1:
                raise ValueError(f"{v} is not convertible to Logic")
            self._v = v

    dut = _Dut(y=0)
    dut.a = _OneBit()
    env = Env(dut, "TP-0001", _Model(), tmp_path, input_ports=["a"])
    env._drive("a", 2)
    env.check("CHK-0001", "y")
    env._resolve()
    assert env.sb.failed == ["CHK-0001"]
    assert "could not be driven" in env.sb.mismatches[0]["reason"]


def test_a_handle_the_simulator_will_not_write_is_a_verdict_too(tmp_path):
    """And it must be caught in `reset()`, not only in `drive()`.

    Reset drives every input to its idle value before the stimulus runs, so an
    unwritable handle killed the testpoint one step earlier than `drive()` --
    before a single vector had been applied.
    """
    dut = _Dut(y=0)
    dut.a = _Immutable()
    env = Env(dut, "TP-0001", _Model(), tmp_path, input_ports=["a"])
    env._drive("a", 0)
    assert env.bad_stimulus and "immutable" in env.bad_stimulus[0]


def test_internal_trace_is_off_unless_asked(tmp_path, monkeypatch):
    """The per-edge internal dump is a debug instrument. Unset, `_record` must
    do no extra work and `finish` must write no extra file -- it runs inside
    every testpoint of every suite."""
    import importlib

    import specflow.tb.runtime as runtime

    monkeypatch.delenv("SPECFLOW_TRACE_INTERNALS", raising=False)
    importlib.reload(runtime)
    assert runtime._INTERNALS == []

    monkeypatch.setenv("SPECFLOW_TRACE_INTERNALS", "cnt, clk_en ,")
    importlib.reload(runtime)
    assert runtime._INTERNALS == ["cnt", "clk_en"]

    monkeypatch.delenv("SPECFLOW_TRACE_INTERNALS", raising=False)
    importlib.reload(runtime)


def test_a_signal_the_model_does_not_carry_is_not_a_disagreement():
    """`divergence_trace` compares DUT internals against model attributes of the
    same name. A name the model lacks reads back `None` on every edge, which is
    the model not having that concept -- not a disagreement.

    Counting it as one is worse than useless. On the generated i2c model, naming
    golden's `sta_condition` (which that model never stores) made every edge
    disagree and reported the first divergence at edge 0, hiding the real one at
    edge 1.
    """
    from benchmarks.divergence_trace import unmodelled

    edges = [
        {"dut_internal": {"absent": 0, "real": 1},
         "model_internal": {"absent": None, "real": 1}},
        {"dut_internal": {"absent": 1, "real": 1},
         "model_internal": {"absent": None, "real": 0}},
    ]
    assert unmodelled(["absent", "real"], edges) == ["absent"]


def test_a_signal_the_model_carries_only_sometimes_is_still_compared():
    """`None` on SOME edges is a real divergence -- a model that stops updating
    a register half way through is exactly the defect worth catching."""
    from benchmarks.divergence_trace import unmodelled

    edges = [
        {"dut_internal": {"s": 0}, "model_internal": {"s": 0}},
        {"dut_internal": {"s": 1}, "model_internal": {"s": None}},
    ]
    assert unmodelled(["s"], edges) == []


def test_no_edges_means_nothing_is_declared_unmodelled():
    """An empty trace proves nothing either way; it must not silently mark every
    named signal as absent and report a clean comparison."""
    from benchmarks.divergence_trace import unmodelled

    assert unmodelled(["a", "b"], []) == []
