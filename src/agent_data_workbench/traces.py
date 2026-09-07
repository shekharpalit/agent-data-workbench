"""Import JSON/JSONL without coupling to an agent framework."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import Trace, _reject_constant, json_text

MAX_FILE_BYTES = 50 * 1024 * 1024


def read_json(path: Path) -> Any:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds the alpha's 50 MiB limit: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def normalize(records: list[Any]) -> list[Trace]:
    if not records:
        raise ValueError("The trace export is empty")
    traces: list[Trace] = []
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict) or not record:
            raise ValueError(f"Record {index} must be a nonempty JSON object")
        supplied_id = record.get("trace_id", record.get("id"))
        if supplied_id is None:
            supplied_id = "trace-" + hashlib.sha256(json_text(record).encode()).hexdigest()[:16]
        if not isinstance(supplied_id, str) or not supplied_id.strip():
            raise ValueError(f"Record {index}: trace_id/id must be a nonempty string")
        if supplied_id in seen:
            raise ValueError(f"Duplicate trace ID: {supplied_id}")
        seen.add(supplied_id)
        traces.append(Trace(trace_id=supplied_id, data=record))
    return traces


def load_traces(path: Path) -> list[Trace]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Trace export exceeds 50 MiB; export a smaller batch")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        records = []
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line, parse_constant=_reject_constant))
                except ValueError as exc:
                    raise ValueError(f"Invalid JSON on line {number}") from exc
    else:
        value = read_json(path)
        if isinstance(value, dict) and "traces" in value:
            value = value["traces"]
        records = value if isinstance(value, list) else [value]
    return normalize(records)


def fingerprint(traces: list[Trace]) -> str:
    return hashlib.sha256(json_text([t.model_dump() for t in traces]).encode()).hexdigest()
