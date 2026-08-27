"""Temporal operators for requirement oracles.

An oracle decides a requirement over a trace, and almost every hardware
requirement is temporal: *when* A holds, *then* B must follow -- eventually,
or throughout, or exactly once. Python has no vocabulary for that, so every
oracle re-derives it as hand-rolled index arithmetic, and the shape that
arithmetic makes easiest is the one that is usually wrong.

Measured on a2-i2c. Fourteen oracles were convicted vacuous, and six of them --
REQ-0051, 0053, 0055, 0057, 0092, 0094 -- evaluate the expectation on the SAME
trace row as the activation. REQ-0092 is the clearest: its activation is
`cmd == 8 and ena == 1`, the command-issue window, and it reads `sda_oen`
there. An i2c bit controller drives SDA during transmission, tens of edges
after `cmd` has deasserted. The check is not weak, it is empty -- it reads a
port at edges where nothing was ever going to be wrong, which is why it passed
all five designs built to violate it.

Nothing in those oracles is badly written. There is no early return, no
any-match standing in for all-match; an AST screen over all fourteen found no
such pattern. Each half is a faithful transcription of the normalized form.
The fault is the joint assumption that the two halves hold at one instant.

WINDOWS CLOSE ON A CONDITION, NEVER A CYCLE COUNT. Phases 3-6 severed pacing
from latency and stopped `latency_cycles` gating because the specification does
not pin cycle counts, and a check that asserts one either fails correct designs
or asserts nothing. `until` mirrors the stimulus schema's own idiom, which
exists for the same reason: "drive this, then wait for that event" is
expressible where "wait 12 edges" is a guess.

AND THE TRUNCATION DISTINCTION COMES BACK STRUCTURED. `verdict.truncated()`
tells "failed because it saw a defect" from "failed because the trace ran out"
-- VIOLATES against NOT_EXERCISED -- by string-matching the oracle's own prose
against seven phrases ("end of trace", "never asserted", ...). An author who
words it differently is scored as having found a real bug. A window that closes
by running out of trace returns UNKNOWN here, once, and says so in wording
`truncated()` already recognises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

#: A predicate over one trace row. A row is a STATE, not a clock edge:
#: consecutive edges with identical inputs AND outputs collapse into one entry
#: carrying `held`, the number of edges it lasted. `edge` is its first edge and
#: is for pointing at a failure, not for computing with.
Pred = Callable[[dict], bool]

#: What a check reports. `None` is not a third kind of failure: it means the
#: trace could not answer, and every gate in this pipeline keeps that separate
#: from a verdict it has earned.
Verdict = tuple[bool | None, int | None, str]


def _val(row: dict, port: str):
    outs = row.get("outputs") or {}
    return outs[port] if port in outs else (row.get("inputs") or {}).get(port)


@dataclass
class Window:
    """One activation and the rows it governs.

    `rows` runs from the activation row up to and including the row that closed
    the window. `closed` is False when the trace ended first, which is what
    makes "we never saw the end of this" reportable rather than silently a
    failure.
    """

    start: dict
    rows: list[dict] = field(default_factory=list)
    closed: bool = True

    @property
    def edge(self) -> int | None:
        return self.start.get("edge")

    def value(self, port: str):
        """The value of `port` at the activation -- for expectations written
        against what the inputs were WHEN the requirement applied, which is the
        commonest form and the easiest to get wrong by re-reading it later."""
        return _val(self.start, port)


#: The transitions an activation may open on. `change` is either direction, for
#: "whenever X moves" -- narrower than it sounds, since a row exists only where
#: something moved.
EDGES = ("rise", "fall", "change")


def edges(trace: list[dict], port: str, direction: str = "change") -> set[int]:
    """The `edge` numbers of rows where `port` took that transition.

    A LEVEL IS NOT AN EDGE, and the schema could only say level. Measured on
    a2-i2c: 28 of 105 requirements name an edge or a transition in their own
    text, and their normalized activations came back as `{scl_i: 0}` -- the
    author knew it was an edge and had nowhere to write it. REQ-0038's
    requirement text says "a falling edge observed on the filtered SCL", its
    activation text says "a filtered SCL falling edge occurs", and its schema
    said `scl_i == 0`.

    `after` will not save you here, and that is the subtle part. It opens on a
    RISING activation, so a lone `{scl_i: 0}` does give falling-edge-of-scl_i
    windows. But the moment the condition is MIXED -- "scl_i falls WHILE
    scl_oen is released" -- `after` opens on the edge of the CONJUNCTION, which
    fires when `scl_oen` rises over an already-low `scl_i`. That is a different
    event, and it is the one three checks reported as never occurring.

    So the edge is computed here, over the port alone, and combined with the
    level conditions afterwards:

        fell = edges(trace, "scl_i", "fall")
        after(trace, lambda r: r["edge"] in fell and _val(r, "scl_oen") == 1)

    Returns `edge` numbers rather than rows because `edge` is the one field a
    row can be identified by; identity comparison on dicts is not stable across
    a re-read of the trace.

    The FIRST row is never an edge: a transition needs a previous sample, which
    is `$rose`/`$fell` semantics and not a limitation to work around. A port
    that starts at its target value has not moved to it.

    ON A MULTI-BIT PORT `rise`/`fall` MEAN INCREASED/DECREASED, and SVA's
    `$rose`/`$fell` are defined on the LSB. Those coincide exactly on a 1-bit
    port, which is every port these requirements name an edge of; on a wider
    one the two readings differ and `change` is what is usually meant.
    Documented rather than rejected here, and warned about at normalisation
    where the port width is known.
    """
    if direction not in EDGES:
        raise ValueError(f"direction must be one of {EDGES}, got {direction!r}")
    out: set[int] = set()
    prev = None
    for row in trace:
        now = _val(row, port)
        if prev is not None and now != prev:
            if (direction == "change"
                    or (direction == "rise" and now > prev)
                    or (direction == "fall" and now < prev)):
                out.add(int(row.get("edge", -1)))
        prev = now
    out.discard(-1)
    return out


def after(trace: list[dict], activation: Pred, *, until: Pred | None = None,
          max_windows: int = 64) -> list[Window]:
    """Every window the requirement applies over.

    A window opens on a RISING activation -- the first row where `activation`
    holds and the row before it did not -- so a condition true for forty
    consecutive edges is one window, not forty. It closes on the first row
    satisfying `until`, or on the last row where `activation` still holds when
    no `until` is given.
    """
    out: list[Window] = []
    i, n = 0, len(trace)
    while i < n and len(out) < max_windows:
        if not activation(trace[i]):
            i += 1
            continue
        w = Window(start=trace[i], rows=[trace[i]], closed=False)
        j = i + 1
        while j < n:
            w.rows.append(trace[j])
            if until is not None:
                if until(trace[j]):
                    w.closed = True
                    break
            elif not activation(trace[j]):
                w.closed = True
                break
            j += 1
        out.append(w)
        i = j + 1
    return out


def eventually(w: Window, holds: Pred, *, what: str = "the expected response"
               ) -> Verdict:
    """`holds` must be true at some row before the window closes.

    A window that ran off the end of the trace returns UNKNOWN, not False:
    nothing was seen to be wrong, we simply stopped looking. That is the
    distinction `verdict.truncated()` reconstructs from prose today.
    """
    for row in w.rows:
        if holds(row):
            return True, row.get("edge"), f"{what} occurred"
    if not w.closed:
        return None, w.edge, (
            f"{what} had not occurred by the end of trace, and the window "
            f"opened at edge {w.edge} never closed")
    return False, w.edge, (
        f"{what} never occurred in the window opening at edge {w.edge}")


def throughout(w: Window, holds: Pred, *, what: str = "the invariant"
               ) -> Verdict:
    """`holds` must be true at EVERY row of the window.

    Fails on the first row that breaks it, and names that row -- an invariant
    is refuted by one counterexample, and the first is the one that explains
    the rest.
    """
    for row in w.rows:
        if not holds(row):
            return False, row.get("edge"), (
                f"{what} broke at edge {row.get('edge')}, in the window opening "
                f"at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} held for every row seen, but the window opening at edge "
            f"{w.edge} ran to the end of trace without closing")
    return True, w.edge, f"{what} held throughout"


def stable(w: Window, port: str) -> Verdict:
    """`port` must not change anywhere in the window.

    The "held steady" shape, which on i2c is most of the `slave_wait` cluster:
    while the bus is stretched, `scl_oen` must not take its next phase-driven
    transition. Distinct from `throughout` because the value it must hold is
    whatever it happened to be, not one the requirement names.
    """
    if not w.rows:
        return None, w.edge, f"{port} had no rows to hold over"
    first = _val(w.rows[0], port)
    for row in w.rows[1:]:
        if _val(row, port) != first:
            return False, row.get("edge"), (
                f"{port} changed from {first} to {_val(row, port)} at edge "
                f"{row.get('edge')}, in the window opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{port} was steady for every row seen, but the window opening at "
            f"edge {w.edge} ran to the end of trace without closing")
    return True, w.edge, f"{port} stayed at {first} throughout"


def pulse(w: Window, port: str, *, active: int = 1, width: int = 1) -> Verdict:
    """`port` must go active for exactly `width` consecutive rows, once.

    i2c's `cmd_ack` is this and nothing else -- "asserts for one clk cycle to
    acknowledge completion" appears verbatim in several requirements. Written
    by hand it needs a rising-edge scan, a run-length count and a second-pulse
    check, and getting any of the three wrong produces a check that passes
    everything.
    """
    # WIDTH IS IN EDGES, AND ROWS ARE NOT EDGES. The trace an oracle sees is
    # state-compressed: consecutive edges with identical inputs AND outputs are
    # one entry carrying `held`. A one-edge pulse is therefore ONE row with
    # `held == 1`, and counting rows would call a 40-edge assertion a
    # single-cycle pulse. Summing `held` is the only reading that matches what
    # the requirement means by "for one clk cycle".
    runs: list[tuple[int, int]] = []
    run = 0
    for row in w.rows:
        if _val(row, port) == active:
            run += int(row.get("held", 1) or 1)
        elif run:
            runs.append((run, row.get("edge")))
            run = 0
    if run:
        runs.append((run, w.rows[-1].get("edge")))
    if not runs:
        if not w.closed:
            return None, w.edge, (
                f"{port} had not pulsed by the end of trace, and the window "
                f"opening at edge {w.edge} never closed")
        return False, w.edge, (
            f"{port} never went to {active} in the window opening at edge "
            f"{w.edge}")
    if len(runs) > 1:
        return False, runs[1][1], (
            f"{port} pulsed {len(runs)} times in one window opening at edge "
            f"{w.edge}; exactly one was required")
    got, at = runs[0]
    if got != width:
        return False, at, (
            f"{port} was held at {active} for {got} edge(s), not {width}, in the "
            f"window opening at edge {w.edge}")
    return True, at, f"{port} pulsed once for {width} edge(s)"


def worst(verdicts: list[Verdict]) -> Verdict:
    """Fold many window verdicts into one, failure first.

    A requirement holding on nine windows and breaking on the tenth is broken,
    and an UNKNOWN outranks a pass for the same reason `_worst` gives one level
    up: a grown evidence set only ever moves a verdict toward worse, so nothing
    can be laundered by adding more of it.
    """
    if not verdicts:
        return None, None, "the activation never occurred"
    for ok, edge, detail in verdicts:
        if ok is False:
            return False, edge, detail
    for ok, edge, detail in verdicts:
        if ok is None:
            return None, edge, detail
    return verdicts[0]
