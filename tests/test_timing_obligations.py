"""Phase 5's gate: how many duration obligations does the corpus contain?

The plan said to measure before building, and the measurement says do not build.
Across all 64 ChipVerilog specifications there are **3 boundary-observable
duration obligations in 2 modules**, all of them the same claim -- `cmd_ack` is
one clock cycle wide -- and both modules are in the i2c family. That is not a
pipeline feature; that is one sentence.

These cases pin the extractor's distractor rejections, because building it
produced two live examples of the failure the plan warned about:

* `or1200_except`'s specification says "except_start is a combinational level
  signal, NOT a one-cycle pulse". The first version read the denial as an
  obligation and generated a check the golden design fails.
* scanning the golden Verilog for `output` without stripping comments first
  matched the word inside `// i2c clock line output enable (active low)`, so
  `i2c_master_bit_ctrl` acquired ports named `enable`, `end` and `yet` -- and
  "At the **end** of a command sequence" became a claim about a port.

An oracle that fails correct RTL is the defect this whole line of work exists to
remove. A timing extractor that reintroduces it is a bad trade, which is why the
counter-examples are tests rather than notes.
"""

from __future__ import annotations

from benchmarks.timing_obligations import _extract, _outputs, _validate

_PORTS = ["cmd_ack", "busy", "first_hit_ack", "except_start"]


def _obligations(sentence: str, ports: list[str] | None = None):
    return _extract("T", sentence, ports or _PORTS).obligations


def _why(sentence: str, ports: list[str] | None = None) -> list[str]:
    return [why for _, why in _extract("T", sentence, ports or _PORTS).rejected]


# ------------------------------------------------------- the true positive


def test_the_one_shape_the_corpus_actually_supports():
    """`exactly` occurs once in the entire corpus, and this is the sentence."""
    obs = _obligations(
        "At the end of every START, STOP, READ, or WRITE sequence, `cmd_ack` "
        "is asserted for exactly one `clk` cycle.")
    assert [(o.port, o.cycles) for o in obs] == [("cmd_ack", 1)]


def test_a_negation_in_a_different_clause_does_not_lose_the_obligation():
    """Scope cuts both ways; sentence-wide negation threw a real one away."""
    obs = _obligations(
        "If stop is not asserted, the FSM returns to ST_IDLE, sets core_cmd to "
        "NOP, and generates a one-cycle cmd_ack.")
    assert [(o.port, o.cycles) for o in obs] == [("cmd_ack", 1)]


# ------------------------------------------------------- the distractors


def test_a_denied_pulse_is_not_an_obligation():
    """The most dangerous distractor: the spec is not silent, it says the opposite."""
    assert _obligations(
        "except_start is a combinational level signal, not a one-cycle pulse;") == []
    assert _why(
        "except_start is a combinational level signal, not a one-cycle pulse;"
    ) == ["the clause DENIES the duration"]


def test_a_glossary_label_is_a_noun_phrase_not_a_claim():
    """`or1200_ic_fsm` calls `first_hit_ack` a "One-cycle acknowledge" and golden
    implements it as a continuous assign with no width guarantee at all."""
    line = "- first_hit_ack: One-cycle acknowledge for a cache hit or immediately satisfied access."
    assert _obligations(line) == []
    assert _why(line) == ["no verb of assertion; a noun phrase"]


def test_a_latency_claim_is_not_a_width_claim():
    """"one-cycle delayed" says WHEN, not HOW LONG.

    A design that delays by one cycle and then holds for ten satisfies it, so
    reading it as a pulse width invents an obligation the sentence never made.
    """
    line = ("The external acknowledge signal cmd_ack is a registered, one-cycle "
            "delayed version of dbg_stb_i.")
    assert _obligations(line) == []
    assert _why(line) == ["a latency claim, not a width claim"]


def test_an_internal_signal_is_not_boundary_observable():
    line = "It is cleared on reset, set for one cycle when genpc_refetch is asserted."
    assert _obligations(line) == []
    assert _why(line) == ["no declared output port in the sentence"]


# ------------------------------------------------------- the port list


def test_output_ports_are_read_from_code_not_from_comments():
    rtl = """
    module m (
        input             clk,
        output reg        cmd_ack,  // command complete acknowledge
        output            scl_o,    // i2c clock line output
        output reg        scl_oen   // i2c clock line output enable (active low)
    );
    endmodule
    """
    assert _outputs(rtl) == ["cmd_ack", "scl_o", "scl_oen"]


# ------------------------------------------------------- golden validation


def test_a_continuous_assign_cannot_guarantee_a_pulse_width():
    from benchmarks.timing_obligations import Obligation

    ob = Obligation("or1200_ic_fsm", "first_hit_ack", 1, "...")
    _validate(ob, "assign first_hit_ack = hitmiss_eval & !hitmiss_eval_r;")
    assert ob.verdict == "cannot-hold"


def test_the_opencores_delay_annotation_does_not_hide_the_pulse():
    """Every non-blocking assignment in the i2c core carries `#1`.

    A validator that did not allow it reported the one obligation the corpus
    actually contains as inconclusive -- reading a failure to parse as a failure
    to hold.
    """
    from benchmarks.timing_obligations import Obligation

    ob = Obligation("i2c_master_bit_ctrl", "cmd_ack", 1, "...")
    _validate(ob, "          cmd_ack <= #1 1'b0;\n                    cmd_ack <= #1 1'b1;\n")
    assert ob.verdict == "holds"
