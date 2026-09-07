import io
import tarfile

import pytest

from agent_data_workbench.ingest_transport import archive_files


def trace_archive(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, value in entries:
            member = tarfile.TarInfo(name)
            body = value.encode()
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
    buffer.seek(0)
    return buffer


def test_archive_keeps_relative_names_and_contents_and_removes_temporary_files():
    # Given: independent run files include a nested directory and spaces.
    bodies = {"nested/run b.jsonl": '{"message":"two"}\n', "run a.jsonl": '{"message":"one"}\n'}
    # When: a container stages the archive before importing it.
    with archive_files(trace_archive(bodies.items())) as files:
        paths = [item.path for item in files]
        observed = {item.source_path: item.path.read_text() for item in files}
    # Then: logical file names and data survive transport, and staging is cleaned up.
    assert {"files": observed, "temporary_files_exist": [path.exists() for path in paths]} == {
        "files": bodies,
        "temporary_files_exist": [False, False],
    }


@pytest.mark.parametrize(
    ("entries", "error"),
    [
        ([], "contains no JSON/JSONL"),
        ([("../run.jsonl", "{}\n")], "relative paths"),
        ([("/run.jsonl", "{}\n")], "relative paths"),
        ([("run.txt", "{}\n")], "Unsupported trace file"),
        ([("run.jsonl", "{}\n"), ("./run.jsonl", "{}\n")], "Duplicate trace file"),
    ],
)
def test_invalid_archive_is_rejected_before_yielding_any_import_source(entries, error):
    # Given: a transport archive cannot unambiguously represent the selected trace files.
    yielded = False
    # When / Then: the caller receives no source, so it cannot start a partial import.
    with pytest.raises(ValueError, match=error):
        with archive_files(trace_archive(entries)):
            yielded = True
    assert {"source_yielded": yielded} == {"source_yielded": False}


def test_symlink_members_are_not_materialized(tmp_path):
    # Given: a member tries to replace a run file with a link outside the staged input.
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"private":"unchanged"}\n')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("run.jsonl")
        member.type = tarfile.SYMTYPE
        member.linkname = str(outside)
        archive.addfile(member)
    buffer.seek(0)
    # When / Then: links are rejected and the outside file remains unchanged.
    with pytest.raises(ValueError, match="regular files"):
        with archive_files(buffer):
            pytest.fail("Invalid archive was exposed to ingestion")
    assert {"outside": outside.read_text()} == {"outside": '{"private":"unchanged"}\n'}


def test_truncated_member_is_rejected_before_import():
    # Given: a complete header promises more data than the transport supplied.
    member = tarfile.TarInfo("run.jsonl")
    member.size = 4096
    buffer = io.BytesIO(member.tobuf() + b'{"partial":true}\n')
    # When / Then: the incomplete batch cannot reach the store.
    with pytest.raises(ValueError, match="complete tar archive"):
        with archive_files(buffer):
            pytest.fail("Truncated archive was exposed to ingestion")


def test_hardlinked_run_files_are_imported_once_using_the_first_logical_name():
    # Given: host tar represents two names for the same physical trace with a hardlink.
    buffer = io.BytesIO()
    body = b'{"session_id":"run","event":"start"}\n'
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        original = tarfile.TarInfo("z-run.jsonl")
        original.size = len(body)
        archive.addfile(original, io.BytesIO(body))
        alias = tarfile.TarInfo("a-run.jsonl")
        alias.type = tarfile.LNKTYPE
        alias.linkname = "z-run.jsonl"
        archive.addfile(alias)
    buffer.seek(0)
    # When: the same archive enters the Docker import transport.
    with archive_files(buffer) as files:
        observed = [{"name": item.source_path, "body": item.path.read_bytes()} for item in files]
    # Then: the physical run is deduplicated exactly as native file discovery does.
    assert observed == [{"name": "a-run.jsonl", "body": body}]
