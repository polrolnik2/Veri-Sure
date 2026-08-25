

def test_oracles_get_more_reasoning_on_the_same_model():
    """Measured, not assumed.

    Eleven oracles `[O]` could not make non-vacuous were re-authored at full
    strength; of the first five, one produced a check `gpt-5-mini`/medium could
    not write. The arms were unequal in the direction that strengthens it: the
    originals had three attempts with the counterexample fed back, the
    re-author had one shot with none, because `run_oracle_gen`'s repair loop
    gates on `gate_one`, which is structural only. So 20% is a floor.

    Pulled with reasoning rather than by promoting the model: a 77-call fan-out
    must not change which model serves it, which is what
    `test_no_fanned_out_stage_is_full_strength_by_default` guards.

    The stage is named per requirement (`oracle_REQ-0001`, and `_fix1` on a
    repair pass), so this depends on `for_stage` matching the leading segment.
    Exact membership could never name one of them.
    """
    from specflow.model_io import PortSettings

    settings = PortSettings(model="big", effort="xhigh",
                            small_model="small", small_effort="medium")
    for stage in ("oracle_REQ-0001", "oracle_REQ-0001_fix1"):
        assert settings.for_stage(stage) == ("small", "high"), stage

    # Off switch: no deep_effort leaves them exactly where they were.
    off = PortSettings(small_model="small", small_effort="medium",
                       deep_effort=None)
    assert off.for_stage("oracle_REQ-0001") == ("small", "medium")

    # The narrow checks stay small: they are the ones whose cost this pays for.
    for stage in ("correspond_REQ-0001", "variant_REQ-0001_trigger",
                  "stimulus_TP-0007"):
        assert settings.for_stage(stage) == ("small", "medium"), stage


def test_the_continuation_slice_scales_with_effort():
    """A slice is a budget for REASONING AND CONTENT TOGETHER.

    Below the reasoning budget it yields no content, the continuation makes no
    progress, and the stream is reaped -- the trap the continuation mechanism
    exists to escape, entered from the other side.

    Found by shipping `deep_effort="high"` beside the 9000 default: the first
    call died with `RemoteProtocolError ... continuation 1/6, 0 chars so far` on
    an 18 KB prompt. Raising oracle effort would have taken every oracle call
    with it.
    """
    from specflow.model_io import PortSettings

    s = PortSettings()
    assert s.chunk_for("high") > s.chunk_for("medium")
    assert s.chunk_for("xhigh") >= s.chunk_for("high")
    # An unknown or absent effort falls back rather than raising.
    assert s.chunk_for(None) == s.chunk_for("medium")
    assert s.chunk_for("nonsense") == s.responses_chunk


def test_a_slice_a_caller_set_is_never_shrunk():
    """The table RAISES for deeper effort; it must not override a deliberate
    caller value downward."""
    from specflow.model_io import PortSettings

    s = PortSettings(responses_chunk=30000)
    assert s.chunk_for("medium") == 30000
    assert s.chunk_for("xhigh") >= 30000


def test_the_shipped_deep_effort_gets_a_slice_that_fits_it():
    """The two defaults have to agree, which is the bug this pins."""
    from specflow.model_io import PortSettings

    s = PortSettings()
    assert s.deep_effort == "high"
    assert s.chunk_for(s.deep_effort) > PortSettings.responses_chunk
