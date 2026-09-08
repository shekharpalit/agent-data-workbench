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


def _environment(config: HarborExportConfig) -> dict[str, str]:
    # Harbor 0.22 scrubs AUTH-named --ae values from every result file. Passing
    # this nonsecret boolean as --ae would replace every digit 1 in JSON/logs.
    # The official Codex adapter also reads the child process environment.
    return {"CODEX_FORCE_AUTH_JSON": "1"} if config.use_host_codex_login else {}
