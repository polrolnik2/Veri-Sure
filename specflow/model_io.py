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
import time
from dataclasses import dataclass, field, replace
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


@dataclass(frozen=True)
class PortSettings:
    """Every runtime switch the model path has, in one explicit object.

    Passed in, never read from the environment at call time. That is not a style
    preference -- it is the fix for a class of failure this code kept producing.
    `load_env_file` values OVERRIDE `os.environ` on purpose, so a rotated key can
    reach a session already running; the consequence is that any knob also read
    from the environment is decided by whichever file the *callee* happens to
    load, not by what the caller asked for. Measured: a benchmark run launched
    with `--env-file env.high` did its reference-model generation at `xhigh`,
    because every stage re-read `.env.local` behind the caller's back. A switch
    that a caller sets and a callee silently overrides is worse than no switch.

    Credentials stay in the env file deliberately. A key or base URL is not a
    runtime choice, and the file is the one channel a live process can re-read
    when one rotates.
    """

    #: Whole-artifact model and effort. `None` defers to the resolved config.
    model: str | None = None
    effort: str | None = None
    api_flavor: str | None = None
    stream: bool | None = None

    #: The narrow, fanned-out stages run a small model on a narrow task.
    #: `full_strength_stages` names the ones that must NOT be downgraded --
    #: the reference model above all, since every check in the suite compares
    #: the design against it.
    small_model: str | None = None
    small_effort: str | None = None
    full_strength_stages: frozenset[str] = frozenset({"refmodel"})

    #: Total output budget for one stage call, and the per-continuation slice of
    #: it. The slice exists because a single long call goes silent long enough
    #: to be reaped; see `_complete_responses`.
    max_output_tokens: int = 48000
    responses_chunk: int = 9000

    #: Retries for a DROPPED stream. Distinct from `max_retries`, which the SDK
    #: applies before a response starts.
    stream_retries: int = 2

    #: 2, not the SDK's 8. A request this gateway structurally cannot complete
    #: costs `max_retries` x ~300s of silence, and eight of those is ~40 minutes
    #: with nothing written -- the incident that first made this configurable.
    #: It used to be recoverable only by putting `OPENAI_MAX_RETRIES` in the env
    #: file, which is exactly the ambient-knob pattern this class removes, so the
    #: lesson lives in the default instead. Genuine rate limits still get two.
    max_retries: int = 2
    timeout_s: float = 600.0

    def for_stage(self, stage: str | None) -> tuple[str | None, str | None]:
        """`(model, effort)` overrides for one stage, or `(None, None)`."""
        if stage is not None and stage in self.full_strength_stages:
            return None, None
        return self.small_model, self.small_effort


def _as_input_item(item) -> dict:
    """An output item, reshaped into something the API accepts as INPUT.

    The two are not the same schema, and the difference is not written down
    anywhere you would look for it. Feeding a reasoning item straight back
    yields `Unknown parameter: 'input[1].status'` -- `status` is emitted on
    output and rejected on input. Nulls go for the same reason: to a strict
    validator an explicit `"content": null` is not an absent key.
    """
    if hasattr(item, "model_dump"):
        data = item.model_dump(exclude_none=True)
    else:
        data = {k: v for k, v in dict(item).items() if v is not None}
    data.pop("status", None)
    return data


def _responses_body(cfg, prompt: str, default_cap: int = 48000) -> dict:
    """The request body for `/v1/responses`, built where it can be tested.

    Pure on purpose: the two bugs this had were both invisible from the outside
    -- the request looked fine in the code and wrong on the wire -- so the thing
    that needs a test is the body itself, not the call around it.
    """
    body: dict = {
        "model": cfg.model,
        "input": prompt,
        "reasoning": {"effort": cfg.reasoning_effort or "medium", "summary": "auto"},
    }
    gen = dict(cfg.generate_kwargs or {})
    # `max_completion_tokens` is the chat spelling; Responses calls it
    # `max_output_tokens`. Carrying the chat name over silently drops the cap,
    # and an uncapped reasoning request is exactly the one that runs out of
    # budget with no content to show for it.
    cap = (gen.pop("max_completion_tokens", None)
           or gen.pop("max_output_tokens", None)
           or default_cap)
    body["max_output_tokens"] = int(cap)

    # DEEP merge, because a shallow one silently destroys the keepalive.
    # `body.update({"reasoning": {"effort": "xhigh"}})` REPLACES the whole
    # reasoning dict, dropping `summary` -- and with no summary the gateway
    # sends nothing for the entire reasoning phase, so the connection really is
    # idle. This container is launched with exactly that value in
    # `OPENAI_EXTRA_BODY`, and it is only harmless because `.env.local` clears
    # the key; an operator who set it themselves would lose the keepalive with
    # no signal at all.
    for key, value in (gen.get("extra_body") or {}).items():
        if isinstance(value, dict) and isinstance(body.get(key), dict):
            body[key] = {**body[key], **value}
        else:
            body[key] = value
    if isinstance(body.get("reasoning"), dict):
        body["reasoning"].setdefault("summary", "auto")
    return body


#: Exceptions that will fail identically however many times we resend.
#:
#: Everything else is retried. That asymmetry is deliberate: a wrong guess in
#: this direction costs one wasted resend, and a wrong guess the other way
#: throws away a whole generation -- an i2c reference model at `xhigh` is ~30
#: minutes of work, and one was lost to a gateway 500 whose own message said
#: "You can retry your request".
_PERMANENT = frozenset({
    "BadRequestError",           # 400 -- the body is malformed; it still will be
    "AuthenticationError",       # 401
    "PermissionDeniedError",     # 403
    "NotFoundError",             # 404 -- wrong route, or a model this gateway
                                 # cannot resolve
    "UnprocessableEntityError",  # 422
    "TypeError", "KeyError", "IndexError",  # an event shape the SDK cannot parse
})

#: Error `code`/`type` values that stay permanent inside a 500-shaped reply.
_PERMANENT_CODES = frozenset({
    "content_filter", "invalid_request_error", "context_length_exceeded",
    "invalid_prompt", "model_not_found", "string_above_max_length",
})


def _retryable(exc: BaseException) -> bool:
    """Should this failure be resent?

    The exception's type alone is not enough to decide. When an SSE stream
    carries an error event the SDK raises a **bare `APIError`** -- not an
    `APIStatusError`, so there is no `status_code` to read -- and that is
    exactly how this gateway reports a transient server-side 500 in the middle
    of a long generation. Classifying by name filed it with the permanent
    failures, so a 500 that explicitly invited a retry killed a 30-minute
    reference-model generation on its second continuation chunk instead.

    Permanent by name, permanent by error code in the body, retryable
    otherwise -- deliberately biased towards retrying, because the two mistakes
    do not cost the same.
    """
    if type(exc).__name__ in _PERMANENT:
        return False
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        for key in ("code", "type"):
            value = body.get(key)
            if isinstance(value, str) and value in _PERMANENT_CODES:
                return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 409, 429):
        return False
    return True


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
    #: Overrides `OPENAI_MODEL` for this port only. The fanned-out stages run a
    #: small model on a narrow task -- measured, `gpt-5-mini` at `low` effort
    #: answers a one-requirement prompt in 9s median with 4/4 structurally valid
    #: output -- while the whole-artifact stages keep the configured one. Named
    #: `SPECFLOW_SMALL_MODEL` in the environment.
    model_override: str | None = None
    #: Reasoning effort for this port only, same reasoning.
    effort_override: str | None = None
    #: Every runtime switch, supplied by the caller. Defaults are the dataclass
    #: defaults -- NOT the environment, which is what let a caller's `--env-file`
    #: be silently overridden by whichever file a stage happened to re-read.
    settings: PortSettings = field(default_factory=PortSettings)
    #: Stages the override must NOT touch. The docstring above has always said
    #: "the whole-artifact stages keep the configured one", and the code did not
    #: do it: `make_port` attaches the override to the single port the whole run
    #: shares, so `SPECFLOW_SMALL_MODEL` silently captured EVERY stage.
    #:
    #: Measured on a live `alu` run: the operator had configured
    #: `gpt-5.6-luna` at `xhigh`, and every artifact in the run -- including the
    #: reference model -- was written by `gpt-5-mini` at `low`. Nothing reported
    #: it; the artifacts looked plausible and the node accepted. The reference
    #: model is the one artifact whose correctness the whole pipeline rests on,
    #: so it is the one that must never be quietly downgraded.
    #:
    #: Kept for callers that construct an ApiPort directly; `settings` is the
    #: supported route and wins when it names anything.
    full_strength_stages: frozenset = frozenset({"refmodel"})
    #: Where prompt-cache accounting goes. Optional, because the single-call
    #: stages have nothing to cache across; supplied by every fanned-out stage,
    #: because there a silent cache loss is a ~30x cost regression that no gate,
    #: artifact or verdict would notice. See `specflow/cache_stats.py`.
    stats: object | None = None
    #: Client kwargs resolved in `config()` while `.env.local`'s overrides are
    #: applied. Defaulted here so a port whose `_config` was injected still
    #: builds a client rather than raising AttributeError.
    _client_kwargs: dict | None = None

    # ------------------------------------------------------------------ config
    def config(self, stage: str | None = None):
        """Resolve model, key, base URL and generation kwargs.

        `.env.local` (or `$SPECFLOW_ENV_FILE`) wins over the process
        environment -- see `load_env_file` for why that direction is the useful
        one. `eda_agent.config.load_openai_config` then does the rest, including
        parsing `OPENAI_EXTRA_BODY`, which is where a reasoning effort set by the
        operator lives.
        """
        # The BASE config is cached; the stage-dependent overrides are not, and
        # that separation is the whole point. Caching the fully-resolved config
        # meant the first stage to call this froze its own model choice for the
        # entire run -- `classify` runs first, so the small model captured every
        # later stage including `refmodel`, which is exactly the stage the
        # override is supposed to leave alone.
        cfg = self._config
        if cfg is None:
            cfg = self._resolve_base()
            self._config = cfg
        return self._apply_overrides(cfg, stage)

    def _apply_overrides(self, cfg, stage: str | None):
        st = self.settings
        if st.model:
            cfg = replace(cfg, model=st.model)
        if st.effort:
            cfg = replace(cfg, reasoning_effort=st.effort)
        if st.api_flavor:
            cfg = replace(cfg, api_flavor=st.api_flavor)
        if st.stream is not None:
            cfg = replace(cfg, stream=st.stream)

        small_model, small_effort = st.for_stage(stage)
        small_model = small_model or (
            None if (stage is not None and stage in self.full_strength_stages)
            else self.model_override
        )
        small_effort = small_effort or (
            None if (stage is not None and stage in self.full_strength_stages)
            else self.effort_override
        )
        if small_model:
            cfg = replace(cfg, model=small_model)
        if small_effort:
            cfg = replace(cfg, reasoning_effort=small_effort)
        return cfg

    def _resolve_base(self):
        """`.env.local` plus the process environment, without any stage override."""
        from eda_agent.config import load_openai_config

        overrides = load_env_file()
        saved = {k: os.environ.get(k) for k in overrides}
        os.environ.update(overrides)
        try:
            cfg = load_openai_config()
            # Captured INSIDE the override window. `_client()` used to read
            # these from `os.environ` after this `finally` had already put the
            # environment back, so `.env.local` could not set either one: a
            # declared `OPENAI_MAX_RETRIES=2` still built a client with 8.
            # A request that cannot survive the network path then costs eight
            # attempts, which is the ~40 minutes of silence recorded in
            # docs/specflow-migration.md as a fixed problem. It was not fixed on
            # this path -- `benchmarks/run_chipverilog.py` only appeared to fix
            # it because it updates os.environ permanently before any port is
            # built.
            self._client_kwargs = {
                "max_retries": self.settings.max_retries,
                "timeout": self.settings.timeout_s,
            }
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
        return cfg

    def _client(self):
        from openai import OpenAI

        cfg = self.config()
        kwargs: dict = {"api_key": cfg.api_key,
                        **(self._client_kwargs or {"max_retries": 8, "timeout": 600.0})}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        if cfg.organization:
            kwargs["organization"] = cfg.organization
        return OpenAI(**kwargs)

    # -------------------------------------------------------------- responses
    def _stream_chunk(self, client, call: dict):
        """One streamed chunk, resent on any failure that a resend could fix.

        Two things this gets right that the obvious version does not.

        The final response is taken from the `response.completed` /
        `response.incomplete` EVENT, not from `stream.get_final_response()`.
        That helper raises "Didn't receive a `response.completed` event" on
        anything else -- and `incomplete` is the normal path here, because
        hitting the chunk cap is exactly how a continuation is signalled. Using
        the helper alone made the chunking unable to ever take its own
        continuation branch.

        And a mid-stream failure is retried with backoff whenever a resend
        could fix it -- see `_retryable`. It is intermittent: the identical
        request and prompt completed in 120s on one attempt and dropped on
        another. Retrying is cheap precisely because the work is chunked -- one
        chunk is lost, not a whole generation -- so the thing that made chunking
        necessary also makes it affordable. The list used to be transport
        errors by name, which let a gateway 500 arriving as a bare `APIError`
        through as fatal and cost a 30-minute i2c generation at `xhigh`.
        """
        attempts = max(0, self.settings.stream_retries) + 1
        last: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                # Backoff, because the failure that makes this loop necessary is
                # usually a server-side 500 and resending it instantly tends to
                # hit the same unhealthy backend. Bounded so the retries cannot
                # themselves become the 300s idle gap this whole path exists to
                # avoid.
                time.sleep(min(30.0, 4.0 * (2 ** (attempt - 1))))
            got: list[str] = []
            final = None
            try:
                # `create(stream=True)`, NOT the `stream()` helper. The helper
                # runs an accumulator that rebuilds a response snapshot from
                # every event, and it raises on shapes this gateway actually
                # sends: `IndexError: list index out of range` from
                # `snapshot.output[event.output_index]`, which killed a live run
                # in `classify` -- a small, cheap stage that has nothing to do
                # with long generations. Raw event iteration never hit it once
                # across every probe run here, thousands of events. The
                # accumulation was never needed: the final response arrives in
                # the terminal event.
                for event in client.responses.create(**call, stream=True):
                    kind = getattr(event, "type", "")
                    if kind == "response.output_text.delta":
                        got.append(event.delta)
                    elif kind in ("response.completed", "response.incomplete",
                                  "response.failed"):
                        final = getattr(event, "response", None) or final
                return got, final
            except Exception as exc:  # noqa: BLE001
                if not _retryable(exc):
                    raise
                last = exc
        raise last  # type: ignore[misc]


    def _complete_responses(
        self, cfg, *, stage: str, round_: int, prompt: str, response_path: Path
    ) -> str:
        """`/v1/responses`, streamed, and CHUNKED so no single call goes quiet.

        The constraint, measured rather than assumed. Instrumenting a real
        refmodel request edge by edge: the stream was healthy for 328s -- 5144
        events, maximum gap between them 8.6s -- and then the model went
        **completely silent for 300.2s** and the connection was closed. It is an
        idle timeout of exactly 300s, not an elapsed-time limit, which is why
        three earlier runs died at 474s, 550s and 662s: variable time until the
        model stops emitting, plus 300.

        Streaming with `reasoning.summary` is necessary and not sufficient. It
        keeps bytes flowing while the model is summarising, and it cannot help
        through a gap the model itself creates.

        So each call is capped low enough to return long before 300s of silence,
        and continued. Continuation carries the model's OWN reasoning, not a
        summary of it: `include: ["reasoning.encrypted_content"]` returns the
        reasoning items with their full state, and feeding those items back
        verbatim resumes the model where it was. The plaintext `content` field
        comes back empty from this gateway and the summary is lossy by
        construction, so the encrypted item is the only faithful carrier.

        `store: false` keeps it stateless -- the continuation depends on what we
        send, not on what the gateway remembers, and this gateway cannot even
        retrieve a stored response (`GET /v1/responses/{id}` 404s, it has no
        model to route on).

        Measured on a real refmodel prompt at `xhigh`: round 0 returned
        `incomplete` at 119s having spent all 9000 tokens on reasoning and
        emitted no content at all; round 1 completed at 105s with the whole
        model. 223s total, maximum gap under 10s, effort never lowered.
        """
        effort = cfg.reasoning_effort or "medium"
        body = _responses_body(cfg, prompt, self.settings.max_output_tokens)
        total = int(body.pop("max_output_tokens"))
        chunk = int(self.settings.responses_chunk)
        body["include"] = ["reasoning.encrypted_content"]
        body["store"] = False
        body["max_output_tokens"] = min(chunk, total)

        client = self._client()
        conversation: list = [{"role": "user", "content": prompt}]
        parts: list[str] = []
        final = None
        spent = 0
        rounds = max(1, -(-total // max(1, chunk)))

        for attempt in range(rounds):
            call = dict(body)
            call["input"] = conversation
            got: list[str] = []
            try:
                got, final = self._stream_chunk(client, call)
            except Exception as exc:  # noqa: BLE001
                # Distinct failures used to read identically here, and this
                # message is the only record of which one ended the run -- the
                # exception has already been retried to exhaustion by
                # `_stream_chunk` before it reaches this point.
                #
                # The earlier version had two buckets and put everything that
                # was not a named transport error into "the SDK could not parse
                # an event", which is how a gateway 500 came to be reported as
                # an SDK parse bug. Three buckets, and the middle one is the one
                # that was missing.
                name = type(exc).__name__
                if name in ("RemoteProtocolError", "ReadTimeout", "ConnectError",
                            "ReadError", "APIConnectionError", "APITimeoutError"):
                    what = "the connection dropped mid-stream"
                elif name in ("TypeError", "KeyError", "IndexError"):
                    what = "the SDK could not parse an event the gateway sent"
                else:
                    what = "the gateway failed the request"
                raise RuntimeError(
                    f"{stage} r{round_}: /v1/responses -- {what} "
                    f"({type(exc).__name__}: {exc}). Effort={effort!r}, "
                    f"{len(prompt)} bytes of prompt, chunk={call['max_output_tokens']}, "
                    f"continuation {attempt + 1}/{rounds}, "
                    f"{len(''.join(parts + got))} chars so far."
                ) from exc

            parts.extend(got)
            usage = getattr(final, "usage", None)
            spent += int(getattr(usage, "output_tokens", 0) or 0)
            if getattr(final, "status", None) != "incomplete":
                break
            reason = getattr(getattr(final, "incomplete_details", None), "reason", None)
            if reason != "max_output_tokens":
                break
            # Feed the model's own reasoning items back, verbatim. Anything less
            # -- a summary, or a bare "carry on" -- restarts the reasoning.
            conversation = conversation + [
                _as_input_item(item)
                for item in (getattr(final, "output", None) or [])
            ] + [{"role": "user",
                  "content": "Continue from exactly where you stopped. Do not "
                             "repeat anything you have already produced."}]
            body["max_output_tokens"] = min(chunk, max(chunk, total - spent))

        text = "".join(parts).strip() or (getattr(final, "output_text", "") or "").strip()
        if not text:
            reason = getattr(getattr(final, "incomplete_details", None), "reason", None)
            raise RuntimeError(
                f"{stage} r{round_}: model returned no content after {rounds} "
                f"continuation(s) (status={getattr(final, 'status', None)!r}, "
                f"incomplete={reason!r}, {spent} output tokens spent). At "
                f"effort={effort!r} the reasoning budget can consume every chunk; "
                f"raise SPECFLOW_MAX_OUTPUT_TOKENS or SPECFLOW_RESPONSES_CHUNK."
            )

        response_path.write_text(text, encoding="utf-8")
        usage = getattr(final, "usage", None)
        if self.stats is not None:
            self.stats.record_usage(
                stage=stage,
                model=str(getattr(final, "model", None) or cfg.model),
                usage=usage,
            )
        record_fixture(
            Path(self.root), stage, round_,
            {
                "port": "api",
                "surface": "responses",
                "requested_model": cfg.model,
                "served_model": getattr(final, "model", None),
                "generate_kwargs": {k: v for k, v in body.items() if k != "input"},
                "continuations": len(parts) and rounds,
                "output_tokens_total": spent,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
            },
        )
        return text

    def _chat_call(self, cfg, kwargs: dict, prompt: str):
        """`/chat/completions`, resent on a failure a resend could fix.

        The streamed branch used to iterate the response OUTSIDE any try/except,
        so a mid-stream error -- which the SDK raises as a bare `APIError` when
        the SSE carries an error event -- propagated raw and unretried. That is
        the identical defect that cost a 30-minute reference-model generation on
        the `/v1/responses` path; this path is the DEFAULT flavour, so it had
        the same hole in the more travelled road.

        Unlike the responses path there is nothing partial worth keeping: the
        text is only meaningful once the stream ends, so a retry re-issues the
        whole call. Returns `(response, text)` because the streamed branch has
        to reassemble before it can produce either.
        """
        attempts = max(0, self.settings.stream_retries) + 1
        last: Exception | None = None
        for attempt in range(attempts):
            if attempt:
                time.sleep(min(30.0, 4.0 * (2 ** (attempt - 1))))
            try:
                response = self._client().chat.completions.create(
                    model=cfg.model,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs,
                )
                if not cfg.stream:
                    return response, (response.choices[0].message.content or "").strip()
                # Reassemble, and keep the usage record: it arrives in a final
                # chunk that carries no choices, which is why `include_usage` is
                # set by the caller. Without it an API run would record a
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
                return _StreamedResponse(text, usage_obj, finish, cfg.model), text
            except Exception as exc:  # noqa: BLE001
                if not _retryable(exc):
                    raise
                last = exc
        raise last  # type: ignore[misc]

    # ------------------------------------------------------------------- call
    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        cfg = self.config(stage)
        prompt_path, response_path = _paths(Path(self.root), stage, round_)
        prompt_path.write_text(prompt, encoding="utf-8")

        if str(getattr(cfg, "api_flavor", "chat")).lower() == "responses":
            return self._complete_responses(
                cfg, stage=stage, round_=round_, prompt=prompt,
                response_path=response_path)

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
            response, text = self._chat_call(cfg, kwargs, prompt)
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
            if type(exc).__name__ == "NotFoundError":
                # A 404 from a gateway has two causes and they read identically
                # in the SDK's message, so both are named. Measured here: an
                # `OPENAI_BASE_URL` with no path component made every call land
                # on `/chat/completions` and 404, when the gateway serves at
                # `/v1`; and separately, the configured model had been withdrawn
                # from the gateway while the URL was fine. A run dies the same
                # way either time, and the difference is one `curl` nobody
                # thinks to make.
                from urllib.parse import urlparse

                base = cfg.base_url or ""
                hint = ""
                if base and not urlparse(base).path.strip("/"):
                    hint = (f" The base URL {base!r} has no path: most "
                            f"OpenAI-compatible gateways serve at <base>/v1, so "
                            f"this request went to /chat/completions.")
                raise RuntimeError(
                    f"{stage} r{round_}: the gateway returned 404. Either the "
                    f"model {cfg.model!r} is not available on it, or the base "
                    f"URL is wrong.{hint} `curl -H \"Authorization: Bearer "
                    f"$OPENAI_API_KEY\" {base.rstrip('/')}/v1/models` lists what "
                    f"the gateway actually serves."
                ) from exc
            raise

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


def make_port(kind: str, root: Path, stats: object | None = None,
              settings: PortSettings | None = None) -> ModelPort:
    """`stats` is only meaningful for the API path -- the file and replay ports
    make no requests, so there is no cache to account for.

    Keyword-optional rather than required so a caller that substitutes this
    function (tests do) is not broken by the addition.
    """
    kinds = {"file": FilePort, "replay": ReplayPort, "api": ApiPort}
    if kind not in kinds:
        raise ValueError(f"unknown model port {kind!r}; expected one of {sorted(kinds)}")
    if kind == "api":
        st = settings or PortSettings()
        return ApiPort(
            root=Path(root),
            stats=stats,
            settings=st,
            full_strength_stages=st.full_strength_stages,
        )
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
