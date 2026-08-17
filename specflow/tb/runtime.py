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


@dataclass
class Scoreboard:
    """Accumulates check outcomes. Never raises."""

    invoked: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)

    def check(self, chk_uid: str, got: Any, expected: Any, ctx: dict | None = None) -> bool:
        self.invoked.append(chk_uid)
        ok = got == expected
        if not ok:
            self.failed.append(chk_uid)
            # Every mismatch carries its own values and stimulus. The recorded
            # failure of the old flow was 210 MISMATCH lines carrying 2 actual
            # values, which told the repair agent nothing it could act on.
            self.mismatches.append(
                {
                    "check": chk_uid,
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

    def __init__(self, dut, tp_uid: str, model, results_dir: Path):
        self.dut = dut
        self.tp_uid = tp_uid
        self.ref = model
        self.results_dir = Path(results_dir)
        self.sb = Scoreboard()
        self.cov = CoverageRecorder()
        self._finished = False

    # -- construction ------------------------------------------------------

    @classmethod
    async def start(cls, dut, *, tp_uid: str, model, period_ns: int = 10) -> "Env":
        results_dir = Path(os.environ.get("SPECFLOW_RESULTS", "results"))
        env = cls(dut, tp_uid, model, results_dir)

        clk = getattr(dut, "clk", None)
        if clk is not None:
            import cocotb
            from cocotb.clock import Clock

            cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
            await env.reset()
        return env

    async def reset(self, cycles: int = 2) -> None:
        rst = None
        for name in ("rst", "reset", "rst_n", "resetn"):
            rst = getattr(self.dut, name, None)
            if rst is not None:
                break
        if rst is None:
            return

        active_low = "n" in rst._name.lower().split("_")[-1] if hasattr(rst, "_name") else False
        rst.value = 0 if active_low else 1
        await self.tick(cycles)
        rst.value = 1 if active_low else 0
        await self.tick(1)
        if hasattr(self.ref, "reset"):
            self.ref.reset()

    # -- driving -----------------------------------------------------------

    async def tick(self, n: int = 1) -> None:
        clk = getattr(self.dut, "clk", None)
        if clk is None:
            from cocotb.triggers import Timer

            await Timer(1, unit="ns")
            return
        from cocotb.triggers import RisingEdge

        for _ in range(n):
            await RisingEdge(clk)

    async def drive(self, stim: dict) -> None:
        for name, value in stim.items():
            port = getattr(self.dut, name, None)
            if port is None:
                raise AttributeError(f"{self.tp_uid}: DUT has no port {name!r}")
            port.value = int(value)
        await self.settle()

    async def settle(self) -> None:
        """Let the DUT respond: one delta for combinational, LATENCY+1 edges
        for a registered output."""
        latency = int(getattr(self.ref, "LATENCY_CYCLES", 0) or 0)
        if getattr(self.dut, "clk", None) is None:
            from cocotb.triggers import Timer

            await Timer(1, unit="ns")
        else:
            await self.tick(max(1, latency + 1))

    def sample(self, signal: str) -> int:
        return _plain(getattr(self.dut, signal).value)

    def expect(self, stim: dict) -> dict:
        """Expected outputs from the reference model, never from the testcase."""
        fn = getattr(self.ref, "step", None) if hasattr(self.ref, "step") else None
        if int(getattr(self.ref, "LATENCY_CYCLES", 0) or 0) > 1 and callable(fn):
            return fn(dict(stim))
        return self.ref.evaluate(dict(stim))

    # -- verdict -----------------------------------------------------------

    def check(self, chk_uid: str, signal: str, expected_map: dict, ctx: dict) -> bool:
        return self.sb.check(chk_uid, self.sample(signal), expected_map.get(signal), ctx)

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
