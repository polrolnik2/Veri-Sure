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

#: Two independent obligations joined in one restatement. Deliberately narrow:
#: it looks for a second *subject-verb* obligation, not for the word "and",
#: because "drives SCL and SDA low" is one obligation over two ports.
_OBLIGATION = re.compile(
    r"\b(shall|must|is required to|are required to)\b", re.I
)

Kind = Literal["behavioural", "interface", "scaffolding"]


class Obligation(BaseModel):
    """One atomic requirement of a unit.

    `start` and `end` are offsets *within the unit* and they are an ACCOUNTING
    DEVICE, not the requirement's span. They exist so `_tiling_issues` can ask
    whether every character of the unit was accounted for -- which is the only
    thing in the chain that punishes under-splitting, and on c1-i2c it was 13 of
    the 20 issues the gate raised. What the requirement RECORDS as its
    provenance is the whole unit, because a span narrower than the unit is a
    fragment of a sentence: REQ-0010 shipped with the span `" and glitch
    filtering."` and asserted a mechanism those 22 characters do not contain.

    Relative rather than absolute on purpose: the numbers stay small and local,
    so a model cannot wander into another part of the document.
    """

    start: int = 0
    end: int = 0
    text: str = ""
    ports: list[str] = Field(default_factory=list)


class UnitClassification(BaseModel):
    reasoning: str = ""
    kind: Kind = "scaffolding"
    #: True when this unit is the continuation of the one before it -- a list
    #: stem and its items, a sentence whose subject is the preceding paragraph.
    continues_previous: bool = False
    obligations: list[Obligation] = Field(default_factory=list)
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
specification's author drew, or the end of one of their sentences. Your job is
everything below that boundary.

You NEVER quote the specification, and you never choose what text a requirement
is attributed to. THE WHOLE UNIT IS THE SPAN OF EVERY REQUIREMENT YOU RETURN
FROM IT. That is deliberate: a span narrower than a sentence is a fragment, and
a requirement resting on a fragment asserts more than its evidence says.

You still return OFFSETS into the unit, and they are ACCOUNTING: together they
must show that every character of the unit was read by some obligation, which is
how a unit stating two things cannot be answered with one. They do not narrow
what the requirement is attributed to. Offsets are 0-based and relative to the
unit, where 0 is its first character.

For the unit, decide:

  kind                "behavioural" if it states observable behaviour a design
                      must exhibit; "interface" if it only declares ports,
                      widths or names; "scaffolding" for titles, cross-
                      references and prose that constrains nothing.

  continues_previous  true if this unit and the previous one are really ONE
                      unit -- a requirement whose statement STRADDLES the
                      boundary between them. The boundaries you are given are a
                      first guess made before anyone read the text; this is how
                      you correct it.

                      What happens then: the two are joined and you are asked
                      again, with the WHOLE joined text as one unit, so a
                      requirement spanning both gets written once from all of
                      it. Nothing is discarded and no requirement is lost, so
                      say true whenever the previous unit is part of what this
                      unit states.

                      Say false when this unit merely REFERS to the previous
                      one without extending it. A reference you can resolve in
                      your restatement -- naming the subject instead of writing
                      "it" -- is not a continuation; that is what `text` is for.
                      The test is whether the previous unit's words are part of
                      the requirement, or only part of how you found its
                      subject.

  obligations         for a behavioural unit, one entry per atomic requirement.
                      An atomic requirement is ONE thing that could be
                      independently right or wrong and will become exactly one
                      method of a reference model. "The output is the sum" is
                      one; "the output is the sum, saturating on overflow" is
                      two.

Each obligation carries:
  start, end   offsets within this unit. Together they must TILE the unit:
               no overlap, no gap other than whitespace. They are accounting,
               not attribution -- the requirement's span is the whole unit
               either way.
  text         your restatement, ONE sentence, SELF-CONTAINED. It must not
               begin with "it", "this", "also", "otherwise" or any other
               reference to something outside itself -- name the subject. You
               can see the whole specification and the neighbouring units, so
               resolve the reference rather than inheriting it.
  ports        the port names this obligation constrains, exactly as the
               contract declares them.

If the specification does not determine a behaviour here, do not invent one:
record the question in `underdetermined`.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "kind": "behavioural",
  "continues_previous": false,
  "obligations": [
    {"start": 0, "end": 41, "text": "...", "ports": ["sum"]}
  ],
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


def parse_response(text: str) -> UnitClassification:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        if isinstance(obj, dict) and "kind" not in obj and "obligations" not in obj:
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
                "the response carries neither `kind` nor `obligations` (the "
                f"object recovered from it had keys {keys}), which means its "
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

    Deliberately has **no minimum span length**. Two threshold rules were tried
    and reverted this session: a 24-character minimum rejected the half adder's
    legitimate `' - output cout'`, and a distinct-span ban rejected one sentence
    constraining two ports. The anti-gaming property is structural instead --
    over-splitting is punished downstream, where G2 requires every requirement to
    yield a stimulus and an expected response and G4 requires its fragment to
    write a declared output port, while under-splitting is punished here. Neither
    gate alone is safe; the pair is, because no artifact satisfies both by
    degenerating.
    """
    body = normalize_spec(spec)[unit.start:unit.end]
    issues: list[Issue] = []
    path = f"unit[{unit.start}:{unit.end}]"

    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", path, out.reasoning)]

    if out.kind != "behavioural":
        if out.obligations:
            issues.append(
                Issue("error", path,
                      f"kind is {out.kind!r} but {len(out.obligations)} "
                      f"obligation(s) were returned")
            )
        return issues

    if not out.obligations:
        issues.append(
            Issue("error", path, "behavioural unit with no obligations", "uncovered")
        )
        return issues

    declared = {
        str(p.get("name")) for p in ((contract or {}).get("io") or []) if p.get("name")
    }

    spans: list[tuple[int, int]] = []
    for i, ob in enumerate(out.obligations):
        p = f"{path}.obligation[{i}]"
        # check 2: within its own unit, and a real range
        if not (0 <= ob.start < ob.end <= unit.length):
            issues.append(
                Issue("error", p,
                      f"span [{ob.start}:{ob.end}] is not inside the unit "
                      f"(length {unit.length})")
            )
            continue
        spans.append((ob.start, ob.end))

        restated = (ob.text or "").strip()
        if not restated:
            issues.append(Issue("error", p, "empty restatement"))
            continue

        # check 3: one obligation per requirement
        if len(_OBLIGATION.findall(restated)) > 1:
            issues.append(
                Issue("error", p,
                      f"restatement carries more than one obligation: {restated!r}")
            )

        # check 4: self-contained. This is the 15-28% failure mode, checked on
        # the restatement -- which the model authors -- rather than on spec text,
        # which it must not touch.
        m = _BACKREF.match(restated)
        if m:
            issues.append(
                Issue("error", p,
                      f"restatement opens with the unresolved reference "
                      f"{m.group(1)!r}; name the subject instead: {restated!r}")
            )

        # check 5: contract cross-check
        for port in ob.ports or []:
            if declared and port not in declared:
                issues.append(
                    Issue("error", f"{p}.ports",
                          f"{port!r} is not a port in the contract")
                )

    # check 1: the obligations tile the unit -- no overlap, no word-carrying gap.
    # This replaces "unattributed spec text", scoped to a unit rather than the
    # whole document, which is exactly what makes a 100%-of-spec span impossible.
    issues.extend(_tiling_issues(body, spans, path))
    return issues


def _tiling_issues(body: str, spans: list[tuple[int, int]], path: str) -> list[Issue]:
    issues: list[Issue] = []
    ordered = sorted(spans)
    for a, b in zip(ordered, ordered[1:]):
        if b[0] < a[1]:
            issues.append(
                Issue("error", path,
                      f"obligations overlap at [{b[0]}:{a[1]}]; each character of "
                      f"the unit belongs to exactly one requirement")
            )
    cursor = 0
    for start, end in ordered:
        if start > cursor and body[cursor:start].strip():
            issues.append(
                Issue("error", path,
                      f"no obligation claims [{cursor}:{start}]: "
                      f"{body[cursor:start].strip()[:80]!r}", "uncovered")
            )
        cursor = max(cursor, end)
    if cursor < len(body) and body[cursor:].strip():
        issues.append(
            Issue("error", path,
                  f"no obligation claims [{cursor}:{len(body)}]: "
                  f"{body[cursor:].strip()[:80]!r}", "uncovered")
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
    """Absolute-offset requirements, in document order, uids minted in sequence.

    **A requirement's span is the WHOLE UNIT it came from**, never the
    obligation's own offsets. Those offsets tile the unit so the gate can see
    that nothing went unread (`_tiling_issues`), and they stop there. Attributing
    a requirement to a slice of a sentence is what put `" and glitch filtering."`
    on REQ-0010: 22 characters that name a feature and state no behaviour, from
    which the pipeline then authored a check about a three-sample filter window.
    Since `divide` cuts at sentence ends, the unit is the smallest span that can
    still be read as a claim.

    Two obligations from one unit therefore share a span, and that is correct
    rather than a collision -- "the output is the sum, saturating on overflow" is
    two requirements resting on one sentence. A distinct-span ban was tried and
    reverted for exactly this case.

    **`continues_previous` is resolved before this function runs.** It merges
    two units into one and `divide_and_classify` re-classifies the merged block,
    so by the time obligations arrive here every unit is already as wide as the
    classifier thinks a requirement's text needs to be, and the span is just the
    unit. Nothing here folds, widens or drops.

    That is a correction, and the measurement is in
    `docs/evidence/continuations.md`: the original fold extended the PREVIOUS
    requirement's span and DROPPED the continuation's obligations, and on
    c1-i2c that discarded **42 of the 169 obligations the classifier authored --
    25%**. Because the span survived, `assure`'s unattributed-spec-text check
    saw nothing missing, so the loss was silent. Among the discarded: "the
    filter counter `filter_cnt` derives its sampling interval from the prescale
    value `clk_cnt` shifted right by two bits", which no surviving requirement
    stated -- which is why the filter cluster had no threshold to quote and
    scored INVERTED against golden RTL. Also gone were `busy` set on START and
    cleared on STOP, and the FSM's return to idle on arbitration loss.

    The intermediate fix -- keep the obligations, widen their spans backwards --
    stopped the loss but left TWO independent classifications standing, one per
    half of a thought, with no call having seen the whole. Merging the units and
    re-reading them is what makes a requirement spanning two sentences get
    authored once, from both.
    """
    text = normalize_spec(spec)
    reqs: list[dict] = []
    n = 0
    for unit, res in zip(units, results):
        out = res.output
        if out.kind != "behavioural":
            continue
        for ob in out.obligations:
            start, end = unit.start, unit.end
            reqs.append({
                "uid": mint(PREFIX_REQUIREMENT, n),
                "rev": 1,
                "text": ob.text.strip(),
                "kind": "function",
                "spec_spans": [{"start": start, "end": end, "quote": text[start:end]}],
                "ports": list(ob.ports or []),
                "needs": ["testplan", "refmodel"],
            })
            n += 1
    return reqs


def _chains(results: list[StageResult[UnitClassification]]) -> list[list[int]]:
    """Maximal runs of units the classifier read as ONE, as index groups.

    A unit that sets `continues_previous` joins the run its predecessor is in,
    so three consecutive continuations make one group of four. Index 0 can never
    continue -- there is nothing before it -- and a group is always contiguous,
    which is what keeps a merged unit from reaching across the document.
    """
    groups: list[list[int]] = []
    for i, res in enumerate(results):
        if i and res.output.continues_previous and groups:
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
    """The whole of the new S1: divide, classify, MERGE what spans units, assemble.

    **`divide` produces a scaffold, not the answer.** It cuts where the author
    cut and at sentence ends, which is the best guess available before anything
    has read the text -- but a requirement can straddle two of those boundaries,
    and only a reader can tell. `continues_previous` is how the classifier says
    so, and it means *these two units are one unit*.

    So there are two passes. The first classifies every unit alone and is read
    ONLY for that flag. Chains of it become merged units, and the second pass
    re-classifies each merged block **as a single unit**, so a requirement
    spanning two sentences is authored once, from both of them, by a model
    looking at the whole of it. Units nobody merged keep their first-pass result
    and cost no second call.

    That is the difference between merging and linking, and it is why this is
    not just a wider span. Widening leaves TWO independent classifications
    standing: unit A authored an obligation from half the thought and unit B
    authored one from the other half, and no call ever saw the whole. Merging
    re-reads. Linking a requirement to context it refers to but does not extend
    is a separate concern and is deliberately not this flag.

    Cost is one extra call per merged block, not per unit. The merge is applied
    ONCE: a block that declares continuation again in pass two is left alone,
    because a fixed point here would cost a call per round for a case the first
    pass -- which already absorbs consecutive flags -- has no evidence of.

    `fanout=False` runs serially, which is what a `ReplayPort` wants -- fixtures
    are deterministic and a thread pool only adds nondeterminism to a test.
    `merge=False` returns the scaffold partition unmerged, which is what a test
    pinning one pass wants.
    """
    from .stage import run_fanout

    units = divide(spec)

    def classify(all_units: list[Unit]):
        work = list(enumerate(all_units))

        def one(pair):
            i, unit = pair
            return run_unit(spec=spec, contract_json=contract_json, unit=unit,
                            index=i, units=all_units, port=port,
                            max_repairs=max_repairs)

        return run_fanout(work, one) if fanout else [one(p) for p in work]

    results = classify(units)
    if not merge:
        return units, results, to_requirements(spec, units, results)

    groups = _chains(results)
    merged = [_merge(units, g) for g in groups]
    if len(merged) == len(units):
        # Nothing chained. The partition is unchanged, so pass two would re-ask
        # every unit the identical question -- skip it entirely.
        return units, results, to_requirements(spec, units, results)

    # Only the blocks that actually merged are re-read; the rest keep pass one.
    todo = [(i, merged[i]) for i, g in enumerate(groups) if len(g) > 1]

    def one(pair):
        i, unit = pair
        return run_unit(spec=spec, contract_json=contract_json, unit=unit,
                        index=i, units=merged, port=port, max_repairs=max_repairs)

    fresh = dict(zip((i for i, _ in todo),
                     run_fanout(todo, one) if fanout else [one(p) for p in todo]))
    final = [fresh.get(i, results[g[0]]) for i, g in enumerate(groups)]
    return merged, final, to_requirements(spec, merged, final)
