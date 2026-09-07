"""Explicit target execution adapters. Commands run locally, not in a security sandbox."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from .backends import CliAnalyzer, run_process
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

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "command" and not self.command:
            raise ValueError("Command runner requires an explicit argv list")
        if self.kind != "command" and (not self.model or not self.prompt):
            raise ValueError("Model runner requires an explicit model and target prompt")
        if self.kind != "command" and self.fidelity == "environment":
            raise ValueError("CLI model runner cannot claim environment execution")
        return self


class JsonReply(Contract):
    output_json: str = Field(description="The requested output, encoded as a JSON object string.")


class ConfiguredRunner:
    def __init__(self, config: RunnerConfig, base_dir: Path):
        self.config = config
        self.base_dir = base_dir.resolve()
        self.sources = {}
        for filename in config.source_files:
            path = (self.base_dir / filename).resolve()
            if not path.is_file():
                raise ValueError("Runner source file does not exist")
            self.sources[str(path)] = digest(path.read_text(encoding="utf-8"))
        self.args = list(config.command)
        if self.args:
            executable = Path(self.args[0])
            if executable.is_absolute():
                resolved = str(executable)
            elif "/" in self.args[0]:
                resolved = str((self.base_dir / executable).resolve())
            else:
                resolved = shutil.which(self.args[0])
            if not resolved or not Path(resolved).is_file():
                raise ValueError("Runner executable not found")
            self.args[0] = resolved
            # Resolve explicitly supplied relative script paths before switching trial cwd.
            for i, arg in enumerate(self.args[1:], 1):
                if not arg.startswith("-") and (self.base_dir / arg).is_file():
                    self.args[i] = str((self.base_dir / arg).resolve())

    def identity(self) -> dict:
        return {
            "config": self.config.model_dump(),
            "source_sha256": self.sources,
            "resolved_command": self.args,
            "sha256": digest(
                {"config": self.config.model_dump(), "sources": self.sources, "command": self.args}
            ),
        }

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        started = time.monotonic()
        try:
            for filename, sha in self.sources.items():
                if digest(Path(filename).read_text(encoding="utf-8")) != sha:
                    raise ValueError("Runner source changed during the experiment")
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
