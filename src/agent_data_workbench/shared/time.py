"""UTC timestamps for persisted artifact history."""

from __future__ import annotations

from datetime import UTC, datetime


def now() -> str:
    return datetime.now(UTC).isoformat()
