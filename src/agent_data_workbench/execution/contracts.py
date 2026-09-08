"""Typed inputs, outputs and adapter protocols for target execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from agent_data_workbench.shared.contracts import Contract


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


class EnvironmentConfig(Contract):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    authority: str = Field(
        min_length=1, description="Actual service/store inspected by the observer"
    )
    setup: list[str] = Field(min_length=1)
    reset: list[str] = Field(min_length=1)
    ready: list[str] = Field(min_length=1)
    inspect: list[str] = Field(min_length=1)
    teardown: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    initial_state_sha256: str | None = None
    timeout: int | None = Field(default=None, ge=1)


class Observation(Contract):
    artifacts: dict[str, Any]


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
