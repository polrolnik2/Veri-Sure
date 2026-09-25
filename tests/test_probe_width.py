"""A probe takes the width the specification STATES -- and a one-bit predicate
may not borrow the name of a wider quantity."""
from eda_agent.contract_linter import names_a_multibit_quantity, probe_issues, stated_width

SPEC = (
    "A filter counter, `filter_cnt`, derives its sampling interval from clk_cnt. "
    "Whenever this counter expires, new synchronized samples are shifted into the "
    "three-sample histories `fSCL` and `fSDA`. The filtered outputs `sSCL` and "
    "`sSDA` are generated using a majority function over the three-sample "
    "histories. wire [67:0] fifo_dat_i: Fifo data input. The core datapath is the "
    "8-bit shift register `sr`. When `shift` is asserted, sr shifts left. The module "
    "transmits eight bits through core_txd. reg outstanding_store: Outstanding "
    "store. The outstanding_store register tracks a pending store.")


def _probe(name, width=1):
    return {"name": name, "dir": "probe", "width": width,
            "licensed_by": ["REQ-1"], "spans": ["A filter counter, `filter_cnt`,"]}


def _errors(p):
    return [i for i in probe_issues([p], SPEC) if i.severity == "error"
            and ("width" in i.path or i.path.endswith(".name"))]


def test_stated_widths_are_read_from_the_name_they_belong_to():
    assert stated_width(SPEC, "fscl") == 3 and stated_width(SPEC, "fsda") == 3
    assert stated_width(SPEC, "fifo_dat_i") == 68
    assert stated_width(SPEC, "sr") == 8
    #: A neighbour's width is not this name's width.
    assert stated_width(SPEC, "sscl") is None
    #: English words and counts over time are not widths.
    assert stated_width(SPEC, "shift") is None
    assert stated_width(SPEC, "core_txd") is None


def test_a_stated_width_is_the_width():
    assert _errors(_probe("fscl", 1)), "a 3-bit history minted as one bit"
    assert not _errors(_probe("fscl", 3))
    assert _errors(_probe("fifo_dat_i", 1))


def test_an_unstated_width_is_still_refused():
    assert _errors(_probe("sscl", 2))


def test_a_one_bit_predicate_may_not_take_a_counters_name():
    assert names_a_multibit_quantity(SPEC, "filter_cnt")
    assert _errors(_probe("filter_cnt", 1))
    assert not _errors(_probe("filter_cnt_expired", 1))


def test_a_one_bit_register_is_not_multibit_by_being_called_a_register():
    assert not names_a_multibit_quantity(SPEC, "outstanding_store")
    assert not _errors(_probe("outstanding_store", 1))
