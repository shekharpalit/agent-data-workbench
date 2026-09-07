"""Multi-file imports preserve complete runs and commit only complete batches."""

import json

import pytest

from agent_data_workbench.identifiers import stable_id
from agent_data_workbench.ingestion import FilesSource, SourceFile, discover_files
from agent_data_workbench.models import json_text
from agent_data_workbench.project import Project
from agent_data_workbench.store import TraceStore


def write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    return path


def test_many_run_files_preserve_repeated_event_ids_order_types_and_common_labels(tmp_path):
    # Given
    inputs = tmp_path / "agent traces"
    first = [
        {"trace_id": "session-a", "id": "event-1", "thread_id": "thread-a", "agent_type": "chat"},
        {"trace_id": "session-a", "id": "event-1", "value": {"boolean": True, "number": 7}},
        {"trace_id": "session-a", "id": "event-2", "message": "done"},
    ]
    second = [{"session_id": "session-b", "id": "event-1", "message": "hello"}]
    write_events(inputs / "a.jsonl", first)
    write_events(inputs / "nested" / "b.ndjson", second)
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Compare runs"))
    # When
    source = FilesSource([inputs], root=inputs)
    imported = store.ingest(source)
    repeated = store.ingest(FilesSource([inputs], root=inputs))
    # Then
    assert {
        "files": [source.source_path for source in source.files],
        "imported": {key: imported[key] for key in ("added", "unchanged", "total", "strata")},
        "repeated": {key: repeated[key] for key in ("added", "unchanged", "total")},
        "records": [store.get(key).model_dump() for key in ("session-a", "session-b")],
        "groups": [store.metadata(key)["group_id"] for key in ("session-a", "session-b")],
    } == {
        "files": ["a.jsonl", "nested/b.ndjson"],
        "imported": {
            "added": 2,
            "unchanged": 0,
            "total": 2,
            "strata": {"chat": 1, "unclassified": 1},
        },
        "repeated": {"added": 0, "unchanged": 2, "total": 2},
        "records": [
            {
                "trace_id": "session-a",
                "data": {
                    "events": first,
                    "source": {"path": "a.jsonl"},
                    "thread_id": "thread-a",
                    "agent_type": "chat",
                },
            },
            {
                "trace_id": "session-b",
                "data": {"events": second, "source": {"path": "nested/b.ndjson"}},
            },
        ],
        "groups": ["thread-a", "session-b"],
    }


def test_directories_globs_files_and_hardlink_overlaps_resolve_once_in_stable_order(tmp_path):
    # Given
    inputs = tmp_path / "path with spaces"
    first = write_events(inputs / "a.jsonl", [{"id": "event-a"}])
    second = write_events(inputs / "nested" / "b.JSONL", [{"id": "event-b"}])
    (inputs / "ignored.txt").write_text("ignored", encoding="utf-8")
    (inputs / "z.jsonl").hardlink_to(first)
    # When
    files = discover_files([second, inputs, str(inputs / "*.jsonl"), first], root=inputs)
    # Then
    assert [{"path": file.path, "source_path": file.source_path} for file in files] == [
        {"path": first, "source_path": "a.jsonl"},
        {"path": second, "source_path": "nested/b.JSONL"},
    ]


@pytest.mark.parametrize("layout", ["runs", "records"])
def test_malformed_later_file_rolls_back_every_file_in_batch(tmp_path, layout):
    # Given
    inputs = tmp_path / "traces"
    write_events(inputs / "a.jsonl", [{"trace_id": "first", "value": 1}])
    write_events(inputs / "b.jsonl", [{"trace_id": "second"}])
    with (inputs / "b.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{broken\n")
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Atomic import"))
    before = store.inventory()
    # When / Then
    with pytest.raises(ValueError, match=r"b.jsonl.*line 2"):
        store.ingest(FilesSource([inputs], layout=layout, root=inputs))
    assert store.inventory() == before


def test_conflicting_native_ids_across_files_roll_back_batch(tmp_path):
    # Given
    inputs = tmp_path / "traces"
    write_events(inputs / "a.jsonl", [{"trace_id": "same", "result": "yes"}])
    write_events(inputs / "b.jsonl", [{"trace_id": "same", "result": "no"}])
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Reject ambiguous IDs"))
    before = store.inventory()
    # When / Then
    with pytest.raises(ValueError, match="already has different content"):
        store.ingest(FilesSource([inputs], root=inputs))
    assert store.inventory() == before


def test_generated_run_ids_use_logical_file_paths_and_events_not_event_ids_or_temp_roots(tmp_path):
    # Given
    events = [{"id": "repeated-event", "nested": {"trace_id": "not-a-run-id"}}]
    first = write_events(tmp_path / "first extraction" / "a.jsonl", events)
    second = write_events(tmp_path / "second extraction" / "a.jsonl", events)
    different = write_events(tmp_path / "first extraction" / "b.jsonl", events)
    # When
    actual = [
        list(FilesSource([SourceFile(path, name)]).read())[0].model_dump()
        for path, name in ((first, "a.jsonl"), (second, "a.jsonl"), (different, "b.jsonl"))
    ]
    # Then
    assert actual == [
        {
            "trace_id": stable_id("run", json_text({"source": name, "events": events})),
            "data": {"events": events, "source": {"path": name}},
        }
        for name in ("a.jsonl", "a.jsonl", "b.jsonl")
    ]


@pytest.mark.parametrize(
    "events, expected_id, labels",
    [
        ([{"trace_id": "t", "session_id": "s"}, {"trace_id": "t"}], "t", {}),
        ([{"trace_id": "a", "session_id": "s"}, {"trace_id": "b", "session_id": "s"}], "s", {}),
        ([{"trace_id": "a", "thread_id": "one"}, {"trace_id": "b", "thread_id": "two"}], None, {}),
        ([{"agent_type": 1}, {"agent_type": True}], None, {}),
        ([{"agent_type": 1}, {"agent_type": 1}], None, {"agent_type": 1}),
    ],
)
def test_run_identity_and_promoted_metadata_require_consistent_scalar_values(
    tmp_path, events, expected_id, labels
):
    # Given
    path = write_events(tmp_path / "run.jsonl", events)
    # When
    actual = list(FilesSource([path], root=tmp_path).read())
    # Then
    assert [trace.model_dump() for trace in actual] == [
        {
            "trace_id": expected_id
            or stable_id("run", json_text({"source": "run.jsonl", "events": events})),
            "data": {"events": events, "source": {"path": "run.jsonl"}, **labels},
        }
    ]


@pytest.mark.parametrize(
    "value",
    [
        [{"session_id": "run", "message": "hi"}],
        {"session_id": "run", "messages": [{"role": "user", "content": "hi"}]},
    ],
)
def test_json_files_preserve_arrays_as_events_and_complete_objects_as_one_event(tmp_path, value):
    # Given
    path = tmp_path / "run.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    # When
    records = [trace.model_dump() for trace in FilesSource([path], root=tmp_path).read()]
    # Then
    assert records == [
        {
            "trace_id": "run",
            "data": {
                "events": value if isinstance(value, list) else [value],
                "source": {"path": "run.json"},
            },
        }
    ]


def test_records_layout_retains_row_export_contract_across_many_files(tmp_path):
    # Given
    records = [{"trace_id": "a", "message": "first"}, {"trace_id": "b", "message": "second"}]
    write_events(tmp_path / "first.jsonl", records)
    (tmp_path / "second.json").write_text(
        json.dumps({"traces": [{"trace_id": "c", "value": 3}]}), encoding="utf-8"
    )
    # When
    actual = [
        trace.model_dump()
        for trace in FilesSource([tmp_path], layout="records", root=tmp_path).read()
    ]
    # Then
    assert actual == [
        {"trace_id": record["trace_id"], "data": record}
        for record in [*records, {"trace_id": "c", "value": 3}]
    ]


@pytest.mark.parametrize(
    "contents, error", [("{}\n[]\n", "line 2"), ("\n", "empty"), ('{"value": NaN}\n', "line 1")]
)
def test_invalid_run_events_fail_with_the_source_filename(tmp_path, contents, error):
    # Given
    path = tmp_path / "bad run.jsonl"
    path.write_text(contents, encoding="utf-8")
    # When / Then
    with pytest.raises(ValueError, match=f"bad run.jsonl.*{error}"):
        list(FilesSource([path], root=tmp_path).read())


@pytest.mark.parametrize("selection", ["empty", "missing*.jsonl", "unsupported.txt"])
def test_empty_or_unmatched_inputs_are_errors(tmp_path, selection):
    # Given
    (tmp_path / "empty").mkdir()
    (tmp_path / "unsupported.txt").write_text("not traces", encoding="utf-8")
    # When / Then
    with pytest.raises(ValueError, match="No JSON, JSONL or NDJSON files found"):
        discover_files([tmp_path / selection])


def test_explicit_source_files_keep_logical_names_and_deduplicate_physical_inputs(tmp_path):
    # Given
    events = [{"session_id": "session"}]
    path = write_events(tmp_path / "temporary name.jsonl", events)
    alias = tmp_path / "alias.jsonl"
    alias.symlink_to(path)
    # When
    source = FilesSource(
        [SourceFile(path, "nested/run.jsonl"), SourceFile(alias, "nested/run.jsonl")]
    )
    # Then
    assert {
        "files": [{"path": file.path, "source_path": file.source_path} for file in source.files],
        "traces": [trace.model_dump() for trace in source.read()],
    } == {
        "files": [{"path": path, "source_path": "nested/run.jsonl"}],
        "traces": [
            {
                "trace_id": "session",
                "data": {"events": events, "source": {"path": "nested/run.jsonl"}},
            }
        ],
    }


def test_directory_file_and_glob_roots_are_independent_of_current_directory(tmp_path, monkeypatch):
    # Given
    inputs = tmp_path / "traces"
    path = write_events(inputs / "nested" / "run.jsonl", [{"session_id": "session"}])
    monkeypatch.chdir(tmp_path)
    # When
    directory = discover_files([inputs])
    globbed = discover_files([str(inputs / "**" / "*.jsonl")])
    direct = discover_files([path])
    explicit = discover_files([path], root=tmp_path)
    monkeypatch.chdir(inputs / "nested")
    repeated = discover_files([inputs])
    # Then
    assert {
        "directory": [file.source_path for file in directory],
        "globbed": [file.source_path for file in globbed],
        "direct": [file.source_path for file in direct],
        "explicit": [file.source_path for file in explicit],
        "repeated": [file.source_path for file in repeated],
    } == {
        "directory": ["nested/run.jsonl"],
        "globbed": ["nested/run.jsonl"],
        "direct": ["run.jsonl"],
        "explicit": ["traces/nested/run.jsonl"],
        "repeated": ["nested/run.jsonl"],
    }


def test_native_directory_and_container_archive_imports_have_identical_identity(tmp_path):
    # Given
    events = [{"id": "event", "message": "original run"}]
    native_root = tmp_path / "native traces"
    write_events(native_root / "nested" / "run.jsonl", events)
    extracted = write_events(tmp_path / "container temp" / "run.jsonl", events)
    # When
    native = list(FilesSource([native_root]).read())
    archive = list(FilesSource([SourceFile(extracted, "nested/run.jsonl")]).read())
    # Then
    assert {
        "native": [trace.model_dump() for trace in native],
        "archive": [trace.model_dump() for trace in archive],
    } == {
        key: [
            {
                "trace_id": stable_id(
                    "run", json_text({"source": "nested/run.jsonl", "events": events})
                ),
                "data": {"events": events, "source": {"path": "nested/run.jsonl"}},
            }
        ]
        for key in ("native", "archive")
    }


def test_multiple_inputs_use_common_ancestor_of_directory_file_and_glob_anchors(tmp_path):
    # Given
    write_events(tmp_path / "first" / "nested" / "a.jsonl", [{"session_id": "a"}])
    second = write_events(tmp_path / "second" / "b.jsonl", [{"session_id": "b"}])
    write_events(tmp_path / "third" / "deep" / "c.jsonl", [{"session_id": "c"}])
    # When
    files = discover_files([tmp_path / "first", second, str(tmp_path / "third" / "**" / "*.jsonl")])
    # Then
    assert [file.source_path for file in files] == [
        "first/nested/a.jsonl",
        "second/b.jsonl",
        "third/deep/c.jsonl",
    ]


def test_source_root_must_be_an_existing_directory_containing_inputs(tmp_path):
    # Given
    path = write_events(tmp_path / "run.jsonl", [{"session_id": "session"}])
    other = tmp_path / "other"
    other.mkdir()
    # When / Then
    with pytest.raises(ValueError, match="Source root must be an existing directory"):
        discover_files([path], root=path)
    with pytest.raises(ValueError, match="outside source root"):
        discover_files([path], root=other)
