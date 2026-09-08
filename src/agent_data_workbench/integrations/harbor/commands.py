"""Translate captured configuration to the official Harbor CLI."""

import json
from pathlib import Path

from .contracts import HarborExportConfig


def _command(
    bundle: Path, config: HarborExportConfig, job_name: str, conversation: bool
) -> list[str]:
    command = [
        "harbor",
        "run",
        "--path",
        str(bundle),
        "--agent",
        config.agent,
        "-e",
        config.environment_type,
        "--n-attempts",
        str(config.repetitions),
        "--jobs-dir",
        str(bundle.parent / "jobs"),
        "--job-name",
        job_name,
    ]
    if config.model:
        command.extend(["--model", config.model])
    for key, value in sorted(config.agent_kwargs.items()):
        command.extend(["--ak", f"{key}={json.dumps(value)}"])
    if conversation:
        command.append("--resume-trajectory")
    return command
