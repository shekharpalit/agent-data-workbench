"""Stream a native CLI invocation without rebuilding its agent loop or context."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from agent_data_workbench.shared.processes import BackendError


class SessionPaused(BackendError):
    pass


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def stream_session(
    args: list[str],
    prompt: str,
    *,
    cwd: Path,
    events_path: Path,
    stderr_path: Path,
    cancel_path: Path,
    timeout: float | None,
    on_event: Callable[[dict], None],
) -> None:
    started = time.monotonic()
    with (
        stderr_path.open("w", encoding="utf-8") as errors,
        events_path.open("w", encoding="utf-8") as events,
    ):
        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
            start_new_session=os.name == "posix",
        )
        messages: queue.Queue[str | None] = queue.Queue(maxsize=256)
        stopping = threading.Event()

        def enqueue(line):
            while not stopping.is_set():
                try:
                    messages.put(line, timeout=0.1)
                    return
                except queue.Full:
                    continue

        def read_output():
            try:
                for line in process.stdout:
                    enqueue(line)
            finally:
                enqueue(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        closed = False
        terminal_error = False
        try:
            process.stdin.write(prompt)
            process.stdin.close()
            while not (closed and process.poll() is not None):
                if cancel_path.exists():
                    raise SessionPaused("Research paused; resume its saved native session")
                if timeout is not None and time.monotonic() - started >= timeout:
                    raise SessionPaused("Developer-supplied time budget reached; progress is saved")
                try:
                    line = messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    closed = True
                    continue
                events.write(line)
                events.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    on_event(event)
                    if event.get("type") == "turn.failed" or (
                        event.get("type") == "result" and event.get("is_error")
                    ):
                        terminal_error = True
            if process.wait() != 0 or terminal_error:
                raise BackendError(
                    f"Native CLI exited with code {process.returncode}; "
                    "progress and local diagnostics are saved"
                )
        finally:
            stopping.set()
            _terminate(process)
            reader.join(timeout=5)
            process.stdout.close()
            if not process.stdin.closed:
                process.stdin.close()
