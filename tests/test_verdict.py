

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


# --------------------------------------------------------------- ABANDONED


def test_only_an_earned_verdict_may_be_downgraded():
    """THE SOFTENING MUST BE EARNED, and this is where that is enforced.

    `UNOBSERVABLE` and `NOT_EXERCISED` used to be downgradable. They now mean
    "the resolution pass / the stimulus loop did not run" -- a harness defect,
    which is what should halt a build. Only `ABANDONED`, which no stage can emit
    without an attempt record, may soften.

    Without the split the gate rewards not trying: z-i2c reported
    `stimulus_added: 0` on all three turns with 33 oracles at NOT_EXERCISED.
    """
    from specflow.refmodel import verdict

    assert "ABANDONED" in verdict.DOWNGRADABLE
    # `NOT_EXERCISED` is out already: the stimulus loop is what earns the
    # softening and reaching the verdict means it did not run. `UNOBSERVABLE`
    # follows when the resolution pass exists -- see
    # `test_advisory_verdicts.test_unobservable_leaves_this_set_when_it_gains_a_route`,
    # which pins the pairing so the two cannot drift apart.
    assert "NOT_EXERCISED" not in verdict.DOWNGRADABLE
    issue = verdict.to_issue("REQ-0000", "NOT_EXERCISED",
                             advisory={"NOT_EXERCISED"})
    assert issue.severity == "error", "a skipped loop must not soften"


def test_an_abandoned_verdict_softens_only_when_the_caller_asks():
    from specflow.refmodel import verdict

    assert verdict.to_issue("REQ-0000", "ABANDONED").severity == "error"
    soft = verdict.to_issue("REQ-0000", "ABANDONED", advisory={"ABANDONED"})
    assert soft.severity == "warning"


def test_abandoned_blocks_and_routes_nowhere():
    """It still blocks by default -- softening is the caller's choice. And it
    routes to nobody, because the attempt ran and ran out: there is no party
    left with a move, which is exactly what distinguishes it from the verdicts
    that accuse someone."""
    from specflow.refmodel import verdict

    assert "ABANDONED" in verdict.BLOCKING
    assert verdict.ROUTE["ABANDONED"].startswith("none")


def test_the_reasons_are_a_closed_set():
    """A free-text reason would let one stage report "gave up" without saying
    which bounded attempt ran out, which is the evidence the discard rests on."""
    from specflow.refmodel import verdict

    assert verdict.ABANDONED_REASONS == frozenset({
        "no observation route found", "never reached",
        "no check survived repair"})
