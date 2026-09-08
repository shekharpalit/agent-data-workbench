"""Build one trace per run file while preserving ordered original events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Literal

from agent_data_workbench.data.contracts import Trace
from agent_data_workbench.data.discovery import SUPPORTED_SUFFIXES, SourceFile, discover_files
from agent_data_workbench.data.sources import JsonSource
from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.shared.json import _reject_constant, json_text

ImportLayout = Literal["runs", "records"]


def _events(source: SourceFile) -> list[dict]:
    path = source.path
    events: list[dict] = []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line, parse_constant=_reject_constant)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid JSON in {source.source_path!r} on line {number}: {exc}"
                    ) from exc
                if not isinstance(event, dict):
                    raise ValueError(
                        f"Invalid event in {source.source_path!r} on line {number}: "
                        "expected a JSON object"
                    )
                events.append(event)
    else:
        try:
            with path.open(encoding="utf-8") as stream:
                value = json.load(stream, parse_constant=_reject_constant)
        except ValueError as exc:
            raise ValueError(f"Invalid JSON in {source.source_path!r}: {exc}") from exc
        for number, event in enumerate(value if isinstance(value, list) else [value], 1):
            if not isinstance(event, dict):
                raise ValueError(
                    f"Invalid event in {source.source_path!r} at item {number}: "
                    "expected a JSON object"
                )
            events.append(event)
    if not events:
        raise ValueError(f"The run file {source.source_path!r} is empty")
    return events


def _common(events: list[dict], key: str) -> str | int | None:
    values = [event[key] for event in events if key in event]
    if not values or any(type(value) not in (str, int) for value in values):
        return None
    first = values[0]
    if isinstance(first, str) and not first.strip():
        return None
    return first if all(type(value) is type(first) and value == first for value in values) else None


def _run(source: SourceFile) -> Trace:
    events = _events(source)
    data = {"events": events, "source": {"path": source.source_path}}
    for key in ("thread_id", "agent_type"):
        common = _common(events, key)
        if common is not None:
            data[key] = common
    trace_id = next(
        (
            value
            for key in ("trace_id", "session_id")
            if isinstance(value := _common(events, key), str)
        ),
        None,
    )
    return Trace(
        trace_id=trace_id
        or stable_id("run", json_text({"source": source.source_path, "events": events})),
        data=data,
    )


class FilesSource:
    """One TraceSource for every selected file; call TraceStore.ingest only once.

    Runs layout preserves each file as one trace with ordered, unmodified events.
    Records layout retains JsonSource's one-record-per-trace export interpretation.
    Input file contents are read lazily inside the store's transaction. Memory use in
    runs layout follows the largest run file, rather than the whole input collection.
    """

    def __init__(
        self,
        inputs: Iterable[str | Path] | Iterable[SourceFile],
        *,
        layout: ImportLayout = "runs",
        root: Path | None = None,
    ):
        if layout not in {"runs", "records"}:
            raise ValueError("Import layout must be 'runs' or 'records'")
        selected = tuple(inputs)
        if selected and all(isinstance(item, SourceFile) for item in selected):
            files: list[SourceFile] = []
            seen: set[tuple[int, int] | str] = set()
            for source in sorted(selected, key=lambda item: (item.source_path, str(item.path))):
                if not source.source_path or Path(source.source_path).is_absolute():
                    raise ValueError("Source paths must be nonempty relative paths")
                if source.path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    raise ValueError(f"Unsupported input file {source.source_path!r}")
                resolved = source.path.resolve(strict=True)
                stat = resolved.stat()
                identity = (stat.st_dev, stat.st_ino) if stat.st_ino else str(resolved)
                if identity not in seen:
                    seen.add(identity)
                    files.append(SourceFile(resolved, source.source_path))
            self.files = tuple(files)
        elif any(isinstance(item, SourceFile) for item in selected):
            raise ValueError("Supply either source files or input paths, not a mixture")
        else:
            self.files = discover_files(selected, root=root)
        self.layout = layout

    def read(self) -> Iterator[Trace]:
        for source in self.files:
            if self.layout == "runs":
                yield _run(source)
            else:
                try:
                    for trace in JsonSource(source.path).read():
                        json_text(trace.data)
                        yield trace
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid trace export {source.source_path!r}: {exc}") from exc
