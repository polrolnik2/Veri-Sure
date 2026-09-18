"""A PROBE TAKES THE SPECIFICATION'S NAME FOR THE STATE, WHERE IT HAS ONE.

The rule in force said the opposite -- "name them for the situation, not for
the mechanism" -- and on an I2C bit controller the author obeyed. The
specification names `cSCL`, `cSDA`, `scl_sync`, `sda_chk`, `sta_condition`,
`sto_condition`, `clk_en` and `filter_cnt`; not one of the seventeen probes
carried any of those names. They came back as `filtered_scl_high`,
`scl_sync_active`, `start_condition`.

The cost is a chain, and its end is the number this stage is furthest from.
"The controller captures the raw scl_i and sda_i signals into two-stage
internal synchronization registers cSCL and cSDA" has no probe to name, so
`normalize` routes it to a declared output -- `busy` -- and every check written
for it infers a START/STOP signature from raw input edges and asserts about a
port the requirement never mentions. That check convicted the known-good
reference design, alone in its run, and no golden-free instrument could see
anything wrong with it: zero convictions of seven spec-derived designs, zero
`placement`, zero `dissent_weighted`, zero cells closed.
"""
from __future__ import annotations

from specflow.probes import SYSTEM, ProbeEntry, ProbeOutput, _unnamed_states

SPEC = (
    "On each rising edge of clk, the controller captures the raw scl_i and "
    "sda_i signals into two-stage internal synchronization registers cSCL and "
    "cSDA. The clk_en strobe advances the state machine."
)


def _out(*names: str, aliases=()):
    return ProbeOutput(
        reasoning="r",
        probes=[ProbeEntry(name=n, notes="n", spans=["s"]) for n in names],
        aliases=list(aliases),
    )


def test_a_state_the_spec_NAMES_with_no_probe_is_reported():
    got = _unnamed_states(_out("filtered_scl_high"), SPEC, {"scl_i", "sda_i"})
    assert len(got) == 1, got
    said = got[0].message
    assert "cSCL" in said and "cSDA" in said and "clk_en" in said
    #: The declared ports are not reported -- they are already nameable.
    assert "scl_i" not in said and "sda_i" not in said


def test_the_probe_that_carries_the_name_settles_it():
    """Lower-cased, because a probe becomes a port of the generated module --
    so `cSCL` is covered by `cscl` and the comparison is case-insensitive."""
    got = _unnamed_states(_out("cscl", "csda", "clk_en"), SPEC,
                          {"scl_i", "sda_i"})
    assert got == [], got[0].message if got else ""


def test_an_alias_settles_it_too():
    """`ALIAS` is the other answer the stage may give: the interface already
    exposes the term under a different name, and a probe would then hand the
    check author two names for one wire."""
    from specflow.probes import Alias

    got = _unnamed_states(
        _out("csda", "clk_en", aliases=[Alias(term="cSCL", port="scl_i",
                                              span="s")]),
        SPEC, {"scl_i", "sda_i"})
    assert got == [], got[0].message if got else ""


def test_it_WARNS_and_never_blocks():
    """An identifier-shaped token in prose is a heuristic: it catches a module
    name and a signal mentioned in passing. A screen whose false-positive rate
    is unmeasured does not block -- this tree has twice paid for one that did.
    `i2c_master_bit_ctrl` in the finding above is exactly such a false
    positive, and it is why this reports rather than rejects."""
    got = _unnamed_states(_out("nothing_matching"), SPEC, set())
    assert got and all(i.severity == "warning" for i in got)


def test_the_prompt_asks_for_the_specifications_own_name_FIRST():
    """A prompt-content pin: the ordering is the whole rule. 'Name for the
    situation' survives, as the fallback for a state the text describes without
    naming, and a deletion here is invisible in every behavioural test."""
    assert "WHEN THE SPECIFICATION NAMES THE STATE, USE ITS NAME" in SYSTEM
    assert "`cSCL` -> `cscl`" in SYSTEM
    #: The fallback is still there and is explicitly second.
    assert "when, and only when, the specification does not" in SYSTEM
    #: And the measured consequence travels with the rule.
    assert "convicted the known-good reference design" in SYSTEM

    first = SYSTEM.index("WHEN THE SPECIFICATION NAMES THE STATE")
    second = SYSTEM.index("NAME THEM FOR THE SITUATION when")
    assert first < second, "the fallback is stated before the rule"
