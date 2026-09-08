"""Persistent target sessions using a line-delimited JSON subprocess protocol."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
from pathlib import Path

from agent_data_workbench.execution.contracts import SessionReply, UserTurn
from agent_data_workbench.shared.commands import check_sources
from agent_data_workbench.shared.identifiers import new_id


class CommandSession:
    """One NDJSON process. Each turn request gets exactly one SessionReply line."""

    def __init__(
        self,
        args: list[str],
        visible_input: dict,
        trial_dir: Path,
        seed: int,
        timeout: int | None,
        source_sha256: dict[str, str] | None = None,
    ):
        self.sources = source_sha256 or {}
        self.session_id = new_id()
        self.initial_input = visible_input
        self.seed = seed
        self.timeout = timeout
        self.index = 0
        self.lines: queue.Queue = queue.Queue()
        self.stderr = (trial_dir / "target-stderr.log").open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                args,
                cwd=trial_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.stderr,
                text=True,
                encoding="utf-8",
                start_new_session=True,
            )
        except BaseException:
            self.stderr.close()
            raise
        self.reader = threading.Thread(target=self._read_lines, daemon=True)
        self.reader.start()

    def _read_lines(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        except OSError, UnicodeError:
            pass
        finally:
            self.lines.put(None)

    def send(self, turn: UserTurn) -> SessionReply:
        check_sources(self.sources)
        request = {
            "type": "turn",
            "session_id": self.session_id,
            "turn_index": self.index,
            "seed": self.seed,
            "message": turn.message,
        }
        if self.index == 0:
            request["input"] = self.initial_input
        self.process.stdin.write(json.dumps(request, allow_nan=False) + "\n")
        self.process.stdin.flush()
        try:
            line = self.lines.get(timeout=self.timeout)
        except queue.Empty as exc:
            raise TimeoutError("Target session timed out") from exc
        if line is None:
            raise RuntimeError("Target session exited without a reply")
        from agent_data_workbench.shared.json import parse_object

        result = SessionReply.model_validate(parse_object(line))
        check_sources(self.sources)
        self.index += 1
        return result

    def close(self) -> None:
        try:
            if not self.process.stdin.closed:
                self.process.stdin.close()
        except BrokenPipeError:
            pass
        # The leader may already have exited while its children still own stdout.
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        finally:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait()
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.stderr.close()
        check_sources(self.sources)
