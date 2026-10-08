"""Step 6: the check author can say what the specification says.

Three edits, ten lines between them, and they carry the whole measured effect:
on the 11 k1 requirements whose bodies use a probe, checks went 0 of 11 to 5 of
11 on "fires and never convicts a correct design" (p = 0.0074). Everything else
in the probe architecture is plumbing that makes these three true.
"""
from __future__ import annotations

import json

import pytest

from specflow.normalize import NormalizeOutput, gate_one
from specflow.refmodel.oracle_gen import shared_prefix
from specflow.refmodel.oracles import RequirementOracle, well_formed

CONTRACT = {"module_name": "dcfsm", "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "tagcomp_miss", "dir": "input", "width": 1},
    {"name": "burst", "dir": "output", "width": 1},
    {"name": "in_lrefill3", "dir": "probe", "width": 1,
     "notes": "the FSM is in the state the specification calls LREFILL3",
     "licensed_by": ["REQ-0017"],
     "spans": ["the FSM advances to LREFILL3"]},
], "clocking": {"is_sequential": True,
                "clock": {"name": "clk", "edge": "posedge"}}}

PLAIN = {**CONTRACT,
         "io": [p for p in CONTRACT["io"] if p.get("dir") != "probe"]}


def test_the_author_is_told_the_probe_exists_and_what_it_means() -> None:
    """The measured intervention. Without this block nothing else pays."""
    prompt = shared_prefix("{}", CONTRACT, spec="")
    assert "in_lrefill3" in prompt
    # Its meaning IN THE SPECIFICATION'S OWN WORDS -- the author is not asked to
    # infer what the name refers to.
    assert "the FSM advances to LREFILL3" in prompt
    # And that it is read like any other signal.
    assert 'row["outputs"]' in prompt


def test_a_contract_with_no_probes_says_nothing_about_them() -> None:
    """No probe block, no probe paragraph, no changed digest for a plain run."""
    assert "probe" not in shared_prefix("{}", PLAIN, spec="").lower()


def test_the_prompt_states_the_default_AND_the_override() -> None:
    """Measured both ways, and neither extreme is what ships.

    Made absolute, the scope rule refuses the transition obligations that are
    most of what this kind of specification says. Dropped entirely, authors
    asserted on probes freely and the count of checks passing because they
    cannot fail DOUBLED. The default with an override did neither.
    """
    prompt = shared_prefix("{}", CONTRACT, spec="")
    assert "SCOPE A WINDOW WITH A PROBE FREELY" in prompt
    assert "PREFER A DECLARED OUTPUT FOR WHAT YOU ASSERT" in prompt
    assert "quote those words" in prompt
    # And that a probe is not drivable, which `ports.py` enforces structurally.
    assert "never an input" in prompt


def _norm(**fields) -> NormalizeOutput:
    base = {"req_uid": "REQ-0017", "activation": {
                "text": "on tagcomp_miss the FSM advances to LREFILL3",
                "inputs": {}, "opens_on": [], "until": [], "aborts_on": [],
                "sustains": [], "effect_follows": "same_edge"},
            "observable": ["burst"],
            # A route is demanded for an OUTPUT, which is unrelated to probes
            # and predates them. Supplied so these tests measure the probe
            # edits rather than this rule.
            "observed_via": [{"port": "burst", "through_req": "",
                              "shows": "burst rises on the refill and stays "
                                       "high until the last word",
                              "otherwise": "burst stays low for a hit, which "
                                           "is what distinguishes the two",
                              "when": "from the edge tagcomp_miss is sampled "
                                      "until the final refill word"}],
            "expectation": "burst is asserted"}
    base.update(fields)
    return NormalizeOutput.model_validate({"reasoning": "r", "normalized": [base]})


REQ = {"uid": "REQ-0017", "text": "on tagcomp_miss the FSM advances to LREFILL3"}


def test_a_window_may_open_on_a_DECLARED_probe() -> None:
    out = _norm(activation={**_norm().normalized[0].activation.model_dump(),
                            "opens_on": [{"in_lrefill3": 1}]})
    assert gate_one(REQ, out, CONTRACT) == []


def test_a_window_may_NOT_open_on_an_undeclared_name() -> None:
    """The existing rejection still does the work; no new gate was added.

    `_ports(contract, "probe")` puts declared probes into the lookup, and
    everything else falls through to the refusal that was always there.
    """
    out = _norm(activation={**_norm().normalized[0].activation.model_dump(),
                            "opens_on": [{"in_lrefill3": 1}]})
    issues = gate_one(REQ, out, PLAIN)
    assert issues, "an undeclared name must still be refused"
    assert any("in_lrefill3" in i.message for i in issues)


def test_a_probe_may_be_the_observable_when_declared() -> None:
    """A transition obligation states its effect ON the state.

    Refusing this would make the scope rule absolute by the back door, and would
    refuse exactly the requirements probes exist for.
    """
    # No `observed_via`: a probe is the requirement's own noun, so there is no
    # indirection to explain and none is demanded.
    only_probe = _norm(observable=["in_lrefill3"], observed_via=[])
    assert gate_one(REQ, only_probe, CONTRACT) == []
    assert gate_one(REQ, only_probe, PLAIN) != []


def test_an_OUTPUT_observable_still_needs_its_route() -> None:
    """The route rule is scoped, not removed.

    It explains how a port the requirement does not name shows the effect it
    does. That question is still real for an output, and probes do not answer it.
    """
    assert gate_one(REQ, _norm(observed_via=[]), CONTRACT) != []
    assert gate_one(REQ, _norm(observable=["burst", "in_lrefill3"],
                               observed_via=[]), CONTRACT) != []


BODY = ("def decide(trace):\n"
        "    for r in trace:\n"
        "        if r['outputs'].get('in_lrefill3'):\n"
        "            return (True, r['edge'], 'in LREFILL3')\n"
        "    return (None, None, 'never entered')\n")


def test_well_formed_accepts_a_check_whose_effect_is_a_probe() -> None:
    """`_declared_outputs` is the one place the default had to widen."""
    oracle = RequirementOracle(req_uid="REQ-0017", clause="", source=BODY,
                               tp_uids=["TP-0000"])
    plan = [{"uid": "TP-0000", "covers": ["REQ-0017@1"]}]
    assert well_formed(oracle, CONTRACT, plan) is None
    # Without the declaration it is refused, which is what makes the acceptance
    # above mean something.
    assert well_formed(oracle, PLAIN, plan) is not None


def test_normalize_is_untouched_where_the_plan_says_it_is() -> None:
    """`reaching`, `Reach`, `gate_indirect`, `indirect_prefix`,
    `resolve_indirect` are not read by any of this and are not edited.

    The claim matters because the staging change deliberately does NOT use the
    prerequisite chain those build. Adjacency for a state nothing has reached is
    the stimulus author's call, decided from the specification with every
    reachable prefix in view -- there is no mechanical source for it, and a
    depth heuristic picks the wrong branch on a fork. If this list starts being
    read, that claim needs re-examining rather than quietly widening.
    """
    import subprocess

    out = subprocess.run(
        ["git", "diff", "origin/agent-hardening-probes", "--", "specflow/normalize.py"],
        capture_output=True, text=True, cwd="/home/user/Veri-Sure").stdout
    touched = [ln for ln in out.splitlines()
               if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    for name in ("def reaching", "class Reach", "def gate_indirect",
                 "def indirect_prefix", "def resolve_indirect"):
        assert not any(name in ln for ln in touched), (name, touched[:5])


def test_the_probe_block_neutralises_the_SYSTEM_rule_it_contradicts() -> None:
    """The measured cause of 12-of-12 de-probing on a repair round.

    `SYSTEM` carries a standing rule -- "Internal signals are not in the trace"
    -- and this block described a probe as "an internal flag". Both are in
    every probe-bearing prompt. On a first shot the block won: 29 of 34 k1
    bodies named a probe. On a repair round, where the author is told its check
    is defective and re-reads the rules for a reason, the rule won: 12 of 12
    repaired bodies deleted every probe, four of them while answering a pure
    syntax error, reporting it as "removed references to non-existent internal
    probes".

    A failure means the two statements are back to contradicting each other,
    and a probe survives generation but not repair -- which puts the check back
    on the output proxy the whole architecture exists to remove.
    """
    prompt = shared_prefix("{}", CONTRACT, spec="")
    assert "Internal signals are" in prompt and "not in the trace" in prompt
    assert "DOES NOT APPLY to these" in prompt
    assert "sampled into every row" in prompt


def test_the_override_is_absent_when_no_probe_is_declared() -> None:
    """It corrects a collision that a probe-free prompt does not have.

    The rule alone is true when nothing is declared, so saying otherwise would
    change the cached prefix of every existing design to answer a question it
    never asks. `test_a_contract_with_no_probes_says_nothing_about_them` is the
    general form; this names the specific sentence.
    """
    assert "DOES NOT APPLY to these" not in shared_prefix("{}", PLAIN, spec="")


def test_a_probe_is_INSIDE_the_declared_ports_object() -> None:
    """Placement, not prose. The triage that forced this is worth stating.

    `SYSTEM` says "Read only DECLARED PORTS out of `outputs` and `inputs`".
    Probes used to be appended AFTER that object closed, so an author checking
    whether `in_cload` was a declared port looked in those two keys, did not
    find it, and was right. Six of twelve k1 repair rounds deleted a probe
    saying exactly that -- "not a declared port", "undefined port in_cload",
    "since FSM state is internal". A paragraph contradicting the layout was
    tried first and moved the drop rate 12 -> 11; a third key is the fix.

    A failure means the rule's own two-key test excludes probes again, and no
    amount of surrounding prose will stop an author acting on it.
    """
    import json as _json
    import re as _re
    prompt = shared_prefix("{}", CONTRACT, spec="")
    block = _re.search(r"<declared_ports>\n(\{.*?\n\})", prompt, _re.S)
    assert block, "the declared-ports JSON object is not where it was"
    ports = _json.loads(block.group(1))
    assert "probes" in ports, sorted(ports)
    assert [p["name"] for p in ports["probes"]] == ["in_lrefill3"]
    # And it is NOT smuggled into the two keys the output-only gates read.
    assert all(p["name"] != "in_lrefill3"
               for p in ports.get("outputs", []) + ports.get("inputs", []))


def test_a_probe_free_contract_still_has_exactly_two_keys() -> None:
    """The third key appears only when there is something to put in it.

    A failure means every existing probe-free design's cached prefix changed to
    carry an empty list, for nothing.
    """
    import json as _json
    import re as _re
    block = _re.search(r"<declared_ports>\n(\{.*?\n\})",
                       shared_prefix("{}", PLAIN, spec=""), _re.S)
    assert block and "probes" not in _json.loads(block.group(1))


def test_the_probe_block_answers_the_held_input_problem() -> None:
    """The one place Class A can be stated as a POSITIVE rather than a warning.

    An input is held by the stimulus; a probe is true exactly while the
    situation is. That makes the probe the FIX for the held-input false alarm,
    which is worth saying where the probes are introduced.
    """
    prompt = shared_prefix("{}", CONTRACT, spec="")
    assert "ANSWER TO A HELD INPUT" in prompt
    assert "not held by anybody" in prompt


def test_the_held_input_answer_is_absent_without_probes() -> None:
    """It names probes as the remedy, so it cannot appear where there are none
    -- and the probe-free prefix must stay byte-identical for the cache."""
    assert "ANSWER TO A HELD INPUT" not in shared_prefix("{}", PLAIN, spec="")


# --- the rows an author is shown ------------------------------------------
#
# The author had never seen a row. `build_prompt` takes a requirement, a
# contract, a specification and a normalized form, and out of that it writes
# `trace[i + 1]` against a row list whose unit it cannot know. These pin the
# provenance rule and the shape of what it is now shown.

def _rows(n: int, *, moving_from: int = 2) -> list[dict]:
    out = []
    for i in range(n):
        out.append({
            "edge": i, "held": 1 if i >= moving_from else 3,
            "inputs": {"req": 1 if i else 0},
            "outputs": {"ack": 1 if i >= moving_from else 0},
        })
    return out


def test_rows_from_anything_but_the_witness_are_refused():
    """The one parameter that carries a trace refuses golden BY TYPE.

    A failure means the author could be handed the design under test, which
    is the control leak `oracles_stage` holds out as the grade.
    """
    from specflow.refmodel.oracle_gen import WitnessRows

    WitnessRows(by_tp={"TP-0001": _rows(4)})          # the witness is fine
    with pytest.raises(ValueError) as exc:
        WitnessRows(by_tp={"TP-0001": _rows(4)}, origin="golden")
    assert "witness" in str(exc.value)


def test_the_block_shows_a_contiguous_window_that_starts_at_the_activity():
    """Contiguous, never sampled, and never the idle prefix.

    A check compares row i against row i-1, so a scattered sample destroys the
    structure the rows are being shown to convey; and an author shown only the
    quiet opening of a testpoint learns nothing it did not already assume.
    """
    from specflow.refmodel.oracle_gen import WitnessRows, witness_rows_block

    rows = _rows(30, moving_from=10)
    block = witness_rows_block(WitnessRows(by_tp={"TP-0001": rows}), per_tp=5)
    shown = json.loads(block.split("<witness_rows>")[1].split("</witness_rows>")[0])
    edges = [r["edge"] for r in shown[0]["rows"]]
    assert edges == [9, 10, 11, 12, 13], edges
    assert shown[0]["rows_in_full"] == 30
    assert all("held" in r for r in shown[0]["rows"])


def test_the_block_says_what_held_means_because_that_is_the_whole_point():
    """`held` is the fact the author was missing, so the prose must state it.

    Four rows in five hold a single clock edge and the rest absorb up to two
    thousand; without that sentence the number is decoration.
    """
    from specflow.refmodel.oracle_gen import WitnessRows, witness_rows_block

    block = witness_rows_block(WitnessRows(by_tp={"TP-0001": _rows(6)}))
    assert "clock edge" in block
    assert "next row" in block


def test_a_prompt_without_rows_is_byte_identical_to_before():
    """The default changes nothing, so no cached prefix and no arm moves.

    A failure means landing this altered every existing prompt, which would
    make every before/after comparison in the experiment series incomparable.
    """
    from specflow.refmodel.oracle_gen import build_prompt

    req = {"uid": "REQ-0001", "text": "ack rises after req"}
    contract = {"io": [{"name": "req", "dir": "input", "width": 1},
                       {"name": "ack", "dir": "output", "width": 1}]}
    cj = json.dumps(contract, indent=2, sort_keys=True)
    assert (build_prompt(requirement=req, contract_json=cj, contract=contract)
            == build_prompt(requirement=req, contract_json=cj, contract=contract,
                            rows=None))


def test_the_rows_reach_the_prompt_when_they_are_given():
    from specflow.refmodel.oracle_gen import WitnessRows, build_prompt

    req = {"uid": "REQ-0001", "text": "ack rises after req"}
    contract = {"io": [{"name": "req", "dir": "input", "width": 1},
                       {"name": "ack", "dir": "output", "width": 1}]}
    cj = json.dumps(contract, indent=2, sort_keys=True)
    p = build_prompt(requirement=req, contract_json=cj, contract=contract,
                     rows=WitnessRows(by_tp={"TP-0001": _rows(6)}))
    assert "<witness_rows>" in p and "TP-0001" in p
