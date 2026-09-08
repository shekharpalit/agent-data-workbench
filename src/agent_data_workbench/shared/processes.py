"""Subprocess execution and error handling shared by trusted command adapters."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


class BackendError(RuntimeError):
    pass


def run_process(args: list[str], prompt: str, cwd: Path, timeout: int) -> str:
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise BackendError(
            f"Analyzer timed out after {timeout}s; no fallback was attempted"
        ) from exc
    if process.returncode:
        # Do not echo provider stderr: it can contain private trace content or account details.
        raise BackendError(
            f"{Path(args[0]).name} exited with code {process.returncode}. "
            "Check its login and account limits directly; no fallback was attempted."
        )
    return stdout
