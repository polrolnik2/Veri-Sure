from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any


@dataclass(frozen=True)
class OpenAIConfig:
    model: str = "gpt-5.2"
    api_key: str | None = None
    base_url: str | None = None
    organization: str | None = None
    reasoning_effort: str | None = None
    stream: bool = False
    generate_kwargs: dict[str, Any] = field(default_factory=dict)


def load_openai_config(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    organization: str | None = None,
    reasoning_effort: str | None = None,
    stream: bool | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_completion_tokens: int | None = None,
    extra_body: dict[str, Any] | str | None = None,
) -> OpenAIConfig:
    env_model = os.environ.get("OPENAI_MODEL")
    env_key = os.environ.get("OPENAI_API_KEY")
    env_base_url = os.environ.get("OPENAI_BASE_URL")
    env_org = os.environ.get("OPENAI_ORGANIZATION")
    # Every other field here is env-resolvable; reasoning_effort was the one
    # that could only be set from Python, so an operator setting an effort in
    # the environment got it silently dropped. It is a named request parameter
    # rather than an extra_body key because that is the spelling the OpenAI
    # chat-completions schema defines -- the nested {"reasoning":{"effort":...}}
    # form belongs to the Responses API and is rejected as an unknown parameter.
    env_effort = os.environ.get("OPENAI_REASONING_EFFORT")
    env_extra_body = os.environ.get("OPENAI_EXTRA_BODY")

    generate_kwargs: dict[str, Any] = {}
    if temperature is not None:
        generate_kwargs["temperature"] = temperature
    if top_p is not None:
        generate_kwargs["top_p"] = top_p
    if max_completion_tokens is not None:
        generate_kwargs["max_completion_tokens"] = max_completion_tokens
    extra_body_value = extra_body if extra_body is not None else env_extra_body
    if extra_body_value is not None:
        if isinstance(extra_body_value, str):
            extra_body_value = extra_body_value.strip()
            if extra_body_value:
                try:
                    extra_body_value = json.loads(extra_body_value)
                except json.JSONDecodeError as exc:
                    raise ValueError("OPENAI_EXTRA_BODY must be valid JSON.") from exc
            else:
                extra_body_value = None
        if extra_body_value is not None and not isinstance(extra_body_value, dict):
            raise ValueError("OPENAI_EXTRA_BODY must be a JSON object.")
    if extra_body_value:
        generate_kwargs["extra_body"] = extra_body_value

    return OpenAIConfig(
        model=model or env_model or OpenAIConfig.model,
        api_key=api_key or env_key,
        base_url=base_url or env_base_url,
        organization=organization or env_org,
        reasoning_effort=reasoning_effort or env_effort,
        stream=OpenAIConfig.stream if stream is None else stream,
        generate_kwargs=generate_kwargs,
    )
