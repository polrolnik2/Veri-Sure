"""Step 8: it ships, and the probes do not ship with it.

A check is a claim about the design that SHIPS, so the connection point has to
exist there -- `asserter.py` and the boolean miter both skip a non-port
direction, so an assertion bound to a testbench-only signal has nowhere to
attach. That is why a probe is a port of the generated module and not a bind.

Then it has to leave, because golden has no probes and a design carrying extra
outputs is not the design the specification describes.
"""
from __future__ import annotations

from eda_agent.strip_probes import strip_probes, traces_agree
from specflow import reachability as R
from specflow.unreach import Discharge

#: One probe merely assigned from state (inert), one wired INTO a real output
#: (not inert). The second is what lets the pin be shown to fail.
RTL = """module dcfsm (
  input wire clk,
  input wire go,
  output wire busy,
  output wire ack,
  output wire in_cload,
  output wire in_wired
);
  reg [1:0] state;
  always @(posedge clk) state <= go ? 2'd1 : 2'd0;
  assign in_cload = (state == 2'd1);
  assign in_wired = (state == 2'd1);
  assign busy = (state == 2'd1);
  assign ack = go & in_wired;
endmodule
"""


def test_the_probes_are_ports_of_the_generated_module() -> None:
    """The correction that turned a testbench bind into a contract port."""
    for probe in ("in_cload", "in_wired"):
        assert f"output wire {probe}" in RTL


def test_an_inert_probe_is_removed_cleanly() -> None:
    out, left = strip_probes(RTL, ["in_cload"])
    assert left == []
    assert "in_cload" not in out
    # And nothing else moved.
    assert "assign busy = (state == 2'd1);" in out
    assert "output wire busy" in out


def test_a_probe_ANOTHER_LINE_READS_is_left_in_place_and_reported() -> None:
    """Deleting a signal something depends on produces RTL that does not
    compile, and a confusing compile error is worse than a visible extra port.

    `ack` reads `in_wired`, so removing it would break the module.
    """
    out, left = strip_probes(RTL, ["in_wired"])
    assert left == ["in_wired"]
    assert "in_wired" in out


def test_a_probe_that_is_not_declared_is_reported_not_silently_ok() -> None:
    _, left = strip_probes(RTL, ["in_nowhere"])
    assert left == ["in_nowhere"]


REAL = ["busy", "ack"]


def _rows(busy, ack):
    return [{"edge": i, "outputs": {"busy": b, "ack": a}}
            for i, (b, a) in enumerate(zip(busy, ack))]


def test_the_pin_passes_when_stripping_changed_nothing() -> None:
    before = {"tp_0001": _rows([0, 1, 1], [0, 1, 0])}
    after = {"tp_0001": _rows([0, 1, 1], [0, 1, 0])}
    assert traces_agree(before, after, REAL) == []


def test_the_pin_FAILS_when_a_real_port_moved() -> None:
    """It has to be able to fail, or it is not a pin.

    A probe wired into a real output changes the design, and removing it changes
    it back. This is the one way probes could silently alter what ships.
    """
    before = {"tp_0001": _rows([0, 1, 1], [0, 1, 0])}
    after = {"tp_0001": _rows([0, 1, 1], [0, 0, 0])}
    bad = traces_agree(before, after, REAL)
    assert bad and "ack" in bad[0] and "edge 1" in bad[0]


# ------------------------------------------------- the one authority

STATED = {"config_gated": "OR1200_DC_STORE_REFILL", "value": False,
          "span": "Store-miss refill is present only when "
                  "OR1200_DC_STORE_REFILL is defined"}


def test_only_a_PASSING_proof_disposes_of_anything() -> None:
    """A timeout is not evidence about a design.

    Treating one as a proof shrinks the denominator on the strength of a solver
    not having finished -- which is the difference between an exclusion and an
    excuse.
    """
    for status in ("unknown", "timeout", "error", "skip"):
        disp, why = R.dispose(Discharge("in_srefill4", status), hypothesis=STATED)
        assert disp == "", status
        assert "establishes nothing" in why


def test_a_reachable_verdict_records_that_a_stimulus_EXISTS() -> None:
    """sby's counterexample is a stimulus that reaches the state."""
    disp, why = R.dispose(Discharge("in_cload", "reachable"), hypothesis=None)
    assert disp == ""
    assert "counterexample" in why and "reachable" in why


def test_unreachable_WITH_a_quoted_span_is_a_legitimate_absence() -> None:
    disp, why = R.dispose(Discharge("in_srefill4", "unreachable"),
                          hypothesis=STATED)
    assert disp == R.UNREACHABLE
    assert "OR1200_DC_STORE_REFILL" in why
    assert "leave the denominator" in why


def test_unreachable_WITHOUT_one_is_a_DESIGN_FINDING_not_a_discard() -> None:
    """The distinction the whole hypothesis mechanism exists for.

    Silently treating a missing feature as a legitimate absence is how a design
    defect becomes a smaller denominator.
    """
    disp, why = R.dispose(Discharge("in_srefill4", "unreachable"), hypothesis=None)
    assert disp == R.DESIGN_MISSING_STATE
    assert "missing a state the specification requires" in why
    assert "checks stay blocking" in why


def test_a_hypothesis_with_NO_span_disposes_as_a_design_finding() -> None:
    """A config key without the specification stating the dependency is an
    inference, and an inference may not turn a design defect into a discard."""
    bare = {"config_gated": "OR1200_DC_WRITETHROUGH", "value": False, "span": ""}
    disp, _ = R.dispose(Discharge("x", "unreachable"), hypothesis=bare)
    assert disp == R.DESIGN_MISSING_STATE


def test_the_oracle_stage_never_assigns_either(monkeypatch) -> None:
    """The authority rule, as a grep. Nothing before RTL exists may say this."""
    from pathlib import Path
    src = Path("specflow/oracles_stage.py").read_text()
    assert "UNREACHABLE" not in src
    assert "DESIGN_MISSING_STATE" not in src


# ------------------------------------------- the base case needs a reset

RESET_CONTRACT = {"module_name": "dcfsm", "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "rst", "dir": "input", "width": 1},
    {"name": "busy", "dir": "output", "width": 1},
    {"name": "in_srefill4", "dir": "probe", "width": 1}],
    "clocking": {"clock": {"name": "clk"},
                 "reset": {"name": "rst", "active": "high"}}}


def test_the_cover_probe_assumes_the_design_STARTS_FROM_RESET() -> None:
    """Without this the instrument can never prove any state unreachable.

    `mode prove` is k-induction: a base case and an inductive step. The step is
    what makes a PASS unbounded and needs no help. The BASE CASE does -- with
    nothing constraining the initial state the solver may start the design in
    any bit pattern its registers hold, including the state under test.

    MEASURED on a two-bit FSM whose state 3 is never assigned anywhere: the log
    reads "Temporal induction successful" -- the design genuinely cannot ENTER
    the state -- while the base case failed at step 0 because the solver started
    there, and the verdict came back `reachable`. Left unfixed, the one
    authority for UNREACHABLE would be vacuous while appearing to run.
    """
    from specflow.unreach import render_cover_probe

    sv = render_cover_probe(dut_module="dcfsm", contract=RESET_CONTRACT,
                            condition_sv="in_srefill4")
    assert "initial assume (rst);" in sv
    # And the property is asserted only AFTER reset, which is what makes the
    # question "reachable from reset" rather than "reachable from anywhere".
    assert "_past_reset" in sv
    assert "if (_past_reset) assert (!(in_srefill4));" in sv


def test_an_active_low_reset_is_assumed_at_its_own_level() -> None:
    contract = {**RESET_CONTRACT,
                "clocking": {"clock": {"name": "clk"},
                             "reset": {"name": "rst", "active": "low"}}}
    sv = render_cover_probe_of(contract)
    assert "initial assume (!rst);" in sv


def render_cover_probe_of(contract):
    from specflow.unreach import render_cover_probe
    return render_cover_probe(dut_module="dcfsm", contract=contract,
                              condition_sv="in_srefill4")


def test_a_design_with_NO_reset_is_left_as_it_was() -> None:
    """A design with no reset has no defined start state, so "reachable from
    reset" is not a question it can be asked -- and inventing an assumption
    would be proving something about a design that does not exist."""
    contract = {**RESET_CONTRACT, "clocking": {"clock": {"name": "clk"}}}
    sv = render_cover_probe_of(contract)
    assert "assume" not in sv
    assert "assert (!(in_srefill4));" in sv
