"""One executable mini-oracle per requirement.

The reference model is the oracle for a whole design. A `RequirementOracle` is
the same object scoped to one clause of the specification: given the model's
trace under the stimulus written for that requirement, it DECIDES whether the
clause holds, and says at which edge it made up its mind.

Why executable rather than declarative. A closed vocabulary of predicates was
tried on paper first and does not survive the corpus: `cmd_ack` pulsing for
exactly one clock is a duration claim, SDA released while filtered SCL is high
relates two ports at one edge, and arbitration lost when the value read back
differs from the value driven relates an input to an output. Anything covering
those is a temporal language, and writing one is a larger project than the loop
it would serve.

Why one per requirement rather than several. A bag of unordered predicates
cannot decide -- nobody can say which subset means "met" -- and this codebase
would not call anything an oracle that could not decide. One-per-requirement
also gives the repair loop a metric with the same shape as the verdict set it
came from: N failing oracles going to zero, comparable turn against turn.

Nothing here does I/O and nothing here calls a model. That is what lets a debug
attempt cost milliseconds: `specflow/refmodel/base.py` imports nothing from
cocotb, so a generated model runs in a plain interpreter.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from ..ports import asserted_resets, idle_values, pinned_inputs
from ..tb.runtime import is_reset_step, normalise_step
from .validate import _static_checks

#: Hard bound on edges any one replay will simulate. A stimulus step may declare
#: `until ... timeout=4000`, and an oracle that never fires must not spin.
EDGE_BUDGET = 4000


class RequirementOracle(BaseModel):
    """A decision procedure for one requirement, written by the judge."""

    #: Stamped by the harness, never trusted from the model -- the same
    #: treatment `run_judge` already gives `RequirementVerdict.req_uid`.
    req_uid: str = ""
    #: The testpoints whose stimulus exercises this clause.
    tp_uids: list[str] = Field(default_factory=list)
    #: The sentence of the requirement this oracle decides, verbatim, so a
    #: reader can tell an over-strict oracle from a real defect.
    clause: str = ""
    #: Python defining `def decide(trace)` and returning
    #: `(ok: bool | None, edge: int | None, detail: str)`.
    source: str = ""
    #: Content hash over the question asked and the answer given -- see
    #: `freeze.content_hash`. Stamped when the set is frozen, so that a later
    #: turn can prove it is deciding with the same oracles it started with.
    #: Empty means "never frozen", which is what a judge-written oracle is.
    hash: str = ""


@dataclass(frozen=True)
class OracleResult:
    """Why `broken` is separate from `ok`.

    An oracle that raises, returns the wrong shape, or names a testpoint that
    does not exist is a defect in the ORACLE. Reporting that as a failing model
    would send a repair loop after code that may be perfectly correct, which is
    the exact failure this whole design exists to stop -- one level up.
    """

    req_uid: str
    #: True, False, or None. None means the clause's SCENARIO never occurred in
    #: this trace -- see `decide` for why that cannot be folded into False.
    ok: bool | None
    edge: int | None = None
    detail: str = ""
    broken: str = ""
    #: True when what raised was the MODEL, not the oracle. `broken` alone
    #: cannot be routed: an oracle that returns the wrong shape is a defect in
    #: the check and chasing it means editing code that may be correct, while a
    #: model that crashes mid-replay is a defect in the MODEL and the cheapest
    #: way to make every oracle stop complaining. Measured on h-i2c r3: one edit
    #: raised `AttributeError('Model' object has no attribute 'COMPLETE')` and
    #: 54 of 77 oracles went `broken` at once, which scored as near-perfect
    #: because `distance()` counts neither failing nor unexercised there.
    model_broke: bool = False
    #: The trace it judged, so a caller never re-runs to find out why.
    rows: list[dict] = field(default_factory=list)

    def failed(self) -> bool:
        """The model is wrong here. The only state a repair loop should chase."""
        return self.ok is False and not self.broken

    def model_defect(self) -> bool:
        """A finding about the MODEL, whether it answered wrongly or crashed."""
        return self.failed() or self.model_broke

    def unexercised(self) -> bool:
        """The stimulus never created the situation the clause is about.

        Not a model defect and not an oracle defect -- a testplan finding.
        """
        return self.ok is None and not self.broken


@dataclass(frozen=True)
class Replay:
    rows: list[dict]
    notes: list[str] = field(default_factory=list)
    error: str = ""


def _load(source: str, base: str):
    """`(fn, error)` -- a callable bound method of a fresh `Model`, or why not."""
    namespace: dict = {}
    try:
        exec(compile(source, "<refmodel>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return None, f"does not import: {exc!r}"
    model_cls = namespace.get("Model")
    if model_cls is None:
        return None, "defines no class named Model"
    try:
        fn = getattr(model_cls(), base, None)
    except Exception as exc:  # noqa: BLE001
        return None, f"Model() does not instantiate: {exc!r}"
    if not callable(fn):
        return None, f"has no callable {base!r}"
    return fn, ""


def replay(
    source: str,
    contract: dict,
    steps: list[dict],
    *,
    base: str,
    edge_budget: int = EDGE_BUDGET,
) -> Replay:
    """Drive `source` over one testpoint's concrete stimulus, structurally.

    Rows are `{"edge": int, "inputs": {...}, "outputs": {...}}` -- the shape an
    oracle reasons over. The run-length-encoded strings elsewhere in this
    package exist for prompts, where repetition costs tokens; a decision
    procedure wants the edges.

    `normalise_step` is the testbench's own decoder, imported rather than
    reimplemented, so a replay cannot drift from what the suite will really do.
    `until` resolves against the MODEL's output here -- there is no DUT at this
    stage -- and runs to the timeout the testpoint declared, because capping it
    at a render budget makes a scenario stop early and read as one the model
    never completed.
    """
    fn, err = _load(source, base)
    if err:
        return Replay([], [], err)

    idle_resets = dict(pinned_inputs(contract))
    active_resets = asserted_resets(contract)
    all_idle = dict(idle_values(contract))
    state = dict(idle_resets)
    rows: list[dict] = []
    notes: list[str] = []
    resetting = False
    exhausted = False
    for raw in steps:
        if exhausted:
            # ONLY the edge budget stops a replay. A step whose `until` timed
            # out has produced a real, complete observation -- "waited, it did
            # not happen" -- and the steps after it are a different part of the
            # scenario, not a continuation of that wait.
            #
            # Breaking on any note instead truncated 61 of the 167 testpoints on
            # d-i2c, throwing away 259 stimulus steps and 17 reset steps that
            # were never executed at all. The oracles then reported, correctly,
            # that they could not see their scenario -- and the loss looked like
            # a thin testplan when the testplan had asked for exactly the right
            # thing and the harness had declined to run it.
            break
        inputs, hold, until, timeout = normalise_step(raw)
        if is_reset_step(raw):
            # Both halves, together. `model.reset()` restores the state the
            # runtime's own reset would, and driving the reset port ACTIVE makes
            # that visible to an oracle -- a requirement about reset behaviour
            # is otherwise unjudgeable, because it can never observe the event
            # it is about. Doing only the first would leave the trace showing
            # reset de-asserted throughout; doing only the second would trust a
            # generated model to honour a port it may ignore.
            # Every input to its idle value while reset is held, mirroring
            # `Env.reset()`, which does the same so the DUT and the model start
            # from one defined state rather than from whatever the last vector
            # left. Holding the previous functional inputs instead would let the
            # design keep advancing through its own reset.
            state = dict(all_idle)
            state.update(active_resets)
            until, timeout = None, 0
            resetting = True
        else:
            resetting = False
            state.update(idle_resets)
            state.update(inputs)
        edges = timeout if until else hold
        reached = False
        for _ in range(max(1, edges)):
            if len(rows) >= edge_budget:
                notes.append(f"stopped after {edge_budget} edges")
                exhausted = True
                break
            if resetting:
                # Re-applied every edge: reset is a level, not a pulse, so the
                # model must be in its reset state for as long as it is held --
                # and a generated model that ignores the reset PORT would
                # otherwise keep running underneath an asserted reset.
                try:
                    fn.__self__.reset()
                except Exception as exc:  # noqa: BLE001
                    return Replay(rows, notes,
                                  f"reset() raised at edge {len(rows)}: {exc!r}")
            try:
                out = fn(dict(state))
            except Exception as exc:  # noqa: BLE001
                return Replay(rows, notes, f"raised at edge {len(rows)}: {exc!r}")
            if not isinstance(out, dict):
                return Replay(
                    rows, notes,
                    f"returned {type(out).__name__} at edge {len(rows)}, "
                    f"expected a dict of outputs",
                )
            rows.append({
                "edge": len(rows),
                "inputs": dict(state),
                "outputs": dict(out),
            })
            if until and out.get(str(until.get("port"))) == until.get("value"):
                reached = True
                break
        if until and not reached and not exhausted:
            # Stated, never blamed. Checked against the known-correct control on
            # this run's own stimulus: 23 of 60 scenarios never fire their
            # `until`, because the stimulus paired clk_cnt=200 with timeout=500
            # when one command at that divider needs upwards of 1000 edges.
            notes.append(
                f"{until.get('port')} did not reach {until.get('value')!r} "
                f"within the {edges} edges this testpoint allows"
            )
    return Replay(rows, notes, "")


def transactional_view(rows: list[dict]) -> list[dict]:
    """The trace as a sequence of distinct states, with how long each was held.

    `trace_compare.transactional` is the accept criterion this whole pipeline
    compares by: the ordered sequence of distinct observable states, durations
    reported rather than enforced. It exists because cycle-exactness was being
    enforced against a fiction -- a guessed `latency_cycles` -- and measured
    three times WORSE at separating good RTL from bad (separation 15 vs 40).

    An oracle deciding over raw edges is not held to that criterion. It indexes
    absolute edge numbers, and the measured consequence is the dominant form of
    over-strictness on g-i2c: "busy low when START detected at edge 13", when
    the design sees that START through a two-stage synchroniser and a
    three-sample majority filter and answers several edges later. 27 of 77
    oracles are failed by an implementation scoring 181/181 against golden.

    So give the oracle the same view the accept criterion uses. Consecutive
    identical rows collapse, which makes "the next row" mean "the next distinct
    state" rather than "the next clock" -- much closer to what a specification
    means by "then", and latency-insensitive by construction.

    Compression is over the WHOLE row, inputs included, not over outputs alone.
    An i2c oracle detects START as an INPUT event (SDA falling while SCL is
    high); compressing outputs only would swallow input transitions inside a
    held output state and hide exactly the events these clauses are about.

    This is not a guarantee. An oracle can still write "at the state where the
    input event appears, require the output" and be wrong -- no trace shape
    prevents that, which is why the must-pass gate exists. What it removes is
    the temptation to pin an absolute edge, and it converts a large class of
    edge-exact reasoning into state-sequence reasoning for free.

    `edge` is kept, holding the FIRST edge of each state, so an oracle written
    against the raw shape still runs and still localises. `index` and `held` are
    what a transactional oracle should use.
    """
    out: list[dict] = []
    for row in rows:
        key = (tuple(sorted(row["inputs"].items())),
               tuple(sorted(row["outputs"].items())))
        if out and out[-1]["_key"] == key:
            out[-1]["held"] += 1
            continue
        out.append({
            "_key": key,
            "index": len(out),
            "edge": row["edge"],
            "first_edge": row["edge"],
            "held": 1,
            "inputs": dict(row["inputs"]),
            "outputs": dict(row["outputs"]),
        })
    for row in out:
        del row["_key"]
    return out


def decide(oracle: RequirementOracle, trace: list[dict]) -> OracleResult:
    """Run one oracle over one trace. Never raises.

    `ok` is True, False, or **None -- the clause's scenario never occurred**.

    That third state is not fastidiousness. Without it an oracle whose
    precondition is absent has two choices and both are wrong: return True and
    it is vacuous, which the sensitivity gate exists to convict; return False
    and a correct model is blamed for stimulus that never drove the case. Every
    judge in the a-i2c run faced that choice and most took the second option --
    of the 22 oracles a known-good control failed, 13 fail with details like
    "no STOP condition observed in trace", "nReset was never asserted low", and
    (this one wrote its own epitaph) "trace does not expose cnt or clk_en;
    cannot determine reload".

    Those 13 were then handed to a debug agent as model defects. It could not
    fix them, because there was nothing wrong to fix.

    This is the same discipline gate 2 already applies when it reports UNKNOWN
    rather than vacuous, and that the trace note applies when it refuses to call
    a short timeout a defect: a check that cannot see must never report a
    verdict it has not earned.
    """
    fn, err = _oracle_fn(oracle)
    if err:
        return OracleResult(oracle.req_uid, ok=False, broken=err, rows=trace)
    try:
        verdict = fn(trace)
    except Exception as exc:  # noqa: BLE001
        return OracleResult(
            oracle.req_uid, ok=False, rows=trace,
            broken=f"decide() raised: {exc!r}",
        )
    ok, edge, detail = _unpack(verdict)
    if ok is MALFORMED:
        return OracleResult(
            oracle.req_uid, ok=False, rows=trace,
            broken=f"decide() returned {verdict!r}, expected (ok, edge, detail)",
        )
    return OracleResult(oracle.req_uid, ok=ok, edge=edge, detail=detail, rows=trace)


def _oracle_fn(oracle: RequirementOracle):
    namespace: dict = {}
    try:
        exec(compile(oracle.source, f"<oracle:{oracle.req_uid}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return None, f"oracle does not import: {exc!r}"
    fn = namespace.get("decide")
    if not callable(fn):
        return None, "oracle defines no callable named `decide`"
    return fn, ""


#: `_unpack` cannot use None to mean "bad shape" any more -- None is now a
#: verdict in its own right.
MALFORMED = object()

#: `decide` returns a bool, but its author also writes a VERDICT in the same
#: reply and sometimes carries that vocabulary across. Only exact words map;
#: anything else is still a malformed oracle.
_WORD_TO_OK: dict[str, object] = {
    "true": True, "met": True, "pass": True, "passed": True, "holds": True,
    "false": False, "not_met": False, "fail": False, "failed": False,
    "violated": False,
    "none": None, "ambiguous": None, "unknown": None, "inconclusive": None,
    "not_exercised": None, "unexercised": None, "not_applicable": None,
}


def _unpack(verdict: Any) -> tuple[Any, int | None, str]:
    """Accept `(ok, edge, detail)`, and a bare bool for the trivial case.

    `ok` may be True, False, or None; None means the scenario never occurred.
    """
    if isinstance(verdict, bool):
        return verdict, None, ""
    if isinstance(verdict, (tuple, list)) and len(verdict) in (2, 3):
        ok, edge, detail = (
            verdict if len(verdict) == 3 else (verdict[0], None, verdict[1])
        )
        # A verdict WORD where the tri-state wants a bool. The judge writes the
        # verdict and the oracle in one reply, and it carries the vocabulary of
        # the first across into the second: on d-i2c r0 that was 5 oracles
        # returning ('met', ...), ('ambiguous', ...) or ('not_met', ...). The
        # mapping is exact and the rest of the tuple is fine, so reading it
        # loses nothing -- and an oracle discarded here is a requirement handed
        # back to the model agent as unverifiable prose.
        if isinstance(ok, str):
            ok = _WORD_TO_OK.get(ok.strip().lower().replace(" ", "_"), MALFORMED)
        if isinstance(ok, bool) or ok is None:
            edge = edge if isinstance(edge, int) and not isinstance(edge, bool) else None
            return ok, edge, str(detail)
    return MALFORMED, None, ""


def decide_all(
    oracles: list[RequirementOracle],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    edge_budget: int = EDGE_BUDGET,
    transactional: bool = False,
) -> list[OracleResult]:
    """Decide every oracle, replaying each testpoint at most once.

    An oracle naming several testpoints holds only if it holds on all of them:
    each is a scenario the clause is supposed to survive, so the first failure
    is the answer and carries its own edge.
    """
    cache: dict[str, Replay] = {}
    out: list[OracleResult] = []
    for oracle in oracles:
        results: list[OracleResult] = []
        for tp in oracle.tp_uids:
            steps = stimulus_by_tp.get(tp)
            if not steps:
                results.append(OracleResult(
                    oracle.req_uid, ok=False,
                    broken=f"no stimulus recorded for {tp}",
                ))
                continue
            if tp not in cache:
                cache[tp] = replay(
                    source, contract, steps, base=base, edge_budget=edge_budget)
            rep = cache[tp]
            if rep.error:
                results.append(OracleResult(
                    oracle.req_uid, ok=False, rows=rep.rows,
                    broken=f"the MODEL {rep.error}",
                    model_broke=True,
                ))
                continue
            rows = transactional_view(rep.rows) if transactional else rep.rows
            results.append(decide(oracle, rows))
        out.append(_worst(oracle.req_uid, results))
    return out


def _worst(req_uid: str, results: list[OracleResult]) -> OracleResult:
    """Broken beats failing beats passing beats unexercised.

    Unexercised ranks below failing because a clause shown to be violated on one
    testpoint is violated, whatever the others could not see.

    It ranks below PASSING, which is a change from ranking above. The old rule
    read "an oracle that passed only where its scenario never arose has not
    actually agreed to anything" -- true when EVERY result is unexercised, and
    wrong when one testpoint genuinely staged the scenario and the clause held.
    Silence is not disagreement, and an oracle cannot return True without having
    SEEN its case (`decide`'s tri-state guarantees it), so a pass among the
    results is a real observation while the `None` beside it is the absence of
    one.

    Under the old rule a clause exercised by one of its testpoints and not by
    another could never be reported as met, and an evidence set that GREW could
    only make a verdict worse -- which makes adding a testpoint a hostile act
    rather than the monotone improvement it should be.
    """
    if not results:
        return OracleResult(req_uid, ok=False, broken="the oracle names no testpoint")
    for r in results:
        if r.broken:
            return r
    for r in results:
        if r.failed():
            return r
    for r in results:
        if r.ok is True:
            return r
    return results[0]


def ports_read(oracle: RequirementOracle, contract: dict) -> set[str]:
    """The declared ports this oracle's source mentions.

    Used to project a trace down to what this clause is about. Without it the
    mutation gate convicts a correct narrow oracle for staying silent about a
    signal it was never meant to watch -- and pushing oracles wider is exactly
    what the over-strictness gate then punishes.

    A string-literal scan rather than dataflow: an oracle reads a trace row by
    subscripting it with port names, so the names appear as constants. Over-
    approximating here is safe -- it only makes the gate more conservative.
    """
    declared = {
        str(p.get("name")) for p in (contract.get("io") or []) if p.get("name")
    }
    try:
        tree = ast.parse(oracle.source)
    except SyntaxError:
        return set()
    seen = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    return {name for name in declared if name in seen}


def well_formed(
    oracle: RequirementOracle, contract: dict, testplan: list[dict]
) -> str | None:
    """Why this oracle cannot be used, or None.

    Screened BEFORE the loop sees it, so no debug attempt is ever spent
    satisfying something malformed. The sandbox is `validate._static_checks`,
    reused rather than re-derived: an oracle is the same trust class as the
    reference model -- generated Python this process will execute -- and if that
    screen is not good enough for one it is not good enough for the other.
    """
    if not oracle.source.strip():
        return "the oracle has no source"
    issues = [i for i in _static_checks(oracle.source, [], {}) if i.severity == "error"]
    if issues:
        return issues[0].message
    if not oracle.tp_uids:
        return "the oracle names no testpoint to replay"
    known = {str(tp.get("uid")) for tp in testplan}
    unknown = [tp for tp in oracle.tp_uids if tp not in known]
    if unknown:
        return f"names testpoints that are not in the testplan: {sorted(unknown)}"
    fn, err = _oracle_fn(oracle)
    if err:
        return err
    try:
        arity = fn.__code__.co_argcount
    except AttributeError:
        return "`decide` is not an ordinary function"
    if arity != 1:
        return f"`decide` takes {arity} arguments, expected exactly 1 (the trace)"
    if not ports_read(oracle, contract):
        # An oracle naming no declared port cannot be about observable
        # behaviour, and the mutation gate could never scope a mutant to it.
        return "names no declared port, so it decides nothing observable"
    return None


@dataclass(frozen=True)
class Liveness:
    """Which testpoints actually make the model do something."""

    #: tp_uid -> distinct output states observed across its replay.
    states: dict[str, int] = field(default_factory=dict)
    #: tp_uid -> edges replayed.
    edges: dict[str, int] = field(default_factory=dict)
    #: tp_uids whose replay never changed a single output.
    inert: list[str] = field(default_factory=list)
    #: tp_uid -> why the replay could not run at all.
    errors: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict:
        total = len(self.states) + len(self.errors)
        return {
            "testpoints": total,
            "inert": len(self.inert),
            "failed_to_replay": len(self.errors),
            "inert_fraction": round(len(self.inert) / total, 3) if total else 0.0,
        }


def stimulus_liveness(
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    edge_budget: int = EDGE_BUDGET,
) -> Liveness:
    """Replay every testpoint and record whether the model moved at all.

    An inert testpoint cannot decide anything, so every oracle naming one is
    unjudgeable however well it is written. That makes this the root cause
    underneath two symptoms that look like other people's fault: an oracle
    reporting "no STOP condition observed in trace" reads as over-strictness,
    and a sensitivity sweep finding no in-scope mutant reads as a thin oracle.
    Both are the stimulus.

    Measured on the a-i2c run, where 35 of 167 testpoints moved neither the
    generated model nor the known-good control: the dominant cause was a
    prescaler driven far faster than the run is long. `clk_cnt` selects a
    divider, and 60 of 167 testpoints hold a value so large that the run ends
    before one tick completes -- `clk_cnt=1000` with 129 edges, `clk_cnt=65535`
    at all. On testpoints where the control moves the median run affords 3.5
    ticks; on the inert ones, 0.2.

    This cannot move into `gate_suite`, which runs before any model exists and
    which deliberately refuses distinctness rules for reasons its own docstring
    gives. Inertness is not distinctness: it is a property of the DUT's response,
    so it can only be measured once there is something to respond.
    """
    states: dict[str, int] = {}
    edges: dict[str, int] = {}
    inert: list[str] = []
    errors: dict[str, str] = {}
    for tp, steps in stimulus_by_tp.items():
        run = replay(source, contract, steps, base=base, edge_budget=edge_budget)
        if run.error:
            errors[tp] = run.error
            continue
        seen = {tuple(sorted(r["outputs"].items())) for r in run.rows}
        states[tp] = len(seen)
        edges[tp] = len(run.rows)
        if len(seen) <= 1:
            inert.append(tp)
    return Liveness(states=states, edges=edges, inert=sorted(inert), errors=errors)
