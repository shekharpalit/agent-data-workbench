"""Native-session integration and full-corpus coverage without provider credentials."""

import asyncio
import json
import sys

import pytest
from identities import uid
from test_workbench_data import NativeFixture, Source, make_project, result, spec
from typer.testing import CliRunner

from agent_data_workbench.backends import BackendError
from agent_data_workbench.cli import app
from agent_data_workbench.project import Project, save
from agent_data_workbench.research import (
    NativeSession,
    ResearchWorkspace,
    investigate,
    start_investigation,
)
from agent_data_workbench.research.artifacts import investigation_view
from agent_data_workbench.research.sessions import session_lock
from agent_data_workbench.store import JsonSource, TraceStore
from agent_data_workbench.tasks import load_task
from agent_data_workbench.workflow import load_request, prepare_run


@pytest.fixture
def workspace(tmp_path):
    project = make_project(tmp_path)
    value = start_investigation(project, "Find evidence", mode="complete")
    return ResearchWorkspace(project, value["id"])


def test_complete_pass_checkpoints_every_record_and_retries_only_unfinished(workspace):
    # Given: a callback interrupted after two successful records and one failure.
    called = []

    def interrupted(trace):
        called.append(trace.trace_id)
        if trace.trace_id == "r2":
            raise ValueError("Retry this record")
        if trace.trace_id == "r3":
            raise KeyboardInterrupt()
        return {"observed": trace.data["value"]}

    # When
    with pytest.raises(KeyboardInterrupt):
        workspace.dataset.process(interrupted, method="Observed numeric field", page_size=2)
    before = workspace.dataset.coverage()
    with pytest.raises(ValueError, match="pending or failed"):
        workspace.publish(result())
    reopened = ResearchWorkspace(workspace.project, workspace.id)
    retried = []

    def finish(trace):
        retried.append(trace.trace_id)
        return {"observed": trace.data["value"]}

    resumed = reopened.dataset.process(finish, method="Observed numeric field", page_size=2)
    published = reopened.publish(result())
    # Then
    assert {
        "called": called,
        "before": before,
        "retried": retried,
        "resumed": resumed,
        "published": published,
    } == {
        "called": ["r0", "r1", "r2", "r3"],
        "before": {"total": 9, "retrieved": 4, "completed": 2, "failed": 1, "pending": 6},
        "retried": [f"r{i}" for i in range(2, 9)],
        "resumed": {"total": 9, "retrieved": 9, "completed": 9, "failed": 0, "pending": 0},
        "published": {"id": workspace.id, "status": "complete", "coverage": resumed},
    }
    with pytest.raises(ValueError, match="Published outcomes"):
        reopened.dataset.record("r0", error="changed", method="later")
    assert reopened.info()["coverage"] == resumed


def test_snapshot_matches_inventory_and_processes_beyond_page_boundaries(tmp_path):
    # Given: substantially more than the previous 100-record default.
    project = Project.create(tmp_path / "project", "Coverage", "All records")
    source = Source([{"trace_id": f"r{i:04}", "value": i, "flag": i % 2 == 0} for i in range(257)])
    inventory = TraceStore(project).ingest(source)
    value = start_investigation(project, "Count", mode="complete")
    workspace = ResearchWorkspace(project, value["id"])
    # When
    coverage = workspace.dataset.process(
        lambda t: {"flag": t.data["flag"]}, method="Read flag", page_size=17
    )
    summary = workspace.dataset.aggregate("/flag", results=True)
    out = workspace.dataset.export(tmp_path / "outcomes.jsonl")
    batch = prepare_run(list(source.read()), tmp_path / "batch")
    # Then
    assert {
        "snapshot": value["source"],
        "coverage": coverage,
        "summary": summary,
        "exported": out["records"],
        "batch_selected": load_request(batch)[0]["selected_traces"],
    } == {
        "snapshot": {k: inventory[k] for k in ("total", "strata", "sha256", "excluded_groups")},
        "coverage": {"total": 257, "retrieved": 257, "completed": 257, "failed": 0, "pending": 0},
        "summary": {
            "pointer": "/flag",
            "source": "outcomes",
            "eligible": 257,
            "missing_or_non_scalar": 0,
            "distinct": 2,
            "counts": [{"value": True, "count": 129}, {"value": False, "count": 128}],
            "next_offset": None,
            "numeric_count": 0,
            "mean": None,
            "minimum": None,
            "maximum": None,
        },
        "exported": 257,
        "batch_selected": 257,
    }


def test_large_record_is_preserved_and_can_be_read_without_truncation(workspace, tmp_path):
    # Given
    text = "x" * 2_000_001
    path = tmp_path / "large.jsonl"
    path.write_text(json.dumps({"trace_id": "large", "text": text}) + "\n")
    # When
    TraceStore(workspace.project).ingest(JsonSource(path))
    value = start_investigation(workspace.project, "Read the full input")
    large = ResearchWorkspace(workspace.project, value["id"])
    first = large.read("large", pointer="/text", max_chars=23)
    rest = large.read("large", pointer="/text", offset=first["next_offset"], max_chars=None)
    # Then
    assert {
        "joined": first["content"] + rest["content"],
        "total": rest["total_chars"],
        "next": rest["next_offset"],
    } == {"joined": text, "total": len(text), "next": None}


def test_artifacts_and_tasks_retain_snapshot_lineage(workspace):
    # Given
    chart = {
        "title": "Outcomes",
        "description": "Synthetic counts",
        "values": [{"label": "Failed", "value": 2}],
    }
    save(workspace.directory / "chart.json", chart)
    task = spec(workspace.project, trace_ids=["r8"])
    # When
    workspace.publish(result(), complete=False)
    artifact = workspace.attach("chart.json", "Outcomes", "chart")
    path, checked = workspace.artifact_path(artifact["id"])
    published = workspace.publish_tasks([task])
    # Then
    assert {
        "chart": checked["chart"],
        "file": json.loads(path.read_text()),
        "tasks": published,
        "review": load_task(workspace.project, task.id)[0]["review"]["status"],
    } == {
        "chart": chart,
        "file": chart,
        "tasks": {"task_ids": [task.id], "review": "draft"},
        "review": "draft",
    }
    # When / Then: the published copy is independent, but changes to that copy are detected.
    save(workspace.directory / "chart.json", {})
    assert json.loads(workspace.artifact_path(artifact["id"])[0].read_text()) == chart
    path.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        workspace.artifact_path(artifact["id"])
    with pytest.raises(ValueError):
        workspace.attach("../project.json", "Outside")


def test_active_lock_detects_live_sessions_and_allows_crash_recovery(workspace):
    # Given
    value = workspace.value | {"status": "running"}
    save(workspace.project.path("investigations", workspace.id), value)
    # When
    with session_lock(workspace.directory):
        active = investigation_view(workspace.project, workspace.id)["active"]
        with pytest.raises(ValueError, match="active session"):
            investigate(workspace.project, workspace.id, NativeFixture(lambda w: None))
    stopped = investigation_view(workspace.project, workspace.id)["active"]
    resumed = investigate(
        workspace.project, workspace.id, NativeFixture(lambda w: w.checkpoint("Recovered"))
    )
    # Then
    assert {"active": active, "stopped": stopped, "status": resumed["status"]} == {
        "active": True,
        "stopped": False,
        "status": "paused",
    }


@pytest.mark.parametrize("backend", ["codex", "claude"])
def test_native_commands_keep_tools_auth_and_persistent_resume(workspace, monkeypatch, backend):
    # Given
    monkeypatch.setattr(
        "agent_data_workbench.research.sessions.shutil.which", lambda name: f"/installed/{name}"
    )
    agent = NativeSession(backend, model="chosen")
    session = uid("native")
    # When
    command = agent.command(workspace, session)
    # Then
    assert {
        "executable": command[0],
        "resume": command[command.index("resume" if backend == "codex" else "--resume") + 1],
        "model": command[command.index("--model") + 1],
        "disabled": [
            x
            for x in command
            if x
            in {
                "--bare",
                "--safe-mode",
                "--ephemeral",
                "--no-session-persistence",
                "--dangerously-bypass-approvals-and-sandbox",
            }
        ],
        "default_timeout": agent.timeout,
    } == {
        "executable": f"/installed/{backend}",
        "resume": session,
        "model": "chosen",
        "disabled": [],
        "default_timeout": None,
    }
    if backend == "codex":
        mcp_args = ["-m", "agent_data_workbench", "mcp", str(workspace.project.root), workspace.id]
        config = [command[i + 1] for i, x in enumerate(command) if x == "-c"]
        assert config == [
            'sandbox_mode="workspace-write"',
            f"sandbox_workspace_write.writable_roots={json.dumps([str(workspace.project.root)])}",
            f"mcp_servers.workbench.command={json.dumps(sys.executable)}",
            f"mcp_servers.workbench.args={json.dumps(mcp_args)}",
            "mcp_servers.workbench.required=true",
        ]
    else:
        assert json.loads((workspace.directory / "mcp.json").read_text()) == {
            "mcpServers": {
                "workbench": {
                    "command": sys.executable,
                    "args": [
                        "-m",
                        "agent_data_workbench",
                        "mcp",
                        str(workspace.project.root),
                        workspace.id,
                    ],
                }
            }
        }


@pytest.mark.parametrize("ending", ["cancel", "timeout", "exit", "terminal_error"])
def test_native_process_logs_session_before_interruption(workspace, monkeypatch, ending):
    # Given: a real local subprocess producing native CLI-shaped events.
    session = uid("native-subprocess")
    initial_event = {"type": "thread.started", "thread_id": session}
    body = "import sys,json,time; sys.stdin.read(); "
    body += f"print({json.dumps(initial_event)!r}, flush=True); "
    if ending in {"cancel", "timeout"}:
        body += "time.sleep(30)"
    elif ending == "exit":
        body += "sys.exit(7)"
    else:
        error_event = {"type": "turn.failed", "error": {"message": "private error"}}
        body += f"print({json.dumps(error_event)!r}, flush=True)"
    agent = NativeSession(timeout=0.5 if ending == "timeout" else None)
    monkeypatch.setattr(agent, "command", lambda w, s: [sys.executable, "-c", body])

    def event(event):
        if ending == "cancel":
            (workspace.directory / ".pause").touch()

    # When
    if ending in {"exit", "terminal_error"}:
        with pytest.raises(BackendError):
            investigate(workspace.project, workspace.id, agent, on_event=event)
    else:
        investigate(workspace.project, workspace.id, agent, on_event=event)
    saved = investigation_view(workspace.project, workspace.id)
    events = [
        json.loads(s)
        for s in (workspace.directory / saved["attempts"][0]["events"]).read_text().splitlines()
    ]
    # Then
    assert {
        "status": saved["status"],
        "session": saved["session"]["id"],
        "active": saved["active"],
        "first_event": events[0],
        "private_error_exposed": "private error" in saved["error"],
    } == {
        "status": "paused",
        "session": session,
        "active": False,
        "first_event": {"type": "thread.started", "thread_id": session},
        "private_error_exposed": False,
    }


def test_official_mcp_stdio_exposes_the_same_workspace_and_recovers_from_bad_calls(workspace):
    # Given
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def exercise():
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent_data_workbench", "mcp", str(workspace.project.root), workspace.id],
        )
        async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            invalid = await session.call_tool("read_trace", {"trace_id": "absent"})
            read = await session.call_tool("read_trace", {"trace_id": "r0", "pointer": "/text"})
            recorded = await session.call_tool(
                "record_outcomes",
                {
                    "outcomes": [
                        {
                            "trace_id": "r0",
                            "output": {"label": "observed"},
                            "method": "test fixture",
                        }
                    ]
                },
            )
            await session.call_tool("checkpoint", {"note": "MCP progress"})
            draft = await session.call_tool(
                "publish_findings", {"result": result(), "complete": False}
            )
            return {
                "tools": sorted(t.name for t in tools.tools),
                "invalid": invalid.is_error,
                "read": read.structured_content,
                "recorded": recorded.structured_content,
                "draft": draft.structured_content,
            }

    # When
    actual = asyncio.run(exercise())
    # Then
    coverage = {"total": 9, "retrieved": 1, "completed": 1, "failed": 0, "pending": 8}
    assert actual == {
        "tools": sorted(
            [
                "workspace_info",
                "search_traces",
                "read_trace",
                "aggregate_traces",
                "read_context",
                "checkpoint",
                "record_outcomes",
                "publish_findings",
                "publish_tasks",
                "save_artifact",
            ]
        ),
        "invalid": True,
        "read": {
            "trace_id": "r0",
            "pointer": "/text",
            "content": "actual result",
            "offset": 0,
            "total_chars": 13,
            "next_offset": None,
        },
        "recorded": coverage,
        "draft": {"id": workspace.id, "status": "paused", "coverage": coverage},
    }


def test_cli_workspace_can_process_publish_and_export_without_analyzer(tmp_path):
    # Given
    project = make_project(tmp_path)
    cli = CliRunner()
    # When
    created = cli.invoke(
        app, ["research", "create", str(project.root), "Find evidence", "--mode", "complete"]
    )
    value = json.loads(created.output)
    workspace = ResearchWorkspace(project, value["id"])
    workspace.dataset.process(lambda t: {"value": t.data["value"]}, method="Read original value")
    response = tmp_path / "result.json"
    save(response, result())
    published = cli.invoke(
        app, ["research", "publish", str(project.root), workspace.id, str(response)]
    )
    exported = cli.invoke(
        app,
        ["research", "export", str(project.root), workspace.id, str(tmp_path / "outcomes.jsonl")],
    )
    # Then
    assert {
        "exit_codes": [created.exit_code, published.exit_code, exported.exit_code],
        "status": json.loads(published.output)["status"],
        "records": json.loads(exported.output)["records"],
        "instructions": [p.name for p in workspace.directory.glob("*.md")],
    } == {
        "exit_codes": [0, 0, 0],
        "status": "complete",
        "records": 9,
        "instructions": ["AGENTS.md", "CLAUDE.md"],
    }


@pytest.mark.parametrize("revise", [False, True])
def test_large_knowledge_file_reaches_native_context_intact(tmp_path, revise):
    # Given
    project = make_project(tmp_path)
    text = "Policy content\n" * 10_000
    path = tmp_path / "policy.md"
    path.write_text(text)
    cli = CliRunner()
    # When
    added = cli.invoke(app, ["knowledge", "add", str(project.root), str(path), "Policy"])
    knowledge = json.loads(added.output)
    expected = text + "Revised" if revise else text
    project.review_knowledge(
        knowledge["id"], "accepted", "Reviewed policy", content=expected if revise else None
    )
    value = start_investigation(project, "Apply the whole policy")
    # Then
    assert {"exit": added.exit_code, "content": value["context"]["knowledge"][0]["content"]} == {
        "exit": 0,
        "content": expected,
    }
