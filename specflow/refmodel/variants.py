"""Violating variants: the must-fail leg, derived from the requirement.

`qualify.py:3-22` already states the argument this step rests on: a suite can
cover every testpoint and still be unable to fail. A coverage bin is satisfiable
by stimulus alone -- reach the state, check nothing, bin green -- so anything
optimising for coverage writes stimulus and skips checks. A surviving variant
cannot be answered that way: killing it needs stimulus that REACHES the change
and a check that DISCRIMINATES it, both at once, so it cannot be gamed by
producing more of the cheap half.

**Why not `mutate_model` alone.** Gate 2 already mutates, and it stays -- a free
AST pass is the only affordable way to re-check a frozen oracle per turn against
a model the debug agent just edited. But its mutants come from the reference
model's SOURCE, so what they test is "does this oracle notice an edit to this
implementation", not "does this oracle notice a design that violates this
requirement". Those differ exactly where it matters: an implementation can be
wrong in ways no single-token edit reaches, and it can be edited in ways the
requirement does not care about. I4 asks for variants derived from the
requirement, and this is that.

**k is determined by the requirement, never picked.** One variant per clause
KIND the requirement actually contains -- a trigger and an action always, a
threshold only when the text states one. A requirement with one clause gets one
variant. Choosing k any other way would make the denominator an argument.

**What the variant author sees, and what it must not.** It sees the requirement,
the normalized form, the ports, and a conforming implementation -- because a
variant has to RUN, and the cheapest runnable violation of one clause is a
correct implementation with that clause broken. It does not see the oracle and
it does not see the tests: `build_prompt` has no parameter either could arrive
through, which is the same structural enforcement `oracle_gen.build_prompt`
uses for I1. That is the independence I4 is about. Independence from the
IMPLEMENTATION is not available and is not claimed -- a variant that shares no
code with any implementation is not a variant, it is a second design.

**Equivalent variants are dropped mechanically, not argued about.** A variant
whose trace, projected onto the ports the requirement is observable on, is
identical to the conforming implementation's has changed nothing this clause can
see. It leaves the denominator before any oracle is asked about it, which
subsumes the equivalent-mutant problem `qualify.py:67` names for G8 without an
LLM call.

**The must-fail leg only means anything after the must-pass leg.** An
over-strict oracle fails everything, variants included, and would look maximally
sensitive. `gate_one`'s must-pass leg runs first, inside oracle generation, so
by the time a variant is offered the oracle has already been shown to accept a
correct reading. Reading the two legs in the other order flatters exactly the
oracles that are worst.
"""

from __future__ import annotations

import re

from eda_agent.utils import extract_json_object, strip_markdown_code_fences
from pydantic import BaseModel

import json

from ..fanout import compose, json_block, shared_block
from ..model_io import ModelPort
from ..schema import Issue
from ..stage import StageResult, run_fanout, run_stage
from .oracles import (
    RequirementOracle,
    decide,
    ports_read,
    replay,
    transactional_view,
)
from .trust import CONVICTED, MIN_IN_SCOPE, SENSITIVE, UNKNOWN, _project
from .validate import _static_checks

STAGE = "variant"

PARSE_ERROR = "Parse Error: "

#: The three ways a clause can be broken. `trigger` and `action` are present in
#: every requirement by construction -- the normalized form has an activation
#: and an expectation -- so only `threshold` has to be detected.
TRIGGER = "trigger"
THRESHOLD = "threshold"
ACTION = "action"

#: What a threshold looks like in prose. Deliberately generous: proposing a
#: threshold variant for a requirement that has none costs one call and the
#: variant is then dropped as equivalent, while missing one that does costs the
#: only evidence that would have convicted a count-blind oracle.
_THRESHOLD = re.compile(
    r"\b\d+\b|\bat least\b|\bat most\b|\bmore than\b|\bfewer than\b|\bless than\b"
    r"|\bgreater\b|\bexceed\w*\b|\bwithin\b|\buntil\b|\bfor\s+\w+\s+cycles?\b"
    r"|\bone\b|\btwo\b|\bthree\b|\bfour\b|\beight\b|\bsixteen\b",
    re.IGNORECASE)

WHAT_EACH_KIND_MEANS = {
    TRIGGER: "make the behaviour happen at the wrong time -- fire when the "
             "activation does NOT hold, or stay silent when it does.",
    THRESHOLD: "get the boundary wrong -- off by one, the wrong comparison, "
               "the wrong count. Keep the shape of the behaviour intact.",
    ACTION: "do the wrong thing once activated -- the wrong value, the wrong "
            "port, the wrong duration.",
}


class VariantOutput(BaseModel):
    reasoning: str = ""
    #: The sentence of the requirement this variant breaks, verbatim.
    clause: str = ""
    #: A complete `Model`, correct in every other respect.
    source: str = ""


class Variant(BaseModel):
    req_uid: str = ""
    kind: str = ""
    clause: str = ""
    source: str = ""


SYSTEM = """\
You write a reference model that is WRONG, in one stated way, on purpose.

This is not sabotage and it is not a trick question. A check written for a
requirement is only worth keeping if something can fail it, and the only way to
find out is to build a design that violates the requirement and see whether the
check notices. You are building that design.

Rules.

1. Break the ONE clause you are told to break, in the ONE way you are told to
   break it. Everything else about the model stays correct.
2. The violation must be OBSERVABLE at the ports. A model that differs only in
   internal state is not a variant -- nothing can see it, so nothing can be
   asked to catch it.
3. Produce a complete, runnable model with the same class name, the same
   OUTPUT_PORTS, and the same method the conforming implementation defines.
   Start from that implementation and change what the clause requires changing.
4. Do not comment on the fact that it is wrong, do not add a `# BUG` marker, and
   do not leave the correct behaviour behind a flag. A variant that announces
   itself tests nothing.
5. Do not import anything outside `specflow`.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "one or two sentences on what you changed and why it violates the clause",
  "clause": "the sentence of the requirement this variant breaks, verbatim",
  "source": "the complete Python source of the violating model"
}
"""


def kinds_for(requirement: dict, normalized: dict | None = None) -> list[str]:
    """Which clause kinds this requirement actually contains.

    Returns `[TRIGGER, ACTION]` for a requirement that states no bound, plus
    `THRESHOLD` for one that does. Never empty: every requirement has something
    that makes it apply and something it then demands.
    """
    norm = normalized or {}
    act = (norm.get("activation") or {})
    text = " ".join(str(x) for x in (
        requirement.get("text") or requirement.get("statement") or "",
        act.get("text") or "",
        norm.get("expectation") or "",
    ))
    kinds = [TRIGGER, ACTION]
    if _THRESHOLD.search(text):
        kinds.insert(1, THRESHOLD)
    return kinds


def shared_prefix(contract_json: str, contract: dict,
                  conforming_source: str) -> str:
    """Byte-identical across every requirement and every kind of one node.

    The conforming implementation belongs HERE rather than in the per-item
    block: it is the same text for every variant of every requirement, so
    putting it in the item body would cost the stage its prefix cache on a body
    that never changes.
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
        ("declared_ports", json.dumps(ports, indent=2)),
        ("conforming_implementation", conforming_source),
    )


def build_prompt(
    *,
    requirement: dict,
    kind: str,
    contract_json: str,
    contract: dict,
    conforming_source: str,
    normalized: dict | None = None,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """Compose the prompt. There is no parameter an ORACLE could arrive through.

    Same structural enforcement as `oracle_gen.build_prompt`, aimed at the other
    invariant: I4 asks that a variant not be written against the check that will
    be asked to catch it, and a named signature makes slipping one in a visible
    change to a function rather than one more key in a dict.
    """
    parts = [
        json_block("requirement", requirement),
        f"BREAK THIS CLAUSE KIND: {kind}\n{WHAT_EACH_KIND_MEANS.get(kind, '')}",
    ]
    if normalized:
        parts.append(json_block("normalized", normalized))
    return compose(
        shared_prefix(contract_json, contract, conforming_source),
        "\n\n".join(parts),
        issues=issues,
        previous=previous,
    )


def parse_response(text: str) -> VariantOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return VariantOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return VariantOutput(reasoning=f"{PARSE_ERROR}{exc}")


def gate_one(
    out: VariantOutput,
    *,
    req_uid: str,
    kind: str,
    contract: dict,
    conforming_source: str,
    steps: list[dict],
    observable: set[str],
    base: str = "step",
) -> list[Issue]:
    """A variant must run, and it must be VISIBLY different. Nothing else.

    It is deliberately not checked for being wrong in the way it was asked to be
    wrong: that judgement would need an oracle, and an oracle is the thing this
    variant exists to test. What can be checked without one is that the design
    exists, executes, and moves something the requirement is about -- and a
    variant that fails the last test is equivalent, which is a real answer
    rather than a defect.
    """
    if out.reasoning.startswith(PARSE_ERROR):
        return [Issue("error", f"variant.{req_uid}.{kind}.response", out.reasoning)]
    # The same sandbox screen the reference model gets: a variant is generated
    # Python this process will execute. `requirements=[]` because a variant
    # carries no coverage map -- it is one design, not an answer to a fan-out.
    broken = [i for i in _static_checks(out.source, [])
              if i.severity == "error"]
    if broken:
        return [Issue("error", f"variant.{req_uid}.{kind}.source",
                      "; ".join(i.message for i in broken))]

    run = replay(out.source, contract, steps, base=base)
    if run.error:
        return [Issue("error", f"variant.{req_uid}.{kind}.replay",
                      f"the variant {run.error}; it must be a model that runs, "
                      f"not a sketch")]
    if not observable:
        return []
    reference = replay(conforming_source, contract, steps, base=base)
    if reference.error:
        return []                # nothing to compare against; not its fault
    if _project(run.rows, observable) == _project(reference.rows, observable):
        return [Issue(
            "error", f"variant.{req_uid}.{kind}.equivalent",
            f"this variant produces exactly the same "
            f"{', '.join(sorted(observable))} as the conforming implementation, "
            f"so nothing at the ports can tell them apart. Change what the "
            f"requirement is about, at a port a test can watch.")]
    return []


def run_variant_gen(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    conforming_source: str,
    stimulus_by_tp: dict[str, list[dict]],
    tp_by_req: dict[str, list[str]],
    port: ModelPort,
    normalized: dict[str, dict] | None = None,
    observable_by_req: dict[str, set[str]] | None = None,
    base: str = "step",
    max_repairs: int = 1,
    fanout: bool = True,
) -> tuple[list[Variant], list[StageResult[VariantOutput]]]:
    """k variants per requirement, generated once, from requirement text.

    A requirement with no conforming implementation to start from, or with no
    stimulus to run against, gets none: there would be nothing to demonstrate
    the violation on, and paying a call to find that out is waste.
    """
    if not conforming_source:
        return [], []

    norm = normalized or {}
    obs = observable_by_req or {}
    jobs: list[tuple[dict, str, list[dict], set[str]]] = []
    for req in requirements:
        uid = str(req.get("uid") or "")
        steps = next((stimulus_by_tp[tp] for tp in tp_by_req.get(uid, [])
                      if stimulus_by_tp.get(tp)), None)
        if not steps:
            continue
        watch = obs.get(uid) or set(norm.get(uid, {}).get("observable") or [])
        for kind in kinds_for(req, norm.get(uid)):
            jobs.append((req, kind, steps, watch))

    def one(job: tuple[dict, str, list[dict], set[str]]
            ) -> StageResult[VariantOutput]:
        req, kind, steps, watch = job
        uid = str(req.get("uid") or "")
        return run_stage(
            stage=f"{STAGE}_{uid or 'unknown'}_{kind}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt(
                requirement=req, kind=kind, contract_json=contract_json,
                contract=contract, conforming_source=conforming_source,
                normalized=norm.get(uid), issues=issues, previous=previous,
            ),
            parse=parse_response,
            gate=lambda out: gate_one(
                out, req_uid=uid, kind=kind, contract=contract,
                conforming_source=conforming_source, steps=steps,
                observable=watch, base=base),
            max_repairs=max_repairs,
        )

    results = run_fanout(jobs, one) if fanout else [one(j) for j in jobs]
    variants = [
        Variant(req_uid=str(req.get("uid") or ""), kind=kind,
                clause=result.output.clause, source=result.output.source)
        for (req, kind, _steps, _watch), result in zip(jobs, results)
        if result.ok
    ]
    return variants, results


def must_fail(
    oracle: RequirementOracle,
    variants: list[Variant],
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str = "step",
    transactional: bool = False,
) -> tuple[str, str]:
    """`(verdict, detail)` -- does this oracle catch a design that violates it?

    Same three outcomes as gate 2 and the same reason for the third: silence
    from an oracle that was shown too little is not vacuity. `MIN_IN_SCOPE`
    transfers unchanged -- one observation is not evidence.
    """
    mine = [v for v in variants if v.req_uid == oracle.req_uid and v.source]
    if not mine:
        return UNKNOWN, "no variant was generated for this requirement"

    steps = next((stimulus_by_tp[tp] for tp in oracle.tp_uids
                  if stimulus_by_tp.get(tp)), None)
    if not steps:
        return UNKNOWN, "no stimulus to run a variant against"

    ports = ports_read(oracle, contract)
    if not ports:
        return UNKNOWN, "the oracle reads no declared port"

    in_scope = 0
    for variant in mine:
        run = replay(variant.source, contract, steps, base=base)
        if run.error:
            continue
        in_scope += 1
        rows = transactional_view(run.rows) if transactional else run.rows
        if decide(oracle, rows).failed():
            return SENSITIVE, f"caught the {variant.kind} variant"
    if in_scope < min(MIN_IN_SCOPE, len(mine)):
        return UNKNOWN, (f"only {in_scope} variant(s) ran; silence over fewer "
                         f"than the requirement's own clauses is not vacuity")
    return CONVICTED, (f"passed all {in_scope} variant(s) of its own "
                       f"requirement, including one that breaks the clause "
                       f"it names")


def save(variants: list[Variant], path) -> None:
    """Written once beside the frozen oracles, and for the same reason.

    A variant regenerated on the next turn would be a different counterexample,
    so an oracle could be convicted of vacuity by silence about a design it was
    never shown. The must-fail leg is only evidence if the thing it fails to
    catch holds still.
    """
    from pathlib import Path

    path = Path(path)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"variants": [v.model_dump() for v in variants]},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def load(path) -> list[Variant]:
    from pathlib import Path

    path = Path(path)
    if not path.exists():
        return []
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Variant.model_validate(v) for v in (blob.get("variants") or [])]
