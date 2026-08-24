"""Write one requirement's oracle, from the requirement and nothing else.

Today the oracle is written by the JUDGE, in the same reply as its verdict, from
a prompt that carries the reference model's source (`judge.py:456`), the model
driven over a corner sweep (`:459`), and the model replayed under each
testpoint's concrete stimulus (`:665`). Three measurements say what that costs:

* On `a-i2c` the generated model passed 35 of 54 trusted oracles while the
  known-good control passed 25. A correct design scoring WORSE than the design
  under test, on checks meant to come from the specification, is what an oracle
  fitted to what it was shown looks like.
* On the same run 22 of 54 trusted oracles were failed by that control, and 10
  of the 18 findings the debug agent could not discharge were among them. It
  spent its attempts on demands no correct model can meet.
* Reading the implementation is HOW an oracle acquires implementation-specific
  demands. There is no prompt rule that survives having the answer in context;
  the ISSTA-2026 misguidance result is that presence in context is the cause,
  not intent.

So the oracle is generated here instead, before any verdict exists, from the
normalized requirement plus the contract's port list. Not "and is asked not to
look at the model" -- the model is not in the prompt, and
`tests/test_oracle_isolation.py` reads the constructed prompt back and asserts
it. That is the same enforcement `validate._static_checks` (`validate.py:40-70`)
already applies to RTL contamination of the reference model: a property of the
artifact, checkable by a script, rather than an instruction.

**`tp_uids` is assigned by the harness, not chosen by the model.** S2 already
recorded which testpoints cover which requirement, in `covers`, before any
oracle existed. Letting the generator choose instead means letting it choose
without having seen any stimulus -- and on `d-i2c` that failure was measured at
17 of 23 malformed oracles: 11 omitted `tp_uids` and 6 invented names no
testplan contains. Assigning it removes the whole class, and it keeps the
scoping that step 0 measured as load-bearing (deciding oracles outside their
named testpoints traded 1 true finding for 27 false ones).
"""

from __future__ import annotations

import json

from eda_agent.utils import extract_json_object, strip_markdown_code_fences
from pydantic import BaseModel

from ..fanout import compose, json_block, shared_block
from ..model_io import ModelPort
from ..schema import Issue
from ..stage import StageResult, run_fanout, run_stage
from .oracles import RequirementOracle, well_formed

STAGE = "oracle"

PARSE_ERROR = "Parse Error: "


class OracleOutput(BaseModel):
    reasoning: str = ""
    clause: str = ""
    source: str = ""


SYSTEM = """\
You write the DECISION PROCEDURE for one requirement: a small Python function
that decides mechanically whether a design honours it.

You are not judging anything. You have not been shown an implementation and you
will not be -- that is deliberate and it is the point of this stage. An oracle
written while looking at a design ends up encoding that design's choices, and
then a DIFFERENT correct design fails it. Measured on this pipeline: oracles
written that way were failed by a known-good reference implementation 41% of the
time, and the loop spent its repair budget on demands no correct design can
meet.

So write what the SPECIFICATION requires, not what any particular design does.
Where the specification leaves something open -- an exact cycle count it never
states, an encoding it does not fix -- your check must leave it open too.

You are given the requirement, the specification text it was drawn from, and its
normalized form:

  activation   WHEN the requirement applies
  observable   WHICH declared output ports the behaviour is visible on
  expectation  WHAT must then be true of them

Your oracle decides the `expectation` over the `observable`, at the moments the
`activation` holds.

    def decide(trace):
        # trace is a list of STATES, not of clock edges:
        #   {"index": int,      position in the sequence, 0, 1, 2, ...
        #    "held":  int,      how many clock edges this state lasted
        #    "inputs": {...}, "outputs": {...},
        #    "edge":  int}      the first clock edge of this state
        #
        # Consecutive edges with identical inputs AND outputs are one entry, so
        # trace[i+1] is THE NEXT DISTINCT STATE, not the next clock. That is
        # what a specification means by "then": the design may take any number
        # of edges to get there -- synchronisers, filters and prescaler dividers
        # all cost edges the spec does not fix -- and it is still correct.
        #
        # Walk the sequence. Use `index` to talk about order and `held` when the
        # requirement states a duration. Do not compute with `edge`; it is there
        # so a failure can be pointed at, not reasoned from.
        # Return (ok: bool | None, edge: int | None, detail: str).
        #
        # Return ok=None when THE ACTIVATION NEVER OCCURS in this trace -- no
        # START was issued, reset was never asserted, the arbitration case never
        # arose. Do NOT return False for that. False means you SAW the situation
        # and the design got it wrong, and it sends someone to fix code that may
        # be perfectly correct. Do NOT return True either: an oracle that passes
        # because it never looked is vacuous, and is discarded as such. ok=None
        # is the honest answer and costs you nothing -- it is routed to whoever
        # writes the stimulus, not counted against the design.

Rules, each for a reason:

  - Read only DECLARED PORTS out of `outputs` and `inputs`. Internal signals are
    not in the trace. An oracle naming none is rejected as deciding nothing.
  - NEVER look for a clock transition. Every row IS one rising clock edge, so
    the clock port is pinned at its idle value for the whole trace and carries
    no information. "the next rising edge" is simply the next row. An oracle
    hunting a 0->1 on the clock finds a flat line and reports that it cannot see
    its scenario -- which reads as a thin testplan when nothing is wrong.
  - Decide ONLY this requirement's clause. An oracle that also checks
    neighbouring behaviour is discarded for rejecting a correct design.
  - DO NOT DEMAND A RESPONSE AT A PARTICULAR EDGE. The comparison this feeds
    compares the ORDERED SEQUENCE of distinct output states and ignores how long
    each is held, so a design is not required to be cycle-accurate. Real designs
    put synchronisers, majority filters and prescaler dividers between an input
    event and the output that answers it, and every one of those costs edges the
    specification does not fix.

    So "busy rises at the edge the START appears" is wrong even when "busy rises
    after a START" is right, and "al is high at every edge the condition holds"
    is wrong even when "al goes high once the condition occurs" is right. Say
    THAT THE STATE IS REACHED, and where order matters say only that one state
    precedes another. Search forward for the state you expect; do not index a
    fixed edge, and do not require the response in the same row as its cause.

    Demand an exact count only when the requirement itself states one AND the
    specification text you were given says it -- "cmd_ack is high for exactly one
    clock" is a duration the spec fixes, and checking it is correct.

    Measured: 27 of 77 oracles written without this rule are failed by an
    implementation that scores 181/181 against golden RTL, and demanding a
    response too early is the single largest reason.
  - Return the EDGE your decision turns on, so a failure localises itself.
  - No imports, no file or network access.
  - It must FAIL a design that violates the clause and PASS one that honours it.
    It is checked both ways: against an implementation built from this same
    requirement, and against deliberately broken variants of it. An oracle
    nothing can falsify is discarded as demanding nothing.

Do NOT name testpoints. Which testpoints exercise this requirement was decided
by the test plan and is filled in for you.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "clause": "cmd_ack is high for exactly one clock when the command completes",
  "source": "def decide(trace):\\n    pulses = [r for r in trace if r['outputs']['cmd_ack']]\\n    if not pulses:\\n        return (None, None, 'cmd_ack never rose; the command never completed in this trace')\\n    bad = [r['held'] for r in pulses if r['held'] != 1]\\n    if bad:\\n        return (False, pulses[0]['edge'], f'cmd_ack held for {bad} edges, expected 1')\\n    return (True, None, f'{len(pulses)} single-edge pulse(s)')"
}
"""


def shared_prefix(contract_json: str, contract: dict) -> str:
    """Byte-identical across every requirement of one node.

    It contains the SYSTEM prompt, the contract and the port lists -- and
    deliberately nothing else. Everything that changes per round in the judge's
    prefix (the model source, its observed behaviour) is absent here, so unlike
    the judge's this prefix is warm for the whole node rather than cold at the
    start of every round.
    """
    ports = {
        "outputs": [
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "output" and p.get("name")
        ],
        "inputs": [
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "input" and p.get("name")
        ],
    }
    return shared_block(
        ("system", SYSTEM),
        ("contract_json", contract_json),
        ("declared_ports",
         json.dumps(ports, indent=2)
         + "\n\nThese are the only names that appear in a trace row. Anything "
           "else the requirement mentions is internal to the design and cannot "
           "be read."),
    )


def build_prompt(
    *,
    requirement: dict,
    contract_json: str,
    contract: dict,
    normalized: dict | None = None,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """Compose the prompt. There is no parameter that could carry a design.

    That is the structural half of invariant I1, and it is why this function
    takes a requirement rather than taking `**kwargs` or a context object: a
    later edit that wanted to pass the model source would have to add a
    parameter, which is a visible change to a signature rather than one more key
    in a dict.
    """
    parts = [json_block("requirement", requirement)]
    if normalized:
        parts.append(json_block("normalized", normalized))
    return compose(
        shared_prefix(contract_json, contract),
        "\n\n".join(parts),
        issues=issues,
        previous=previous,
    )


def parse_response(text: str) -> OracleOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return OracleOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return OracleOutput(reasoning=f"{PARSE_ERROR}{exc}")


def gate_one(
    out: OracleOutput,
    *,
    req_uid: str,
    tp_uids: list[str],
    contract: dict,
    testplan: list[dict],
    conforming_source: str = "",
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
) -> list[Issue]:
    """Screen the oracle before it costs anything downstream.

    Reuses `oracles.well_formed` unchanged rather than re-deriving a screen: an
    oracle is the same trust class as the reference model -- generated Python
    this process will execute -- and if that sandbox is not good enough for one
    it is not good enough for the other.

    **The must-pass leg.** With a conforming implementation supplied, the oracle
    is RUN against it and a failure is returned as a gate issue -- which puts
    over-strictness inside `run_stage`'s existing repair loop rather than
    discovering it a stage later, when the only remaining option is to discard
    the oracle and hand its requirement back as prose.

    That the loop already exists is the point: `run_stage` re-prompts with
    `gate_failures_block`, so the author is shown the exact edge and the exact
    detail its check tripped on. Measured on g-i2c, the dominant over-strictness
    is demanding a response at a fixed edge -- "busy low when START detected at
    edge 13" -- and that is a defect an author can act on when told, and cannot
    when merely discarded.

    A failure here is NOT proof the oracle is wrong: the conforming
    implementation is a second reading of the same requirement, not a golden
    model, so a disagreement could be either. The message says so, because an
    author told "you are wrong" will contort a correct check.
    """
    if out.reasoning.startswith(PARSE_ERROR):
        return [Issue("error", f"oracle.{req_uid}.response", out.reasoning)]
    if not out.clause.strip():
        return [Issue("error", f"oracle.{req_uid}.clause",
                      "no clause; say which sentence of the requirement this "
                      "decides, so a reader can tell an over-strict oracle from "
                      "a real defect")]
    oracle = RequirementOracle(req_uid=req_uid, tp_uids=list(tp_uids),
                               clause=out.clause, source=out.source)
    why = well_formed(oracle, contract, testplan)
    if why:
        return [Issue("error", f"oracle.{req_uid}.source", why)]

    if not conforming_source or not stimulus_by_tp:
        return []
    from . import trust

    result = trust._decide_over(  # noqa: SLF001
        oracle, conforming_source, contract, stimulus_by_tp, base=base)
    if not result.failed():
        # A pass, an unexercised scenario and a broken replay are all silence
        # here. Only a definite failure carries information, and reporting the
        # others would re-ask for reasons the author cannot act on.
        return []
    where = f" at edge {result.edge}" if result.edge is not None else ""
    return [Issue(
        "error", f"oracle.{req_uid}.over_strict",
        f"An independent implementation of this same requirement FAILS your "
        f"check{where}: {result.detail or '(no detail)'}. One of the two readings "
        f"is wrong and it may be either -- but a check no reading of the "
        f"requirement satisfies can never be discharged by anyone. If your check "
        f"pins a detail the specification leaves open -- which edge the response "
        f"lands on, an exact count the requirement does not state, an ordering "
        f"the text does not fix -- relax it to what the requirement actually "
        f"says. If you are confident the requirement does state it, keep the "
        f"check and say so in `reasoning`.")]


def run_oracle_gen(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    testplan: list[dict],
    port: ModelPort,
    normalized: dict[str, dict] | None = None,
    #: An implementation built from these same requirements, for the must-pass
    #: leg. NEVER the golden control: feeding a known-good design's behaviour
    #: back into oracle generation is the contamination I1 exists to prevent,
    #: and it would destroy `golden_check` as a held-out measure.
    conforming_source: str = "",
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
    max_repairs: int = 2,
    fanout: bool = True,
    #: `req_uid -> issues` seeding the FIRST prompt for that requirement, so a
    #: rejected oracle is re-asked with the reason it was rejected for. This is
    #: what gives the oracle stage the repair loop every other stage has: today
    #: a rejection is terminal because nothing ever re-asks.
    feedback: dict[str, list[Issue]] | None = None,
    #: Regenerate only these requirements. Scoped repair costs one call each,
    #: against 77 for a full pass.
    only: set[str] | None = None,
    #: Appended to the stage name so a LATER pass over the same requirement is
    #: recorded beside the first rather than on top of it. `model_io` keys every
    #: prompt/response pair by `{stage}_r{round}` and each `run_stage` call
    #: starts its rounds at zero, so a repair pass silently rewrites the record
    #: of the attempt it is repairing -- destroying both the oracle that was
    #: rejected and the prompt showing why, which is the evidence every
    #: measurement in this project is reconstructed from.
    label: str = "",
) -> tuple[list[RequirementOracle], dict[str, StageResult[OracleOutput]]]:
    """One oracle per requirement, generated before any verdict exists.

    `tp_uids` comes from the testplan's `covers`, never from the model. A
    requirement no testpoint covers gets no oracle: there would be nothing to
    replay it against, and an oracle naming no testpoint is discarded by
    `well_formed` anyway -- better to not spend the call.

    **Every oracle that has a source is returned, including one whose gate
    failed**, keyed results beside it. Dropping the failures here is what made 5
    of 77 requirements vanish on h-i2c into an `UNDECIDED` that also means
    "decided nothing" -- a silent subset, which is the failure mode the verdict
    enum exists to remove. Deciding what a gate-failing oracle IS belongs to the
    stage, which can record it; it does not belong to the generator, which can
    only forget it.
    """
    from ..obligation import by_requirement

    attached = by_requirement(testplan)
    wanted = [r for r in requirements if attached.get(str(r.get("uid") or ""))]
    if only is not None:
        wanted = [r for r in wanted if str(r.get("uid") or "") in only]
    seeds = feedback or {}

    def one(req: dict) -> StageResult[OracleOutput]:
        uid = str(req.get("uid") or "")
        tps = attached.get(uid, [])
        return run_stage(
            stage=f"{STAGE}_{uid or 'unknown'}{label}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt(
                requirement=req, contract_json=contract_json, contract=contract,
                normalized=(normalized or {}).get(uid),
                issues=issues or seeds.get(uid), previous=previous,
            ),
            parse=parse_response,
            gate=lambda out: gate_one(
                out, req_uid=uid, tp_uids=tps, contract=contract,
                testplan=testplan, conforming_source=conforming_source,
                stimulus_by_tp=stimulus_by_tp, base=base),
            max_repairs=max_repairs,
        )

    results = run_fanout(wanted, one) if fanout else [one(r) for r in wanted]
    by_uid: dict[str, StageResult[OracleOutput]] = {}
    oracles: list[RequirementOracle] = []
    for req, result in zip(wanted, results):
        uid = str(req.get("uid") or "")
        by_uid[uid] = result
        if not (result.output.source or "").strip():
            continue
        oracles.append(RequirementOracle(
            req_uid=uid,
            tp_uids=list(attached.get(uid, [])),
            clause=result.output.clause,
            source=result.output.source,
        ))
    return oracles, by_uid
