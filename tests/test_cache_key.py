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


def test_the_debug_loop_gets_its_own_key_and_a_bare_call_gets_a_derived_one():
    """One agent is one shared prefix: its system prompt and tool schema are
    identical on every call of every turn.

    THIS TEST USED TO ASSERT THE OPPOSITE OF ITS SECOND HALF -- that "an agent
    given no key must behave exactly as it did before this existed", i.e. sends
    no key at all. That was the defect, not the contract: arm A takes this
    module whole from HEAD but its seven agents from the merge base, where no
    call site passes a key, so every request it ever made went out unrouted
    with the mechanism sitting unused one frame away. A bare call now derives a
    key from the CALLER's module, which is per-prefix exactly as an explicit
    one is."""
    from eda_agent.config import OpenAIConfig
    from eda_agent.model import make_openai_model

    cfg = OpenAIConfig(model="gpt-5.6-luna", api_key="x",
                       base_url="http://localhost")
    keyed = make_openai_model(cfg, cache_key="refmodel-debug")
    assert (keyed._base_model.generate_kwargs["prompt_cache_key"]
            == "veri-sure:refmodel-debug:gpt-5.6-luna")
    # Derived from this test module, and never absent.
    bare = make_openai_model(cfg)._base_model.generate_kwargs
    assert bare["prompt_cache_key"] == "veri-sure:test_cache_key:gpt-5.6-luna"


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


# -------------------------------------------- the eda_agent side of the door
def _built_from(module_name: str, **kw):
    """Build a model as if `make_openai_model` were called from `module_name`.

    The derivation reads the CALLER's frame, so the only faithful way to
    exercise it is to call from globals carrying that `__name__`.
    """
    from eda_agent.config import OpenAIConfig
    from eda_agent.model import make_openai_model
    cfg = OpenAIConfig(model="gpt-5-mini", api_key="dummy",
                       base_url="https://example.invalid/v1")
    ns = {"make_openai_model": make_openai_model, "cfg": cfg, "kw": kw,
          "__name__": module_name}
    exec("m = make_openai_model(cfg, **kw)", ns)  # noqa: S102 -- see docstring
    return ns["m"].generate_kwargs


def test_an_agent_that_passes_no_key_still_gets_one():
    """OPT-IN WAS THE BUG, and this is the pin for it.

    `make_openai_model` used to set `prompt_cache_key` only when handed one, so
    an agent that did not pass one sent every request unrouted and nothing said
    so. Measured: arm A (`benchmarks/make_arm_a.sh`) takes eda_agent/model.py
    whole from HEAD but its seven agents from the merge base, where
    `git grep cache_key` matches nothing -- so the mechanism was present and
    unused on every request that arm ever made.

    Byte replay reached that arm because it lives INSIDE the single door
    (`make_formatter`). The key did not, because it was handed in from outside.
    """
    got = _built_from("eda_agent.rtl_editor")
    assert got["prompt_cache_key"] == "veri-sure:rtl_editor:gpt-5-mini"


def test_the_default_is_still_ONE_KEY_PER_PREFIX_not_a_shared_pool():
    """The property that must survive the convenience.

    Pooling two agents would send traffic to a backend holding a head it cannot
    use -- every agent has its own system prompt and tool schema, so every agent
    is its own prefix. A default that collapsed them would be worse than none.
    """
    a = _built_from("eda_agent.rtl_editor")["prompt_cache_key"]
    b = _built_from("eda_agent.tb_editor")["prompt_cache_key"]
    assert a != b


def test_an_explicit_key_beats_the_derived_one():
    """The seven explicit keys stay, and stay authoritative: they survive a file
    rename, and a module that grows a second differently-prefixed agent has to
    say so rather than silently pooling the two under one module name."""
    got = _built_from("eda_agent.rtl_editor", cache_key="rtl-debug")
    assert got["prompt_cache_key"] == "veri-sure:rtl-debug:gpt-5-mini"


def test_a_key_already_in_generate_kwargs_is_not_overwritten():
    """`setdefault`, not assignment -- a caller that has chosen a key for its
    own reasons keeps it."""
    from eda_agent.config import OpenAIConfig
    from eda_agent.model import make_openai_model
    cfg = OpenAIConfig(model="gpt-5-mini", api_key="dummy",
                       base_url="https://example.invalid/v1",
                       generate_kwargs={"prompt_cache_key": "mine"})
    assert make_openai_model(cfg).generate_kwargs["prompt_cache_key"] == "mine"


def test_every_shipped_agent_still_names_its_own_key():
    """The census, so a new agent module cannot quietly join an existing pool."""
    import pathlib
    import re
    seen = {}
    for path in pathlib.Path("eda_agent").glob("*.py"):
        for m in re.finditer(r'make_openai_model\([^)]*cache_key=["\']([^"\']+)',
                             path.read_text(encoding="utf-8")):
            seen.setdefault(m.group(1), []).append(path.name)
    assert set(seen) == {"rtl-debug", "tb-debug", "refmodel-debug", "architect",
                         "asserter", "rtl-generate", "boolean-proofer"}, seen
    assert all(len(v) == 1 for v in seen.values()), seen


# --------------------------------------- reading usage off a dict-subclass
def test_usage_is_read_off_a_dict_subclass_without_raising():
    """THE CRASH THIS PINS, and it killed a full run at its first call.

    agentscope's `ChatUsage` subclasses `dict` through `DictMixin`, so its
    `__getattr__` is `self[name]` and a missing key raises KeyError -- which the
    three-argument `getattr` does NOT absorb, because its default only covers
    AttributeError. `getattr(usage, "input_tokens_details", None)` therefore
    raises rather than returning None, and the cached-token instrumentation sat
    on exactly that call.

    Live: c1-i2c died on its first model response with
    `KeyError: 'input_tokens_details'`, produced no specflow/ directory at all,
    and EXITED 0 -- the leaf exception is caught and reported as a result, so a
    total failure reads as a run that happened to make nothing.
    """
    from specflow.cache_stats import _attr

    class _DictUsage(dict):
        """`ChatUsage`'s shape: attribute access delegates to the mapping."""
        def __getattr__(self, name):
            return self[name]        # KeyError, not AttributeError

    u = _DictUsage(input_tokens=10, output_tokens=5)
    assert getattr(u, "input_tokens") == 10
    try:
        getattr(u, "input_tokens_details", None)
        raise AssertionError("expected the KeyError this test exists for")
    except KeyError:
        pass
    assert _attr(u, "input_tokens_details") is None
    assert _attr(u, "input_tokens") == 10
    assert _attr(u, "nope", "dflt") == "dflt"


def test_the_same_reader_handles_plain_objects_and_plain_dicts():
    """Both real API shapes still work: the OpenAI SDK returns pydantic objects
    on one path and this repo reads recorded JSON on another."""
    from specflow.cache_stats import _attr, _first_int

    class _Obj:
        input_tokens = 3

    assert _attr(_Obj(), "input_tokens") == 3
    assert _attr(_Obj(), "missing", "dflt") == "dflt"
    assert _attr({"input_tokens": 7}, "input_tokens") == 7
    # Chat-shaped and Responses-shaped names, neither raising on the other.
    assert _first_int({"prompt_tokens": 4}, ("input_tokens", "prompt_tokens")) == 4
    assert _first_int({"input_tokens": 9}, ("input_tokens", "prompt_tokens")) == 9
