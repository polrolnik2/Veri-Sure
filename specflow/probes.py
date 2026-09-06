"""[P] -- the specification's nouns, made into declared signals.

A specification states its requirements in terms its interface cannot name.
k1's is largely transition obligations -- "on `tagcomp_miss` with
`biudata_valid`, the FSM advances to LREFILL3" -- and LREFILL3 is not a port. So
the check author is asked to name a thing the vocabulary cannot name, and every
answer to that is wrong somewhere: `or1200_dc_fsm` projects six state variables
onto ten output bits, and CLOAD-with-miss-pending is indistinguishable from
LREFILL3 on `(burst, biu_read, first_miss_ack)`. The check's window then opens in
a state the requirement never mentioned, and it is rejected as off-target -- 23
of k1's 34 non-trusted behavioural requirements, and the top blocker on all
three measured designs.

This stage gives the vocabulary the noun. It reads the requirements, finds the
terms that have no port image, and emits each as a one-bit `dir: "probe"` entry
in the contract. Everything downstream then treats it as an ordinary signal.

THREE THINGS ABOUT ITS SHAPE, each of which was a defect first.

ONE MERGED CALL, never a fan-out. "Filtered SDA", "the debounced data line" and
"sSDA" are one signal, and a per-requirement fan-out would name it three times.
Naming coherence has no gate that can fix it afterwards -- the fix is that one
call sees every requirement at once and is asked to collapse phrasings. This is
the `cmd`-encoding fix applied to states: one table on the contract, resolved
once.

IT RUNS BEFORE NORMALIZE, so the first normalization pass already sees probes as
declared ports. That is what lets a requirement's `observable` name the state
directly instead of being routed through `observed_via` to a proxy, and it is
where the measured gain comes from.

IT NEVER ASSIGNS A DISPOSITION, and it has no authority to. It runs before any
design exists, so it cannot know what a design reaches. The one thing it may say
about a design is a `config_gated` HYPOTHESIS, and only where the specification
states the dependency in words this stage quotes -- the presence of a config key
is not the specification stating anything. That hypothesis changes no schedule
and no budget; its single use is that a later proof of unreachability on
generated RTL reads as "legitimately absent" rather than "the design is missing a
state the specification requires".
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field, model_validator

from .fanout import json_block
from eda_agent.utils import extract_json_object, strip_markdown_code_fences
from .model_io import ModelPort
from .schema import Issue, has_errors
from .stage import StageResult, gate_failures_block, previous_answer_block, run_stage

logger = logging.getLogger(__name__)

STAGE = "probes"

SYSTEM = """You are given a hardware specification and the requirements extracted
from it, plus the module's declared interface.

The requirements talk about things the interface does not name: states of a
state machine, internal flags, counters. A check written against this interface
has to guess at those, by watching combinations of output ports, and that guess
admits behaviours the specification never licensed. Your job is to name them.

For each term the requirements use that has NO port of its own, decide which of
two things it is:

  ALIAS  -- the interface already exposes it under another name. `saved_addr_r`
            is an internal register, but `assign saved_addr = saved_addr_r`, so
            it is the declared output `saved_addr` under another name. Record
            the mapping. Do NOT invent a signal for something already visible.

  PROBE  -- there is no port for it. Declare it: a ONE-BIT signal that is true
            exactly when the situation holds. `in_lrefill3` is true exactly when
            the FSM is in the state the specification calls LREFILL3.

RULES, and each of them is refused by a gate rather than merely requested:

1. ONE SITUATION GETS ONE PROBE. If three requirements say "the LREFILL3 state",
   "the line-refill state" and "while the cache line is being refilled", that is
   ONE probe with three spans, not three probes. You are given every requirement
   at once precisely so you can see that they are the same thing.

   THEN SWEEP BACK. Once you have settled the list, go through EVERY requirement
   again and ask, of each probe: does this requirement talk about this situation
   in words you have not yet quoted? If it does, add that phrasing as another
   span and add the requirement to `licensed_by`. A requirement that says "during
   a cache-line refill" is about the refill state even though it never writes
   LREFILL3, and a probe whose spans miss that phrasing will not be recognised as
   covering it. Measured on a 89-requirement specification: without this sweep an
   extractor found the states but quoted only the phrasings that name them
   explicitly, covering 20 of the 34 requirements it should have covered.

2. EVERY PROBE QUOTES THE SPECIFICATION, VERBATIM. Each entry's `spans` are
   exact substrings of the specification text -- copied, never paraphrased,
   never summarised. This is what makes a probe spec-licensed rather than a
   design choice: you are running before any design exists, so anything you
   cannot quote you are inventing.

   Copy each span out of the specification and check it back against the text
   before you use it. Assembling a sentence out of the right words in the right
   order is still a paraphrase, and it is refused: a gate searches the
   specification for each span (ignoring only line wrapping) and rejects any it
   cannot find.

3. ONE BIT, ALWAYS. Never a state vector or a counter value. A wider signal
   would need an encoding the specification does not state, and inventing one is
   how ten checks were previously made unfalsifiable. Say `cnt_nonzero`, not
   `cnt`.

4. NAME THEM FOR THE SITUATION, not for the mechanism: `in_lrefill3`,
   `cnt_nonzero`, `hitmiss_eval`. Lower case, valid Verilog identifiers.

5. YOU MAY NOT SAY A STATE IS UNREACHABLE, or absent, or dead. You are reading a
   specification, not a design; no design exists yet. The ONE exception is a
   `config_gated` hypothesis, and only when the specification ITSELF states that
   the thing exists only under a build option -- quote that sentence in the
   hypothesis's own `span`. A config key appearing in the build configuration is
   NOT the specification saying this.

   A STATE THE SPECIFICATION SAYS IS CONDITIONALLY ABSENT IS STILL DECLARED.
   Do not drop it. "The store-refill path is present only when
   OR1200_DC_STORE_REFILL is defined; on this build it is absent" names a state,
   so it gets a probe, carrying the hypothesis. This is the whole reason the
   hypothesis exists: later, on real hardware, a prover will find that state
   unreachable, and the ONLY thing that distinguishes *the specification told us
   it would be absent* from *the design is missing a state the specification
   requires* is whether you recorded the sentence that said so. Dropping the
   probe throws that distinction away, and its dependent requirements are then
   blamed on the test stimulus instead.

   `config_gated` is `null`, or an OBJECT with all three fields -- never a bare
   string:

       "config_gated": {"key": "OR1200_DC_STORE_REFILL", "value": false,
                        "span": "...the verbatim sentence stating the dependency..."}

   The `span` is what separates a hypothesis the specification licensed from an
   inference off a config key, so an entry without one is refused.

Also emit CROSS-CONSTRAINTS: where the specification relates a probe to real
ports ("in LREFILL3 the burst output is asserted"), write it as an ordinary
requirement sentence. These are what stop a check from verifying the design
against its own private vocabulary -- a design that lies about a probe fails
them, on real outputs.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "probes": [
    {"name": "in_lrefill3",
     "notes": "the FSM is in the state the specification calls LREFILL3",
     "licensed_by": ["REQ-0017", "REQ-0018"],
     "spans": ["...verbatim specification text...", "...another phrasing..."],
     "config_gated": null}
  ],
  "aliases": [
    {"term": "saved_addr_r", "port": "saved_addr",
     "why": "the specification assigns the output directly from this register"}
  ],
  "cross_constraints": [
    {"text": "While the FSM is in LREFILL3, burst is asserted.",
     "probe": "in_lrefill3", "ports": ["burst"],
     "span": "...verbatim specification text..."}
  ]
}
"""


class ConfigGated(BaseModel):
    key: str = ""
    value: bool = False
    #: The specification's OWN words stating the dependency. Without it the
    #: hypothesis is an inference from a config key, which is a design fact this
    #: stage may not assert.
    span: str = ""

    @model_validator(mode="before")
    @classmethod
    def _lift_bare_key(cls, value):
        """A bare `"config_gated": "OR1200_DC_STORE_REFILL"` becomes a keyed
        hypothesis with NO span, which the linter then refuses by name.

        Not leniency. Rejecting the shape at parse time throws away the whole
        probe table over one field and hands the repair round a pydantic type
        error about the document, when the thing that needs saying is specific:
        *this hypothesis has no span, and a span is what separates one the
        specification licensed from an inference off a config key.* Lifting it
        here is what lets the gate say that.
        """
        if isinstance(value, str):
            return {"key": value, "value": False, "span": ""}
        return value


class ProbeEntry(BaseModel):
    name: str = ""
    notes: str = ""
    licensed_by: list[str] = Field(default_factory=list)
    spans: list[str] = Field(default_factory=list)
    config_gated: ConfigGated | None = None

    def as_io(self) -> dict:
        """The `contract["io"]` entry. Width is not the model's to choose."""
        entry = {
            "name": self.name, "dir": "probe", "width": 1,
            "notes": self.notes,
            "licensed_by": list(self.licensed_by),
            "spans": list(self.spans),
        }
        if self.config_gated is not None:
            entry["config_gated"] = self.config_gated.model_dump()
        return entry


class Alias(BaseModel):
    term: str = ""
    port: str = ""
    why: str = ""


class CrossConstraint(BaseModel):
    text: str = ""
    probe: str = ""
    ports: list[str] = Field(default_factory=list)
    span: str = ""


class ProbeOutput(BaseModel):
    reasoning: str = ""
    probes: list[ProbeEntry] = Field(default_factory=list)
    aliases: list[Alias] = Field(default_factory=list)
    cross_constraints: list[CrossConstraint] = Field(default_factory=list)


def build_prompt(*, requirements: list[dict], contract_json: str, spec: str,
                 issues: list[Issue] | None = None,
                 previous: str | None = None) -> str:
    parts = [
        SYSTEM,
        json_block("requirements", requirements),
        "<contract_json>\n" + contract_json.rstrip() + "\n</contract_json>",
        "<specification>\n" + (spec or "").rstrip() + "\n</specification>",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_response(text: str) -> ProbeOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return ProbeOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return ProbeOutput(reasoning=f"Parse Error: {exc}")


def gate(out: ProbeOutput, *, contract: dict, spec: str,
         requirements: list[dict]) -> list[Issue]:
    """The gate. The probe RULES are the linter's; this adds only what it cannot see.

    `contract_linter.probe_issues` owns width, licensing, span presence, span
    uniqueness and the config hypothesis, and it is CALLED rather than
    reimplemented -- it lints a contract however produced, so a second copy of
    those rules here would be a second place for them to drift. What is added
    here is what needs this stage's inputs: that a name is usable, that it does
    not collide with a declared port, and that `licensed_by` names requirements
    that exist.
    """
    from eda_agent.contract_linter import probe_issues

    if out.reasoning.startswith("Parse Error: "):
        return [Issue("error", "probes.response", out.reasoning)]

    entries = [p.as_io() for p in out.probes]
    issues = [Issue(i.severity, i.path, i.message)
              for i in probe_issues(entries, spec or "")]

    declared = {str(p.get("name")) for p in (contract.get("io") or [])
                if p.get("name")}
    known = {str(r.get("uid") or "") for r in requirements}
    seen: set[str] = set()
    for idx, probe in enumerate(out.probes):
        path = f"probes[{idx}]"
        name = (probe.name or "").strip()
        if not name.isidentifier() or name != name.lower():
            issues.append(Issue(
                "error", f"{path}.name",
                f"{probe.name!r} is not a lower-case identifier; a probe becomes "
                f"a port of the generated module and has to be nameable in "
                f"Verilog"))
        if name in declared:
            # The alias case, not caught: the interface already exposes this, so
            # a probe would hand the check author two names for one wire and
            # inflate every count downstream.
            issues.append(Issue(
                "error", f"{path}.name",
                f"{name!r} is already a declared port -- record it as an alias, "
                f"not as a probe; declaring it twice gives the check author two "
                f"names for one signal"))
        if name in seen:
            issues.append(Issue("error", f"{path}.name",
                                f"probe {name!r} is declared twice"))
        seen.add(name)
        unknown = sorted(set(probe.licensed_by) - known)
        if unknown:
            issues.append(Issue(
                "error", f"{path}.licensed_by",
                f"probe {name!r} cites {unknown}, which are not requirements in "
                f"this specification"))

    for idx, alias in enumerate(out.aliases):
        if alias.port and alias.port not in declared:
            issues.append(Issue(
                "error", f"aliases[{idx}].port",
                f"alias {alias.term!r} points at {alias.port!r}, which is not a "
                f"declared port"))

    for idx, cc in enumerate(out.cross_constraints):
        if cc.probe and cc.probe not in seen:
            issues.append(Issue(
                "error", f"cross_constraints[{idx}].probe",
                f"cross-constraint names probe {cc.probe!r}, which is not in "
                f"this table"))
        outside = sorted(set(cc.ports) - declared)
        if outside:
            issues.append(Issue(
                "error", f"cross_constraints[{idx}].ports",
                f"cross-constraint names {outside}, which are not declared "
                f"ports -- the point of one is that it ties a probe to signals "
                f"a design cannot lie about"))
    return issues


def augmented(contract: dict, out: ProbeOutput) -> dict:
    """`contract` with the probe table written into `io`. Never mutates."""
    doc = json.loads(json.dumps(contract))
    doc.setdefault("io", [])
    doc["io"] = list(doc["io"]) + [p.as_io() for p in out.probes]
    doc["probes"] = [p.name for p in out.probes]
    if out.aliases:
        doc["probe_aliases"] = [a.model_dump() for a in out.aliases]
    return doc


def cross_constraint_requirements(out: ProbeOutput,
                                  requirements: list[dict]) -> list[dict]:
    """The cross-constraints, as ORDINARY requirements. No new machinery.

    They go through normalize, the check author and every existing gate exactly
    as any requirement does. With the scope rule reduced to a default, these are
    what stop a check verifying the design against its own private vocabulary: a
    design that lies about a probe fails them, on REAL OUTPUTS, where golden and
    the miter can both see it.
    """
    from .ids import PREFIX_REQUIREMENT, mint, next_index

    # From the uids that EXIST, not from the count. `mint(prefix, len(reqs))`
    # collides whenever uids are 1-based or have a gap -- with two requirements
    # numbered REQ-0001 and REQ-0002 it mints REQ-0002 again, and the
    # cross-constraint silently replaces a real requirement.
    base = next_index([str(r.get("uid") or "") for r in (requirements or [])],
                      PREFIX_REQUIREMENT)
    out_reqs: list[dict] = []
    for offset, cc in enumerate(out.cross_constraints):
        if not cc.text.strip():
            continue
        out_reqs.append({
            "uid": mint(PREFIX_REQUIREMENT, base + offset),
            "text": cc.text.strip(),
            "unit_kind": "behavioural",
            "spec_spans": [cc.span] if cc.span else [],
            "derived_from_probe": cc.probe,
        })
    return out_reqs


def orphans(contract: dict, normalized: list) -> list[str]:
    """Probes no requirement's activation or effect names, after normalize.

    Reported, not enforced, and the report has to say which of two things it is,
    because they have opposite fixes. If a licensing requirement's TEXT plainly
    names the state but its normalized activation does not, normalize failed to
    use a declared probe -- that is a defect in the port lookup, not here. If no
    requirement's activation actually depends on the state, this stage
    over-nominated and its prompt needs tightening.
    """
    from .refmodel.base import probe_names

    named: set[str] = set()
    for n in normalized or []:
        entry = n if isinstance(n, dict) else getattr(n, "model_dump", dict)()
        act = (entry.get("activation") or {})
        for field_ in ("opens_on", "until", "aborts_on", "sustains"):
            for clause in (act.get(field_) or []):
                if isinstance(clause, dict):
                    named |= set(clause)
        named |= set(entry.get("observable") or [])
    return sorted(set(probe_names(contract)) - named)


def run_probes(*, requirements: list[dict], contract: dict, contract_json: str,
               spec: str, port: ModelPort,
               max_repairs: int = 3) -> tuple[dict, list[dict],
                                              StageResult[ProbeOutput]]:
    """One call. Returns `(contract with probes, cross-constraints, result)`.

    On a gate the repairs cannot satisfy, the ORIGINAL contract is returned
    unchanged. A half-accepted probe table is worse than none: every stage below
    would be built on names that failed their licensing, and the failure would
    surface as checks that convict a correct design rather than as a stage that
    did not run.
    """
    result = run_stage(
        stage=STAGE, port=port,
        build_prompt=lambda issues, previous: build_prompt(
            requirements=requirements, contract_json=contract_json, spec=spec,
            issues=issues, previous=previous),
        parse=parse_response,
        gate=lambda out: gate(out, contract=contract, spec=spec,
                              requirements=requirements),
        max_repairs=max_repairs,
    )
    if not result.ok or not result.output.probes:
        if result.output is not None and has_errors(result.issues):
            logger.warning("probes: no usable probe table (%d issue(s)); the "
                           "contract is unchanged and every state term stays "
                           "unnameable", len(result.issues))
        return contract, [], result

    doc = augmented(contract, result.output)
    extra = cross_constraint_requirements(result.output, requirements)
    logger.info("probes: %d probe(s) %s; %d alias(es); %d cross-constraint(s)",
                len(result.output.probes), [p.name for p in result.output.probes],
                len(result.output.aliases), len(extra))
    return doc, extra, result


def write_artifacts(run_dir, contract: dict, result: StageResult[ProbeOutput]):
    """`probes.json` beside the other stage artifacts.

    The probe table is also written into `contract["io"]`, which is where every
    stage reads it from; this file is the stage's own record -- what it
    nominated, what it resolved as an alias instead, the cross-constraints it
    emitted, and the issues its gate raised. A reviewer asking "why is
    `in_lrefill3` a probe" reads it here, with the spans, rather than
    reconstructing it from the contract.
    """
    from pathlib import Path as _Path

    out = result.output or ProbeOutput()
    out_dir = _Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "probes.json"
    path.write_text(json.dumps({
        "probes": [p.as_io() for p in out.probes],
        "aliases": [a.model_dump() for a in out.aliases],
        "cross_constraints": [c.model_dump() for c in out.cross_constraints],
        "reasoning": out.reasoning,
        "issues": [{"severity": i.severity, "path": i.path, "message": i.message}
                   for i in result.issues],
        "rounds": result.rounds,
        "note": ("[P] runs before normalize and before any design exists, so it "
                 "may not say a state is unreachable; a config_gated entry is a "
                 "HYPOTHESIS licensed by a quoted span, and only a prover on "
                 "generated RTL can confirm it"),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
