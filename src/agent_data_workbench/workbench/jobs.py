"""One explicit model job at a time, independent of HTTP request lifetimes."""

import copy
import threading
from collections.abc import Callable

from agent_data_workbench.shared.identifiers import new_id


class JobQueue:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def snapshot(self) -> list[dict]:
        with self._lock:
            return copy.deepcopy(list(self._jobs.values()))

    def launch(self, name: str, function: Callable[[], dict]) -> dict:
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

        def work():
            try:
                result = function()
                with self._lock:
                    self._jobs[key].update(status="complete", result=result)
            except Exception:
                with self._lock:
                    self._jobs[key].update(
                        status="error",
                        error="Operation failed. Check the saved artifact and CLI; "
                        "resume explicitly.",
                    )

        threading.Thread(target=work, daemon=True).start()
        return {"job_id": key}
