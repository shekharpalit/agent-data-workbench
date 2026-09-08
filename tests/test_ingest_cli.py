import io
import json
import tarfile
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_data_workbench.cli import app
from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.shared.json import digest
from agent_data_workbench.workspace.project import Project

runner = CliRunner()


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def expected_import(
    records, *, files, layout="runs", added=None, unchanged=0, groups=None, strata=None
):
    groups = groups or {}
    strata = strata or {}
    return {
        "files": files,
        "layout": layout,
        "added": len(records) if added is None else added,
        "unchanged": unchanged,
        "total": len(records),
        "strata": dict(Counter(strata.get(key, "unclassified") for key in records)),
        "sha256": digest(
            [
                (key, digest(data), groups.get(key, key), strata.get(key, "unclassified"))
                for key, data in sorted(records.items())
            ]
        ),
        "excluded_groups": 0,
    }


def test_ingest_multiple_files_keeps_each_ordered_run_together(tmp_path, monkeypatch):
    # Given: two runs contain multiple events, with shared run IDs rather than unique event IDs.
    monkeypatch.chdir(tmp_path)
    project = Project.create(tmp_path / "project", "Agent", "Compare complete runs")
    runs = {
        "alpha": [
            {"trace_id": "alpha", "role": "user", "content": "Question"},
            {"trace_id": "alpha", "role": "assistant", "content": "Answer"},
        ],
        "beta": [
            {"trace_id": "beta", "type": "tool_call", "name": "search"},
            {"trace_id": "beta", "type": "tool_result", "result": {"found": True}},
        ],
    }
    for key, events in runs.items():
        write_jsonl(Path(f"{key}.jsonl"), events)
    expected = {
        key: {"events": events, "source": {"path": f"{key}.jsonl"}} for key, events in runs.items()
    }

    # When
    result = runner.invoke(app, ["ingest", str(project.root), "alpha.jsonl", "beta.jsonl"])
    store = TraceStore(project)

    # Then
    assert {
        "exit_code": result.exit_code,
        "output": json.loads(result.output),
        "traces": {key: store.get(key).model_dump() for key in runs},
    } == {
        "exit_code": 0,
        "output": expected_import(expected, files=2),
        "traces": {key: {"trace_id": key, "data": data} for key, data in expected.items()},
    }


def test_ingest_directory_and_quoted_glob_share_reimport_identity(tmp_path, monkeypatch):
    # Given: run files span a directory and a nested directory with a nontrace file alongside.
    monkeypatch.chdir(tmp_path)
    project = Project.create(tmp_path / "project", "Agent", "Import a run collection")
    write_jsonl(Path("traces/alpha.jsonl"), [{"trace_id": "alpha", "text": "A"}])
    write_jsonl(Path("traces/nested/beta.ndjson"), [{"trace_id": "beta", "text": "B"}])
    Path("traces/notes.txt").write_text("This is not a trace export.")
    expected = {
        "alpha": {
            "events": [{"trace_id": "alpha", "text": "A"}],
            "source": {"path": "alpha.jsonl"},
        },
        "beta": {
            "events": [{"trace_id": "beta", "text": "B"}],
            "source": {"path": "nested/beta.ndjson"},
        },
    }

    # When
    initial = runner.invoke(app, ["ingest", str(project.root), "traces"])
    repeated = runner.invoke(
        app, ["ingest", str(project.root), "traces/**/*.jsonl", "traces/**/*.ndjson"]
    )

    # Then
    assert {
        "exit_codes": [initial.exit_code, repeated.exit_code],
        "initial": json.loads(initial.output),
        "repeated": json.loads(repeated.output),
    } == {
        "exit_codes": [0, 0],
        "initial": expected_import(expected, files=2),
        "repeated": expected_import(expected, files=2, added=0, unchanged=2),
    }


def test_ingest_record_layout_preserves_legacy_records_and_pointer_flags(tmp_path):
    # Given: each JSONL line is already a complete trace in an older export format.
    project = Project.create(tmp_path / "project", "Agent", "Keep record exports")
    records = {
        "one": {"trace_id": "one", "tags": {"group": "customer", "stratum": "support"}},
        "two": {"trace_id": "two", "tags": {"group": "customer", "stratum": "support"}},
    }
    export = tmp_path / "records.jsonl"
    write_jsonl(export, list(records.values()))

    # When
    result = runner.invoke(
        app,
        [
            "ingest",
            str(project.root),
            str(export),
            "--layout",
            "records",
            "--group-pointer",
            "/tags/group",
            "--stratum-pointer",
            "/tags/stratum",
        ],
    )
    store = TraceStore(project)

    # Then
    assert {
        "exit_code": result.exit_code,
        "output": json.loads(result.output),
        "traces": {key: store.get(key).model_dump() for key in records},
    } == {
        "exit_code": 0,
        "output": expected_import(
            records,
            files=1,
            layout="records",
            groups={"one": "customer", "two": "customer"},
            strata={"one": "support", "two": "support"},
        ),
        "traces": {key: {"trace_id": key, "data": data} for key, data in records.items()},
    }


@pytest.mark.parametrize("layout", ["runs", "records"])
def test_ingest_invalid_later_file_rolls_back_entire_batch(tmp_path, layout):
    # Given: an existing dataset and a two-file import whose second file is malformed.
    project = Project.create(tmp_path / "project", "Agent", "Atomic batch imports")
    existing = tmp_path / "existing.jsonl"
    write_jsonl(existing, [{"trace_id": "existing", "text": "Keep this"}])
    seed = runner.invoke(app, ["ingest", str(project.root), str(existing), "--layout", layout])
    assert {"seed_exit": seed.exit_code} == {"seed_exit": 0}
    store = TraceStore(project)
    before = store.inventory()
    good, bad = tmp_path / "a-good.jsonl", tmp_path / "z-bad.jsonl"
    write_jsonl(good, [{"trace_id": "new", "text": "Roll this back"}])
    bad.write_text('{"text": "valid first event"}\n{invalid-json}\n')

    # When
    result = runner.invoke(
        app, ["ingest", str(project.root), str(good), str(bad), "--layout", layout]
    )

    # Then
    assert {"exit_code": result.exit_code, "inventory": store.inventory()} == {
        "exit_code": 2,
        "inventory": before,
    }


@pytest.mark.parametrize(
    "pointer_flags",
    [[], ["--group-pointer", "/events/0/thread_id", "--stratum-pointer", "/events/0/agent_type"]],
)
def test_ingest_run_layout_preserves_grouping_with_default_and_event_pointers(
    tmp_path, monkeypatch, pointer_flags
):
    # Given: run metadata and explicit event pointers can both preserve grouping and strata.
    monkeypatch.chdir(tmp_path)
    project = Project.create(tmp_path / "project", "Agent", "Preserve task groups")
    events = [
        {"trace_id": "one", "thread_id": "customer", "agent_type": "support"},
        {"trace_id": "one", "content": "Done"},
    ]
    write_jsonl(Path("run.jsonl"), events)
    expected = {
        "one": {
            "events": events,
            "source": {"path": "run.jsonl"},
            "thread_id": "customer",
            "agent_type": "support",
        }
    }

    # When
    result = runner.invoke(app, ["ingest", str(project.root), "run.jsonl", *pointer_flags])

    # Then
    assert {"exit_code": result.exit_code, "output": json.loads(result.output)} == {
        "exit_code": 0,
        "output": expected_import(
            expected, files=1, groups={"one": "customer"}, strata={"one": "support"}
        ),
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], "Provide one or more trace paths, directories, or glob patterns"),
        (["trace.jsonl", "--archive-stdin"], "Use trace paths or --archive-stdin, not both"),
        (
            ["--archive-stdin", "--source-root", "."],
            "--source-root cannot be used with --archive-stdin; archives already name files",
        ),
    ],
)
def test_ingest_rejects_missing_or_ambiguous_sources_before_opening_project(
    tmp_path, arguments, message
):
    # Given: no project exists and the source selection is missing or ambiguous.
    missing_project = tmp_path / "missing"

    # When
    result = runner.invoke(app, ["ingest", str(missing_project), *arguments])

    # Then
    assert {
        "exit_code": result.exit_code,
        "message": result.output.strip(),
        "project_created": missing_project.exists(),
    } == {
        "exit_code": 2,
        "message": f"Error: {message}",
        "project_created": False,
    }


@pytest.mark.parametrize("layout", ["runs", "records"])
def test_ingest_archive_stream_imports_multiple_files_with_original_paths(tmp_path, layout):
    # Given: Docker transports several files through one binary tar stream.
    project = Project.create(tmp_path / "project", "Agent", "Import container traces")
    records = {
        "one": {"trace_id": "one", "content": "First run"},
        "two": {"trace_id": "two", "content": "Second run"},
    }
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for key, event in records.items():
            payload = (json.dumps(event) + "\n").encode("utf-8")
            member = tarfile.TarInfo(f"traces/{key}.jsonl")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    expected = {
        key: {"events": [event], "source": {"path": f"traces/{key}.jsonl"}}
        if layout == "runs"
        else event
        for key, event in records.items()
    }

    # When
    result = runner.invoke(
        app,
        ["ingest", str(project.root), "--archive-stdin", "--layout", layout],
        input=stream.getvalue(),
    )
    store = TraceStore(project)

    # Then
    assert {
        "exit_code": result.exit_code,
        "output": json.loads(result.output),
        "traces": {key: store.get(key).model_dump() for key in records},
    } == {
        "exit_code": 0,
        "output": expected_import(expected, files=2, layout=layout),
        "traces": {key: {"trace_id": key, "data": data} for key, data in expected.items()},
    }


def test_ingest_source_root_keeps_identity_across_separate_selections(tmp_path):
    # Given: separate daily selections belong to one stable source namespace.
    project = Project.create(tmp_path / "project", "Agent", "Preserve imported identities")
    source_root = tmp_path / "runs"
    records = {
        "one": {"trace_id": "one", "content": "Monday"},
        "two": {"trace_id": "two", "content": "Tuesday"},
    }
    for day, key in [("monday", "one"), ("tuesday", "two")]:
        write_jsonl(source_root / day / "run.jsonl", [records[key]])
    first_expected = {"one": {"events": [records["one"]], "source": {"path": "monday/run.jsonl"}}}
    all_expected = {
        **first_expected,
        "two": {"events": [records["two"]], "source": {"path": "tuesday/run.jsonl"}},
    }
    options = ["--source-root", str(source_root)]

    # When
    first = runner.invoke(
        app, ["ingest", str(project.root), str(source_root / "monday/run.jsonl"), *options]
    )
    combined = runner.invoke(app, ["ingest", str(project.root), str(source_root), *options])
    store = TraceStore(project)

    # Then
    assert {
        "exit_codes": [first.exit_code, combined.exit_code],
        "first": json.loads(first.output),
        "combined": json.loads(combined.output),
        "traces": {key: store.get(key).model_dump() for key in records},
    } == {
        "exit_codes": [0, 0],
        "first": expected_import(first_expected, files=1),
        "combined": expected_import(all_expected, files=2, added=1, unchanged=1),
        "traces": {key: {"trace_id": key, "data": data} for key, data in all_expected.items()},
    }
