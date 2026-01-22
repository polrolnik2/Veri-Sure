from __future__ import annotations

import json
from subprocess import PIPE, Popen, TimeoutExpired
from typing import Tuple

from pydantic import BaseModel


class CommandResult(BaseModel):
    stdout: str
    stderr: str


def run_bash_command(
    cmd: str,
    timeout: float | None = None,
    *,
    cwd: str | None = None,
) -> Tuple[bool, str]:
    process = Popen(
        cmd,
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        cwd=cwd,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except TimeoutExpired:
        process.kill()
        err_msg = f"Timeout {timeout}s reached."
        return (
            False,
            json.dumps(
                CommandResult(stdout="", stderr=err_msg).model_dump(), indent=4
            ),
        )
    return (
        process.returncode == 0,
        json.dumps(CommandResult(stdout=stdout, stderr=stderr).model_dump(), indent=4),
    )
