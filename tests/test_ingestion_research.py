import json

from agent_data_workbench.data.ingestion import FilesSource
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.research import ResearchWorkspace, start_investigation
from agent_data_workbench.workspace.project import Project


def test_many_run_files_are_researched_together_without_losing_event_order(tmp_path):
    # Given: independent JSONL run files each contain repeated event IDs and ordered tool events.
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    expected = {}
    for name, status in [("run-a", "declined"), ("run-b", "completed")]:
        events = [
            {"session_id": name, "id": "event", "kind": "request", "message": "Refund order"},
            {"session_id": name, "id": "event", "kind": "tool", "status": status},
            {"session_id": name, "id": "event", "kind": "reply", "message": "Processed"},
        ]
        (inputs / f"{name}.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
        expected[name] = {"events": events, "source": {"path": f"{name}.jsonl"}}
    project = Project.create(tmp_path / "project", "Agent", "Compare claimed and actual outcomes")
    store = TraceStore(project)
    store.ingest(FilesSource([inputs]))
    investigation = start_investigation(
        project, "Which runs claimed an unperformed refund?", mode="complete"
    )
    workspace = ResearchWorkspace(project, investigation["id"])
    # When: one investigation reads each complete run and compares outcomes across run files.
    captured = {trace.trace_id: trace.data for trace in workspace.dataset.records(page_size=1)}
    coverage = workspace.dataset.process(
        lambda trace: {"false_success": trace.data["events"][1]["status"] == "declined"},
        method="Compare ordered tool status and final reply",
        page_size=1,
    )
    rows = workspace.dataset.rows()
    # Then: both runs share one snapshot, retain all events, and receive distinct outcomes.
    assert {
        "runs": captured,
        "coverage": coverage,
        "outcomes": {row["trace_id"]: row["output"] for row in rows},
    } == {
        "runs": expected,
        "coverage": {"total": 2, "retrieved": 2, "completed": 2, "failed": 0, "pending": 0},
        "outcomes": {"run-a": {"false_success": True}, "run-b": {"false_success": False}},
    }
