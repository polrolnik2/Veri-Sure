"""End-to-end replay against a recorded fixture.

The fixture is a real VerilogEval-v2-EXT problem (Prob024_hadd) whose S1
response was produced once by a Claude subagent through `FilePort`. Replaying it
needs no model, so this runs in CI and is the regression net for the whole S1
path -- prompt composition, parsing, G1 and the loop -- against real spec text
rather than a hand-built fixture.

A Claude subagent is not the production model, so this records *a* model's
behaviour, not *the* model's. It pins the machinery, not prompt quality.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from specflow.model_io import ReplayPort
from specflow.s1_requirements import run_s1

FIXTURE = Path(__file__).parent / "fixtures" / "specflow" / "hadd"


def _run(tmp_path: Path):
    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract = (run_dir / "contract.json").read_text(encoding="utf-8")
    return run_s1(
        spec=spec,
        contract_json=contract,
        port=ReplayPort(root=run_dir / "agent_io"),
    )


def test_recorded_response_passes_g1_on_the_first_round(tmp_path):
    res = _run(tmp_path)
    assert res.ok, [i.message for i in res.issues]
    # One round: the gate accepted it outright, so no repair prompt was needed.
    assert res.rounds == 1


def test_decomposition_is_atomic_and_traceable(tmp_path):
    res = _run(tmp_path)
    reqs = res.output.requirements

    # A half adder has exactly two independent output behaviours. One
    # requirement would not be atomic; three would mean the spec was
    # over-decomposed.
    assert len(reqs) == 2

    # Each requirement must own its output port, which is what makes the
    # later requirement -> reference-model-method mapping mechanical.
    owned = {p for r in reqs for p in r.ports}
    assert {"sum", "cout"} <= owned

    for r in reqs:
        assert r.spec_spans, f"{r.uid} quotes no spec text"
        assert "testplan" in r.needs and "refmodel" in r.needs


def test_every_span_is_verbatim_spec_text(tmp_path):
    from specflow.s1_requirements import normalize_spec

    spec = normalize_spec((FIXTURE / "prompt.txt").read_text(encoding="utf-8"))
    res = _run(tmp_path)

    for r in res.output.requirements:
        for sp in r.spec_spans:
            assert spec[sp.start : sp.end] == sp.quote, f"{r.uid} span not verbatim"


def test_replay_is_deterministic(tmp_path):
    a = _run(tmp_path / "a")
    b = _run(tmp_path / "b")
    assert a.output.model_dump() == b.output.model_dump()


# --- the whole chain, S1 -> S2 -> S3 ---------------------------------------


def _chain(tmp_path: Path):
    from specflow.s2_testplan import run_s2
    from specflow.s3_coverage import run_s3

    run_dir = tmp_path / "run"
    shutil.copytree(FIXTURE, run_dir)
    spec = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    contract = (run_dir / "contract.json").read_text(encoding="utf-8")
    port = ReplayPort(root=run_dir / "agent_io")

    s1 = run_s1(spec=spec, contract_json=contract, port=port)
    reqs = [r.model_dump() for r in s1.output.requirements]
    s2 = run_s2(requirements=reqs, contract_json=contract, port=port)
    tps = [e.model_dump() for e in s2.output.elements]
    s3 = run_s3(testplan=tps, contract_json=contract, port=port)
    return s1, s2, s3


def test_all_three_gates_pass_on_the_recorded_chain(tmp_path):
    s1, s2, s3 = _chain(tmp_path)
    assert s1.ok, [i.message for i in s1.issues]
    assert s2.ok, [i.message for i in s2.issues]
    assert s3.ok, [i.message for i in s3.issues]


def test_every_requirement_reaches_a_check_transitively(tmp_path):
    """The property the whole chain exists to guarantee.

    Not "every bin names a requirement" -- that is the direction every surveyed
    system already has. This is the other one: every requirement derived from
    the spec ends up with something that can fail on its behalf.
    """
    s1, s2, s3 = _chain(tmp_path)

    reqs = {r.uid for r in s1.output.requirements}
    tp_by_req: dict[str, set[str]] = {}
    for e in s2.output.elements:
        for ref in e.covers:
            tp_by_req.setdefault(ref.split("@")[0], set()).add(e.uid)

    checked_tps = {ref.split("@")[0] for c in s3.output.checks for ref in c.covers}
    binned_tps = {ref.split("@")[0] for b in s3.output.bins for ref in b.covers}

    for req in reqs:
        tps = tp_by_req.get(req, set())
        assert tps, f"{req} reaches no testplan element"
        assert tps & checked_tps, f"{req} reaches no check"
        assert tps & binned_tps, f"{req} reaches no cover bin"


def test_no_check_compares_an_input(tmp_path):
    """A check on an input compares the stimulus against itself."""
    _, _, s3 = _chain(tmp_path)
    inputs = {"a", "b"}
    for c in s3.output.checks:
        assert not (set(c.signals) & inputs), f"{c.uid} checks an input"
