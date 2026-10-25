"""`AgentPort` -- the rendezvous a local agent answers, and the hazards it closes.

`FilePort`'s pins live in test_model_io.py; these are only about the two things
this port does differently: it waits, and it refuses to hand back an answer that
predates the question.
"""
import threading
import time

import pytest

from specflow.model_io import AgentPort, make_port


def _answer_after(path, text, delay=0.05):
    def run():
        time.sleep(delay)
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_waits_for_an_answer_instead_of_raising(tmp_path):
    port = AgentPort(root=tmp_path, poll=0.01)
    _answer_after(tmp_path / "s_r0_response.txt", "the check")
    assert port.complete(stage="s", round_=0, prompt="write one") == "the check"
    assert (tmp_path / "s_r0_prompt.txt").read_text() == "write one"


def test_a_stale_response_is_deleted_before_the_prompt_is_published(tmp_path):
    """The hazard `FilePort` documents and cannot fix: a repair round composes a
    NEW prompt under the same (stage, round_), and the previous round's answer is
    still sitting there. Returning it would be a reply to a question never asked.
    """
    (tmp_path / "s_r0_response.txt").write_text("answer to the OLD prompt")
    port = AgentPort(root=tmp_path, poll=0.01)
    _answer_after(tmp_path / "s_r0_response.txt", "answer to the NEW prompt")
    assert port.complete(stage="s", round_=0, prompt="repair it") == "answer to the NEW prompt"


def test_an_empty_response_file_is_not_an_answer(tmp_path):
    """`open(...,'w')` creates the file before a byte of it exists, so existence
    alone would hand the stage a parse failure and blame the model for it."""
    port = AgentPort(root=tmp_path, poll=0.01)
    (tmp_path / "s_r0_response.txt").write_text("")
    _answer_after(tmp_path / "s_r0_response.txt", "  real  ", delay=0.1)
    assert port.complete(stage="s", round_=0, prompt="p").strip() == "real"


def test_the_prompt_is_published_atomically(tmp_path):
    """A poller must never see a half-written prompt, so the visible file appears
    only once it is complete -- never as a growing partial."""
    port = AgentPort(root=tmp_path, poll=0.01)
    seen = []

    def watch():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            p = tmp_path / "s_r0_prompt.txt"
            if p.exists():
                seen.append(p.read_text())
                break
    t = threading.Thread(target=watch, daemon=True)
    t.start()
    _answer_after(tmp_path / "s_r0_response.txt", "x", delay=0.2)
    port.complete(stage="s", round_=0, prompt="x" * 100_000)
    t.join(timeout=2)
    assert seen == ["x" * 100_000]
    assert not list(tmp_path.glob("*.part"))


def test_a_dead_pool_times_out_rather_than_hanging_the_stage(tmp_path):
    port = AgentPort(root=tmp_path, timeout=0.05, poll=0.01)
    with pytest.raises(TimeoutError, match="no agent answered"):
        port.complete(stage="s", round_=0, prompt="p")


def test_concurrent_calls_surface_every_prompt_at_once(tmp_path):
    """The point of blocking rather than raising: a fan-out over N items shows N
    prompts to the pool. `FilePort` aborts the fan-out on item one instead."""
    port = AgentPort(root=tmp_path, poll=0.01)
    threads = [threading.Thread(target=port.complete, kwargs=dict(
        stage=f"oracle_REQ-{i:04d}", round_=0, prompt=f"p{i}"), daemon=True)
        for i in range(5)]
    for t in threads:
        t.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(list(tmp_path.glob("*_prompt.txt"))) < 5:
        time.sleep(0.01)
    assert len(list(tmp_path.glob("*_prompt.txt"))) == 5
    for i in range(5):
        (tmp_path / f"oracle_REQ-{i:04d}_r0_response.txt").write_text("done")
    for t in threads:
        t.join(timeout=2)
        assert not t.is_alive()


def test_make_port_knows_the_kind(tmp_path):
    assert isinstance(make_port("agent", tmp_path), AgentPort)
