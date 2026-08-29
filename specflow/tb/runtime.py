"""The testbench runtime. Hand-written, protected, never generated.

This module owns everything that decides a verdict: the clock, the reset, the
scoreboard, the coverage recorder and the result record. A rendered testcase
supplies only stimulus. That split is what makes the design safe rather than
merely well-intentioned:

* a generated testcase cannot contain a dead check, because it does not write
  checks -- the renderer emits them from the coverage model;
* a generated testcase cannot smuggle in a mirrored oracle, because expected
  values come from the frozen reference model and nowhere else;
* adding a testcase is monotone -- it can add obligations, never remove one.

**The verdict is data, not text.** `Env.finish()` writes a JSON record. Nothing
downstream parses prose for a PASS marker, which deletes an entire failure class:
`sim_reviewer`'s `_EXPLICIT_PASS_RE` and friends exist because 5 of 30 recorded
oracles could never print a marker the harness recognised, and were scored as
design failures for it.

`Env.check()` records and returns -- it never raises. That is what makes a single
testcase report all of its mismatches instead of dying on the first.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..ports import idle_value, inactive_value, is_clock, is_reset

#: Internal signals to record per edge, from `SPECFLOW_TRACE_INTERNALS`.
#:
#: A defect in a reference model is almost never visible in its outputs at the
#: edge where it happens -- both control-model bugs were "read a value from the
#: wrong clock generation", and each surfaced as an output divergence many edges
#: later, in a different signal, after the model had fallen a whole command
#: behind. Localising one means comparing the two sides' INTERNALS edge by edge,
#: which is how both were pinned.
#:
#: An environment variable rather than a constructor argument because this has
#: to cross into the cocotb subprocess, which the harness does not construct --
#: the same reason `SPECFLOW_COMPARE` is one. Debug only: unset, `_record` does
#: no extra work and `finish` writes no extra file.
_INTERNALS: list[str] = [
    n.strip() for n in os.environ.get("SPECFLOW_TRACE_INTERNALS", "").split(",")
    if n.strip()
]

#: Edges an `until` step waits before giving up. Generous on purpose: a
#: prescaled design can legitimately take hundreds -- one i2c testpoint sets a
#: prescaler needing 506 edges for a single command -- and a bound that is too
#: tight turns a slow-but-correct design into a timeout. It exists to stop a
#: design that never responds from hanging the suite, not to police latency.
DEFAULT_UNTIL_TIMEOUT = 2000



@dataclass
class Scoreboard:
    """Accumulates check outcomes. Never raises."""

    invoked: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)

    def check(
        self,
        chk_uid: str,
        got: Any,
        expected: Any,
        ctx: dict | None = None,
        signal: str | None = None,
        step: int | None = None,
    ) -> bool:
        self.invoked.append(chk_uid)
        ok = got == expected
        if not ok:
            self.failed.append(chk_uid)
            # Every mismatch carries its own values and stimulus. The recorded
            # failure of the old flow was 210 MISMATCH lines carrying 2 actual
            # values, which told the repair agent nothing it could act on.
            #
            # `signal` is why this is not a cosmetic field. One check covers
            # every signal the coverage model listed for it -- on
            # `i2c_master_bit_ctrl` that is six outputs -- and the renderer emits
            # one `Env.check` call per signal under the same UID. Without the
            # name, "CHK-0002 expected=0 got=1" does not say whether `scl_oen`,
            # `sda_oen`, `busy`, `al`, `dout` or `cmd_ack` diverged, and a repair
            # agent handed 8 failing testpoints of that had nothing to act on.
            # It stalled at 8 for six consecutive simulation runs.
            self.mismatches.append(
                {
                    "check": chk_uid,
                    "signal": signal,
                    "step": step,
                    "got": _plain(got),
                    "expected": _plain(expected),
                    "ctx": {k: _plain(v) for k, v in (ctx or {}).items()},
                }
            )
        return ok

    def record(
        self,
        chk_uid: str,
        signals: list[str],
        verdict: Any,
        ctx: dict | None = None,
        timeouts: list[str] | None = None,
    ) -> bool:
        """Record one whole-run comparison, as `check` records one instant.

        The mismatch row keeps the shape everything downstream already reads --
        `check`, `signal`, `step`, `got`, `expected`, `ctx` -- so
        `integration.trace_summary`, `specflow_node.format_failures` and the
        repair loop's rollback guard need no change. Only the MEANING of `step`
        moves: it was a stimulus vector index, and it is now the index of the
        first divergent output state. Both are integers on the same monotone
        later-is-better axis, which is the only property the rollback guard
        relies on.

        `signals` is added alongside `signal` because a state is the tuple of
        every signal the check covers, and more than one of them can diverge on
        the same state. `signal` keeps naming the first, so an older reader sees
        what it always saw.
        """
        self.invoked.append(chk_uid)
        if getattr(verdict, "ok", False):
            return True
        self.failed.append(chk_uid)

        names = list(signals)
        got, expected = verdict.got, verdict.expected
        if got is None or expected is None:
            # The two runs are different lengths -- one side stopped. That is
            # not attributable to a signal, and naming one would be a guess.
            diverging: list[str] = []
        else:
            diverging = [
                n for n, g, e in zip(names, got, expected) if g != e
            ]
        self.mismatches.append(
            {
                "check": chk_uid,
                "signal": diverging[0] if diverging else None,
                "signals": diverging,
                "step": verdict.diverged_at,
                "got": _state(names, got),
                "expected": _state(names, expected),
                "ctx": {k: _plain(v) for k, v in (ctx or {}).items()},
                "reason": getattr(verdict, "reason", ""),
                "timeouts": list(timeouts or []),
            }
        )
        return False


@dataclass
class CoverageRecorder:
    """Functional coverage: which bins were reached.

    A dict, not a covergroup. Bin hit/no-hit is the only question the gate asks
    and a dict answers it, so the gating path needs no UCIS layer and no
    third-party coverage package.
    """

    hits: dict[str, int] = field(default_factory=dict)

    def hit(self, bin_uid: str) -> None:
        self.hits[bin_uid] = self.hits.get(bin_uid, 0) + 1


def is_reset_step(step: object) -> bool:
    """`{"reset": true}` -- sequence a reset here, rather than drive inputs.

    A separate predicate rather than a fifth element of `normalise_step`'s tuple
    because five call sites unpack that tuple by arity, and a reset step is
    something a caller must handle deliberately: a replay that ignored it would
    silently run the scenario without the reset it was written for.
    """
    return isinstance(step, dict) and bool(step.get("reset"))


def reset_ports(step: object) -> list[str] | None:
    """Which reset ports this step asserts. `None` means every declared one.

        {"reset": true}              every reset port -- the whole-design reset
        {"reset": ["rst"]}           that port only, the others left idle

    THE LIST FORM EXISTS BECAUSE A TWO-RESET DESIGN IS OTHERWISE UNASKABLE.
    `{"reset": true}` drives `rst` active AND `nReset` active at the same edge,
    so a requirement that distinguishes the synchronous reset from the
    asynchronous one -- which is the entire content of i2c's REQ-0006 -- can
    never observe the state it is about. It is not a stimulus defect and no
    hint fixes it; the scenario simply had no expression in the schema.

    `true` stays the default and keeps its meaning, because whole-design reset
    is what almost every testpoint wants and changing that would rewrite the
    semantics of every suite already on disk.
    """
    if not isinstance(step, dict):
        return None
    value = step.get("reset")
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return None


def normalise_step(step: dict) -> tuple[dict, int, dict | None, int]:
    """A stimulus step, in either shape, as `(inputs, hold, until, timeout)`.

    Two shapes are accepted so the change is not a flag day:

        {"a": 1, "b": 0}                                  # bare: inputs, held 1 edge
        {"inputs": {...}, "hold": 8}                      # held for N edges
        {"inputs": {...}, "until": {"port": "cmd_ack", "value": 1},
         "timeout": 200}                                  # held until an event

    A bare dict holds for ONE edge. It used to hold for `LATENCY_CYCLES + 1`,
    which tied how long a stimulus is applied to a per-output latency figure the
    contract guesses -- so an unstable contract silently changed the stimulus
    timing of the whole suite between runs, and two runs of one design were not
    comparable. Duration is a property of the test, not of a port's latency.

    `until` is what a multi-cycle design actually needs. Every testpoint on
    i2c_master_bit_ctrl had 3 vectors, and at 4 edges each that is 12 clocks
    against the 26 golden needs to finish one START: 61 of 168 testpoints could
    not complete a single command, and one asked for a prescaler needing 506.
    "Drive the command, then wait until it acknowledges" expresses that; a fixed
    edge count cannot.
    """
    if not isinstance(step, dict):
        return {}, 1, None, 0
    if "reset" in step or "inputs" in step or "hold" in step or "until" in step:
        inputs = dict(step.get("inputs") or {})
        until = step.get("until") if isinstance(step.get("until"), dict) else None
        try:
            hold = max(1, int(step.get("hold", 1)))
        except (TypeError, ValueError):
            hold = 1
        try:
            timeout = max(0, int(step.get("timeout", 0)))
        except (TypeError, ValueError):
            timeout = 0
        return inputs, hold, until, timeout
    return dict(step), 1, None, 0


def _plain(value: Any) -> Any:
    """Make a cocotb BinaryValue (or anything) JSON-safe."""
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    for attr in ("integer", "value"):
        try:
            return int(getattr(value, attr))
        except Exception:  # noqa: BLE001
            pass
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return str(value)


def _state(names: list[str], state: Any) -> Any:
    """A state tuple as something a repair agent can read.

    One signal stays a bare value, because `expected=1 got=0` is what the
    failure payload has always said. Several become a dict, so
    `expected={'scl_oen': 1, 'sda_oen': 0}` names which output is which instead
    of asking the reader to match a tuple against the check's signal list.
    `None` means the side had no state at all -- it ran out.
    """
    if state is None:
        return None
    values = [_plain(v) for v in state]
    if len(names) == 1 and len(values) == 1:
        return values[0]
    return dict(zip(names, values))


class Env:
    """Per-testpoint environment: clock, reset, reference model, verdict record."""

    def __init__(
        self,
        dut,
        tp_uid: str,
        model,
        results_dir: Path,
        input_ports: list[str] | None = None,
        pinned: dict[str, int] | None = None,
        idle: dict[str, int] | None = None,
    ):
        self.dut = dut
        self.tp_uid = tp_uid
        self.ref = model
        self.results_dir = Path(results_dir)
        self.sb = Scoreboard()
        self.cov = CoverageRecorder()
        # Every declared input, and the subset the runtime owns. The stimulus is
        # deliberately a strict subset of the first; `expect` closes the gap.
        self.input_ports = list(input_ports or [])
        self.pinned = dict(pinned or {})
        #: Every declared input's quiescent value. Supplied by the renderer from
        #: the contract; falls back to the name rules so an older suite still
        #: runs. `pinned` stays the runtime-owned subset and takes precedence.
        self.idle = {n: idle_value(n) for n in self.input_ports}
        self.idle.update(dict(idle or {}))
        self.idle.update(self.pinned)
        # Which stimulus step is being driven. The SystemVerilog path gave the
        # repair agent a `fail_time` to locate a failure in the waveform; this
        # backend had no temporal pointer at all, so a mismatch on a stateful
        # design could not be placed in its sequence. On a design whose stimulus
        # repeats a step, two identical context dicts are two different
        # situations, and without the index they are indistinguishable.
        self.step_index = -1
        #: Outputs from the most recent `drive()`, computed by advancing the
        #: model in lockstep with the DUT's clock. `expect()` returns this
        #: rather than taking a fresh step -- see `settle`.
        self._expected: dict | None = None
        #: The inputs of the step being driven, for `expect`/`check` context.
        self._inputs: dict = {}
        #: Declared ports the DUT does not expose. A verdict, not a crash.
        self.missing_ports: list[str] = []
        #: Stimulus values a port could not hold. Also a verdict, not a crash.
        self.bad_stimulus: list[str] = []
        #: `until` steps whose condition never occurred. Recorded rather than
        #: raised: a timeout is a verdict about the design, and one testpoint
        #: timing out must not stop the rest of the suite reporting.
        self.timeouts: list[str] = []
        #: One row per clock edge after reset: (dut outputs, model outputs).
        #: Both sides already advance in lockstep, so this is a recording rather
        #: than a second simulation, and it is what lets a check compare
        #: SEQUENCES instead of one sampled point per stimulus vector.
        self._trace: list[tuple[dict, dict]] = []
        #: Per-edge internal signals, when `SPECFLOW_TRACE_INTERNALS` names any.
        #: Empty and untouched otherwise -- see `_INTERNALS`.
        self._internals: list[tuple[dict, dict]] = []
        #: Signals registered per check uid, in the order the renderer emitted
        #: them. The comparison runs at `finish()` over the whole trace.
        self._registered: dict[str, list[str]] = {}
        self._finished = False

    def _clk(self):
        """The clock handle, found by name classification rather than literally.

        Three sites used to look up `getattr(self.dut, "clk")`. `ports.is_clock`
        already knows `clock`, `clk_i`, `aclk`, `sysclk` and the rest, and
        `classify()` uses it -- but the runtime did not, so a design whose clock
        is named `clock` got no cocotb `Clock`, no `reset()` call (it is only
        invoked when a clock is found), and the combinational `Timer` path.
        28 of the ~90 ChipVerilog designs name it `clock` or `Clock`.

        The failure is silent and looks like success: with nothing driving the
        reset either, the DUT sits held in reset, `_bundle` reads that same
        reset off the DUT so the model resets too, and every check compares two
        constants that agree. `tests/test_harness_conformance.py` pins it with a
        tied-off DUT, which is the only thing that tells the two apart.
        """
        for name in self.input_ports:
            if is_clock(name):
                handle = getattr(self.dut, name, None)
                if handle is not None:
                    return handle
        return getattr(self.dut, "clk", None)

    # -- construction ------------------------------------------------------

    @classmethod
    async def start(
        cls,
        dut,
        *,
        tp_uid: str,
        model,
        period_ns: int = 10,
        input_ports: list[str] | None = None,
        pinned: dict[str, int] | None = None,
        idle: dict[str, int] | None = None,
    ) -> "Env":
        results_dir = Path(os.environ.get("SPECFLOW_RESULTS", "results"))
        env = cls(dut, tp_uid, model, results_dir, input_ports, pinned, idle)

        clk = env._clk()
        if clk is not None:
            import cocotb
            from cocotb.clock import Clock

            cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
            await env.reset()
        return env

    async def reset(self, cycles: int = 2,
                    only: list[str] | None = None) -> None:
        """Assert the declared resets, hold, release, then reset the model.

        `only` names a subset, mirroring `{"reset": ["rst"]}` in the step
        schema, and the two sides must agree on what that means or the invariant
        this method exists for is gone: for a SUBSET the port is driven and the
        model is NOT force-reset, because the question being asked is whether
        the design responds to that particular port. `replay` does the same.

        Reset names come from the contract via `tb/ports.py`, not from a local
        probe list. The probe list this replaced knew `rst`/`reset`/`rst_n`/
        `resetn` and therefore found nothing on a design whose reset is called
        `nReset` -- so the DUT ran the entire suite un-reset and the reference
        model's own `reset()` was never called.
        """
        names = [n for n in self.input_ports if is_reset(n)]
        if not names:
            names = [n for n in ("rst", "reset", "rst_n", "resetn", "nReset")
                     if getattr(self.dut, n, None) is not None]
        whole = only is None or set(map(str, only)) >= set(names)
        if only is not None:
            wanted = {str(n) for n in only}
            names = [n for n in names if n in wanted]

        handles = [(n, getattr(self.dut, n, None)) for n in names]
        handles = [(n, h) for n, h in handles if h is not None]
        if not handles:
            return

        # Every input to its idle value BEFORE reset is released, so the DUT and
        # the model start from the same defined state. Without this, functional
        # inputs are never driven at all during reset: the DUT samples X while
        # `_bundle` hands the model `inactive_value` -- a plain 0 -- and the two
        # begin the first stimulus vector already disagreeing. On i2c that is
        # where `dout` picks up the X it never loses, and `dout` alone was 996 of
        # 2016 diverging edges.
        for name in self.input_ports:
            if is_reset(name):
                continue
            handle = getattr(self.dut, name, None)
            if handle is not None:
                self._drive(name, self.idle.get(name, 0))
        for name, _ in handles:
            self._drive(name, 1 - inactive_value(name))
        # Only for a whole-design reset -- see the docstring. A selective reset
        # drives its port and leaves the model to answer for itself, which is
        # the whole point of naming one.
        if whole and hasattr(self.ref, "reset"):
            self.ref.reset()
        # Lockstep through reset too. The DUT takes `cycles + 1` edges here, and
        # a model that took none arrives at the first stimulus vector that many
        # edges behind -- which for a design whose outputs move on specific
        # edges misaligns every comparison that follows.
        for _ in range(cycles):
            await self.tick(1)
            self._advance_model({})
        for name, _ in handles:
            self._drive(name, inactive_value(name))
        await self.tick(1)
        self._advance_model({})

    # -- driving -----------------------------------------------------------

    async def tick(self, n: int = 1) -> None:
        clk = self._clk()
        if clk is None:
            from cocotb.triggers import Timer

            await Timer(1, unit="ns")
            return
        from cocotb.triggers import RisingEdge

        for _ in range(n):
            await RisingEdge(clk)

    async def drive(self, stim: dict) -> None:
        self.step_index += 1
        self._expected = None
        inputs, hold, until, timeout = normalise_step(stim)
        if is_reset_step(stim):
            # `reset()` already sequences the DUT and the model together, which
            # is the invariant that keeps reset out of `_drivable`. Routing the
            # step here rather than driving the port directly is what lets a
            # testpoint exercise reset without the two sides diverging -- and
            # the named subset goes through the same door for the same reason.
            await self.reset(cycles=hold, only=reset_ports(stim))
            return
        self._inputs = inputs
        for name, value in inputs.items():
            port = getattr(self.dut, name, None)
            if port is None:
                # Recorded, not raised. Raising here killed the testpoint before
                # `finish()` could write its record, so a candidate that simply
                # omitted a declared input produced NO verdict rather than a
                # verdict naming the missing port -- and the suite lost the
                # evidence for the very defect it had found. `_resolve` turns
                # this into a failing check with the port named.
                if name not in self.missing_ports:
                    self.missing_ports.append(name)
                continue
            self._drive(name, value)
        await self.settle(inputs, hold=hold, until=until, timeout=timeout)

    def _drive(self, name: str, value) -> None:
        """Write one input, recording rather than raising when it will not take.

        Two things go wrong here and both used to kill the testpoint before
        `finish()` could write its record -- so the suite lost the evidence for
        the very defect it had just found. A value the port cannot hold (2 on a
        1-bit input) and a handle the simulator will not let us write (Verilator
        has optimised the signal into a constant, or it is not really an input)
        are both verdicts about this run, and `_resolve` reports them as failing
        checks that name the port.
        """
        handle = getattr(self.dut, name, None)
        if handle is None:
            if name not in self.missing_ports:
                self.missing_ports.append(name)
            return
        try:
            handle.value = int(value)
        except Exception as exc:  # noqa: BLE001 -- any refusal is the same verdict
            note = f"{name}={value!r} could not be driven ({type(exc).__name__}: {exc})"
            if note not in self.bad_stimulus:
                self.bad_stimulus.append(note)

    async def settle(
        self,
        stim: dict | None = None,
        *,
        hold: int = 1,
        until: dict | None = None,
        timeout: int = 0,
    ) -> None:
        """Hold the vector and advance the DUT and the model TOGETHER.

        One `step()` per clock edge. `RefModel.step` is documented as "advance
        one clock edge and return the outputs", so a model driven at any other
        rate is not the design's oracle -- it is a different machine.

        How LONG a vector is held is the test's business, not a port's. This
        used to be `LATENCY_CYCLES + 1`, which made the contract's guessed
        per-output latency set the pace of every stimulus in the suite. On a
        design whose contract reported 3 the DUT ran at 4x the model's rate
        until both were advanced together; even after that was fixed, the figure
        still silently rescaled the whole suite whenever the contract changed --
        and it changed between two runs of the same spec, 3 then 1.
        """
        latency_free_hold = max(1, int(hold))
        if self._clk() is None:
            from cocotb.triggers import Timer

            await Timer(1, unit="ns")
            if stim is not None:
                self._expected = self._advance_model(stim)
            # Record here too. A combinational design has no edge, so without
            # this its trace stays empty, `transactional([], [])` is trivially
            # equal, and EVERY check on it passes having compared nothing. That
            # is the vacuity the whole design exists to prevent, and it would
            # have been reintroduced by the comparison moving off the sample.
            self._record()
            return

        async def one_edge() -> None:
            await self.tick(1)
            if stim is not None:
                self._expected = self._advance_model(stim)
            await self._settled()
            self._record()

        if until:
            # Run until the design says it is done. `timeout` bounds it so a
            # design that never responds fails as a timeout rather than hanging
            # the suite; 0 means "use the default bound".
            port = str(until.get("port") or "")
            want = until.get("value", 1)
            budget = timeout or DEFAULT_UNTIL_TIMEOUT
            handle = getattr(self.dut, port, None) if port else None
            for _ in range(budget):
                await one_edge()
                if handle is not None and _plain(handle.value) == want:
                    break
            else:
                self.timeouts.append(
                    f"step {self.step_index}: waited {budget} edges for "
                    f"{port}=={want} and it never happened"
                )
            return

        for _ in range(latency_free_hold):
            await one_edge()

    async def _settled(self) -> None:
        """Let this edge's non-blocking updates land before anything samples.

        `RisingEdge` fires in the same delta as the edge, so a read taken
        straight after it returns the PREVIOUS cycle's value. One simulator time
        STEP, not one picosecond: `Timer(1, unit="ps")` raises on any design
        whose timescale is coarser than a picosecond.
        """
        from cocotb.triggers import Timer

        await Timer(1, unit="step")

    def sample(self, signal: str) -> int | None:
        """Read one DUT output, or `None` if the design does not expose it.

        A missing port used to raise `AttributeError` out of `drive()`, which
        killed the testpoint before `finish()` could write its record -- so a
        candidate that simply omitted a declared output produced no verdict at
        all rather than a verdict saying so. That is the same failure the
        per-testpoint record exists to prevent: a crash mid-suite must cost the
        crashing testpoint, never the evidence.

        `None` is not swallowed. It enters the trace as the DUT's value, the
        model's declared value is not `None`, and the comparison fails at the
        first state with `got={'<port>': None}` -- which names the missing port
        instead of a traceback that names cocotb's `handle.py`.
        """
        handle = getattr(self.dut, signal, None)
        if handle is None:
            return None
        return _plain(handle.value)

    def expect(self, stim: dict) -> dict:
        """Expected outputs from the reference model, never from the testcase.

        Dispatch by what the model actually implements, not by re-deriving the
        choice here. `compose.choose_base` already decides `evaluate` vs `step`
        from the contract and the generated model implements exactly that one,
        so a second, differently-worded decision in the runtime can only
        disagree with the first.

        It did. This gated on `LATENCY_CYCLES > 1`, so a sequential model with
        latency 0 or 1 -- which `choose_base` still routes to `step`, because it
        also keys on `clocking.is_sequential` and completion signals -- fell
        through to `evaluate`, which such a model does not define. The base
        class raised `NotImplementedError` and every testpoint in the suite
        crashed before writing a record. On i2c_master_bit_ctrl that was 23 of
        23, and it means specflow's sequential path had never once run; the half
        adder worked only because a combinational model does define `evaluate`.
        """
        if self._expected is not None:
            return self._expected
        # `expect()` without a preceding `drive()` -- the standalone path a few
        # unit tests use. One step, which is the whole answer for a
        # combinational model and the best available one otherwise.
        return self._advance_model(stim)

    def _advance_model(self, stim: dict) -> dict:
        """Advance the reference model exactly one clock edge.

        Split out of `expect` so `settle` can call it once per DUT edge. The
        dispatch choice is unchanged and still made by what the model
        implements, never re-derived here.
        """
        from ..refmodel.base import RefModel

        bundle = self._bundle(stim)
        if type(self.ref).step is not RefModel.step:
            return self.ref.step(bundle)
        return self.ref.evaluate(bundle)

    def _bundle(self, stim: dict) -> dict:
        """The complete declared input set, not just the ports being swept.

        The stimulus drives functional inputs only -- the runtime owns clock and
        reset. But the contract declares all of them, so the reference model is
        entitled to read any of them, and a model that read one it was not given
        raised `KeyError` and killed the testpoint before `finish()` could write
        a record. Fill the gap from the DUT, which is the truth at this instant,
        and fall back to the pinned inactive value when the handle is absent.
        """
        bundle = dict(stim)
        for name in self.input_ports:
            if name in bundle:
                continue
            handle = getattr(self.dut, name, None)
            if handle is None:
                bundle[name] = self.idle.get(name, inactive_value(name))
                continue
            sampled = _plain(handle.value)
            bundle[name] = (
                sampled if isinstance(sampled, int)
                else self.idle.get(name, inactive_value(name))
            )
        return bundle

    # -- verdict -----------------------------------------------------------

    def _record(self) -> None:
        """Append this edge to the trace: both sides' outputs, and its stimulus.

        The stimulus travels with the edge because the divergence index is an
        index into the run-length-encoded STATE sequence, and a repair agent
        cannot act on "state 4 is wrong" without knowing what was being driven
        when state 4 began. Carrying it per edge is what lets `_resolve` hand
        back the vector that produced the divergence rather than whichever
        vector happened to be last.
        """
        ports = list(getattr(self.ref, "OUTPUT_PORTS", []) or [])
        if not ports:
            return
        expected = self._expected or {}
        self._trace.append((
            {p: self.sample(p) for p in ports},
            {p: _plain(expected.get(p)) for p in ports},
            self.step_index,
            # THE COMPLETE DECLARED INPUT SET, not just the ports this step
            # sweeps -- the same correction `_bundle` already makes for the
            # reference model's benefit, applied to what gets recorded.
            #
            # `self._inputs` is the stimulus vector, and the stimulus drives
            # functional inputs only: the runtime owns clock and reset. So a
            # recorded row carried 6 of this design's 9 declared inputs, with
            # `clk`, `nReset` and `rst` absent. `oracles.replay` carries all
            # nine, and a check reading `row["inputs"]["nReset"]` therefore
            # decided against a model and abstained against the DUT -- for a
            # harness reason, wearing "the activation never occurred".
            #
            # Measured on the golden i2c suite before this fix: 59 of 110
            # checks abstained that way, and REQ-0009 said it outright --
            # "normal-operation activation (nReset=1, rst=0) never occurred",
            # of a trace that was in normal operation almost throughout.
            self._bundle(self._inputs),
        ))
        if _INTERNALS:
            self._internals.append((
                {n: self.sample(n) for n in _INTERNALS},
                {n: _plain(getattr(self.ref, n, None)) for n in _INTERNALS},
            ))

    def check(self, chk_uid: str, *signals: str) -> None:
        """Register a check. The comparison happens at `finish()`.

        It used to compare one signal at one instant, once per stimulus vector,
        and the verdict was the conjunction of those samples. That looked at 3
        of 12 cycles on i2c and a median of 4 of 8 outputs, so a faithful oracle
        scored 77 of 168 not because it was aligned but because most divergence
        was never examined.

        Registering here and comparing at the end keeps the emitted call shape
        that G5's AST vacuity gate looks for -- a literal `env.check("CHK-...")`
        -- and keeps `finish()`'s "no check ran" assertion meaningful, while the
        comparison itself becomes a question about the whole run.
        """
        names = [s for s in signals if s]
        self._registered.setdefault(chk_uid, [])
        for name in names:
            if name not in self._registered[chk_uid]:
                self._registered[chk_uid].append(name)

    def _resolve(self) -> None:
        """Run every registered check over the recorded trace.

        An empty trace fails rather than passing. `transactional([], [])` is
        trivially equal, so a testpoint that recorded nothing -- no clock and no
        `_record`, or a model declaring no outputs -- would otherwise report
        every one of its checks as passed having compared nothing. That is the
        exact vacuity `render.py` and G5 exist to make impossible, and moving
        the comparison off the per-vector sample is precisely where it could
        creep back in.
        """
        from ..trace_compare import Verdict, cycle_exact, transactional

        # `SPECFLOW_COMPARE=cycle_exact` is a measuring instrument and nothing
        # else. The gap between the two criteria is how much of a disagreement
        # is phasing rather than behaviour, and that is a question about the
        # harness -- asked in this repo's own experiments against golden RTL by
        # `benchmarks/golden_check.py`. It is never set by the pipeline, and the
        # cycle-exact verdict is never shown to an agent: telling a repair agent
        # its failure is "phasing only" understates the one thing the
        # benchmark's sequential-equivalence scoring cares about, where a single
        # surplus hold cycle is a function failure.
        compare = (
            cycle_exact
            if os.environ.get("SPECFLOW_COMPARE") == "cycle_exact"
            else transactional
        )

        for chk_uid, signals in self._registered.items():
            if not signals:
                continue
            missing = self.missing_ports + [
                s for s in signals
                if getattr(self.dut, s, None) is None and s not in self.missing_ports
            ]
            if self.bad_stimulus:
                self.sb.record(
                    chk_uid, signals,
                    Verdict(False, reason="; ".join(self.bad_stimulus)),
                    ctx=dict(self._inputs), timeouts=self.timeouts,
                )
                continue
            if missing:
                verdict = Verdict(
                    False,
                    reason=f"the design does not expose "
                           f"{', '.join(sorted(missing))}; the contract declares "
                           f"{'it' if len(missing) == 1 else 'them'} as "
                           f"{'a port' if len(missing) == 1 else 'ports'}, so the "
                           f"stimulus could not be applied or the outputs read",
                )
                self.sb.record(chk_uid, signals, verdict,
                               ctx=dict(self._inputs), timeouts=self.timeouts)
                continue
            if not self._trace:
                verdict = Verdict(
                    False,
                    reason="nothing was recorded for this testpoint; the check "
                           "compared no cycles and cannot be said to have passed",
                )
            else:
                dut = [tuple(row[0].get(s) for s in signals) for row in self._trace]
                model = [tuple(row[1].get(s) for s in signals) for row in self._trace]
                verdict = compare(dut, model)
            self.sb.record(
                chk_uid, signals, verdict,
                ctx=self._ctx_at(verdict), timeouts=self.timeouts,
            )

    def _ctx_at(self, verdict) -> dict:
        """The input state in force when the divergent state began.

        A superset of the stimulus vector since `_record` began bundling: the
        reset and clock ports are in here now too, which is strictly more of
        what a repair agent needs to reproduce a divergence and never less.
        """
        at = getattr(verdict, "diverged_at", None)
        if at is None or not self._trace:
            return dict(self._inputs)
        # Run `at` of the DUT's encoding starts after every earlier run's edges.
        # When the DUT ran OUT of states, `at == len(runs)` and the sum lands
        # one past the end -- the last edge is the closest true answer. The
        # cycle-exact instrument reports no durations because its index already
        # IS an edge, so an empty list means "take it literally".
        offset = sum(verdict.dut_durations[:at]) if verdict.dut_durations else at
        edge = min(offset, len(self._trace) - 1)
        _, _, step, inputs = self._trace[edge]
        return {"vector": step, **{k: _plain(v) for k, v in inputs.items()}}

    async def finish(self) -> None:
        """Write this testpoint's record, then assert once.

        Written per testpoint rather than accumulated in memory: cocotb runs
        every test in one simulator process, so a crash mid-suite would lose an
        accumulated set. Writing here means a crash preserves every testpoint
        that already completed -- which is what makes "all failing scenarios at
        once" hold even when the simulation dies, not only when it fails
        cleanly.
        """
        if self._finished:
            return
        self._finished = True
        self._resolve()

        status = "FAIL" if self.sb.failed else ("PASS" if self.sb.invoked else "NOT_EXERCISED")
        record = {
            "tp_uid": self.tp_uid,
            "status": status,
            "checks_invoked": sorted(set(self.sb.invoked)),
            "checks_failed": sorted(set(self.sb.failed)),
            "signals_failed": sorted(
                {
                    name
                    for m in self.sb.mismatches
                    for name in (m.get("signals") or ([m["signal"]] if m.get("signal") else []))
                }
            ),
            "timeouts": list(self.timeouts),
            "bins_hit": sorted(self.cov.hits),
            "mismatches": self.sb.mismatches,
        }
        self.results_dir.mkdir(parents=True, exist_ok=True)
        (self.results_dir / f"{self.tp_uid}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if _INTERNALS:
            (self.results_dir / f"{self.tp_uid}.trace.json").write_text(
                json.dumps({
                    "tp_uid": self.tp_uid,
                    "signals": _INTERNALS,
                    "outputs": list(getattr(self.ref, "OUTPUT_PORTS", []) or []),
                    "edges": [
                        {"edge": i, "step": t[2], "inputs": t[3],
                         "dut": t[0], "model": t[1],
                         "dut_internal": v[0], "model_internal": v[1]}
                        for i, (t, v) in enumerate(zip(self._trace, self._internals))
                    ],
                }, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )

        assert not self.sb.failed, (
            f"{self.tp_uid}: {len(self.sb.failed)} of {len(self.sb.invoked)} checks "
            f"failed: {sorted(set(self.sb.failed))}"
        )
        assert self.sb.invoked, f"{self.tp_uid}: no check ran; this testpoint is vacuous"
