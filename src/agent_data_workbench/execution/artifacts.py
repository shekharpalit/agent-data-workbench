"""Read explicitly named JSON artifacts captured from a target trial."""

from __future__ import annotations

import json
from pathlib import Path

from agent_data_workbench.shared.files import relative_path


def read_artifacts(trial_dir: Path, names: list[str]) -> dict:
    artifacts = {}
    for name in names:
        relative_path(name)
        path = (trial_dir / name).resolve()
        if not path.is_relative_to(trial_dir.resolve()) or not path.is_file():
            continue
        try:
            from agent_data_workbench.shared.json import _reject_constant

            artifacts[name] = json.loads(
                path.read_text(encoding="utf-8"), parse_constant=_reject_constant
            )
        except ValueError, UnicodeError:
            continue
    return artifacts
