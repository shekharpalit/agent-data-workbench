"""Trace source protocol and streaming complete-record JSON source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.normalization import load_traces


class TraceSource(Protocol):
    def read(self) -> Iterable[Trace]: ...


class JsonSource:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> Iterable[Trace]:
        # Stream JSONL exports without imposing a corpus or record size limit.
        if self.path.suffix.lower() not in {".jsonl", ".ndjson"}:
            yield from load_traces(self.path)
            return
        from agent_data_workbench.data.normalization import normalize

        with self.path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    yield normalize([json.loads(line)])[0]
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid trace on line {number}") from exc
