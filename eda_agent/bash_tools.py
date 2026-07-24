from __future__ import annotations

import json
import os
import signal
import sys
from subprocess import PIPE, Popen, TimeoutExpired
from typing import Tuple

from pydantic import BaseModel


class CommandResult(BaseModel):
    stdout: str
    stderr: str


def _kill_process_tree(proc: Popen) -> None:
    """Kill the process and all its children via process group or direct kill."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        pass


def run_bash_command(
    cmd: str,
    timeout: float | None = None,
    *,
    cwd: str | None = None,
) -> Tuple[bool, str]:
    kwargs: dict = dict(
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        cwd=cwd,
    )
    if sys.platform != "win32":
        kwargs["start_new_session"] = True

    process = Popen(cmd, **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except TimeoutExpired:
        _kill_process_tree(process)
        err_msg = f"Timeout {timeout}s reached."
        return (
            False,
            json.dumps(
                CommandResult(stdout="", stderr=err_msg).model_dump(), indent=4
            ),
        )
    except Exception:  # noqa: BLE001
        _kill_process_tree(process)
        raise
    return (
        process.returncode == 0,
        json.dumps(CommandResult(stdout=stdout, stderr=stderr).model_dump(), indent=4),
    )
