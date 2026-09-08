"""Track operation status while FastAPI executes response background tasks."""

import copy
import threading
from collections.abc import Callable

from fastapi import BackgroundTasks

from agent_data_workbench.shared.identifiers import new_id


class JobQueue:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def snapshot(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(list(self._jobs.values()))

    def launch(
        self, background_tasks: BackgroundTasks, name: str, function: Callable[[], dict]
    ) -> dict:
        """Reserve an operation before scheduling its execution through FastAPI."""
        with self._lock:
            if any(job["status"] == "running" for job in self._jobs.values()):
                raise ValueError("An operation is already running")
            key = new_id()
            self._jobs[key] = {
                "id": key,
                "name": name,
                "status": "running",
                "result": None,
                "error": None,
            }
        background_tasks.add_task(self._run, key, function)
        return {"job_id": key}

    def _run(self, key: str, function: Callable[[], dict]) -> None:
        try:
            result = function()
            with self._lock:
                self._jobs[key].update(status="complete", result=result)
        except Exception:
            with self._lock:
                self._jobs[key].update(
                    status="error",
                    error="Operation failed. Check the saved artifact and CLI; resume explicitly.",
                )
