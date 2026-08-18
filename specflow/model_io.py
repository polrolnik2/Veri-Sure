"""How a stage reaches a model.

Each specflow stage is a script wrapped around exactly one agent call -- the only
non-deterministic step -- so that call can be split into *emit* and *ingest*
phases with no async blocking. Three ports implement the same interface:

* `FilePort`  -- writes the prompt to disk and stops; a separate ingest run reads
  the response. Used while no API key exists, with a Claude subagent serving the
  call by hand.
* `ReplayPort` -- reads a recorded response. No model, no I/O, fully
  deterministic. This is what makes M5-M9 developable and CI-testable without a
  model in the loop at all.
* `ApiPort`   -- the HTTP path, resolving credentials through
  `eda_agent.config` and recording every exchange as a replayable fixture.

The side effect matters more than the workaround: every emit/ingest pair is a
recorded fixture, so a stage driven once by hand replays forever. Given that
`tests/` held a single file before this work, that is the regression net.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class PendingResponse(Exception):
    """Raised by `FilePort` when the prompt has been emitted but no response
    exists yet. The CLI turns this into a clean exit, not a traceback: it is the
    expected outcome of `--emit`, not a failure."""

    def __init__(self, prompt_path: Path, response_path: Path):
        self.prompt_path = prompt_path
        self.response_path = response_path
        super().__init__(
            f"prompt written to {prompt_path}\n"
            f"write the model's reply to {response_path}, then re-run with --ingest"
        )


class ModelPort(Protocol):
    def complete(self, *, stage: str, round_: int, prompt: str) -> str: ...


def _paths(root: Path, stage: str, round_: int) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    return (
        root / f"{stage}_r{round_}_prompt.txt",
        root / f"{stage}_r{round_}_response.txt",
    )


@dataclass
class FilePort:
    """Emit the prompt, stop; ingest the response on the next invocation."""

    root: Path

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        prompt_path, response_path = _paths(Path(self.root), stage, round_)
        # Always rewrite the prompt: a repair round composes a new one from the
        # gate's issues, and a stale prompt beside a fresh response is the kind
        # of mismatch that is invisible until the artifacts disagree.
        prompt_path.write_text(prompt, encoding="utf-8")
        if not response_path.exists():
            raise PendingResponse(prompt_path, response_path)
        return response_path.read_text(encoding="utf-8")


@dataclass
class ReplayPort:
    """Read a recorded response. Never writes, never calls anything."""

    root: Path

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        _, response_path = _paths(Path(self.root), stage, round_)
        if not response_path.exists():
            raise FileNotFoundError(
                f"no recorded response at {response_path}; "
                f"drive this stage with --model-port file first"
            )
        return response_path.read_text(encoding="utf-8")


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Read `KEY=value` lines from a credentials file, if one exists.

    This exists because a container's environment is a snapshot taken when the
    process started: rotating a key in the environment's settings does not reach
    a session already running, and nothing the session can execute re-reads it.
    A file is the one channel that a live process *can* re-read, so values found
    here **override** the process environment rather than filling in behind it --
    the stale value is precisely what is in `os.environ`.

    Deliberately not a dotenv dependency: two rules (`#` comments, one
    `KEY=value` per line) are the whole format, and a credential loader is not
    somewhere to add a package.
    """
    if path is None:
        path = Path(os.environ.get("SPECFLOW_ENV_FILE") or ".env.local")
    path = Path(path)
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip one matched pair of surrounding quotes; a key pasted with them
        # otherwise authenticates as a different string than it looks like.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


@dataclass
class _StreamedResponse:
    """Enough of a completion object for the recording path to be shared.

    Reassembling into the same shape keeps one code path for the empty-content
    guard and the fixture record, rather than forking them by transport.
    """

    text: str
    usage: object | None
    finish_reason: str | None
    model: str

    @property
    def choices(self):
        message = type("_M", (), {"content": self.text})()
        return [type("_C", (), {"message": message,
                                "finish_reason": self.finish_reason})()]


@dataclass
class ApiPort:
    """The HTTP path: one blocking chat completion per stage round.

    Synchronous on purpose. Every specflow stage is a script around exactly one
    model call, so there is nothing to overlap, and a sync port keeps `run_stage`
    free of an event loop it would otherwise have to own.

    It also **records what it sends and receives** into the same layout
    `FilePort` and `ReplayPort` use. That is not incidental: one paid run becomes
    a `--model-port replay` fixture that reproduces for free forever, which is
    what lets an API-driven result be re-checked without re-buying it.
    """

    root: Path
    model: object | None = None
    _config: object | None = None
    #: Where prompt-cache accounting goes. Optional, because the single-call
    #: stages have nothing to cache across; supplied by every fanned-out stage,
    #: because there a silent cache loss is a ~30x cost regression that no gate,
    #: artifact or verdict would notice. See `specflow/cache_stats.py`.
    stats: object | None = None

    # ------------------------------------------------------------------ config
    def config(self):
        """Resolve model, key, base URL and generation kwargs.

        `.env.local` (or `$SPECFLOW_ENV_FILE`) wins over the process
        environment -- see `load_env_file` for why that direction is the useful
        one. `eda_agent.config.load_openai_config` then does the rest, including
        parsing `OPENAI_EXTRA_BODY`, which is where a reasoning effort set by the
        operator lives.
        """
        if self._config is not None:
            return self._config

        from eda_agent.config import load_openai_config

        overrides = load_env_file()
        saved = {k: os.environ.get(k) for k in overrides}
        os.environ.update(overrides)
        try:
            cfg = load_openai_config()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        if not cfg.api_key:
            raise RuntimeError(
                "no API key: set OPENAI_API_KEY, or write it to .env.local "
                "(a running session cannot re-read its own environment)"
            )
        self._config = cfg
        return cfg

    def _client(self):
        from openai import OpenAI

        cfg = self.config()
        kwargs: dict = {
            "api_key": cfg.api_key,
            "max_retries": int(os.environ.get("OPENAI_MAX_RETRIES", "8")),
            "timeout": float(os.environ.get("OPENAI_TIMEOUT_S", "600")),
        }
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        if cfg.organization:
            kwargs["organization"] = cfg.organization
        return OpenAI(**kwargs)

    # ------------------------------------------------------------------- call
    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        cfg = self.config()
        prompt_path, response_path = _paths(Path(self.root), stage, round_)
        prompt_path.write_text(prompt, encoding="utf-8")

        kwargs: dict = dict(cfg.generate_kwargs or {})
        if cfg.reasoning_effort:
            kwargs["reasoning_effort"] = cfg.reasoning_effort

        if cfg.stream:
            # Streaming is not about latency here. A non-streaming reasoning
            # request sends nothing until generation completes, so to any
            # intermediary a long one looks idle -- and this gateway cuts such a
            # request at ~300s regardless of the client timeout. Streaming keeps
            # bytes flowing, which is what lets a generation outlast the
            # ceiling. Whether it does is a property of the gateway, so
            # `--stream` is offered rather than assumed.
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

        try:
            response = self._client().chat.completions.create(
                model=cfg.model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            # A generation longer than the network path will tolerate dies as a
            # bare connection error, which reads like a flaky link and is not.
            # Measured on this gateway: a 37.9KB S1 prompt at xhigh is cut at
            # ~301s even with a 2400s client timeout, so the ceiling is upstream
            # and cannot be raised from here.
            #
            # This is silent by default and therefore expensive: the SDK retries
            # connection errors, so a call that structurally cannot fit burns
            # `max_retries` x ~300s writing nothing, because those retries are
            # logged at DEBUG. Naming the ceiling turns 40 wasted minutes into
            # one actionable message.
            if type(exc).__name__ in ("APIConnectionError", "APITimeoutError"):
                raise RuntimeError(
                    f"{stage} r{round_}: the request did not survive the network "
                    f"path ({type(exc).__name__}). A {len(prompt)}-byte prompt at "
                    f"effort={cfg.reasoning_effort!r} generates for longer than "
                    f"the ~300s ceiling this gateway enforces. Lower the effort, "
                    f"lower max_completion_tokens, or split the stage -- raising "
                    f"the client timeout does not help, the cut is upstream."
                ) from exc
            raise
        if cfg.stream:
            # Reassemble the response, and keep the usage record: it arrives in
            # a final chunk that carries no choices, which is why
            # `include_usage` is set above. Without it an API run would record a
            # fixture with no cost attached.
            parts: list[str] = []
            usage_obj = None
            finish = None
            for chunk in response:
                usage_obj = getattr(chunk, "usage", None) or usage_obj
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta is not None and getattr(delta, "content", None):
                        parts.append(delta.content)
                    finish = getattr(choice, "finish_reason", None) or finish
            text = "".join(parts).strip()
            response = _StreamedResponse(text, usage_obj, finish, cfg.model)
        else:
            text = (response.choices[0].message.content or "").strip()

        # An empty completion is its own failure and must not reach the parser.
        # A reasoning model that spends its whole token budget before emitting
        # any content returns exactly this, and the resulting gate report would
        # otherwise blame the decomposition for a budget problem.
        if not text:
            finish = getattr(response.choices[0], "finish_reason", None)
            raise RuntimeError(
                f"{stage} r{round_}: model returned no content "
                f"(finish_reason={finish!r}); raise max_tokens or lower the "
                f"reasoning effort"
            )

        response_path.write_text(text, encoding="utf-8")
        usage = getattr(response, "usage", None)
        if self.stats is not None:
            self.stats.record_usage(
                stage=stage,
                model=str(getattr(response, "model", None) or cfg.model),
                usage=usage,
            )
        record_fixture(
            Path(self.root),
            stage,
            round_,
            {
                "port": "api",
                "requested_model": cfg.model,
                "served_model": getattr(response, "model", None),
                "generate_kwargs": kwargs,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
            },
        )
        return text


def make_port(kind: str, root: Path) -> ModelPort:
    kinds = {"file": FilePort, "replay": ReplayPort, "api": ApiPort}
    if kind not in kinds:
        raise ValueError(f"unknown model port {kind!r}; expected one of {sorted(kinds)}")
    return kinds[kind](root=Path(root))  # type: ignore[abstract]


def record_fixture(root: Path, stage: str, round_: int, meta: dict) -> None:
    """Note what a recorded pair represents, so a fixture whose provenance is
    forgotten can still be judged. A Claude subagent is not the production
    model, so fixtures record *a* model's behaviour, not *the* model's."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stage}_r{round_}_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
