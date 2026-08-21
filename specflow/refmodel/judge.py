"""R2/R3: judge the reference model one requirement at a time.

The reference model is generated whole, because a model needs global context to
be coherent. Judging it does not: "does this model satisfy requirement N" is a
local question with a local answer, so this is where the fan-out belongs.

**The judge can block and cannot accept.** That asymmetry is the whole safety
argument, and it is what lets an LLM into a gate design whose founding rule is
that an LLM never certifies its own side's completeness:

* `not_met` and `ambiguous` are errors -- they block and drive a repair round;
* `met` certifies nothing. Acceptance still requires the script checks in
  `validate.py` and, ultimately, the cocotb suite against golden RTL.

So the judge can only **add obligations or raise doubts, never discharge one** --
the same monotonicity that makes `add_testcase` safe to hand an agent whose
objective is making things pass. A judge that is wrong in the permissive
direction costs nothing; one that is wrong in the strict direction costs a repair
round. That is the right way round.

**What `ambiguous` means.** Not "the specification is silent" -- that is
`underdetermined`, which the generator reports and which is a different thing
entirely. `ambiguous` means *the judge could not determine whether the
requirement is satisfied*, which covers both a requirement implemented
illegibly and a requirement not implemented at all. The judge does not know
which, so the remedy offers both branches and the generator picks. Wording it as
"explain why it is met" would presuppose correctness and invite a justifying
comment over absent behaviour -- the exact failure the asymmetry above exists to
contain, and not worth inviting even though it is contained.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from ..fanout import compose, json_block, shared_block
from ..model_io import ModelPort
from ..schema import Issue
from ..stage import run_fanout

STAGE = "judge"

Verdict = Literal["met", "not_met", "ambiguous"]

#: Verdicts that block. `met` is deliberately absent -- see the module docstring.
BLOCKING: frozenset[str] = frozenset({"not_met", "ambiguous"})


class RequirementVerdict(BaseModel):
    req_uid: str = ""
    verdict: Verdict = "ambiguous"
    #: Why the judge concluded what it did. Always present, including for `met`,
    #: because a reader auditing the model later needs the reasoning as much as
    #: the repair round does.
    reason: str = ""
    #: The methods and lines it read to decide. This is what makes a `not_met`
    #: actionable rather than an opinion.
    evidence: str = ""
    #: What the generator should change. Empty when met.
    remedy: str = ""

    @field_validator("reason", "evidence", "remedy", mode="before")
    @classmethod
    def _accept_a_list_of_lines(cls, v):
        """A model answering a free-text field with a list of lines is being
        reasonable, and rejecting it discards the whole verdict.

        This is the second time this shape has cost real verdicts. First
        `RefModelOutput.underdetermined` was typed dict-only and the model sent
        question strings, so 27 of 60 generation calls were re-asked for nothing
        else. Then `evidence` here was typed `str` and the model sent
        `["_sync_and_filter_step lines 4-9", "..."]` -- every one of the five
        `ambiguous` verdicts on the first live judging round was a parse error,
        not a judgement.

        Free-text fields take prose or a list of lines. There is no information
        in the distinction and nothing downstream reads it structurally.
        """
        if isinstance(v, (list, tuple)):
            return "; ".join(str(x) for x in v if str(x).strip())
        if v is None:
            return ""
        return v

    @property
    def blocks(self) -> bool:
        return self.verdict in BLOCKING


SYSTEM = """\
You check ONE requirement against a reference model someone else wrote.

The model is a Python class derived from a hardware specification. It is the
ORACLE a testbench will compare a design against, so a requirement it fails to
implement becomes a behaviour nobody ever verifies, and a requirement it
implements wrongly becomes a correct design marked as broken.

You are given the whole model, one requirement, the method names its author
claims implement that requirement, and -- when it could be produced -- an
<observed_behaviour> trace of the model actually running, plus the testpoints
the test plan wrote for this requirement.

The trace OUTRANKS the source. Source shows what the model was written to do;
the trace shows what it did. Where they disagree, the trace decides: code can
be structurally perfect and sit behind a condition that is never true, and a
requirement implemented in unreachable code is a requirement nobody verifies.
Before answering "met", find the steps of the trace where this requirement's
behaviour should be visible and check that it is. If the outputs never move at
all, no requirement about an output is met, whatever the source says.

The testpoints say what exercising this requirement looks like. They are prose,
and the trace is a GENERIC input sweep, not the testpoint's scenario -- so for
most requirements the exact scenario will NOT appear in the trace. That is
expected and is NOT a finding: absence of the scenario is not evidence of
anything, and must not by itself make a requirement "ambiguous". Where the
scenario is absent, judge from the source as you otherwise would.

Use the trace where it does bear:
  - outputs that CONTRADICT the requirement at a step where the relevant
    behaviour is visible -> "not_met", citing the step;
  - outputs that never move AT ALL across the whole trace -> "not_met" for any
    requirement about an output, whatever the source says. This case is always
    visible, needs no scenario, and is stated for you at the end of the trace.

Read those methods. Decide:

  "met"         the code satisfies the requirement. Say which lines do it.
  "not_met"     the code demonstrably does not satisfy it -- it does something
                else, or does nothing.
  "ambiguous"   you cannot determine whether it is satisfied.

On "ambiguous": this does NOT mean "probably met but unclear". It means you do
not know, and both possibilities are open -- the requirement may be implemented
in a way you cannot follow, or it may not be implemented at all. Do not guess
which. Say what you could not determine and why.

On the specification being vague: that is not your call and not this field. Judge
the code against the requirement as written. If the requirement itself is
unclear, that is `not_met` only if the code plainly fails every reading of it.

Your verdict CANNOT accept anything. "met" does not certify the model -- separate
mechanical checks and a simulation against real hardware do that. So there is no
value in being generous, and a wrong "met" simply wastes the one thing you were
asked for. Be exact.

Reply with ONE JSON object and nothing else:

{
  "verdict": "not_met",
  "reason": "the requirement demands cmd_ack pulse for exactly one cycle; \
_fsm sets cmd_ack and never clears it",
  "evidence": "_fsm lines 12-18: `o['cmd_ack'] = 1` with no reset on the \
following call",
  "remedy": "clear cmd_ack at the start of each step so it is high for one \
cycle only"
}
"""


def parse_response(text: str) -> RequirementVerdict:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return RequirementVerdict.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        # A verdict that will not parse is not a pass. Defaulting to `ambiguous`
        # keeps the failure inside the blocking set rather than letting a
        # malformed response through as silence.
        return RequirementVerdict(
            verdict="ambiguous",
            reason=f"Parse Error: {exc}",
            remedy="the judge's response could not be read; no conclusion was reached",
        )


# ------------------------------------------------------------------ prompting


def observed_behaviour(source: str, contract: dict, *, base: str) -> str | None:
    """Drive the model over the corner-first sweep and render what it DID.

    The judge was asked whether source code implements a requirement, and it
    answered from the code alone. That reads a claim, not a behaviour, and code
    can be structurally perfect and never reached. Measured on
    `i2c_master_bit_ctrl`: rounds 1, 2 and 3 each emitted exactly ONE output
    state across 64 vectors -- outputs that never move, an oracle that cannot
    discriminate any DUT from any other -- and the judge returned "met" on 77 of
    77 requirements for every one of them.

    The whole trace, not a summary. A requirement is about a particular moment
    ("on the eligible clk_en edge while idle the DUT accepts START"), so a
    judge reasoning about it needs the steps, not an aggregate over them. The
    distinct-state count is appended as a stated fact rather than left for the
    judge to derive by counting 64 rows.

    Rendered into the SHARED prefix, which is byte-identical across every
    requirement of a round, so this is sent once per round and cached for the
    remaining ~70 calls rather than repeated per requirement.

    Returns None when the model cannot be driven at all. That is not this
    function's failure to report: `_behavioural_checks` already blocks on it,
    and the judge does not run on a model with mechanical errors.
    """
    try:
        from ..ports import pinned_inputs
        from ..tb.render import default_stimulus

        namespace: dict = {}
        exec(compile(source, "<judge_trace>", "exec"), namespace)  # noqa: S102
        model_cls = namespace.get("Model")
        if model_cls is None:
            return None
        model = model_cls()
        fn = getattr(model, base, None)
        if not callable(fn):
            return None
        pinned = dict(pinned_inputs(contract))
        walk = [{**pinned, **v} for v in default_stimulus(contract)]
        if not walk:
            return None
        rows: list[str] = []
        states: set = set()
        for step, inputs in enumerate(walk):
            out = fn(dict(inputs))
            if not isinstance(out, dict):
                return None
            states.add(tuple(sorted((k, str(v)) for k, v in out.items())))
            rows.append(
                f"{step:>3}  "
                + " ".join(f"{k}={inputs[k]}" for k in sorted(inputs))
                + "  ->  "
                + " ".join(f"{k}={out[k]}" for k in sorted(out))
            )
    except Exception:  # noqa: BLE001 -- never let instrumentation fail a round
        return None

    verdict = (
        f"{len(states)} distinct output state(s) over {len(walk)} vectors."
        + (
            "  The outputs NEVER CHANGE. A reference model whose outputs never "
            "move agrees with whichever DUT is quietest and can discriminate no "
            "correct design from any wrong one, whatever its source says."
            if len(states) == 1
            else ""
        )
    )
    return (
        "Every step of the model driven over a corner-first input sweep.\n"
        "This is what the model DOES; the source above is only what it claims.\n"
        "step  inputs  ->  outputs\n"
        + "\n".join(rows)
        + f"\n\n{verdict}"
    )


def shared_prefix(
    source: str, contract_json: str, behaviour: str | None = None
) -> str:
    """Byte-identical across every requirement of one judging round.

    It contains the model source, which changes every repair round -- so unlike
    S1-S3, whose prefix is fixed for a whole node, this cache is cold at the
    start of each round and warms after two calls. With ~70 requirements per
    round that is still nearly all of them hitting; `cache_stats` reports it as a
    lower per-round rate rather than a defect.
    """
    # INVARIANT sections first, then the ones that change per round. Prefix
    # caching keeps a prefix only up to its first differing byte, so a block
    # that changes each repair round makes everything after it cold too.
    # `contract_json` is fixed for the whole node and was sitting AFTER the
    # model source: measured on i2c_master_bit_ctrl, that stranded 10.2 kB
    # behind a 7.9 kB block that changes every round, on all ~77 calls of every
    # round after the first. Ordering it ahead grows the cross-round warm head
    # from 3.5 kB to 13.7 kB and costs nothing.
    blocks = [
        ("system", SYSTEM),
        ("contract_json", contract_json),
        ("reference_model", source),
    ]
    if behaviour:
        blocks.append(("observed_behaviour", behaviour))
    return shared_block(*blocks)


#: Rows rendered per testpoint, counted AFTER run-length compression -- not
#: raw edges. The distinction decides what the judge actually sees.
#:
#: Measured by replaying this run's stimulus against the known-correct control
#: oracle, 60 testpoints: median 107 raw edges but a median of FOUR compressed
#: rows, because a prescaled design spends nearly every edge idle while the
#: divider counts down. Capping at 40 raw edges showed 22 of 60 scenarios in
#: full; capping at 40 compressed rows shows 55 of 60. Same budget, far more of
#: the scenario, because the compression drops only repetition.
#:
#: A raw-edge cap also truncates in the worst place. Stimulus now runs to a
#: median of 432 edges, so 40 edges is the opening ~9% -- the setup, ending
#: before the command it is meant to demonstrate ever completes.
_SCENARIO_ROWS = 40

#: Head and tail kept when a scenario exceeds the row budget. Completion is at
#: the END -- `cmd_ack` pulses when the command finishes -- so keeping only the
#: first rows preserves the setup and loses the outcome, which is the half a
#: requirement is usually about.
_SCENARIO_HEAD, _SCENARIO_TAIL = 25, 15

#: Hard bound on edges actually simulated, so an `until` that never resolves
#: cannot spin. Generous: this stimulus reaches 8008 edges on its longest
#: testpoint, and the point is to let `until` reach its real timeout rather
#: than stop early and imply the design never responded.
_SCENARIO_EDGE_BUDGET = 4000


def _rle(rows: list[tuple[str, str]]) -> list[str]:
    """Collapse consecutive identical edges, losslessly.

    A prescaled design spends most of a scenario waiting: of the 35 edges one
    START takes at clk_cnt=4, the great majority are byte-identical rows while
    the divider counts down. Sending all of them, for 3 testpoints across ~77
    requirements, measured 894 kB (~223k tokens) of uncacheable prompt per
    round against 146 kB for the prose alone.

    Nothing is dropped -- an identical row repeated N times becomes the same row
    with a count -- so the judge still sees every state the model passed through
    and how long it held, which is what a duration claim needs. The edge index
    of each run is kept so the trace can still be cited by step.
    """
    out: list[str] = []
    i = 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[i]:
            j += 1
        span = f"{i:>3}" if j == i else f"{i:>3}-{j}"
        held = "" if j == i else f"   (held {j - i + 1} edges)"
        out.append(f"{span}  {rows[i][0]}  ->  {rows[i][1]}{held}")
        i = j + 1
    return out


def scenario_trace(
    source: str, contract: dict, steps: list[dict], *, base: str
) -> list[str] | None:
    """Replay ONE testpoint's concrete stimulus against a fresh model.

    The generic sweep in `observed_behaviour` cannot contain a multi-cycle
    scenario -- it varies every input at every step, so on the real
    `i2c_master_bit_ctrl` contract the longest run that could advance the FSM is
    0, where one START needs ~26 edges. That is why the judge is told a missing
    scenario is not a finding.

    These steps are different: `run_suite_stimulus` writes them precisely to
    hold a command stable across the edges a design needs. Replayed here, the
    judge sees the model under the scenario its own testpoint describes, and
    "the requirement is not implemented" becomes a statement about behaviour
    under the right stimulus rather than about unexercised source.

    `normalise_step` is the testbench's own decoder, reused rather than
    reimplemented, so a replay cannot drift from what the suite will really do.
    `until` resolves against the MODEL here -- there is no DUT at this stage, and
    the model's own wait is what its trace should show.
    """
    try:
        from ..ports import pinned_inputs
        from ..tb.runtime import normalise_step

        namespace: dict = {}
        exec(compile(source, "<judge_scenario>", "exec"), namespace)  # noqa: S102
        model_cls = namespace.get("Model")
        if model_cls is None:
            return None
        fn = getattr(model_cls(), base, None)
        if not callable(fn):
            return None

        state = dict(pinned_inputs(contract))
        rows: list[tuple[str, str]] = []
        notes: list[str] = []
        simulated = 0
        for raw in steps:
            if notes:
                break
            inputs, hold, until, timeout = normalise_step(raw)
            state.update(inputs)
            # `until` runs to its REAL timeout. Capping it at the render budget
            # made a scenario stop early and read as one the model never
            # completed -- and 354 of this stimulus's steps are `until`, so that
            # was most of them. The edge budget only stops a runaway.
            edges = timeout if until else hold
            reached = False
            for _ in range(max(1, edges)):
                if simulated >= _SCENARIO_EDGE_BUDGET:
                    notes.append(
                        f"... stopped after {_SCENARIO_EDGE_BUDGET} edges")
                    break
                simulated += 1
                out = fn(dict(state))
                if not isinstance(out, dict):
                    return None
                rows.append((
                    " ".join(f"{k}={state[k]}" for k in sorted(state)),
                    " ".join(f"{k}={out[k]}" for k in sorted(out)),
                ))
                if until and out.get(str(until.get("port"))) == until.get("value"):
                    reached = True
                    break
            # An `until` that never fires is worth saying -- a trace that just
            # stops reads as one that finished -- but it must NOT be phrased as
            # a defect. Checked against the known-correct control oracle on this
            # run's own stimulus: 23 of 60 scenarios never fire, because the
            # stimulus picked a timeout too short for the prescaler it also
            # picked (`clk_cnt=200` with `timeout=500`, when one command at that
            # divider needs upwards of 1000 edges). Blaming the model there
            # would have the judge return `not_met` on correct behaviour, which
            # is the very failure this evidence exists to prevent.
            if until and not reached and not notes:
                notes.append(
                    f"... {until.get('port')} did not reach "
                    f"{until.get('value')!r} within the {edges} edges this "
                    f"testpoint allows. That may mean the model never gets "
                    f"there, or that the testpoint's own timeout is too short "
                    f"for the clock divider it selected -- the trace above "
                    f"shows which. Do not treat it as a defect on its own."
                )
    except Exception:  # noqa: BLE001 -- never let instrumentation fail a round
        return None
    return (_budget(_rle(rows)) + notes) or None


def _budget(lines: list[str]) -> list[str]:
    """Bound the trace by COMPRESSED rows, keeping both ends.

    Applied after `_rle`, so the budget is spent on distinct states rather than
    on repetition: median 4 rows from a median 107 edges on this stimulus.

    When it does overflow, the middle goes. Completion lives at the end -- the
    acknowledge pulses when the command finishes -- and a requirement is usually
    about whether that happened, so head-only truncation drops the half being
    judged. The elision says how many rows it covers, so the judge can see that
    a gap exists rather than reading two ends as adjacent.
    """
    if len(lines) <= _SCENARIO_ROWS:
        return lines
    dropped = len(lines) - _SCENARIO_HEAD - _SCENARIO_TAIL
    return [
        *lines[:_SCENARIO_HEAD],
        f"        ... {dropped} further state changes elided ...",
        *lines[-_SCENARIO_TAIL:],
    ]


#: Testpoints per requirement run 1 to 6, median 2, at ~1.1 kB each, and they
#: are the only part of this that cannot be cached -- the trace rides in the
#: shared prefix and is sent once per round. Unprojected and uncapped they added
#: 260 kB (~65k tokens) per round on `i2c_master_bit_ctrl`, which is a real cost
#: for context whose job is narrow: telling the judge which moment of the trace
#: bears on this requirement.
_TP_LIMIT = 3
#: `check_method` tells the TESTBENCH how to check, not the judge how to judge;
#: `dimension`, `needs`, `rev` and `covers` say nothing about the behaviour.
_TP_FIELDS = ("uid", "stimulus", "expected_response")


def _for_judge(
    testpoints: list[dict],
    *,
    source: str | None = None,
    contract: dict | None = None,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
) -> list[dict]:
    """Each testpoint as the judge should see it, with its replay when there is one.

    When the concrete stimulus exists the prose `stimulus` is dropped: the
    vectors ARE the stimulus, and the trace beneath them shows what the model
    did on exactly those vectors. `expected_response` stays either way -- that
    is the specification's claim, and it is what the trace has to be judged
    against.
    """
    out: list[dict] = []
    for tp in testpoints[:_TP_LIMIT]:
        entry = {k: tp[k] for k in _TP_FIELDS if k in tp}
        steps = (stimulus_by_tp or {}).get(str(tp.get("uid")))
        if steps and source and contract:
            rows = scenario_trace(source, contract, steps, base=base)
            if rows:
                entry.pop("stimulus", None)
                entry["model_run_on_this_testpoint_stimulus"] = rows
        out.append(entry)
    return out


def build_prompt(
    *,
    source: str,
    contract_json: str,
    requirement: dict,
    methods: list[str],
    issues: list[Issue] | None = None,
    previous: str | None = None,
    behaviour: str | None = None,
    testpoints: list[dict] | None = None,
    contract: dict | None = None,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
) -> str:
    parts = [
        json_block("requirement", requirement),
        "<claimed_methods>\n"
        + (", ".join(methods) if methods else "(none declared)")
        + "\n</claimed_methods>",
    ]
    # The testpoints S2 wrote for THIS requirement, which say what exercising it
    # looks like -- "present cmd=START and keep it stable through that clk_en
    # edge". Prose, not vectors: `testcase_agent` concretises these, and it runs
    # later, in the repair loop. Their value here is telling the judge which
    # moment of the trace above bears on the requirement it was asked about.
    if testpoints:
        parts.append(json_block(
            "testpoints_covering_this_requirement",
            _for_judge(testpoints, source=source, contract=contract,
                       stimulus_by_tp=stimulus_by_tp, base=base),
        ))
    return compose(shared_prefix(source, contract_json, behaviour), "\n\n".join(parts),
                   issues=issues, previous=previous)


# --------------------------------------------------------------------- issues


def to_issue(v: RequirementVerdict) -> Issue | None:
    """One `Issue` per blocking verdict, carrying the judge's whole reasoning.

    The feedback channel is the product here, not the verdict. A judge returning
    only pass/fail would be an expensive boolean, and the mechanical gates
    already produce better booleans for free. What this adds is a per-requirement
    statement of what is wrong and what to do about it, which is strictly more
    than G4 can say: `leaves ['cout'] unwritten on inputs {...}` reports that a
    port is free, not which requirement went unserved or why.
    """
    if not v.blocks:
        return None
    parts = [v.reason.strip() or "no reason given"]
    if v.evidence.strip():
        parts.append(f"evidence: {v.evidence.strip()}")
    if v.remedy.strip():
        parts.append(f"remedy: {v.remedy.strip()}")
    elif v.verdict == "ambiguous":
        # The two-branch remedy, supplied by the harness when the judge did not
        # phrase one. Deliberately NOT "explain why it is met": that presupposes
        # the code is right and steers the generator into justifying absent
        # behaviour instead of adding it.
        parts.append(
            "remedy: resolve this either way -- if the requirement is not "
            "implemented, implement it; if it is, make that legible with an "
            "inline comment at the implementation site saying how the code "
            "satisfies it"
        )
    return Issue("error", f"refmodel.{v.req_uid}.{v.verdict}", "; ".join(parts))


class JudgeResult(BaseModel):
    verdicts: list[RequirementVerdict] = Field(default_factory=list)

    @property
    def issues(self) -> list[Issue]:
        return [i for i in (to_issue(v) for v in self.verdicts) if i is not None]

    def counts(self) -> dict[str, int]:
        out = {"met": 0, "not_met": 0, "ambiguous": 0}
        for v in self.verdicts:
            out[v.verdict] = out.get(v.verdict, 0) + 1
        return out


# ----------------------------------------------------------------- the stage


def run_judge(
    *,
    source: str,
    contract_json: str,
    requirements: list[dict],
    covers: dict[str, list[str]],
    port: ModelPort,
    round_: int = 0,
    fanout: bool = True,
    contract: dict | None = None,
    base: str = "step",
    testplan: list[dict] | None = None,
    stimulus_by_tp: dict[str, list[dict]] | None = None,
) -> JudgeResult:
    """One small call per requirement, concurrent, over one frozen model.

    No repair loop of its own: the judge is asked once per round about a given
    model, and the *generator's* repair round is what changes anything. Re-asking
    the same judge about the same source would only resample its opinion, which
    is not evidence.
    """
    behaviour = (
        observed_behaviour(source, contract, base=base) if contract else None
    )
    # testpoint.covers holds "REQ-0007@1"; the revision is not part of the key.
    by_req: dict[str, list[dict]] = {}
    for tp in testplan or []:
        for ref in tp.get("covers") or []:
            by_req.setdefault(str(ref).split("@", 1)[0], []).append(tp)

    def one(req: dict) -> RequirementVerdict:
        uid = str(req.get("uid") or "")
        prompt = build_prompt(
            source=source, contract_json=contract_json, requirement=req,
            methods=list(covers.get(uid) or []),
            behaviour=behaviour, testpoints=by_req.get(uid),
            contract=contract, stimulus_by_tp=stimulus_by_tp, base=base,
        )
        raw = port.complete(stage=f"{STAGE}_{uid}", round_=round_, prompt=prompt)
        v = parse_response(raw)
        # The uid is the harness's to assign, never the judge's: a judge that
        # answered about the wrong requirement would otherwise silently retarget
        # its own verdict.
        return v.model_copy(update={"req_uid": uid})

    verdicts = (
        run_fanout(requirements, one) if fanout else [one(r) for r in requirements]
    )
    return JudgeResult(verdicts=verdicts)


def write_report(run_dir, result: JudgeResult) -> None:
    """Persist every verdict, including the passing ones.

    A `met` certifies nothing mechanically, but it is the record of what was
    examined and why it was thought fine -- which is exactly what someone
    auditing the oracle a month later needs, and it is free to keep.
    """
    from pathlib import Path

    out = Path(run_dir) / "specflow"
    out.mkdir(parents=True, exist_ok=True)
    (out / "refmodel_judge.json").write_text(
        json.dumps(
            {
                "counts": result.counts(),
                "blocking": sorted(v.req_uid for v in result.verdicts if v.blocks),
                "verdicts": [v.model_dump() for v in result.verdicts],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
