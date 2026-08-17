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
