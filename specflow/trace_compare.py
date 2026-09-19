"""Compare a DUT against the reference model by CONTENT, not by cycle count.

The testbench used to require the DUT and the model to agree at every sampled
point, cycle for cycle. That is only worth its cost if the cycle reference is
correct, and ours is a guess: `contract.timing.cmd_ack.latency_cycles` was 3 in
one run of `i2c_master_bit_ctrl` and 1 in the next, while the golden design takes
5 `clk_en` phases. The specification cannot settle it either -- it describes
START as three transitions, golden implements five, and two of those five are
invisible (`start_a`/`start_b` are no-ops from reset and `start_d` is
byte-identical to `start_c`, a pure hold). The phase count appears nowhere in
15,715 characters, because it is an arbitrary-but-fixed choice of that core.

So cycle-exactness was being enforced against a fiction: all of the cost --
rejecting correct RTL, which the repair loop was observed doing -- and none of
the benefit, since it still did not match golden.

Measured, same oracle, two DUTs, `dout` excluded:

    DUT                     cycle-exact   transactional
    golden (correct)          48 / 168      82 / 168
    our generated (wrong)     33 / 168      42 / 168
    separation                      15            40

Ignoring durations separates good RTL from bad ~3x better, because phase noise
from a guessed latency was swamping the real behavioural signal.

**What is compared.** The ordered sequence of distinct observable output states.
A state is the full tuple of declared outputs, so any output changing starts a
new one. A skipped state, a spurious state, or a wrong value all fail; only how
long each state is held is ignored.

**What is NOT ignored.** Durations are returned, never silently swallowed. A
requirement like "`cmd_ack` is asserted for exactly one `clk` cycle" is a
duration claim, and a design that pulses for two cycles has the same state
sequence and is still wrong. Run-length encoding must not absorb that class; it
is reported so it can be checked where the specification actually states it.

Cycle-exact comparison remains available as `cycle_exact` and is used only as an
experiment instrument against golden RTL. It is not an accept criterion and its
verdict never reaches an agent: telling a repair agent its failure is
"phasing only" understates the one thing the benchmark's sequential-equivalence
scoring cares about, where a single surplus hold cycle is `function_fail`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

State = tuple[Any, ...]


def compress(seq: Sequence[State]) -> tuple[list[State], list[int]]:
    """Run-length encode, keeping the durations rather than discarding them."""
    states: list[State] = []
    durations: list[int] = []
    for value in seq:
        if states and states[-1] == value:
            durations[-1] += 1
        else:
            states.append(value)
            durations.append(1)
    return states, durations


def first_divergence(a: Sequence[Any], b: Sequence[Any]) -> int | None:
    """Index of the first differing element, or of the truncation point.

    `None` when the two are equal. A shorter sequence diverges at its own end:
    a design that stopped early has not agreed, it has run out.
    """
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


@dataclass(frozen=True)
class Verdict:
    """The outcome of one comparison, with enough to act on it."""

    ok: bool
    #: Index into the run-length-encoded state sequence, not a cycle number.
    #: Still a monotone "later is better" integer, which is what
    #: `integration.trace_summary`'s `fail_step` and the repair loop's rollback
    #: guard need in order to keep working.
    diverged_at: int | None = None
    expected: State | None = None
    got: State | None = None
    #: Per-state hold lengths for both sides, positionally aligned up to the
    #: divergence. Present so a duration obligation can be checked on top; this
    #: comparison does not itself judge them.
    dut_durations: list[int] = field(default_factory=list)
    model_durations: list[int] = field(default_factory=list)
    reason: str = ""


def transactional(dut: Sequence[State], model: Sequence[State]) -> Verdict:
    """Do the DUT and the model produce the same sequence of output states?"""
    ds, dd = compress(dut)
    ms, md = compress(model)
    at = first_divergence(ds, ms)
    if at is None:
        return Verdict(True, dut_durations=dd, model_durations=md)
    exp = ms[at] if at < len(ms) else None
    got = ds[at] if at < len(ds) else None
    if got is None:
        reason = (
            f"the design stopped after {len(ds)} output state(s); the model "
            f"expected {len(ms)}"
        )
    elif exp is None:
        reason = (
            f"the design produced {len(ds)} output state(s); the model expected "
            f"only {len(ms)}"
        )
    else:
        reason = f"output state {at} is {got!r}; the model expects {exp!r}"
    return Verdict(False, at, exp, got, dd, md, reason)


def cycle_exact(dut: Sequence[State], model: Sequence[State]) -> Verdict:
    """Every cycle must match. An experiment instrument, never a gate.

    Kept because the gap between this and `transactional` is the measurement
    that says how much of a disagreement is phasing rather than behaviour -- and
    that is a question about the harness, asked in this repo's own test loop
    against golden RTL, not a signal to hand an agent.
    """
    at = first_divergence(list(dut), list(model))
    if at is None:
        return Verdict(True)
    exp = model[at] if at < len(model) else None
    got = dut[at] if at < len(dut) else None
    return Verdict(False, at, exp, got,
                   reason=f"cycle {at}: design {got!r}, model {exp!r}")
