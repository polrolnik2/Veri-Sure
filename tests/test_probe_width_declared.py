"""A probe may be a VALUE, not only a situation, when the specification says so.

`ProbeEntry.as_io` pinned every probe to `width: 1` -- "width is not the
model's to choose" -- and `probe_block` told the author, unconditionally, to
maintain each as a BOOLEAN. The pair agreed with each other and both were wrong
wherever the specification names a value.

On `i2c_master_bit_ctrl` the stage minted `fscl` and `fsda` (the three-sample
histories), `filter_cnt` (a counter) and `cscl`/`csda` (two-stage registers) as
one-bit booleans -- beside its own `spans` field quoting "the three-sample
histories `fSCL` and `fSDA`" and "a filter counter, `filter_cnt`". Those five
are exactly the probes that bind a wider signal on a design written from the
specification rather than from this contract: 3 bits, 3, 14, 2 and 2.

The default stays 1. A width the model INVENTS is still not the model's to
choose; a width the specification STATES is a fact it may report.
"""
from specflow.probes import ProbeEntry
from specflow.refmodel.compose import probe_block, probe_widths

SITUATION = {"name": "idle", "dir": "probe", "width": 1, "notes": "the FSM is idle"}
VALUE = {"name": "fscl", "dir": "probe", "width": 3,
         "notes": "the three-sample filtered history"}


def test_a_probe_is_one_bit_unless_it_says_otherwise():
    assert ProbeEntry(name="idle").as_io()["width"] == 1


def test_a_declared_width_reaches_the_contract():
    assert ProbeEntry(name="fscl", width=3).as_io()["width"] == 3, (
        "a width the specification states must survive into contract['io'], "
        "or the runtime guard compares against 1 and refuses the binding")


def test_a_nonsense_width_falls_back_to_one():
    assert ProbeEntry(name="x", width=0).as_io()["width"] == 1


def test_the_width_reaches_the_runtime_map():
    """`probe_widths` is what `Env.sample` binds against."""
    contract = {"io": [SITUATION, VALUE]}
    assert probe_widths(contract) == {"idle": 1, "fscl": 3}


def test_the_author_is_told_which_probes_are_values():
    block = probe_block({"io": [SITUATION, VALUE]}, "step")
    assert "`fscl` [3 bits]" in block, "the bit count has to be visible in the list"
    assert "INTEGER attribute, not a flag" in block, (
        "an author told 'maintain each as a BOOLEAN' will squeeze a "
        "three-sample history into a flag, which is the defect this fixes")
    assert "WITHOUT a bit count is a situation" in block, (
        "the one-bit probes must still be described as situations, or the "
        "author makes all 24 of them integers")


def test_an_all_situation_contract_keeps_the_simple_briefing():
    """No wide probe, no paragraph about integers -- it would only confuse."""
    block = probe_block({"io": [SITUATION]}, "step")
    assert "BOOLEAN ATTRIBUTE" in block
    assert "INTEGER attribute" not in block
    assert "[" not in block.split("A probe is a specification term")[0], (
        "a one-bit probe carries no bit count in the list")


def test_no_probes_still_says_nothing():
    assert probe_block({"io": [{"name": "q", "dir": "output", "width": 1}]},
                       "step") == ""
