"""Discover run files with stable logical paths across import transports."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SUPPORTED_SUFFIXES = {".json", ".jsonl", ".ndjson"}


@dataclass(frozen=True)
class SourceFile:
    """A physical input and its logical path, independent of container extraction paths."""

    path: Path
    source_path: str


def discover_files(
    inputs: Iterable[str | Path], *, root: Path | None = None
) -> tuple[SourceFile, ...]:
    """Resolve files, recursive directories and globs; import each physical file once.

    A directory anchors its contents, a file anchors at its parent, and a glob
    anchors at its directory prefix before any wildcard. Multiple inputs use the
    common ancestor of those anchors. An explicit root overrides this selection.
    """
    found: dict[tuple[int, int] | str, Path] = {}
    anchors: list[Path] = []
    for supplied in inputs:
        text = os.fspath(supplied)
        path = Path(text).expanduser()
        if path.exists():
            matches = [path]
            anchors.append(path.resolve() if path.is_dir() else path.resolve().parent)
        else:
            anchor = Path(path.anchor) if path.anchor else Path(".")
            for part in path.parts[1:] if path.anchor else path.parts:
                if glob.has_magic(part):
                    break
                anchor = anchor / part
            anchors.append(anchor.resolve())
            matches = [
                Path(match)
                for match in glob.glob(os.fspath(path), recursive=True, include_hidden=True)
            ]
        candidates: list[Path] = []
        for match in matches:
            if match.is_dir():
                candidates.extend(
                    child
                    for child in match.rglob("*")
                    if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES
                )
            elif match.is_file() and match.suffix.lower() in SUPPORTED_SUFFIXES:
                candidates.append(match)
        if not candidates:
            raise ValueError(f"No JSON, JSONL or NDJSON files found for {text!r}")
        for candidate in sorted(candidates, key=lambda item: str(item.resolve())):
            resolved = candidate.resolve(strict=True)
            stat = resolved.stat()
            identity = (stat.st_dev, stat.st_ino) if stat.st_ino else str(resolved)
            previous = found.get(identity)
            if previous is None or str(resolved) < str(previous):
                found[identity] = resolved
    paths = sorted(found.values(), key=str)
    if not paths:
        raise ValueError("Supply at least one JSON, JSONL or NDJSON file, directory or glob")
    if root is None:
        root = Path(os.path.commonpath(anchors))
    else:
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Source root must be an existing directory: {root}")
    files = []
    for path in paths:
        if not path.is_relative_to(root):
            raise ValueError(f"Input {path} is outside source root {root}")
        files.append(SourceFile(path, path.relative_to(root).as_posix()))
    return tuple(files)
