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


def test_there_is_always_a_cap(monkeypatch):
    monkeypatch.delenv("SPECFLOW_MAX_OUTPUT_TOKENS", raising=False)
    assert _responses_body(_Cfg(), "p")["max_output_tokens"] == 48000
    monkeypatch.setenv("SPECFLOW_MAX_OUTPUT_TOKENS", "9000")
    assert _responses_body(_Cfg(), "p")["max_output_tokens"] == 9000
