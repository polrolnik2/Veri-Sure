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


# ------------------------------------------------- the SPEC picks the symbols


def test_the_SPEC_chooses_which_symbols_belong_to_a_port():
    """The pipeline's selector, and it deliberately reads no design.

    `referenced_by_decode` answers the same question from the RTL, which is
    right for offline analysis and wrong for a contract: the golden design is
    the scoring instrument and may not decide what a check looks at, even
    indirectly. The specification already answers it -- i2c's `cmd` entry says
    the field "is decoded as one of the supported commands" and lists all four
    -- so the spec picks WHICH and the header supplies only the VALUES.
    """
    from specflow.encoding import symbols_in_spec
    spec = (BENCH / "i2c_master_bit_ctrl/description.txt").read_text()
    names = set(parse_defines(DEFINES.read_text()))
    assert symbols_in_spec(spec, "cmd", names) == {
        "I2C_CMD_START", "I2C_CMD_STOP", "I2C_CMD_WRITE", "I2C_CMD_READ"}
    # A port the spec names no symbols for gets none -- the paragraph scan must
    # not bleed across port entries.
    assert symbols_in_spec(spec, "din", names) == set()
    assert symbols_in_spec(spec, "nosuchport", names) == set()


def test_enrichment_touches_only_the_ports_the_spec_enumerates():
    from specflow.encoding import enrich_contract, find_defines
    spec = (BENCH / "i2c_master_bit_ctrl/description.txt").read_text()
    found = find_defines(RTL)
    assert [p.name for p in found] == ["i2c_master_defines.v"]

    c = {"io": [{"name": "cmd", "dir": "input", "width": 4},
                {"name": "din", "dir": "input", "width": 1},
                {"name": "busy", "dir": "output", "width": 1}]}
    notes = enrich_contract(c, spec=spec, defines=found)
    assert notes and "cmd" in notes[0]
    cmd, din, busy = c["io"]
    assert cmd["encoding"] == TRUE and cmd["encoding_complete"] is True
    assert cmd["encoding_source"]["file"] == "i2c_master_defines.v"
    assert "encoding" not in din and "encoding" not in busy


def test_enrichment_is_a_NO_OP_without_a_header_or_without_symbols():
    """The inertness pin, one level up. A design with no shared constants file,
    or a spec that names no symbols, must come out byte-identical."""
    from specflow.encoding import enrich_contract
    import copy
    c = {"io": [{"name": "cmd", "dir": "input", "width": 4}]}
    before = copy.deepcopy(c)
    assert enrich_contract(c, spec="cmd[3:0]:a command\n", defines=[]) == []
    assert c == before
    spec_no_symbols = "cmd[3:0]:Bit-level command from the byte controller.\n"
    assert enrich_contract(c, spec=spec_no_symbols, defines=[DEFINES]) == []
    assert c == before


def test_one_named_symbol_is_a_mention_not_an_enumeration():
    """Closing the value space off a single name would reject every other value
    the port legitimately takes, so two are required."""
    from specflow.encoding import enrich_contract
    c = {"io": [{"name": "cmd", "dir": "input", "width": 4}]}
    one = "cmd[3:0]:issued as `I2C_CMD_START` when starting.\n"
    assert enrich_contract(c, spec=one, defines=[DEFINES]) == []
    assert "encoding" not in c["io"][0]


def test_the_contract_builder_actually_calls_it():
    """WIRED, not merely built. `extract_port_encoding` sat callable and unused
    for a whole commit: the schema accepted symbols, the gate rejected illegal
    values, the reviewer got the table -- and nothing populated it, so on every
    real run the whole mechanism was inert."""
    import inspect

    from eda_agent.top_agent import TopAgent
    src = inspect.getsource(TopAgent._build_contract_json)
    assert "encoding.enrich_contract" in src
    assert "encoding.find_defines" in src
    # And it enriches the object that gets WRITTEN, not a discarded copy.
    assert src.index("enrich_contract") < src.index('file_name="contract.json"')


# --------------------------------------------- the reviewer knows the operators


def test_the_REVIEWER_is_told_what_the_operators_RETURN():
    """Measured before this existed: `strong=True` and `stable` appeared ZERO
    times in the correspondence prompt, against 6 and 10 in the author's -- and
    the reviewer's entire job is to enumerate the paths on which a check returns
    False. It was judging code that calls operators whose return contract it had
    never been given, which is the encoding defect in another costume.

    The block lives in `temporal.py` so the semantics and the sentence
    describing them cannot drift apart.
    """
    from specflow.refmodel.correspondence import SYSTEM
    from specflow.refmodel.temporal import OPERATOR_CONTRACT

    assert OPERATOR_CONTRACT in SYSTEM, "shared verbatim, not paraphrased"
    for phrase in ("ONLY `False` IS A CONVICTION",
                   "A path that returns None is not a False path",
                   "strong=True",
                   "tested BEFORE `until`",
                   "one window per RISING activation"):
        assert phrase in SYSTEM, phrase
    # The author states all of this too; the point is that BOTH now do.
    from specflow.refmodel.oracle_gen import SYSTEM as AUTHOR
    for w in ("strong=True", "stable", "eventually"):
        assert AUTHOR.count(w) and SYSTEM.count(w), w


def test_the_EVIDENCE_DRIVER_enriches_before_anything_reads_the_contract():
    """The second call site, and the one that was missing.

    `top_agent` has always enriched; `docs/evidence/downstream.py` never did, so
    every run in the evidence series shipped a contract with no `cmd` table and
    the oracle author guessed. Measured on n4-i2c: of 18 numeric `cmd` values
    normalization wrote, 8 were right, 5 wrong and 3 illegal -- `cmd=3` matches
    no arm of the design's `case`, so those windows can never open, which at
    decide time is indistinguishable from "the design never did it". READ was
    never once correct.

    Source-level, like the `top_agent` guard above, because the alternative is
    running the whole driver. What it pins is ORDER: enrichment has to happen
    before `port` is built, or the stages read the un-enriched object.
    """
    src = (Path(__file__).resolve().parents[1]
           / "docs" / "evidence" / "downstream.py").read_text()
    assert "encoding.enrich_contract" in src
    assert "encoding.find_defines" in src
    # A runtime switch, not an environment variable.
    assert "--defines-root" in src
    assert src.index("enrich_contract") < src.index("port = resumable(")


# ---------------------------------------------- a value-set of SYMBOLS


def _contract_with_encoding() -> dict:
    """A contract carrying `cmd`'s real table, harvested from the design's own
    defines rather than typed in, so the values cannot drift from the design."""
    from specflow.encoding import parse_defines
    table = parse_defines(DEFINES.read_text())
    return {"io": [
        {"name": "cmd", "dir": "input", "width": 4,
         "encoding": {n: v for n, v in table.items() if n.startswith("I2C_CMD_")},
         "encoding_complete": True},
        {"name": "ena", "dir": "input", "width": 1},
    ]}



def test_resolve_any_turns_a_SYMBOL_SET_into_the_values_it_admits():
    """The shape the eight untriggered h2 requirements needed: "a START, STOP,
    READ or WRITE command is accepted" is one activation over four values, and
    `inputs` could only say AND."""
    from specflow.encoding import resolve_any
    c = _contract_with_encoding()
    vals, why = resolve_any(
        "cmd", ["I2C_CMD_START", "I2C_CMD_STOP", "I2C_CMD_READ",
                "I2C_CMD_WRITE"], c)
    assert why == ""
    assert vals == (1, 2, 4, 8)


def test_resolve_any_gives_a_SCALAR_back_as_a_one_tuple():
    """One shape downstream. A consumer that had to branch on scalar-vs-list
    would get the membership test right in one branch and wrong in the other."""
    from specflow.encoding import resolve_any
    c = _contract_with_encoding()
    assert resolve_any("cmd", "I2C_CMD_WRITE", c) == ((4,), "")
    assert resolve_any("cmd", 4, c) == ((4,), "")


def test_a_symbol_set_with_ONE_bad_member_resolves_to_NOTHING():
    """Dropping the bad member silently narrows the window. Rejecting the set
    whole is what puts the sentence in front of the author instead."""
    from specflow.encoding import resolve_any
    c = _contract_with_encoding()
    vals, why = resolve_any("cmd", ["I2C_CMD_START", "I2C_CMD_NOPE"], c)
    assert vals is None
    assert "I2C_CMD_NOPE" in why


def test_a_value_set_survives_annotate_as_a_list():
    """`annotate` builds the numeric form the oracle author writes comparisons
    against, so a set has to arrive there as a set."""
    from specflow.encoding import annotate
    c = _contract_with_encoding()
    got = annotate({"cmd": ["I2C_CMD_START", "I2C_CMD_STOP"], "ena": 1}, c)
    assert got == {"cmd": [1, 2], "ena": 1}
