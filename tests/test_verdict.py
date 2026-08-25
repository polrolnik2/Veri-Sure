

# ------------------------------------------------- truncation is the stimulus


class _R:
    """Enough of `OracleResult` to exercise `of_result`."""

    def __init__(self, ok, detail="", edge=None, rows=(), broken="",
                 model_broke=False):
        self.ok, self.detail, self.edge = ok, detail, edge
        self.rows, self.broken, self.model_broke = list(rows), broken, model_broke


def _trace(last):
    return [{"edge": e, "outputs": {}} for e in range(last + 1)]


def test_running_out_of_trace_is_the_stimulus_not_the_design():
    """An oracle asserting "eventually X" can fail two ways, with two owners.

    Measured on w-i2c: of the 15 oracles a KNOWN-GOOD control fails, seven fail
    by reaching the end -- and reporting those as VIOLATES is what sent the
    debug agent after edits that cannot exist.
    """
    from specflow.refmodel.verdict import of_result

    assert of_result(_R(False, "al never asserted before end of trace",
                        edge=3, rows=_trace(40))) == "NOT_EXERCISED"
    assert of_result(_R(False, "never returned both lines to released idle",
                        edge=9, rows=_trace(40))) == "NOT_EXERCISED"


def test_a_defect_on_the_last_edge_is_still_a_defect():
    """The heuristic this pins the ABSENCE of.

    "Failed at the last edge" was tried as a second signal and removed: it
    cannot tell "the trace ran out while I waited" from "the defect happened to
    be at the end". It silently reclassified a real violation -- a fixture whose
    model drives `y` high on the final row, which the oracle correctly failed --
    and that is the reclassification-to-flatter-the-numbers this must not do.

    The cost is honest and smaller than feared: only REQ-0066 (failed at edge
    210 of 210, saying nothing about waiting) is lost. REQ-0025 is still caught
    by its own wording -- "no later dout change" -- so the detector removes 6 of
    the 15 rather than 7.
    """
    from specflow.refmodel.verdict import of_result

    assert of_result(_R(False, "y rose but should not",
                        edge=9, rows=_trace(9))) == "VIOLATES"


def test_a_real_defect_mid_trace_is_still_VIOLATES():
    """The reclassification must not swallow findings. REQ-0038 fails at edge
    29 of 52 with room to spare, and is a genuine disagreement."""
    from specflow.refmodel.verdict import of_result

    assert of_result(_R(False, "FSM-driven outputs changed while ena==0",
                        edge=29, rows=_trace(52))) == "VIOLATES"


def test_unknown_edges_do_not_guess():
    """No rows and no edge is not evidence of truncation."""
    from specflow.refmodel.verdict import of_result

    assert of_result(_R(False, "busy was 1, expected 0")) == "VIOLATES"


def test_conforms_and_broken_are_untouched():
    from specflow.refmodel.verdict import of_result

    assert of_result(_R(True, "ok", edge=9, rows=_trace(9))) == "CONFORMS"
    assert of_result(_R(None, "", rows=_trace(9))) == "NOT_EXERCISED"
    assert of_result(_R(False, "x", broken="raised")) == "UNDECIDED"
    assert of_result(_R(False, "x", model_broke=True)) == "VIOLATES"
