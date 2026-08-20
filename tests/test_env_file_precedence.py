"""`--env-file` must reach the stages, not just the process environment.

`load_env_file` values deliberately OVERRIDE `os.environ` -- a rotated key has
to be able to reach a session that is already running, and the stale value is
exactly what is in the environment. That design makes a second env file
dangerous: every specflow port calls `load_env_file()` itself, so unless
`SPECFLOW_ENV_FILE` names the same file, `.env.local` wins and the flag is
decorative.

Measured before the fix: a run launched with an env file naming `high` did its
reference-model generation at `xhigh`. The only reason it was noticed is that a
failure message happened to print the effort it had used.
"""

from __future__ import annotations

from pathlib import Path

from specflow.model_io import load_env_file


def test_a_named_env_file_wins_over_the_default(tmp_path, monkeypatch):
    other = tmp_path / "other.env"
    other.write_text("OPENAI_REASONING_EFFORT=high\n", encoding="utf-8")
    default = tmp_path / ".env.local"
    default.write_text("OPENAI_REASONING_EFFORT=xhigh\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(other))
    assert load_env_file()["OPENAI_REASONING_EFFORT"] == "high"

    monkeypatch.delenv("SPECFLOW_ENV_FILE")
    assert load_env_file()["OPENAI_REASONING_EFFORT"] == "xhigh", (
        "without SPECFLOW_ENV_FILE the default is read -- which is why the "
        "runner must set it"
    )


def test_the_runner_points_the_stages_at_the_same_file():
    """The bug was that it did not. Pinned by source, because reproducing it
    needs a live run and it cost one."""
    src = Path(__file__).resolve().parents[1] / "benchmarks" / "run_chipverilog.py"
    text = src.read_text(encoding="utf-8")
    assert 'os.environ["SPECFLOW_ENV_FILE"]' in text
    assert text.index('os.environ["SPECFLOW_ENV_FILE"]') < text.index(
        "os.environ.update(load_env_file("
    ), "the stages must be pointed at the file before anything reads it"
