"""The data workspace used by Python scripts, MCP tools and native coding agents."""

from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..identifiers import new_id
from ..models import Contract
from ..persistence import atomic_text
from ..project import Project, save
from ..tasks import TaskSpec, relative_path, write_task
from ..traces import read_json
from .artifacts import investigation_directory, investigation_view, load_investigation
from .contracts import ResearchResult
from .dataset import Dataset
from .reporting import research_report
from .validation import validate_result


class ChartValue(Contract):
    label: str
    value: float = Field(ge=0, allow_inf_nan=False)


class Chart(Contract):
    title: str
    description: str = ""
    values: list[ChartValue]


class RecordOutcome(Contract):
    trace_id: str
    output: dict | None = None
    error: str | None = None
    method: str = Field(min_length=1)


class ResearchWorkspace:
    def __init__(self, project: Project | Path | str, investigation_id: str):
        self.project = project if isinstance(project, Project) else Project(Path(project))
        self.value = load_investigation(self.project, investigation_id)
        if self.value.get("protocol_version") != "0.4":
            raise ValueError(
                "This investigation predates native sessions; start a new investigation"
            )
        self.id = self.value["id"]
        self.directory = investigation_directory(self.project, self.id)
        self.dataset = Dataset(self.directory / "dataset.sqlite3")
        self.dataset.outcome_lock = self.outcome_lock

    @contextmanager
    def outcome_lock(self):
        with self.project.lock():
            if load_investigation(self.project, self.id)["status"] == "complete":
                raise ValueError("Published outcomes are complete; start a new investigation")
            yield

    def info(self) -> dict:
        value = investigation_view(self.project, self.id)
        return {
            k: value.get(k)
            for k in (
                "id",
                "question",
                "mode",
                "status",
                "source",
                "coverage",
                "session",
                "attachments",
                "result",
                "error",
            )
        }

    def search(
        self,
        *,
        text: str = "",
        stratum: str = "",
        after: str | None = None,
        page_size: int = 20,
        pending_only: bool = False,
    ) -> dict:
        rows = self.dataset.rows(
            text=text, stratum=stratum, after=after, page_size=page_size, pending_only=pending_only
        )
        records = []
        for row in rows:
            raw = json.dumps(row["data"], ensure_ascii=False, sort_keys=True)
            records.append(
                {
                    "trace_id": row["trace_id"],
                    "stratum": row["stratum"],
                    "group_id": row["group_id"],
                    "preview": raw[:1000],
                    "total_chars": len(raw),
                    "truncated": len(raw) > 1000,
                    "status": row["status"],
                }
            )
        cursor = rows[-1]["trace_id"] if len(rows) == page_size else None
        return {"records": records, "next_cursor": cursor, "coverage": self.dataset.coverage()}

    def read(
        self, trace_id: str, *, pointer: str = "", offset: int = 0, max_chars: int | None = 16000
    ) -> dict:
        from ..models import json_text, pointer_value

        if offset < 0 or max_chars is not None and max_chars < 1:
            raise ValueError(
                "Use a nonnegative offset and positive page size, or null for full text"
            )
        trace = self.dataset.get(trace_id)
        value = pointer_value(trace.data, pointer)
        raw = value if isinstance(value, str) else json_text(value)
        end = len(raw) if max_chars is None else min(len(raw), offset + max_chars)
        return {
            "trace_id": trace_id,
            "pointer": pointer,
            "content": raw[offset:end],
            "offset": offset,
            "total_chars": len(raw),
            "next_offset": end if end < len(raw) else None,
        }

    def checkpoint(self, note: str) -> dict:
        if not note.strip():
            raise ValueError("Supply a research note")
        self.dataset.event("checkpoint", note)
        return self.dataset.coverage()

    def record_outcomes(self, outcomes: list[RecordOutcome]) -> dict:
        for outcome in outcomes:
            self.dataset.record(**outcome.model_dump())
        return self.dataset.coverage()

    def publish(self, result: ResearchResult | dict, *, complete: bool = True) -> dict:
        result = ResearchResult.model_validate(result)
        ids = {e.trace_id for f in result.analysis.findings for e in f.evidence}
        ids.update(e.trace_id for signal in result.signals for e in signal.evidence)
        ids.update(t for case in result.analysis.cases for t in case.trace_ids)
        traces = [self.dataset.get(key, mark=False) for key in sorted(ids)]
        validate_result(result, traces)
        with self.project.lock():
            value = load_investigation(self.project, self.id)
            if value["status"] == "complete":
                raise ValueError("Investigation is complete; start a new investigation")
            coverage = self.dataset.coverage()
            if (
                complete
                and value["mode"] == "complete"
                and (coverage["pending"] or coverage["failed"])
            ):
                raise ValueError("Complete-pass processing still has pending or failed records")
            value.update(
                result=result.model_dump(),
                evidence_snapshot=[t.model_dump() for t in traces],
                visited_ids=sorted(ids),
                error=None,
                published_coverage=coverage,
            )
            if complete:
                value["status"] = "complete"
            save(self.project.path("investigations", self.id), value)
            atomic_text(self.project.path("investigations", self.id, ".md"), research_report(value))
        self.dataset.event(
            "published" if complete else "draft",
            result.analysis.summary,
            {"coverage": coverage, "complete": complete},
        )
        return {"id": self.id, "status": value["status"], "coverage": coverage}

    def publish_tasks(self, tasks: list[TaskSpec]) -> dict:
        value = load_investigation(self.project, self.id)
        findings = {
            f["id"] for f in (value.get("result") or {}).get("analysis", {}).get("findings", [])
        }
        if len({t.id for t in tasks}) != len(tasks):
            raise ValueError("Task IDs must be unique")
        for task in tasks:
            if not set(task.finding_ids) <= findings:
                raise ValueError("Task references unknown investigation findings")
            for key in task.trace_ids:
                self.dataset.get(key, mark=False)
            task.context_sha256 = value["context"]["sha256"]
        with self.project.lock():
            if any(self.project.path("tasks", t.id).exists() for t in tasks):
                raise ValueError("A task ID already exists")
            saved = [write_task(self.project, t, origin=self.id) for t in tasks]
        return {"task_ids": [t["id"] for t in saved], "review": "draft"}

    def attach(
        self,
        path: str,
        title: str,
        kind: Literal["chart", "report", "data", "code", "other"] = "other",
    ) -> dict:
        relative_path(path)
        source = (self.directory / path).resolve()
        if not source.is_relative_to(self.directory.resolve()) or not source.is_file():
            raise ValueError("Choose a file inside this investigation workspace")
        if not title.strip() or kind not in {"chart", "report", "data", "code", "other"}:
            raise ValueError("Supply an artifact title and supported kind")
        chart = Chart.model_validate(read_json(source)).model_dump() if kind == "chart" else None
        key = new_id()
        folder = self.directory / "outputs"
        folder.mkdir(exist_ok=True, mode=0o700)
        destination = folder / (key + source.suffix)
        shutil.copyfile(source, destination)
        with destination.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        artifact = {
            "id": key,
            "title": title,
            "kind": kind,
            "path": str(destination.relative_to(self.directory)),
            "filename": source.name,
            "sha256": sha,
            "bytes": destination.stat().st_size,
            "chart": chart,
        }
        with self.project.lock():
            value = load_investigation(self.project, self.id)
            value["attachments"].append(artifact)
            save(self.project.path("investigations", self.id), value)
        self.dataset.event("artifact", title, {"id": key, "kind": kind})
        return artifact

    def save_chart(self, chart: Chart | dict) -> dict:
        """Publish chart content without requiring a caller-chosen workspace path."""
        chart = Chart.model_validate(chart)
        path = self.directory / (new_id() + ".json")
        try:
            save(path, chart.model_dump())
            return self.attach(path.name, chart.title, "chart")
        finally:
            path.unlink(missing_ok=True)

    def artifact_path(self, key: str) -> tuple[Path, dict]:
        from ..identifiers import canonical_uuid

        key = canonical_uuid(key)
        value = load_investigation(self.project, self.id)
        artifact = next((a for a in value["attachments"] if a["id"] == key), None)
        if artifact is None:
            raise ValueError("Unknown research artifact")
        path = (self.directory / artifact["path"]).resolve()
        if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
            raise ValueError("Research artifact is missing")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != artifact["sha256"]:
                raise ValueError("Research artifact changed since publication")
        return path, artifact
