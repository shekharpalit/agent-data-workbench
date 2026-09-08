from types import SimpleNamespace

import datasets
import huggingface_hub
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from agent_data_workbench.data.imports import import_dataset
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.integrations.huggingface import DatasetImport, HuggingFaceSource
from agent_data_workbench.workspace.project import Project


@pytest.fixture
def hub(tmp_path, monkeypatch):
    load_dataset = datasets.load_dataset
    load_builder = datasets.load_dataset_builder
    path = tmp_path / "records.parquet"

    def source(rows):
        pq.write_table(pa.Table.from_pylist(rows), path)
        monkeypatch.setattr(
            huggingface_hub.HfApi,
            "dataset_info",
            lambda *args, **kwargs: SimpleNamespace(
                id="synthetic/traces", sha="pinned-revision", card_data={"license": "mit"}
            ),
        )
        monkeypatch.setattr(
            datasets,
            "load_dataset_builder",
            lambda *args, **kwargs: load_builder("parquet", data_files=str(path)),
        )
        monkeypatch.setattr(
            datasets,
            "load_dataset",
            lambda *args, **kwargs: load_dataset(
                "parquet",
                data_files=str(path),
                split=kwargs["split"],
                streaming=kwargs["streaming"],
                fragment_scan_options=kwargs.get("fragment_scan_options"),
            ),
        )
        return DatasetImport(
            dataset="synthetic/traces",
            id_pointer="/trajectory_id",
            group_pointer="/instance_id",
            stratum_pointer="/repo",
        )

    return source


def test_streaming_parquet_keeps_complete_nested_records_and_reimport_is_idempotent(tmp_path, hub):
    # Given
    original = [
        {
            "trajectory_id": f"attempt-{i}",
            "instance_id": "issue-1",
            "repo": "synthetic/project",
            "resolved": i % 2,
            "trajectory": [
                {
                    "role": "tool",
                    "content": "full output α " * 10000 + "FINAL-EVIDENCE",
                    "tool_calls": [{"arguments": '{"enabled":false,"count":0}'}],
                }
            ],
            "nullable": None,
        }
        for i in range(3)
    ]
    config = hub(original)
    project = Project.create(tmp_path / "project", "Tests", "Preserve all evidence")
    # When
    first = import_dataset(project, config)
    second = import_dataset(project, config)
    store = TraceStore(project)
    # Then
    assert {
        "original_records": [store.get(row["trajectory_id"]).data for row in original],
        "first": {k: first["result"][k] for k in ("added", "unchanged", "total")},
        "second": {k: second["result"][k] for k in ("added", "unchanged", "total")},
        "selection": first["source"]["selection"],
        "revision": first["config"]["revision"],
        "metadata": [
            {k: store.metadata(row["trajectory_id"])[k] for k in ("group_id", "stratum")}
            for row in original
        ],
        "receipt_statuses": sorted(r["status"] for r in project.artifacts("imports")),
    } == {
        "original_records": original,
        "first": {"added": 3, "unchanged": 0, "total": 3},
        "second": {"added": 0, "unchanged": 3, "total": 3},
        "selection": {"limit": None, "order": "dataset order"},
        "revision": "pinned-revision",
        "metadata": [{"group_id": "issue-1", "stratum": "synthetic/project"}] * 3,
        "receipt_statuses": ["complete", "complete"],
    }


def test_explicit_row_selection_and_generated_ids_preserve_distinct_identical_attempts(
    tmp_path, hub
):
    # Given
    config = hub([{"value": "same evidence"}] * 4).model_copy(update={"id_pointer": "", "limit": 2})
    # When
    first = list(HuggingFaceSource(config).read())
    second = list(HuggingFaceSource(config).read())
    # Then
    assert {
        "rows": [r.data for r in first],
        "distinct_ids": len({r.trace_id for r in first}),
        "stable": first == second,
    } == {"rows": [{"value": "same evidence"}] * 2, "distinct_ids": 2, "stable": True}


def test_invalid_row_rolls_back_entire_dataset_import_and_records_failure(tmp_path, hub):
    # Given
    config = hub(
        [
            {"trajectory_id": "first", "content": "complete"},
            {"trajectory_id": None, "content": "invalid identity"},
        ]
    )
    project = Project.create(tmp_path / "project", "Tests", "Atomic imports")
    # When
    with pytest.raises(ValueError, match="string or integer trace ID"):
        import_dataset(project, config)
    # Then
    assert {
        "total": TraceStore(project).inventory()["total"],
        "receipt_statuses": [r["status"] for r in project.artifacts("imports")],
    } == {"total": 0, "receipt_statuses": ["error"]}


def test_unavailable_dataset_retains_an_actionable_import_receipt(tmp_path, monkeypatch):
    # Given
    from agent_data_workbench.data import imports

    project = Project.create(tmp_path / "project", "Tests", "Import failure")

    def unavailable(config):
        raise ValueError("Dataset split does not exist")

    monkeypatch.setattr(imports, "HuggingFaceSource", unavailable)
    # When
    with pytest.raises(ValueError, match="split does not exist"):
        import_dataset(project, DatasetImport(dataset="synthetic/missing"))
    # Then
    assert [
        {"status": r["status"], "error": r["error"], "resolved": r["source"]["resolved"]}
        for r in project.artifacts("imports")
    ] == [{"status": "error", "error": "Dataset split does not exist", "resolved": False}]


def test_reimport_cannot_silently_change_source_group_lineage(tmp_path, hub):
    # Given
    config = hub([{"trajectory_id": "attempt", "instance_id": "issue", "repo": "repository"}])
    project = Project.create(tmp_path / "project", "Tests", "Stable group identity")
    import_dataset(project, config)
    before = TraceStore(project).metadata("attempt")
    # When
    with pytest.raises(ValueError, match="different group/category mapping"):
        import_dataset(project, config.model_copy(update={"group_pointer": "/missing"}))
    # Then
    assert TraceStore(project).metadata("attempt") == before
