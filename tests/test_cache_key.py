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
