"""D6: every stage that made one batched call now makes one call per item.

Two things are asserted for all of them at once, because both failures are
silent:

* **C1 across every fanned-out stage** -- the prompts of one stage share a
  byte-identical prefix. Lose it and the stage costs ~30x while succeeding,
  validating and gating exactly as before.
* **uids are minted after the fan-out, never inside it** -- a uid assigned in a
  worker depends on completion order, and `--reuse` and the recorded fixtures
  both rely on identical inputs producing identical artifacts.
"""

from __future__ import annotations

import json
import os

import pytest

from specflow.fanout import PREFIX_SENTINEL, compose, json_block, shared_block
from specflow.s2_testplan import build_prompt_one as s2_prompt
from specflow.s2_testplan import run_s2_fanout
from specflow.s2_testplan import shared_prefix as s2_shared
from specflow.s3_coverage import build_prompt_one as s3_prompt
from specflow.s3_coverage import run_s3_fanout
from specflow.s3_coverage import shared_prefix as s3_shared

CONTRACT = json.dumps({
    "module_name": "TopModule",
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
        {"name": "cout", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": False},
    "timing": {"sum": {"latency_cycles": 0}, "cout": {"latency_cycles": 0}},
})
REQS = [
    {"uid": f"REQ-{i:04d}", "rev": 1, "text": f"Requirement {i}.",
     "ports": ["sum"], "needs": ["testplan", "refmodel"]}
    for i in range(6)
]
TPS = [
    {"uid": f"TP-{i:04d}", "rev": 1, "covers": [f"REQ-{i:04d}@1"], "dimension": "D1_data_boundary",
     "stimulus": "drive a", "expected_response": "sum follows", "check_method": "compare",
     "needs": ["bin", "check"]}
    for i in range(6)
]


class Scripted:
    """Replies by stage name, and records every prompt it was given."""

    def __init__(self, reply):
        self.reply = reply
        self.prompts: dict[str, str] = {}

    def complete(self, *, stage, round_, prompt):
        self.prompts[stage] = prompt
        return self.reply(stage, round_)


# ------------------------------------------------- C1 over every fanned stage


@pytest.mark.parametrize(
    "shared, prompts",
    [
        pytest.param(
            s2_shared(CONTRACT),
            [s2_prompt(r, CONTRACT) for r in REQS],
            id="s2_testplan",
        ),
        pytest.param(
            s3_shared(CONTRACT),
            [s3_prompt(e, CONTRACT) for e in TPS],
            id="s3_coverage",
        ),
    ],
)
def test_c1_a_fanned_stage_shares_a_byte_identical_prefix(shared, prompts):
    common = os.path.commonprefix(prompts)
    assert PREFIX_SENTINEL in common, "the shared block is not actually shared"
    assert all(p.startswith(shared) for p in prompts)
    assert len(common) >= 0.5 * len(prompts[0])


def test_json_block_is_key_order_stable():
    """An unsorted dump reorders between calls without changing meaning, and
    takes the cache with it."""
    a = json_block("x", {"name": "clk", "dir": "input"})
    b = json_block("x", {"dir": "input", "name": "clk"})
    assert a == b


def test_compose_puts_repair_material_after_the_item():
    from specflow.schema import Issue

    shared = shared_block(("system", "RULES"))
    plain = compose(shared, "<item>x</item>")
    repaired = compose(shared, "<item>x</item>",
                       issues=[Issue("error", "p", "m")], previous="{}")
    assert repaired.startswith(shared)
    assert repaired.index("<item>") < repaired.index("gate_failures")
    assert len(repaired) > len(plain)


# --------------------------------------------------------------- S2 fan-out


def test_s2_makes_one_call_per_requirement_and_renumbers_once():
    def reply(stage, round_):
        uid = stage.split("_", 1)[1]
        return json.dumps({"elements": [{
            "uid": "TP-9999", "rev": 1, "covers": [f"{uid}@1"], "dimension": "D1_data_boundary",
            "stimulus": "s", "expected_response": "e", "check_method": "c",
            "needs": ["bin", "check"],
        }]})

    port = Scripted(reply)
    merged, results = run_s2_fanout(
        requirements=REQS, contract_json=CONTRACT, port=port, fanout=False)

    assert set(port.prompts) == {f"s2_{r['uid']}" for r in REQS}
    assert all(r.ok for r in results), [i.message for r in results for i in r.issues]
    # Renumbered after the merge, in requirement order -- not by completion.
    assert [e.uid for e in merged.elements] == [f"TP-{i:04d}" for i in range(6)]


def test_s2_a_single_bad_requirement_does_not_poison_the_others():
    """The batched call's failure mode: one unparseable response cost every
    element. Here it costs one."""
    def reply(stage, round_):
        if stage.endswith("REQ-0003"):
            return "not json"
        uid = stage.split("_", 1)[1]
        return json.dumps({"elements": [{
            "uid": "TP-9999", "rev": 1, "covers": [f"{uid}@1"], "dimension": "D1_data_boundary",
            "stimulus": "s", "expected_response": "e", "check_method": "c",
            "needs": ["bin", "check"],
        }]})

    merged, results = run_s2_fanout(
        requirements=REQS, contract_json=CONTRACT, port=Scripted(reply),
        max_repairs=0, fanout=False)
    bad = [r for r in results if not r.ok]
    assert len(bad) == 1
    assert len(merged.elements) == 5


# --------------------------------------------------------------- S3 fan-out


def test_s3_makes_one_call_per_element_and_renumbers_once():
    def reply(stage, round_):
        uid = stage.split("_", 1)[1]
        return json.dumps({
            "bins": [{"uid": "BIN-9999", "covers": [f"{uid}@1"], "condition": "a is 1"}],
            "checks": [{"uid": "CHK-9999", "covers": [f"{uid}@1"],
                        "expr": "sum matches the model", "signals": ["sum"]}],
        })

    port = Scripted(reply)
    merged, results = run_s3_fanout(
        testplan=TPS, contract_json=CONTRACT, port=port, fanout=False)

    assert set(port.prompts) == {f"s3_{e['uid']}" for e in TPS}
    assert all(r.ok for r in results), [i.message for r in results for i in r.issues]
    assert [b.uid for b in merged.bins] == [f"BIN-{i:04d}" for i in range(6)]
    assert [c.uid for c in merged.checks] == [f"CHK-{i:04d}" for i in range(6)]


# The refmodel fan-out and its four tests are gone. Splitting *generation* was
# the wrong half to fan out: a reference model needs global context for
# execution order, reset priority and the state several requirements share, and
# per-requirement calls removed exactly that -- then `helpers` had to be deduped
# across calls that had never seen each other, which was the shape of the
# problem rather than a fix for it. The fan-out moved into the gate instead,
# where "does this model satisfy requirement N" is a local question with a local
# answer. See tests/test_specflow_judge.py.


# ------------------------------------------------- the divided arm end to end


def test_build_artifacts_can_run_the_divided_arm(tmp_path):
    """S1 by division, then fanned-out S2/S3/refmodel, all the way to a suite.

    Asserts the artifact shape is the *same* as the generative arm's, because
    every downstream stage, `--reuse` and the committed baselines all read
    `requirements.json` and must not care which arm wrote it.
    """
    from specflow.divide import divide
    from specflow.integration import build_artifacts

    spec = (
        "The sum output is the exclusive or of a and b.\n\n"
        "The cout output is the logical and of a and b.\n"
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "contract.json").write_text(CONTRACT, encoding="utf-8")
    units = divide(spec)

    def reply(stage, round_):
        if stage.startswith("boundary_"):
            # Every unit stands alone here, so the partition the classifier
            # sees is the scaffold `divide` produced.
            return json.dumps({"reasoning": "-", "continues_previous": False})
        if stage.startswith("classify_"):
            start = int(stage.split("_")[1])
            unit = next(u for u in units if u.start == start)
            port = "sum" if "sum" in unit.text(spec) else "cout"
            return json.dumps({
                "kind": "behavioural",
                "text": f"The {port} output is driven as specified.",
                "ports": [port],
            })
        if stage.startswith("s2_"):
            uid = stage.split("_", 1)[1]
            return json.dumps({"elements": [{
                "uid": "TP-9999", "rev": 1, "covers": [f"{uid}@1"],
                "dimension": "D1_data_boundary", "stimulus": "s",
                "expected_response": "e", "check_method": "c",
                "needs": ["bin", "check"]}]})
        if stage.startswith("s3_"):
            uid = stage.split("_", 1)[1]
            return json.dumps({
                "bins": [{"uid": "BIN-9999", "covers": [f"{uid}@1"], "condition": "a is 1"}],
                "checks": [{"uid": "CHK-9999", "covers": [f"{uid}@1"],
                            "expr": "matches the model", "signals": ["sum"]}]})
        if stage == "refmodel":
            # One call, one whole model -- shaped by the design, not by the
            # requirement list -- plus its own claim about where each
            # requirement lives.
            return json.dumps({
                "base": "evaluate",
                "source": "def evaluate(self, i):\n"
                          "    o = {p: None for p in self.OUTPUT_PORTS}\n"
                          "    o['sum'] = (i['a'] ^ i['b']) & 1\n"
                          "    o['cout'] = (i['a'] & i['b']) & 1\n"
                          "    return o\n",
                "covers": {"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]}})
        if stage.startswith("judge_"):
            # The judge blocks and cannot accept, so a `met` here does not make
            # the build pass -- the script checks above still decide. See
            # test_specflow_judge.py for that guarantee under test.
            return json.dumps({
                "verdict": "met",
                "reason": "the dispatch computes the named output directly",
                "evidence": "evaluate",
                "remedy": "",
            })
        if stage == "witness":
            # [W] A SECOND IMPLEMENTATION, and this test used not to serve it.
            #
            # Without it the oracle stage raised, `build_artifacts` logged a
            # warning and carried on, and this test asserted `res.ok` on a run
            # that had been decided against NO oracles at all. It passed
            # because of the defect it should have caught -- the same shape as
            # the test that pinned `PortSettings()` while the runner overrode
            # it, and the reason a scripted port has to serve every stage the
            # build actually reaches.
            return json.dumps({
                "base": "evaluate",
                "source": "def evaluate(self, i):\n"
                          "    o = {p: None for p in self.OUTPUT_PORTS}\n"
                          "    o['sum'] = (i['a'] ^ i['b']) & 1\n"
                          "    o['cout'] = (i['a'] & i['b']) & 1\n"
                          "    return o\n",
                "covers": {"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]}})
        if stage.startswith("oracle_"):
            port = "sum" if stage.endswith("REQ-0000") else "cout"
            op = "^" if port == "sum" else "&"
            return json.dumps({
                "reasoning": f"{port} follows a {op} b at every edge",
                "clause": f"the {port} output is driven as specified",
                "source": "def decide(trace):\n"
                          "    for row in trace:\n"
                          f"        want = (row['inputs']['a'] {op} "
                          "row['inputs']['b']) & 1\n"
                          f"        if row['outputs']['{port}'] != want:\n"
                          "            return False, row['edge'], 'wrong'\n"
                          f"    return True, 0, '{port} followed the rule'\n"})
        raise AssertionError(f"unexpected stage {stage}")

    import specflow.integration as integration

    real = integration.make_port
    integration.make_port = lambda *_, **__: Scripted(reply)
    try:
        res = build_artifacts(
            run_dir=run_dir, spec=spec, contract_json=CONTRACT,
            divide_s1=True, fanout=True, stimulus_agent=False,
        )
    finally:
        integration.make_port = real

    assert res.ok, f"{res.stage}: {[i.message for i in (res.issues or [])]}"

    # AND IT PASSED WITH AN ORACLE SET, not past a stage that failed silently.
    # `oracles.json` existing is the check that distinguishes the two, and its
    # absence is exactly how y-i2c and z-i2c both presented as green.
    assert (run_dir / "specflow" / "oracles.json").is_file(), (
        "the build reported ok with no oracle set, which is the false green")

    # Same artifact shape as the generative arm.
    reqs = json.loads((run_dir / "specflow" / "requirements.json").read_text())
    assert [r["uid"] for r in reqs["requirements"]] == ["REQ-0000", "REQ-0001"]
    # The core is `obligation`, a field. `spec_spans` beside it is context and
    # is legitimately empty when a requirement needs none.
    assert all(r["obligation"]["quote"] for r in reqs["requirements"])

    # The number that says the catch-all is gone: no requirement claims the spec.
    gate = json.loads((run_dir / "specflow" / "s1_gate.json").read_text())
    assert gate["arm"] == "divide"
    assert gate["word_carrying_gaps"] == 0
    assert gate["largest_requirement_chars"] < gate["spec_chars"], (
        "a requirement still claims the whole specification"
    )
    assert (run_dir / "specflow" / "suite" / "manifest.json").exists()
