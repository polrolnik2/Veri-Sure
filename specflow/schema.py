"""Artifact schemas for the spec -> testplan -> coverage chain.

House two-tier convention, matching `eda_agent/`:

* Tier 1 -- `pydantic.BaseModel` for anything an agent produces or that is
  serialized to disk. Every agent-output wrapper carries a `reasoning` field and
  is parsed by a function that never raises (see `eda_agent/asserter_agent.py`).
* Tier 2 -- `@dataclass(frozen=True)` plus a `Literal` status alias for internal
  results (see `eda_agent/asserter.py`, `eda_agent/contract_linter.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- tier 1

#: The seven behavioural dimensions a testplan element is decomposed across.
Dimension = Literal[
    "D1_data_boundary",
    "D2_control_flow",
    "D3_timing",
    "D4_fsm_transition",
    "D5_protocol",
    "D6_error_injection",
    "D7_microarch",
]

#: What a source artifact declares it must be covered *by*. This is the field
#: that makes the denominator originate in the spec rather than in the agent:
#: a testplan element covering a requirement that never asked for one is
#: `unwanted`, not bonus coverage.
NeedKind = Literal["testplan", "bin", "check", "refmodel"]


class SpecSpan(BaseModel):
    """A verbatim quotation of the spec text a requirement was derived from.

    `quote` must be a literal substring of `prompt.txt`; G1 checks that. It is
    what makes "which spec text did nothing claim?" answerable by a script.
    """

    start: int
    end: int
    quote: str


class Requirement(BaseModel):
    uid: str
    rev: int = 1
    text: str
    spec_spans: list[SpecSpan] = Field(default_factory=list)
    kind: str = "behaviour"
    #: Ports this requirement constrains, declared explicitly rather than mined
    #: out of `text`. Declaring them makes the contract cross-check exact: every
    #: name here must appear in `contract.io`. Inferring them from prose instead
    #: would make G1 fuzzy, and G1 blocks the pipeline.
    ports: list[str] = Field(default_factory=list)
    needs: list[NeedKind] = Field(default_factory=lambda: ["testplan", "refmodel"])


class TestplanElement(BaseModel):
    uid: str
    rev: int = 1
    covers: list[str] = Field(default_factory=list)  # "REQ-0007@1"
    dimension: Dimension = "D2_control_flow"
    stimulus: str = ""
    expected_response: str = ""
    check_method: str = ""
    needs: list[NeedKind] = Field(default_factory=lambda: ["bin", "check"])


class CoverBin(BaseModel):
    uid: str
    rev: int = 1
    covers: list[str] = Field(default_factory=list)  # "TP-0007@1"
    condition: str = ""
    #: Set only by `unreach.py`, and only with a recorded proof. A bin with a
    #: disposition leaves the accept criterion; one without does not.
    disposition: dict[str, Any] | None = None


class Check(BaseModel):
    uid: str
    rev: int = 1
    covers: list[str] = Field(default_factory=list)  # "TP-0007@1"
    expr: str = ""
    signals: list[str] = Field(default_factory=list)


class Testcase(BaseModel):
    uid: str
    targets: list[str] = Field(default_factory=list)  # BIN uids
    module: str = ""  # "test_TP0007"
    frozen: bool = False


class Underdetermined(BaseModel):
    """A requirement the spec does not pin down.

    An honest "the spec does not say" is worth more than a confident guess, so
    the pipeline needs somewhere to put it. Requirements listed here are
    excluded from the accept criterion with a recorded disposition, exactly like
    a proved-unreachable bin.
    """

    req_uid: str
    question: str

    @classmethod
    def coerce(cls, value):
        """Accept a bare question string as well as `{req_uid, question}`.

        The prompts ask for "the question you would ask", so a model answering
        with a question -- a string -- is following the instruction. Typing the
        field as dict-only rejected the whole response as a parse error and threw
        away the fragments alongside it.

        That penalised precisely the behaviour this pipeline most wants. The
        prompt says an honest "the spec does not say" is worth more than a
        confident guess, because a guess becomes a wrong oracle that fails
        correct designs -- and then the schema discarded every response that said
        it. Measured live on `i2c_master_bit_ctrl`: 27 of 60 reference-model
        calls were re-asked for this and nothing else.
        """
        if isinstance(value, str):
            return {"req_uid": "", "question": value}
        return value


# --- agent output wrappers (always `reasoning` + payload) -------------------


class RequirementsOutput(BaseModel):
    reasoning: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    underdetermined: list[Underdetermined] = Field(default_factory=list)


class TestplanOutput(BaseModel):
    reasoning: str = ""
    elements: list[TestplanElement] = Field(default_factory=list)


class CoverageOutput(BaseModel):
    reasoning: str = ""
    bins: list[CoverBin] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)


# ---------------------------------------------------------------- tier 2

Severity = Literal["error", "warning"]

#: The four link defects. `uncovered` is the load-bearing one -- it is the
#: direction every surveyed system omits.
DefectKind = Literal["uncovered", "orphaned", "unwanted", "outdated"]


@dataclass(frozen=True)
class Issue:
    """Same shape as `eda_agent.contract_linter.ContractIssue`, so all gates
    render through one formatter and speak one dialect to the repair agent."""

    severity: Severity
    path: str
    message: str
    kind: DefectKind | None = None


TestpointStatus = Literal["PASS", "FAIL", "NOT_EXERCISED"]


@dataclass(frozen=True)
class TestpointResult:
    # Not a pytest test class despite the name; without this pytest tries to
    # collect it and warns on the constructor.
    __test__ = False

    tp_uid: str
    status: TestpointStatus
    checks_invoked: tuple[str, ...] = ()
    checks_failed: tuple[str, ...] = ()
    bins_hit: tuple[str, ...] = ()
    mismatches: tuple[dict[str, Any], ...] = ()


GateOutcome = Literal["ACCEPT", "REPAIR_RTL", "EXTEND_TB", "STALLED"]


@dataclass(frozen=True)
class GateVerdict:
    outcome: GateOutcome
    failing: tuple[str, ...] = ()
    not_exercised: tuple[str, ...] = ()
    reason: str = ""


def render_issues(issues: list[Issue]) -> str:
    """Identical format to `render_contract_issues` so the repair prompt reads
    the same regardless of which gate produced the list."""
    if not issues:
        return ""
    return "\n".join(f"- [{it.severity}] {it.path}: {it.message}" for it in issues) + "\n"


def has_errors(issues: list[Issue]) -> bool:
    return any(it.severity == "error" for it in issues)


# ------------------------------------------------------------ the obligation


def core_span(req: dict) -> dict:
    """The ONE span a requirement is checked against.

    It lives in `obligation`, a single object, not an entry in a list. That is
    the point: a list with one member marked `role: "core"` reads as though
    there could be two, and a schema that can express a state the design forbids
    will eventually be handed one. `spec_spans` beside it holds CONTEXT only --
    spans the obligation cannot be read without, never a second thing to check.

    **Falls back to a marked or first `spec_spans` entry** when `obligation` is
    absent, which is what every artifact written before this shape looks like,
    including the generative arm's. Recorded runs stay readable rather than
    silently losing their provenance.
    """
    ob = req.get("obligation")
    if isinstance(ob, dict) and ob:
        return ob
    spans = req.get("spec_spans") or []
    for sp in spans:
        if sp.get("role") == "core":
            return sp
    return spans[0] if spans else {}


def supporting_spans(req: dict) -> list[dict]:
    """The spans a requirement is READ WITH.

    They are evidence, not decoration: normalisation legitimately draws an
    activation, an observability route, or a definition from them -- those are
    the fields an obligation most often leaves open. What they may never supply
    is the EXPECTATION. What must be true is what the obligation says; a
    behaviour stated in a context span is a different requirement with its own
    uid, and taking it here checks that one twice while leaving this one
    unchecked.
    """
    spans = list(req.get("spec_spans") or [])
    ob = req.get("obligation")
    if isinstance(ob, dict) and ob:
        return spans          # the core is not in here at all
    return [sp for sp in spans if sp.get("role") == "supporting"]


def all_spans(req: dict) -> list[dict]:
    """Every span this requirement rests on. For PROVENANCE, never for deciding
    what it must satisfy -- that is `core_span`, and there is one.

    In the new shape the core lives in `obligation` and `spec_spans` is context,
    so both halves are concatenated. In the OLD shape -- the generative arm,
    which emits "one or more VERBATIM quotations" with no roles at all --
    `spec_spans` already holds everything, and this must return ALL of it.
    Composing this from `core_span` plus `supporting_spans` looked equivalent
    and was not: with no roles marked, the second returns nothing, so every span
    after the first vanished and G1 failed on requirements it had passed for
    months.
    """
    spans = list(req.get("spec_spans") or [])
    ob = req.get("obligation")
    if isinstance(ob, dict) and ob:
        return [ob] + spans
    return spans
