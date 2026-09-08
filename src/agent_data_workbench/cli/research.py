"""Native investigation sessions and explicit workspace operations."""

from pathlib import Path

import typer

from agent_data_workbench.cli.common import emit, errors
from agent_data_workbench.research import (
    NativeSession,
    ResearchWorkspace,
    investigate,
    pause_investigation,
    start_investigation,
)
from agent_data_workbench.research.artifacts import investigation_view, load_investigation
from agent_data_workbench.research.sessions import prepare_workspace
from agent_data_workbench.shared.json import read_json
from agent_data_workbench.workspace.project import Project

app = typer.Typer(no_args_is_help=True)
operations = typer.Typer(no_args_is_help=True)


@app.command("investigate")
@errors
def investigate_command(
    project: Path,
    question: str = "What should we improve next?",
    backend: str | None = None,
    model: str | None = None,
    mode: str = "research",
    exclude_final: bool = False,
    timeout: float | None = None,
    resume: str = "",
):
    """Run one native coding-agent session; resume it explicitly after interruption."""
    p = Project(project)
    value = (
        load_investigation(p, resume)
        if resume
        else start_investigation(p, question, mode=mode, exclude_final=exclude_final)
    )
    previous = value.get("session") or {}
    selected = backend or previous.get("backend", "codex")
    agent = NativeSession(selected, model or previous.get("model"), timeout)
    typer.echo(f"Investigation: {value['id']}. Using {selected}'s native session and account.")
    completed = investigate(p, value["id"], agent)
    emit({k: completed.get(k) for k in ("id", "status", "session", "coverage", "error")})
    if completed["status"] != "complete":
        typer.echo(f"Continue with --resume {value['id']}")


@app.command("mcp")
@errors
def mcp_server(project: Path, investigation: str):
    """Expose this investigation's data tools over local MCP stdio; no model call."""
    from agent_data_workbench.research.mcp import create_mcp

    create_mcp(ResearchWorkspace(project, investigation)).run()


@operations.command("create")
@errors
def create(project: Path, question: str, mode: str = "research", exclude_final: bool = False):
    """Prepare a data workspace to use from an existing coding-agent session."""
    p = Project(project)
    value = start_investigation(p, question, mode=mode, exclude_final=exclude_final)
    workspace = ResearchWorkspace(p, value["id"])
    prepare_workspace(workspace)
    emit(
        {
            "id": workspace.id,
            "workspace": str(workspace.directory),
            "mode": mode,
            "mcp": ["agent-data-workbench", "mcp", str(p.root), workspace.id],
        }
    )


@operations.command("info")
@errors
def info(project: Path, investigation: str):
    emit(investigation_view(Project(project), investigation))


@operations.command("records")
@errors
def records(
    project: Path,
    investigation: str,
    after: str | None = None,
    page_size: int = 100,
    pending_only: bool = False,
):
    workspace = ResearchWorkspace(project, investigation)
    rows = workspace.dataset.rows(after=after, page_size=page_size, pending_only=pending_only)
    emit({"records": rows, "next_cursor": rows[-1]["trace_id"] if len(rows) == page_size else None})


@operations.command("record")
@errors
def record(project: Path, investigation: str, outcomes: Path):
    from agent_data_workbench.research.workspace import RecordOutcome

    workspace = ResearchWorkspace(project, investigation)
    emit(workspace.record_outcomes([RecordOutcome.model_validate(v) for v in read_json(outcomes)]))


@operations.command("publish")
@errors
def publish(project: Path, investigation: str, result: Path, draft: bool = False):
    emit(ResearchWorkspace(project, investigation).publish(read_json(result), complete=not draft))


@operations.command("attach")
@errors
def attach(project: Path, investigation: str, path: str, title: str, kind: str = "other"):
    emit(ResearchWorkspace(project, investigation).attach(path, title, kind))


@operations.command("export")
@errors
def export(project: Path, investigation: str, out: Path):
    emit(ResearchWorkspace(project, investigation).dataset.export(out))


@operations.command("pause")
@errors
def pause(project: Path, investigation: str):
    emit(pause_investigation(Project(project), investigation))
