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
    #: The row immediately before the activation, for `$past`. One row, not a
    #: history: `$past(sig, 3)` is a cycle count and Phases 3-6 severed those.
    #: `$past(sig)` -- "what it was before this happened" -- is not.
    prev: dict | None = None

    @property
    def edge(self) -> int | None:
        return self.start.get("edge")

    @property
    def body(self) -> list[dict]:
        """The rows AFTER the activation row -- the `|=>` half of the window.

        `rows` opens AT the activation, so a consequent that happens to be true
        at that instant satisfies `eventually` over `rows`. That is the exact
        vacuity this module was written to remove: six of a2-i2c's fourteen
        vacuous checks evaluated the expectation on the SAME row as the
        activation. Reading `body` instead is `|=>`.
        """
        return self.rows[1:]

    def past(self, port: str):
        """`$past(port)` at the activation -- its value on the row before.

        `None` when the activation is the first row of the trace, which is
        `$past`'s own semantics: there is no previous sample to name.
        """
        return _val(self.prev, port) if self.prev is not None else None

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
          max_windows: int = 64, overlap: bool = False) -> list[Window]:
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
        # A RISING activation, in both modes: a condition true for forty
        # consecutive rows opens one window, not forty. What `overlap` changes
        # is where the scan resumes, not what counts as a start.
        rising = activation(trace[i]) and (i == 0 or not activation(trace[i - 1]))
        if not rising:
            i += 1
            continue
        w = Window(start=trace[i], rows=[trace[i]], closed=False,
                   prev=trace[i - 1] if i else None)
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
        i = i + 1 if overlap else j + 1
    return out


def eventually(w: Window, holds: Pred, *, strong: bool = False,
               after_activation: bool = False,
               what: str = "the expected response") -> Verdict:
    """`holds` must be true at some row before the window closes.

    `s_eventually` VERSUS `eventually`, AND THE DEFAULT IS THE WEAK ONE.
    A window that ran off the end of the trace returns UNKNOWN, not False:
    nothing was seen to be wrong, we simply stopped looking. That is the
    distinction `verdict.truncated()` reconstructs from prose today.

    But a requirement that says the response MUST come is a strong liveness
    claim, and under weak semantics it can never be violated by this instrument
    -- only left undecided. Measured on a2-i2c: 11 of 105 requirements are
    phrased that way, and 5 of 14 abstaining checks abstained for exactly this
    reason ("had not occurred by the end of trace"). `strong=True` is
    `s_eventually`: running out of trace is a failure, because the obligation
    was never discharged.

    `after_activation` is `|=>` against `|->`. The window OPENS at the
    activation row, so a consequent that is already true there satisfies the
    default -- which is the vacuity this module exists to remove. Set it when
    the requirement says the effect FOLLOWS the trigger, which is most of them.
    """
    rows = w.body if after_activation else w.rows
    for row in rows:
        if holds(row):
            return True, row.get("edge"), f"{what} occurred"
    if not w.closed:
        if strong:
            return False, w.edge, (
                f"{what} never occurred, and the window opening at edge "
                f"{w.edge} ran to the end of trace -- the obligation was never "
                f"discharged")
        return None, w.edge, (
            f"{what} had not occurred by the end of trace, and the window "
            f"opened at edge {w.edge} never closed")
    return False, w.edge, (
        f"{what} never occurred in the window opening at edge {w.edge}")


def throughout(w: Window, holds: Pred, *, after_activation: bool = False,
               what: str = "the invariant") -> Verdict:
    """`holds` must be true at EVERY row of the window.

    Fails on the first row that breaks it, and names that row -- an invariant
    is refuted by one counterexample, and the first is the one that explains
    the rest.

    `after_activation` excludes the activation row, for a requirement whose
    invariant begins once the trigger has happened rather than at it.
    """
    for row in (w.body if after_activation else w.rows):
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


def never(w: Window, holds: Pred, *, what: str = "the forbidden condition"
          ) -> Verdict:
    """`holds` must be true at NO row of the window -- SVA's `not`.

    `throughout(w, lambda r: not p(r))` says the same thing and reads as its
    own double negative. A requirement phrased "shall never" deserves an
    operator spelled the way the requirement is, so the transcription stays
    mechanical and the failure message says "occurred" rather than "the
    invariant broke".
    """
    for row in w.rows:
        if holds(row):
            return False, row.get("edge"), (
                f"{what} occurred at edge {row.get('edge')}, in the window "
                f"opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} was not seen, but the window opening at edge {w.edge} ran "
            f"to the end of trace without closing")
    return True, w.edge, f"{what} never occurred"


def nexttime(w: Window, holds: Pred, *, what: str = "the expected response"
             ) -> Verdict:
    """`holds` at the row immediately after the activation -- SVA `##1`.

    ORDERING, NOT A CYCLE COUNT, and the difference is the whole reason this
    one is admissible while `##[2:5]` is not. A row is a STATE: consecutive
    edges with identical inputs and outputs collapse into one. So "the next
    row" means "the next time anything changed", which is what "then" means in
    a specification -- not "one clock later", which the specification does not
    state and Phases 3-6 stopped this pipeline from asserting.
    """
    body = w.body
    if not body:
        return None, w.edge, (
            f"nothing follows the activation at edge {w.edge}; the trace ends "
            f"there, so {what} could not be observed either way")
    row = body[0]
    if holds(row):
        return True, row.get("edge"), f"{what} occurred at the next state"
    return False, row.get("edge"), (
        f"{what} did not hold at the state after edge {w.edge}")


def sequence(w: Window, *steps: Pred, strong: bool = False,
             what: str = "the sequence") -> Verdict:
    """The steps must occur IN ORDER within the window -- SVA `a ##[1:$] b`.

    Each step matches at a row strictly after the previous step's, so this is
    the count-free form: `##[1:$]` between every pair, never `##[2:5]`. What it
    adds over a conjunction of `eventually` calls is exactly the ordering, and
    that is the whole point -- three `eventually`s pass a design that does the
    three things backwards.

    Only 5 of a2-i2c's 105 requirements name an ordered multi-step sequence,
    because bit-level i2c is deliberately low-level. A byte-level or
    protocol-level design is dominated by them, which is why this is here
    before it is needed rather than after.

    Names the step that stalled, because "the sequence did not complete" sends
    a reader to re-read the whole check.
    """
    if not steps:
        return None, w.edge, "no steps given, so there is nothing to decide"
    at = 0
    for n, step in enumerate(steps):
        while at < len(w.rows) and not step(w.rows[at]):
            at += 1
        if at >= len(w.rows):
            if not w.closed and not strong:
                return None, w.edge, (
                    f"{what} reached step {n + 1} of {len(steps)} and the "
                    f"window opening at edge {w.edge} ran to the end of trace")
            return False, w.edge, (
                f"{what} stalled at step {n + 1} of {len(steps)}, in the "
                f"window opening at edge {w.edge}")
        at += 1
    return True, w.edge, f"{what} completed all {len(steps)} steps in order"


def until(w: Window, holds: Pred, release: Pred, *, strong: bool = False,
          what: str = "the condition") -> Verdict:
    """`holds` at every row until `release` occurs -- SVA `until` / `s_until`.

    Distinct from `after(..., until=)`, which DEFINES the window. This asserts
    something about the rows inside one: "SCL stays low until the divider
    ticks" is `until`, where "while SCL is low" is the window.

    Weak, like SVA's: if `release` never occurs, holding throughout is enough.
    `strong=True` is `s_until` and additionally requires the release to happen
    -- reach the end without it and the obligation was never discharged.
    """
    for row in w.rows:
        if release(row):
            return True, row.get("edge"), (
                f"{what} held until the release at edge {row.get('edge')}")
        if not holds(row):
            return False, row.get("edge"), (
                f"{what} broke at edge {row.get('edge')}, before any release, "
                f"in the window opening at edge {w.edge}")
    if strong:
        return False, w.edge, (
            f"{what} held, but the release never occurred in the window "
            f"opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} held for every row seen, but the window opening at edge "
            f"{w.edge} ran to the end of trace without a release")
    return True, w.edge, f"{what} held and was never released"


def first_match(windows: list[Window]) -> list[Window]:
    """Only the first window -- SVA `first_match`.

    For a requirement about the FIRST time something happens ("the first
    filtered SCL rising edge after reset samples dout"), where folding every
    later occurrence in with `worst` would convict the design for behaviour the
    requirement says nothing about.

    A list rather than one window so it drops into the same comprehension the
    other operators are used from, and so an empty trace stays empty rather
    than becoming `None` for a caller to special-case.
    """
    return windows[:1]


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
