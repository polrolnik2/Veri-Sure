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

**The model cannot choose the top-level granularity.** It may divide a unit
further and may chain adjacent units, but an obligation may never span
non-adjacent units. The catch-all that claimed 100% of the spec on both real
runs is unavailable rather than discouraged.

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

from pydantic import BaseModel, Field

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
    """One atomic requirement, located by offsets *within its unit*.

    Relative rather than absolute on purpose: the numbers stay small and local,
    so a model cannot wander into another part of the document, and the
    conversion to absolute offsets is arithmetic this module owns.
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


SYSTEM = """\
You divide ONE unit of a hardware specification into atomic requirements.

The unit is a paragraph, list item, heading or table row -- a boundary the
specification's author drew. Your job is everything below that boundary.

You NEVER quote the specification. You return OFFSETS into the unit, and the
harness slices the text itself. Offsets are 0-based and relative to the unit,
where 0 is its first character.

For the unit, decide:

  kind                "behavioural" if it states observable behaviour a design
                      must exhibit; "interface" if it only declares ports,
                      widths or names; "scaffolding" for titles, cross-
                      references and prose that constrains nothing.

  continues_previous  true if this unit cannot stand alone because it continues
                      the previous one -- a list whose stem is the paragraph
                      above, or a sentence whose subject is named there.

  obligations         for a behavioural unit, one entry per atomic requirement.
                      An atomic requirement is ONE thing that could be
                      independently right or wrong and will become exactly one
                      method of a reference model. "The output is the sum" is
                      one; "the output is the sum, saturating on overflow" is
                      two.

Each obligation carries:
  start, end   offsets within this unit. Together they must TILE the unit:
               no overlap, no gap other than whitespace.
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

    The stage name carries the unit's offset rather than its index so a rerun
    over a re-divided spec cannot silently collide with a recorded fixture from a
    different partition.
    """
    try:
        contract = json.loads(contract_json) if contract_json.strip() else {}
    except json.JSONDecodeError:
        contract = {}

    return run_stage(
        stage=f"{STAGE}_{unit.start}",
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

    `continues_previous` chains a unit onto the one before it, so a list stem and
    its items become one requirement group rather than an orphaned fragment. The
    chain only ever reaches *adjacent* units: that restriction is what keeps a
    span from covering the whole document.
    """
    text = normalize_spec(spec)
    reqs: list[dict] = []
    n = 0
    for i, (unit, res) in enumerate(zip(units, results)):
        out = res.output
        if out.kind != "behavioural":
            continue
        for ob in out.obligations:
            start, end = unit.start + ob.start, unit.start + ob.end
            if out.continues_previous and reqs and i > 0 and units[i - 1].end <= start:
                # Extend the previous requirement's span backwards to include the
                # unit it depends on, rather than leaving a fragment that reads
                # as a standalone claim it is not.
                reqs[-1]["spec_spans"][-1]["end"] = end
                continue
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


def divide_and_classify(
    *,
    spec: str,
    contract_json: str,
    port: ModelPort,
    max_repairs: int = 2,
    fanout: bool = True,
) -> tuple[list[Unit], list[StageResult[UnitClassification]], list[dict]]:
    """The whole of the new S1: divide, classify every unit, assemble.

    `fanout=False` runs serially, which is what a `ReplayPort` wants -- fixtures
    are deterministic and a thread pool only adds nondeterminism to a test.
    """
    from .stage import run_fanout

    units = divide(spec)
    work = list(enumerate(units))

    def one(pair):
        i, unit = pair
        return run_unit(spec=spec, contract_json=contract_json, unit=unit,
                        index=i, units=units, port=port, max_repairs=max_repairs)

    results = run_fanout(work, one) if fanout else [one(p) for p in work]
    return units, results, to_requirements(spec, units, results)
