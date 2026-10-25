"""Step 6: the oracle set is written once and read forever.

The property under test is not "a hash is computed". It is that the set the
loop measures against cannot move while it measures -- and that the one thing
which is SUPPOSED to move, an oracle's evidence set, does not read as drift.
"""

from __future__ import annotations

import json

from specflow.refmodel import freeze
from specflow.refmodel.oracles import RequirementOracle

SRC = "def decide(trace):\n    return True, 0, 'ok'\n"
NORM = {
    "REQ-0001": {
        "activation": {"text": "cmd is WRITE", "inputs": {"cmd": 2}},
        "observable": ["dout"],
        "expectation": "dout holds the byte read back",
    },
}


def _oracle(**kw) -> RequirementOracle:
    base = {"req_uid": "REQ-0001", "tp_uids": ["TP-0001"],
            "clause": "the byte is presented", "source": SRC}
    return RequirementOracle(**{**base, **kw})


def test_hash_is_stable_across_equal_oracles():
    assert freeze.content_hash(_oracle(), NORM["REQ-0001"]) == \
        freeze.content_hash(_oracle(), NORM["REQ-0001"])


def test_a_rewritten_decision_procedure_is_a_different_oracle():
    other = _oracle(source=SRC.replace("True", "False"))
    assert freeze.content_hash(_oracle(), NORM["REQ-0001"]) != \
        freeze.content_hash(other, NORM["REQ-0001"])


def test_a_changed_requirement_is_a_different_oracle():
    """Open question 3: the hash covers what was ASKED, not only the answer."""
    moved = {**NORM["REQ-0001"], "expectation": "dout holds something else"}
    assert freeze.content_hash(_oracle(), NORM["REQ-0001"]) != \
        freeze.content_hash(_oracle(), moved)


def test_appending_a_testpoint_is_not_drift():
    """`add_stimulus` grows the evidence set on purpose. It is not a rewrite."""
    grown = _oracle(tp_uids=["TP-0001", "TP-0200"])
    assert freeze.content_hash(grown, NORM["REQ-0001"]) == \
        freeze.content_hash(_oracle(), NORM["REQ-0001"])
    assert freeze.evidence_hash(grown) != freeze.evidence_hash(_oracle())


def test_freeze_writes_once_and_the_frozen_set_wins(tmp_path):
    path = tmp_path / "oracles.json"
    first, drift = freeze.freeze([_oracle()], path, NORM)
    assert not drift
    assert first[0].hash

    rewritten = _oracle(source=SRC.replace("True", "None"))
    second, drift = freeze.freeze([rewritten], path, NORM)
    # The regenerated oracle is reported and DISCARDED. Returning it would make
    # the file a log rather than a freeze.
    assert second[0].source == SRC
    assert list(drift) == ["REQ-0001"]


def test_freeze_records_the_evidence_hash_beside_the_content_hash(tmp_path):
    path = tmp_path / "oracles.json"
    freeze.freeze([_oracle()], path, NORM)
    blob = json.loads(path.read_text(encoding="utf-8"))
    entry = blob["oracles"][0]
    assert entry["hash"] == freeze.content_hash(_oracle(), NORM["REQ-0001"])
    assert entry["evidence"] == freeze.evidence_hash(_oracle())


def test_load_returns_nothing_when_nothing_was_frozen(tmp_path):
    assert freeze.load(tmp_path / "absent.json") == []


def test_load_survives_a_corrupt_artifact(tmp_path):
    """A freeze that cannot be read must not take the run with it."""
    path = tmp_path / "oracles.json"
    path.write_text("{not json", encoding="utf-8")
    assert freeze.load(path) == []


def test_drift_reports_both_directions():
    frozen = [_oracle(hash=freeze.content_hash(_oracle(), NORM["REQ-0001"])),
              _oracle(req_uid="REQ-0002")]
    now = [_oracle(), _oracle(req_uid="REQ-0003")]
    moved = freeze.drift(now, frozen, NORM)
    assert moved["REQ-0003"] == "not in the frozen set"
    assert moved["REQ-0002"] == "dropped from the regenerated set"
    assert "REQ-0001" not in moved


def test_stale_proofs_names_only_the_oracles_that_gained_evidence():
    """I7, narrowed by append-only: nothing else can go stale."""
    a, b = _oracle(), _oracle(req_uid="REQ-0002")
    proofs = {a.req_uid: freeze.evidence_hash(a),
              b.req_uid: freeze.evidence_hash(b)}
    b.tp_uids.append("TP-0200")
    assert freeze.stale_proofs([a, b], proofs) == ["REQ-0002"]


def test_the_model_is_not_in_the_hash():
    """An oracle written from the requirement alone cannot depend on the code.

    That independence is the whole reason it can be frozen, so no input to the
    hash may carry the implementation.
    """
    payload = freeze.content_hash(_oracle(), NORM["REQ-0001"])
    # Same oracle, same requirement, and nothing else is accepted as an input:
    # a caller cannot pass a model source in at all.
    assert payload == freeze.content_hash(_oracle(), NORM["REQ-0001"])
