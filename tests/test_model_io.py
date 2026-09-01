

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
                            small_model="small", small_effort="medium",
                            deep_effort="high")
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


def test_deep_effort_is_off_by_default():
    """A measured retreat, not caution.

    It shipped as "high". Against a real ~19 KB oracle prompt through this
    gateway that killed the stream SIX times running -- RemoteProtocolError,
    "0 chars so far" -- at chunk 9000 and again at 24000, so a wider slice does
    not rescue it. The same model answers in 3.5s at "high" on a one-line
    prompt, so it is effort interacting with prompt size.

    Left on, it would have broken every oracle call in every run.
    """
    from specflow.model_io import PortSettings

    assert PortSettings().deep_effort is None
    # But when it IS turned on, the slice must still fit it -- the pairing bug
    # that came first, and which switching the default off would otherwise hide.
    assert PortSettings(deep_effort="high").chunk_for("high") > \
        PortSettings.responses_chunk


def test_deep_effort_never_overrides_an_explicit_caller_effort():
    """`deep_effort` raises the SMALL tier. With no small tier, it is a no-op.

    Found by it silently ruining an experiment. A script launched with
    `PortSettings(model="gpt-5-mini", effort="medium")` ran every oracle call at
    `high`, because the deep-effort branch answered before the caller's own
    effort was consulted — and the run was then reported as a medium-effort arm
    on the strength of the label on the command line.

    That is the exact failure `PortSettings`' own docstring names: a switch a
    caller sets and a callee silently overrides is worse than no switch.
    """
    from specflow.model_io import PortSettings

    caller = PortSettings(model="gpt-5-mini", effort="medium",
                          deep_effort="high")
    assert caller.for_stage("oracle_REQ-0001") == (None, None), (
        "deep_effort overrode an effort the caller set explicitly")

    # With a small tier present it does its job.
    tiered = PortSettings(model="big", effort="xhigh", small_model="mini",
                          small_effort="medium", deep_effort="high")
    assert tiered.for_stage("oracle_REQ-0001") == ("mini", "high")
    assert tiered.for_stage("variant_REQ-0001_trigger") == ("mini", "medium")

    # `small_effort` alone is enough of a tier to raise.
    effort_only = PortSettings(small_effort="low", deep_effort="high")
    assert effort_only.for_stage("oracle_REQ-0001") == (None, "high")


def test_the_prefix_sentinel_cannot_drift():
    """`model_io` duplicates `fanout.PREFIX_SENTINEL` instead of importing it.

    It has to: `fanout` imports `stage` and `stage` imports `model_io`, so the
    import would close a cycle. A duplicated constant that silently diverges
    would make `_seed_id` split the prompt in the wrong place -- or, more
    likely, never find a boundary and quietly do nothing.
    """
    from specflow.fanout import PREFIX_SENTINEL
    from specflow.model_io import _PREFIX_SENTINEL

    assert _PREFIX_SENTINEL == PREFIX_SENTINEL


def test_prefix_seeding_is_off_and_inert_by_default():
    """It is unproven -- see `PortSettings.prefix_seed` -- so it must not fire.

    `_seed_id` returns None without touching the client on every path that
    should not seed, which is what lets the flag ship dark: the transport sends
    the flat prompt exactly as it did before the code existed.
    """
    from pathlib import Path

    from specflow.fanout import PREFIX_SENTINEL
    from specflow.model_io import ApiPort, PortSettings

    with_sentinel = f"shared{PREFIX_SENTINEL}\n\nitem"
    off = ApiPort(root=Path("/tmp"), settings=PortSettings())
    assert off.settings.prefix_seed is False
    # A client of None proves it is never called: any use would raise.
    assert off._seed_id(None, None, stage="oracle_REQ-0001",
                        prompt=with_sentinel) is None

    # On, but a whole-artifact prompt has no shared prefix to hoist.
    on = ApiPort(root=Path("/tmp"), settings=PortSettings(prefix_seed=True))
    assert on._seed_id(None, None, stage="refmodel",
                       prompt="no sentinel here") is None
