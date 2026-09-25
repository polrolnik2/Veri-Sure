"""What actually goes on the wire for `/v1/responses`.

Both bugs this file pins were invisible from the outside: the code read
correctly and the request was wrong. The only way either was found was to stand
up a local server and look at the bytes, which is not something a reviewer will
do — so the body construction is a pure function now, and these are the tests.

The stake is a long reasoning request surviving at all. Without
`reasoning.summary`, the gateway sends nothing for the entire reasoning phase,
so the connection is genuinely idle and gets reaped; with it, a measured 437s
call never had a gap longer than 10.0s.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from specflow.model_io import _responses_body


@dataclass
class _Cfg:
    model: str = "gpt-5.6-luna"
    reasoning_effort: str | None = "xhigh"
    generate_kwargs: dict[str, Any] = field(default_factory=dict)


def test_the_keepalive_is_requested():
    body = _responses_body(_Cfg(), "p")
    assert body["reasoning"] == {"effort": "xhigh", "summary": "auto"}


def test_extra_body_merges_into_reasoning_instead_of_replacing_it():
    """The footgun. A shallow `update` drops `summary` and nothing reports it.

    This container is launched with exactly this value in `OPENAI_EXTRA_BODY`.
    It is harmless today only because `.env.local` clears the key — an operator
    who set it themselves would silently lose the keepalive.
    """
    cfg = _Cfg(generate_kwargs={"extra_body": {"reasoning": {"effort": "high"}}})
    body = _responses_body(cfg, "p")
    assert body["reasoning"] == {"effort": "high", "summary": "auto"}


def test_summary_cannot_be_lost_even_if_extra_body_names_it_away():
    cfg = _Cfg(generate_kwargs={"extra_body": {"reasoning": {"summary": None}}})
    assert _responses_body(cfg, "p")["reasoning"]["summary"] is None, (
        "an explicit choice is honoured -- only ABSENCE is defaulted"
    )


def test_non_reasoning_extra_body_keys_still_pass_through():
    cfg = _Cfg(generate_kwargs={"extra_body": {"service_tier": "flex"}})
    body = _responses_body(cfg, "p")
    assert body["service_tier"] == "flex"
    assert body["reasoning"]["summary"] == "auto"


def test_the_chat_spelling_of_the_cap_is_translated_not_dropped():
    """`max_completion_tokens` is the chat name; Responses wants
    `max_output_tokens`. Carrying it over unchanged leaves the request UNCAPPED,
    and an uncapped reasoning request is the one that spends its whole budget
    before emitting any content."""
    cfg = _Cfg(generate_kwargs={"max_completion_tokens": 12345})
    body = _responses_body(cfg, "p")
    assert body["max_output_tokens"] == 12345
    assert "max_completion_tokens" not in body


def test_there_is_always_a_cap():
    """An uncapped reasoning request is the one that spends its whole budget
    before emitting any content, so the cap is a parameter with a default rather
    than something to remember to pass."""
    assert _responses_body(_Cfg(), "p")["max_output_tokens"] == 48000
    assert _responses_body(_Cfg(), "p", 9000)["max_output_tokens"] == 9000


# ------------------------------------------ developer_role_prefix (the fix)
def test_developer_role_prefix_is_ON_BY_DEFAULT():
    """Flipped on the run-scale measurement the old default was waiting for.

    h3-i2c's oracle stage ran 149 real calls at fan-out concurrency with the
    switch off and cached 1.3% of 2,058,353 input tokens -- while carrying a
    ~13k-token identical prefix, 93% of each prompt. Five stages on gpt-5-mini
    in the same run cached 61-83% with a SMALLER shared head. Off is the
    expensive setting; see `PortSettings.developer_role_prefix`.
    """
    from specflow.fanout import PREFIX_SENTINEL

    prompt = f"shared stuff{PREFIX_SENTINEL}\n\nitem text"
    assert _responses_body(_Cfg(), prompt)["input"] == [
        {"role": "developer", "content": f"shared stuff{PREFIX_SENTINEL}"},
        {"role": "user", "content": "item text"},
    ]


def test_developer_role_prefix_can_still_be_turned_OFF():
    """The flat shape stays reachable, so the 1.3%-vs-99.6% comparison can be
    re-run rather than taken on faith."""
    from specflow.fanout import PREFIX_SENTINEL

    prompt = f"shared stuff{PREFIX_SENTINEL}\n\nitem text"
    assert _responses_body(_Cfg(), prompt,
                           developer_role_prefix=False)["input"] == prompt


def test_developer_role_prefix_splits_at_the_sentinel_when_on():
    """THE FIX. See `PortSettings.developer_role_prefix` for the measurement:
    this exact split reads 99.6% cached on gpt-5.6-luna where one flat `user`
    string reads 0%, isolated against streaming, `include`, and structure
    alone (a single-item list also read 0%)."""
    from specflow.fanout import PREFIX_SENTINEL

    prompt = f"shared stuff{PREFIX_SENTINEL}\n\nitem text"
    body = _responses_body(_Cfg(), prompt, developer_role_prefix=True)
    assert body["input"] == [
        {"role": "developer", "content": f"shared stuff{PREFIX_SENTINEL}"},
        {"role": "user", "content": "item text"},
    ]


def test_developer_role_prefix_is_a_noop_with_no_shared_block():
    """A whole-artifact stage (refmodel, witness) has no `shared_block`
    sentinel at all -- turning the switch on for it must not invent a split
    that was never there, or misparse ordinary prompt text as a boundary."""
    body = _responses_body(_Cfg(), "just a plain prompt, no sentinel",
                           developer_role_prefix=True)
    assert body["input"] == "just a plain prompt, no sentinel"


def test_the_body_default_and_PortSettings_CANNOT_DRIFT():
    """One decision, one place.

    `_responses_body` carried its own bare `False` while `PortSettings` also
    said `False`, so the duplication was invisible -- until the dataclass
    flipped to True and the function default did not, and a direct call
    silently kept sending the flat shape that measured 1.3%. Production was
    never wrong (ApiPort passes `self.settings.developer_role_prefix`), which
    is exactly what makes this the kind of drift a test has to hold.
    """
    import inspect

    from specflow.model_io import PortSettings, _responses_body

    got = inspect.signature(_responses_body).parameters[
        "developer_role_prefix"].default
    assert got is PortSettings.developer_role_prefix, (
        "the body default must come FROM PortSettings, not from a second "
        f"literal (signature says {got!r}, PortSettings says "
        f"{PortSettings.developer_role_prefix!r})"
    )
