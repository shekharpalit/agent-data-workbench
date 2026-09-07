"""Explicit target execution adapters. Commands run locally, not in a security sandbox."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from .backends import CliAnalyzer, run_process
from .command_sources import check_sources, pinned_command
from .conversations import (
    CommandSession,
    CommandUserSimulator,
    ConversationRunner,
    ConversationSpec,
)
from .environments import EnvironmentConfig, EnvironmentRunner
from .models import Contract, json_text
from .project import digest
from .tasks import parse_object, relative_path


class Execution(Contract):
    output: dict[str, Any] = Field(default_factory=dict)
    status: Literal["completed", "runner_error", "timeout"] = "completed"
    error: str | None = None
    latency_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage: dict[str, Any] = Field(default_factory=dict)


class TargetRunner(Protocol):
    def identity(self) -> dict: ...
    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution: ...


class RunnerConfig(Contract):
    name: str = Field(min_length=1)
    kind: Literal["command", "codex", "claude"]
    command: list[str] = Field(default_factory=list)
    model: str = ""
    prompt: str = ""
    timeout: int = Field(default=120, ge=1, le=3600)
    environment_version: str = Field(min_length=1)
    source_files: list[str] = Field(default_factory=list)
    fidelity: Literal["output", "next_action", "environment"] = "output"
    environment: EnvironmentConfig | None = None
    conversation: ConversationSpec | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "command" and not self.command:
            raise ValueError("Command runner requires an explicit argv list")
        if self.kind != "command" and (not self.model or not self.prompt):
            raise ValueError("Model runner requires an explicit model and target prompt")
        if self.kind != "command" and self.conversation is not None:
            raise ValueError("Multi-turn runs require a persistent command session adapter")
        if self.kind != "command" and self.fidelity == "environment":
            raise ValueError("CLI model runner cannot claim environment execution")
        return self


class JsonReply(Contract):
    output_json: str = Field(description="The requested output, encoded as a JSON object string.")


class ConfiguredRunner:
    def __init__(self, config: RunnerConfig, base_dir: Path):
        self.config = config.model_copy(deep=True)
        self.base_dir = base_dir.resolve()
        self.args, self.sources = pinned_command(config.command, config.source_files, self.base_dir)
        self._conversation = None
        self._simulator = None
        if config.conversation:
            if config.conversation.simulator:
                self._simulator = CommandUserSimulator(
                    config.conversation.simulator, self.base_dir, self.base_dir
                )
            self._conversation = ConversationRunner(self, config.conversation, self._simulator)
        target = self._conversation or _OneShot(self)
        self._environment = (
            EnvironmentRunner(target, config.environment, self.base_dir)
            if config.environment
            else None
        )

    def identity(self) -> dict:
        value = {
            "config": self.config.model_dump(),
            "source_sha256": self.sources,
            "resolved_command": self.args,
            "environment": self._environment.environment_identity() if self._environment else None,
            "simulator": self._simulator.identity() if self._simulator else None,
        }
        return {**value, "sha256": digest(value)}

    def for_task(
        self, environment: EnvironmentConfig | None, conversation: ConversationSpec | None
    ) -> ConfiguredRunner:
        """Bind a task's frozen scenario without accepting changed target implementation."""
        check_sources(self.sources)
        config = self.config.model_copy(
            deep=True,
            update={
                "environment": environment,
                "conversation": conversation,
            },
        )
        runner = ConfiguredRunner(RunnerConfig.model_validate(config.model_dump()), self.base_dir)
        if runner.sources != self.sources:
            raise ValueError("Target sources changed while binding the task scenario")
        return runner

    def authoritative_artifacts(self, trial_dir: Path) -> dict:
        return self._environment.authoritative_artifacts(trial_dir) if self._environment else {}

    def trial_evidence(self, trial_dir: Path) -> dict:
        return {
            "environment": self._environment.trial_evidence(trial_dir)
            if self._environment
            else None,
            "conversation": (
                self._conversation.trial_evidence(trial_dir) if self._conversation else None
            ),
        }

    def open_session(self, visible_input: dict, trial_dir: Path, seed: int) -> CommandSession:
        check_sources(self.sources)
        if self.config.kind != "command":
            raise ValueError("Target does not support persistent sessions")
        return CommandSession(
            self.args, visible_input, trial_dir, seed, self.config.timeout, self.sources
        )

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        if self._environment:
            return self._environment.run(visible_input, trial_dir, seed)
        if self._conversation:
            return self._conversation.run(visible_input, trial_dir, seed)
        return self._run_once(visible_input, trial_dir, seed)

    def _run_once(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        started = time.monotonic()
        try:
            check_sources(self.sources)
            if self.config.kind == "command":
                request = json_text({"input": visible_input, "seed": seed})
                raw = run_process(self.args, request, trial_dir, self.config.timeout)
                if len(raw) > 2_000_000:
                    raise ValueError("Runner output exceeds 2 million characters")
                envelope = parse_object(raw)
                if not isinstance(envelope.get("output"), dict):
                    raise ValueError("Runner must return an envelope with an output object")
                result = Execution.model_validate(envelope)
            else:
                backend = CliAnalyzer(
                    self.config.kind, model=self.config.model, timeout=self.config.timeout
                )
                result = JsonReply.model_validate(
                    backend.analyze(
                        self.config.prompt
                        + "\nReturn the requested output encoded in output_json.\n"
                        + json_text({"input": visible_input}),
                        JsonReply.model_json_schema(),
                    )
                )
                result = Execution(
                    output=parse_object(result.output_json),
                    usage={"seed_control": "unsupported by this CLI adapter"},
                )
            check_sources(self.sources)
            result.latency_seconds = time.monotonic() - started
            if result.cost_usd is not None and result.cost_usd < 0:
                raise ValueError("Recorded cost must be nonnegative")
            return result
        except (RuntimeError, ValueError, OSError) as exc:
            # Private provider/runner output is never embedded in an error message.
            return Execution(
                status="timeout" if "timed out" in str(exc) else "runner_error",
                error="Target failed; inspect its configuration, dependencies and limits",
                latency_seconds=time.monotonic() - started,
            )


class _OneShot:
    def __init__(self, runner: ConfiguredRunner):
        self.runner = runner

    def identity(self):
        return self.runner.identity()

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        return self.runner._run_once(visible_input, trial_dir, seed)


def read_artifacts(trial_dir: Path, names: list[str]) -> dict:
    artifacts = {}
    for name in names:
        relative_path(name)
        path = (trial_dir / name).resolve()
        if not path.is_relative_to(trial_dir.resolve()) or not path.is_file():
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            from .models import _reject_constant

            artifacts[name] = json.loads(
                path.read_text(encoding="utf-8"), parse_constant=_reject_constant
            )
        except ValueError, UnicodeError:
            continue
    return artifacts
