"""D2 + G1': classify one authorial unit, and gate the partition it produces.

`divide.py` cuts the specification where its author cut it and stops. This module
does everything below that boundary: for one unit it decides whether the unit
states behaviour, divides it into atomic obligations, and restates each one
self-containedly. Every stage that follows consumes those obligations.

Three properties, each of which is a defect in the generative S1 this replaces:

**The model emits offsets, never spec text.** A requirement's span is arithmetic
over the unit it came from. That removes verbatim quotation as a failure mode
entirely -- a faithful 14,842-character quote was rejected earlier for two
missing spaces of list indentation, and no amount of care makes transcription of
that length reliable.

**The model cannot choose granularity at all.** It may read one unit as several
obligations and may chain adjacent units, but a requirement's span is always the
whole unit -- `divide` cuts at sentence ends, so that is the smallest text that
can still be read as a claim. The catch-all that claimed 100% of the spec on
both real runs is unavailable rather than discouraged, and so is its mirror: on
c1-i2c the model subdivided 121 of 127 spans, 41 of them beginning mid-sentence,
and attributed a filter-window requirement to `" and glitch filtering."`.

**Context is preserved and it is nearly free.** The whole specification sits in
the shared, cached prefix -- measured at 97% cache hit -- so a unit-level call
reads the entire document while paying ~3% of it, and the neighbouring units are
marked explicitly so a back-reference has its referent in view. That is what
makes splitting below the paragraph safe here when a script doing the same thing
severed a link one time in five.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .divide import Unit, divide
from .fanout import PREFIX_SENTINEL, compose, shared_block

__all__ = ["PREFIX_SENTINEL"]  # re-exported: tests assert the stage's prefix
from .ids import PREFIX_REQUIREMENT, mint
from .model_io import ModelPort
from .s1_requirements import normalize_spec
from .schema import Issue
from .stage import StageResult, run_stage

STAGE = "classify"
BOUNDARY_STAGE = "boundary"

#: A restatement opening with one of these has inherited a dependency the split
#: was supposed to resolve. Measured on the raw specs, 28% and 15% of
#: within-paragraph sentences begin this way; after classification it should be
#: ~0, because resolving them is the classifier's job.
_BACKREF = re.compile(
    r"^\W*(it|its|this|that|these|those|they|their|the same|such|also|then|"
    r"otherwise|however|additionally|in addition|likewise|as above|as described|"
    r"doing so|the latter|the former)\b",
    re.I,
)

Kind = Literal["behavioural", "interface", "scaffolding"]


class BoundaryDecision(BaseModel):
    """Does this unit continue the one before it? Nothing else.

    A SEPARATE, EARLIER STAGE, and that is the point. `divide` produces a
    scaffold; some requirements straddle its boundaries; only a reader can say
    which. Asking that question inside the classifier meant one call was doing
    two jobs -- judging a boundary and dividing text into obligations -- and the
    obligations were then thrown away wherever the boundary judgement said
    "merge". So classification ran at a granularity the same call had just
    declared wrong.

    Here the boundary is settled FIRST, on its own. Classification then runs
    exactly once per final unit, always at the granularity that survives, so
    `ports` and every other relational field is filled against the requirement's
    real extent rather than against a fragment of it.

    The answer is one boolean, so the call is short in output -- which is what
    dominates latency -- and it shares the same cached prefix as everything else
    in S1.
    """

    reasoning: str = ""
    #: True when this unit and the previous one are ONE unit: a requirement
    #: whose statement straddles the boundary between them.
    continues_previous: bool = False


class UnitClassification(BaseModel):
    """One unit, one requirement. There is no obligation list, ON PURPOSE.

    **The unit IS the obligation granularity.** `divide` cuts, the boundary pass
    enlarges by merging with the unit before, and nothing else may move the
    line. A classifier that could return several obligations for one unit was
    choosing granularity again through a smaller door: on n3-i2c one feature-list
    sentence became nine requirements sharing one span, and one reset sentence
    became seven. Whether those are one requirement or nine is a judgement the
    divider and the boundary pass are supposed to have already made.

    So the restatement is a field of the classification, not an element of a
    list. The rule is enforced by the SHAPE of the answer rather than by a gate,
    which is the difference between a model that cannot break it and a model
    that is told not to.
    """

    reasoning: str = ""
    kind: Kind = "scaffolding"
    #: The requirement this unit states, restated in one self-contained
    #: sentence. Empty for a non-behavioural unit.
    text: str = ""
    #: The port names this unit's requirement constrains.
    ports: list[str] = Field(default_factory=list)
    #: The spec is silent or ambiguous here. An honest "it does not say" is worth
    #: more than a guess, which becomes a wrong oracle that fails correct designs.
    underdetermined: list[str] = Field(default_factory=list)

    @field_validator("underdetermined", mode="before")
    @classmethod
    def _accept_either_shape(cls, v):
        """Some calls answer with `{req_uid, question}` dicts rather than bare
        strings. Both are the same information; rejecting one shape throws away
        the fragments in the same response."""
        if isinstance(v, list):
            return [x.get("question", "") if isinstance(x, dict) else str(x) for x in v]
        return v


SYSTEM = """\
You divide ONE unit of a hardware specification into atomic requirements.

The unit is a SENTENCE, list item, heading or table row -- a boundary the
specification's author drew, or the end of one of their sentences -- or several
of those JOINED, when an earlier pass found a requirement whose statement runs
across them. Either way it is one unit and you treat it as one. Your job is
everything below that boundary.

You NEVER quote the specification and you NEVER choose where a requirement
begins or ends. THE UNIT IS THE REQUIREMENT. It was cut by a script and, where a
requirement ran across two of those cuts, joined by an earlier pass; by the time
it reaches you the granularity is settled. You say what it requires.

For the unit, decide:

  kind                "behavioural" if it states observable behaviour a design
                      must exhibit; "interface" if it only declares ports,
                      widths or names; "scaffolding" for titles, cross-
                      references and prose that constrains nothing.

  text                for a behavioural unit, the requirement it states,
                      restated as ONE self-contained sentence. Not a list: this
                      unit is one requirement, and if it reads as two things
                      then the specification states them in one breath and they
                      are verified together.

                      SELF-CONTAINED means it must not begin with "it", "this",
                      "also", "otherwise" or any other reference to something
                      outside itself -- name the subject. You can see the whole
                      specification and the unit before this one, so resolve the
                      reference rather than inheriting it.

  ports               the port names this requirement constrains, exactly as the
                      contract declares them.

If the specification does not determine a behaviour here, do not invent one:
record the question in `underdetermined`.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "kind": "behavioural",
  "text": "The sum output equals a xor b.",
  "ports": ["sum"],
  "underdetermined": []
}
"""


# ------------------------------------------------------------------- prompting


def shared_prefix(spec: str, contract_json: str) -> str:
    """The byte-identical head of every call in this stage.

    Nothing here may vary per unit -- no index, no uid, no count. That is the
    whole cache contract, it is worth ~30x on a fanned-out stage, and breaking it
    is silent, so `tests/test_specflow_cache.py` asserts it offline.
    """
    text = normalize_spec(spec)
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except json.JSONDecodeError:
        contract = {}
    io = contract.get("io") or []
    return shared_block(
        ("system", SYSTEM),
        ("specification", text),
        ("contract_io", json.dumps(io, indent=2, sort_keys=True)),
    )


def build_prompt(
    *,
    spec: str,
    contract_json: str,
    unit: Unit,
    index: int,
    units: list[Unit],
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """Shared block, then this unit, then any repair material. In that order.

    The order is the cache contract: repair rounds append after the unit so a
    round-1 prompt still opens with the round-0 prefix.
    """
    text = normalize_spec(spec)
    before = units[index - 1] if index > 0 else None
    after = units[index + 1] if index + 1 < len(units) else None

    item = []
    if before is not None:
        item.append(f"<previous_unit>\n{text[before.start:before.end]}\n</previous_unit>")
    item.append(
        f'<unit kind="{unit.kind}" length="{unit.length}">\n'
        + text[unit.start:unit.end]
        + "\n</unit>"
    )
    if after is not None:
        item.append(f"<next_unit>\n{text[after.start:after.end]}\n</next_unit>")
    return compose(
        shared_prefix(spec, contract_json), "\n\n".join(item),
        issues=issues, previous=previous,
    )


BOUNDARY_SYSTEM = """\
You are given ONE unit of a hardware specification and the unit before it, and
you answer a single question: are these two really ONE unit?

The units were cut by a script, at blank lines, list items, headings, table rows
and sentence ends. That is a first guess made before anybody read the text. It
is usually right and sometimes cuts through the middle of a requirement.

Answer TRUE when a requirement's statement STRADDLES the boundary -- when the
previous unit's words are part of what this unit requires, so that neither half
states the whole thing. A list item under the stem that introduces it, a clause
that completes the sentence before it, a sentence that supplies the value the
one before it left open.

Answer FALSE when this unit states something of its own, even if it REFERS
backwards. "It is then cleared" refers to the previous unit; it does not need
the previous unit's words to be a requirement, because the subject can simply be
named. The test is whether the previous unit's words belong INSIDE the
requirement, or only tell you what its subject is called.

Answer FALSE when the previous unit is a heading, a title or a cross-reference
that constrains nothing -- unless this unit is one of the items it introduces.

Nothing is lost either way. TRUE joins the two and a later pass reads the joined
text as one unit; FALSE leaves them as they are. Neither answer discards any
text or any requirement.

Reply with ONE JSON object and nothing else:

{"reasoning": "...", "continues_previous": false}
"""


def boundary_prompt(
    *,
    spec: str,
    contract_json: str,
    unit: Unit,
    index: int,
    units: list[Unit],
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """The same cached prefix as `classify`, with its own system text.

    The prefix is rebuilt from `shared_prefix`'s sections with BOUNDARY_SYSTEM
    swapped in, so this stage caches over its own 15KB of specification exactly
    as the classifier does -- and the two never share a cache key, because the
    system text differs in the first bytes.
    """
    text = normalize_spec(spec)
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except json.JSONDecodeError:
        contract = {}
    shared = shared_block(
        ("system", BOUNDARY_SYSTEM),
        ("specification", text),
        ("contract_io", json.dumps(contract.get("io") or [], indent=2, sort_keys=True)),
    )
    before = units[index - 1] if index > 0 else None
    item = []
    if before is not None:
        item.append(f"<previous_unit>\n{text[before.start:before.end]}\n</previous_unit>")
    else:
        item.append("<previous_unit>\n(none -- this is the first unit)\n</previous_unit>")
    item.append(f"<unit>\n{text[unit.start:unit.end]}\n</unit>")
    return compose(shared, "\n\n".join(item), issues=issues, previous=previous)


def parse_boundary(text: str) -> BoundaryDecision:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        if isinstance(obj, dict) and "continues_previous" not in obj:
            # Same guard, same reason, as `parse_response`: a response that lost
            # its opening is recovered by `extract_json_object` as some inner
            # fragment, and every field then falls to its default -- which here
            # is `False`, a real answer. Measured at 1.5% of calls on c1-i2c and
            # 3.6% on n3-i2c, so it is not rare enough to leave defaulting.
            raise ValueError(
                "the response carries no `continues_previous` (the object "
                f"recovered from it had keys {sorted(obj)[:8]}), which means its "
                "opening was lost. Return ONE complete JSON object, starting "
                "with `{` and with `continues_previous` as a top-level field.")
        return BoundaryDecision.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return BoundaryDecision(reasoning=f"Parse Error: {exc}")


def gate_boundary(out: BoundaryDecision, *, index: int) -> list[Issue]:
    """Thin, because the question is a judgement and code cannot second-guess it.

    What code CAN say is that the first unit has nothing before it, so it cannot
    continue anything -- and that a parse failure is a failure.
    """
    path = f"boundary[{index}]"
    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", path, out.reasoning)]
    if index == 0 and out.continues_previous:
        return [Issue("error", path,
                      "the first unit cannot continue anything; there is "
                      "nothing before it")]
    return []


def run_boundary(
    *,
    spec: str,
    contract_json: str,
    unit: Unit,
    index: int,
    units: list[Unit],
    port: ModelPort,
    max_repairs: int = 2,
) -> StageResult[BoundaryDecision]:
    """One unit, one boundary question."""
    return run_stage(
        stage=f"{BOUNDARY_STAGE}_{unit.start}_{unit.end}",
        port=port,
        build_prompt=lambda issues, previous: boundary_prompt(
            spec=spec, contract_json=contract_json, unit=unit, index=index,
            units=units, issues=issues, previous=previous,
        ),
        parse=parse_boundary,
        gate=lambda out: gate_boundary(out, index=index),
        max_repairs=max_repairs,
    )


def parse_response(text: str) -> UnitClassification:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        if isinstance(obj, dict) and "kind" not in obj:
            # A RESPONSE THAT LOST ITS HEAD, RECOVERED AS A FRAGMENT. Measured
            # on n3-i2c: 6 of 168 responses arrived with their first output-text
            # delta missing, so the text began at `"reasoning": "...` or even
            # `": "...` with no opening brace. `extract_json_object` then
            # scraped the innermost complete object it could find -- the LAST
            # OBLIGATION, `{start, end, text, ports}` -- and every field of
            # `UnitClassification` fell to its default, which means
            # `kind="scaffolding"` and no obligations. `gate_unit` passes a
            # scaffolding unit with no obligations without a word, so six
            # behavioural units silently produced nothing while the gate read
            # `ok=True, issues 0`. One of them was the unit stating that `busy`
            # is set on START and cleared on STOP.
            #
            # `kind` is the field that decides everything and the prompt always
            # asks for it, so its absence is a truncated response and never a
            # verdict. Raising here turns a silent scaffolding into a gate error
            # and a repair round. This is the same guard, for the same reason,
            # as the one in `normalize.parse_response`.
            keys = sorted(obj)[:8]
            raise ValueError(
                "the response carries no `kind` (the object recovered "
                f"from it had keys {keys}), which means its "
                "opening was lost in transport. Return ONE complete JSON "
                "object, starting with `{` and with `kind` as a top-level "
                "field.")
        return UnitClassification.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return UnitClassification(reasoning=f"Parse Error: {exc}")


# ------------------------------------------------------------------- gate G1'


def gate_unit(
    out: UnitClassification, *, unit: Unit, spec: str, contract: dict | None
) -> list[Issue]:
    """G1', for one unit. Pure code.

    Deliberately SMALL, and it shrank when the unit became the requirement.
    Three checks went away because the freedom they policed no longer exists:
    obligations cannot overlap or leave a gap when there is exactly one and it
    is the unit; a span cannot fall outside the unit when it IS the unit; and
    "more than one obligation in a restatement" was a defence against a model
    claiming a wide span with a crammed sentence, which is not a move it can
    make now that the divider and the boundary pass own the extent. Keeping that
    last one would have been actively wrong: a merged block or a sentence that
    states two things in one breath MUST be restated as both, and the check
    would have rejected the only correct answer, round after round.

    What remains is what code can still know: a parse failure is a failure, a
    behavioural unit has to say something, a non-behavioural one must not, the
    restatement has to stand on its own, and a port has to exist.
    """
    issues: list[Issue] = []
    path = f"unit[{unit.start}:{unit.end}]"
    restated = (out.text or "").strip()

    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", path, out.reasoning)]

    if out.kind != "behavioural":
        if restated:
            issues.append(
                Issue("error", path,
                      f"kind is {out.kind!r} but a requirement was stated: "
                      f"{restated!r}")
            )
        return issues

    if not restated:
        return [Issue("error", path, "behavioural unit states no requirement",
                      "uncovered")]

    # The 15-28% failure mode, checked on the restatement -- which the model
    # authors -- rather than on spec text, which it must not touch.
    m = _BACKREF.match(restated)
    if m:
        issues.append(
            Issue("error", path,
                  f"restatement opens with the unresolved reference "
                  f"{m.group(1)!r}; name the subject instead: {restated!r}")
        )

    declared = {
        str(p.get("name")) for p in ((contract or {}).get("io") or []) if p.get("name")
    }
    for port in out.ports or []:
        if declared and port not in declared:
            issues.append(
                Issue("error", f"{path}.ports",
                      f"{port!r} is not a port in the contract")
            )
    return issues


# ------------------------------------------------------------------ the stage


def run_unit(
    *,
    spec: str,
    contract_json: str,
    unit: Unit,
    index: int,
    units: list[Unit],
    port: ModelPort,
    max_repairs: int = 2,
) -> StageResult[UnitClassification]:
    """One unit, one bounded agent-plus-gate loop.

    The stage name carries the unit's offsets rather than its index, so a rerun
    over a re-divided spec cannot silently collide with a recorded fixture from
    a different partition. BOTH offsets: naming by the start alone was
    one-sided, and widening `_SENTENCE_CUT` is the case that showed it -- 168
    units became 172 with every existing START unchanged, so a resume would have
    replayed a longer unit's response for the four that split. The gate caught
    it, because those obligations run past the new `unit.length`, but a name
    that cannot collide is better than a gate that notices afterwards. It also
    gives a merged block (§`_chains`) a name of its own.
    """
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except json.JSONDecodeError:
        contract = {}

    return run_stage(
        stage=f"{STAGE}_{unit.start}_{unit.end}",
        port=port,
        build_prompt=lambda issues, previous: build_prompt(
            spec=spec, contract_json=contract_json, unit=unit, index=index,
            units=units, issues=issues, previous=previous,
        ),
        parse=parse_response,
        gate=lambda out: gate_unit(out, unit=unit, spec=spec, contract=contract),
        max_repairs=max_repairs,
    )


def to_requirements(
    spec: str, units: list[Unit], results: list[StageResult[UnitClassification]]
) -> list[dict]:
    """One behavioural unit, one requirement, spanning exactly that unit.

    Mechanical by construction. Everything that could once move the line has
    been moved earlier: `divide` cuts, the boundary pass enlarges by merging
    with the unit before, and the classifier says what the unit requires. There
    is nothing here to fold, widen, split or drop.

    Four designs reached this shape, and each earlier one lost or blurred
    something (`docs/evidence/continuations.md`):

      * folding a continuation into the previous requirement DELETED its
        obligations -- 42 of 169 on c1-i2c, silently, because the span survived
        and `assure` checks spans. Among them the sentence stating the filter's
        sampling interval as `clk_cnt >> 2`, which is why that cluster had no
        threshold to quote and scored INVERTED against golden RTL;
      * widening spans instead kept the text but left two classifications
        standing, one per half of a thought, with no call having seen the whole;
      * merging inside the classifier meant every merged block was classified at
        a granularity the same call had just declared wrong;
      * a LIST of obligations per unit let the classifier choose granularity
        again through a smaller door -- one feature-list sentence became nine
        requirements sharing one span.

    What is left is a partition built by code and a boundary judgement made once,
    so a requirement's extent is never the model's to invent and never a
    fragment of a sentence. c1-i2c's REQ-0083 carried 1,369 characters and stated
    one sentence's worth of them; that shape is now unreachable.
    """
    text = normalize_spec(spec)
    reqs: list[dict] = []
    n = 0
    for unit, res in zip(units, results):
        out = res.output
        if out.kind != "behavioural" or not (out.text or "").strip():
            continue
        reqs.append({
            "uid": mint(PREFIX_REQUIREMENT, n),
            "rev": 1,
            "text": out.text.strip(),
            "kind": "function",
            "spec_spans": [{"start": unit.start, "end": unit.end,
                            "quote": text[unit.start:unit.end]}],
            "ports": list(out.ports or []),
            "needs": ["testplan", "refmodel"],
        })
        n += 1
    return reqs


def _chains(flags: list[bool]) -> list[list[int]]:
    """Maximal runs of units the boundary pass read as ONE, as index groups.

    A unit whose flag is set joins the run its predecessor is in, so three
    consecutive flags make one group of four -- not three pairwise merges, and
    that is right because continuation is transitive: each flag is relative to
    the immediate predecessor. Index 0 can never continue (`gate_boundary`
    rejects it), and a group is always contiguous, which is what keeps a merged
    unit from reaching across the document.

    NOT BOUNDED, and it is the one way the catch-all could return. If every flag
    after the first were set, all units would merge into a single unit spanning
    the whole specification -- exactly the answer this subsystem exists to make
    unavailable. `divide_and_classify` reports the largest merged block for that
    reason. A cap is deliberately not imposed: a number standing in for a
    property is the mistake `MIN_SPAN_CHARS` and the distinct-span ban were both
    reverted for, and an unusually large block is a finding about the boundary
    pass, not something to silently truncate.
    """
    groups: list[list[int]] = []
    for i, flag in enumerate(flags):
        if i and flag and groups:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _merge(units: list[Unit], group: list[int]) -> Unit:
    """One unit spanning a whole group. Its kind comes from the first member,
    which is the one that can be read on its own; pass two re-decides it."""
    first, last = units[group[0]], units[group[-1]]
    return Unit(first.start, last.end, first.kind)


def divide_and_classify(
    *,
    spec: str,
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 2,
    fanout: bool = True,
    merge: bool = True,
) -> tuple[list[Unit], list[StageResult[UnitClassification]], list[dict]]:
    """The whole of the new S1: divide, settle the boundaries, THEN classify.

    Three steps, in this order, and the order is the design:

        divide      a script cuts at authorial boundaries and sentence ends.
                    A SCAFFOLD -- the best guess available before anything has
                    read the text.
        boundary    one short call per unit: does this unit and the one before
                    it form a single unit? Chains of yes are merged.
        classify    one call per FINAL unit: kind, obligations, ports.

    **Classification runs once, at the granularity that survives.** That is why
    the boundary question is its own stage rather than a field on the
    classifier's answer. When the classifier decided both, every merged block
    had been classified at a granularity the same call had just declared wrong,
    and that work was discarded -- so `ports`, the obligation split and every
    other relational field were authored against a fragment and then thrown
    away. Here they are authored once, against the requirement's real extent.

    Cost. The boundary pass is N calls whose entire output is a sentence and a
    boolean, over the same cached prefix, so it is short where it counts --
    output tokens dominate latency. Classification is then M calls with M <= N.
    Against a single classify pass this is not free: on a specification where
    nothing merges it is N extra cheap calls for no change in the partition.
    That is the price of never classifying at a granularity that is about to be
    revised, and it is paid whether or not the revision happens.

    Returns the FINAL units, their classifications, and the requirements.
    `fanout=False` runs serially, which is what a `ReplayPort` wants -- fixtures
    are deterministic and a thread pool only adds nondeterminism to a test.
    `merge=False` skips the boundary pass entirely and classifies the scaffold,
    which is what a test pinning the divider alone wants.
    """
    from .stage import run_fanout

    units = divide(spec)

    def spread(items, fn):
        return run_fanout(items, fn) if fanout else [fn(x) for x in items]

    if merge and len(units) > 1:
        decisions = spread(
            list(enumerate(units)),
            lambda pair: run_boundary(
                spec=spec, contract_json=contract_json, unit=pair[1],
                index=pair[0], units=units, port=port, max_repairs=max_repairs),
        )
        groups = _chains([d.output.continues_previous for d in decisions])
        units = [_merge(units, g) for g in groups]

    results = spread(
        list(enumerate(units)),
        lambda pair: run_unit(
            spec=spec, contract_json=contract_json, unit=pair[1],
            index=pair[0], units=units, port=port, max_repairs=max_repairs),
    )
    return units, results, to_requirements(spec, units, results)
