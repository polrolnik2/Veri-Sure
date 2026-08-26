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
from pydantic import BaseModel, Field

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
)
from .slicer import splice_methods
from .trust import (CONVICTED, MIN_IN_SCOPE, SENSITIVE, UNKNOWN, _difference,
                    _steps_for,
                    _decide_over, _project)
from .validate import _static_checks

STAGE = "variant"

PARSE_ERROR = "Parse Error: "

#: The ways a clause can be broken. `trigger` and `action` are present in every
#: requirement by construction -- the normalized form has an activation and an
#: expectation -- so the others have to be detected from the text.
TRIGGER = "trigger"
THRESHOLD = "threshold"
ACTION = "action"
#: The right values in the wrong sequence, and the right sequence held for the
#: wrong length. Added because the first three were not enough, and the gap was
#: measured rather than guessed at.
#:
#: A generated model scoring 30/168 against golden RTL differs from a
#: known-good control on 134 of 167 testpoints IN THE TRANSACTIONAL VIEW the
#: oracles decide over, and 36 of 56 trusted oracles assert on a port that
#: diverges in a testpoint they name. Two of them notice. The checks are live,
#: on-target, non-vacuous, watching the right ports -- and satisfied by both
#: designs, because "cmd_ack pulses" holds for a design that pulses it at the
#: wrong time.
#:
#: Characterised per (testpoint, port), that divergence is 636 duration, 186
#: value, 171 order -- `ACTION` covers only the value column.
#:
#: ORDER is the larger lever of the two and DURATION the smaller, which the
#: per-port tally overstates: at TESTPOINT granularity only 14 of the 148
#: diverging testpoints differ by duration alone, the other 134 differing in a
#: way the state sequence already shows. Duration is added anyway because a
#: requirement that states a length ("a one-clock pulse") is entitled to a
#: check that enforces it, and 13 of these 77 requirements state one.
ORDER = "order"
DURATION = "duration"

#: What a threshold looks like in prose. Deliberately generous: proposing a
#: threshold variant for a requirement that has none costs one call and the
#: variant is then dropped as equivalent, while missing one that does costs the
#: only evidence that would have convicted a count-blind oracle.
_THRESHOLD = re.compile(
    r"\b\d+\b|\bat least\b|\bat most\b|\bmore than\b|\bfewer than\b|\bless than\b"
    r"|\bgreater\b|\bexceed\w*\b|\bwithin\b|\buntil\b|\bfor\s+\w+\s+cycles?\b"
    r"|\bone\b|\btwo\b|\bthree\b|\bfour\b|\beight\b|\bsixteen\b",
    re.IGNORECASE)

#: Ordering language. Generous for the reason `_THRESHOLD` is: proposing one
#: for a requirement that states no ordering costs a call and the variant is
#: dropped as equivalent, while missing one that does costs the only evidence
#: that would convict an order-blind check.
_ORDER = re.compile(
    r"\bthen\b|\bafter\b|\bbefore\b|\bfollowed by\b|\bwhile\b|\bduring\b"
    r"|\bsequence\b|\border(?:ing|ed)?\b|\bfirst\b|\bnext\b|\bfinally\b"
    r"|\buntil\b|\bonce\b|\bprior to\b|\bsubsequent\b|\bphase\b",
    re.IGNORECASE)

#: Duration language, including the shapes that state a length without a number
#: -- "a one-clock pulse", "remains set", "single-cycle".
_DURATION = re.compile(
    r"\bpulse\b|\bone[- ]clock\b|\bone[- ]cycle\b|\bsingle[- ]cycle\b"
    r"|\bfor\s+\w+\s+(?:clock|cycle|edge)s?\b|\bremains?\b|\bstays?\b"
    r"|\bheld?\b|\bholding\b|\bcontinuous(?:ly)?\b|\bthroughout\b"
    r"|\buntil\b|\bwidth\b|\bduration\b",
    re.IGNORECASE)

WHAT_EACH_KIND_MEANS = {
    TRIGGER: "make the behaviour happen at the wrong time -- fire when the "
             "activation does NOT hold, or stay silent when it does.",
    THRESHOLD: "get the boundary wrong -- off by one, the wrong comparison, "
               "the wrong count. Keep the shape of the behaviour intact.",
    ACTION: "do the wrong thing once activated -- the wrong value, the wrong "
            "port, the wrong duration.",
    ORDER: "produce the RIGHT VALUES IN THE WRONG SEQUENCE. Every value the "
           "requirement calls for still appears on every port it names, and "
           "the order they appear in is wrong -- swap two phases, drive the "
           "second before the first, release a line before pulling the other "
           "one low. A check that only asks WHETHER each value appeared will "
           "still pass this; that is the point of it.",
    DURATION: "hold the right values, in the right order, FOR THE WRONG "
              "LENGTH. Stretch a one-edge pulse across several, or collapse a "
              "phase that should persist into a single edge. Do not change "
              "which values appear or the order they appear in.",
}


class VariantOutput(BaseModel):
    reasoning: str = ""
    #: The sentence of the requirement this variant breaks, verbatim.
    clause: str = ""
    #: The CHANGED METHODS only, `name -> the whole def`. Spliced onto the
    #: conforming implementation to produce `source`.
    #:
    #: Emitting the whole module cost 32% of a2-i2c's output tokens -- 948k over
    #: 185 calls -- to re-type a median 283 of 289 unchanged code lines. And the
    #: saving is the smaller half: naming the methods BOUNDS THE BLAST RADIUS.
    #: A variant that rewrites five methods now has to say so, where before it
    #: was visible only by diffing against the witness after the fact.
    methods: dict[str, str] = Field(default_factory=dict)
    #: A complete `Model`, correct in every other respect. Built by splicing
    #: `methods`; still accepted verbatim, because a variant that genuinely has
    #: to restructure the model should not be forced to lie about it in patches.
    source: str = ""
    #: Why the splice failed, if it did. Carried rather than raised so the
    #: repair loop gets it as an Issue -- a failed splice is the most actionable
    #: feedback this stage produces: mechanical, exact, and not a judgement.
    splice_error: str = ""


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
3. SEND ONLY THE METHODS YOU CHANGE, not the whole model. Each one is the
   complete `def name(self, ...)` including its body, and it is spliced onto
   the conforming implementation by NAME -- so everything you do not send stays
   exactly as it is, which is what rule 1 asks for. A method the conforming
   implementation does not define is ADDED, so a helper or a new piece of state
   is available to you; put new instance attributes in the method that already
   initialises the others.
4. Do not comment on the fact that it is wrong, do not add a `# BUG` marker, and
   do not leave the correct behaviour behind a flag. A variant that announces
   itself tests nothing.
5. Do not import anything outside `specflow`.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "one or two sentences on what you changed and why it violates the clause",
  "clause": "the sentence of the requirement this variant breaks, verbatim",
  "methods": {
    "_tick": "def _tick(self, i):\n    ...the whole method, changed...",
    "step":  "def step(self, i):\n    ...only if you changed this one too..."
  }
}

Fewer methods is better, and the smallest change that breaks the clause
observably is the right one. Sending the whole module instead of `methods` WILL
BE REJECTED: rule 1 asks that everything else stay correct, and the only way to
show that is to not re-type it.
"""


def kinds_for(requirement: dict, normalized: dict | None = None) -> list[str]:
    """Which clause kinds this requirement actually contains.

    Returns `[TRIGGER, ACTION]` for a requirement that states nothing else,
    plus `THRESHOLD`, `ORDER` and `DURATION` for one whose text does. Never
    empty: every requirement has something that makes it apply and something it
    then demands.

    Detected from the text rather than assumed, because a variant for a
    property the requirement does not state is one an oracle is RIGHT to
    ignore, and convicting it for that would be the over-strictness this whole
    stage is built to avoid causing.
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
    if _ORDER.search(text):
        kinds.append(ORDER)
    if _DURATION.search(text):
        kinds.append(DURATION)
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


def parse_and_splice(text: str, conforming_source: str) -> VariantOutput:
    """Parse, then build `source` from `methods` against the conforming model.

    Done at PARSE time rather than in the gate so the gate keeps receiving one
    thing -- a complete model -- and every check after it is unchanged. The
    splice is how the model's answer is READ, not a judgement about it.
    """
    out = parse_response(text)
    if out.source or not out.methods:
        return out              # emitted whole, or emitted nothing to splice
    spliced, errors = splice_methods(conforming_source, out.methods)
    if errors:
        return out.model_copy(update={"splice_error": "; ".join(errors)})
    return out.model_copy(update={"source": spliced})


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
    whole_module_ok: bool = False,
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
    if out.splice_error:
        return [Issue("error", f"variant.{req_uid}.{kind}.methods",
                      f"the changed methods could not be spliced onto the "
                      f"conforming model -- {out.splice_error}")]
    if not out.source:
        return [Issue("error", f"variant.{req_uid}.{kind}.methods",
                      "no `methods` and no `source`: there is no design here")]
    if not out.methods and not whole_module_ok:
        # ASKED FOR IN THE PROMPT IS NOT ENFORCED. The instruction to send only
        # changed methods landed in the live prompt and the model emitted the
        # whole module on 5 of 5 calls anyway, taking the escape clause every
        # time -- the same failure as `add_stimulus` asking an agent not to
        # repeat itself, and the reason I8 became a tool refusal instead of
        # prose. So the escape stays reachable and stops being free: it is
        # refused once, with the reason, and the repair round may take it.
        return [Issue("error", f"variant.{req_uid}.{kind}.methods",
                      "send `methods` -- the changed methods only, spliced onto "
                      "the conforming model by name -- not the whole module. "
                      "Everything you do not send stays exactly as it is, which "
                      "is what 'everything else about the model stays correct' "
                      "asks for. If this change truly cannot be written as whole "
                      "methods, send `source` again and it will be accepted.")]
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
        # One refusal, then the model's judgement stands. Counting here rather
        # than threading a round number through `run_stage` keeps the state
        # where the retries happen and out of the gate's signature.
        seen = {"n": 0}

        def gate(out: VariantOutput) -> list[Issue]:
            seen["n"] += 1
            return gate_one(
                out, req_uid=uid, kind=kind, contract=contract,
                conforming_source=conforming_source, steps=steps,
                observable=watch, base=base, whole_module_ok=seen["n"] > 1)

        return run_stage(
            stage=f"{STAGE}_{uid or 'unknown'}_{kind}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt(
                requirement=req, kind=kind, contract_json=contract_json,
                contract=contract, conforming_source=conforming_source,
                normalized=norm.get(uid), issues=issues, previous=previous,
            ),
            parse=lambda t: parse_and_splice(t, conforming_source),
            gate=gate,
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
    conforming: str = "",
) -> tuple[str, str, str]:
    """`(verdict, detail, counterexample)` -- does this oracle catch a design
    that violates it?

    `counterexample` is what the AUTHOR is told when this convicts, and it is
    empty for every other outcome. `detail` says the oracle passed N variants;
    it does not say what any of them DID, and until now nothing else did either
    -- `_repair_issue` sent "check the specific behaviour the clause states",
    which is what the author already tried.

    That is the same starvation `_strengthen` had, where it produced 0 of 72
    successes, one notch worse: adequacy at least quoted a line number. Measured
    on the rejected sets of s-i2c and r-i2c, reconstructed from `agent_io`,
    every vacuous oracle has a variant that differs from the conforming
    implementation at ports it READS -- 11 of 11 and 13 of 13, and in fact every
    variant of every one of them, 22 of 22 and 19 of 19 replays. There was
    always something to send.

    `conforming` is the implementation the variants were derived from. Without
    it there is no pair to diff and the counterexample is empty, which is why it
    defaults to "" rather than raising: a caller that has no conforming source
    still gets the verdict.

    Same three outcomes as gate 2 and the same reason for the third: silence
    from an oracle that was shown too little is not vacuity. `MIN_IN_SCOPE`
    transfers unchanged -- one observation is not evidence.

    **AN ORACLE THAT WAS NEVER TRIGGERED DID NOT PASS ANYTHING.** This used to
    convict on it, twice over, and both were the same conflation:

    * `decide(...).failed()` is False when the oracle PASSED the variant and
      equally False when the variant's trace never reached the clause's
      scenario. Only the first is vacuity; the second is a fact about the
      stimulus, and this module's siblings already refuse to reject on it --
      `verify_one` because "the scenario not being staged is the stimulus's
      business", `_decide_over` by keeping `unexercised()` distinct from
      `failed()`. Here `ok is None` was read as "did not catch it".
    * worse, the unexercised replay also counted toward `in_scope`, and
      `in_scope` is what satisfies `min(MIN_IN_SCOPE, len(mine))`. So the
      never-triggered replays were not merely miscounted, they were the
      evidence that licensed the conviction.

    Measured on the 11 `VACUOUS` requirements of w-i2c: of 22 variant replays,
    10 never triggered the oracle at all, and for the 6 that stayed vacuous
    through three re-authoring rounds the split was 6 genuinely passed, 6 never
    triggered, 0 caught. Roughly half the evidence behind those convictions was
    the stimulus, not the check.

    And it decides across EVERY testpoint the oracle names, via `_decide_over`,
    rather than replaying against `next(tp for tp in tp_uids if stimulus)`. The
    first named testpoint is not the only one, and `_decide_over` carries the
    measurement for why that matters -- an oracle unexercised on TP-A and
    decided on TP-B was being judged on TP-A alone.
    """
    mine = [v for v in variants if v.req_uid == oracle.req_uid and v.source]
    if not mine:
        return UNKNOWN, "no variant was generated for this requirement", ""

    if not any(stimulus_by_tp.get(tp) for tp in oracle.tp_uids):
        return UNKNOWN, "no stimulus to run a variant against", ""

    ports = ports_read(oracle, contract)
    if not ports:
        return UNKNOWN, "the oracle reads no declared port", ""

    in_scope = 0
    never = 0
    passed: Variant | None = None
    for variant in mine:
        held = _decide_over(oracle, variant.source, contract, stimulus_by_tp,
                            base=base, transactional=transactional)
        if held.broken:
            # The replay produced no usable verdict. Silence from a variant that
            # did not run says nothing either way, exactly as `run.error` did.
            continue
        if held.failed():
            return SENSITIVE, f"caught the {variant.kind} variant", ""
        if held.unexercised():
            never += 1
            continue
        in_scope += 1
        if passed is None:
            passed = variant          # the first one it let through
    if in_scope < min(MIN_IN_SCOPE, len(mine)):
        # Say WHICH kind of thin evidence it was: "the variants did not run" and
        # "the variants ran and never reached the scenario" route to different
        # owners, and reporting them identically is what hid this for so long.
        if never:
            return UNKNOWN, (
                f"{never} of {len(mine)} variant(s) never reached the scenario "
                f"this oracle decides, leaving {in_scope} real observation(s) "
                f"-- a stimulus finding, not vacuity"), ""
        return UNKNOWN, (f"only {in_scope} variant(s) ran; silence over fewer "
                         f"than the requirement's own clauses is not vacuity"), ""
    # WHY it passed, not just that it did. The three causes want different
    # owners, and "passed all N variant(s)" named none of them.
    label, why = why_passed(oracle, passed, conforming, contract,
                            stimulus_by_tp, ports, base=base)
    if label == "no-discrimination":
        # Not vacuity. No check over these ports could have told the designs
        # apart, so convicting this one blames the author for the requirement.
        return UNKNOWN, why, ""
    detail = (f"passed all {in_scope} variant(s) of its own requirement, "
              f"including one that breaks the clause it names")
    if why:
        detail = f"{detail} -- {why}"
    return CONVICTED, detail, _apart(oracle, passed, conforming, contract,
                                     stimulus_by_tp, ports, base=base)


class _Watched(dict):
    """One trace row that records having been read.

    The oracle is free-form Python and returns a single deciding `edge`, which
    is `None` exactly when it abstained -- so nothing in the artifact says which
    rows it LOOKED AT. Handing `decide` a list of these recovers that: any read
    of a row marks its index, and the set of marks is the window the check
    actually examined.
    """

    __slots__ = ("_seen", "_idx")

    def __init__(self, data: dict, seen: set, idx: int) -> None:
        super().__init__(data)
        self._seen, self._idx = seen, idx

    def __getitem__(self, key):
        self._seen.add(self._idx)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._seen.add(self._idx)
        return super().get(key, default)


def _examined(oracle: RequirementOracle, rows: list[dict]) -> set[int]:
    """Row indices this oracle read while deciding. Never raises."""
    seen: set[int] = set()
    try:
        decide(oracle, [_Watched(r, seen, i) for i, r in enumerate(rows)])
    except Exception:  # noqa: BLE001
        return seen
    return seen


def _diverging(a: list[dict], b: list[dict], ports: set[str]) -> list[int]:
    """Row indices where two traces disagree on the ports this oracle reads."""
    out: list[int] = []
    for i in range(min(len(a), len(b))):
        pa = (a[i].get("outputs") or {})
        pb = (b[i].get("outputs") or {})
        if any(pa.get(p) != pb.get(p) for p in ports):
            out.append(i)
    out.extend(range(min(len(a), len(b)), max(len(a), len(b))))
    return out


def _span(idx: list[int] | set[int]) -> str:
    idx = sorted(idx)
    return f"{idx[0]}-{idx[-1]}" if idx else "none"


def why_passed(oracle: RequirementOracle, variant: Variant, conforming: str,
               contract: dict, stimulus_by_tp: dict, ports: set[str], *,
               base: str = "step") -> tuple[str, str]:
    """`(label, detail)` -- WHY did this oracle pass a design built to break it?

    "Passed all N variants" stops at the symptom, and the three causes want
    different owners. Comparing where the variant DIFFERS on the ports this
    oracle reads against the rows the oracle actually READ separates them:

      differs inside the window   the check looked and did not care -- vacuous
      differs outside the window  it looked in the wrong place -- REPAIRABLE,
                                  and the author is told both ranges
      differs nowhere             no check over these ports could discriminate;
                                  a specification finding, not an oracle defect

    Measured on a2-i2c, where 14 oracles all reported "passed all N variant(s)"
    and the artifact could not tell REQ-0092 -- which checks `sda_oen` against
    `din` during the `cmd==8` command-issue window while the FSM drives SDA tens
    of edges later -- from REQ-0063, "the two-stage capture reduces metastability
    risk", which no functional replay can observe at any port ever.

    EDGES OBSERVED, NEVER A CYCLE COUNT. Phases 3-6 stopped `latency_cycles`
    gating because the specification does not pin cycle counts, and this reports
    where two traces were seen to differ rather than asserting when anything
    ought to happen.
    """
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps or not conforming or variant is None:
        return "", ""
    good = replay(conforming, contract, steps, base=base)
    bad = replay(variant.source, contract, steps, base=base)
    if good.error or bad.error:
        return "", ""
    diverged = _diverging(good.rows, bad.rows, ports)
    if not diverged:
        return "no-discrimination", (
            f"no variant differs from the conforming design at any port this "
            f"oracle reads ({', '.join(sorted(ports))}), so no check over those "
            f"ports could tell them apart -- a specification finding rather "
            f"than a defect in this check")
    looked = _examined(oracle, bad.rows)
    if looked & set(diverged):
        return "vacuous", (
            f"the designs differ at edge(s) {_span(diverged)}, which this check "
            f"read, and it passed both anyway")
    return "window-missed", (
        f"the designs differ at edge(s) {_span(diverged)}; this check only read "
        f"edge(s) {_span(looked)}. It is looking in the right trace at the wrong "
        f"time -- widen it from the instant the activation holds to the window "
        f"its consequence falls in, closing on a CONDITION rather than a count")


def _apart(oracle, variant, conforming: str, contract: dict,
           stimulus_by_tp: dict, ports: set[str], *, base: str) -> str:
    """What the variant this oracle let through did differently, at its ports.

    NEITHER SIDE IS NAMED, for the reason `trust._difference` records and with
    one extra turn of the screw here: the conforming side is the WITNESS, a
    second reading of the same requirements by the same author. Telling the
    author "the first trace is the correct one" would have it write its check
    against the witness -- and the same move, measured, is what took
    over-strictness 27 -> 15 while convictions went 2 -> 16, oracles relaxed
    until they stopped disagreeing with an implementation nobody had shown to be
    right.

    So the author gets the disagreement and decides from the requirement.
    """
    if variant is None or not conforming:
        return ""
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps:
        return ""
    good = replay(conforming, contract, steps, base=base)
    bad = replay(variant.source, contract, steps, base=base)
    if good.error or bad.error:
        return ""
    diffs = _difference(good.rows, bad.rows, ports)
    if not diffs:
        return ""
    return ("passed a design built to VIOLATE this requirement. It differs "
            "from the one you were shown:\n"
            + "\n".join(f"    {d}" for d in diffs)
            + f"\n  The {variant.kind} clause is the one it breaks. Decide "
            f"from the requirement which of the two is wrong and make the "
            f"check FAIL that one. Do not assume either trace is correct.")


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
