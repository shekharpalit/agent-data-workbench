"""SQLAlchemy trace repository with atomic imports and deterministic retrieval."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.database import TraceRow, trace_engine
from agent_data_workbench.data.sources import TraceSource
from agent_data_workbench.shared.files import save
from agent_data_workbench.shared.json import digest, json_text, pointer_value
from agent_data_workbench.shared.time import now
from agent_data_workbench.workspace.project import Project


class TraceStore:
    def __init__(self, project: Project, *, exclude_groups: set[str] | None = None):
        self.project = project
        self.exclude_groups = exclude_groups or set()
        self.path = project.root / "traces.sqlite3"
        self.engine = trace_engine(self.path)

    @contextmanager
    def connect(self) -> Iterator[Session]:
        """One session per operation; commit on success and roll back the entire failed batch."""
        with Session(self.engine) as session, session.begin():
            yield session

    def iter_rows(self, *, text: str = "", stratum: str = "") -> Iterator[RowMapping]:
        """Stream visible rows in stable ID order without buffering the full trace corpus."""
        statement = select(TraceRow.id, TraceRow.stratum, TraceRow.group_id, TraceRow.data)
        if text:
            statement = statement.where(func.instr(func.lower(TraceRow.data), func.lower(text)) > 0)
        if stratum:
            statement = statement.where(TraceRow.stratum == stratum)
        statement = statement.order_by(TraceRow.id).execution_options(yield_per=100)
        with self.connect() as db:
            for row in db.execute(statement).mappings():
                if row["group_id"] not in self.exclude_groups:
                    yield row

    def ingest(
        self,
        source: TraceSource,
        *,
        group_pointer: str = "/thread_id",
        stratum_pointer: str = "/agent_type",
    ) -> dict:
        added = unchanged = 0
        with self.project.lock(), self.connect() as db:
            for trace in source.read():
                encoded = json_text(trace.data)
                sha = digest(trace.data)
                old = db.scalar(select(TraceRow.sha256).where(TraceRow.id == trace.trace_id))
                if old is not None:
                    if old != sha:
                        raise ValueError(
                            f"Trace ID {trace.trace_id!r} already has different content"
                        )
                    unchanged += 1
                    continue

                def label(pointer, fallback):
                    try:
                        v = pointer_value(trace.data, pointer)
                        return (
                            str(v)
                            if isinstance(v, (str, int)) and not isinstance(v, bool)
                            else fallback
                        )
                    except ValueError:
                        return fallback

                db.add(
                    TraceRow(
                        id=trace.trace_id,
                        group_id=label(group_pointer, trace.trace_id),
                        stratum=label(stratum_pointer, "unclassified"),
                        data=encoded,
                        sha256=sha,
                        imported_at=now(),
                    )
                )
                added += 1
        return {"added": added, "unchanged": unchanged, **self.inventory()}

    def inventory(self) -> dict:
        with self.connect() as db:
            statement = select(
                TraceRow.id, TraceRow.sha256, TraceRow.stratum, TraceRow.group_id
            ).order_by(TraceRow.id)
            rows = [
                r
                for r in db.execute(statement).mappings()
                if r["group_id"] not in self.exclude_groups
            ]
        return {
            "total": len(rows),
            "strata": dict(Counter(r["stratum"] for r in rows)),
            "sha256": digest([(r["id"], r["sha256"], r["group_id"], r["stratum"]) for r in rows]),
            "excluded_groups": len(self.exclude_groups),
        }

    def get(self, trace_id: str) -> Trace:
        with self.connect() as db:
            row = (
                db.execute(select(TraceRow.data, TraceRow.group_id).where(TraceRow.id == trace_id))
                .mappings()
                .first()
            )
        if row is None or row["group_id"] in self.exclude_groups:
            raise ValueError("Unknown trace ID")
        return Trace(trace_id=trace_id, data=json.loads(row["data"]))

    def metadata(self, trace_id: str) -> dict:
        with self.connect() as db:
            row = (
                db.execute(
                    select(TraceRow.id, TraceRow.group_id, TraceRow.stratum, TraceRow.sha256).where(
                        TraceRow.id == trace_id
                    )
                )
                .mappings()
                .first()
            )
        if row is None or row["group_id"] in self.exclude_groups:
            raise ValueError("Unknown trace ID")
        return dict(row)

    def select(
        self,
        *,
        text: str = "",
        stratum: str = "",
        limit: int = 20,
        seed: int = 0,
        offset: int = 0,
        sample: bool = False,
        equals_pointer: str | None = None,
        equals_json: str | None = None,
    ) -> dict:
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("Limit must be 1–200 and offset nonnegative")
        if (equals_pointer is None) != (equals_json is None):
            raise ValueError("Supply both equals_pointer and equals_json")
        expected = None
        if equals_pointer is not None:
            from agent_data_workbench.shared.json import _reject_constant, pointer_parts

            pointer_parts(equals_pointer)
            expected = json_text(json.loads(equals_json, parse_constant=_reject_constant))
        rows = []
        for row in self.iter_rows(text=text, stratum=stratum):
            if equals_pointer is not None:
                try:
                    actual = json_text(pointer_value(json.loads(row["data"]), equals_pointer))
                except ValueError:
                    continue
                if actual != expected:
                    continue
            rows.append({"id": row["id"], "stratum": row["stratum"]})
        ids = [r["id"] for r in rows]
        if sample:
            buckets = defaultdict(list)
            rng = random.Random(seed)
            for r in rows:
                buckets[r["stratum"]].append(r["id"])
            for values in buckets.values():
                rng.shuffle(values)
            ids = []
            # Round-robin strata: intentionally balanced, not a prevalence sample.
            while buckets:
                for key in sorted(list(buckets)):
                    ids.append(buckets[key].pop())
                    if not buckets[key]:
                        del buckets[key]
        selected = ids[offset : offset + limit]
        return {
            "eligible": len(rows),
            "selected": len(selected),
            "ids": selected,
            "selection": "balanced strata with seeded shuffle" if sample else "ID order",
            "seed": seed,
            "offset": offset,
            "text": text,
            "stratum": stratum,
            "records": [self.get(key).model_dump() for key in selected],
        }

    def aggregate(self, pointer: str, *, text: str = "", stratum: str = "") -> dict:
        counts, numeric, missing, total = Counter(), [], 0, 0
        for row in self.iter_rows(stratum=stratum):
            if text and text.lower() not in row["data"].lower():
                continue
            total += 1
            try:
                value = pointer_value(json.loads(row["data"]), pointer)
            except ValueError:
                missing += 1
                continue
            if isinstance(value, (dict, list)):
                missing += 1
                continue
            counts[json_text(value)] += 1
            if type(value) in (int, float):
                numeric.append(value)
        return {
            "pointer": pointer,
            "eligible": total,
            "missing_or_non_scalar": missing,
            "counts": [{"value": json.loads(k), "count": v} for k, v in counts.most_common()],
            "distinct": len(counts),
            "numeric_count": len(numeric),
            "mean": sum(numeric) / len(numeric) if numeric else None,
            "minimum": min(numeric) if numeric else None,
            "maximum": max(numeric) if numeric else None,
            "filter": {"text": text, "stratum": stratum},
        }

    def snapshot(self, ids: list[str], path: Path) -> None:
        save(path, [self.get(key).model_dump() for key in sorted(set(ids))])
