"""Can this oracle fail at all? Asked of the trace, not of a mutant.

[M] asks whether an oracle would notice a different MODEL, and needs the
mutation operator to produce one it can see: `MIN_IN_SCOPE = 3` is what makes
silence mean inadequacy, and on `n-i2c` 44 of 70 oracles never reached it. This
asks the question one level down and constructs the difference directly --
replay the trace the oracle just decided, change one output port to another
legal value, and see whether the verdict moves.

Measured on that same frozen set: 31 of 70 oracles could not be moved by any
perturbation of any port they read, on any testpoint they name. Eleven of those
had reported CONFORMS. `adequacy` convicted 10 of the 31 and ABSTAINED on 21;
it never contradicted this (nothing dead was called adequate), so the two agree
where mutation has evidence and this one has evidence far more often.

WHY THE VERDICT SPLITS IN TWO, AND HOW THE SPLIT IS DECIDED. An oracle that
cannot fail has two possible causes with different owners, and reporting one
number would repeat the mistake the verdict enum exists to fix. The split is
made by ASKING, not by guessing from which ports happen to vary:

  * a NEAR perturbation moves each observed value by one, so it probes the
    neighbourhood of what the design actually did;
  * a FAR one drives the port to each end of its declared range.

Move it near and the oracle is live. Move it only far, and the check can fail
but not anywhere this stimulus goes -- a testplan finding, because the scenario
that would fail it was never approached. Move it neither way and the check
cannot fail at all, which is the author's.

The earlier version of this split guessed the second case from "does any port
it reads vary", and that misroutes: an oracle with a threshold the stimulus
never approaches reads a moving port and is still not the author's fault.

WHAT THIS IS NOT. It is not a claim that the check is wrong, and it says
nothing about whether the check decides the right requirement -- an oracle can
be perfectly live and test the wrong thing entirely. It is the weaker and more
basic property: an instrument that cannot read differently for different inputs
is not an instrument.

DIRECTION OF ERROR. Any change of verdict counts as live, including
CONFORMS -> NOT_EXERCISED caused by a perturbation that destroys the oracle's
own trigger. So the instrument over-credits liveness and the dead set is a
LOWER bound -- which is the safe direction for something whose output is an
accusation.

ISOLATION, AND WHY IT COSTS NOTHING. This takes the model source as an argument
and never chooses it. In [O] the caller passes the WITNESS, because the
reference model does not exist yet; running it against the shipped model would
make oracle acceptance depend on the design, which is the property the stage
order exists to remove.

That would be a real accuracy sacrifice if the answer depended on which design
it ran against. Measured, it does not. The same 70 frozen oracles were assessed
against a generated model scoring 30/168 against golden RTL and against the
known-good control scoring 168/168:

    generated (30/168)  live 44 · dead-oracle 20 · dead-stimulus 3 · unknown 3
    control   (168/168) live 44 · dead-oracle 20 · dead-stimulus 3 · unknown 3

Identical on all 70, and not because the designs are alike -- five oracles
reach different base verdicts on them and four have different assertion port
sets. An oracle that cannot fail cannot fail whatever it is pointed at, which
is what "cannot fail" ought to mean, and it is what makes the witness a
sufficient stand-in here.
"""

from __future__ import annotations

from .oracles import (
    RequirementOracle,
    decide,
    ports_read,
    replay,
    transactional_view,
)

#: A near perturbation moves it: the check discriminates where the design is.
LIVE = "live"
#: Nothing moves it, near or far. The check cannot fail. The author's.
DEAD_ORACLE = "dead-oracle"
#: Only a far perturbation moves it -- it can fail, but not near anything this
#: stimulus produces. A testplan finding, not the author's.
DEAD_STIMULUS = "dead-stimulus"
#: No replayable testpoint, no declared output port, or the model would not run.
UNKNOWN = "unknown"

#: Single-row perturbations tried per port, evenly spaced through the trace, in
#: addition to the whole-trace one. More points only ever move an oracle from
#: dead to live, so this bounds cost against a one-directional gain.
SAMPLE_POINTS = 3


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(str(value), 2)
    except (TypeError, ValueError):
        return None


def _widths(contract: dict) -> dict[str, int]:
    """Declared OUTPUT ports and their widths.

    Outputs only, and that is the substantive choice rather than a filter.
    Inputs are the STIMULUS: changing one asks a different question of the
    design, so an oracle that failed to notice would be right to. Only what the
    design produced is fair to perturb.
    """
    out: dict[str, int] = {}
    for port in contract.get("io") or []:
        name = str(port.get("name") or "")
        if not name or str(port.get("dir") or "").lower() != "output":
            continue
        try:
            out[name] = max(1, int(port.get("width") or 1))
        except (TypeError, ValueError):
            out[name] = 1
    return out


#: "One step from whatever this row holds" -- there is no single target value,
#: so the near direction is spelled as an absence of one.
NEAR = None


def _targets(width: int) -> list[int]:
    """The far targets: each end of the declared range.

    Both ends, tried separately. An earlier version returned them as a list and
    used the first, which meant every port was only ever driven to 0 -- so an
    oracle with an upper threshold was called dead for a reason that was an
    artifact of the probe. Caught by a fixture whose oracle fails above 200 and
    which the sweep reported as unable to fail at all.
    """
    return [0, (1 << width) - 1]


def _perturb(rows: list[dict], port: str, width: int, at: int | None,
             target: int | None = NEAR) -> list[dict] | None:
    """`rows` with `port` set to `target` -- everywhere, or at one row.

    `target is NEAR` means one step from whatever each row holds. `None` comes
    back when nothing changed: the port is absent from the trace, or every row
    already carries the target, and in both cases there is no evidence to take
    from the attempt.

    Shallow-copies only what it rewrites: the trace can be thousands of rows
    and this runs once per (oracle, testpoint, port, point, target).
    """
    out: list[dict] = []
    touched = False
    for index, row in enumerate(rows):
        outputs = row.get("outputs") or {}
        value = _to_int(outputs.get(port))
        if (at is not None and index != at) or port not in outputs or value is None:
            out.append(row)
            continue
        want = (value + 1) % (1 << width) if target is NEAR else target
        if want == value:
            out.append(row)
            continue
        changed = dict(outputs)
        changed[port] = want
        new = dict(row)
        new["outputs"] = changed
        out.append(new)
        touched = True
    return out if touched else None


def _signature(oracle: RequirementOracle, rows: list[dict], transactional: bool):
    """What counts as "the same answer": the decision, not its wording.

    `detail` is prose the oracle composed and can differ for reasons that are
    not a different verdict, so comparing it would call an oracle live for
    changing a number in a message it prints.
    """
    view = transactional_view(rows) if transactional else rows
    result = decide(oracle, view)
    return (result.ok, bool(result.broken))


def _points(count: int) -> list[int | None]:
    """The whole trace, then a few single rows spread through it."""
    if count <= 0:
        return []
    spread = [
        (i + 1) * count // (SAMPLE_POINTS + 1) for i in range(SAMPLE_POINTS)
    ]
    return [None, *sorted({min(max(p, 0), count - 1) for p in spread})]


def liveness_of(
    oracle: RequirementOracle,
    traces: dict[str, list[dict]],
    contract: dict,
    *,
    transactional: bool = True,
) -> dict:
    """One oracle's liveness over the testpoints it names.

    `traces` is testpoint uid -> replayed rows, shared across the whole set:
    replaying once per testpoint rather than once per oracle is what makes this
    cheap enough to be a gate.
    """
    widths = _widths(contract)
    reads = sorted(ports_read(oracle, contract) & set(widths))   # outputs only
    named = [tp for tp in oracle.tp_uids if traces.get(tp)]
    record: dict = {
        "reads": reads,
        "testpoints": named,
        "asserts_on": [],
        "asserts_on_far": [],
        "varying": [],
        "base": {},
    }
    if not named:
        record["verdict"] = UNKNOWN
        record["detail"] = "no testpoint it names has a replayable trace"
        return record
    if not reads:
        record["verdict"] = UNKNOWN
        record["detail"] = "the oracle names no declared output port"
        return record

    near: set[str] = set()
    far: set[str] = set()
    varying: set[str] = set()
    violates = False
    for tp in named:
        rows = traces[tp]
        base = _signature(oracle, rows, transactional)
        record["base"][tp] = list(base)
        if base[0] is False:
            # ALREADY FAILING IS ALREADY LIVE, and it has to be said here
            # rather than left to the perturbation loop. This asks whether the
            # verdict MOVES, and an oracle failing at the first row goes on
            # failing whatever is done to the trace after it -- so the loop
            # would find nothing and report the strongest possible evidence of
            # liveness as its absence. An oracle that is failing a design has
            # demonstrated it can fail; there is no cheaper proof available.
            violates = True
        for port in reads:
            seen = {
                str((row.get("outputs") or {}).get(port))
                for row in rows
                if port in (row.get("outputs") or {})
            }
            if len(seen) > 1:
                varying.add(port)
            attempts = [(NEAR, near)] + [
                (t, far) for t in _targets(widths[port])]
            for target, found in attempts:
                if port in found:
                    continue
                for at in _points(len(rows)):
                    moved = _perturb(rows, port, widths[port], at, target)
                    if moved is None:
                        continue   # nothing to change at this point
                    if _signature(oracle, moved, transactional) != base:
                        found.add(port)
                        break

    record["asserts_on"] = sorted(near)
    record["asserts_on_far"] = sorted(far)
    record["varying"] = sorted(varying)
    if violates and not near:
        record["verdict"] = LIVE
        record["detail"] = ("it is failing this design, which is a "
                            "demonstration that it can fail")
    elif near:
        record["verdict"] = LIVE
        record["detail"] = f"the verdict moves when {', '.join(sorted(near))} changes"
    elif far:
        record["verdict"] = DEAD_STIMULUS
        record["detail"] = (
            f"the check can fail -- {', '.join(sorted(far))} at the end of its "
            f"range moves it -- but nothing this stimulus produces comes near "
            f"that, so it cannot decide anything here")
    else:
        record["verdict"] = DEAD_ORACLE
        record["detail"] = (
            f"no legal value of {', '.join(reads)}, near or far, changes the "
            f"verdict on any testpoint it names")
    return record


def replay_all(
    oracles: list[RequirementOracle],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
) -> dict[str, list[dict]]:
    """Each named testpoint replayed once, for the whole oracle set."""
    traces: dict[str, list[dict]] = {}
    for tp in sorted({tp for o in oracles for tp in o.tp_uids}):
        steps = stimulus_by_tp.get(tp)
        if not steps:
            continue
        run = replay(source, contract, steps, base=base)
        if not run.error and run.rows:
            traces[tp] = run.rows
    return traces


def assess(
    oracles: list[RequirementOracle],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    transactional: bool = True,
) -> dict[str, dict]:
    """`req_uid -> record` for every oracle, including the ones nothing decided.

    Every oracle appears, for the reason `verdict.classify` gives: a set that
    silently omits the ones it could not judge reads as a clean result.
    """
    traces = replay_all(oracles, source, contract, stimulus_by_tp, base=base)
    return {
        oracle.req_uid: liveness_of(
            oracle, traces, contract, transactional=transactional)
        for oracle in oracles
    }


def counts(report: dict[str, dict]) -> dict[str, int]:
    """Every verdict counted, zeroes kept -- `verdict.counts`'s reasoning."""
    out = {v: 0 for v in (LIVE, DEAD_ORACLE, DEAD_STIMULUS, UNKNOWN)}
    for record in report.values():
        verdict = record.get("verdict", UNKNOWN)
        out[verdict] = out.get(verdict, 0) + 1
    return out


def dead(report: dict[str, dict]) -> dict[str, str]:
    """The oracles that cannot fail, and why -- the author's ones only.

    `DEAD_STIMULUS` is deliberately absent: the check demonstrably CAN fail --
    a far perturbation moved it -- so it is a finding about the testplan, and
    handing it to the oracle author would have them strengthen a check that was
    never the problem.
    """
    return {
        uid: record.get("detail", "")
        for uid, record in sorted(report.items())
        if record.get("verdict") == DEAD_ORACLE
    }


def assertion_ports(report: dict[str, dict]) -> dict[str, set[str]]:
    """The ports each oracle actually decides on.

    `adequacy` scopes its mutants with `ports_read`, which counts a port the
    oracle only TRIGGERS on -- measured on the frozen set, 45% of the ports it
    scopes on carry no assertion. Projecting onto these instead narrows the
    mutants that count to the ones the oracle could actually have caught.
    """
    return {
        uid: set(record.get("asserts_on") or ())
        for uid, record in report.items()
    }
