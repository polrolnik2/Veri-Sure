"""I6: making a requirement unverifiable is not progress.

The hazard is on the model side only. Appending stimulus cannot lose coverage --
nothing existing is edited -- but whether a scenario OCCURS is a joint property
of the stimulus and the design, so an edit that stops the model entering a state
un-fires an activation the stimulus still drives. The failing count drops, and
the requirement stops being checkable at all.
"""

from __future__ import annotations

import json

from specflow.refmodel import ratchet


def test_the_record_only_ever_grows(tmp_path):
    path = tmp_path / "exercised.json"
    ratchet.note(path, {"REQ-0001": "CONFORMS", "REQ-0002": "NOT_EXERCISED"})
    ratchet.note(path, {"REQ-0001": "NOT_EXERCISED", "REQ-0002": "VIOLATES"})
    assert ratchet.read(path) == {"REQ-0001", "REQ-0002"}


def test_a_requirement_that_stops_being_exercised_is_named(tmp_path):
    path = tmp_path / "exercised.json"
    assert ratchet.note(path, {"REQ-0001": "VIOLATES"}) == []
    assert ratchet.note(path, {"REQ-0001": "NOT_EXERCISED"}) == ["REQ-0001"]


def test_the_verdict_is_not_rewritten_to_buy_the_route(tmp_path):
    """A regressed oracle did not FAIL, it went silent. Both facts survive."""
    issues = ratchet.issues(["REQ-0001"])
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "stopped being exercised" in issues[0].message
    assert "REQ-0001" in issues[0].message


def test_no_regression_produces_no_issue():
    assert ratchet.issues([]) == []


def test_an_oracle_that_became_invalid_is_not_blamed_on_the_model(tmp_path):
    """ORACLE_INVALID and VACUOUS say nothing about the design reaching a
    state, so sending the repair loop after the model would be a false lead."""
    path = tmp_path / "exercised.json"
    ratchet.note(path, {"REQ-0001": "CONFORMS", "REQ-0002": "CONFORMS"})
    lost = ratchet.note(path, {"REQ-0001": "ORACLE_INVALID",
                               "REQ-0002": "VACUOUS"})
    assert lost == []


def test_a_requirement_that_was_never_exercised_cannot_regress(tmp_path):
    path = tmp_path / "exercised.json"
    ratchet.note(path, {"REQ-0001": "NOT_EXERCISED"})
    assert ratchet.note(path, {"REQ-0001": "NOT_EXERCISED"}) == []


def test_a_missing_file_is_an_empty_record_not_a_crash(tmp_path):
    assert ratchet.read(tmp_path / "absent.json") == set()


def test_a_corrupt_record_does_not_take_the_run_with_it(tmp_path):
    path = tmp_path / "exercised.json"
    path.write_text("{not json", encoding="utf-8")
    assert ratchet.read(path) == set()


def test_the_file_is_readable_and_sorted(tmp_path):
    path = tmp_path / "exercised.json"
    ratchet.note(path, {"REQ-0002": "CONFORMS", "REQ-0001": "VIOLATES"})
    assert json.loads(path.read_text())["exercised"] == ["REQ-0001", "REQ-0002"]


# ------------------------------------------------------------ inside the loop


def test_the_loop_blocks_a_turn_that_lost_an_activation(tmp_path):
    """The end-to-end property, over a model edited to stop reaching a state."""
    from specflow.refmodel import compose
    from specflow.refmodel.oracles import RequirementOracle

    contract = {"io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]}
    reaches = ("from specflow.refmodel.base import RefModel\n\n\n"
               "class Model(RefModel):\n"
               "    OUTPUT_PORTS = ['y']\n\n"
               "    def step(self, i):\n"
               "        return {'y': i['a']}\n")
    #: The same model with y nailed low: the clause's scenario stops occurring.
    inert = reaches.replace("i['a']", "0")
    # Fires only where y goes high, and fails there.
    oracle = RequirementOracle(
        req_uid="REQ-0001", tp_uids=["TP-0000"], clause="y rises",
        source="def decide(trace):\n"
               "    for row in trace:\n"
               "        if row['outputs']['y'] == 1:\n"
               "            return False, row['edge'], 'y rose but should not'\n"
               "    return None, None, 'y never rose'\n")

    class _Inert:
        def debug(self, session):
            return inert, 1, "nailed y low"

    _src, issues = compose._debug_turns(
        source=reaches, contract=contract, contract_json="{}",
        requirements=[{"uid": "REQ-0001", "text": "y rises"}],
        covers={"step": ["REQ-0001"]}, oracles=[oracle], base="step",
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0001@1"]}],
        stimulus_by_tp={"TP-0000": [{"a": 0}, {"a": 1}, {"a": 1}]},
        run_dir=tmp_path, debugger=_Inert(), max_turns=1,
        control_source=None, normalized=None, item_port=None,
    )
    blob = json.loads(
        (tmp_path / "specflow" / "judge" / "r1" / "trust.json").read_text())
    assert blob["regressed"] == ["REQ-0001"]
    assert any("stopped being exercised" in i.message for i in issues)
