"""Developer-supplied reactive user commands with pinned source identities."""

from __future__ import annotations

from pathlib import Path

from agent_data_workbench.execution.contracts import SimulatorConfig, UserTurn
from agent_data_workbench.shared.commands import check_sources, pinned_command
from agent_data_workbench.shared.json import json_text


class CommandUserSimulator:
    """A user-provided simulator command receives only the visible conversation."""

    def __init__(self, config: SimulatorConfig, base_dir: Path, cwd: Path):
        self.config = config
        self.args, self.sources = pinned_command(config.command, config.source_files, base_dir)
        self.cwd = cwd

    def identity(self):
        return {"config": self.config.model_dump(), "sources": self.sources, "command": self.args}

    def next_turn(self, interaction: list[dict]) -> UserTurn | None:
        from agent_data_workbench.shared.json import parse_object
        from agent_data_workbench.shared.processes import run_process

        check_sources(self.sources)
        raw = run_process(
            self.args, json_text({"interaction": interaction}), self.cwd, self.config.timeout
        )
        check_sources(self.sources)
        response = parse_object(raw)
        if response.get("message") is None:
            return None
        return UserTurn(message=response["message"])
