"""Resolve trusted argv and fingerprint every directly invoked file."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pinned_command(
    command: list[str], source_files: list[str], base_dir: Path
) -> tuple[list, dict]:
    args = list(command)
    sources = {}
    for filename in source_files:
        path = (base_dir / filename).resolve()
        if not path.is_file():
            raise ValueError("Declared command source file does not exist")
        sources[str(path)] = file_sha256(path)
    if not args:
        return args, sources
    executable = Path(args[0])
    if executable.is_absolute():
        resolved = executable.resolve()
    elif "/" in args[0]:
        resolved = (base_dir / executable).resolve()
    else:
        located = shutil.which(args[0])
        if not located:
            raise ValueError("Command executable not found")
        resolved = Path(located).resolve()
    if not resolved.is_file():
        raise ValueError("Command executable not found")
    args[0] = str(resolved)
    sources[str(resolved)] = file_sha256(resolved)
    for index, arg in enumerate(args[1:], 1):
        if not arg.startswith("-"):
            path = (base_dir / arg).resolve()
            if path.is_file():
                args[index] = str(path)
                sources[str(path)] = file_sha256(path)
    return args, sources


def check_sources(sources: dict[str, str]) -> None:
    for filename, sha256 in sources.items():
        if file_sha256(Path(filename)) != sha256:
            raise ValueError("Declared execution source changed after identity was captured")
