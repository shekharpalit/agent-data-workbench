"""Private local project artifacts, reviewed knowledge, and serialized mutations."""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from .identifiers import canonical_uuid, new_id
from .models import Contract, json_text
from .persistence import atomic_text
from .traces import read_json

ARTIFACT_KINDS = {
    "knowledge",
    "investigations",
    "tasks",
    "suites",
    "experiments",
    "exports",
    "worlds",
    "improvements",
    "calibrations",
    "taxonomies",
    "coverage",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(value) -> str:
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


class ProjectConfig(Contract):
    version: str = "0.3"
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    success_criteria: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = ProjectConfig.model_validate(read_json(self.root / "project.json"))
        if self.config.version != "0.3":
            raise ValueError(
                "This project uses an older artifact format. Create a new project and reimport "
                "its traces; existing files are unchanged."
            )

    @classmethod
    def create(cls, root: Path, name: str, objective: str, criteria: list[str] | None = None):
        if root.is_symlink() or root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise ValueError("Project directory must be new or empty")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        config = ProjectConfig(name=name, objective=objective, success_criteria=criteria or [])
        save(root / "project.json", config.model_dump())
        for folder in ARTIFACT_KINDS:
            (root / folder).mkdir(mode=0o700)
        (root / ".gitignore").write_text("*\n", encoding="utf-8")
        return cls(root)

    def directory(self, kind: str) -> Path:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unknown artifact kind")
        directory = self.root / kind
        if not directory.resolve().is_relative_to(self.root):
            raise ValueError("Artifact directory escapes project")
        return directory

    def path(self, kind: str, name: str, suffix: str = ".json") -> Path:
        path = self.directory(kind) / (canonical_uuid(name) + suffix)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Artifact path escapes project")
        return path

    @contextmanager
    def lock(self):
        """Crash-safe process lock. OS releases it when the owning process exits."""
        import fcntl

        with (self.root / ".lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError(
                    "Project is busy; retry after its current operation finishes"
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def artifacts(self, kind: str) -> list[dict]:
        directory = self.directory(kind)
        return [read_json(p) for p in sorted(directory.glob("*.json"))]

    def add_knowledge(self, title: str, content: str, source: str) -> dict:
        if not title.strip() or not content.strip() or not source.strip():
            raise ValueError("Knowledge needs a title, content, and source")
        entry = {
            "id": new_id(),
            "title": title,
            "content": content,
            "source": source,
            "status": "draft",
            "revision": 1,
            "created_at": now(),
            "reviews": [],
        }
        with self.lock():
            save(self.path("knowledge", entry["id"]), entry)
        return entry

    def review_knowledge(self, key: str, status: str, note: str, content: str | None = None):
        if status not in {"accepted", "rejected", "draft"} or not note.strip():
            raise ValueError("Review needs a valid status and a note")
        with self.lock():
            path = self.path("knowledge", key)
            entry = read_json(path)
            old = digest(entry)
            if content is not None:
                if not content.strip():
                    raise ValueError("Knowledge content must be nonempty")
                entry["content"] = content
            entry.update(status=status, revision=entry["revision"] + 1)
            entry["reviews"].append(
                {"at": now(), "note": note, "status": status, "previous_sha256": old}
            )
            save(path, entry)
            return entry

    def context(self) -> dict:
        entries = [e for e in self.artifacts("knowledge") if e["status"] == "accepted"]
        value = {"project": self.config.model_dump(), "knowledge": entries}
        from .worlds import active_worlds

        worlds = active_worlds(self)
        if worlds:
            value["worlds"] = worlds
        return {**value, "sha256": digest(value)}

    def history(self, limit: int = 10) -> list[dict]:
        return [
            {k: e.get(k) for k in ("id", "created_at", "proposal", "conclusion", "summary")}
            for e in sorted(
                [e for e in self.artifacts("experiments") if e.get("split") != "final"],
                key=lambda e: e["created_at"],
                reverse=True,
            )[:limit]
        ]

    def final_groups(self, *, consumed: bool = False) -> set[str]:
        return {
            group
            for suite in self.artifacts("suites")
            if not consumed or suite.get("final_exposure") or suite.get("research_exposure")
            for task in suite["tasks"]
            if task["split"] == "final"
            for group in task["trace_groups"]
        }


def environment_identity() -> dict:
    import platform
    import sys

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "package": "0.5.0",
        "pid": os.getpid(),
    }
