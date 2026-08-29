"""The feedback edge for a check nothing could satisfy.

This handles the other direction -- a check a debug loop spent its whole turn
budget on, that a second implementation of the same requirement also fails.

Measured on s-i2c: the loop drove VIOLATES 15 -> 9, and 7 of the 9 it could not
clear are checks the known-good control ALSO fails. Those 7 block G4, which is
why a reference model scoring the best separation of the series -- 57/168 at
+24, the first positive one -- produced no RTL at all. The residue was the
checks, not the design, and nothing sent them anywhere.
"""

from __future__ import annotations


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


# ------------------------------------------------- the two edges are separate


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


# ------------------------------------------------- one loop, the same tools
#
# A strengthening round is the oracle stage SCOPED, not a smaller copy of it.
# It used to dispatch to `_strengthen`, which reimplemented a subset -- one
# generation, one verify, keep-or-revert -- so the second iteration of the
# refmodel/oracle loop ran on strictly weaker instruments than the first, and
# WHICH instruments it lost was decided by which keyword arguments a call site
# in `compose` happened to pass.


def test_there_is_only_one_oracle_stage():
    """The separate path is gone, not merely bypassed."""
    from specflow import oracles_stage

    assert not hasattr(oracles_stage, "_strengthen")


def test_a_scoped_round_inherits_the_instruments_rather_than_being_told_them():
    """Read off the set being strengthened, so a caller that forgets a flag
    does not get a quieter round -- it gets the same round."""
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    body = src[src.index("scoped = set(reconsider"):]
    for flag in ("correspondence", "variants", "staging",
                 "max_repairs", "repair_attempts"):
        assert f'inherited.get("{flag}"' in body, flag


def test_the_set_records_what_it_was_built_with():
    from specflow.oracles_stage import OracleSet

    assert OracleSet().tools == {}


def test_variants_are_inherited_on_a_scoped_round_never_redrawn():
    """A variant is a wrong implementation of ONE requirement and the
    requirement has not changed. A different draw would convict an oracle
    vacuous this round and clear it next for no reason anyone could name --
    the same argument `_witness` makes for reading itself back."""
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    assert "list(previous.variants) if only and previous" in src
    # Three conditions now guard the draw, and the last one is what makes
    # "once" survive the process rather than only the round: whatever is
    # already on disk wins over generating a second draw.
    assert "if want_variants and witness and not only and not variants:" in src
    assert "variants = variants_mod.load(variants_path)" in src


# ------------------------------------------------------- the adequacy gate


