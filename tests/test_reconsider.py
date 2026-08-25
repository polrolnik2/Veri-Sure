"""The feedback edge for a check nothing could satisfy.

`_strengthen` handles a check something provably wrong got past: tighten it.
This handles the other direction -- a check a debug loop spent its whole turn
budget on, that a second implementation of the same requirement also fails.

Measured on s-i2c: the loop drove VIOLATES 15 -> 9, and 7 of the 9 it could not
clear are checks the known-good control ALSO fails. Those 7 block G4, which is
why a reference model scoring the best separation of the series -- 57/168 at
+24, the first positive one -- produced no RTL at all. The residue was the
checks, not the design, and nothing sent them anywhere.
"""

from __future__ import annotations

import re

import json

from specflow import oracles_stage as O
from specflow.refmodel import verdict
from specflow.refmodel.oracles import RequirementOracle

from tests.test_oracles_stage import (
    CONTRACT, GOOD, STIM, TESTPLAN, WITNESS, _Port, _reply,
)

REQS = [{"uid": "REQ-0001", "text": "y follows a"}]

#: Demands something no implementation provides.
IMPOSSIBLE = (
    "def decide(trace):\n"
    "    return (False, 0, 'no design satisfies this')\n"
)


def _previous(source: str) -> O.OracleSet:
    return O.OracleSet(
        trusted=[RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                                   clause="y follows a", source=source)],
        dispositions={"REQ-0001": O.TRUSTED},
        witness_notes={"REQ-0001": "could not satisfy it either"},
    )


def _run(previous, port, tmp_path, **kw):
    return O.run_oracle_stage(
        requirements=REQS, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=TESTPLAN, stimulus_by_tp=STIM,
        port=port, workdir=tmp_path, base="step", run_dir=tmp_path,
        fanout=False, max_repairs=0, previous=previous, **kw)


def test_a_check_nothing_satisfies_is_re_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    got = _run(_previous(IMPOSSIBLE), port, tmp_path,
               reconsider={"REQ-0001": "could not satisfy it either"})

    asked = [p for p in port.prompts if "Nothing has been able to satisfy" in p]
    assert asked, "the author is never told"
    assert "spent its entire turn budget" in asked[0]
    assert got.trusted[0].source != IMPOSSIBLE, "the replacement was taken"
    assert "reconsidered" in got.reasons["REQ-0001"]


def test_the_author_may_keep_the_check(tmp_path, monkeypatch):
    """Two implementations can be wrong the same way, and that is exactly the
    case a check like this exists to catch. When this disagreement could
    REJECT, over-strictness fell 27 -> 15 while convictions rose 2 -> 16 --
    checks relaxed until they stopped disagreeing."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    _run(_previous(IMPOSSIBLE), port, tmp_path,
         reconsider={"REQ-0001": "could not satisfy it either"})
    asked = [p for p in port.prompts if "Nothing has been able to satisfy" in p][0]
    assert "YOU MAY CHOOSE IT" in asked
    assert "KEEP IT AS IT IS" in asked
    assert "Nothing is rejected for that" in asked


def test_a_relaxation_that_goes_vacuous_leaves_the_previous_check_standing(
        tmp_path, monkeypatch):
    """The guard that makes the exit safe. Relaxing until nothing disagrees is
    the compliance ratchet; a replacement that stops deciding anything fails
    `verify_one` and does not get promoted for being eager."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    monkeypatch.setattr(
        O, "verify_one",
        lambda *a, **k: ("vacuous: demands nothing", True, {}))
    port = _Port([_reply("def decide(trace):\n    return True, 0, 'ok'\n")])
    got = _run(_previous(IMPOSSIBLE), port, tmp_path,
               reconsider={"REQ-0001": "could not satisfy it either"})
    assert got.trusted[0].source == IMPOSSIBLE, (
        "a vacuous replacement must not overwrite the check it replaced")
    assert "the previous oracle stands" in got.reasons["REQ-0001"]


def test_only_a_violates_qualifies_for_this_edge():
    """A NOT_EXERCISED is the stimulus's and an ORACLE_INVALID already went
    through the stage's own repair loop. Neither is a check two implementations
    could not satisfy, and re-asking either spends a call to learn nothing."""
    issues = [verdict.to_issue("REQ-0001", "VIOLATES", ""),
              verdict.to_issue("REQ-0002", "NOT_EXERCISED", ""),
              verdict.to_issue("REQ-0003", "VACUOUS", ""),
              verdict.to_issue("REQ-0004", "ORACLE_INVALID", "")]
    got = {i.path.split(".")[1] for i in issues
           if i.path.startswith("refmodel.") and i.path.endswith(".violates")}
    assert got == {"REQ-0001"}


def test_the_two_edges_carry_different_reasons(tmp_path, monkeypatch):
    """One says tighten, the other says you may have over-tightened. Sending
    the wrong one is how an oscillation becomes a ratchet."""
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    _run(_previous(IMPOSSIBLE), port, tmp_path,
         strengthen={"REQ-0001": "cannot tell two designs apart. Both pass it, "
                     "and they differ:\n    edge 3: y is 1 in one and 0 in the "
                     "other\n  One of them violates this requirement."})
    tighten = [p for p in port.prompts if "tighten the check" in p]
    assert tighten and "Nothing has been able to satisfy" not in tighten[0]


def test_the_tighten_edge_never_quotes_a_design(tmp_path, monkeypatch):
    """Invariant I1, on the one path that had been quietly breaking it.

    `oracle_gen.build_prompt` "has no parameter that could carry a design", but
    the inadequacy edge was passing `Finding.detail` -- "survived line 21: True
    becomes False" -- which is a line number in the reference model. The author
    cannot see that file, so it could not aim, and measured over t-i2c's 51
    calls and w-i2c's 21 it never moved one oracle to adequate; every rejection
    read `vacuous`, meaning it answered by writing a WEAKER check.

    The counterexample has to be traces: ports and edges, which is what the
    oracle's own `decide` reads. And NEITHER TRACE MAY BE LABELLED CORRECT --
    naming it hands the author the reference model's behaviour to write
    against, which is the same defect as repairing an oracle from a control,
    with the loop closed tighter.
    """
    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    _run(_previous(IMPOSSIBLE), port, tmp_path,
         strengthen={"REQ-0001": "cannot tell two designs apart. Both pass it, "
                     "and they differ:\n    edge 3: y is 1 in one and 0 in the "
                     "other\n  One of them violates this requirement."})
    tighten = [p for p in port.prompts if "tighten the check" in p]
    assert tighten, "the strengthening prompt was never sent"
    sent = tighten[0]
    assert "edge 3" in sent, "the counterexample must reach the author"
    # The feedback block only. "line" is an ordinary word in the base prompt --
    # "active-low line", "a flat line" -- and asserting on the bare word pins
    # prose instead of the property.
    block = sent.split("<gate_failures>")[1].split("</gate_failures>")[0]
    assert not re.search(r"line \d+", block), (
        f"a source line reference points into a file I1 forbids the author "
        f"from seeing: {block!r}")
    assert "Do not assume either trace is the correct one." in sent


# ------------------------------------------------- the two edges are separate


def test_the_two_edges_are_gated_apart():
    """Running both in one round makes them fight, and the net is zero.

    Measured on t-i2c, which ran both: `strengthen` tightened 5 oracles and
    `reconsider` relaxed 7, and the set's over-strictness did not move -- 15
    checks failed a known-good control before the round and 15 after, two fixed
    (REQ-0014, REQ-0024) and two newly created (REQ-0003, REQ-0005).

    `strengthen` is what MANUFACTURES over-strictness: tighten until you catch
    this mutant, and a check tightened past what the requirement states is
    exactly a check no correct design satisfies. Relaxing alone is the move
    that can unblock a gate, and it cannot be tested while something else is
    tightening underneath it.
    """
    import inspect

    from specflow.refmodel import compose

    sig = inspect.signature(compose._closed_loop).parameters
    assert "adequacy_rounds" in sig and "reconsider_rounds" in sig
    assert sig["reconsider_rounds"].default == 0, "off until measured alone"

    body = inspect.getsource(compose._closed_loop)
    # Each edge is silenced by its OWN counter, not by the other's.
    assert "if not int(reconsider_rounds) or round_ >= int(reconsider_rounds)" in body
    assert "if not int(adequacy_rounds) or round_ >= int(adequacy_rounds)" in body
    assert "feedback_rounds = max(0, int(adequacy_rounds), int(reconsider_rounds))" in body


def test_the_switch_reaches_the_command_line():
    """A switch that stops at an internal function cannot be measured."""
    import inspect

    from eda_agent.top_agent import __file__ as top
    from specflow import integration

    assert "reconsider_rounds" in inspect.signature(
        integration.build_artifacts).parameters
    assert "specflow_reconsider_rounds" in open(top).read()
    assert "--reconsider-rounds" in open(
        "benchmarks/run_chipverilog.py").read()


# ------------------------------------------ the tighten edge, end to end


def test_a_strengthened_check_that_catches_the_mutant_is_taken_and_is_adequate(
        tmp_path, monkeypatch):
    """The whole tighten edge on one oracle, with no model call.

    The edge has run live twice and never once moved an oracle from inadequate
    to adequate -- t-i2c 51 calls, w-i2c 21 -- so before spending more on it,
    the PLUMBING is worth proving separately from the author: given a
    replacement that does catch what got past, does the round accept it, and
    does adequacy then agree?

    Scripting the reply is what isolates that. A live round tests the author
    AND the plumbing at once, and a null result cannot be attributed to either.
    """
    from specflow.refmodel import adequacy
    from tests.test_adequacy import CONTRACT as A_CONTRACT
    from tests.test_adequacy import FINAL, SHARP, STIM as A_STIM, WEAK, _oracle

    before = adequacy.assess([_oracle(WEAK)], FINAL, A_CONTRACT, A_STIM,
                             base="step")["REQ-0001"]
    assert before.verdict == adequacy.INADEQUATE, before
    assert "edge" in before.counterexample, before.counterexample

    monkeypatch.setattr(O, "_witness", lambda **_kw: (WITNESS, O.WITNESS))
    port = _Port([_reply(GOOD)])
    got = _run(_previous(IMPOSSIBLE), port, tmp_path,
               strengthen={"REQ-0001": before.counterexample})

    sent = [p for p in port.prompts if "tighten the check" in p]
    assert sent, "the tighten prompt never went out"
    assert "edge" in sent[0], "the trace counterexample has to reach the author"
    assert got.trusted[0].source != IMPOSSIBLE, (
        "a verifying replacement has to be taken, or the edge cannot ever work")
    assert "strengthened" in got.reasons["REQ-0001"], got.reasons

    # And the instrument agrees about the replacement, which is the half the
    # live runs never reached: SHARP reproduces the design's rule exactly, so
    # every mutant that changes y is caught.
    after = adequacy.assess([_oracle(SHARP)], FINAL, A_CONTRACT, A_STIM,
                            base="step")["REQ-0001"]
    assert after.verdict == adequacy.ADEQUATE, after
    assert after.counterexample == "", (
        "an adequate oracle has nothing to send a strengthening round")
