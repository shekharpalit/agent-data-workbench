"""Reproducible trusted environment commands and independent observer evidence.

Commands execute with host access. Directory separation establishes evidence ownership,
not a sandbox; the configured observer must inspect the authoritative service/state.
"""

from __future__ import annotations

import copy
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from .backends import run_process
from .command_sources import check_sources, pinned_command
from .identifiers import new_id
from .models import Contract, json_text
from .project import digest, save

if TYPE_CHECKING:
    from .runners import Execution, TargetRunner


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


class EnvironmentRunner:
    def __init__(self, target: TargetRunner, config: EnvironmentConfig, base_dir: Path):
        self.target = target
        self.config = config.model_copy(deep=True)
        self.commands = {}
        self.sources = {}
        for phase in ("setup", "reset", "ready", "inspect", "teardown"):
            args, sources = pinned_command(getattr(config, phase), config.source_files, base_dir)
            self.commands[phase] = args
            self.sources.update(sources)
        self._evidence: dict[str, dict] = {}
        self._observations: dict[str, dict] = {}

    def environment_identity(self) -> dict:
        value = {
            "config": self.config.model_dump(),
            "commands": self.commands,
            "source_sha256": self.sources,
        }
        return {**value, "sha256": digest(value)}

    def identity(self) -> dict:
        return {"target": self.target.identity(), "environment": self.environment_identity()}

    def authoritative_artifacts(self, trial_dir: Path) -> dict:
        """Never read target-returned usage or files to reconstruct trusted evidence."""
        return copy.deepcopy(self._observations.get(str(trial_dir.resolve()), {}))

    def trial_evidence(self, trial_dir: Path) -> dict:
        return copy.deepcopy(self._evidence.get(str(trial_dir.resolve()), {}))

    def run(self, visible_input: dict, trial_dir: Path, seed: int) -> Execution:
        from .runners import Execution
        from .tasks import parse_object, relative_path

        started = time.monotonic()
        key = str(trial_dir.resolve())
        self._observations.pop(key, None)
        self._evidence.pop(key, None)
        observer_dir = trial_dir.parent / (new_id() + "-environment")
        observer_dir.mkdir(mode=0o700)
        phases = []
        result = Execution(status="runner_error", error="Environment did not start")
        initial_state = None
        final_state = None
        target_context = {}
        current_phase = "setup"

        def phase(name: str, *, moment: str | None = None):
            check_sources(self.sources)
            entry = {"phase": name, "moment": moment, "status": "running", "output": None}
            phases.append(entry)
            save(observer_dir / "lifecycle.json", {"phases": phases})
            request = {
                "phase": name,
                "moment": moment,
                "seed": seed,
                "trial_dir": str(trial_dir.resolve()),
                "state_dir": str(observer_dir),
                "input": visible_input,
            }
            try:
                raw = run_process(
                    self.commands[name], json_text(request), observer_dir, self.config.timeout
                )
                output = parse_object(raw)
                check_sources(self.sources)
                entry.update(status="completed", output=output)
                return output
            except RuntimeError, ValueError, OSError:
                entry["status"] = "error"
                raise
            finally:
                save(observer_dir / "lifecycle.json", {"phases": phases})

        def observe(moment: str):
            observation = Observation.model_validate(phase("inspect", moment=moment))
            for name in observation.artifacts:
                relative_path(name)
            return observation.artifacts

        try:
            setup = phase("setup")
            target_context = setup.get("target_context", {})
            if not isinstance(target_context, dict):
                raise ValueError("Setup target_context must be an object")
            current_phase = "reset"
            if phase("reset").get("reset") is not True:
                raise ValueError("Reset command must affirm a successful reset")
            current_phase = "ready"
            if phase("ready").get("ready") is not True:
                raise ValueError("Environment is not ready")
            current_phase = "inspect_initial"
            initial_state = observe("initial")
            if (
                self.config.initial_state_sha256 is not None
                and digest(initial_state) != self.config.initial_state_sha256
            ):
                raise ValueError("Reset state differs from the reviewed initial state")
            current_phase = "target"
            if "environment_context" in visible_input:
                raise ValueError("environment_context is reserved for environment setup")
            result = self.target.run(
                {**visible_input, "environment_context": target_context}, trial_dir, seed
            )
            current_phase = "inspect_final"
            final_state = observe("final")
            self._observations[key] = copy.deepcopy(final_state)
        except (RuntimeError, ValueError, OSError) as exc:
            result.status = "timeout" if "timed out" in str(exc) else "runner_error"
            result.error = (
                f"Environment lifecycle failed during {current_phase}; inspect its record"
            )
        finally:
            if self.commands["teardown"]:
                try:
                    phase("teardown")
                except RuntimeError, ValueError, OSError:
                    result.status = "runner_error"
                    result.error = "Environment teardown failed; inspect its lifecycle record"
            evidence_dir = trial_dir / (new_id() + "-environment-evidence")
            shutil.move(str(observer_dir), evidence_dir)
            record = {
                "identity": self.environment_identity(),
                "phases": phases,
                "initial_state": initial_state,
                "final_state": final_state,
                "initial_state_sha256": digest(initial_state)
                if initial_state is not None
                else None,
                "final_state_sha256": digest(final_state) if final_state is not None else None,
                "status": result.status,
                "observer_directory": str(evidence_dir),
                "evidence_source": "configured_authoritative_observer",
                "isolation": "trusted_host_commands",
            }
            self._evidence[key] = copy.deepcopy(record)
            save(evidence_dir / "lifecycle.json", record)
            save(trial_dir / "environment.json", record)
            result.latency_seconds = time.monotonic() - started
        return result
