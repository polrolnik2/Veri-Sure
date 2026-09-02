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


def test_the_default_is_found_from_ANY_cwd_because_it_lives_at_the_repo_root(
        tmp_path, monkeypatch):
    """A driver launched from elsewhere used to get `{}` and no warning.

    `.env.local` is a repo-root file -- gitignored there, and the only channel
    a live process has for a rotated key. Resolving it against the cwd alone
    meant `cd /home/user/runs/h3-i2c && python run.py` silently found nothing
    and ran on the container's environment, whose OPENAI_BASE_URL is missing
    its `/v1`. Every call then 404'd with an error naming the MODEL, which is
    the wrong place to look; the run was lost and relaunched.
    """
    monkeypatch.delenv("SPECFLOW_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)          # no .env.local here
    repo_root = Path(load_env_file.__globals__["__file__"]).resolve().parent.parent

    if (repo_root / ".env.local").exists():
        assert load_env_file(), (
            "the repo root carries a credentials file, so a run launched from "
            "an unrelated directory must still find it"
        )
    else:
        assert load_env_file() == {}


def test_finding_NO_credentials_file_is_WARNED_not_swallowed(
        tmp_path, monkeypatch, caplog):
    """The silence is the defect, not the empty dict.

    Returning `{}` is right -- the process environment is a legitimate source.
    Doing it without a word is what turns a wrong working directory into a 404
    forty seconds later that blames the model.
    """
    monkeypatch.delenv("SPECFLOW_ENV_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        load_env_file.__globals__["Path"], "exists", lambda self: False)

    with caplog.at_level("WARNING"):
        assert load_env_file() == {}
    assert any("no credentials file found" in r.message for r in caplog.records), (
        "a missing credentials file must say so, and name where it looked"
    )
