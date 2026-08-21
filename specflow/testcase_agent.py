"""Generate a testcase for an uncovered bin.

**The agent chooses stimulus; it does not write test code.** This is the single
most important constraint in the design, and it is what makes it safe to hand
this tool to the RTL-repair agent -- whose objective is making things pass.

What the tool cannot express is the guarantee:

* checks come from the coverage model, so none can be weakened or omitted;
* expected values come from the frozen reference model, so none can be bent
  toward the current RTL;
* the agent supplies a bounded stimulus list, never Python;
* the bin must already be uncovered in the gate's own report, so targets cannot
  be invented.

Together these make adding a testcase **monotone**: it can add obligations, never
remove one. An agent reaching for this to escape a failing check can only make
its own job harder. The safety is a property of the interface, not a policy the
agent is asked to respect.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .ids import PREFIX_TESTCASE, mint, next_index
from .model_io import ModelPort
from .ports import classify
from .schema import Issue
from .tb.runtime import normalise_step
from .fanout import compose, json_block, shared_block
from .stage import (
    StageResult,
    gate_failures_block,
    previous_answer_block,
    run_fanout,
    run_stage,
)

STAGE = "testcase"
SUITE_STAGE = "stimulus"

#: Steps one testpoint may declare. Named rather than an inline default so the
#: gate applied when a recorded `stimulus.json` is REUSED is provably the same
#: bound applied when it was generated -- a reuse path gated more loosely than
#: the generator is a way to accept what a fresh run would reject.
STIMULUS_MAX_STEPS = 24


def _drivable(contract: dict) -> dict[str, int]:
    """Input ports a testcase may drive: the functional ones.

    Clock and reset are excluded because the runtime owns them -- `Env.reset()`
    sequences the reset and calls the reference model's own `reset()`, so a
    testcase toggling reset underneath would desynchronise the two. They are
    still in the model's input bundle; see `specflow/ports.py`.
    """
    _, _, functional = classify(contract)
    widths = {
        str(p.get("name")): int(p.get("width") or 1)
        for p in (contract.get("io") or [])
    }
    return {name: widths.get(name) or 1 for name in functional}


class TestcaseSpec(BaseModel):
    # Not a pytest test class despite the name.
    __test__ = False

    reasoning: str = ""
    targets: list[str] = Field(default_factory=list)
    #: Bounded choice list: one dict of port -> value per step.
    stimulus_steps: list[dict] = Field(default_factory=list)
    notes: str = ""


SYSTEM = """\
You choose stimulus for a coverage bin the testbench has not yet reached.

You do NOT write test code. You do NOT state expected values. You supply input
values only; the harness drives them, records the bin, and compares the outputs
against the reference model on your behalf.

Supply:
  targets         the bin uid(s) this stimulus is meant to reach
  stimulus_steps  a list of steps, each a dict of input port name -> integer
                  value. Every input port must appear in every step.
  notes           one line on why this stimulus should reach the bin

Rules the gate enforces mechanically:
  * every port you name must be an input port in the contract
  * every value must fit its port width
  * at least one step
  * targets must be bins currently reported uncovered

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "targets": ["BIN-0007"],
  "stimulus_steps": [{"a": 1, "b": 1}],
  "notes": "..."
}
"""


def build_prompt(
    *,
    bin_uid: str,
    condition: str,
    testplan_element: dict,
    contract: dict,
    gap_category: str,
    already_reached: list[dict],
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    inputs = [
        {"name": name, "width": width} for name, width in _drivable(contract).items()
    ]
    parts = [
        SYSTEM,
        f"<bin uid=\"{bin_uid}\" category=\"{gap_category}\">\n{condition}\n</bin>",
        "<testplan_element>\n"
        + json.dumps(testplan_element, indent=2, ensure_ascii=False)
        + "\n</testplan_element>",
        "<input_ports>\n" + json.dumps(inputs, indent=2) + "\n</input_ports>",
        # What existing testcases already drove. "These were reached, this one
        # was not" is a far more tractable prompt than "write a test for this".
        "<already_driven>\n"
        + json.dumps(already_reached[:32], indent=2)
        + "\n</already_driven>",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_response(text: str) -> TestcaseSpec:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return TestcaseSpec.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return TestcaseSpec(reasoning=f"Parse Error: {exc}")


def gate(
    spec: TestcaseSpec, *, bin_uid: str, contract: dict, uncovered: set[str]
) -> list[Issue]:
    if spec.reasoning.startswith("Parse Error: "):
        return [Issue("error", "testcase.response", spec.reasoning)]

    issues: list[Issue] = []
    inputs = _drivable(contract)

    if not spec.stimulus_steps:
        issues.append(Issue("error", "testcase.stimulus_steps", "no steps supplied"))

    for i, step in enumerate(spec.stimulus_steps):
        path = f"testcase.stimulus_steps[{i}]"
        for name, value in step.items():
            if name not in inputs:
                issues.append(
                    Issue("error", path, f"{name!r} is not an input port in the contract")
                )
                continue
            try:
                as_int = int(value)
            except Exception:  # noqa: BLE001
                issues.append(Issue("error", path, f"{name}={value!r} is not an integer"))
                continue
            if not (0 <= as_int < (1 << inputs[name])):
                issues.append(
                    Issue("error", path,
                          f"{name}={as_int} does not fit {inputs[name]} bit(s)")
                )
        missing = set(inputs) - set(step)
        if missing:
            issues.append(
                Issue("error", path, f"does not drive {sorted(missing)}")
            )

    # The tool cannot invent targets: the bin must already be uncovered in the
    # gate's own report. This is what keeps the addition monotone.
    for target in spec.targets or [bin_uid]:
        if target not in uncovered:
            issues.append(
                Issue("error", "testcase.targets",
                      f"{target} is not currently reported uncovered")
            )

    return issues


def run_testcase_agent(
    *,
    bin_uid: str,
    condition: str,
    testplan_element: dict,
    contract: dict,
    gap_category: str,
    already_reached: list[dict],
    uncovered: set[str],
    port: ModelPort,
    max_repairs: int = 2,
) -> StageResult[TestcaseSpec]:
    return run_stage(
        stage=f"{STAGE}_{bin_uid.replace('-', '')}",
        port=port,
        build_prompt=lambda issues, previous: build_prompt(
            bin_uid=bin_uid, condition=condition, testplan_element=testplan_element,
            contract=contract, gap_category=gap_category,
            already_reached=already_reached, issues=issues, previous=previous,
        ),
        parse=parse_response,
        gate=lambda spec: gate(
            spec, bin_uid=bin_uid, contract=contract, uncovered=uncovered
        ),
        max_repairs=max_repairs,
    )


def next_testcase_uid(existing: list[dict]) -> str:
    return mint(PREFIX_TESTCASE, next_index([t.get("uid", "") for t in existing],
                                            PREFIX_TESTCASE))


def append_testcase(
    *, testcases_path: Path, uid: str, targets: list[str], module: str
) -> list[dict]:
    """Record the testcase. Existing entries are never rewritten.

    `frozen` makes the append-only discipline enforceable: an accepted testcase
    is not a thing a later round may quietly amend.
    """
    path = Path(testcases_path)
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing.append({"uid": uid, "targets": targets, "module": module, "frozen": True})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return existing


# ------------------------------------------------- suite stimulus (build time)

SUITE_SYSTEM = """\
You choose the input stimulus for every element of a verification testplan.

You do NOT write test code. You do NOT state expected values. You supply input
values only; the harness drives them, records coverage, and compares the outputs
against a reference model on your behalf. A wrong expected value is not a
mistake you are able to make.

Each testplan element states, in prose, the stimulus its testpoint requires --
"issue a START command", "hold scl_i low after SCL is released", "sweep the
prescale value". Turn each of those into a concrete ordered sequence of input
values that actually performs it.

Order matters and state persists. The steps of one testpoint are applied in
order to a sequential design that is reset once at the start, so step N sees
whatever state steps 0..N-1 produced.

ONE STEP IS ONE CLOCK EDGE unless you say otherwise, and a step can state its
own duration. This matters more than it sounds: a design gated on a prescaler
advances one phase per tick, so a command can take tens or hundreds of clocks,
and a sequence that runs out of edges half way through verifies nothing after
that point.

  {"a": 1, "b": 0}                          one edge
  {"inputs": {...}, "hold": 8}              the same inputs, held 8 edges
  {"inputs": {...}, "until": {"port": "done", "value": 1}, "timeout": 200}
                                            held until the DESIGN says so

Prefer `until` over a large `hold`. "Wait for the acknowledge" is a fact about
the design; "wait 26 clocks" is a guess about its implementation, and it will be
wrong on the next prescaler value. `until` waits on a declared OUTPUT -- what the
design reports, never what you drive.

Supply:
  testpoints  one entry per testplan element, each with
                tp_uid          the element's uid, exactly as given
                stimulus_steps  an ordered list of steps. A step is either a
                                bare dict of input port name -> integer value,
                                or {"inputs": {...}} with an optional "hold" or
                                "until"/"timeout". Every drivable input must
                                appear in every step.

Return ONE json object:

{
  "reasoning": "...",
  "testpoints": [
    {"tp_uid": "TP-0000", "stimulus_steps": [{"ena": 1, "cmd": 1}, {"ena": 1, "cmd": 0}]}
  ]
}
"""


class TestpointStimulus(BaseModel):
    __test__ = False

    tp_uid: str = ""
    stimulus_steps: list[dict] = Field(default_factory=list)


class SuiteStimulus(BaseModel):
    __test__ = False

    reasoning: str = ""
    testpoints: list[TestpointStimulus] = Field(default_factory=list)


def build_suite_prompt(
    *,
    testplan: list[dict],
    contract: dict,
    max_steps: int,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    inputs = [
        {"name": name, "width": width} for name, width in _drivable(contract).items()
    ]
    elements = [
        {
            "uid": tp.get("uid"),
            "dimension": tp.get("dimension"),
            "stimulus": tp.get("stimulus"),
            "expected_response": tp.get("expected_response"),
        }
        for tp in testplan
    ]
    parts = [
        SUITE_SYSTEM,
        f"At most {max_steps} steps per testpoint.",
        "<input_ports>\n" + json.dumps(inputs, indent=2) + "\n</input_ports>",
        "<testplan>\n"
        + json.dumps(elements, indent=2, ensure_ascii=False)
        + "\n</testplan>",
    ]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def parse_suite_response(text: str) -> SuiteStimulus:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return SuiteStimulus.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return SuiteStimulus(reasoning=f"Parse Error: {exc}")


#: Bounds on a step's declared duration. `hold` is capped low deliberately: a
#: large fixed edge count is a guess, and `until` is the honest way to say "wait
#: for the design". The timeout bound only has to be generous enough for a
#: heavily prescaled design -- one i2c testpoint needs 506 edges for one command.
MAX_HOLD = 64
MAX_TIMEOUT = 4000


def gate_suite(
    spec: SuiteStimulus, *, testplan: list[dict], contract: dict, max_steps: int
) -> list[Issue]:
    """Every testpoint gets a valid, non-empty, in-range stimulus sequence.

    Deliberately *not* gated on distinctness. The observed failure was 25 of 25
    testpoints running an identical vector list, and a distinctness rule is
    exactly the kind of check a model satisfies by permuting one value -- the
    same lesson G1 taught when a coverage rule was answered with one 14.8KB
    quote. What makes stimulus meaningful is whether it reaches the bins, and
    the coverage gate already asks that and answers `EXTEND_TB` when it does
    not. Distinctness is reported below as a diagnostic, not enforced.
    """
    if spec.reasoning.startswith("Parse Error: "):
        return [Issue("error", "stimulus.response", spec.reasoning)]

    issues: list[Issue] = []
    inputs = _drivable(contract)
    outputs = {
        str(p.get("name")) for p in (contract.get("io") or [])
        if p.get("dir") == "output" and p.get("name")
    }
    wanted = [str(tp.get("uid")) for tp in testplan]
    by_uid = {tp.tp_uid: tp for tp in spec.testpoints}

    for uid in wanted:
        entry = by_uid.get(uid)
        if entry is None or not entry.stimulus_steps:
            issues.append(
                Issue("error", f"stimulus.{uid}", "no stimulus supplied", "uncovered")
            )
            continue
        if len(entry.stimulus_steps) > max_steps:
            issues.append(
                Issue("error", f"stimulus.{uid}",
                      f"{len(entry.stimulus_steps)} steps exceeds the {max_steps} limit")
            )
        for i, raw in enumerate(entry.stimulus_steps):
            path = f"stimulus.{uid}.steps[{i}]"
            step, hold, until, timeout = normalise_step(raw)
            # A step may state its own duration. Before this, `hold`/`until`
            # were rejected as "not a drivable input" -- there was no way to say
            # a command needs cycles except to repeat the identical dict, and
            # how long a vector was actually applied came from the contract's
            # guessed `latency_cycles` instead of from the test.
            if hold > MAX_HOLD:
                issues.append(
                    Issue("error", path,
                          f"hold={hold} exceeds the {MAX_HOLD} edge limit; use "
                          f"`until` to wait for the design instead of guessing "
                          f"a large edge count")
                )
            if until is not None:
                port = str(until.get("port") or "")
                if port not in outputs:
                    issues.append(
                        Issue("error", path,
                              f"until.port={port!r} is not a declared output; a "
                              f"step waits on what the DESIGN reports, not on "
                              f"what the test drives")
                    )
                if timeout and timeout > MAX_TIMEOUT:
                    issues.append(
                        Issue("error", path,
                              f"timeout={timeout} exceeds the {MAX_TIMEOUT} "
                              f"edge limit")
                    )
            for name, value in step.items():
                if name not in inputs:
                    issues.append(
                        Issue("error", path,
                              f"{name!r} is not a drivable input; the runtime owns "
                              f"clock and reset")
                    )
                    continue
                try:
                    as_int = int(value)
                except Exception:  # noqa: BLE001
                    issues.append(
                        Issue("error", path, f"{name}={value!r} is not an integer")
                    )
                    continue
                if not (0 <= as_int < (1 << inputs[name])):
                    issues.append(
                        Issue("error", path,
                              f"{name}={as_int} does not fit {inputs[name]} bit(s)")
                    )
            missing = set(inputs) - set(step)
            if missing:
                issues.append(Issue("error", path, f"does not drive {sorted(missing)}"))

    for uid in set(by_uid) - set(wanted):
        issues.append(
            Issue("error", f"stimulus.{uid}", "no such testplan element", "orphaned")
        )

    return issues


def stimulus_diagnostics(spec: SuiteStimulus) -> list[Issue]:
    """How much of the suite is actually distinct. Reported, never enforced."""
    seen: dict[str, str] = {}
    for tp in spec.testpoints:
        seen.setdefault(json.dumps(tp.stimulus_steps, sort_keys=True), tp.tp_uid)
    n, distinct = len(spec.testpoints), len(seen)
    if n and distinct < n:
        return [
            Issue("warning", "stimulus",
                  f"{n} testpoints share {distinct} distinct stimulus sequence(s); "
                  f"testpoints running identical stimulus test the same thing under "
                  f"different names")
        ]
    return []


def run_suite_stimulus(
    *,
    testplan: list[dict],
    contract: dict,
    port: ModelPort,
    max_steps: int = STIMULUS_MAX_STEPS,
    max_repairs: int = 2,
) -> StageResult[SuiteStimulus]:
    """One call for the whole suite, not one per testpoint.

    Same shape as the reference model's single fragment call: a node with 25
    testplan elements makes one request carrying 25 stimulus sequences, and a
    repair round re-asks with the gate's issues rather than regenerating from
    nothing.
    """
    return run_stage(
        stage=SUITE_STAGE,
        port=port,
        build_prompt=lambda issues, previous: build_suite_prompt(
            testplan=testplan, contract=contract, max_steps=max_steps,
            issues=issues, previous=previous,
        ),
        parse=parse_suite_response,
        gate=lambda spec: gate_suite(
            spec, testplan=testplan, contract=contract, max_steps=max_steps
        ),
        max_repairs=max_repairs,
    )


def suite_shared_prefix(contract: dict, max_steps: int) -> str:
    """Everything identical across testpoints: the task, the limits, the ports.

    OUTPUTS are listed as well as inputs, because `until` waits on a declared
    output and `gate_suite` rejects one that is not. Listing only the inputs
    left the agent to guess output names out of the testpoint prose, and the
    prose names internal signals: measured on i2c_master_bit_ctrl, 12 of the
    first 41 testpoints needed a repair round, and the errors were
    `until.port='clk_en'`, `'idle'`, `'slave_wait'`, `'filtered_sda'` -- all
    real signals of the design, none of them ports. The gate was validating
    against a list the agent had never been shown.

    Both lists sit in the shared prefix, so they cost one cache write rather
    than one copy per testpoint.
    """
    inputs = [
        {"name": name, "width": width} for name, width in _drivable(contract).items()
    ]
    outputs = [
        {"name": p.get("name"), "width": p.get("width", 1)}
        for p in (contract.get("io") or [])
        if p.get("dir") == "output" and p.get("name")
    ]
    return shared_block(
        ("system", SUITE_SYSTEM),
        ("limits", f"At most {max_steps} steps for this testpoint."),
        ("input_ports", json.dumps(inputs, indent=2)),
        ("output_ports",
         json.dumps(outputs, indent=2)
         + "\n\nThese are the ONLY signals `until` may wait on. Anything else "
           "named in the testpoint prose is internal to the design and is not "
           "observable at the boundary."),
    )


def spec_quotes_for(element: dict, requirements: list[dict] | None) -> list[str]:
    """The specification text behind this testpoint, via `covers`.

    A testpoint carries no spec of its own -- its fields are uid, rev, covers,
    dimension, stimulus, expected_response, needs -- so the stimulus stage was
    working purely from S2's paraphrase. Measured across a whole run, every
    stage keyed on a REQUIREMENT carried spec text (s2 77/77, refmodel 7/7,
    judge 539/539) and every stage keyed on a TESTPOINT carried none (s3 0/226,
    stimulus 0/34).

    The paraphrase is lossy in the direction that matters here. TP-0000's prose
    reads "clk_cnt large so clk_en ticks predictably", which is sound advice to
    a reader who knows clk_cnt is the divider reload and actively misleading to
    one who does not: larger means FEWER edges per command, and the monolithic
    run duly chose clk_cnt=1000 and then drove it for a single edge.

    `covers` holds "REQ-0007@1"; the revision is not part of the key.
    """
    if not requirements:
        return []
    by_uid = {str(r.get("uid")): r for r in requirements}
    quotes: list[str] = []
    for ref in element.get("covers") or []:
        req = by_uid.get(str(ref).split("@", 1)[0])
        for span in (req or {}).get("spec_spans") or []:
            quote = (span or {}).get("quote")
            if quote and quote not in quotes:
                quotes.append(quote)
    return quotes


def build_suite_prompt_one(
    element: dict,
    contract: dict,
    max_steps: int,
    issues: list[Issue] | None = None,
    previous: str | None = None,
    requirements: list[dict] | None = None,
) -> str:
    item = {
        "uid": element.get("uid"),
        "dimension": element.get("dimension"),
        "stimulus": element.get("stimulus"),
        "expected_response": element.get("expected_response"),
    }
    quotes = spec_quotes_for(element, requirements)
    if quotes:
        item["specification_this_testpoint_covers"] = quotes
    return compose(
        suite_shared_prefix(contract, max_steps),
        json_block("testplan_element", item),
        issues=issues,
        previous=previous,
    )


def run_suite_stimulus_fanout(
    *,
    testplan: list[dict],
    contract: dict,
    port: ModelPort,
    max_steps: int = STIMULUS_MAX_STEPS,
    max_repairs: int = 2,
    fanout: bool = True,
    requirements: list[dict] | None = None,
) -> tuple[SuiteStimulus, list[StageResult[SuiteStimulus]]]:
    """One call per testpoint, because testpoints do not constrain each other.

    The reference model is generated whole for a real reason -- it needs global
    context for ordering, reset priority and shared state. Stimulus has no such
    coupling: each testpoint's vectors are independent of every other's, which
    is exactly the condition that makes fanning out correct rather than merely
    cheaper.

    Monolithic generation was measured failing on `i2c_master_bit_ctrl` at 167
    testpoints. Three repair rounds returned stimulus for TEN of them; the
    fourth returned all 167 with exactly one step each, every `hold` equal to 1
    and only 59 distinct sequences -- one testpoint drove `clk_cnt=1000` for a
    single edge, which cannot advance a prescaler that needs 1000 ticks, let
    alone complete a START. `gate_suite` passed it, because it requires stimulus
    to be non-empty and one step is non-empty.

    That is what a single call carrying 167 x 24 steps x 6 ports degrades into,
    and the repair channel makes it worse rather than better: one invalid step
    anywhere invalidates the whole batch and re-asks for all of it, so the
    cheapest way out is to shrink every sequence. Per testpoint, the same budget
    buys the depth the scenario actually needs.
    """
    def one(element: dict) -> StageResult[SuiteStimulus]:
        return run_stage(
            stage=f"{SUITE_STAGE}_{element.get('uid', 'unknown')}",
            port=port,
            build_prompt=lambda issues, previous: build_suite_prompt_one(
                element, contract, max_steps, issues, previous,
                requirements=requirements),
            parse=parse_suite_response,
            gate=lambda spec: gate_suite(
                spec, testplan=[element], contract=contract, max_steps=max_steps),
            max_repairs=max_repairs,
        )

    results = run_fanout(testplan, one) if fanout else [one(e) for e in testplan]
    merged = SuiteStimulus(
        reasoning="; ".join(
            r.output.reasoning for r in results if r.output.reasoning)[:2000],
        testpoints=[tp for r in results for tp in r.output.testpoints],
    )
    return merged, results


def stimulus_by_tp(spec: SuiteStimulus) -> dict[str, list[dict]]:
    return {
        tp.tp_uid: tp.stimulus_steps for tp in spec.testpoints if tp.stimulus_steps
    }
