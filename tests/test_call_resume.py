"""A resumed run must not re-pay for calls it already made.

`reuse` skips a stage whose ARTIFACT is on disk. That covers S1..stimulus and
does nothing for a fan-out: variants and oracle generation write no artifact
until the whole stage completes, so a container reclaim part way through
discarded every call already paid for.

`ResumePort` exists for exactly this -- its own docstring cites the oracle
stage losing ~600 variant calls after 1h40m -- and was defined but wired to
nothing, which is what these tests pin. Measured live: two container restarts
inside forty minutes, each discarding every oracle generated since the last,
against a stage needing about seventy.

It gets its OWN switch, and hanging it on `reuse` was tried and is wrong.
`reuse` means "skip a stage whose artifact still passes its gate", which is not
the claim "the inputs have not changed". A run can carry `reuse=True` over an
artifact the gate then REJECTS -- and that stage must regenerate with a real
call, while a replayed recording would hand back the very answer that produced
the rejected artifact, so re-gating would stop meaning anything.
`test_specflow_reuse.test_a_stale_artifact_is_regenerated_not_trusted` caught
exactly that, which is why `resume_calls` is stated by the caller and inferred
from nothing.
"""

from __future__ import annotations

import inspect

from specflow import integration
from specflow.model_io import ModelPort, ResumePort, resumable


class _Counting(ModelPort):
    """Records what it was actually asked to call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.calls.append((stage, round_))
        return "fresh"


def _record(root, stage, round_, text):
    """Write a recording where `_paths` looks for one: flat, in the root.

    The layout is load-bearing rather than incidental -- the live run's
    `agent_io` holds `oracle_REQ-0003_r0_response.txt` at the top level, and a
    helper that invented a per-stage subdirectory would pass while resume found
    nothing on the artifacts that actually matter.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{stage}_r{round_}_response.txt").write_text(text, encoding="utf-8")


def test_a_recorded_response_is_REPLAYED_instead_of_re_called(tmp_path):
    inner = _Counting()
    port = resumable(inner, tmp_path)
    _record(tmp_path, "oracle_REQ-0003", 0, '{"clause": "already paid for"}')

    got = port.complete(stage="oracle_REQ-0003", round_=0, prompt="p")
    assert got == '{"clause": "already paid for"}'
    assert inner.calls == [], "a recorded response must not reach the model"

    port.complete(stage="oracle_REQ-0004", round_=0, prompt="p")
    assert inner.calls == [("oracle_REQ-0004", 0)], (
        "only the items the first attempt did not reach are re-called"
    )


def test_an_EMPTY_recording_is_a_call_that_died_and_is_re_run(tmp_path):
    """Returning "" would hand the stage a parse failure and blame the model
    for a container reclaim."""
    inner = _Counting()
    port = resumable(inner, tmp_path)
    _record(tmp_path, "oracle_REQ-0005", 0, "   \n")

    assert port.complete(stage="oracle_REQ-0005", round_=0, prompt="p") == "fresh"
    assert inner.calls == [("oracle_REQ-0005", 0)]


def test_build_artifacts_WIRES_the_resume_port():
    """Pinned by source: reproducing it needs a live run, and it cost two.

    The defect was not that `ResumePort` was wrong -- it was that nothing ever
    constructed one, so the class passed its own tests while every interrupted
    fan-out still paid twice.
    """
    src = inspect.getsource(integration.build_artifacts)
    assert "resumable(port" in src, (
        "ResumePort was defined but never wired; a fan-out that dies part way "
        "loses every call it had already paid for"
    )


def test_resume_is_its_OWN_switch_and_never_rides_on_reuse():
    """The pin on the mistake, not just on the feature.

    `reuse` skips a stage whose artifact still passes its gate. It does NOT say
    the inputs are unchanged -- a `reuse=True` run over an artifact the gate
    REJECTS must regenerate with a real call, and replaying the recording there
    returns the same rejected content and makes re-gating vacuous.
    """
    assert "resume_calls" in inspect.signature(integration.build_artifacts).parameters
    assert integration.build_artifacts.__kwdefaults__ is not None
    src = inspect.getsource(integration.build_artifacts)
    assert "if resume_calls:" in src
    assert "if reuse:\n        port = resumable" not in src, (
        "resume must not be inferred from `reuse` -- a stage the gate rejects "
        "has to regenerate with a real call"
    )


def test_resumable_returns_a_ResumePort_wrapping_the_inner_port(tmp_path):
    inner = _Counting()
    port = resumable(inner, tmp_path)
    assert isinstance(port, ResumePort)
    assert port.inner is inner
