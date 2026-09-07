"""Official local CLI adapters; no credential extraction or provider fallback."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal, Protocol


class Analyzer(Protocol):
    name: str

    def analyze(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class BackendError(RuntimeError):
    pass


def structured_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Provider strict output requires every declared field, including nullable defaults."""
    import copy

    result = copy.deepcopy(schema)

    def visit(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object" and "properties" in value:
                value["required"] = list(value["properties"])
                value["additionalProperties"] = False
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    return result


def run_process(args: list[str], prompt: str, cwd: Path, timeout: int) -> str:
    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(input=prompt, timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise BackendError(
            f"Analyzer timed out after {timeout}s; no fallback was attempted"
        ) from exc
    if process.returncode:
        # Do not echo provider stderr: it can contain private trace content or account details.
        raise BackendError(
            f"{Path(args[0]).name} exited with code {process.returncode}. "
            "Check its login and account limits directly; no fallback was attempted."
        )
    return stdout


class CliAnalyzer:
    def __init__(
        self, backend: Literal["codex", "claude"], model: str | None = None, timeout: int = 300
    ):
        if backend not in {"codex", "claude"}:
            raise ValueError("Backend must be codex or claude")
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        self.name = backend
        self.model = model
        self.timeout = timeout

    def analyze(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        schema = structured_schema(schema)
        executable = shutil.which(self.name)
        if executable is None:
            raise BackendError(f"{self.name} is not installed or not on PATH")
        with tempfile.TemporaryDirectory(prefix="agent-data-workbench-") as directory:
            cwd = Path(directory)
            if self.name == "codex":
                schema_path = cwd / "schema.json"
                result_path = cwd / "result.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                args = [
                    executable,
                    "exec",
                    "--ignore-user-config",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--color",
                    "never",
                    "-c",
                    "features.shell_tool=false",
                    "-c",
                    'web_search="disabled"',
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(result_path),
                ]
                if self.model:
                    args.extend(["--model", self.model])
                args.append("-")
                run_process(args, prompt, cwd, self.timeout)
                if not result_path.is_file():
                    raise BackendError("Codex returned no structured result")
                response = result_path.read_text(encoding="utf-8")
            else:
                args = [
                    executable,
                    "--safe-mode",
                    "--print",
                    "--output-format",
                    "json",
                    "--json-schema",
                    json.dumps(schema),
                    "--tools",
                    "",
                    "--strict-mcp-config",
                    "--mcp-config",
                    '{"mcpServers":{}}',
                    "--disable-slash-commands",
                    "--no-session-persistence",
                    "--permission-mode",
                    "dontAsk",
                ]
                if self.model:
                    args.extend(["--model", self.model])
                raw = run_process(args, prompt, cwd, self.timeout)
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise BackendError("Claude returned invalid JSON") from exc
                if not isinstance(envelope, dict) or envelope.get("is_error"):
                    raise BackendError(
                        "Claude did not complete successfully; check its login/limits"
                    )
                result = envelope.get("structured_output")
                if not isinstance(result, dict):
                    raise BackendError("Claude returned no structured_output object")
                return result
            try:
                result = json.loads(response)
            except json.JSONDecodeError as exc:
                raise BackendError("Codex returned invalid JSON") from exc
            if not isinstance(result, dict):
                raise BackendError("Codex returned a non-object result")
            return result
