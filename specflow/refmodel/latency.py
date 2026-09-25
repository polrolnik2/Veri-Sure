"""A check that asserts a latency the requirement never stated.

**THE SPECIFICATION SAYS "AFTER", AND THE CHECK READS THE SAME ROW.** "busy is
cleared after a STOP condition is detected"; "sto_condition = sSDA & ~dSDA &
sSCL"; "hold clk_en low while slave_wait is asserted". None of these states a
latency, and a design that registers its response -- the response arriving one
clock after the condition that causes it -- implements every one of them
faithfully. A check that reads the response on the very row its condition
occurs admits only the other, zero-latency reading.

Measured on `full2` against the known-good i2c design, with the pipeline's own
rules: REQ-0035 requires `busy` low on the row `sto_condition` rises (golden
clears it one row later); REQ-0051 requires `clk_en` low on the row
`slave_wait` rises (golden, one row later); REQ-0067/0110 require
`sto_condition` on the row its equation first holds (golden registers it).
Every spec-derived population member computes these on the same row -- 13 of 13
START events in all seven -- so no population instrument can see it.

**SO THE TEST IS MECHANICAL AND DESIGN-FREE.** Take a trace the check PASSES on
(any runnable spec-derived design serves, the way `oracle_liveness` uses one),
make the signals the requirement observes arrive ONE CLOCK LATER -- exactly the
trace a registered implementation of the same design would record -- and replay
the check. If it now fails, it rests on a latency the requirement never stated.

Licensed where the requirement states the timing: `licenses_a_cycle_count`
("immediately", "on the next clock", "within N cycles") and the explicit
same-cycle words below. Reads no known-good design and no verdict about one.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .oracles import RequirementOracle, decide, shift_probe, transactional_view
from .temporal import licenses_a_cycle_count

#: Words that DO state a zero-latency relation, beyond a cycle count.
_SAME_CYCLE = re.compile(
    r"\b(asynchronous(ly)?|combinational(ly)?|same (clock|cycle)|"
    r"without (any )?delay|in the same (clock|cycle)|immediately)\b", re.I)

PREFIX = "latency:"


def licensed(requirement_text: str) -> bool:
    """Does the requirement's own sentence state the response's timing?"""
    text = requirement_text or ""
    return licenses_a_cycle_count(text) or bool(_SAME_CYCLE.search(text))


def lagged(raw_rows: list[dict], names: Sequence[str]) -> list[dict]:
    """`raw_rows` with each named output arriving one clock later.

    RAW rows, one per clock edge -- lagging after the transactional view would
    move a value by one distinct STATE, which is not what a register does.
    """
    out = raw_rows
    for name in names:
        out = shift_probe(out, name, -1)
    return out


def observed_names(oracle: RequirementOracle, observable: Sequence[str]) -> list[str]:
    """The requirement's observables that this check actually reads."""
    src = oracle.source or ""
    return [n for n in dict.fromkeys(observable or ())
            if n and re.search(rf"\b{re.escape(str(n))}\b", src)]


def fragile(oracle: RequirementOracle, raw_rows_by_tp: Mapping[str, list[dict]],
            observable: Sequence[str], requirement_text: str, *,
            testpoints: Sequence[str] | None = None,
            transactional: bool = True, lags: Sequence[int] = (1, 2),
            max_passing: int = 40) -> str:
    """Why this check rests on an unstated latency, or `""` if it does not.

    **EVERY TESTPOINT, NOT THE CHECK'S OWN TWO.** A check is decided on every
    testpoint the stimulus has, so testing it only on its `tp_uids` (median ~2)
    missed most of what it will be judged on: there the triggering event often
    never occurs with a value that exposes a lag. Measured on `full2` against
    golden with its probes bound: tested on its own testpoints the gate flagged
    55 of 440 bodies; tested on every passing testpoint, 194 -- among them every
    `dout`-on-the-edge, `cmd_ack`-inside-the-sequence and `din`-to-`sda_oen`
    check that convicts the known-good design.

    So: the check's own testpoints first, then every other testpoint in sorted
    order, stopping after `max_passing` on which it PASSES as recorded (a
    testpoint it fails or abstains on says nothing about latency). On each, the
    observables are delayed by each of `lags` clocks -- one AND two, because a
    registered design with a registered output stage answers two clocks late
    (`din` -> `sda_oen` on the i2c reference). Never raises.
    """
    if licensed(requirement_text):
        return ""
    names = observed_names(oracle, observable)
    if not names:
        return ""
    view = transactional_view if transactional else (lambda rows: rows)
    order = (list(testpoints) if testpoints is not None else
             list(dict.fromkeys([*oracle.tp_uids, *sorted(raw_rows_by_tp)])))
    passing = 0
    for tp in order:
        raw = raw_rows_by_tp.get(tp)
        if not raw:
            continue
        try:
            if decide(oracle, view(raw)).ok is not True:
                continue
        except Exception:  # noqa: BLE001 -- a check that cannot run is another gate's
            continue
        passing += 1
        if passing > max_passing:
            break
        moved = raw
        for k in range(1, max(lags) + 1):
            moved = lagged(moved, names)
            if k not in lags:
                continue
            try:
                late = decide(oracle, view(moved))
            except Exception:  # noqa: BLE001
                break
            if late.ok is False:
                return (f"{PREFIX} this check passes on {tp} but FAILS when "
                        f"{', '.join(names)} arrive{'s' if len(names) == 1 else ''} "
                        f"{k} clock{'s' if k > 1 else ''} later -- which is "
                        f"exactly what a design that registers "
                        f"{'them' if len(names) > 1 else 'it'} records. The "
                        f"requirement states no latency, so that design is a "
                        f"faithful implementation and the check must not convict "
                        f"it. Do not read the response on the row of the "
                        f"condition that causes it, or on the next one: open a "
                        f"window on the condition and require the response "
                        f"within it (`eventually`, closing at the next "
                        f"occurrence of the condition or the end of the "
                        f"transaction). Late reading: {late.detail}")
    return ""


def refuser(witness: str, contract: dict, stimulus_by_tp: Mapping[str, list],
            normalized_by_uid: Mapping[str, dict], text_by_uid: Mapping[str, str],
            *, base: str, transactional: bool = True):
    """`why(uid, oracle) -> str`: `fragile` against one substrate design.

    The substrate is replayed once per testpoint and cached, because the same
    trace serves every check that names it. `stimulus_by_tp` is read at CALL
    time, so testpoints the stage stages after this was built are replayed when
    first asked for. `None` when there is no substrate to replay.
    """
    if not (witness or "").strip():
        return None
    from .oracles import replay

    cache: dict[str, list] = {}

    class _Rows(Mapping):
        """Every testpoint of the stimulus, the substrate replayed on first read."""

        def __getitem__(self, tp):
            if tp not in cache:
                steps = stimulus_by_tp.get(tp)
                try:
                    cache[tp] = (list(replay(witness, contract, steps, base=base).rows)
                                 if steps else [])
                except Exception:  # noqa: BLE001
                    cache[tp] = []
            return cache[tp]

        def __iter__(self):
            return iter(list(stimulus_by_tp))

        def __len__(self):
            return len(stimulus_by_tp)

    rows = _Rows()

    def why(uid: str, oracle: RequirementOracle) -> str:
        shape = normalized_by_uid.get(uid) or {}
        return fragile(oracle, rows, shape.get("observable") or [],
                       str(text_by_uid.get(uid) or ""), transactional=transactional)

    return why
