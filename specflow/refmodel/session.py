"""A debug session over one reference model and one frozen set of oracles.

This is the half of the agentic loop that has nothing to do with agents. It
holds the model source, decides the oracles against it, edits methods, and
tracks the best version it has seen. `eda_agent/refmodel_editor.py` wraps it in
tools and hands it to a ReAct agent; everything decidable about the loop's
behaviour is decidable here, without a model call.

Two rules the session enforces rather than trusts:

**Oracles are frozen.** Nothing here can edit one. A loop able to weaken what
measures it will do that, because it is the cheapest path to green -- the same
shortcut as an inert reference model, one level up.

**A turn cannot end worse than it started.** `best()` returns the lowest
`distance()` seen, with `note_best`'s tie rule: the EARLIEST source reaching a
given score wins, so a run wandering across a plateau returns where it first
arrived rather than wherever it happened to stop.

**The scoring key counts unexercised oracles as well as failing ones.** It has
to. An oracle reports `ok is False` for a case the model got wrong and
`ok is None` for a case that never arose, and only the first is "failing" -- so
scoring on failing alone means an edit that stops the design ever reaching a
scenario reduces the count and is recorded as an improvement. Making a
requirement unverifiable would score as fixing it.
"""

from __future__ import annotations

import ast
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..ids import PREFIX_TESTPLAN, mint, next_index
from ..obligation import FIRED, Obligation, check_static
from .oracles import OracleResult, RequirementOracle, decide_all, replay
from .validate import validate_source

#: I8's two repair routes. A turn takes exactly one, and which one is decided
#: by the session rather than by the agent: an agent free to pick would take
#: whichever is cheaper to look busy on, and the whole value of the rule is that
#: a turn's outcome stays attributable to one cause.
MODEL = "model"
STIMULUS = "stimulus"


@dataclass
class Edit:
    """One attempt, and what became of it."""

    method: str
    accepted: bool
    reason: str
    failing_before: int
    failing_after: int


def _activity(rows: list[dict]) -> dict:
    """Where each output first moves, and how many states the run reaches.

    Without this the window IS the view, and it defaults to the first 60 edges.
    On a prescaled design the first thousand edges are identical idle rows, so
    an agent reading them sees a flat trace and cannot tell "this testpoint
    exercises nothing" from "I did not look far enough" -- two conclusions that
    demand opposite responses, with six attempts to spend on the difference.
    The a-i2c debug turn reported the former about testpoints whose head was all
    it had seen, and it had no tool that could have told it otherwise.

    Computed over the whole replay, never the window, because its entire purpose
    is to describe what the window is missing.
    """
    if not rows:
        return {"distinct_output_states": 0, "inert": True, "first_change": {}}
    first = dict(rows[0]["outputs"])
    changes: dict[str, int | None] = dict.fromkeys(first)
    for row in rows:
        for name, value in row["outputs"].items():
            if changes.get(name) is None and value != first.get(name):
                changes[name] = row["edge"]
    states = len({tuple(sorted(r["outputs"].items())) for r in rows})
    return {
        "distinct_output_states": states,
        "inert": states <= 1,
        "first_change": changes,
    }


class DebugSession:
    """Edit a reference model until a frozen set of oracles is satisfied."""

    def __init__(
        self,
        source: str,
        contract: dict,
        stimulus_by_tp: dict[str, list[dict]],
        oracles: list[RequirementOracle],
        *,
        base: str,
        requirements: list[dict] | None = None,
        verdicts: dict[str, str] | None = None,
        reasons: dict[str, dict] | None = None,
        covers: dict[str, list[str]] | None = None,
        #: `req_uid -> what a second implementation of the same requirement
        #: observed`, for the checks it could not satisfy either. NOT a verdict
        #: and never a reason to skip: the witness is a second reading by the
        #: same author and cannot overrule the requirement. It says where a
        #: turn is unlikely to be repaid, and the agent decides.
        #:
        #: Measured on r-i2c: the loop drove VIOLATES 9 -> 5 and spent its last
        #: three turns on the 5 that remained, every one of which a known-good
        #: control also fails. The witness had flagged exactly those five
        #: before the reference model existed.
        witness_notes: dict[str, str] | None = None,
        workdir: Path | None = None,
        #: `(requirement, hint) -> steps`, or None. Injected rather than
        #: imported for the same reason `compose.RefModelDebugger` is: the
        #: generator needs a model port, and the decidable half of this session
        #: must stay runnable with no model at all.
        stimulus_gen=None,
        #: req_uid -> normalized form, for matching a new testpoint to the
        #: activations it fires.
        normalized: dict[str, dict] | None = None,
        testplan: list[dict] | None = None,
        reset_ports: frozenset[str] = frozenset(),
        #: Decide over distinct states rather than raw edges, matching the
        #: accept criterion (`trace_compare.transactional`). Must match what
        #: screening used, or the session sees verdicts the gates never did.
        transactional: bool = False,
        #: Testpoints this session may add, total. Append-only means they
        #: accumulate, and every one becomes a simulator process in the rendered
        #: suite (`run.py:200-204`, ~0.39s each).
        stimulus_budget: int = 12,
        #: The previous turn edited the model and the failing count did not
        #: fall. See `route` -- this is what stops failing-first from starving
        #: the stimulus route forever.
        model_route_stalled: bool = False,
    ):
        self.source = source
        self.contract = contract
        self.stimulus_by_tp = stimulus_by_tp
        self.oracles = list(oracles)
        self.base = base
        self.requirements = {str(r.get("uid")): r for r in (requirements or [])}
        self.verdicts = dict(verdicts or {})
        self.reasons = dict(reasons or {})
        self.covers = dict(covers or {})
        self.witness_notes = dict(witness_notes or {})
        # `validate_source` writes a scratch copy so the exec has a filename;
        # it is not optional and the session must not scribble in the run dir.
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="refmodel-debug-"))

        self.stimulus_gen = stimulus_gen
        self.normalized = dict(normalized or {})
        self.testplan = list(testplan or [])
        self.reset_ports = reset_ports
        self.transactional = transactional
        self.stimulus_budget = int(stimulus_budget)
        self.added: list[str] = []

        self.history: list[Edit] = []
        self._results: list[OracleResult] = []
        self.best_source = source
        self.best_failing: int | None = None
        self.refresh()
        #: I8, decided once at entry. ADVISORY as of the measurement below:
        #: it chooses what the brief leads with and feeds the stalled signal,
        #: and it no longer refuses a tool. A turn with both a failing oracle
        #: and an unexercised one has two repair routes available, and taking
        #: both makes the turn's outcome harder to attribute -- the model
        #: changed AND the evidence changed. That is a reason to ORDER them,
        #: which the brief does, and `trust.json` records `stimulus_added` per
        #: turn separately from the verdict counts so the two are still
        #: tellable apart after the fact. FAILING FIRST -- a VIOLATES is
        #: evidence about the model that already exists and costs no model call
        #: to act on, while a NOT_EXERCISED costs a stimulus generation and may
        #: still not fire.
        #:
        #: As a REFUSAL it cost the whole route: `add_stimulus` permitted only
        #: when nothing was failing, and `RefModelEditor.debug` invoking the
        #: agent only when something was. Mutually exclusive, and the tool went
        #: uncalled in five consecutive runs.
        #:
        #: "Nothing left to do" is NOT "nothing failing", and reading it that
        #: way starves the stimulus route completely. Measured on h-i2c:
        #: VIOLATES fell 9, 7, 5 over three turns and never reached zero, so
        #: `add_stimulus` was never once reached and NOT_EXERCISED sat at 18
        #: throughout. A turn that reduced the failing count earned another
        #: model turn; a turn that did not has run the model route dry, whether
        #: or not something is still failing.
        self.route = MODEL
        if not self.failing():
            self.route = STIMULUS
        elif model_route_stalled and any(r.unexercised() for r in self._results):
            self.route = STIMULUS

    # ------------------------------------------------------------- state

    def refresh(self) -> list[OracleResult]:
        self._results = decide_all(
            self.oracles, self.source, self.contract,
            self.stimulus_by_tp, base=self.base,
            transactional=self.transactional,
        )
        self.note_best(self.source)
        return self._results

    @property
    def results(self) -> list[OracleResult]:
        return self._results

    def failing(self) -> list[OracleResult]:
        """Oracles still to satisfy. A BROKEN oracle is not one of them.

        It decides nothing, so counting it would make the session chase a defect
        in the oracle by editing the model -- which is the confusion this whole
        design exists to prevent.
        """
        return [r for r in self._results if r.failed()]

    def all_met(self) -> bool:
        return not self.failing()

    def undecided(self) -> list[OracleResult]:
        """Oracles whose scenario the stimulus never staged, under this model.

        Not the agent's to fix -- but very much its to AVOID CAUSING, which is
        why the scoring key below counts them.
        """
        return [r for r in self._results if r.unexercised()]

    def distance(self) -> int:
        """How far this model is from satisfying the oracle set.

        `failing()` alone is the wrong key, and the way it is wrong rewards the
        worst available edit. An oracle reports `ok is False` when the model got
        the case wrong and `ok is None` when the case never arose
        (`oracles.py:80-89`), and only the first counts as failing -- so an edit
        that stops the design ever reaching a scenario turns a VIOLATES into a
        NOT_EXERCISED, REDUCES the failing count, and is recorded as a new best.
        Making a requirement unverifiable scored as fixing it.

        Counting both closes that: the conversion is now neutral rather than
        rewarded, while genuinely satisfying a clause still improves the score.

        Broken ORACLES stay out, exactly as `failing()` leaves them out. One
        decides nothing, so chasing it means editing the model to fix a defect
        in the check -- the confusion this whole design exists to prevent.

        A broken MODEL is the opposite case and must be counted, for the same
        reason unexercised is. When the model raises mid-replay every result
        goes `broken` at once, which is neither failing nor unexercised -- so
        without this the score COLLAPSES TO ZERO and the crashing model is
        recorded as the best one seen. Measured on h-i2c r3: an edit raised
        `AttributeError('Model' object has no attribute 'COMPLETE')` and 54 of
        77 oracles stopped deciding in one step.
        """
        return (len(self.failing()) + len(self.undecided())
                + sum(1 for r in self._results if r.model_broke))

    def note_best(self, source: str) -> bool:
        """Record `source` if it is the best seen. Ties do NOT overwrite.

        Tie semantics taken unchanged from `rtl_editor._EditSession.note_best`,
        whose rule is pinned by `tests/test_rollback_guard.py`: the EARLIEST
        source reaching a given score wins, so a run wandering across a plateau
        returns where it first arrived rather than wherever it stopped.
        """
        count = self.distance()
        if self.best_failing is None or count < self.best_failing:
            self.best_failing = count
            self.best_source = source
            return True
        return False

    def best(self) -> str:
        """The best model this session reached -- never worse than it started."""
        return self.best_source

    # ------------------------------------------------------------- tools

    #: Said on every finding that has no executable check behind it. The verdict
    #: is unchanged -- losing an oracle is not evidence about the model -- but
    #: what supports it is different in kind, and a caller that cannot tell the
    #: two apart will spend the same effort on both.
    ANECDOTAL = (
        "NO EXECUTABLE CHECK. This verdict rests only on the judge's reading of "
        "the source -- it was never mechanically confirmed, and no oracle "
        "survived screening for it. Treat it as a lead, not a proven defect: "
        "read `explain` for the reasoning, replay the behaviour yourself, and "
        "if the reasoning does not hold up, leave the model alone."
    )

    # ------------------------------------------------------------ targeting
    #
    # THE FAILURE DECIDES WHAT IS READABLE.
    #
    # `RTLEditor` never offers the agent the design. It slices backwards from
    # the signals that actually diverged (`trace_slicer.dynamic_slice`, depth 3)
    # and the agent's whole readable surface is that slice: `read_block` refuses
    # an id outside it, `list_suspect_blocks` returns only it, and the trace
    # window is anchored at the first divergence because "the earliest
    # divergence is the one that explains the others, and a later sample is
    # usually downstream corruption" (`trace_report.py:_extract_values`).
    #
    # This session already holds both projections a slice needs and used neither
    # to shape a tool: `covers` maps a requirement to the methods claimed to
    # implement it (the driver map), and `OracleResult.edge` is the edge the
    # oracle decided on (the anchor). The defaults below are built from them.
    #
    # WHAT TARGETING MUST NOT DO. `rtl_editor` records B21: dropping the
    # expected/actual VALUES left the debugger with signal names only, so it
    # "invented a timing theory ... rewrote `always_ff` to `always_comb` and
    # broke the contract's 1-cycle latency". The rule is the decisive data in
    # full and nothing else -- never a smaller sample of everything.
    #
    # And no silent caps: every narrowed answer says what it left out and how to
    # ask for it (`rtl_editor.py:236-243`).

    #: Rows either side of the deciding edge. Small because the decisive datum
    #: is the edge itself; the neighbours are there to show the approach to it.
    WINDOW = 12

    def _methods_for(self, uids: list[str]) -> list[str]:
        """The methods `covers` implicates for these requirements -- the slice."""
        out: list[str] = []
        for uid in uids:
            for m in self.covers.get(uid, []):
                if m not in out:
                    out.append(str(m))
        return out

    def focus(self) -> list[str]:
        """The requirements this turn can act on, in the order it should try.

        The analogue of `list_suspect_blocks`: derived from what is failing (or
        unexercised, on a stimulus turn), never from the whole set.
        """
        rows = self.failing() if self.route == MODEL else self.undecided()
        return [r.req_uid for r in rows]

    def board(self) -> dict:
        """Detail for what the turn can act on; one line for everything else.

        The `list_suspect_blocks` shape. That tool does not return block bodies
        -- it returns an entry per block (id, kind, trigger, line span) and the
        body arrives only when `read_block` asks for one. Summary in the list,
        detail on request.

        So `not_acting_on` NAMES every other requirement under its status rather
        than counting them. Counting alone was the wrong half to drop: the agent
        must know a requirement is already met before it edits the method that
        satisfies it, and a census cannot tell it which ones those are. Naming
        them costs ~12 B each -- 1.3 KB across the 104 of the last live run,
        against the ~40 KB the full records cost -- and every one stays one
        `explain(req_uid)` away.
        """
        rows = self.list_oracles()
        wanted = "NOT MET" if self.route == MODEL else "NOT EXERCISED"
        acting = [r for r in rows if r["status"] == wanted]
        shown = {r["req_uid"] for r in acting}
        rest: dict[str, list[str]] = {}
        for r in rows:
            if r["req_uid"] not in shown:
                rest.setdefault(r["status"], []).append(r["req_uid"])
        return {
            "this_turn_is_about": wanted,
            "acting_on": acting,
            "not_acting_on": {k: sorted(v) for k, v in sorted(rest.items())},
            "note": (
                f"{len(rows) - len(acting)} further oracle(s) are named above "
                f"without detail because this turn cannot act on them -- but "
                f"they are the ones an edit can BREAK. Read any of them in full "
                f"by name: explain(req_uid) or run_oracle(req_uid)."
            ) if len(rows) > len(acting) else "",
            "methods_to_look_at_first": self._methods_for(
                [r["req_uid"] for r in acting]),
        }

    def list_oracles(self) -> list[dict]:
        """Every finding the turn is working on, checked or not.

        Requirements whose oracle was discarded during screening used to be
        absent entirely, which made the loss of an oracle look like the loss of
        the finding. The verdict still blocks and it is still the judge's
        conclusion; all that changed is that nothing can decide it mechanically.
        Hiding it left the agent unable to act on it or to argue with it.
        """
        by_uid = {r.req_uid: r for r in self._results}
        out = []
        for oracle in self.oracles:
            r = by_uid.get(oracle.req_uid)
            out.append({
                "req_uid": oracle.req_uid,
                "clause": oracle.clause,
                "tp_uids": oracle.tp_uids,
                "status": ("broken" if r and r.broken else
                           "met" if r and r.ok else
                            "NOT EXERCISED" if r and r.unexercised() else "NOT MET"),
                "edge": None if r is None else r.edge,
                "detail": "" if r is None else (r.broken or r.detail),
                # What a SECOND implementation of the same requirement made of
                # this check, where it could not satisfy it either. Empty for
                # most. Not a verdict: see `witness_notes`.
                "a_second_implementation_also_fails_this": bool(
                    self.witness_notes.get(oracle.req_uid)),
                "checked": True,
            })
        have = {o.req_uid for o in self.oracles}
        for uid, verdict in sorted(self.verdicts.items()):
            if uid in have or verdict not in ("not_met", "ambiguous"):
                continue
            out.append({
                "req_uid": uid,
                "clause": str((self.reasons.get(uid) or {}).get("reason") or "")[:200],
                "tp_uids": [],
                "status": verdict.upper().replace("_", " "),
                "edge": None,
                "detail": self.ANECDOTAL,
                "checked": False,
            })
        return out

    def explain(self, req_uid: str) -> dict:
        """Everything needed to act on one finding, joined from five sources.

        Requirement text and spec spans, the judge's reasoning, the oracle's own
        source, the concrete stimulus, and the methods claimed to implement it.
        They live in four files; an agent asked to join them by hand spends its
        attempts doing that instead of debugging.

        The oracle SOURCE is included deliberately. An agent that can read what
        it must satisfy can tell a model defect from an over-strict oracle, and
        the second is a real possibility this design has to survive.
        """
        oracle = next((o for o in self.oracles if o.req_uid == req_uid), None)
        req = self.requirements.get(req_uid, {})
        if oracle is None:
            # A finding with no oracle is still a finding, and this is the only
            # place its reasoning can be read. Returning an error here made a
            # discarded oracle look like a mistyped uid, so an agent that saw
            # the verdict in `list_oracles` could not follow it up.
            if req_uid not in self.verdicts:
                return {"error": f"no such requirement {req_uid!r}",
                        "known": sorted(self.verdicts)}
            return {
                "req_uid": req_uid,
                "requirement": req.get("text", ""),
                "specification_quoted": [
                    s.get("quote", "") for s in (req.get("spec_spans") or [])
                ],
                "judge_verdict": self.verdicts.get(req_uid, ""),
                "judge_reasoning": self.reasons.get(req_uid, {}),
                "methods_claimed_to_implement_it": self.covers.get(req_uid, []),
                "oracle_clause": None,
                "oracle_source": None,
                "evidence_quality": self.ANECDOTAL,
                "current": {"status": "NO EXECUTABLE CHECK", "edge": None,
                            "detail": self.ANECDOTAL},
            }
        result = next((r for r in self._results if r.req_uid == req_uid), None)
        return {
            "req_uid": req_uid,
            "requirement": req.get("text", ""),
            "specification_quoted": [
                s.get("quote", "") for s in (req.get("spec_spans") or [])
            ],
            "judge_verdict": self.verdicts.get(req_uid, ""),
            "judge_reasoning": self.reasons.get(req_uid, {}),
            "methods_claimed_to_implement_it": self.covers.get(req_uid, []),
            "oracle_clause": oracle.clause,
            "oracle_source": oracle.source,
            # The one unbounded field here: an oracle naming three testpoints
            # carried three full step lists. Capped, and the cap says so.
            "stimulus": {
                tp: _steps_excerpt(self.stimulus_by_tp.get(tp, []), tp)
                for tp in oracle.tp_uids
            },
            "current": {
                "status": ("broken" if result and result.broken else
                           "met" if result and result.ok else
                           "NOT EXERCISED" if result and result.unexercised() else
                           "NOT MET"),
                "edge": None if result is None else result.edge,
                "detail": "" if result is None else (result.broken or result.detail),
            },
        }

    def run_oracle(
        self, req_uid: str, from_edge: int | None = None, rows: int | None = None
    ) -> dict:
        """Replay this requirement's scenario in isolation, windowed.

        Separate from `run_all` because isolation is how a wrong clock
        generation gets found: replay one scenario and read it edge by edge.

        THE WINDOW IS ANCHORED AT THE DECIDING EDGE, not at the head. Its own
        docstring used to argue that "a row budget sized for a prompt is the
        wrong budget for an agent that can ask twice" -- and then defaulted to
        `from_edge=0, rows=60` for EVERY testpoint the oracle names, which is
        the prompt-sized budget applied in the wrong direction. Measured on the
        i2c contract (17 ports): 228 B per row, so three testpoints cost 40 KB
        to reach an edge `OracleResult.edge` already knows.

        The agent can ask twice, so the default is the narrow one and both
        arguments still open it up: `from_edge=0, rows=10_000` is the old
        behaviour. Rows stay CONSECUTIVE either way -- `rtl_editor` keeps its
        mismatch rows consecutive from the first because "the skew detectors
        compare row i against row i-N, so a scattered sample destroys exactly
        the structure they exist to find", and a trace read with a hole in it is
        worse than a short trace for the same reason.

        The deciding testpoint is listed first, and every testpoint reports its
        `edges_total` and what was shown, so nothing is silently omitted.
        """
        oracle = next((o for o in self.oracles if o.req_uid == req_uid), None)
        if oracle is None:
            if req_uid in self.verdicts:
                return {"req_uid": req_uid,
                        "verdict": {"status": "NO EXECUTABLE CHECK",
                                    "edge": None, "detail": self.ANECDOTAL},
                        "testpoints": {},
                        "next": "call explain() for the judge's reasoning"}
            return {"error": f"no such requirement {req_uid!r}"}
        result = next((r for r in self._results if r.req_uid == req_uid), None)
        # THE ANCHOR. `result.edge` is where the oracle actually decided -- the
        # analogue of `fail_time` in `trace_report`, and the reason a narrow
        # window can be narrow without losing the decisive datum. With no
        # decision yet (unexercised, or never run) there is nothing to centre
        # on, so the window falls back to the head.
        decided_at = None if result is None else result.edge
        anchored = rows is None and from_edge is None and decided_at is not None
        span = self.WINDOW if rows is None else max(1, int(rows))
        if from_edge is not None:
            start = max(0, int(from_edge))
        elif decided_at is not None:
            start = max(0, int(decided_at) - self.WINDOW // 2)
        else:
            start = 0

        out: dict = {"req_uid": req_uid, "clause": oracle.clause,
                     "decided_at_edge": decided_at, "testpoints": {}}
        if anchored:
            out["window"] = (
                f"centred on edge {decided_at}, where this oracle decided. "
                f"Pass from_edge/rows to widen it.")
        # Deciding testpoint first: it is the one the verdict came from, and on
        # an oracle naming three it is the only one worth reading first.
        order = list(oracle.tp_uids)
        if result is not None and getattr(result, "tp_uid", None) in order:
            order.remove(result.tp_uid)
            order.insert(0, result.tp_uid)
        for tp in order:
            steps = self.stimulus_by_tp.get(tp)
            if not steps:
                out["testpoints"][tp] = {"error": "no stimulus recorded"}
                continue
            rep = replay(self.source, self.contract, steps, base=self.base)
            if rep.error:
                out["testpoints"][tp] = {"error": f"the model {rep.error}"}
                continue
            window = rep.rows[start:start + span]
            omitted = len(rep.rows) - len(window)
            entry = {
                "edges_total": len(rep.rows),
                "activity": _activity(rep.rows),
                "showing": f"{start}..{start + len(window) - 1}"
                           if window else "(none)",
                "notes": rep.notes,
                "trace": [
                    {"edge": r["edge"],
                     "in": {k: v for k, v in r["inputs"].items()},
                     "out": dict(r["outputs"])}
                    for r in window
                ],
            }
            # No silent caps (`rtl_editor.py:236-243`): a window that does not
            # say what it left out reads as the whole trace.
            if omitted > 0:
                entry["omitted"] = (
                    f"{omitted} further edge(s) not shown; call "
                    f"run_oracle({req_uid!r}, from_edge=..., rows=...) for any "
                    f"range of the {len(rep.rows)} recorded.")
            out["testpoints"][tp] = entry
        out["verdict"] = {
            "status": ("broken" if result and result.broken else
                       "met" if result and result.ok else
                       "NOT EXERCISED" if result and result.unexercised() else
                       "NOT MET"),
            "edge": None if result is None else result.edge,
            "detail": "" if result is None else (result.broken or result.detail),
        }
        return out

    def add_stimulus(self, req_uid: str, what_the_scenario_needs: str) -> dict:
        """Mint a NEW testpoint for a requirement whose oracle sees nothing.

        APPENDS. Nothing existing is edited, which is the `add_testcase`
        discipline (`testcase_agent.py:236-249`) rather than a new one, and it is
        what makes the operation safe to hand an agent whose objective is a lower
        failing count. The shortcut a mutable stimulus would open is real: make
        the scenario stop occurring and a VIOLATES becomes a NOT_EXERCISED.
        Appending cannot do that -- `_worst` (`oracles.py:373`) ranks failing
        above everything a new testpoint could add, so a grown evidence set only
        ever moves a verdict toward worse.

        Restricted to oracles currently reporting `ok=None`, mirroring
        `testcase_agent.gate` (`:191-198`): the target must already be reported
        unexercised, so it cannot be invented.

        The agent supplies INTENT, never steps. Vectors come from the injected
        generator and are gated before they are kept, so the agent cannot
        hand-write a step list the gate would reject.
        """
        # NO ROUTE CHECK. It used to refuse whenever `route != STIMULUS`, and
        # that was a SCHEDULING PREFERENCE implemented as a prohibition. The
        # preference is real and stays -- failing first, because a VIOLATES is
        # evidence that already exists and costs no model call to act on -- but
        # it belongs in the brief, which is where the turn is steered, not in a
        # refusal, which is where invariants live.
        #
        # The safety property the refusal looked like it was buying is already
        # structural and does not depend on it. This APPENDS: nothing existing
        # is edited, `_worst` ranks failing above everything a new testpoint
        # could add, and `distance` counts unexercised alongside failing -- so
        # a grown evidence set can only move a verdict toward WORSE. There is
        # no edit here that turns a VIOLATES into a NOT_EXERCISED.
        #
        # What it cost was measured: paired with `RefModelEditor.debug`
        # returning before the agent ran whenever nothing was failing, the two
        # conditions were mutually exclusive and this tool was unreachable in
        # five consecutive runs. The guard there is fixed too; this removes the
        # other half rather than leaving a route that opens only on the exact
        # turn the other half closes.
        #
        # Everything below stays, because all of it IS an invariant: a budget,
        # a target that must currently be unexercised so it cannot be invented,
        # a generator that must produce steps, and no byte-identical duplicate.
        if self.stimulus_gen is None:
            return {"error": "no stimulus generator is wired into this session"}
        if len(self.added) >= self.stimulus_budget:
            return {"error": f"stimulus budget spent ({self.stimulus_budget} "
                             f"testpoints added); the remaining unexercised "
                             f"requirements need a testplan fix, not more steps"}

        result = next((r for r in self._results if r.req_uid == req_uid), None)
        if result is None or not result.unexercised():
            state = "unknown" if result is None else (
                "failing" if result.failed() else
                "broken" if result.broken else "met")
            return {"error": f"{req_uid} is {state}, not unexercised. This tool "
                             f"only stages a scenario nothing currently reaches "
                             f"-- a failing oracle is a finding about the MODEL "
                             f"and adding stimulus cannot discharge it."}

        req = self.requirements.get(req_uid, {})
        try:
            steps = self.stimulus_gen(req, what_the_scenario_needs)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"stimulus generation failed: {exc!r}"}
        if not steps:
            return {"error": "the generator produced no steps"}

        # Byte-identical to something already present buys nothing and costs a
        # simulator process. `stimulus_diagnostics` already computes this key.
        key = json.dumps(steps, sort_keys=True)
        if any(json.dumps(v, sort_keys=True) == key
               for v in self.stimulus_by_tp.values()):
            return {"error": "identical to stimulus already in the suite"}

        uid = mint(PREFIX_TESTPLAN, next_index(
            [str(t.get("uid", "")) for t in self.testplan]
            + list(self.stimulus_by_tp), PREFIX_TESTPLAN))

        self.stimulus_by_tp[uid] = steps
        self.testplan.append({
            "uid": uid, "covers": [f"{req_uid}@1"],
            "stimulus": what_the_scenario_needs, "expected_response": "",
            "dimension": "D2_control_flow",
        })
        self.added.append(uid)

        attached = self._attach(uid, steps, requester=req_uid)
        self.refresh()
        after = next((r for r in self._results if r.req_uid == req_uid), None)
        return {
            "added": uid,
            "steps": len(steps),
            "attached_to": attached,
            "now": ("still NOT EXERCISED" if after and after.unexercised() else
                    "met" if after and after.ok else
                    "NOT MET -- the scenario now occurs and the model fails it"
                    if after else "unknown"),
            "budget_left": self.stimulus_budget - len(self.added),
        }

    def _attach(self, tp_uid: str, steps: list[dict],
                requester: str = "") -> list[str]:
        """Every requirement whose ACTIVATION this testpoint mechanically fires.

        Not just the one that asked. A newly generated WRITE testpoint genuinely
        stages WRITE, so any requirement needing WRITE is legitimately exercised
        by it, and scoping the testpoint to its requester would waste it.

        Not everything either: deciding an oracle against a scenario it was not
        written for is what measurement rejected -- on f-i2c that traded 1 true
        finding for 27 false ones. `check_static` draws the line without
        judgement, by reading which input-only activations the steps fire. A
        state-dependent activation cannot be matched this way and keeps its
        existing attachment, which is the honest limit rather than a gap.

        **THE REQUESTER IS ALWAYS ATTACHED, AND WITHOUT IT THE WHOLE ROUTE WAS
        INERT.** The loop above needs `activation.inputs` to run `check_static`
        at all, and a requirement without them was skipped -- including the one
        this testpoint was minted for, whose `covers` entry names it. So
        `add_stimulus` generated a scenario for a requirement and then declined
        to let that requirement see it.

        Measured, and it is the reason the stimulus route has never discharged
        anything: t-i2c added 48 testpoints across its turns and `NOT_EXERCISED`
        stayed at exactly 4; w-i2c and v-i2c spent the full 12-testpoint budget
        for the same nothing. Three of w-i2c's four unexercised requirements
        (`REQ-0005`, `REQ-0043`, `REQ-0050`) have no `activation.inputs`, so no
        new testpoint could ever reach them.

        The requester is the one attachment that needs no inference: the
        testpoint exists BECAUSE that oracle sees nothing, the generator was
        given that requirement's own text, and `add_stimulus` already refuses
        unless the target is currently unexercised. Appending is still safe --
        `_worst` ranks failing above anything a new testpoint can add.
        """
        hit: list[str] = []
        if requester:
            oracle = next((o for o in self.oracles if o.req_uid == requester), None)
            if oracle is not None and tp_uid not in oracle.tp_uids:
                oracle.tp_uids.append(tp_uid)
                hit.append(requester)
        for oracle in self.oracles:
            norm = self.normalized.get(oracle.req_uid)
            if not norm:
                continue
            act = (norm.get("activation") or {})
            if not act.get("inputs"):
                continue
            ob = Obligation(oracle.req_uid, act.get("text", ""),
                            dict(act["inputs"]), tuple(norm.get("observable") or ()))
            check = check_static(ob, steps, reset_ports=self.reset_ports)
            if check is not None and check.status == FIRED:
                if tp_uid not in oracle.tp_uids:
                    oracle.tp_uids.append(tp_uid)
                if oracle.req_uid not in hit:
                    hit.append(oracle.req_uid)
        return hit

    def read_model(self, method: str | None = None) -> str:
        """Line-numbered source of ONE method. No argument lists the methods.

        There is no read-the-whole-model form, and that is the point.
        `RTLEditor` has none either: `read_block` accepts only ids the backward
        slice produced and errors otherwise (`rtl_editor.py:611-614`), so the
        agent cannot pull the design into context because no tool will hand it
        over. This used to return the entire line-numbered model -- 10.1 KB on
        the i2c control -- to an agent that then paid to resend it on every
        subsequent call of the turn.

        Losing nothing: `covers` already names the methods claimed to implement
        each requirement, so the failing requirement points straight at the
        methods worth reading, and the listing below names the rest.
        """
        if method is None:
            names = _methods(self.source)
            focus = self._methods_for(self.focus())
            mark = "   <- claimed to implement a requirement this turn can act on"
            lines = [
                "The model defines these methods. Read one with "
                "read_model(method); the whole file is deliberately not "
                "available in one call.",
                "",
            ]
            lines += [f"  {n}{mark if n in focus else ''}" for n in names]
            return "\n".join(lines) + "\n"
        span = _method_span(self.source, method)
        if span is None:
            return (f"no method named {method!r}; the model defines: "
                    f"{', '.join(_methods(self.source))}")
        start, end = span
        lines = self.source.splitlines()
        return _numbered("\n".join(lines[start - 1:end]), start)

    def replace_method(self, method: str, new_code: str) -> dict:
        """Splice one method, then run the verification cascade.

        Addressed by NAME through the AST rather than by line range.
        `rtl_editor` slices blocks because Verilog offers no such handle; a
        Python model does, and `covers` already maps a requirement to the method
        names claimed to implement it, so a finding points straight at one.

        Cheapest-decisive-first, mirroring `_judge_replace_action_execution`:
        a splice that does not parse, or that breaks the mechanical G4 checks,
        is reverted without ever being scored -- those are defects in the edit,
        not evidence about the model.
        """
        if self.route != MODEL:
            return {"error": f"this turn's route is {self.route!r}: nothing is "
                             f"failing, so there is no model finding to act on "
                             f"and an edit made now would be unattributable. "
                             f"Stage a scenario with add_stimulus instead."}
        before = len(self.failing())
        span = _method_span(self.source, method)
        if span is None:
            return self._reject(method, before,
                                f"no method named {method!r}; the model defines: "
                                f"{', '.join(_methods(self.source))}")
        start, end = span
        lines = self.source.splitlines()
        body = _reindent(new_code, _indent_of(lines[start - 1]))
        candidate = "\n".join(lines[:start - 1] + body.splitlines() + lines[end:])
        if self.source.endswith("\n"):
            candidate += "\n"

        try:
            ast.parse(candidate)
        except SyntaxError as exc:
            return self._reject(method, before, f"the result does not parse: {exc}")
        if _method_span(candidate, method) is None:
            return self._reject(
                method, before,
                f"after the splice there is no method named {method!r} -- the "
                f"replacement must be the whole `def {method}(...)`",
            )

        issues = [
            i for i in validate_source(
                source=candidate, requirements=[], contract=self.contract,
                expected_base=self.base, workdir=self.workdir, coverage={},
            ) if i.severity == "error"
        ]
        if issues:
            return self._reject(
                method, before,
                "the mechanical checks reject it: "
                + "; ".join(f"{i.path}: {i.message}" for i in issues[:3]),
            )

        self.source = candidate
        self.refresh()
        after = len(self.failing())
        self.history.append(Edit(method, True, "accepted", before, after))
        return {
            "accepted": True,
            "failing_before": before,
            "failing_after": after,
            "still_failing": [r.req_uid for r in self.failing()],
            "note": _movement(before, after),
        }

    def _reject(self, method: str, before: int, reason: str) -> dict:
        self.history.append(Edit(method, False, reason, before, before))
        return {"accepted": False, "reason": reason, "failing": before}

    def run_all(self) -> dict:
        """Re-decide everything, plus the liveness question."""
        self.refresh()
        states = _distinct_output_states(
            self.source, self.contract, self.stimulus_by_tp, base=self.base)
        return {
            "failing": [
                {"req_uid": r.req_uid, "edge": r.edge, "detail": r.detail}
                for r in self.failing()
            ],
            "met": sum(1 for r in self._results if r.ok),
            "not_exercised": sum(1 for r in self._results if r.unexercised()),
            "not_met": len(self.failing()),
            "broken_oracles": [r.req_uid for r in self._results if r.broken],
            "distinct_output_states": states,
            "liveness": (
                "OUTPUTS NEVER MOVE -- a model whose outputs are constant "
                "satisfies nothing and discriminates no design from any other"
                if states == 1 else "outputs move"
            ),
        }


# ------------------------------------------------------------------ helpers


def _movement(before: int, after: int) -> str:
    if after < before:
        return f"{before - after} fewer failing"
    if after > before:
        return (f"{after - before} MORE failing -- this edit made things worse; "
                f"the session keeps the best version seen, but consider undoing it")
    return "no change in the failing count"


#: Steps shown per testpoint in `explain`. The agent asks for the rest by name.
STEPS_SHOWN = 12


def _steps_excerpt(steps: list[dict], tp: str) -> dict | list:
    """Head of a step list, saying what it left out.

    Never a sample across the list: stimulus is sequential and a scattered
    subset misrepresents the order things are driven in -- the same argument
    `rtl_editor` makes for keeping mismatch rows consecutive.
    """
    if len(steps) <= STEPS_SHOWN:
        return list(steps)
    return {
        "steps": list(steps[:STEPS_SHOWN]),
        "omitted": (
            f"{len(steps) - STEPS_SHOWN} of {len(steps)} steps not shown; "
            f"run_oracle(req_uid) replays {tp} in full."
        ),
    }


def _methods(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        n.name
        for cls in ast.walk(tree)
        if isinstance(cls, ast.ClassDef)
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _method_span(source: str, method: str) -> tuple[int, int] | None:
    """1-based inclusive line span of `method`, decorators included."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for node in cls.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == method):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                return start, int(node.end_lineno or node.lineno)
    return None


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _reindent(code: str, indent: str) -> str:
    """Put `code` at `indent`, whatever indentation it arrived with.

    A model handing back a method at column 0 is the common case and must not
    become a syntax error inside a class body.
    """
    lines = [ln for ln in code.strip("\n").splitlines()]
    if not lines:
        return indent
    base = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()), default=0)
    return "\n".join(
        (indent + ln[base:]) if ln.strip() else "" for ln in lines
    )


def _numbered(text: str, start: int) -> str:
    return "\n".join(
        f"{start + i:>4}: {line}" for i, line in enumerate(text.splitlines())
    )


def _distinct_output_states(
    source: str, contract: dict, stimulus_by_tp: dict, *, base: str
) -> int:
    """How many distinct output states any recorded stimulus produces.

    The inert-model check, over the stimulus this session actually has rather
    than a generic sweep. One state means the model answers everything the same
    way, which is how a reference model comes to certify nothing.
    """
    seen: set = set()
    for steps in list(stimulus_by_tp.values())[:8]:
        rep = replay(source, contract, steps, base=base)
        for row in rep.rows:
            seen.add(tuple(sorted(row["outputs"].items())))
        if len(seen) > 1:
            return len(seen)
    return len(seen)
