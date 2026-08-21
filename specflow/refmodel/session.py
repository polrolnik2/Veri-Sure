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
failing-oracle count seen, with `note_best`'s tie rule: the EARLIEST source
reaching a given count wins, so a run wandering across a plateau returns where
it first arrived rather than wherever it happened to stop.
"""

from __future__ import annotations

import ast
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .oracles import OracleResult, RequirementOracle, decide_all, replay
from .validate import validate_source


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
        workdir: Path | None = None,
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
        # `validate_source` writes a scratch copy so the exec has a filename;
        # it is not optional and the session must not scribble in the run dir.
        self.workdir = Path(workdir or tempfile.mkdtemp(prefix="refmodel-debug-"))

        self.history: list[Edit] = []
        self._results: list[OracleResult] = []
        self.best_source = source
        self.best_failing: int | None = None
        self.refresh()

    # ------------------------------------------------------------- state

    def refresh(self) -> list[OracleResult]:
        self._results = decide_all(
            self.oracles, self.source, self.contract,
            self.stimulus_by_tp, base=self.base,
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

    def note_best(self, source: str) -> bool:
        """Record `source` if it is the best seen. Ties do NOT overwrite.

        Semantics taken unchanged from `rtl_editor._EditSession.note_best`,
        whose tie rule is pinned by `tests/test_rollback_guard.py`.
        """
        count = len(self.failing())
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
            "stimulus": {
                tp: self.stimulus_by_tp.get(tp, []) for tp in oracle.tp_uids
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
        self, req_uid: str, from_edge: int = 0, rows: int = 60
    ) -> dict:
        """Replay this requirement's scenario in isolation, windowed.

        Separate from `run_all` because isolation is how a wrong clock
        generation gets found: replay one scenario and read it edge by edge. The
        window exists because the interesting edge is often past the head, and a
        row budget sized for a prompt is the wrong budget for an agent that can
        ask twice.
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
        out: dict = {"req_uid": req_uid, "clause": oracle.clause, "testpoints": {}}
        for tp in oracle.tp_uids:
            steps = self.stimulus_by_tp.get(tp)
            if not steps:
                out["testpoints"][tp] = {"error": "no stimulus recorded"}
                continue
            rep = replay(self.source, self.contract, steps, base=self.base)
            if rep.error:
                out["testpoints"][tp] = {"error": f"the model {rep.error}"}
                continue
            window = rep.rows[max(0, int(from_edge)):max(0, int(from_edge)) + max(1, int(rows))]
            out["testpoints"][tp] = {
                "edges_total": len(rep.rows),
                "activity": _activity(rep.rows),
                "showing": f"{from_edge}..{from_edge + len(window) - 1}"
                           if window else "(none)",
                "notes": rep.notes,
                "trace": [
                    {"edge": r["edge"],
                     "in": {k: v for k, v in r["inputs"].items()},
                     "out": dict(r["outputs"])}
                    for r in window
                ],
            }
        result = next((r for r in self._results if r.req_uid == req_uid), None)
        out["verdict"] = {
            "status": ("broken" if result and result.broken else
                       "met" if result and result.ok else
                       "NOT EXERCISED" if result and result.unexercised() else
                       "NOT MET"),
            "edge": None if result is None else result.edge,
            "detail": "" if result is None else (result.broken or result.detail),
        }
        return out

    def read_model(self, method: str | None = None) -> str:
        """Line-numbered source, whole or one method."""
        if method is None:
            return _numbered(self.source, 1)
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
