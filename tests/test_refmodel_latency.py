"""G4e: a reference model may not answer faster than its own contract allows.

Every other G4 check asks whether the model is well-formed; none asks whether it
behaves like the design. The per-requirement judge cannot either, because it
reads code against one requirement at a time and a requirement such as "the FSM
advances only when clk_en is asserted" is satisfied by code that then advances
through EVERY phase on a single clk_en. Each requirement passes alone; the
composition is wrong.

That is the defect this exists for. On i2c_master_bit_ctrl the generated model
collapsed the five-phase START sequence into one clk_en tick -- golden takes
five, so at clk_cnt=4 golden asserts cmd_ack at clock edge 26 and the model at
edge 5. The judge returned "met" on all 72 requirements over that model, and
driven through the resulting suite the GOLDEN design failed 120 of 168
testpoints, worse than the LLM-written candidate. No golden RTL is used here:
the cross-check is against the contract, an independently derived reading of the
same specification.
"""

from __future__ import annotations

from specflow.refmodel.base import RefModel
from specflow.refmodel.validate import _min_latency_checks

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "nReset", "dir": "input", "width": 1},
        {"name": "ena", "dir": "input", "width": 1},
        {"name": "clk_cnt", "dir": "input", "width": 16},
        {"name": "cmd", "dir": "input", "width": 4},
        {"name": "scl_i", "dir": "input", "width": 1},
        {"name": "sda_i", "dir": "input", "width": 1},
        {"name": "cmd_ack", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": True},
    "timing": {"cmd_ack": {"latency_cycles": 3}},
}


def _model(ack_at: int, *, needs_bus_idle: bool = False):
    """A model that asserts cmd_ack `ack_at` steps after cmd goes high."""

    class M(RefModel):
        OUTPUT_PORTS = ["cmd_ack"]
        LATENCY_CYCLES = 3

        def reset(self):
            self.n = 0

        def step(self, i):
            if not hasattr(self, "n"):
                self.n = 0
            # Some designs are inert unless the bus is released. Modelling that
            # is what makes the all-zeros vector useless as an "idle" state.
            live = (not needs_bus_idle) or (i.get("scl_i") and i.get("sda_i"))
            if i.get("cmd") and live:
                self.n += 1
            else:
                self.n = 0
            return {"cmd_ack": 1 if self.n == ack_at else 0}

    return M


def test_answering_too_early_is_blocked():
    issues = _min_latency_checks(_model(1), CONTRACT, "step")
    assert len(issues) == 1
    msg = issues[0].message
    assert "faster than the contract allows" in msg
    assert "latency_cycles is 3" in msg
    assert issues[0].severity == "error"


def test_answering_exactly_on_time_passes():
    assert _min_latency_checks(_model(3), CONTRACT, "step") == []


def test_answering_late_is_allowed():
    """One-sided on purpose: a prescaler, a stall or a stretched bus clock all
    legitimately delay an output, and this design's own contract note says the
    wall-clock latency may exceed the declared figure. Only EARLIER is
    impossible, so only earlier blocks."""
    assert _min_latency_checks(_model(9), CONTRACT, "step") == []


def test_a_design_inert_until_the_bus_is_released_is_still_checked():
    """The regression that made two earlier versions of this check useless.

    Holding every non-trigger input at 0 puts an open-drain SDA/SCL LOW -- a
    stuck bus -- and the model then correctly does nothing, so the check saw no
    response and passed. Zero is not "idle" for an active-low or open-drain
    input, and the contract does not say which is which; the rest-state sweep is
    what makes the check see this model at all.
    """
    issues = _min_latency_checks(_model(1, needs_bus_idle=True), CONTRACT, "step")
    assert len(issues) == 1, "a bus-idle-gated design must not escape the check"


def test_combinational_models_are_not_checked():
    assert _min_latency_checks(_model(1), CONTRACT, "evaluate") == []


def test_latency_below_two_is_not_checked():
    """0 or 1 says nothing a step count can contradict."""
    c = {**CONTRACT, "timing": {"cmd_ack": {"latency_cycles": 1}}}
    assert _min_latency_checks(_model(1), c, "step") == []


def test_no_identifiable_trigger_skips_rather_than_guesses():
    c = {
        **CONTRACT,
        "io": [p for p in CONTRACT["io"] if p["name"] != "cmd"],
    }
    assert _min_latency_checks(_model(1), c, "step") == []


def test_a_raising_model_is_left_to_the_determination_check():
    class Boom(RefModel):
        OUTPUT_PORTS = ["cmd_ack"]

        def step(self, i):
            raise RuntimeError("boom")

    assert _min_latency_checks(Boom, CONTRACT, "step") == []


def test_a_free_running_output_is_not_mistaken_for_a_response():
    """The idle twin exists for this. An output that ticks on its own is
    identical in both twins and must never be flagged; comparing against a
    remembered first value instead would call it a step-1 response."""

    class Ticker(RefModel):
        OUTPUT_PORTS = ["cmd_ack"]

        def reset(self):
            self.t = 0

        def step(self, i):
            if not hasattr(self, "t"):
                self.t = 0
            self.t += 1
            return {"cmd_ack": self.t % 2}   # ignores cmd entirely

    assert _min_latency_checks(Ticker, CONTRACT, "step") == []
