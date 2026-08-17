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
* `ApiPort`   -- the eventual HTTP path, wrapping `eda_agent.model`.

The side effect matters more than the workaround: every emit/ingest pair is a
recorded fixture, so a stage driven once by hand replays forever. Given that
`tests/` held a single file before this work, that is the regression net.
"""

from __future__ import annotations

import json
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


@dataclass
class ApiPort:
    """The eventual HTTP path. Deliberately unimplemented rather than stubbed
    with a fake: a silent stub would let a milestone appear to pass without a
    model having been consulted."""

    root: Path
    model: object | None = None

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        raise NotImplementedError(
            "ApiPort is not wired yet; use --model-port file or replay"
        )


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
