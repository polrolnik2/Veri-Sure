"""The phase rule must REACH the author, not merely exist in the module.

A specification writes an equation, not a schedule: "sto_condition = sSDA &
~dSDA & sSCL" says what the condition IS and never says whether the design
offers it in the same cycle or registers it from that cycle. A check that
asserts the probe is already high at the edge its defining transition occurs
admits only one of the two faithful readings.

Measured on `i2c_master_bit_ctrl`: where that formula holds, the known-good
design asserts the probe one edge later 499 times out of 499 and the
spec-derived population asserts it on the same edge 22 of 22. Five checks
written the tight way convict the known-good design, and correcting only those
two probes' phase moves audit from 24.3% to 5.7% with span and blindness
unchanged to four decimal places.

**PINNED AT THE ASSEMBLY SITE, NOT THE CONSTANT.** Prompt text on this branch
has twice been deleted without failing a single behavioural test, because
asserting on the constant still passes when the constant stops being sent.
`shared_prefix` is what the stage actually hands the author.
"""
import pytest

from specflow.refmodel.oracle_gen import shared_prefix

CONTRACT = {"module_name": "m", "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 1},
    {"name": "sto_condition", "dir": "probe", "width": 1},
]}


@pytest.fixture
def prefix():
    """Whitespace-collapsed, so a pin does not break on re-wrapping.

    The rule is prose in a hard-wrapped block: "at the very edge\nits defining
    transition occurs" is one phrase to a reader and two lines to `in`. A pin
    that fails when someone reflows a paragraph trains people to delete pins.
    """
    return " ".join(shared_prefix("{}", CONTRACT, spec="a specification").split())


def test_the_rule_reaches_the_author(prefix):
    assert "A SPECIFICATION WRITES AN EQUATION, NOT A SCHEDULE" in prefix, (
        "the phase rule must be in what the stage HANDS the author; asserting "
        "on the module constant passes even when the constant stops being sent")


def test_it_names_the_thing_not_to_do(prefix):
    assert "at the very edge its defining transition occurs" in prefix


def test_it_states_the_licence_rather_than_banning_the_claim(prefix):
    """A requirement that states its timing may assert it."""
    for licensed in ("immediately", "on the next clock", "within N cycles"):
        assert licensed in prefix, (
            "the rule has to say WHEN the tight form is legitimate, or an "
            "author reads it as a ban and writes a vacuous check instead")


def test_it_carries_the_measurement(prefix):
    """A rule with no evidence behind it is the first thing dropped."""
    assert "499 times out of 499" in prefix
    assert "24.3% to 5.7%" in prefix


def test_it_offers_the_operator_that_admits_both_readings(prefix):
    assert "eventually" in prefix and "until=" in prefix


def test_the_normalized_window_is_a_reading_not_a_fact(prefix):
    """Normalization may propose the window. It may not impose it.

    `gate_one` asks whether the response parsed, whether there is one block,
    whether `clk` is in the window and whether the port names are declared. It
    never asks whether the window is licensed by the requirement's own words,
    and `oracle_gen`'s own comment names the result: "a wrong window arrives as
    an instruction and departs as the author's defect."

    Measured on i2c: `effect_follows` is True on 52 requirements and unlicensed
    by the text on 39 of them; 27 of those reached a shipped check and two
    convict a known-good design.
    """
    assert "OVERRULE IT" in prefix, "the requirement's words beat the block"
    assert "START THERE" in prefix, (
        "the block is still the starting point -- one window per requirement "
        "rather than one per author's taste is what makes neighbouring checks "
        "comparable, and that reason survives")
    assert "TRANSCRIBE IT" not in prefix
    assert "JUDGEMENT, NOT A FACT" in prefix


def test_it_names_effect_follows_and_gives_the_test(prefix):
    """The field that carries |=> vs |-> is the one worth re-reading."""
    assert "effect_follows" in prefix
    assert "after_activation=False" in prefix, (
        "an author told the block may be wrong, without being told what right "
        "looks like, rewrites windows nothing objected to")
    assert "39 of those" in prefix, (
        "the measurement has to travel with the instruction; a rule with no "
        "evidence behind it is the first thing dropped")


def test_it_says_which_change_to_record(prefix):
    assert "say in your reasoning which" in prefix, (
        "a departure from the block that is not recorded cannot be reviewed")


def test_the_effect_follows_paragraph_names_no_design():
    """MY addition to the shared briefing, specifically.

    `SYSTEM` carries deliberate worked examples drawn from one design -- the
    `sda_i` open-drain case, the `cmd_ack` trigger case -- and those are not in
    question here; `test_counting_guidance_is_general_and_names_no_design`
    scopes neutrality to the block that was once overfitted. This pins only the
    paragraph added with the effect_follows measurement, which cites a count
    and must not cite a port.
    """
    from specflow.refmodel.oracle_gen import SYSTEM

    i = SYSTEM.index("THIS BLOCK IS A JUDGEMENT, NOT A FACT")
    para = SYSTEM[i:SYSTEM.index("So `effect_follows` in particular", i)]
    assert "39 of those" in para, "the measurement must be here"
    for token in ("sda_i", "scl_i", "cmd_ack", "slave_wait", "al`", "i2c"):
        assert token not in para, (
            f"{token!r} makes a general rule look like one design's problem")
