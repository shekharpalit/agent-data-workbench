"""Official MCP transport for the same data workspace exposed by the Python SDK."""

from functools import wraps
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from agent_data_workbench.evaluation.tasks.contracts import TaskSpec
from agent_data_workbench.research.contracts import ResearchResult
from agent_data_workbench.research.workspace import RecordOutcome, ResearchWorkspace


def tool_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapped


def create_mcp(workspace: ResearchWorkspace) -> MCPServer:
    server = MCPServer(
        "workbench",
        instructions=(
            "Research this dataset with your native tools and Python SDK. "
            "All inputs are available. "
            "Use cursors to continue reads, checkpoint useful notes, "
            "publish evidence-linked findings, "
            "and save files/charts. Complete-pass mode needs an outcome for every record. "
            "workspace_info shows actual coverage; retrieving a record does not establish review."
        ),
    )

    @server.tool(structured_output=True)
    @tool_errors
    def workspace_info() -> dict[str, Any]:
        """Read the question, dataset inventory, coverage, session and saved results."""
        return workspace.info()

    @server.tool(structured_output=True)
    @tool_errors
    def search_traces(
        text: str = "",
        stratum: str = "",
        after: str | None = None,
        page_size: int = 20,
        pending_only: bool = False,
    ) -> dict[str, Any]:
        """Search all inputs with cursor pagination and complete serialized records."""
        return workspace.search(
            text=text, stratum=stratum, after=after, page_size=page_size, pending_only=pending_only
        )

    @server.tool(structured_output=True)
    @tool_errors
    def read_trace(
        trace_id: str, pointer: str = "", offset: int = 0, max_chars: int | None = None
    ) -> dict[str, Any]:
        """Read a complete original field. Set max_chars explicitly for resumable text pages."""
        return workspace.read(trace_id, pointer=pointer, offset=offset, max_chars=max_chars)

    @server.tool(structured_output=True)
    @tool_errors
    def aggregate_traces(
        pointer: str,
        text: str = "",
        stratum: str = "",
        offset: int = 0,
        page_size: int = 50,
        results: bool = False,
    ) -> dict[str, Any]:
        """Compute over the entire matching dataset or saved outcomes; paginate distinct values."""
        return workspace.dataset.aggregate(
            pointer, text=text, stratum=stratum, offset=offset, page_size=page_size, results=results
        )

    @server.tool(structured_output=True)
    @tool_errors
    def read_context() -> dict[str, Any]:
        """Read the captured project objective and accepted knowledge in full."""
        return workspace.value["context"]

    @server.tool(structured_output=True)
    @tool_errors
    def checkpoint(note: str) -> dict[str, Any]:
        """Persist progress, hypotheses, counterexamples or next steps without ending research."""
        return workspace.checkpoint(note)

    @server.tool(structured_output=True)
    @tool_errors
    def record_outcomes(outcomes: list[RecordOutcome]) -> dict[str, Any]:
        """Checkpoint per-trace analysis outcomes. Errors remain unfinished and may be retried."""
        return workspace.record_outcomes(outcomes)

    @server.tool(structured_output=True)
    @tool_errors
    def publish_findings(result: ResearchResult, complete: bool = True) -> dict[str, Any]:
        """Save structured findings after checking citations. Use complete=false for a draft."""
        return workspace.publish(result, complete=complete)

    @server.tool(structured_output=True)
    @tool_errors
    def publish_tasks(tasks: list[TaskSpec]) -> dict[str, Any]:
        """Create draft tasks with snapshot lineage; audits and review remain separate."""
        return workspace.publish_tasks(tasks)

    @server.tool(structured_output=True)
    @tool_errors
    def save_artifact(path: str, title: str, kind: str = "other") -> dict[str, Any]:
        """Publish a workspace file. Chart JSON has title, description and values[{label,value}]."""
        return workspace.attach(path, title, kind)

    return server
