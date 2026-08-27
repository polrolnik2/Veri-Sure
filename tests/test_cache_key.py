"""`prompt_cache_key`: the routing hint that makes a shared prefix pay.

A prompt cache lives on the backend that served the request. With many distinct
prefixes in flight -- eight stage families across sixteen fan-out workers, plus
a debug loop re-sending one growing conversation -- two calls that share a
prefix can land on different backends and neither sees the other's entry. The
key says "send these together".

It has to group EXACTLY what the prefix shares. Too fine and it routes nothing;
too coarse and it sends traffic to a backend holding a head it cannot use.
"""

from __future__ import annotations

from specflow.model_io import _cache_key, _responses_body


class _Cfg:
    model = "gpt-5-mini"
    reasoning_effort = "medium"
    generate_kwargs: dict = {}


def test_one_key_per_stage_FAMILY_not_per_item():
    """Per item would give one key per call and pool nothing, which is the same
    defect `cache_stats` records one level down: keying on the raw stage name
    gave 65 keys of one call each."""
    k = _cache_key(_Cfg(), "normalize_indirect_REQ-0002")
    assert k == _cache_key(_Cfg(), "normalize_indirect_REQ-0007")
    assert k == "specflow:normalize_indirect:gpt-5-mini"


def test_families_with_different_prefixes_do_not_share_a_key():
    """`family()` exists because splitting at the first underscore pooled
    `normalize_indirect` with `normalize`, and the two have DIFFERENT shared
    prefixes -- different system text, different port note."""
    assert (_cache_key(_Cfg(), "normalize_indirect_REQ-0002")
            != _cache_key(_Cfg(), "normalize_REQ-0002"))
    assert (_cache_key(_Cfg(), "oracle_REQ-0001_r0")
            != _cache_key(_Cfg(), "correspond_REQ-0001_r0"))


def test_the_model_is_in_the_key():
    """A cache entry is per model. Pooling two models under one key sends half
    the traffic to a backend holding a head it cannot use."""
    class _Other(_Cfg):
        model = "gpt-5.6-luna"

    assert _cache_key(_Cfg(), "oracle_x") != _cache_key(_Other(), "oracle_x")


def test_the_responses_body_carries_it_and_omits_it_with_no_stage():
    body = _responses_body(_Cfg(), "p", stage="oracle_REQ-0001_r0")
    assert body["prompt_cache_key"] == "specflow:oracle:gpt-5-mini"
    assert "prompt_cache_key" not in _responses_body(_Cfg(), "p")


def test_an_explicitly_configured_key_is_not_overridden():
    """`generate_kwargs` is the operator's channel. A default that silently beat
    it would make the switch a lie."""
    from eda_agent.config import OpenAIConfig
    from eda_agent.model import make_openai_model

    cfg = OpenAIConfig(model="m", api_key="x", base_url="http://localhost",
                       generate_kwargs={"prompt_cache_key": "mine"})
    m = make_openai_model(cfg, cache_key="refmodel-debug")
    assert m._base_model.generate_kwargs["prompt_cache_key"] == "mine"


def test_the_debug_loop_gets_its_own_key_and_others_are_unchanged():
    """One agent is one shared prefix: its system prompt and tool schema are
    identical on every call of every turn. An agent given no key must behave
    exactly as it did before this existed."""
    from eda_agent.config import OpenAIConfig
    from eda_agent.model import make_openai_model

    cfg = OpenAIConfig(model="gpt-5.6-luna", api_key="x",
                       base_url="http://localhost")
    keyed = make_openai_model(cfg, cache_key="refmodel-debug")
    assert (keyed._base_model.generate_kwargs["prompt_cache_key"]
            == "veri-sure:refmodel-debug:gpt-5.6-luna")
    assert not make_openai_model(cfg)._base_model.generate_kwargs


def test_EVERY_agent_is_keyed_and_no_two_share_a_key():
    """One agent is one shared prefix, so one agent is one key -- and pooling two
    would route traffic to a backend holding a head it cannot use.

    Only the refmodel loop was keyed at first, because it is the largest line in
    the ledger (46.1M input tokens on a2-i2c against 10.8M for every specflow
    stage combined). But `RTLEditor` and `TBEditor` have the same shape -- a
    growing conversation re-sent through a ReAct sub-loop of up to `max_iters`
    calls, `max_trials` times -- so they had the same exposure and none of the
    routing. This pins the whole set, so a new agent added without a key is a
    test failure rather than a silent cache miss found in a bill.
    """
    import re
    from pathlib import Path

    calls: dict[str, list[str]] = {}
    for path in sorted(Path("eda_agent").glob("*.py")):
        if path.name == "model.py":
            continue
        for m in re.finditer(r"make_openai_model\((?P<args>[^)]*)\)",
                             path.read_text(encoding="utf-8")):
            calls.setdefault(path.name, []).append(m.group("args"))

    assert calls, "no call sites found -- the scan is looking in the wrong place"
    unkeyed = {name: args for name, argl in calls.items()
               for args in argl if "cache_key=" not in args}
    assert not unkeyed, f"agents constructing a model with no cache key: {unkeyed}"

    keys = [re.search(r'cache_key="([^"]+)"', a).group(1)
            for argl in calls.values() for a in argl]
    assert len(keys) == len(set(keys)), f"two agents share a prefix key: {keys}"


def test_byte_replay_is_UNIVERSAL_not_opt_in():
    """The byte-replay formatter has to reach every agent, not just the one it
    was built for. Re-serialising a tool call through our own structs can
    reorder JSON keys, and a reordered key breaks prefix matching for every
    request after it -- so the whole remaining conversation reprices as fresh.

    `make_formatter` is the single door every agent goes through, which is why
    the fix belongs there and not at a call site.
    """
    from eda_agent.model import ByteReplayFormatter, make_formatter

    assert isinstance(make_formatter("gpt-5.6-luna"), ByteReplayFormatter)
    assert isinstance(make_formatter(None), ByteReplayFormatter)


def test_the_two_long_editors_report_cached_tokens_beside_input():
    """`cached` is a SUBSET of `input`, and without it a re-sent prefix that hit
    the cache and one that missed look identical in the input total alone --
    which is exactly how a $23 debug loop reads as a cheap one.

    The model has to be reachable for this: constructed inline inside the
    `SafeReActAgent(...)` call it is only reachable through the agent, so both
    editors hold it on the instance.
    """
    import inspect

    from eda_agent.rtl_editor import RTLEditor
    from eda_agent.tb_editor import TBEditor

    for cls in (RTLEditor, TBEditor):
        assert hasattr(cls, "usage"), f"{cls.__name__} reports no usage at all"
        src = inspect.getsource(cls.__init__)
        assert "self._model = make_openai_model(" in src, (
            f"{cls.__name__} builds its model inline, so usage() cannot read it")
