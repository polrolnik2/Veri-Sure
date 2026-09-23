"""Two bodies for one requirement are collapsed, and the scorecard must say so.

`score` keys checks by `req_uid`, so a caller passing more than one body for a
requirement keeps only the LAST and used to be told nothing. A sweep admitting
extra corpus bodies read as 122, 241 and 349 checks and was 122 every time --
blindness APPEARED to rise and `effective_size` to fall as separators were
added, which is not how adding separators behaves. That impossibility is the
only reason the collapse was noticed.

The model is the limit, not the note: blindness over a set with more than one
check per requirement is not computable here, so "fill the pool, then select"
cannot be measured by this function. Reporting is what ships; repairing it
means keying by a per-body identity while span keeps counting requirements,
which changes the headline numbers and wants a real run to validate.
"""

from specflow.scorecard import score

CONTRACT = {"io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 1}]}
REQS = [{"uid": f"REQ-{i:04d}", "unit_kind": "behavioural"} for i in (1, 2)]
NORM = [{"req_uid": r["uid"], "observable": ["q"]} for r in REQS]


def _body(uid, src):
    return {"req_uid": uid, "source": src, "tp_uids": ["TP-0000"], "clause": ""}


def _score(oracles):
    return score(oracles=oracles, normalized=NORM, stimulus_by_tp={},
                 contract=CONTRACT, population=[], requirements=REQS)


def test_one_body_each_says_nothing_about_collapse():
    card = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                   _body("REQ-0002", "def decide(t):\n    return True")])
    assert not any("DISCARDED" in n for n in card.notes)


def test_a_second_body_for_one_requirement_is_reported():
    card = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                   _body("REQ-0001", "def decide(t):\n    return False"),
                   _body("REQ-0002", "def decide(t):\n    return True")])
    said = " ".join(card.notes)
    assert "DISCARDED" in said, (
        "silently keeping the last body is what made a 349-body sweep read as "
        "349 checks when it was 122")
    assert "3 check bodies" in said and "2 requirement(s)" in said
    assert "1 were DISCARDED" in said


def test_the_note_warns_specifically_about_blindness():
    """Blindness is the figure a reader is most likely to misread here.

    Span and audit are per-requirement and survive the collapse unchanged.
    Blindness is the one a bigger pool is supposed to move, so it is the one a
    reader will take as evidence the pool worked.
    """
    card = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                   _body("REQ-0001", "def decide(t):\n    return False")])
    said = " ".join(card.notes)
    assert "blindness" in said.lower()
    assert "cannot be read as a property of the larger set" in said


def test_many_extra_bodies_are_counted_correctly():
    card = _score([_body("REQ-0001", f"def decide(t):\n    return {i}")
                   for i in range(5)])
    said = " ".join(card.notes)
    assert "5 check bodies" in said and "4 were DISCARDED" in said
