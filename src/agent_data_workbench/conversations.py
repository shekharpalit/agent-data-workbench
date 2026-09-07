"""Continuous target sessions with scripted or developer-supplied reactive users."""

from __future__ import annotations

import copy
import json
import os
import queue
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import Field, model_validator

from .command_sources import check_sources, pinned_command
from .identifiers import new_id
from .models import Contract, json_text
from .project import digest, save

if TYPE_CHECKING:
    from .runners import Execution


class UserTurn(Contract):
    message: str = Field(min_length=1)


class SimulatorConfig(Contract):
    command: list[str] = Field(min_length=1)
    source_files: list[str] = Field(default_factory=list)
    timeout: int | None = Field(default=None, ge=1)


class ConversationSpec(Contract):
    turns: list[UserTurn] = Field(min_length=1)
    simulator: SimulatorConfig | None = None
    max_turns: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid(self):
        if self.simulator and len(self.turns) != 1:
            raise ValueError("Reactive conversations specify one initial user turn")
        if self.max_turns is not None and self.max_turns < len(self.turns):
            raise ValueError("max_turns cannot truncate scripted follow-ups")
        return self


class SessionReply(Contract):
    message: str
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage: dict[str, Any] = Field(default_factory=dict)


class AgentSession(Protocol):
    """Adapters keep the same real target session and tool state between sends."""

    def send(self, turn: UserTurn) -> SessionReply: ...
    def close(self) -> None: ...


class SessionTarget(Protocol):
    def identity(self) -> dict: ...
    def open_session(self, visible_input: dict, trial_dir: Path, seed: int) -> AgentSession: ...


class ReactiveUser(Protocol):
    """A user simulator sees the interaction, never task verifier truth."""

    def identity(self) -> dict: ...
    def next_turn(self, interaction: list[dict]) -> UserTurn | None: ...


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
        from .tasks import parse_object

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


class CommandUserSimulator:
    """A user-provided simulator command receives only the visible conversation."""

    def __init__(self, config: SimulatorConfig, base_dir: Path, cwd: Path):
        self.config = config
        self.args, self.sources = pinned_command(config.command, config.source_files, base_dir)
        self.cwd = cwd

    def identity(self):
        return {"config": self.config.model_dump(), "sources": self.sources, "command": self.args}

    def next_turn(self, interaction: list[dict]) -> UserTurn | None:
        from .backends import run_process
        from .tasks import parse_object

        check_sources(self.sources)
        raw = run_process(
            self.args, json_text({"interaction": interaction}), self.cwd, self.config.timeout
        )
        check_sources(self.sources)
        response = parse_object(raw)
        if response.get("message") is None:
            return None
        return UserTurn(message=response["message"])


class ConversationRunner:
    def __init__(
        self, target: SessionTarget, spec: ConversationSpec, simulator: ReactiveUser | None = None
    ):
        self.target = target
        self.spec = spec.model_copy(deep=True)
        self.simulator = simulator
        self._evidence: dict[str, dict] = {}

    def identity(self):
        return {
            "target": self.target.identity(),
            "conversation": self.spec.model_dump(),
            "simulator": self.simulator.identity() if self.simulator else None,
        }

    def trial_evidence(self, trial_dir: Path) -> dict:
        return copy.deepcopy(self._evidence.get(str(trial_dir.resolve()), {}))

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        from .runners import Execution

        started = time.monotonic()
        interaction = []
        result = Execution()
        session = None
        stop_reason = "script_finished"
        next_turn = self.spec.turns[0]
        try:
            session = self.target.open_session(visible_input, trial_dir, seed)
            while next_turn is not None:
                index = len(interaction)
                event = {
                    "index": index,
                    "user": next_turn.model_dump(),
                    "reply": None,
                    "status": "pending",
                    "error": None,
                }
                interaction.append(event)
                # Save the attempted turn before invoking external code.
                save(trial_dir / "interaction.json", {"turns": interaction, "status": "running"})
                reply = session.send(next_turn)
                event.update(reply=reply.model_dump(), status="completed")
                result.output = reply.output
                if reply.cost_usd is not None:
                    result.cost_usd = (result.cost_usd or 0) + reply.cost_usd
                if self.simulator:
                    if self.spec.max_turns is not None and len(interaction) >= self.spec.max_turns:
                        stop_reason = "turn_limit"
                        break
                    next_turn = self.simulator.next_turn(copy.deepcopy(interaction))
                    if next_turn is None:
                        stop_reason = "simulator_stopped"
                else:
                    next_turn = (
                        self.spec.turns[index + 1] if index + 1 < len(self.spec.turns) else None
                    )
        except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
            result.status = "timeout" if isinstance(exc, TimeoutError) else "runner_error"
            result.error = "Conversation failed; inspect the recorded partial interaction"
            stop_reason = "execution_error"
            if interaction and interaction[-1]["status"] == "pending":
                interaction[-1].update(status=result.status, error=result.error)
        finally:
            if session is not None:
                try:
                    session.close()
                except OSError, RuntimeError:
                    result.status = "runner_error"
                    result.error = "Target session did not close cleanly"
                    stop_reason = "cleanup_error"
            result.latency_seconds = time.monotonic() - started
            record = {
                "spec_sha256": digest(self.spec.model_dump()),
                "turns": interaction,
                "status": result.status,
                "stop_reason": stop_reason,
                "success_determined_by": "task_verifier",
                "evidence_source": "target_session_adapter",
                "session_id": getattr(session, "session_id", None),
                "error": result.error,
                "simulator": self.simulator.identity() if self.simulator else None,
            }
            self._evidence[str(trial_dir.resolve())] = copy.deepcopy(record)
            save(trial_dir / "interaction.json", record)
        return result
