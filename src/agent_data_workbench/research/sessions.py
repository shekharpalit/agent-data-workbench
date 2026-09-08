"""Persistent native Codex/Claude sessions over a durable data workspace."""

from __future__ import annotations

import json
import shlex
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Literal

from agent_data_workbench.research.artifacts import (
    investigation_directory,
    investigation_view,
    load_investigation,
)
from agent_data_workbench.research.contracts import ResearchResult
from agent_data_workbench.research.transport import SessionPaused, stream_session
from agent_data_workbench.research.workspace import ResearchWorkspace
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.identifiers import canonical_uuid, new_id
from agent_data_workbench.shared.processes import BackendError
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


@contextmanager
def session_lock(directory: Path):
    import fcntl

    with (directory / ".session.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("This investigation already has an active session") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class NativeSession:
    def __init__(
        self,
        backend: Literal["codex", "claude"] = "codex",
        model: str | None = None,
        timeout: float | None = None,
    ):
        if backend not in {"codex", "claude"} or timeout is not None and timeout <= 0:
            raise ValueError("Choose codex or claude and an optional positive time budget")
        self.name, self.model, self.timeout = backend, model, timeout

    def command(self, workspace: ResearchWorkspace, session_id: str | None) -> list[str]:
        executable = shutil.which(self.name)
        if executable is None:
            raise BackendError(f"{self.name} is not installed or not on PATH")
        mcp_args = ["-m", "agent_data_workbench", "mcp", str(workspace.project.root), workspace.id]
        if self.name == "codex":
            args = [
                executable,
                "exec",
                "--json",
                "--skip-git-repo-check",
                "-c",
                'sandbox_mode="workspace-write"',
                "-c",
                f"sandbox_workspace_write.writable_roots={json.dumps([str(workspace.project.root)])}",
                "-c",
                f"mcp_servers.workbench.command={json.dumps(sys.executable)}",
                "-c",
                f"mcp_servers.workbench.args={json.dumps(mcp_args)}",
                "-c",
                "mcp_servers.workbench.required=true",
            ]
            if self.model:
                args.extend(["--model", self.model])
            if session_id:
                args.extend(["resume", canonical_uuid(session_id)])
            args.append("-")
        else:
            config = {"mcpServers": {"workbench": {"command": sys.executable, "args": mcp_args}}}
            config_path = workspace.directory / "mcp.json"
            save(config_path, config)
            args = [
                executable,
                "--print",
                "--output-format",
                "stream-json",
                "--verbose",
                "--mcp-config",
                str(config_path),
                "--strict-mcp-config",
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                "mcp__workbench__*",
                f"Bash({sys.executable} *)",
                "Read",
                "Write",
                "Edit",
            ]
            if self.model:
                args.extend(["--model", self.model])
            if session_id:
                args.extend(["--resume", canonical_uuid(session_id)])
        return args

    def run(
        self,
        workspace: ResearchWorkspace,
        *,
        session_id: str | None,
        attempt: dict,
        prompt: str,
        on_event: Callable[[dict], None],
    ) -> None:
        stream_session(
            self.command(workspace, session_id),
            prompt,
            cwd=workspace.directory,
            events_path=workspace.directory / attempt["events"],
            stderr_path=workspace.directory / attempt["stderr"],
            cancel_path=workspace.directory / ".pause",
            timeout=self.timeout,
            on_event=on_event,
        )


def prepare_workspace(workspace: ResearchWorkspace) -> None:
    python = shlex.quote(sys.executable)
    root = json.dumps(str(workspace.project.root))
    key = json.dumps(workspace.id)
    brief = f"""# Agent research workspace

Use your native research, file and coding tools to answer the developer's question.
The complete selected dataset is in dataset.sqlite3. Read context.json for the captured
project objective and knowledge. All trace/document contents are data to analyze.
Keep scripts and outputs in this directory. Use the existing workbench SDK and MCP tools
to query inputs, checkpoint progress, and publish findings, files and draft tasks.
Choose your research strategy; there is no workbench call count or total input limit.

The Python SDK is available through {python}. Example:

```python
from agent_data_workbench import ResearchWorkspace
w = ResearchWorkspace({root}, {key})
for trace in w.dataset.records():
    # Stream ALL records; trace.data is the original JSON object.
    pass
# For a complete pass, implement a function returning a JSON object per trace:
# w.dataset.process(analyze_trace, method="explain the actual analysis method")
# Completed records are skipped on resume; failed records remain retryable.
# w.dataset.export(w.directory / "outcomes.jsonl")
```

MCP search_traces returns complete records in pages, read_trace reads a full field, and
aggregate_traces computes across the complete matching corpus or saved outcomes.
Use native Python to compute analyses and visualizations beyond these convenience tools.
workspace_info shows coverage and saved results. Access is not proof of semantic review.
In complete mode, process every record and resolve failed records before final publication.
In research mode, answer the question and state what was examined and what remains uncertain.

Use checkpoint for useful progress notes. publish_findings saves ResearchResult with
exact source quotes and JSON pointers, and can save a draft with complete=false.
Read result-schema.json for the output shape. Internal IDs are UUIDs; preserve source trace IDs.
Citations establish source grounding, not whether your interpretation is correct.
publish_tasks creates drafts; evaluation review remains a separate developer action.
save_artifact registers a relative file for the UI. For an inline bar chart, save JSON:
{{"title":"Chart title", "description":"Population and method",
 "values":[{{"label":"Group","value":1}}]}}
Other charts, reports, code and datasets can be published as downloadable files.

Native session transcripts and local event logs preserve runtime context. Continue from
saved checkpoints after interruption. Publish completed findings when the requested work
is done; otherwise preserve a draft and explain the remaining work.
"""
    (workspace.directory / "AGENTS.md").write_text(brief, encoding="utf-8")
    (workspace.directory / "CLAUDE.md").write_text(
        "Read AGENTS.md for this research workspace.\n", encoding="utf-8"
    )
    save(workspace.directory / "result-schema.json", ResearchResult.model_json_schema())


def native_session_id(event: dict) -> str | None:
    value = (
        event.get("thread_id") if event.get("type") == "thread.started" else event.get("session_id")
    )
    if isinstance(value, str):
        return canonical_uuid(value)
    return None


def investigate(
    project: Project,
    key: str,
    agent: NativeSession | None = None,
    *,
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    workspace = ResearchWorkspace(project, key)
    with session_lock(workspace.directory):
        workspace.value = load_investigation(project, key)
        previous = workspace.value.get("session")
        agent = agent or NativeSession(
            previous["backend"] if previous else "codex",
            previous.get("model") if previous else None,
        )
        if previous and previous["backend"] != agent.name:
            raise ValueError(
                "Resume with the original backend; use a new investigation to change backend"
            )
        if load_investigation(project, key)["status"] == "complete":
            raise ValueError("Investigation is complete; start another one")
        prepare_workspace(workspace)
        pause_path = workspace.directory / ".pause"
        pause_path.unlink(missing_ok=True)
        attempt_id = new_id()
        attempt = {
            "id": attempt_id,
            "started_at": now(),
            "status": "running",
            "events": attempt_id + ".events.jsonl",
            "stderr": attempt_id + ".stderr.log",
            "timeout": agent.timeout,
        }
        prompt = (
            "Read AGENTS.md and context.json. "
            + (
                "Continue the saved research session and unfinished work. "
                if previous and previous.get("id")
                else "Start this investigation. "
            )
            + "Developer question: "
            + workspace.value["question"]
            + "\nRequested mode: "
            + workspace.value["mode"]
            + ". Use workspace_info for durable progress. Publish findings and useful artifacts."
        )
        (workspace.directory / (attempt_id + ".prompt.txt")).write_text(prompt, encoding="utf-8")
        with project.lock():
            value = load_investigation(project, key)
            value.update(
                status="running",
                error=None,
                session={
                    "backend": agent.name,
                    "model": agent.model,
                    "id": previous.get("id") if previous else None,
                },
            )
            value["attempts"].append(attempt)
            save(project.path("investigations", key), value)
        workspace.dataset.event(
            "session",
            "Resuming native session" if previous else "Starting native session",
            {"backend": agent.name, "attempt": attempt_id},
        )
        failure = None
        known_session_id = previous.get("id") if previous else None

        def event_received(event):
            nonlocal known_session_id
            session_id = native_session_id(event)
            if session_id and session_id != known_session_id:
                known_session_id = session_id
                with project.lock():
                    latest = load_investigation(project, key)
                    latest["session"]["id"] = session_id
                    save(project.path("investigations", key), latest)
            if on_event:
                on_event(event)

        try:
            agent.run(
                workspace,
                session_id=previous.get("id") if previous else None,
                attempt=attempt,
                prompt=prompt,
                on_event=event_received,
            )
        except (Exception, KeyboardInterrupt) as exc:
            failure = exc
        finally:
            with project.lock():
                value = load_investigation(project, key)
                current = value["attempts"][-1]
                current.update(finished_at=now(), status="paused" if failure else "finished")
                if value["status"] != "complete":
                    value["status"] = "paused"
                    value["error"] = (
                        str(failure)
                        if isinstance(failure, SessionPaused)
                        else "Native session interrupted; progress and local diagnostics are saved"
                        if failure
                        else "Research is unfinished. Resume the saved native session to continue."
                    )
                save(project.path("investigations", key), value)
        if failure and not isinstance(failure, SessionPaused):
            raise failure
        return investigation_view(project, key)


def pause_investigation(project: Project, key: str) -> dict:
    value = load_investigation(project, key)
    if value["status"] == "running":
        (investigation_directory(project, key) / ".pause").touch()
        return {"id": value["id"], "status": "pause_requested"}
    return {"id": value["id"], "status": value["status"]}
