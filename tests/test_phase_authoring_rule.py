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
