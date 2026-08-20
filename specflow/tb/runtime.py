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

from ..ports import inactive_value, is_clock, is_reset



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
    ) -> "Env":
        results_dir = Path(os.environ.get("SPECFLOW_RESULTS", "results"))
        env = cls(dut, tp_uid, model, results_dir, input_ports, pinned)

        clk = env._clk()
        if clk is not None:
            import cocotb
            from cocotb.clock import Clock

            cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
            await env.reset()
        return env

    async def reset(self, cycles: int = 2) -> None:
        """Assert every declared reset, hold, release, then reset the model.

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

        handles = [(n, getattr(self.dut, n, None)) for n in names]
        handles = [(n, h) for n, h in handles if h is not None]
        if not handles:
            return

        for name, handle in handles:
            handle.value = 1 - inactive_value(name)
        if hasattr(self.ref, "reset"):
            self.ref.reset()
        # Lockstep through reset too. The DUT takes `cycles + 1` edges here, and
        # a model that took none arrives at the first stimulus vector that many
        # edges behind -- which for a design whose outputs move on specific
        # edges misaligns every comparison that follows.
        for _ in range(cycles):
            await self.tick(1)
            self._advance_model({})
        for name, handle in handles:
            handle.value = inactive_value(name)
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
        for name, value in stim.items():
            port = getattr(self.dut, name, None)
            if port is None:
                raise AttributeError(f"{self.tp_uid}: DUT has no port {name!r}")
            port.value = int(value)
        await self.settle(stim)

    async def settle(self, stim: dict | None = None) -> None:
        """Hold the vector and advance the DUT and the model TOGETHER.

        One `step()` per clock edge. `RefModel.step` is documented as "advance
        one clock edge and return the outputs", so a model driven any other
        rate is not the design's oracle -- it is a different machine.

        This used to tick the DUT `LATENCY_CYCLES + 1` edges and let `expect()`
        take a SINGLE step, which on a design whose contract reports
        `latency_cycles: 3` ran the DUT at 4x the model's rate. Every
        multi-cycle sequence then diverged structurally, and no RTL could
        satisfy the suite: driven through it, the *golden* i2c_master_bit_ctrl
        failed 120 of 168 testpoints (373 mismatches) -- worse than the
        LLM-written candidate's 91/203. A known-correct design scoring below a
        generated one is the signature of a broken oracle, and the skew was it.

        The trap is that `latency_cycles: 0` gives `max(1, 1) = 1` and the bug
        vanishes, so it is invisible on combinational designs and on anything
        whose contract reports no latency. It survived every earlier test for
        that reason.

        `LATENCY_CYCLES` keeps its documented meaning -- how long an output
        takes to answer a stimulus -- and is used here only to decide how long
        to HOLD each vector. It no longer paces the model, because with the two
        advancing together there is nothing left to align.
        """
        latency = int(getattr(self.ref, "LATENCY_CYCLES", 0) or 0)
        if self._clk() is None:
            from cocotb.triggers import Timer

            await Timer(1, unit="ns")
            if stim is not None:
                self._expected = self._advance_model(stim)
            return
        for _ in range(max(1, latency + 1)):
            await self.tick(1)
            if stim is not None:
                self._expected = self._advance_model(stim)
        # Let this edge's non-blocking updates land before anything samples the
        # DUT. `RisingEdge` fires in the same delta as the edge, so a read taken
        # straight after it returns the PREVIOUS cycle's value -- the DUT would
        # then be compared one edge behind the model.
        from cocotb.triggers import Timer

        await Timer(1, unit="ps")

    def sample(self, signal: str) -> int:
        return _plain(getattr(self.dut, signal).value)

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
                bundle[name] = self.pinned.get(name, inactive_value(name))
                continue
            sampled = _plain(handle.value)
            bundle[name] = (
                sampled if isinstance(sampled, int)
                else self.pinned.get(name, inactive_value(name))
            )
        return bundle

    # -- verdict -----------------------------------------------------------

    def check(self, chk_uid: str, signal: str, expected_map: dict, ctx: dict) -> bool:
        return self.sb.check(
            chk_uid, self.sample(signal), expected_map.get(signal), ctx,
            signal=signal, step=self.step_index,
        )

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

        status = "FAIL" if self.sb.failed else ("PASS" if self.sb.invoked else "NOT_EXERCISED")
        record = {
            "tp_uid": self.tp_uid,
            "status": status,
            "checks_invoked": sorted(set(self.sb.invoked)),
            "checks_failed": sorted(set(self.sb.failed)),
            "signals_failed": sorted(
                {m["signal"] for m in self.sb.mismatches if m.get("signal")}
            ),
            "bins_hit": sorted(self.cov.hits),
            "mismatches": self.sb.mismatches,
        }
        self.results_dir.mkdir(parents=True, exist_ok=True)
        (self.results_dir / f"{self.tp_uid}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        assert not self.sb.failed, (
            f"{self.tp_uid}: {len(self.sb.failed)} of {len(self.sb.invoked)} checks "
            f"failed: {sorted(set(self.sb.failed))}"
        )
        assert self.sb.invoked, f"{self.tp_uid}: no check ran; this testpoint is vacuous"
