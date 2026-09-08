"""Subprocess execution and error handling shared by trusted command adapters."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


class BackendError(RuntimeError):
    pass


def run_process(
    args: list[str], prompt: str, cwd: Path, timeout: int | None, *, log_prefix: Path | None = None
) -> str:
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
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate()
        _save_logs(log_prefix, stdout, stderr)
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise BackendError(
            f"Analyzer timed out after {timeout}s; no fallback was attempted"
        ) from exc
    _save_logs(log_prefix, stdout, stderr)
    if process.returncode:
        # Do not echo provider stderr: it can contain private trace content or account details.
        raise BackendError(
            f"{Path(args[0]).name} exited with code {process.returncode}. "
            "Check its login and account limits directly; no fallback was attempted."
        )
    return stdout


def _save_logs(prefix: Path | None, stdout: str, stderr: str) -> None:
    if prefix is not None:
        prefix.with_name(prefix.name + "-stdout.log").write_text(stdout, encoding="utf-8")
        prefix.with_name(prefix.name + "-stderr.log").write_text(stderr, encoding="utf-8")
