"""Create next-action task drafts from a saved conversation boundary."""

from __future__ import annotations

from agent_data_workbench.evaluation.tasks.contracts import Criterion, TaskSpec
from agent_data_workbench.evaluation.tasks.repository import write_task
from agent_data_workbench.shared.identifiers import new_id
from agent_data_workbench.shared.json import json_text
from agent_data_workbench.workspace.project import Project


def replay_task(project: Project, trace_id: str, cutoff: int, title: str) -> dict:
    from agent_data_workbench.data.store import TraceStore

    trace = TraceStore(project).get(trace_id)
    messages = trace.data.get("messages")
    if not isinstance(messages, list) or not 0 < cutoff < len(messages):
        raise ValueError("Trace needs messages and a cutoff before an existing later message")
    key = new_id()
    task = TaskSpec(
        id=key,
        title=title,
        purpose="Evaluate the next action at a saved boundary",
        behavior="next_action",
        trace_ids=[trace_id],
        fidelity="next_action",
        input_json=json_text({"messages": messages[:cutoff]}),
        context_sha256=project.context()["sha256"],
        missing_context=["Define the expected behavior, relevant tools, and audit examples"],
        criteria=[
            Criterion(
                id=new_id(),
                description="Replace with a reviewed criterion",
                source="output",
                kind="semantic",
                rubric="Underspecified",
            )
        ],
    )
    with project.lock():
        return write_task(project, task, origin="replay-prefix")
