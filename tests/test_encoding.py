"""A port's symbolic values, and the guess that used to stand in for them.

The defect this closes is not "a wrong number". It is that the symbol-to-number
step was never modelled, so it happened at the first stage that needed an
integer, as a guess, with nothing recording that a guess was made -- and the
only gate that looked at a `cmd` value checked that it fit in four bits.
"""

from __future__ import annotations

import json
from pathlib import Path

from specflow.encoding import (annotate, encoding_for, extract_port_encoding,
                               parse_defines, referenced_by_decode, resolve,
                               symbol_for)
from specflow.normalize import (Activation, NormalizedRequirement,
                                NormalizeOutput, gate_one)

BENCH = Path(__file__).resolve().parents[1] / "benchmarks/chipverilog/Des/i2c"
DEFINES = BENCH / "i2c_master_defines.v"
RTL = BENCH / "i2c_master_bit_ctrl/i2c_master_bit_ctrl.v"

#: The real thing, from the benchmark's own header.
TRUE = {"I2C_CMD_NOP": 0, "I2C_CMD_START": 1, "I2C_CMD_STOP": 2,
        "I2C_CMD_WRITE": 4, "I2C_CMD_READ": 8}


def _enc():
    return extract_port_encoding(defines_text=DEFINES.read_text(),
                                 rtl=RTL.read_text(), port="cmd",
                                 source="i2c_master_defines.v")


def _contract(port_extra=None):
    cmd = {"name": "cmd", "dir": "input", "width": 4, **(port_extra or {})}
    return {"io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "ena", "dir": "input", "width": 1},
                   cmd,
                   {"name": "cmd_ack", "dir": "output", "width": 1}]}


REQ = {"uid": "REQ-0000", "text": "t"}
SHOWS = "cmd_ack pulses when the requirement holds and stays low when it does not"


def _errors(contract, **activation):
    out = NormalizeOutput(normalized=[NormalizedRequirement(
        observable=["cmd_ack"], expectation="e",
        observed_via=[{"port": "cmd_ack", "through_req": "", "when": "w",
                       "shows": SHOWS}],
        activation=Activation(text="t", **activation))])
    return [i.message for i in gate_one(REQ, out, contract) if i.severity == "error"]


# ------------------------------------------------------- reading the header


def test_the_table_comes_off_the_benchmarks_own_defines_file():
    """Not a fixture. If the benchmark's header changes, this fails, which is
    the point of reading the real file."""
    assert parse_defines(DEFINES.read_text()) == TRUE


def test_a_macro_qualifies_by_BEING_IN_THE_PORTS_DECODE():
    """The admission rule, and it is not "it was in a defines file".

    or1200 ships 611 defines -- cache geometry, `OR1200_NO_DC`, feature flags --
    and none of that is interface. What separates them is whether an external
    agent must know the value to drive the module: the byte controller cannot
    issue a command without `cmd`'s encoding, and nobody outside needs an FSM
    state's. A requirement keyed on the latter is the internal-mechanism class
    NOT_ASSERTABLE exists to route away.
    """
    used = referenced_by_decode(RTL.read_text(), "cmd", set(TRUE))
    assert used == {"I2C_CMD_START", "I2C_CMD_STOP", "I2C_CMD_WRITE", "I2C_CMD_READ"}
    # A macro no decode of this port names is not admitted on its own merits.
    assert "I2C_CMD_NOP" not in used


def test_the_decode_is_not_the_whole_enumeration():
    """The bug this caught before shipping.

    `case (cmd)` has four arms; `I2C_CMD_NOP` has none -- it falls to the
    default. Admitting only what the case names AND THEN calling the value space
    closed would reject `cmd=0`, which is a perfectly legal "no command" value.
    A referenced symbol therefore pulls in its `PREFIX_` siblings from the same
    file: that family is the enumeration the specification's own names describe.
    """
    enc = _enc()
    assert enc["encoding"] == TRUE, "NOP must be admitted as a sibling"
    assert enc["encoding_complete"] is True
    assert resolve("cmd", 0, _contract(enc))[0] == 0, "NOP is a legal value"


def test_a_lone_reference_is_not_evidence_of_a_family():
    """One symbol's prefix is a guess about a family, not evidence of one, so
    the sibling sweep needs two. Otherwise a single `port == \\`SOME_MACRO`
    would drag in every macro sharing its prefix and declare the space closed.
    """
    rtl = "module m(input [3:0] p); wire w = (p == `ONLY_ONE); endmodule"
    defines = "`define ONLY_ONE 4'b0001\n`define ONLY_TWO 4'b0010\n"
    enc = extract_port_encoding(defines_text=defines, rtl=rtl, port="p",
                                source="d.v")
    assert set(enc["encoding"]) == {"ONLY_ONE"}
    assert enc["encoding_complete"] is False, "a bare == says nothing about the rest"


def test_provenance_is_recorded_because_source_of_truth_says_spec():
    """The contract declares `source_of_truth: "spec"`, and a constant taken
    from a header makes that a lie unless the fact carries its own source. The
    hash is what makes a design that REDEFINES the constants a finding rather
    than a new table."""
    enc = _enc()
    assert enc["encoding_source"]["file"] == "i2c_master_defines.v"
    assert len(enc["encoding_source"]["sha256"]) == 64


# ------------------------------------------------------------ resolving


def test_a_symbol_resolves_and_an_unknown_one_names_the_legal_set():
    c = _contract(_enc())
    assert resolve("cmd", "I2C_CMD_WRITE", c)[0] == 4
    assert resolve("cmd", "I2C_CMD_READ", c)[0] == 8
    n, why = resolve("cmd", "I2C_CMD_NOPE", c)
    assert n is None and "I2C_CMD_WRITE" in why, why


def test_a_numeric_STRING_is_an_error_not_a_silent_int():
    """`"4"` is a mistake worth a message. Coercing it would reintroduce the
    guess through the one door the schema change was supposed to close."""
    n, why = resolve("cmd", "4", _contract(_enc()))
    assert n is None and "not one of its declared symbols" in why


def test_a_value_NO_ARM_DECODES_is_rejected_when_the_space_is_closed():
    """Seven of c1-i2c's requirements used `cmd=3`. It matches no arm, so the
    window can never open -- and at decide time that is indistinguishable from a
    design that never did it. The ONLY gate that inspected a cmd value checked
    that it fit in four bits, so every value 0-15 passed."""
    c = _contract(_enc())
    n, why = resolve("cmd", 3, c)
    assert n is None and "is not one of the values" in why
    assert _errors(c, inputs={"cmd": 3})
    assert not _errors(c, inputs={"cmd": 4}), "a legal value still passes"


def test_symbol_for_reports_and_annotate_drops_what_it_cannot_resolve():
    c = _contract(_enc())
    assert symbol_for("cmd", 8, c) == "I2C_CMD_READ"
    assert symbol_for("cmd", 3, c) == ""
    # Dropped, never invented: an entry with no resolvable number has no number
    # to offer, and supplying one is the whole defect.
    assert annotate({"cmd": "I2C_CMD_STOP", "ena": 1}, c) == {"cmd": 2, "ena": 1}
    assert annotate({"cmd": "I2C_CMD_NOPE"}, c) == {}


# --------------------------------------------------- inert without a table


def test_a_port_with_no_encoding_behaves_EXACTLY_as_before():
    """The inertness pin. Every design without a shared constants header, and
    every artifact predating this module, has to decide as it did -- including
    accepting the values a table would have caught."""
    bare = _contract()
    assert encoding_for(bare, "cmd") == ({}, False)
    for v in (0, 1, 2, 3, 4, 7, 8, 15):
        assert not _errors(bare, inputs={"cmd": v}), v
    assert _errors(bare, inputs={"cmd": 16}), "the width check still bites"


def test_a_symbol_without_a_table_says_why_rather_than_failing_obscurely():
    n, why = resolve("cmd", "I2C_CMD_WRITE", _contract())
    assert n is None and "declares no encoding" in why


# ------------------------------------------------------- the other fields


def test_opens_on_takes_a_symbol_and_still_takes_an_EDGE():
    """These fields already carried `int | str` for edge words, so symbols and
    edges share one slot. Both must keep working, and the edge words win."""
    c = _contract(_enc())
    assert not _errors(c, inputs={"ena": 1}, opens_on=[{"cmd": "I2C_CMD_START"}])
    assert not _errors(c, inputs={"ena": 1}, opens_on=[{"cmd_ack": "rise"}])
    bad = _errors(c, inputs={"ena": 1}, until=[{"cmd": "I2C_CMD_NOPE"}])
    assert bad and "neither a value nor one of" in bad[0]
    assert "I2C_CMD_START" in bad[0], "the legal symbols belong in the message"


# --------------------------------------------------------------- prompts


def test_normalization_is_told_to_write_the_symbol():
    from specflow.normalize import SYSTEM
    assert "NAME A VALUE BY ITS SYMBOL WHERE THE PORT DECLARES ONE" in SYSTEM
    assert '{"cmd": "I2C_CMD_WRITE"}' in SYSTEM
    assert "Where a port declares NO encoding, write the number as before." in SYSTEM


def test_the_REVIEWER_gets_the_table_and_is_forbidden_to_infer_one():
    """The measured failure: with no table the reviewer took another
    requirement's wrong normalization as evidence, concluded "WRITE=3, READ=4",
    rejected a correct check, and the repair wrote the illegal value in."""
    from specflow.refmodel.correspondence import SYSTEM, _ports
    projected = _ports(_contract(_enc()))
    cmd = next(p for p in projected["ports"] if p["name"] == "cmd")
    assert cmd["encoding"] == TRUE, "stripped here, the reviewer has to guess"
    assert "A PORT'S ENCODING IS NOT YOURS TO DEDUCE" in SYSTEM
    for phrase in ("from another requirement's normalized form",
                   "never propose a different number"):
        assert phrase in SYSTEM, phrase


def test_the_AUTHOR_already_receives_the_whole_contract():
    """No plumbing needed on this leg -- `oracle_gen` is handed `contract_json`
    entire, so the table arrives with it. Pinned so a later projection of the
    contract does not quietly take it away, which is what happened to the
    reviewer."""
    from specflow.refmodel.oracle_gen import build_prompt
    body = build_prompt(requirement=REQ,
                        contract_json=json.dumps(_contract(_enc()), indent=2),
                        contract=_contract(_enc()))
    assert "I2C_CMD_WRITE" in body and '"encoding"' in body
