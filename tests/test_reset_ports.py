"""A reset step may name WHICH reset ports it asserts.

`{"reset": true}` drives every declared reset at the same edge. On a design
with two -- i2c has a synchronous active-high `rst` beside an asynchronous
active-low `nReset` -- that makes "rst asserted while nReset is released" a
state the runtime never produces, so a requirement about which reset is which
cannot observe the thing it is about.

Measured on a2-i2c, replaying TP-0023 (which already contained a reset step)
against the witness: 204 edges, ONE row with rst==1, nReset==0 on that same
row, and ZERO rows with rst==1 and nReset==1. REQ-0006 and REQ-0007 both guard
on nReset being released, so both abstained by construction -- not a stimulus
defect, and no hint could fix it.
"""

from __future__ import annotations


from specflow.ports import asserted_resets
from specflow.refmodel.oracles import replay
from specflow.tb.runtime import is_reset_step, reset_ports

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "rst", "dir": "input", "width": 1},
    {"name": "nReset", "dir": "input", "width": 1},
    {"name": "d", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 1},
]}

MODEL = (
    "class Model:\n"
    "    OUTPUT_PORTS = ('q',)\n"
    "    def reset(self):\n"
    "        self.q = 0\n"
    "    def step(self, i):\n"
    "        if i.get('rst') == 1 or i.get('nReset') == 0:\n"
    "            self.q = 0\n"
    "        else:\n"
    "            self.q = i.get('d', 0)\n"
    "        return {'q': self.q}\n"
)


def test_true_still_means_every_reset_port():
    assert reset_ports({"reset": True}) is None
    assert set(asserted_resets(CONTRACT)) == {"rst", "nReset"}


def test_a_named_subset_leaves_the_other_reset_idle():
    assert reset_ports({"reset": ["rst"]}) == ["rst"]
    only = asserted_resets(CONTRACT, only=["rst"])
    assert set(only) == {"rst"}
    assert only["rst"] == 1                       # active-high asserts at 1


def test_a_bare_string_is_accepted_as_one_port():
    assert reset_ports({"reset": "nReset"}) == ["nReset"]


def test_a_named_reset_step_is_still_a_reset_step():
    """`is_reset_step` gates five call sites; a list must not slip past it."""
    assert is_reset_step({"reset": ["rst"]})
    assert is_reset_step({"reset": True})
    assert not is_reset_step({"inputs": {"d": 1}})


def test_the_scenario_that_was_unreachable_is_now_reachable():
    """The whole point: rst asserted while nReset stays released."""
    steps = [{"d": 1}, {"reset": ["rst"], "hold": 2}, {"d": 1}]
    rep = replay(MODEL, CONTRACT, steps, base="step")
    assert not rep.error
    both = [r for r in rep.rows
            if r["inputs"].get("rst") == 1 and r["inputs"].get("nReset") == 1]
    assert both, "rst asserted with nReset released must now occur"
    # and the design's own response to rst is what shows, not a forced reset
    assert all(r["outputs"]["q"] == 0 for r in both)


def test_a_whole_reset_still_asserts_both():
    rep = replay(MODEL, CONTRACT, [{"d": 1}, {"reset": True, "hold": 1}],
                 base="step")
    rows = [r for r in rep.rows if r["inputs"].get("rst") == 1]
    assert rows and all(r["inputs"].get("nReset") == 0 for r in rows)


def test_a_selective_reset_does_not_force_the_model_s_reset():
    """Forcing `reset()` is exactly what made the two ports indistinguishable.

    Probed with internal state rather than a driven input: a reset step idles
    EVERY input on both sides -- mirroring `Env.reset()` so the two cannot
    diverge -- so an output that follows `d` reads 0 during the hold whether or
    not the model honoured the port. A counter shows the difference.
    """
    counter = (
        "class Model:\n"
        "    OUTPUT_PORTS = ('q',)\n"
        "    def reset(self):\n"
        "        self.n = 0\n"
        "    def step(self, i):\n"
        "        n = getattr(self, 'n', 0)\n"
        "        self.n = 0 if i.get('nReset') == 0 else (n + 1) % 2\n"
        "        return {'q': self.n}\n"
    )
    rep = replay(counter, CONTRACT,
                 [{"d": 1}, {"d": 1}, {"reset": ["rst"], "hold": 4}],
                 base="step")
    assert not rep.error, rep.error
    held = [r for r in rep.rows if r["inputs"].get("rst") == 1]
    assert held, "the selective reset must appear in the trace"
    # It ignores `rst`, so it keeps counting -- visible, rather than masked by
    # a reset the harness performed on its behalf.
    assert any(r["outputs"]["q"] == 1 for r in held), (
        "a model ignoring rst must show it, not be reset on its behalf")


def test_an_undeclared_reset_port_is_rejected():
    from specflow.testcase_agent import SuiteStimulus, gate_suite
    suite = SuiteStimulus.model_validate({"testpoints": [
        {"tp_uid": "TP-0000",
         "stimulus_steps": [{"reset": ["nonesuch"], "hold": 1}]}]})
    issues = gate_suite(suite, testplan=[{"uid": "TP-0000"}],
                        contract=CONTRACT, max_steps=40)
    assert any("nonesuch" in i.message and i.severity == "error" for i in issues)


def test_an_empty_reset_list_is_rejected():
    from specflow.testcase_agent import SuiteStimulus, gate_suite
    suite = SuiteStimulus.model_validate({"testpoints": [
        {"tp_uid": "TP-0000", "stimulus_steps": [{"reset": [], "hold": 1}]}]})
    issues = gate_suite(suite, testplan=[{"uid": "TP-0000"}],
                        contract=CONTRACT, max_steps=40)
    assert issues, "an empty list asserts nothing and must not pass silently"


def test_the_prompt_documents_the_list_form():
    from specflow.testcase_agent import SUITE_SYSTEM
    assert '{"reset": ["rst"], "hold": 2}' in SUITE_SYSTEM
    assert "more than one reset port" in SUITE_SYSTEM
