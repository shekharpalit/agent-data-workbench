from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import URL, Column, Index, MetaData, Table, Text, create_engine, insert, select
from test_workbench_data import Source

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.shared.json import digest, json_text
from agent_data_workbench.workspace.project import Project


def test_existing_six_column_database_keeps_records_hashes_and_import_timestamps(tmp_path):
    # Given: the pre-SQLAlchemy schema, created independently of the current model.
    project = Project.create(tmp_path / "existing #? café", "Legacy", "Keep data")
    metadata = MetaData()
    legacy = Table(
        "traces",
        metadata,
        Column("id", Text, primary_key=True, nullable=True),
        Column("group_id", Text, nullable=False),
        Column("stratum", Text, nullable=False),
        Column("data", Text, nullable=False),
        Column("sha256", Text, nullable=False),
        Column("imported_at", Text, nullable=False),
    )
    Index("trace_group", legacy.c.group_id)
    Index("trace_stratum", legacy.c.stratum)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(project.root / "traces.sqlite3")),
        connect_args={"autocommit": False},
    )
    metadata.create_all(engine)
    data = {
        "trace_id": "r'1",
        "thread_id": "episode-1",
        "agent_type": "support",
        "text": "Café costs 50%_done",
        "payload": {"number": 1, "boolean": True, "string": "1"},
    }
    original = {
        "id": "r'1",
        "group_id": "episode-1",
        "stratum": "support",
        "data": json_text(data),
        "sha256": digest(data),
        "imported_at": "2026-01-01T00:00:00+00:00",
    }
    with engine.begin() as connection:
        connection.execute(insert(legacy), original)
    engine.dispose()
    # When
    store = TraceStore(project)
    repeated = store.ingest(Source([data]))
    appended = store.ingest(Source([{"trace_id": "next", "value": 2}]))
    with store.connect() as session:
        saved = dict(session.execute(select(legacy).where(legacy.c.id == "r'1")).mappings().one())
    # Then
    assert {
        "record": store.get("r'1").model_dump(),
        "saved_row": saved,
        "repeated": {key: repeated[key] for key in ("added", "unchanged", "total")},
        "append": {key: appended[key] for key in ("added", "unchanged", "total")},
        "literal_substring": store.select(text="%_")["ids"],
    } == {
        "record": {"trace_id": "r'1", "data": data},
        "saved_row": original,
        "repeated": {"added": 0, "unchanged": 1, "total": 1},
        "append": {"added": 1, "unchanged": 0, "total": 2},
        "literal_substring": ["r'1"],
    }


def test_duplicate_records_within_one_stream_are_idempotent(tmp_path):
    # Given
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Test imports"))
    data = {"trace_id": "one", "value": 1}
    # When
    result = store.ingest(Source([data, data]))
    # Then
    assert {key: result[key] for key in ("added", "unchanged", "total")} == {
        "added": 1,
        "unchanged": 1,
        "total": 1,
    }


def test_conflict_inside_a_new_batch_rolls_back_and_allows_a_clean_retry(tmp_path):
    # Given
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Test rollback"))
    before = store.inventory()
    # When / Then
    with pytest.raises(ValueError, match="different content"):
        store.ingest(Source([{"trace_id": "one", "value": 1}, {"trace_id": "one", "value": 2}]))
    assert store.inventory() == before
    # When
    recovered = store.ingest(Source([{"trace_id": "one", "value": 3}]))
    # Then
    assert {
        "import": {key: recovered[key] for key in ("added", "unchanged", "total")},
        "record": store.get("one").model_dump(),
    } == {
        "import": {"added": 1, "unchanged": 0, "total": 1},
        "record": {"trace_id": "one", "data": {"trace_id": "one", "value": 3}},
    }


def test_first_use_and_shared_store_reads_work_across_worker_threads(tmp_path):
    # Given
    project = Project.create(tmp_path / "project", "Agent", "Test worker sessions")
    # When
    with ThreadPoolExecutor(max_workers=4) as workers:
        stores = list(workers.map(lambda _: TraceStore(project), range(4)))
        inventories = list(workers.map(lambda store: store.inventory(), stores))
        stores[0].ingest(Source([{"trace_id": "one", "value": 1}]))
        records = list(workers.map(lambda _: stores[0].get("one").model_dump(), range(4)))
    # Then
    assert {
        "totals": [inventory["total"] for inventory in inventories],
        "records": records,
    } == {
        "totals": [0, 0, 0, 0],
        "records": [{"trace_id": "one", "data": {"trace_id": "one", "value": 1}}] * 4,
    }


def test_streaming_across_batches_preserves_order_and_releases_interrupted_reads(tmp_path):
    # Given
    store = TraceStore(Project.create(tmp_path / "project", "Agent", "Test streaming"))
    store.ingest(Source([{"trace_id": f"r{i:03d}"} for i in range(250)]))
    # When
    iterator = store.iter_rows()
    first = next(iterator)["id"]
    iterator.close()
    appended = store.ingest(Source([{"trace_id": "r250"}]))
    ids = [row["id"] for row in store.iter_rows()]
    # Then
    assert {"first": first, "total": appended["total"], "ids": ids} == {
        "first": "r000",
        "total": 251,
        "ids": [f"r{i:03d}" for i in range(251)],
    }
