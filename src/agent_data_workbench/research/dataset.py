"""Disk-backed investigation inputs, per-record outcomes, and resumable coverage."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

from sqlalchemy import URL, Boolean, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import NullPool

from ..identifiers import new_id
from ..models import Trace, json_text, pointer_value
from ..project import digest, now
from ..store import TraceStore


class Base(DeclarativeBase):
    pass


class InputRow(Base):
    __tablename__ = "inputs"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    group_id: Mapped[str] = mapped_column(Text, index=True)
    stratum: Mapped[str] = mapped_column(Text, index=True)
    data: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    retrieved: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(Text, default="pending", index=True)
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    at: Mapped[str] = mapped_column(Text, index=True)
    kind: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)


class Dataset:
    def __init__(self, path: Path, *, create: bool = False):
        if not create and not path.is_file():
            raise ValueError("Investigation dataset is missing")
        self.path = path
        self.outcome_lock = nullcontext
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(path)),
            connect_args={"timeout": 30, "autocommit": False},
            poolclass=NullPool,
        )
        if create:
            Base.metadata.create_all(self.engine)

    @contextmanager
    def connect(self):
        with Session(self.engine) as db, db.begin():
            yield db

    def capture(self, source: TraceStore) -> dict:
        """Freeze every eligible record in one transaction without buffering the corpus."""
        inventory_hash, total, strata = hashlib.sha256(), 0, Counter()
        inventory_hash.update(b"[")
        with self.connect() as db:
            batch = []
            for row in source.iter_rows():
                sha = digest(json.loads(row["data"]))
                entry = [row["id"], sha, row["group_id"], row["stratum"]]
                if total:
                    inventory_hash.update(b", ")
                inventory_hash.update(json_text(entry).encode())
                total += 1
                strata[row["stratum"]] += 1
                batch.append(dict(row, sha256=sha))
                if len(batch) >= 500:
                    db.execute(InputRow.__table__.insert(), batch)
                    batch = []
            if batch:
                db.execute(InputRow.__table__.insert(), batch)
        inventory_hash.update(b"]")
        return {
            "total": total,
            "strata": dict(strata),
            "sha256": inventory_hash.hexdigest(),
            "excluded_groups": len(source.exclude_groups),
        }

    def coverage(self) -> dict:
        with self.connect() as db:
            counts = dict(
                db.execute(select(InputRow.status, func.count()).group_by(InputRow.status)).all()
            )
            retrieved = db.scalar(
                select(func.count()).select_from(InputRow).where(InputRow.retrieved)
            )
        return {
            "total": sum(counts.values()),
            "retrieved": retrieved,
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "pending": counts.get("pending", 0),
        }

    def rows(
        self,
        *,
        after: str | None = None,
        text: str = "",
        stratum: str = "",
        pending_only: bool = False,
        page_size: int = 100,
    ) -> list[dict]:
        if page_size < 1:
            raise ValueError("Page size must be positive")
        statement = select(InputRow).order_by(InputRow.id).limit(page_size)
        if after is not None:
            statement = statement.where(InputRow.id > after)
        if text:
            statement = statement.where(func.instr(func.lower(InputRow.data), func.lower(text)) > 0)
        if stratum:
            statement = statement.where(InputRow.stratum == stratum)
        if pending_only:
            statement = statement.where(InputRow.status != "completed")
        with self.connect() as db:
            return [
                {
                    "trace_id": row.id,
                    "data": json.loads(row.data),
                    "group_id": row.group_id,
                    "stratum": row.stratum,
                    "status": row.status,
                    "output": json.loads(row.output) if row.output is not None else None,
                    "error": row.error,
                    "method": row.method,
                }
                for row in db.scalars(statement)
            ]

    def records(
        self, *, pending_only: bool = False, page_size: int = 100, text: str = "", stratum: str = ""
    ) -> Iterator[Trace]:
        """Read the complete snapshot in pages. Page size never limits total coverage."""
        after = None
        while rows := self.rows(
            after=after, pending_only=pending_only, page_size=page_size, text=text, stratum=stratum
        ):
            self.mark_retrieved([r["trace_id"] for r in rows])
            for row in rows:
                yield Trace(trace_id=row["trace_id"], data=row["data"])
            after = rows[-1]["trace_id"]

    def get(self, trace_id: str, *, mark: bool = True) -> Trace:
        with self.connect() as db:
            row = db.get(InputRow, trace_id)
            if row is None:
                raise ValueError("Unknown trace ID in this investigation")
            if mark:
                row.retrieved = True
            return Trace(trace_id=row.id, data=json.loads(row.data))

    def mark_retrieved(self, ids: list[str]) -> None:
        from sqlalchemy import update

        with self.connect() as db:
            db.execute(update(InputRow).where(InputRow.id.in_(ids)).values(retrieved=True))

    def record(
        self, trace_id: str, *, output: dict | None = None, error: str | None = None, method: str
    ) -> None:
        if not method.strip() or (output is None) == (error is None):
            raise ValueError("Supply a method and either a result object or an error")
        if output is not None and not isinstance(output, dict):
            raise ValueError("Record analysis must return a JSON object")
        encoded = json_text(output) if output is not None else None
        with self.outcome_lock(), self.connect() as db:
            row = db.get(InputRow, trace_id)
            if row is None:
                raise ValueError("Unknown trace ID in this investigation")
            row.status = "completed" if output is not None else "failed"
            row.output, row.error, row.method = encoded, error, method
            row.retrieved = True

    def process(
        self, function: Callable[[Trace], dict], *, method: str, page_size: int = 100
    ) -> dict:
        """Apply developer/agent code to unfinished records and checkpoint every outcome."""
        if not method.strip():
            raise ValueError("Supply the analysis method")
        for trace in self.records(pending_only=True, page_size=page_size):
            try:
                output = function(trace)
                if not isinstance(output, dict):
                    raise ValueError("Record analysis must return a JSON object")
                self.record(trace.trace_id, output=output, method=method)
            except Exception as exc:
                self.record(trace.trace_id, error=str(exc), method=method)
        return self.coverage()

    def aggregate(
        self,
        pointer: str,
        *,
        text: str = "",
        stratum: str = "",
        offset: int = 0,
        page_size: int = 50,
        results: bool = False,
    ) -> dict:
        from ..models import pointer_parts

        pointer_parts(pointer)
        if offset < 0 or page_size < 1:
            raise ValueError("Use a nonnegative offset and positive page size")
        counts, total, missing, n, mean, minimum, maximum = Counter(), 0, 0, 0, 0.0, None, None
        after = None
        while rows := self.rows(after=after, text=text, stratum=stratum):
            for row in rows:
                total += 1
                try:
                    value = pointer_value(row["output"] if results else row["data"], pointer)
                except ValueError, TypeError:
                    missing += 1
                    continue
                if isinstance(value, (dict, list)):
                    missing += 1
                    continue
                counts[json_text(value)] += 1
                if type(value) in (int, float):
                    n += 1
                    mean += (value - mean) / n
                    minimum = value if minimum is None else min(minimum, value)
                    maximum = value if maximum is None else max(maximum, value)
            after = rows[-1]["trace_id"]
        entries = counts.most_common()
        next_offset = offset + page_size if offset + page_size < len(entries) else None
        return {
            "pointer": pointer,
            "source": "outcomes" if results else "traces",
            "eligible": total,
            "missing_or_non_scalar": missing,
            "distinct": len(entries),
            "counts": [
                {"value": json.loads(k), "count": v}
                for k, v in entries[offset : offset + page_size]
            ],
            "next_offset": next_offset,
            "numeric_count": n,
            "mean": mean if n else None,
            "minimum": minimum,
            "maximum": maximum,
        }

    def event(self, kind: str, note: str, details: Any = None) -> None:
        with self.connect() as db:
            db.add(
                EventRow(id=new_id(), at=now(), kind=kind, note=note, details=json_text(details))
            )

    def events(self, *, offset: int = 0, page_size: int = 50) -> dict:
        if offset < 0 or page_size < 1:
            raise ValueError("Use a nonnegative offset and positive page size")
        with self.connect() as db:
            total = db.scalar(select(func.count()).select_from(EventRow))
            rows = db.scalars(
                select(EventRow).order_by(EventRow.at, EventRow.id).offset(offset).limit(page_size)
            )
            items = [
                {
                    "id": r.id,
                    "at": r.at,
                    "kind": r.kind,
                    "note": r.note,
                    "details": json.loads(r.details),
                }
                for r in rows
            ]
        return {
            "items": items,
            "total": total,
            "next_offset": offset + len(items) if offset + len(items) < total else None,
        }

    def export(self, path: Path) -> dict:
        """Export every record outcome, including pending and failed records."""
        after, count = None, 0
        with path.open("w", encoding="utf-8") as stream:
            while rows := self.rows(after=after):
                for row in rows:
                    stream.write(
                        json_text(
                            {k: row[k] for k in ("trace_id", "status", "output", "error", "method")}
                        )
                        + "\n"
                    )
                    count += 1
                after = rows[-1]["trace_id"]
        return {"path": str(path), "records": count, "coverage": self.coverage()}
