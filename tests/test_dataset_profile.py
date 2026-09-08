from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.dataset import dataset_profile
from agent_data_workbench.exploration.schemas import SearchQuery
from agent_data_workbench.workspace.project import Project


def test_task_groups_and_outcome_counts_use_exact_source_fields_not_error_text(tmp_path):
    # Given
    project = Project.create(tmp_path / "project", "Tests", "Truthful charts")

    class Source:
        def read(self):
            for key, group, resolved in [
                ("a", "issue-a", 1),
                ("b", "issue-a", 0),
                ("c", "issue-b", None),
                ("d", "issue-c", "false"),
            ]:
                yield Trace(
                    trace_id=key,
                    data={
                        "instance_id": group,
                        "repo": "repo",
                        "resolved": resolved,
                        "text": "error failed exception",
                    },
                )

    store = TraceStore(project)
    store.ingest(Source(), group_pointer="/instance_id", stratum_pointer="/repo")
    # When
    result = dataset_profile(store, SearchQuery(limit=1))
    # Then
    assert {k: result[k] for k in ("eligible", "group_count", "groups", "outcomes")} == {
        "eligible": 4,
        "group_count": 3,
        "groups": [
            {
                "id": "issue-a",
                "label": "issue-a",
                "strata": ["repo"],
                "trace_ids": ["a", "b"],
                "outcomes": {"Passed": 1, "Failed": 1, "Unknown": 0},
                "count": 2,
            },
            {
                "id": "issue-b",
                "label": "issue-b",
                "strata": ["repo"],
                "trace_ids": ["c"],
                "outcomes": {"Passed": 0, "Failed": 0, "Unknown": 1},
                "count": 1,
            },
            {
                "id": "issue-c",
                "label": "issue-c",
                "strata": ["repo"],
                "trace_ids": ["d"],
                "outcomes": {"Passed": 0, "Failed": 0, "Unknown": 1},
                "count": 1,
            },
        ],
        "outcomes": [
            {"value": "Passed", "count": 1},
            {"value": "Failed", "count": 1},
            {"value": "Unknown", "count": 2},
        ],
    }
    # When / Then
    assert dataset_profile(store, SearchQuery(trace_ids=["b"]))["outcomes"] == [
        {"value": "Passed", "count": 0},
        {"value": "Failed", "count": 1},
        {"value": "Unknown", "count": 0},
    ]
