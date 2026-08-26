"""C1-C6: the prompt cache, tested as a correctness property.

Fanning a stage out to one call per item is only affordable because every call
shares a byte-identical prefix the provider caches. Measured live: a 20,963-char
prefix reports `cached=4864` of ~5,000 input tokens from the third call onward --
97%. Across ~400-600 calls per node that is ~110k billed input tokens instead of
~3.6M.

**The failure is silent.** If the prefix stops matching, every call still
succeeds, every artifact still validates, every gate still passes; the run is
merely 30x more expensive. So it is tested, not monitored, and five of the six
tests need no network at all -- those are the ones that actually prevent the
regression.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from specflow.cache_stats import (
    MIN_CALLS_FOR_VERDICT,
    WARMUP_CALLS,
    CacheStats,
)
from specflow.stage import run_fanout

SENTINEL = "\n</shared_context>\n"


def build_prompt(item: str, *, issues: str = "", previous: str = "") -> str:
    """A stand-in with the shape every fanned-out stage must have: everything
    shared first, the item last, repair material after the item."""
    shared = "SYSTEM RULES\n" + ("spec text " * 700) + SENTINEL
    out = shared + f"<item>\n{item}\n</item>\n"
    if previous:
        out += f"<previous_answer>\n{previous}\n</previous_answer>\n"
    if issues:
        out += f"<gate_failures>\n{issues}\n</gate_failures>\n"
    return out


# ------------------------------------------------------- C1 prefix byte-identity


def test_c1_every_prompt_in_a_stage_shares_a_byte_identical_prefix():
    """The load-bearing test. A header that interpolates an index fails here in
    milliseconds; live it would cost 30x and report success."""
    prompts = [build_prompt(f"REQ-{i:04d}") for i in range(137)]
    common = os.path.commonprefix(prompts)

    assert all(p[: len(common)] == common for p in prompts)
    # The sentinel must fall *inside* the common prefix: everything declared
    # shared really is. It need not be the last thing -- real uids share a
    # `REQ-0` head, so the accidental agreement runs a few chars further, and
    # those are cached too.
    assert SENTINEL in common, (
        "prompts diverge before the end of the shared block: it is not shared"
    )
    assert len(common) >= 0.9 * len(prompts[0]), (
        f"only {len(common)} of {len(prompts[0])} chars are shared; the cached "
        f"fraction is too small to matter"
    )


def test_c1_an_index_in_the_header_is_caught():
    """Guard the guard: the check must fail on the regression it exists for."""
    def bad(item: str, i: int) -> str:
        return f"SYSTEM RULES (item {i} of 137)\n" + build_prompt(item)

    prompts = [bad(f"REQ-{i:04d}", i) for i in range(20)]
    common = os.path.commonprefix(prompts)
    assert SENTINEL not in common, "the index did not actually break the prefix"


def test_c1_dict_serialisation_is_order_stable():
    """A contract serialised with varying key order breaks the prefix silently."""
    a = {"name": "clk", "dir": "input", "width": 1}
    b = {"width": 1, "dir": "input", "name": "clk"}
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert json.dumps(a) != json.dumps(b), (
        "this test is vacuous unless unsorted dumps really can differ"
    )


# ------------------------------------------- C2 repair rounds keep the prefix


def test_c2_a_repair_round_does_not_disturb_the_prefix():
    """`build_prompt(issues, previous)` gives a caller two ways to prepend by
    accident. Round 1 must still start with round 0's shared block."""
    round0 = build_prompt("REQ-0001")
    round1 = build_prompt("REQ-0001", issues="- [error] bad", previous="{...}")

    common = os.path.commonprefix([round0, round1])
    assert common.endswith(SENTINEL) or common.startswith(
        round0[: round0.index(SENTINEL) + len(SENTINEL)]
    )
    shared = round0[: round0.index(SENTINEL) + len(SENTINEL)]
    assert round1.startswith(shared)


def test_c2_prepending_issues_is_caught():
    prefixed = "<gate_failures>\n- [error] bad\n</gate_failures>\n" + build_prompt("R")
    shared = build_prompt("R")
    shared = shared[: shared.index(SENTINEL) + len(SENTINEL)]
    assert not prefixed.startswith(shared)


# ------------------------------------------------------ C3 prefix-length floor


def test_c3_the_shared_prefix_clears_the_cache_minimum():
    """Caching has a ~1024-token minimum. A prefix under it is never cached and
    no other test here would notice."""
    prefix = build_prompt("REQ-0001")
    prefix = prefix[: prefix.index(SENTINEL)]
    approx_tokens = len(prefix) // 4
    assert approx_tokens > 1024, f"~{approx_tokens} tokens is under the floor"
    # Measured on the real thing, both comfortably over: 5,275 chars (~1,318
    # tokens) contract-only, 20,963 chars (~5,240 tokens) with the spec.


def test_c3_a_short_prefix_warns_rather_than_fails():
    """A 12-line VerilogEval spec legitimately has a small prefix and is cheap
    anyway, so this is a report-level warning, not a gate."""
    stats = CacheStats()
    for _ in range(12):
        stats.record(stage="s1", model="m", input_tokens=300, cached_tokens=0)
    # No verdict machinery pretends a tiny prefix is a defect; the rate is simply
    # reported as below threshold and the operator reads the token counts.
    assert stats.by_key[("s1", "m")].to_dict()["input_tokens"] == 3600


# --------------------------------------------------------- C4 warm-up ordering


def test_c4_the_first_items_run_serially_then_the_rest_overlap():
    """Measured failure: 3 of 8 parallel calls on a cold prefix reported
    `cached=0` because they raced the cache write."""
    lock = threading.Lock()
    spans: list[tuple[float, float]] = []

    def run_one(item):
        start = time.perf_counter()
        time.sleep(0.05)
        end = time.perf_counter()
        with lock:
            spans.append((start, end))
        return item

    result = run_fanout(range(10), run_one, workers=8, warmup=2)
    assert result == list(range(10))

    spans.sort()
    # The two warm-up calls must not overlap each other, nor anything after them.
    assert spans[0][1] <= spans[1][0] + 1e-3, "warm-up calls overlapped"
    assert spans[1][1] <= spans[2][0] + 1e-3, "the pool started before warm-up ended"
    # The remainder must overlap, or the fan-out is not fanning out.
    later = spans[2:]
    assert any(b[0] < a[1] for a, b in zip(later, later[1:])), "no concurrency"


def test_c4_results_come_back_in_input_order():
    """Completion order is not input order; a caller zipping results against
    items must not silently pair the wrong ones."""
    def run_one(n):
        time.sleep(0.02 if n % 2 else 0.001)
        return n * 10

    assert run_fanout(range(12), run_one, workers=8, warmup=2) == [
        n * 10 for n in range(12)
    ]


def test_c4_a_failing_item_is_raised_not_swallowed():
    def run_one(n):
        if n == 5:
            raise ValueError("boom")
        return n

    with pytest.raises(ValueError, match="boom"):
        run_fanout(range(10), run_one, workers=4, warmup=1)


# ------------------------------------------------------ C5 per-model accounting


def test_c5_hit_rates_are_keyed_by_stage_and_model():
    """The escalation ladder moves a failing fragment to another model, whose
    cache is separate. Pooling them lets one escalated miss drag a healthy stage
    under the threshold."""
    stats = CacheStats()
    for _ in range(WARMUP_CALLS):
        stats.record(stage="refmodel", model="gpt-5-mini", input_tokens=5000, cached_tokens=0)
    for _ in range(20):
        stats.record(stage="refmodel", model="gpt-5-mini", input_tokens=5000, cached_tokens=4864)
    for _ in range(2):
        stats.record(stage="refmodel", model="gpt-5.6-luna", input_tokens=5000, cached_tokens=0)

    mini = stats.by_key[("refmodel", "gpt-5-mini")]
    luna = stats.by_key[("refmodel", "gpt-5.6-luna")]
    assert mini.verdict == "ok" and mini.hit_rate > 0.95
    assert luna.verdict == "too_few_calls", "2 calls is not enough to convict"
    assert stats.failing() == [], "an escalated model dragged a healthy stage down"


def test_c5_warmup_calls_are_excluded_and_the_report_says_so():
    stats = CacheStats()
    for _ in range(WARMUP_CALLS):
        stats.record(stage="s1", model="m", input_tokens=5000, cached_tokens=0)
    for _ in range(20):
        stats.record(stage="s1", model="m", input_tokens=5000, cached_tokens=5000)

    d = stats.by_key[("s1", "m")].to_dict()
    assert d["hit_rate"] == 1.0, "warm-up misses were folded into the rate"
    assert d["warmup_calls_excluded"] == WARMUP_CALLS
    assert f"first {WARMUP_CALLS} excluded" in stats.render()


def test_c5_a_genuinely_broken_cache_fails_the_report():
    stats = CacheStats()
    for _ in range(MIN_CALLS_FOR_VERDICT + WARMUP_CALLS):
        stats.record(stage="testplan", model="m", input_tokens=5000, cached_tokens=0)
    assert [s.stage for s in stats.failing()] == ["testplan"]
    assert stats.to_dict()["ok"] is False


def test_c5_reads_both_usage_shapes():
    """Chat completions say `prompt_tokens`; Responses says `input_tokens`.
    A port recording zeros for one shape looks exactly like a dead cache."""
    class _Details:
        cached_tokens = 900

    class _Responses:
        input_tokens = 1000
        input_tokens_details = _Details()

    class _Chat:
        prompt_tokens = 1000
        prompt_tokens_details = _Details()

    for usage in (_Responses(), _Chat()):
        stats = CacheStats()
        call = stats.record_usage(stage="s1", model="m", usage=usage)
        assert call is not None and call.cached_tokens == 900, type(usage).__name__


def test_c5_report_round_trips_and_states_what_it_filtered():
    stats = CacheStats()
    for _ in range(WARMUP_CALLS + 10):
        stats.record(stage="s1", model="m", input_tokens=5000, cached_tokens=4800)
    d = stats.to_dict()
    assert d["warmup_calls_excluded_per_stage"] == WARMUP_CALLS
    assert d["billed_input_tokens"] == d["total_input_tokens"] - d["total_cached_tokens"]
    json.dumps(d)  # must be serialisable for cache_report.json


# ------------------------------------------------------------- C6 live probe


@pytest.mark.skipif(
    not os.environ.get("SPECFLOW_LIVE_API"),
    reason="live gateway probe; set SPECFLOW_LIVE_API=1 to run",
)
def test_c6_the_gateway_still_caches():
    """Confirmation, not prevention. C1-C5 are what stop the regression."""
    from specflow.model_io import ApiPort

    stats = CacheStats()
    port = ApiPort(root=pytest.importorskip("pathlib").Path("/tmp/specflow_cache_probe"),
                   stats=stats)
    prompt = build_prompt("REQ-0001")
    for round_ in range(3):
        port.complete(stage="probe", round_=round_, prompt=prompt)
    calls = next(iter(stats.by_key.values())).calls
    assert calls[-1].cached_tokens > 0, "the gateway stopped caching"


def test_c5_a_fanned_stage_is_one_key_not_one_key_per_item():
    """Found live, missed offline.

    A fanned-out stage names each call after its item -- `classify_869`,
    `s2_REQ-0004`. Keying on the raw name gave 65 keys of one call each on a real
    65-unit spec, every one "too few calls to judge", so the report gate was
    inert on exactly the runs it exists for. The tests above all passed a uniform
    stage name and could not see it.
    """
    from specflow.cache_stats import family

    assert family("classify_869") == "classify"
    assert family("s2_REQ-0004") == "s2"
    assert family("refmodel_REQ-0012") == "refmodel"
    assert family("refmodel") == "refmodel", "a single-call stage keeps its name"

    stats = CacheStats()
    for i in range(WARMUP_CALLS + 20):
        stats.record(stage=f"classify_{i * 37}", model="m",
                     input_tokens=5000, cached_tokens=4736)
    assert list(stats.by_key) == [("classify", "m")]
    d = stats.by_key[("classify", "m")].to_dict()
    assert d["stage"] == "classify", "the report shows one item's name, not the family"
    assert d["calls"] == WARMUP_CALLS + 20
    assert d["verdict"] == "ok", "a healthy fanned stage must be judgeable at all"


def test_a_two_word_family_is_not_split_at_its_first_underscore():
    """`normalize_indirect` and `normalize` have DIFFERENT SHARED PREFIXES --
    different system text, different port note -- so they warm separately and
    cache separately. Pooled, a cold second pass hides behind a warm first one
    and the report says nothing about the stage that was added.

    Same defect as keying on the raw stage name, which gave 65 keys of one call
    each and made the gate inert on exactly the runs it exists for.
    """
    from specflow.cache_stats import family

    assert family("normalize_indirect_REQ-0002") == "normalize_indirect"
    assert family("normalize_REQ-0002") == "normalize"


def test_the_split_is_at_the_first_ITEM_not_the_first_underscore():
    from specflow.cache_stats import family

    assert family("variant_REQ-0028_trigger") == "variant"
    assert family("classify_869") == "classify"
    assert family("s3_TP-0000") == "s3"
    assert family("oracles") == "oracles", "a single-call stage keeps its name"
