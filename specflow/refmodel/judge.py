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

You are given the whole model, one requirement, and the method names its author
claims implement that requirement. Read those methods. Decide:

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


def shared_prefix(source: str, contract_json: str) -> str:
    """Byte-identical across every requirement of one judging round.

    It contains the model source, which changes every repair round -- so unlike
    S1-S3, whose prefix is fixed for a whole node, this cache is cold at the
    start of each round and warms after two calls. With ~70 requirements per
    round that is still nearly all of them hitting; `cache_stats` reports it as a
    lower per-round rate rather than a defect.
    """
    return shared_block(
        ("system", SYSTEM),
        ("reference_model", source),
        ("contract_json", contract_json),
    )


def build_prompt(
    *,
    source: str,
    contract_json: str,
    requirement: dict,
    methods: list[str],
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    item = "\n\n".join([
        json_block("requirement", requirement),
        "<claimed_methods>\n"
        + (", ".join(methods) if methods else "(none declared)")
        + "\n</claimed_methods>",
    ])
    return compose(shared_prefix(source, contract_json), item,
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
) -> JudgeResult:
    """One small call per requirement, concurrent, over one frozen model.

    No repair loop of its own: the judge is asked once per round about a given
    model, and the *generator's* repair round is what changes anything. Re-asking
    the same judge about the same source would only resample its opinion, which
    is not evidence.
    """
    def one(req: dict) -> RequirementVerdict:
        uid = str(req.get("uid") or "")
        prompt = build_prompt(
            source=source, contract_json=contract_json, requirement=req,
            methods=list(covers.get(uid) or []),
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
