"""Read Harbor JSON without losing malformed upstream evidence."""

from pathlib import Path

from agent_data_workbench.shared.json import read_json


def read_artifact(path: Path) -> tuple[dict, str | None]:
    try:
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value, None
    except ValueError as exc:
        error = f"Invalid Harbor JSON in {path.name}: {exc}"
        return {"artifact_error": error, "raw_text": path.read_text(encoding="utf-8")}, error
