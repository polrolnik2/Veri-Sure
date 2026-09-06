"""The contract linter admits `dir: "probe"`, and owns every rule about one.

A probe is a specification term made observable -- `in_lrefill3` is true exactly
when the FSM is in the state the spec calls LREFILL3 -- so that a check can NAME
the moment its requirement is about instead of proxying it through a combination
of outputs. The proxy is lossy, and every unlicensed path it admits is a check
that convicts a correct design.

What makes that safe is the licensing span. A probe must quote the specification
text that licenses it, verbatim, because the stage that proposes probes runs
before any design exists: anything it cannot quote, it is inventing.
"""
from __future__ import annotations

from pathlib import Path

import json

from eda_agent.contract_linter import (PORT_DIRECTIONS, lint_contract_json,
                                        probe_issues)

SPEC = (Path(__file__).parent / "fixtures/probes/spec.txt").read_text()


def _probe(**kw) -> dict:
    """A valid probe. Each test breaks exactly one thing about it."""
    entry = {
        "name": "in_lrefill3",
        "dir": "probe",
        "width": 1,
        "licensed_by": ["REQ-0017"],
        # Deliberately quoted ACROSS THE SPEC'S LINE WRAP. A span lifted from a
        # wrapped paragraph carries the wrap, so a byte-exact comparison would
        # refuse the honest quotation and teach the extractor to quote single
        # words instead of sentences.
        "spans": ["the FSM advances\nto LREFILL3"],
    }
    entry.update(kw)
    return entry


def test_a_valid_probe_is_accepted() -> None:
    assert probe_issues([_probe()], SPEC) == []


def test_b_a_probe_must_be_one_bit() -> None:
    """A wider probe would need an encoding the specification never states.

    That is the defect that broke ten checks through `cmd`, and it has a second
    edge here: the witness holds the state as a string and the RTL as an integer,
    so only a boolean means the same thing on both sides.
    """
    issues = probe_issues([_probe(width=2)], SPEC)
    assert [i.path for i in issues] == ["io[0].width"]


def test_c_a_probe_no_requirement_licenses_is_refused() -> None:
    issues = probe_issues([_probe(licensed_by=[])], SPEC)
    assert [i.path for i in issues] == ["io[0].licensed_by"]


def test_d_a_span_must_be_in_the_specification() -> None:
    """The load-bearing rule: quoted, never paraphrased."""
    issues = probe_issues([_probe(spans=["the FSM advances to CRESET"])], SPEC)
    assert [i.path for i in issues] == ["io[0].spans"]
    assert "not in the specification" in issues[0].message


def test_e_two_probes_quoting_one_sentence_WARNS_and_does_not_refuse() -> None:
    """Demoted from an error, on measurement rather than on caution.

    It was written to catch the collapse failing -- three phrasings of one state
    shipped as three probes. It CANNOT: three phrasings carry three different
    spans, so a same-span test never sees them. What it does catch is one
    sentence naming two distinct signals, which is ordinary English and ordinary
    hardware.

    Run against k1 it fired twice, and both tables were right: "either the store
    or load flag is set" licenses `store_flag` and `load_flag`, and a sentence
    about decrementing `cnt` inside the refill state licenses both `in_lrefill3`
    and `cnt_nonzero`. Two of two honest cases blocked, none of its target case
    caught.

    Kept as a warning: a reviewer reading the stage's report can still use it as
    weak evidence of a duplicate. What actually prevents two names for one thing
    is the merged single call, with the orphan report as its backstop.
    """
    issues = probe_issues([_probe(), _probe(name="in_refilling")], SPEC)
    assert [i.path for i in issues] == ["io[1].spans"]
    assert [i.severity for i in issues] == ["warning"]
    assert not any(i.severity == "error" for i in issues), (
        "a shared sentence must not block an otherwise valid table")


def test_f_a_config_hypothesis_needs_its_own_span() -> None:
    """A config key existing is not the specification stating a dependency.

    This is the one thing a probe may say about a design, and it is a hypothesis
    rather than a verdict: it exists so a later PROOF of unreachability reads as
    "legitimately absent" instead of "the design is missing a required state".
    Letting it be inferred from a key would be inferring a design fact from spec
    text before any design exists.
    """
    gated = {"key": "OR1200_DC_STORE_REFILL", "value": False}
    entry = _probe(name="in_srefill4",
                   spans=["the SREFILL4 state does not exist"],
                   config_gated=gated)
    assert [i.path for i in probe_issues([entry], SPEC)] == ["io[0].config_gated"]

    stated = dict(gated, span="Store-miss refill is present only when "
                              "OR1200_DC_STORE_REFILL is defined")
    assert probe_issues([_probe(name="in_srefill4",
                                spans=["the SREFILL4 state does not exist"],
                                config_gated=stated)], SPEC) == []


def _contract(*extra: dict) -> str:
    """The linter reads contract JSON TEXT, which is what a stage hands it."""
    return json.dumps({
        "source_of_truth": "spec",
        "module_name": "or1200_dc_fsm",
        "io": [
            {"name": "clk", "dir": "input", "width": 1},
            {"name": "burst", "dir": "output", "width": 1},
            *extra,
        ],
        "clocking": {"is_sequential": True,
                     "clock": {"name": "clk", "edge": "posedge"}},
    })


def test_g_the_linter_accepts_a_contract_carrying_a_probe() -> None:
    """The whole point of step 1: this is the one hard blocker.

    Before this, `lint_contract_json` emitted an `error` for any `dir` outside
    the three Verilog directions, so no stage downstream could be tried at all.
    """
    issues, _ = lint_contract_json(_contract(_probe()))
    assert [i.message for i in issues if i.severity == "error"] == []


def test_g_a_probe_does_not_join_the_outputs_set() -> None:
    """`outputs` feeds the spec-header cross-check, and headers have no probes.

    A specification's module header declares the ports the module was written
    with. A probe is a term its PROSE uses. Counting one as an output would
    report every probe as a port the contract has and the header lost.
    """
    with_probe, _ = lint_contract_json(_contract(_probe()), spec=SPEC)
    without, _ = lint_contract_json(_contract(), spec=SPEC)
    assert [i.message for i in with_probe] == [i.message for i in without]


def test_an_unknown_direction_is_still_refused() -> None:
    """Widening the set must not have opened it."""
    issues, _ = lint_contract_json(_contract({"name": "x", "dir": "wire", "width": 1}))
    assert any(i.path == "io[2].dir" for i in issues if i.severity == "error")
    assert PORT_DIRECTIONS == {"input", "output", "inout", "probe"}


def test_no_other_site_refuses_a_probe() -> None:
    """The linter is the ONLY hard blocker, which is what makes this cheap.

    Roughly fifteen sites re-derive a port list inline with a direction test, and
    a probe fails every one of them -- so it is excluded by DEFAULT and each
    inclusion is deliberate. The two that test the three-direction set outside
    this module (`asserter`, `boolean_proofer`) must SKIP a probe, never reject
    it: a shipped assertion and a boolean miter both compare against golden RTL,
    which has no probes at all.
    """
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "eda_agent").glob("*.py")) + \
            sorted((root / "specflow").rglob("*.py")):
        if path.name == "contract_linter.py":
            continue
        lines = path.read_text().splitlines()
        for n, line in enumerate(lines):
            if 'not in {"input", "output", "inout"}' not in line:
                continue
            # `continue` on the next line is a skip; anything else is a refusal.
            nxt = lines[n + 1].strip() if n + 1 < len(lines) else ""
            if nxt != "continue":
                offenders.append(f"{path.relative_to(root)}:{n + 1} -> {nxt}")
    assert offenders == []
