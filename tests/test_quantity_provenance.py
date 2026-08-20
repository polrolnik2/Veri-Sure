"""A requirement may not assert a number its evidence does not contain.

Measured on `i2c_master_bit_ctrl`: seven of 72 requirements assert that
`cmd_ack` is one clock cycle wide, and each cites a span reading only "asserts
`cmd_ack`" -- no duration at all. The count was carried over from a statement
elsewhere in the document. REQ-0068, cited from a span that likewise says only
"asserts `cmd_ack`", did NOT assert a duration, so the same specification
produced both readings. The rate is stable across every recorded run -- 3-10% of
requirements, and the flagged quantity is the same one every time.

Why it matters beyond tidiness: nothing downstream can check the extra claim
against the specification, and everything downstream treats a requirement as
given. The number becomes an obligation the design is held to that no gate can
question -- which is how a testbench comes to reject correct RTL.
"""

from __future__ import annotations

from specflow.assure import _quantities, _unsupported_quantities

_SPEC = (
    "At the end of every sequence, `cmd_ack` is asserted for exactly one `clk` "
    "cycle.\n\nFor a START command, the FSM pulls SCL low and then asserts "
    "`cmd_ack`.\n\nclk_cnt[15:0]: Clock prescale value.\n"
)


def _issues(text: str, quoted: str, spec: str = _SPEC):
    return _unsupported_quantities("REQ-0001", text, quoted, spec)


# ------------------------------------------------------- normalisation


def test_number_words_and_digits_are_the_same_claim():
    """A spec and a requirement written from it routinely differ in exactly this
    way, and the difference is not a defect."""
    for phrasing in ("one clock cycle", "1 clk cycle", "a single cycle", "1 cycle"):
        assert ("1", "cycle") in _quantities(phrasing), phrasing


def test_a_bare_number_is_not_a_quantity():
    """The unit is what keeps this narrow. Bit indices, register addresses and
    state encodings are everywhere in a hardware specification, and flagging
    them would make the check noise rather than signal."""
    assert _quantities("the FSM enters state 3 and writes 0 to the register") == set()


def test_a_bit_range_states_a_width_on_the_evidence_side():
    """`clk_cnt[15:0]` says 16 bits as plainly as the words do.

    Only the evidence side reads ranges: the conservative direction for a gate
    that blocks is the one that ENLARGES what counts as support.
    """
    assert ("16", "bit") in _quantities("clk_cnt[15:0]: prescale", as_evidence=True)
    assert ("16", "bit") not in _quantities("clk_cnt[15:0]: prescale")


# ------------------------------------------------------- the finding


def test_a_duration_the_cited_span_does_not_state_is_flagged():
    """The i2c case, in one line."""
    issues = _issues(
        "The controller pulses cmd_ack for one clock cycle when STOP completes.",
        "t then asserts `cmd_ack`.")
    assert len(issues) == 1
    assert "1 cycle" in issues[0].message


def test_a_requirement_that_matches_its_span_is_silent():
    """REQ-0068's shape: it cited a span with no duration and asserted none."""
    assert _issues("After the read bit cycle the FSM returns to idle and asserts "
                   "cmd_ack.", "the FSM returns to `idle` and asserts `cmd_ack`.") == []


def test_citing_the_span_that_states_it_clears_the_finding():
    """The remedy the message names, asserted rather than described."""
    assert _issues(
        "The controller pulses cmd_ack for one clock cycle when STOP completes.",
        "t then asserts `cmd_ack`.\n"
        "`cmd_ack` is asserted for exactly one `clk` cycle.") == []


def test_a_width_the_span_states_as_a_range_is_attributed():
    assert _issues("The module loads the 16-bit clk_cnt value into the divider.",
                   "clk_cnt[15:0]:Clock prescale value.") == []


# ------------------------------------------------------- severity


def test_a_quantity_stated_elsewhere_in_the_spec_warns_rather_than_blocks():
    """G1 blocks, so its false-positive cost is the whole run.

    A claim whose evidence exists but is not linked is an attribution gap, and
    the fix is to add a span. Stopping a pipeline over a citation, while the
    claim itself is sound, costs more than it buys. Every one of the seven i2c
    findings is this case.
    """
    issues = _issues(
        "The controller pulses cmd_ack for one clock cycle when STOP completes.",
        "t then asserts `cmd_ack`.")
    assert [i.severity for i in issues] == ["warning"]
    assert "does state it, but not in any span" in issues[0].message


def test_a_quantity_that_appears_nowhere_in_the_spec_blocks():
    """Invented, not merely uncited -- and there is no span that would fix it."""
    issues = _issues("The controller asserts cmd_ack for 7 clock cycles.",
                     "t then asserts `cmd_ack`.")
    assert [i.severity for i in issues] == ["error"]
    assert "appears NOWHERE" in issues[0].message


def test_each_unsupported_quantity_is_reported_separately():
    issues = _issues("The 9-bit output is held for 7 cycles.", "the output is held.")
    assert len(issues) == 2
    assert {i.severity for i in issues} == {"error"}


# ------------------------------------------------------- wired into G1


def test_the_check_runs_inside_g1():
    from specflow.assure import check_spec_attribution

    reqs = [{
        "uid": "REQ-0001",
        "text": "The controller pulses cmd_ack for one clock cycle.",
        "spec_spans": [{"start": _SPEC.index("For a START"), "end": 0,
                        "quote": "For a START command, the FSM pulls SCL low and "
                                 "then asserts `cmd_ack`."}],
    }]
    found = [i for i in check_spec_attribution(_SPEC, reqs)
             if i.path == "requirement.REQ-0001.text"]
    assert len(found) == 1 and found[0].severity == "warning"
