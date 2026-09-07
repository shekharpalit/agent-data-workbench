"""SQLAlchemy mapping and connection policy for the existing local trace database."""

from pathlib import Path
from threading import Lock

from sqlalchemy import URL, Index, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


class TraceRow(Base):
    __tablename__ = "traces"
    __table_args__ = (
        Index("trace_group", "group_id"),
        Index("trace_stratum", "stratum"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    group_id: Mapped[str] = mapped_column(Text)
    stratum: Mapped[str] = mapped_column(Text)
    # Keep canonical JSON as TEXT: its exact representation participates in fingerprints.
    data: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[str] = mapped_column(Text)


_schema_lock = Lock()


def trace_engine(path: Path) -> Engine:
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path)),
        connect_args={"timeout": 5, "autocommit": False},
        # Stores are short-lived in API handlers; closing a session releases its file handle.
        poolclass=NullPool,
    )
    # Avoid concurrent first-use schema creation by the local API's worker threads.
    with _schema_lock:
        Base.metadata.create_all(engine)
    return engine
