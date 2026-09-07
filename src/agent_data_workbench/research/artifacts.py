"""Investigation lifecycle and source snapshots, independent of the agent runtime."""

import shutil
from pathlib import Path

from ..identifiers import canonical_uuid, new_id
from ..project import Project, now, save
from ..store import TraceStore
from ..traces import read_json
from .dataset import Dataset


def load_investigation(project: Project, key: str) -> dict:
    return read_json(project.path("investigations", key))


def research_store(project: Project, *, exclude_final: bool = False) -> TraceStore:
    return TraceStore(project, exclude_groups=project.final_groups() if exclude_final else None)


def investigation_directory(project: Project, key: str) -> Path:
    return project.path("investigations", canonical_uuid(key), "")


def start_investigation(
    project: Project,
    question: str,
    seed: int = 0,
    *,
    mode: str = "research",
    exclude_final: bool = False,
) -> dict:
    if not question.strip() or mode not in {"research", "complete"}:
        raise ValueError("Supply a question and research or complete mode")
    key = new_id()
    with project.lock():
        source = research_store(project, exclude_final=exclude_final)
        directory = investigation_directory(project, key)
        directory.mkdir(mode=0o700)
        dataset = Dataset(directory / "dataset.sqlite3", create=True)
        try:
            inventory = dataset.capture(source)
            if not inventory["total"]:
                raise ValueError("Import traces before starting an investigation")
        except Exception:
            shutil.rmtree(directory)
            raise
        context = project.context()
        value = {
            "id": key,
            "created_at": now(),
            "question": question,
            "mode": mode,
            "status": "paused",
            "source": inventory,
            "context": context,
            "seed": seed,
            "exclude_final": exclude_final,
            "session": None,
            "attempts": [],
            "result": None,
            "evidence_snapshot": [],
            "visited_ids": [],
            "attachments": [],
            "error": None,
            "protocol_version": "0.4",
        }
        save(directory / "context.json", context)
        save(project.path("investigations", key), value)
        if not exclude_final:
            for suite in project.artifacts("suites"):
                if any(t["split"] == "final" for t in suite["tasks"]):
                    suite.setdefault("research_exposure", []).append(
                        {
                            "investigation_id": key,
                            "at": now(),
                            "scope": "dataset available to research",
                        }
                    )
                    save(project.path("suites", suite["id"]), suite)
    dataset.event("created", "Investigation inputs captured", {"mode": mode, "source": inventory})
    return value


def session_active(directory: Path) -> bool:
    import fcntl

    path = directory / ".session.lock"
    if not path.exists():
        return False
    with path.open() as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def investigation_view(project: Project, key: str) -> dict:
    value = load_investigation(project, key)
    directory = investigation_directory(project, key)
    value["active"] = session_active(directory)
    path = directory / "dataset.sqlite3"
    if path.exists():
        dataset = Dataset(path)
        value["coverage"] = dataset.coverage()
        value["journal"] = dataset.events()
    else:
        value["coverage"] = {
            "total": value["source"]["total"],
            "retrieved": len(value["visited_ids"]),
            "completed": 0,
            "pending": value["source"]["total"],
            "failed": 0,
        }
        value["journal"] = {
            "items": [
                {
                    "id": str(i),
                    "at": s["at"],
                    "kind": s["decision"]["action"],
                    "note": s["decision"]["note"],
                    "details": s.get("observation"),
                }
                for i, s in enumerate(value.get("steps", []))
            ],
            "total": len(value.get("steps", [])),
            "next_offset": None,
        }
    return value
