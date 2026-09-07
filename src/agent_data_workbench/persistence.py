"""Atomic text persistence shared by project and evaluation artifacts."""

import os
import tempfile
from pathlib import Path


def atomic_text(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".agent-data-workbench-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
