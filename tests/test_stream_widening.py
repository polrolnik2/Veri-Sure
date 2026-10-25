"""A stream that dies with no terminal event is a slice problem, not a network one.

Measured on this gateway, the same 21.7 KB oracle prompt, one stream each, every
event timestamped:

    medium, slice  9000 -- completed in 38.4s, 4535 chars.
    high,   slice  9000 -- 7545 events, EVERY ONE a reasoning summary and not a
                           single content delta; last event at t=206.0s, then
                           300.3s of exact silence, then the drop.
    high,   slice 48000 -- completed in 96.5s, 4408 chars, worst gap 10.2s.

When a response hits `max_output_tokens` while still reasoning, this gateway
sends no `response.incomplete`, no `response.failed`, nothing -- the stream stops
and the 300s idle reaper closes it. The continuation machinery is driven by the
`incomplete` event, so the single failure it exists to handle is the one failure
it never hears about, and the retry loop then resent the identical doomed
request twice more: 25 minutes to reproduce a failure already understood.

Six live failures were attributed to "high effort is unsafe through this
gateway" and the `deep_effort` switch was retreated from on that reading. The
reading was wrong. These pin the correction.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from specflow.model_io import ApiPort, PortSettings


class _Event:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


def _drop() -> Exception:
    return httpx.RemoteProtocolError(
        "peer closed connection without sending complete message body")


class _NeedsSlice:
    """Drops unless `max_output_tokens` reaches `enough`.

    The gateway's actual behaviour: below the reasoning budget the response is
    truncated mid-reasoning and never terminated, so the client sees a bare
    disconnect and no status to act on.
    """

    def __init__(self, enough: int):
        self.enough = enough
        self.slices: list[int] = []

    def create(self, **kw):
        self.slices.append(kw["max_output_tokens"])
        if kw["max_output_tokens"] < self.enough:
            raise _drop()
        final = type("R", (), {"status": "completed", "usage": None,
                               "output_text": "", "model": "m"})()
        return iter([
            _Event("response.output_text.delta", delta="oracle body"),
            _Event("response.completed", response=final),
        ])


def _cfg(effort: str):
    return type("Cfg", (), {"model": "gpt-5-mini", "reasoning_effort": effort,
                            "generate_kwargs": {}, "api_flavor": "responses",
                            "stream": True})()


def _run(port, tmp_path, effort="high"):
    return port._complete_responses(
        _cfg(effort), stage="oracle_REQ-0002", round_=0, prompt="p",
        response_path=tmp_path / "out.txt")


def _port(tmp_path, client, **settings):
    port = ApiPort(root=tmp_path, settings=PortSettings(**settings))
    port._client = lambda: client  # type: ignore[method-assign]
    return port


class TestTheSliceTable:
    def test_high_gets_a_slice_wide_enough_for_the_measured_run(self):
        """48000 completed the probe in 96.5s; 9000 and 24000 both died. The
        table is that measurement doubled, so a run whose reasoning is longer
        than the probe's still lands inside one slice."""
        s = PortSettings()
        assert s.chunk_for("high") == 48000
        assert s.chunk_for("xhigh") >= s.chunk_for("high")
        assert s.chunk_for("medium") == 9000

    def test_the_ceiling_leaves_room_to_continue_at_every_effort(self):
        """`rounds` is `ceil(total / slice)`. With the old 48000 ceiling and
        high's 48000 slice it is 1, and continuation would disappear silently at
        exactly the effort whose generations are longest."""
        s = PortSettings()
        for effort in ("low", "medium", "high", "xhigh"):
            rounds = -(-s.max_output_tokens // s.chunk_for(effort))
            assert rounds >= 3, f"{effort} gets only {rounds} continuation(s)"


class TestWidening:
    def test_a_drop_widens_the_slice_instead_of_failing(self, tmp_path, monkeypatch):
        """The regression, stated as the gateway states it: a disconnect with no
        status. The only repair is a wider slice."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        gw = _NeedsSlice(enough=36000)
        text = _run(_port(tmp_path, type("C", (), {"responses": gw})(),
                          responses_chunk=9000,
                          effort_chunk={"high": 9000}), tmp_path)

        assert text == "oracle body"
        assert gw.slices == [9000, 18000, 36000]

    def test_the_doomed_request_is_not_resent_identically_first(
            self, tmp_path, monkeypatch):
        """Each reproduction costs ~500s of reasoning followed by 300s of
        silence. Resending a request whose repair is already known is 25 minutes
        to learn nothing -- so while widening is available, `stream_retries`
        does not apply."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        gw = _NeedsSlice(enough=36000)
        _run(_port(tmp_path, type("C", (), {"responses": gw})(),
                   responses_chunk=9000, stream_retries=2,
                   effort_chunk={"high": 9000}), tmp_path)

        assert gw.slices == [9000, 18000, 36000], (
            "a resend at the same slice reproduces a failure already understood")

    def test_widening_is_bounded_and_the_failure_is_still_reported(
            self, tmp_path, monkeypatch):
        """Past a 4x under-estimate it is not a slice problem, and pretending
        otherwise would spend the whole ceiling on one hopeless call."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        gw = _NeedsSlice(enough=10 ** 9)
        port = _port(tmp_path, type("C", (), {"responses": gw})(),
                     responses_chunk=9000, stream_retries=0,
                     effort_chunk={"high": 9000})

        with pytest.raises(RuntimeError) as err:
            _run(port, tmp_path)

        assert "the connection dropped mid-stream" in str(err.value)
        assert gw.slices == [9000, 18000, 36000]

    def test_a_slice_already_at_the_ceiling_is_resent_not_widened(
            self, tmp_path, monkeypatch):
        """There is nothing to widen into, so the normal retry policy is the
        only policy left -- and it must still run."""
        monkeypatch.setattr("time.sleep", lambda _s: None)
        gw = _NeedsSlice(enough=10 ** 9)
        port = _port(tmp_path, type("C", (), {"responses": gw})(),
                     responses_chunk=9000, max_output_tokens=9000,
                     stream_retries=2, effort_chunk={"high": 9000})

        with pytest.raises(RuntimeError):
            _run(port, tmp_path)

        assert gw.slices == [9000, 9000, 9000]

    def test_a_healthy_call_is_untouched(self, tmp_path):
        """Nothing about the common path changes: one slice, one request."""
        gw = _NeedsSlice(enough=0)
        text = _run(_port(tmp_path, type("C", (), {"responses": gw})(),
                          responses_chunk=9000), tmp_path, effort="medium")

        assert text == "oracle body"
        assert gw.slices == [9000]


# ------------------------------------- the ceiling the RUNNER actually passes

def test_the_runner_default_leaves_room_to_continue_at_every_effort():
    """`TestTheSliceTable` above asserts on `PortSettings()` and passed happily
    while the live configuration had no continuation at all.

    `run_chipverilog` passes `--max-output-tokens` unconditionally into
    `PortSettings`, so the dataclass default is never what runs. Its default was
    48000, `effort_chunk` gives `xhigh` 64000, and the body cap became
    `min(64000, 48000)` = 48000 = total: `rounds` 1, no continuation, and the
    widening branch disabled because it needs `slice < total`.

    Cost of the gap: y-i2c's witness call, 77 KB of prompt at xhigh, took a
    mid-stream drop with neither recovery mechanism available. The oracle stage
    never ran, and the reference-model gate then passed with zero errors because
    it had nothing to decide against.

    So this pins the RUNNER's number, not the dataclass's.
    """
    import re

    # Read the DECLARED default rather than invoking argparse: the parser
    # requires --task and --out, and mocking those up would test the mock. The
    # literal in the source is exactly what shipped.
    src = Path("benchmarks/run_chipverilog.py").read_text()
    m = re.search(r'"--max-output-tokens", type=int, default=(\d+)', src)
    assert m, "could not find the --max-output-tokens default"
    default = int(m.group(1))

    settings = PortSettings()
    for effort in ("low", "medium", "high", "xhigh"):
        slice_ = settings.chunk_for(effort)
        assert default > slice_, (
            f"the runner's --max-output-tokens default ({default}) is not above "
            f"{effort}'s slice ({slice_}); rounds would be 1 and widening off")
        assert default // slice_ >= 3, (
            f"{effort}: only {default // slice_} continuation(s) at the runner's "
            f"default")


def test_a_ceiling_at_or_below_the_slice_narrows_the_slice_rather_than_dying(
        tmp_path, monkeypatch):
    """An operator may still pass a small ceiling, and it must not be fatal.

    The ceiling is a COST control, so it is respected -- the slice comes down to
    fit rather than the ceiling going up. What must not survive is the state
    where neither continuation nor widening exists.
    """
    monkeypatch.setattr("time.sleep", lambda _s: None)
    gw = _NeedsSlice(enough=30000)
    port = _port(tmp_path, type("C", (), {"responses": gw})(),
                 responses_chunk=3000, max_output_tokens=48000,
                 effort_chunk={"xhigh": 48000})

    text = _run(port, tmp_path, effort="xhigh")

    assert text == "oracle body"
    assert gw.slices[0] < 48000, (
        "slice == ceiling leaves no continuation and no widening; it must be "
        f"narrowed, got {gw.slices[0]}")
    assert len(gw.slices) > 1, "and the widening path must therefore be reachable"
